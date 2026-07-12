import argparse
import asyncio
import json
import os
import time
import urllib.request
from collections import deque
from datetime import datetime, timezone

import websockets

from stats_utils import bootstrap_ci, wilson_ci

WS_BASE = "wss://fstream.binance.com/stream"
REST_BASE = "https://fapi.binance.com/fapi/v1"
UA = {"User-Agent": "liquidation-cascade-live/1.0 (paper-only)"}
DEFAULT_SYMBOLS = ("BTCUSDT", "ETHUSDT", "SOLUSDT")
DEFAULT_HORIZONS = (30, 60, 120, 300)


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def atomic_write(path, value):
    absolute = os.path.abspath(path)
    os.makedirs(os.path.dirname(absolute), exist_ok=True)
    temporary = absolute + ".tmp"
    with open(temporary, "w", encoding="utf-8") as handle:
        json.dump(value, handle, indent=2, sort_keys=True)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, absolute)


def append_jsonl(path, value):
    absolute = os.path.abspath(path)
    os.makedirs(os.path.dirname(absolute), exist_ok=True)
    with open(absolute, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(value, separators=(",", ":")) + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def load_state(path, symbols, horizons, config=None):
    if os.path.exists(path):
        with open(path, encoding="utf-8") as handle:
            state = json.load(handle)
        if (
            state.get("symbols") != list(symbols)
            or state.get("horizons_s") != list(horizons)
            or state.get("config") != config
        ):
            raise ValueError("estado pertence a outra configuracao")
        return state
    return {
        "version": 1,
        "paper_only": True,
        "symbols": list(symbols),
        "horizons_s": list(horizons),
        "config": config,
        "liquidations_seen": 0,
        "cascades": [],
        "results": [],
        "created_utc": utc_now(),
        "updated_utc": utc_now(),
    }


def fetch_book(symbol):
    request = urllib.request.Request(f"{REST_BASE}/ticker/bookTicker?symbol={symbol}", headers=UA)
    with urllib.request.urlopen(request, timeout=10) as response:
        item = json.loads(response.read().decode())
    return {
        "bid": float(item["bidPrice"]),
        "ask": float(item["askPrice"]),
        "observed_ms": int(item.get("time", time.time() * 1000)),
    }


def parse_liquidation(message):
    wrapper = json.loads(message)
    payload = wrapper.get("data", wrapper)
    if payload.get("e") != "forceOrder":
        return None
    order = payload.get("o", {})
    symbol = order.get("s")
    side = order.get("S")
    price = float(order.get("ap", 0) or order.get("p", 0) or 0)
    quantity = float(order.get("z", 0) or order.get("q", 0) or 0)
    event_ms = int(payload.get("E", order.get("T", time.time() * 1000)))
    if not symbol or side not in ("BUY", "SELL") or price <= 0 or quantity <= 0:
        return None
    return {
        "event_ms": event_ms,
        "event_utc": datetime.fromtimestamp(event_ms / 1000, tz=timezone.utc).isoformat(),
        "symbol": symbol,
        "side": side,
        "direction": "SHORT" if side == "SELL" else "LONG",
        "price": price,
        "quantity": quantity,
        "notional_usd": price * quantity,
    }


def detect_cascade(events, event, cascades, window_s, min_count, cooldown_s, min_notional_usd):
    cutoff = event["event_ms"] - window_s * 1000
    matching = [
        item for item in events
        if item["event_ms"] >= cutoff
        and item["symbol"] == event["symbol"]
        and item["direction"] == event["direction"]
    ]
    total_notional = sum(item["notional_usd"] for item in matching)
    recent = [
        item for item in cascades
        if item["symbol"] == event["symbol"]
        and item["direction"] == event["direction"]
        and event["event_ms"] - item["trigger_ms"] < cooldown_s * 1000
    ]
    if len(matching) < min_count or total_notional < min_notional_usd or recent:
        return None
    return {
        "cascade_id": f"{event['symbol']}-{event['direction']}-{event['event_ms']}",
        "trigger_ms": event["event_ms"],
        "trigger_utc": event["event_utc"],
        "symbol": event["symbol"],
        "direction": event["direction"],
        "liquidation_count": len(matching),
        "liquidation_notional_usd": total_notional,
        "resolved_horizons_s": [],
    }


def paper_pnl(direction, entry_book, exit_book, taker_fee_pct):
    if direction == "LONG":
        entry = entry_book["ask"]
        exit_price = exit_book["bid"]
        gross_pct = (exit_price - entry) / entry * 100
    else:
        entry = entry_book["bid"]
        exit_price = exit_book["ask"]
        gross_pct = (entry - exit_price) / entry * 100
    fee_pct = 2 * taker_fee_pct
    return {
        "entry_price": entry,
        "exit_price": exit_price,
        "gross_pnl_pct": gross_pct,
        "fee_pct": fee_pct,
        "net_pnl_pct": gross_pct - fee_pct,
    }


def settle_due(state, now_ms, horizons, taker_fee_pct, book_fn=fetch_book, max_delay_s=5.0):
    settled = []
    books = {}
    for cascade in state["cascades"]:
        for horizon in horizons:
            if horizon in cascade["resolved_horizons_s"]:
                continue
            target_ms = cascade["trigger_ms"] + horizon * 1000
            if now_ms < target_ms:
                continue
            symbol = cascade["symbol"]
            delay_s = max(0.0, (now_ms - target_ms) / 1000)
            if delay_s > max_delay_s:
                result = {
                    "cascade_id": cascade["cascade_id"],
                    "symbol": symbol,
                    "direction": cascade["direction"],
                    "horizon_s": horizon,
                    "trigger_ms": cascade["trigger_ms"],
                    "target_ms": target_ms,
                    "observed_ms": now_ms,
                    "settlement_delay_s": delay_s,
                    "status": "missed",
                }
            else:
                if symbol not in books:
                    books[symbol] = book_fn(symbol)
                pnl = paper_pnl(cascade["direction"], cascade["entry_book"], books[symbol], taker_fee_pct)
                result = {
                    "cascade_id": cascade["cascade_id"],
                    "symbol": symbol,
                    "direction": cascade["direction"],
                    "horizon_s": horizon,
                    "trigger_ms": cascade["trigger_ms"],
                    "target_ms": target_ms,
                    "observed_ms": books[symbol].get("observed_ms", now_ms),
                    "settlement_delay_s": delay_s,
                    "status": "settled",
                    **pnl,
                }
            state["results"].append(result)
            cascade["resolved_horizons_s"].append(horizon)
            settled.append(result)
    if settled:
        state["updated_utc"] = utc_now()
    return settled


def compute_stats(state, horizons, target_per_horizon, primary_horizon=30):
    by_horizon = {}
    passed = []
    for horizon in horizons:
        values = [
            result["net_pnl_pct"]
            for result in state["results"]
            if result["horizon_s"] == horizon and result.get("status", "settled") == "settled"
        ]
        wins = sum(value > 0 for value in values)
        ev_ci = bootstrap_ci(values) if values else (0.0, 0.0, 0.0)
        wr_ci = wilson_ci(wins, len(values))
        gate = len(values) >= target_per_horizon and ev_ci[0] > 0
        if gate:
            passed.append(horizon)
        by_horizon[str(horizon)] = {
            "n": len(values),
            "wins": wins,
            "win_rate": wins / len(values) if values else 0.0,
            "win_rate_wilson_ci95": list(wr_ci),
            "ev_pct_ci95": list(ev_ci),
            "total_pnl_pct": sum(values),
            "paper_gate_pass": gate,
        }
    return {
        "updated_utc": utc_now(),
        "paper_only": True,
        "liquidations_seen": state["liquidations_seen"],
        "cascades": len(state["cascades"]),
        "resolved_results": len(state["results"]),
        "missed_results": sum(result.get("status") == "missed" for result in state["results"]),
        "target_per_horizon": target_per_horizon,
        "horizons": by_horizon,
        "passing_horizons_s": passed,
        "primary_horizon_s": primary_horizon,
        "paper_gate_pass": primary_horizon in passed,
        "decision": "PAPER_SIGNAL" if primary_horizon in passed else "NOT_VALIDATED",
    }


def websocket_url(symbols):
    streams = "/".join(f"{symbol.lower()}@forceOrder" for symbol in symbols)
    return f"{WS_BASE}?streams={streams}"


async def validate_stream(symbols):
    async with websockets.connect(websocket_url(symbols), ping_interval=20, ping_timeout=20) as websocket:
        received = False
        try:
            await asyncio.wait_for(websocket.recv(), timeout=5)
            received = True
        except asyncio.TimeoutError:
            pass
        return {"connected": True, "event_received": received, "url_host": "fstream.binance.com"}


async def run(args):
    symbols = tuple(symbol.upper() for symbol in args.symbols)
    horizons = tuple(sorted(set(args.horizons)))
    if args.validate_only:
        print(json.dumps(await validate_stream(symbols), sort_keys=True))
        return
    if args.primary_horizon not in horizons:
        raise ValueError("primary_horizon deve estar em horizons")
    config = {
        "window_s": args.window_s,
        "min_count": args.min_count,
        "cooldown_s": args.cooldown_s,
        "min_notional_usd": args.min_notional_usd,
        "taker_fee_pct": args.taker_fee_pct,
        "target_per_horizon": args.target_per_horizon,
        "max_settlement_delay_s": args.max_settlement_delay_s,
        "primary_horizon": args.primary_horizon,
    }
    state = load_state(args.state_file, symbols, horizons, config)
    atomic_write(args.state_file, state)
    atomic_write(
        args.stats_file,
        compute_stats(state, horizons, args.target_per_horizon, args.primary_horizon),
    )
    events = deque(maxlen=10000)
    known_events = deque(maxlen=50000)
    started = time.monotonic()
    last_stats_write = 0.0
    while args.duration_s <= 0 or time.monotonic() - started < args.duration_s:
        try:
            async with websockets.connect(websocket_url(symbols), ping_interval=20, ping_timeout=20) as websocket:
                while args.duration_s <= 0 or time.monotonic() - started < args.duration_s:
                    now_ms = int(time.time() * 1000)
                    try:
                        message = await asyncio.wait_for(websocket.recv(), timeout=1)
                        event = parse_liquidation(message)
                        if event:
                            event_key = (event["symbol"], event["side"], event["event_ms"], event["price"], event["quantity"])
                            if event_key not in known_events:
                                known_events.append(event_key)
                                events.append(event)
                                state["liquidations_seen"] += 1
                                append_jsonl(args.events_file, event)
                                cascade = detect_cascade(
                                    events,
                                    event,
                                    state["cascades"],
                                    args.window_s,
                                    args.min_count,
                                    args.cooldown_s,
                                    args.min_notional_usd,
                                )
                                if cascade:
                                    cascade["entry_book"] = fetch_book(cascade["symbol"])
                                    state["cascades"].append(cascade)
                                    append_jsonl(args.cascades_file, cascade)
                                state["updated_utc"] = utc_now()
                                atomic_write(args.state_file, state)
                    except asyncio.TimeoutError:
                        pass
                    settled = settle_due(
                        state,
                        now_ms,
                        horizons,
                        args.taker_fee_pct,
                        max_delay_s=args.max_settlement_delay_s,
                    )
                    for result in settled:
                        append_jsonl(args.results_file, result)
                    if settled:
                        atomic_write(args.state_file, state)
                    if settled or time.monotonic() - last_stats_write >= 60:
                        stats = compute_stats(state, horizons, args.target_per_horizon, args.primary_horizon)
                        atomic_write(args.stats_file, stats)
                        last_stats_write = time.monotonic()
        except Exception as error:
            print(json.dumps({"utc": utc_now(), "error": str(error)}), flush=True)
            await asyncio.sleep(5)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbols", nargs="+", default=list(DEFAULT_SYMBOLS))
    parser.add_argument("--horizons", nargs="+", type=int, default=list(DEFAULT_HORIZONS))
    parser.add_argument("--window-s", type=int, default=10)
    parser.add_argument("--min-count", type=int, default=3)
    parser.add_argument("--cooldown-s", type=int, default=30)
    parser.add_argument("--min-notional-usd", type=float, default=0.0)
    parser.add_argument("--taker-fee-pct", type=float, default=0.04)
    parser.add_argument("--target-per-horizon", type=int, default=30)
    parser.add_argument("--primary-horizon", type=int, default=30)
    parser.add_argument("--max-settlement-delay-s", type=float, default=5.0)
    parser.add_argument("--duration-s", type=float, default=0.0)
    parser.add_argument("--state-file", default="d34_live_state.json")
    parser.add_argument("--events-file", default="d34_liquidations.jsonl")
    parser.add_argument("--cascades-file", default="d34_cascades.jsonl")
    parser.add_argument("--results-file", default="d34_results.jsonl")
    parser.add_argument("--stats-file", default="d34_stats.json")
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args()
    asyncio.run(run(args))


if __name__ == "__main__":
    main()
