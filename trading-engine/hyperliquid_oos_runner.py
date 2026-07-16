import argparse
import json
import os
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone

from stats_utils import bootstrap_ci, wilson_ci

HL_INFO_URL = "https://api.hyperliquid.xyz/info"
BINANCE_FAPI = "https://fapi.binance.com/fapi/v1"
UA = {"User-Agent": "hyperliquid-oos-runner/1.0 (paper-only)"}
SYMBOL_HL = "LINK"
SYMBOL_BN = "LINKUSDT"
HL_TAKER_BPS = 4.5
BINANCE_TAKER_BPS = 5.0
ROUNDTRIP_BPS = 2 * (HL_TAKER_BPS + BINANCE_TAKER_BPS)


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def atomic_write(path, data):
    absolute = os.path.abspath(path)
    os.makedirs(os.path.dirname(absolute), exist_ok=True)
    temporary = absolute + ".tmp"
    with open(temporary, "w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2, sort_keys=True)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, absolute)


def load_state(path):
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def post_hl(body, timeout=15):
    request = urllib.request.Request(
        HL_INFO_URL,
        data=json.dumps(body).encode(),
        headers={**UA, "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode())


def get_json(url, timeout=15):
    request = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode())


def hl_context():
    meta, contexts = post_hl({"type": "metaAndAssetCtxs"})
    for asset, context in zip(meta["universe"], contexts):
        if asset["name"] == SYMBOL_HL:
            return {
                "funding": float(context.get("funding", 0) or 0),
                "mark": float(context.get("markPx", 0) or 0),
                "mid": float(context.get("midPx", 0) or 0),
            }
    raise RuntimeError(f"{SYMBOL_HL} ausente na Hyperliquid")


def hl_book():
    book = post_hl({"type": "l2Book", "coin": SYMBOL_HL})
    levels = book.get("levels", [])
    if len(levels) < 2 or not levels[0] or not levels[1]:
        raise RuntimeError("livro Hyperliquid vazio")
    return {
        "bid": float(levels[0][0]["px"]),
        "ask": float(levels[1][0]["px"]),
        "time_ms": int(book.get("time", time.time() * 1000)),
    }


def hl_funding_history(start_ms, end_ms):
    records = []
    cursor = int(start_ms)
    while cursor < end_ms:
        batch = post_hl({
            "type": "fundingHistory",
            "coin": SYMBOL_HL,
            "startTime": cursor,
            "endTime": int(end_ms),
        })
        if not batch:
            break
        parsed = [{"time": int(item["time"]), "rate": float(item["fundingRate"])} for item in batch]
        records.extend(parsed)
        last_time = parsed[-1]["time"]
        if last_time <= cursor or len(batch) < 500:
            break
        cursor = last_time + 1
    unique = {record["time"]: record for record in records}
    return [unique[key] for key in sorted(unique)]


def binance_funding_history(start_ms, end_ms=None):
    params = {"symbol": SYMBOL_BN, "startTime": int(start_ms), "limit": 1000}
    if end_ms is not None:
        params["endTime"] = int(end_ms)
    data = get_json(f"{BINANCE_FAPI}/fundingRate?{urllib.parse.urlencode(params)}")
    return [{"time": int(item["fundingTime"]), "rate": float(item["fundingRate"])} for item in data]


def binance_book():
    item = get_json(f"{BINANCE_FAPI}/ticker/bookTicker?symbol={SYMBOL_BN}")
    return {
        "bid": float(item["bidPrice"]),
        "ask": float(item["askPrice"]),
        "time_ms": int(item.get("time", time.time() * 1000)),
    }


def market_snapshot():
    context = hl_context()
    hl = hl_book()
    bn = binance_book()
    return {
        "observed_utc": utc_now(),
        "observed_ms": int(time.time() * 1000),
        "hl_bid": hl["bid"],
        "hl_ask": hl["ask"],
        "hl_mark": context["mark"],
        "hl_funding": context["funding"],
        "bn_bid": bn["bid"],
        "bn_ask": bn["ask"],
    }


def latest_completed_funding(now_ms=None):
    now_ms = int(now_ms or time.time() * 1000)
    history = binance_funding_history(now_ms - 24 * 3600 * 1000, now_ms)
    completed = [record for record in history if record["time"] <= now_ms]
    return completed[-1] if completed else None


def exit_price_pnl_bps(state, snapshot):
    hl_pnl = (state["entry"]["hl_sell_bid"] - snapshot["hl_ask"]) / state["entry"]["hl_sell_bid"] * 10000
    bn_pnl = (snapshot["bn_bid"] - state["entry"]["bn_buy_ask"]) / state["entry"]["bn_buy_ask"] * 10000
    return hl_pnl + bn_pnl


def initialize_state(position_usd, snapshot, latest_funding):
    entry_ms = snapshot["observed_ms"]
    last_funding_ms = latest_funding["time"] if latest_funding else entry_ms
    state = {
        "version": 1,
        "strategy": "SHORT_HL_LINK_LONG_BINANCE_LINK",
        "paper_only": True,
        "position_usd_per_leg": position_usd,
        "roundtrip_cost_bps": ROUNDTRIP_BPS,
        "entry": {
            "utc": snapshot["observed_utc"],
            "ms": entry_ms,
            "hl_sell_bid": snapshot["hl_bid"],
            "bn_buy_ask": snapshot["bn_ask"],
        },
        "last_bn_funding_time_ms": last_funding_ms,
        "funding_hl_total_bps": 0.0,
        "funding_bn_total_bps": 0.0,
        "cycles": [],
        "missed_events": [],
        "status": "open",
    }
    initial_price_pnl = exit_price_pnl_bps(state, snapshot)
    state["last_exit_net_bps"] = initial_price_pnl - ROUNDTRIP_BPS
    state["current_exit_net_bps"] = state["last_exit_net_bps"]
    state["current_exit_net_usd"] = position_usd * state["current_exit_net_bps"] / 10000
    state["updated_utc"] = utc_now()
    return state


def settle_funding_event(state, event, hl_history, snapshot):
    event_id = str(event["time"])
    if any(str(cycle["funding_time_ms"]) == event_id for cycle in state["cycles"]):
        return None
    hl_funding_bps = sum(record["rate"] for record in hl_history) * 10000
    bn_funding_bps = event["rate"] * 10000
    hl_collect_bps = hl_funding_bps
    bn_collect_bps = -bn_funding_bps
    state["funding_hl_total_bps"] += hl_collect_bps
    state["funding_bn_total_bps"] += bn_collect_bps
    price_pnl_bps = exit_price_pnl_bps(state, snapshot)
    exit_net_bps = (
        price_pnl_bps
        + state["funding_hl_total_bps"]
        + state["funding_bn_total_bps"]
        - ROUNDTRIP_BPS
    )
    incremental_net_bps = exit_net_bps - state["last_exit_net_bps"]
    cycle = {
        "funding_time_ms": event["time"],
        "funding_time_utc": datetime.fromtimestamp(event["time"] / 1000, tz=timezone.utc).isoformat(),
        "observed_utc": snapshot["observed_utc"],
        "observation_delay_s": max(0.0, (snapshot["observed_ms"] - event["time"]) / 1000),
        "hl_funding_records": len(hl_history),
        "hl_collect_bps": hl_collect_bps,
        "bn_collect_bps": bn_collect_bps,
        "funding_pnl_bps": hl_collect_bps + bn_collect_bps,
        "price_pnl_if_exit_bps": price_pnl_bps,
        "exit_net_bps": exit_net_bps,
        "incremental_net_bps": incremental_net_bps,
        "hl_exit_ask": snapshot["hl_ask"],
        "bn_exit_bid": snapshot["bn_bid"],
    }
    state["cycles"].append(cycle)
    state["last_bn_funding_time_ms"] = event["time"]
    state["last_exit_net_bps"] = exit_net_bps
    state["current_exit_net_bps"] = exit_net_bps
    state["current_exit_net_usd"] = state["position_usd_per_leg"] * exit_net_bps / 10000
    state["updated_utc"] = utc_now()
    return cycle


def compute_stats(state, target_cycles):
    values = [cycle["incremental_net_bps"] for cycle in state.get("cycles", [])]
    wins = sum(value > 0 for value in values)
    ev_ci = bootstrap_ci(values) if values else (0.0, 0.0, 0.0)
    wr_ci = wilson_ci(wins, len(values))
    gate = (
        len(values) >= target_cycles
        and state.get("current_exit_net_bps", 0) > 0
        and ev_ci[0] > 0
        and not state.get("missed_events")
    )
    return {
        "updated_utc": utc_now(),
        "cycles": len(values),
        "target_cycles": target_cycles,
        "wins": wins,
        "win_rate": wins / len(values) if values else 0.0,
        "win_rate_wilson_ci95": list(wr_ci),
        "incremental_ev_bps_ci95": list(ev_ci),
        "current_exit_net_bps": state.get("current_exit_net_bps", 0.0),
        "current_exit_net_usd": state.get("current_exit_net_usd", 0.0),
        "funding_hl_total_bps": state.get("funding_hl_total_bps", 0.0),
        "funding_bn_total_bps": state.get("funding_bn_total_bps", 0.0),
        "missed_events": len(state.get("missed_events", [])),
        "paper_gate_pass": gate,
        "decision": "PAPER_SIGNAL" if gate else "NOT_VALIDATED",
    }


def process_once(state, max_observation_delay_s):
    now_ms = int(time.time() * 1000)
    start_ms = int(state["last_bn_funding_time_ms"]) + 1
    events = binance_funding_history(start_ms, now_ms)
    events = [event for event in events if event["time"] > state["last_bn_funding_time_ms"]]
    processed = []
    for event in events:
        delay_s = (now_ms - event["time"]) / 1000
        if delay_s > max_observation_delay_s:
            state["missed_events"].append({
                "funding_time_ms": event["time"],
                "detected_utc": utc_now(),
                "delay_s": delay_s,
            })
            state["last_bn_funding_time_ms"] = event["time"]
            state["updated_utc"] = utc_now()
            continue
        snapshot = market_snapshot()
        window_start = event["time"] - 8 * 3600 * 1000
        hl_history = hl_funding_history(window_start, event["time"] + 60 * 1000)
        hl_history = [record for record in hl_history if window_start < record["time"] <= event["time"]]
        cycle = settle_funding_event(state, event, hl_history, snapshot)
        if cycle:
            processed.append(cycle)
    return processed


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--position-usd", type=float, default=1000.0)
    parser.add_argument("--target-cycles", type=int, default=30)
    parser.add_argument("--poll-s", type=float, default=60.0)
    parser.add_argument("--max-observation-delay-s", type=float, default=900.0)
    parser.add_argument("--state-file", default="d55_oos_state.json")
    parser.add_argument("--stats-file", default="d55_oos_stats.json")
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args()

    snapshot = market_snapshot()
    latest = latest_completed_funding(snapshot["observed_ms"])
    if args.validate_only:
        print(json.dumps({
            "paper_only": True,
            "snapshot": snapshot,
            "latest_completed_funding": latest,
            "roundtrip_bps": ROUNDTRIP_BPS,
        }, sort_keys=True))
        return

    config = {
        "position_usd": args.position_usd,
        "target_cycles": args.target_cycles,
        "max_observation_delay_s": args.max_observation_delay_s,
        "roundtrip_bps": ROUNDTRIP_BPS,
    }
    state = load_state(args.state_file)
    if state is None:
        state = initialize_state(args.position_usd, snapshot, latest)
        state["config"] = config
        atomic_write(args.state_file, state)
    elif (
        state.get("paper_only") is not True
        or state.get("strategy") != "SHORT_HL_LINK_LONG_BINANCE_LINK"
        or state.get("config") != config
    ):
        raise SystemExit("estado incompativel")

    while state.get("status") == "open":
        processed = process_once(state, args.max_observation_delay_s)
        atomic_write(args.state_file, state)
        stats = compute_stats(state, args.target_cycles)
        atomic_write(args.stats_file, stats)
        print(json.dumps({"processed": len(processed), "stats": stats}, sort_keys=True), flush=True)
        if len(state.get("cycles", [])) >= args.target_cycles:
            state["status"] = "complete"
            state["completed_utc"] = utc_now()
            atomic_write(args.state_file, state)
            break
        if args.once:
            break
        time.sleep(args.poll_s)


if __name__ == "__main__":
    main()
