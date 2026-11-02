#!/usr/bin/env python3
"""D34 — Liquidation Cascade Detection via WebSocket (fixed).

Binance deprecated the public REST endpoint allForceOrders (returns 404).
This version uses the WebSocket forceOrder stream for real-time liquidation
detection, and markPrice@1s for price tracking.

Cascade detection: 3+ liquidations in 10s same direction = cascade.
Tracks P&L at 30s, 60s, 120s, 300s hold periods, net of 0.1% taker fee per side.

Usage:
  python3 d34_cascade_ws.py              # 30min scan
  python3 d34_cascade_ws.py --continuous # infinite
"""
import json
import time
import ssl
import threading
from collections import deque
from datetime import datetime, timezone

try:
    import websocket
except ImportError:
    print("ERROR: pip install websocket-client")
    exit(1)

WS_BASE = "wss://stream.binance.com:9443/stream"
SYMBOLS = ["btcusdt", "ethusdt", "solusdt"]
RUN_DURATION = 1800  # 30 minutes default

FEE_PCT = 0.1  # per side
CASCADE_WINDOW_S = 10
CASCADE_MIN_LIQUIDATIONS = 3
HOLD_PERIODS_S = [30, 60, 120, 300]
CASCADE_COOLDOWN_S = 30  # don't re-detect same cascade within 30s

RESULTS_FILE = "d34_cascade_results.jsonl"


def run_scan():
    print("=" * 80)
    print("D34 — Liquidation Cascade Detection (WebSocket)")
    print("=" * 80)
    print(f"  Symbols: {', '.join(SYMBOLS).upper()}")
    dur_label = "continuous" if RUN_DURATION == 0 else f"{RUN_DURATION}s"
    print(f"  Duration: {dur_label}")
    print(f"  Cascade: {CASCADE_MIN_LIQUIDATIONS}+ liquidations in {CASCADE_WINDOW_S}s same direction")
    print(f"  Hold periods: {HOLD_PERIODS_S}s | Fee: {FEE_PCT}% per side")
    print()

    state = {
        "liquidations": deque(maxlen=5000),
        "price_history": {s.upper(): deque(maxlen=10000) for s in SYMBOLS},
        "cascades": [],
        "cascade_results": [],
        "start_time": time.time(),
        "last_cascade_ts": {},
    }

    def on_message(ws, msg):
        try:
            data = json.loads(msg)
            if "data" in data:
                stream = data.get("stream", "")
                payload = data["data"]
            else:
                stream = ""
                payload = data

            for s in SYMBOLS:
                sym = s.upper()

                if f"{s}@markPrice" in stream:
                    price = float(payload.get("p", 0))
                    now_ms = int(time.time() * 1000)
                    state["price_history"][sym].append((now_ms, price))
                    return

                if f"{s}@forceOrder" in stream:
                    liq = payload.get("o", payload)
                    side = liq.get("S", "")
                    price = float(liq.get("p", 0))
                    qty = float(liq.get("q", 0))
                    now_ms = int(time.time() * 1000)

                    direction = "DOWN" if side == "SELL" else "UP"

                    state["liquidations"].append({
                        "symbol": sym,
                        "side": side,
                        "direction": direction,
                        "price": price,
                        "qty": qty,
                        "ts": now_ms,
                    })

                    print(f"  [LIQ] {sym} {side} {qty} @ {price} ({direction})", flush=True)

                    check_cascade(sym, direction, price, now_ms, state)
                    return
        except Exception as e:
            pass

    def check_cascade(sym, direction, price, now_ms, state):
        recent = [l for l in state["liquidations"]
                  if l["symbol"] == sym
                  and l["direction"] == direction
                  and now_ms - l["ts"] < CASCADE_WINDOW_S * 1000]

        if len(recent) >= CASCADE_MIN_LIQUIDATIONS:
            last_ts = state["last_cascade_ts"].get(f"{sym}_{direction}", 0)
            if now_ms - last_ts < CASCADE_COOLDOWN_S * 1000:
                return

            state["last_cascade_ts"][f"{sym}_{direction}"] = now_ms
            total_notional = sum(l["price"] * l["qty"] for l in recent)

            cascade = {
                "timestamp": now_ms / 1000,
                "symbol": sym,
                "direction": "SHORT" if direction == "DOWN" else "LONG",
                "liquidations": len(recent),
                "notional_usd": total_notional,
                "entry_price": price,
            }

            print(f"\n  *** CASCADE DETECTED ***", flush=True)
            print(f"  {sym} {cascade['direction']} | {len(recent)} liquidations in {CASCADE_WINDOW_S}s", flush=True)
            print(f"  Notional: ${total_notional:,.0f} | Entry: {price}", flush=True)
            print()

            for hold_s in HOLD_PERIODS_S:
                c = dict(cascade)
                c["hold_s"] = hold_s
                c["exit_time"] = cascade["timestamp"] + hold_s
                c["status"] = "pending"
                state["cascades"].append(c)

    def settle_cascades(state):
        now = time.time()
        settled = []
        for c in state["cascades"]:
            if c.get("status") != "pending":
                continue
            if now < c["exit_time"]:
                continue

            sym = c["symbol"]
            target_ts = c["exit_time"] * 1000
            prices = state["price_history"].get(sym, [])

            closest_price = None
            min_diff = float("inf")
            for ts, price in prices:
                diff = abs(ts - target_ts)
                if diff < min_diff:
                    min_diff = diff
                    closest_price = price

            if closest_price and min_diff < 5000:
                entry = c["entry_price"]
                price_change_pct = (closest_price - entry) / entry * 100

                if c["direction"] == "SHORT":
                    pnl_pct = -price_change_pct - FEE_PCT * 2
                else:
                    pnl_pct = price_change_pct - FEE_PCT * 2

                c["exit_price"] = closest_price
                c["pnl_pct"] = pnl_pct
                c["price_change_pct"] = price_change_pct
                c["status"] = "settled"

                result = {
                    "timestamp": c["timestamp"],
                    "symbol": c["symbol"],
                    "direction": c["direction"],
                    "hold_s": c["hold_s"],
                    "liquidations": c["liquidations"],
                    "notional_usd": c["notional_usd"],
                    "entry_price": entry,
                    "exit_price": closest_price,
                    "pnl_pct": pnl_pct,
                    "price_change_pct": price_change_pct,
                }
                state["cascade_results"].append(result)
                settled.append(result)

                emoji = "WIN" if pnl_pct > 0 else "LOSS"
                print(f"  [{emoji}] {c['symbol']} {c['direction']} hold={c['hold_s']}s | "
                      f"P&L: {pnl_pct:+.4f}% | move: {price_change_pct:+.4f}%", flush=True)

                with open(RESULTS_FILE, "a") as f:
                    f.write(json.dumps(result) + "\n")

        return settled

    def periodic_report(state):
        elapsed = time.time() - state["start_time"]
        total_liqs = len(state["liquidations"])
        n_settled = len(state["cascade_results"])
        n_pending = sum(1 for c in state["cascades"] if c.get("status") == "pending")
        print(f"  [{elapsed:.0f}s] Liqs: {total_liqs} | Cascades: {len(state['cascades'])} | "
              f"Settled: {n_settled} | Pending: {n_pending}", flush=True)

        if n_settled > 0:
            for hold_s in HOLD_PERIODS_S:
                results = [r for r in state["cascade_results"] if r["hold_s"] == hold_s]
                if results:
                    pnls = [r["pnl_pct"] for r in results]
                    wins = sum(1 for p in pnls if p > 0)
                    wr = wins / len(results) * 100
                    ev = sum(pnls) / len(pnls)
                    print(f"    hold={hold_s}s N={len(results)} WR={wr:.1f}% EV={ev:+.4f}%", flush=True)

    streams = []
    for s in SYMBOLS:
        streams.append(f"{s}@markPrice@1s")
        streams.append(f"{s}@forceOrder")
    ws_url = f"{WS_BASE}?streams={'/'.join(streams)}"

    print(f"[SCAN] Connecting to Binance WS...", flush=True)

    ws = websocket.WebSocketApp(
        ws_url,
        on_message=on_message,
        on_error=lambda ws, e: print(f"  WS ERROR: {e}", flush=True),
        on_open=lambda ws: print(f"  WebSocket connected — monitoring {len(SYMBOLS)} symbols\n", flush=True),
    )

    if RUN_DURATION > 0:
        def timeout_handler():
            time.sleep(RUN_DURATION)
            print(f"\n  Timeout ({RUN_DURATION}s), closing...", flush=True)
            ws.close()
        timer = threading.Thread(target=timeout_handler, daemon=True)
        timer.start()

    def settle_loop():
        while True:
            time.sleep(5)
            settle_cascades(state)

    settle_thread = threading.Thread(target=settle_loop, daemon=True)
    settle_thread.start()

    def report_loop():
        while True:
            time.sleep(120)
            periodic_report(state)

    report_thread = threading.Thread(target=report_loop, daemon=True)
    report_thread.start()

    ws.run_forever(sslopt={"cert_reqs": ssl.CERT_NONE})

    settle_cascades(state)

    elapsed = time.time() - state["start_time"]
    print(f"\n{'='*80}")
    print("FINAL ANALYSIS")
    print(f"{'='*80}")
    print(f"  Duration: {elapsed:.0f}s | Liquidations: {len(state['liquidations'])} | "
          f"Cascades: {len(state['cascades'])} | Settled: {len(state['cascade_results'])}")

    if state["cascade_results"]:
        for hold_s in HOLD_PERIODS_S:
            results = [r for r in state["cascade_results"] if r["hold_s"] == hold_s]
            if results:
                pnls = [r["pnl_pct"] for r in results]
                wins = sum(1 for p in pnls if p > 0)
                wr = wins / len(results) * 100
                ev = sum(pnls) / len(pnls)
                print(f"  Hold {hold_s}s: N={len(results)} WR={wr:.1f}% EV={ev:+.4f}% Total={sum(pnls):+.4f}%")
                if wr > 60 and ev > 0:
                    print(f"    *** POTENTIAL EDGE ***")
    else:
        print("  No cascades detected. Need longer observation during high volatility.")

    with open("liquidation_cascade_scan_results.json", "w") as f:
        json.dump({
            "duration_s": elapsed,
            "total_liquidations": len(state["liquidations"]),
            "cascades": len(state["cascades"]),
            "resolved": len(state["cascade_results"]),
            "results": state["cascade_results"],
        }, f, indent=2, default=str)


if __name__ == "__main__":
    import sys
    if "--continuous" in sys.argv:
        RUN_DURATION = 0
        print("CONTINUOUS MODE — infinite monitoring, auto-reconnect on WS close")
        while True:
            try:
                run_scan()
            except Exception as e:
                print(f"  Scan error: {e}, restarting in 10s...", flush=True)
                time.sleep(10)
    else:
        run_scan()
