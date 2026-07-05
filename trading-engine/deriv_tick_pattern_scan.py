"""
D46 — Deriv Tick Duplication / Pattern Exploitation

TESE: Deriv's synthetic price feed may have exploitable patterns at the tick level:
  1. Duplicate ticks (same price repeated N times) → predict next tick direction
  2. Tick timing anomalies (gaps > 2s between ticks) → predict volatility spike
  3. Price level clustering (ticks cluster at round numbers) → mean reversion
  4. Sequential patterns (UP-UP-DOWN, DOWN-DOWN-UP) → predict next tick

VECTOR: Market microstructure / synthetic feed anomalies / pattern exploitation

METHOD:
  1. Stream Deriv ticks via WebSocket for multiple synthetic symbols
  2. Record every tick with precise timestamp
  3. Detect duplicate sequences, timing gaps, and sequential patterns
  4. For each pattern, track next-tick direction accuracy
  5. If any pattern predicts next tick > 55% → executable edge (1-tick trade)

AGGRESSIVENESS: This directly probes whether Deriv's RNG has exploitable patterns.
If found, we execute 1-tick CALL/PUT trades to capture the bias.

Usage:
  python3 deriv_tick_pattern_scan.py              # 120s scan
  python3 deriv_tick_pattern_scan.py --continuous  # infinite
"""
import json
import time
import ssl
import threading
from collections import deque, defaultdict
from datetime import datetime, timezone

try:
    import websocket
except ImportError:
    print("ERROR: pip install websocket-client")
    exit(1)

DERIV_WS = "wss://ws.derivws.com/websockets/v3?app_id=1089"
SYMBOLS = [
    "R_10", "R_25", "R_50", "R_75", "R_100",  # Volatility indices
    "1HZ10V", "1HZ25V", "1HZ50V", "1HZ75V", "1HZ100V",  # 1-second variants
]
RUN_DURATION = 120
DUP_THRESHOLD = 3  # 3+ identical ticks in a row = pattern
PATTERN_LEN = 3    # track 3-tick sequences


def run_scan():
    print("=" * 80)
    print("D46 — Deriv Tick Duplication / Pattern Exploitation Scanner")
    print("=" * 80)
    print(f"  Symbols: {', '.join(SYMBOLS)}")
    print(f"  Duration: {RUN_DURATION}s")
    print(f"  Detection: duplicate ticks, timing gaps, sequential patterns")
    print(f"  Target: predict next tick direction > 55% accuracy")
    print()

    state = {
        "symbols": {},
        "total_ticks": 0,
        "patterns": defaultdict(lambda: {"up": 0, "down": 0, "total": 0}),
        "duplicates": defaultdict(int),  # symbol -> count of duplicate sequences
        "timing_gaps": [],  # [{symbol, gap_ms, ts}]
        "start_time": time.time(),
    }

    for s in SYMBOLS:
        state["symbols"][s] = {
            "ticks": deque(maxlen=10000),  # [(ts_ms, price)]
            "last_tick_ts": 0,
            "last_price": 0,
            "dup_streak": 0,
        }

    def save_checkpoint():
        elapsed_now = time.time() - state["start_time"]
        try:
            with open("deriv_tick_pattern_results.json", "w") as f:
                json.dump({
                    "duration_s": elapsed_now,
                    "total_ticks": state["total_ticks"],
                    "duplicates": dict(state["duplicates"]),
                    "timing_gaps": state["timing_gaps"][:50],
                    "patterns": {k: v for k, v in state["patterns"].items() if v["total"] >= 5},
                    "checkpoint": True,
                }, f, indent=2, default=str)
        except Exception:
            pass

    def on_message(ws, msg):
        try:
            data = json.loads(msg)
            if "tick" in data:
                tick = data["tick"]
                symbol = tick.get("symbol", "")
                price = float(tick.get("quote", 0))
                now_ms = int(time.time() * 1000)

                if symbol not in state["symbols"]:
                    return

                sym_state = state["symbols"][symbol]
                prev_price = sym_state["last_price"]
                prev_ts = sym_state["last_tick_ts"]

                # Record tick
                sym_state["ticks"].append((now_ms, price))
                sym_state["last_price"] = price
                state["total_ticks"] += 1

                # 1. Duplicate detection
                if price == prev_price:
                    sym_state["dup_streak"] += 1
                    if sym_state["dup_streak"] == DUP_THRESHOLD:
                        state["duplicates"][symbol] += 1
                        if state["duplicates"][symbol] <= 10:
                            print(f"  [DUP] {symbol}: {DUP_THRESHOLD} identical ticks @ {price}")
                else:
                    sym_state["dup_streak"] = 0

                # 2. Timing gap detection
                if prev_ts > 0:
                    gap_ms = now_ms - prev_ts
                    if gap_ms > 2000:  # > 2s gap
                        state["timing_gaps"].append({
                            "symbol": symbol,
                            "gap_ms": gap_ms,
                            "ts": now_ms,
                        })
                        if len(state["timing_gaps"]) <= 20:
                            print(f"  [GAP] {symbol}: {gap_ms}ms gap between ticks")

                # 3. Sequential pattern tracking
                if prev_price > 0 and price != prev_price:
                    direction = "UP" if price > prev_price else "DOWN"
                    ticks = list(sym_state["ticks"])

                    # Build pattern from last N ticks
                    if len(ticks) >= PATTERN_LEN + 1:
                        pattern = []
                        for i in range(-PATTERN_LEN, 0):
                            if i + 1 < 0 or ticks[i][1] == ticks[i+1][1]:
                                pattern.append("=")
                            elif ticks[i][1] < ticks[i+1][1]:
                                pattern.append("U")
                            else:
                                pattern.append("D")

                        pattern_key = "".join(pattern)
                        state["patterns"][pattern_key]["total"] += 1
                        if direction == "UP":
                            state["patterns"][pattern_key]["up"] += 1
                        else:
                            state["patterns"][pattern_key]["down"] += 1

                sym_state["last_tick_ts"] = now_ms

                # Periodic checkpoint so long continuous runs survive crashes/restarts
                if state["total_ticks"] % 500 == 0:
                    save_checkpoint()

        except Exception as e:
            pass

    print(f"[SCAN] Connecting to Deriv WS...\n")

    ws = websocket.WebSocketApp(
        DERIV_WS,
        on_message=on_message,
        on_error=lambda ws, e: print(f"  WS ERROR: {e}"),
        on_open=lambda ws: print(f"  Connected — subscribing to {len(SYMBOLS)} symbols\n"),
    )

    def subscribe():
        time.sleep(2)
        for s in SYMBOLS:
            ws.send(json.dumps({"ticks": s, "subscribe": 1}))
            time.sleep(0.1)
        print(f"  Subscribed to all {len(SYMBOLS)} symbols\n")

    sub_thread = threading.Thread(target=subscribe, daemon=True)
    sub_thread.start()

    if RUN_DURATION > 0:
        def timeout_handler():
            time.sleep(RUN_DURATION)
            print(f"\n  Timeout reached ({RUN_DURATION}s), closing...")
            ws.close()
        timer = threading.Thread(target=timeout_handler, daemon=True)
        timer.start()

    ws.run_forever(sslopt={"cert_reqs": ssl.CERT_NONE})

    # Summary
    elapsed = time.time() - state["start_time"]
    print(f"\n{'='*80}")
    print("SCAN SUMMARY")
    print(f"{'='*80}")
    print(f"  Duration: {elapsed:.0f}s")
    print(f"  Total ticks: {state['total_ticks']}")
    print(f"  Ticks/second: {state['total_ticks']/elapsed:.1f}" if elapsed > 0 else "")

    print(f"\n  Duplicate sequences (>{DUP_THRESHOLD} identical):")
    for sym, count in sorted(state["duplicates"].items(), key=lambda x: x[1], reverse=True):
        print(f"    {sym}: {count}")

    print(f"\n  Timing gaps (>2s):")
    if state["timing_gaps"]:
        avg_gap = sum(g["gap_ms"] for g in state["timing_gaps"]) / len(state["timing_gaps"])
        max_gap = max(g["gap_ms"] for g in state["timing_gaps"])
        print(f"    Count: {len(state['timing_gaps'])}")
        print(f"    Average: {avg_gap:.0f}ms")
        print(f"    Max: {max_gap}ms")
    else:
        print(f"    None detected")

    # Pattern analysis
    print(f"\n  Sequential patterns (3-tick → next direction):")
    print(f"  {'Pattern':>10s} {'Total':>8s} {'Up%':>8s} {'Down%':>8s} {'Edge':>8s}")
    print(f"  {'-'*10} {'-'*8} {'-'*8} {'-'*8} {'-'*8}")

    edge_patterns = []
    for pattern, counts in sorted(state["patterns"].items(), key=lambda x: x[1]["total"], reverse=True):
        if counts["total"] < 10:
            continue
        up_pct = counts["up"] / counts["total"] * 100
        down_pct = counts["down"] / counts["total"] * 100
        edge = max(up_pct, down_pct)
        marker = " ***" if edge > 55 else ""
        print(f"  {pattern:>10s} {counts['total']:>8d} {up_pct:>7.1f}% {down_pct:>7.1f}% {edge:>7.1f}%{marker}")
        if edge > 55:
            edge_patterns.append((pattern, counts, edge))

    print(f"\n{'='*80}")
    print("VERDICT")
    print(f"{'='*80}")

    if edge_patterns:
        print(f"  *** {len(edge_patterns)} PATTERN(S) WITH > 55% PREDICTIVE ACCURACY ***")
        for pattern, counts, edge in edge_patterns:
            direction = "UP" if counts["up"] > counts["down"] else "DOWN"
            print(f"    Pattern '{pattern}' → {direction} ({edge:.1f}% accuracy, N={counts['total']})")
        print(f"\n  If validated with larger sample → executable 1-tick trades")
    else:
        max_edge = 0
        for pattern, counts in state["patterns"].items():
            if counts["total"] >= 10:
                edge = max(counts["up"], counts["down"]) / counts["total"] * 100
                if edge > max_edge:
                    max_edge = edge
        if max_edge > 0:
            print(f"  NO EDGE: best pattern accuracy {max_edge:.1f}% (need >55%)")
            print(f"  Deriv tick patterns appear random at 3-tick level")
        else:
            print(f"  INSUFFICIENT DATA — need more ticks for pattern analysis")

    # Save
    with open("deriv_tick_pattern_results.json", "w") as f:
        json.dump({
            "duration_s": elapsed,
            "total_ticks": state["total_ticks"],
            "duplicates": dict(state["duplicates"]),
            "timing_gaps": state["timing_gaps"][:50],
            "patterns": {k: v for k, v in state["patterns"].items() if v["total"] >= 5},
        }, f, indent=2, default=str)


if __name__ == "__main__":
    import sys
    if "--continuous" in sys.argv:
        RUN_DURATION = 0
        print("CONTINUOUS MODE")
    run_scan()
