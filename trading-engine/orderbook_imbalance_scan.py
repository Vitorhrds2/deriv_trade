"""
D43 — Binance Order Book Imbalance Predictor

TESE: Binance order book depth imbalance (bid volume >> ask volume) predicts
short-term price direction with >60% accuracy. If we can detect imbalance >70%
in the top 10 levels, we can scalp 1-5 tick moves with high probability.

VECTOR: Market microstructure / order flow information asymmetry

METHOD:
  1. Stream Binance depth20 (top 20 bid/ask levels) via WebSocket
  2. Compute bid/ask volume ratio every 100ms
  3. When imbalance > 70% bid → predict UP, > 70% ask → predict DOWN
  4. Track prediction accuracy over 1s, 5s, 10s, 30s horizons
  5. If accuracy > 60% at any horizon → executable edge

AGGRESSIVENESS: This is a predictive signal that can be directly traded.
The order book is public but most retails don't process it in real-time.

Usage:
  python3 orderbook_imbalance_scan.py              # 120s scan
  python3 orderbook_imbalance_scan.py --continuous  # infinite
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

SYMBOLS = ["btcusdt", "ethusdt", "solusdt"]
RUN_DURATION = 120
IMBALANCE_THRESHOLD = 0.70  # 70% bid or ask = signal
PREDICTION_HORIZONS = [1, 5, 10, 30]  # seconds


def run_scan():
    print("=" * 80)
    print("D43 — Binance Order Book Imbalance Predictor")
    print("=" * 80)
    print(f"  Symbols: {', '.join(SYMBOLS).upper()}")
    print(f"  Duration: {RUN_DURATION}s")
    print(f"  Threshold: {IMBALANCE_THRESHOLD*100:.0f}% bid/ask imbalance = signal")
    print(f"  Horizons: {PREDICTION_HORIZONS}s")
    print()

    # State per symbol
    state = {
        "symbols": {},
        "predictions": [],  # [{symbol, direction, ts, price_at_signal, horizon_results}]
        "start_time": time.time(),
    }

    for s in SYMBOLS:
        state["symbols"][s.upper()] = {
            "bids": [],  # [(price, qty)]
            "asks": [],
            "last_price": 0,
            "price_history": deque(maxlen=10000),  # [(ts_ms, price)]
        }

    def on_message(ws, msg):
        try:
            data = json.loads(msg)
            # Combined stream format
            if "data" in data:
                stream = data.get("stream", "")
                data = data["data"]
            else:
                stream = ""

            # Determine symbol from stream or data
            sym = None
            for s in SYMBOLS:
                if s in stream.lower() or s in str(data.get("lastUpdateId", "")).lower():
                    sym = s.upper()
                    break

            # Depth update format: {lastUpdateId, bids, asks}
            if "bids" in data and "asks" in data:
                if not sym:
                    # Try to extract from stream name
                    for s in SYMBOLS:
                        if s in stream:
                            sym = s.upper()
                            break
                if not sym:
                    return

                bids = [(float(p), float(q)) for p, q in data["bids"][:20]]
                asks = [(float(p), float(q)) for p, q in data["asks"][:20]]

                sym_state = state["symbols"][sym]
                sym_state["bids"] = bids
                sym_state["asks"] = asks

                # Compute mid price
                if bids and asks:
                    mid = (bids[0][0] + asks[0][0]) / 2
                    now_ms = int(time.time() * 1000)
                    sym_state["last_price"] = mid
                    sym_state["price_history"].append((now_ms, mid))

                    # Compute imbalance
                    total_bid = sum(q for _, q in bids)
                    total_ask = sum(q for _, q in asks)
                    total = total_bid + total_ask
                    if total > 0:
                        bid_ratio = total_bid / total
                        ask_ratio = total_ask / total

                        # Generate prediction
                        if bid_ratio > IMBALANCE_THRESHOLD:
                            direction = "UP"
                            generate_prediction(sym, direction, mid, now_ms, state)
                        elif ask_ratio > IMBALANCE_THRESHOLD:
                            direction = "DOWN"
                            generate_prediction(sym, direction, mid, now_ms, state)

        except Exception as e:
            pass

    def generate_prediction(sym, direction, price, ts, state):
        # Avoid duplicate signals within 2s
        recent = [p for p in state["predictions"]
                  if p["symbol"] == sym and ts - p["ts"] < 2000]
        if recent:
            return

        pred = {
            "symbol": sym,
            "direction": direction,
            "ts": ts,
            "price_at_signal": price,
            "horizon_results": {},
            "resolved": False,
        }
        state["predictions"].append(pred)
        if len(state["predictions"]) <= 50:
            print(f"  [SIGNAL] {sym} {direction} @ {price} (ts={ts})")

    # Combined depth stream
    streams = "/".join(f"{s}@depth20@100ms" for s in SYMBOLS)
    ws_url = f"wss://stream.binance.com:9443/stream?streams={streams}"

    print(f"[SCAN] Connecting to {ws_url[:80]}...\n")

    ws = websocket.WebSocketApp(
        ws_url,
        on_message=on_message,
        on_error=lambda ws, e: print(f"  WS ERROR: {e}"),
        on_open=lambda ws: print(f"  WebSocket connected — monitoring {len(SYMBOLS)} symbols\n"),
    )

    def timeout_handler():
        time.sleep(RUN_DURATION)
        print(f"\n  Timeout reached ({RUN_DURATION}s), closing...")
        ws.close()

    timer = threading.Thread(target=timeout_handler, daemon=True)
    timer.start()

    ws.run_forever(sslopt={"cert_reqs": ssl.CERT_NONE})

    # Resolve predictions
    elapsed = time.time() - state["start_time"]
    now_ms = int(time.time() * 1000)

    resolved = 0
    correct = defaultdict(int)
    total = defaultdict(int)

    for pred in state["predictions"]:
        sym = pred["symbol"]
        signal_ts = pred["ts"]
        signal_price = pred["price_at_signal"]
        direction = pred["direction"]

        for horizon in PREDICTION_HORIZONS:
            target_ts = signal_ts + horizon * 1000
            if target_ts > now_ms:
                continue

            # Find closest price at target_ts
            prices = state["symbols"][sym]["price_history"]
            closest_price = None
            min_diff = float("inf")
            for ts, price in prices:
                diff = abs(ts - target_ts)
                if diff < min_diff:
                    min_diff = diff
                    closest_price = price

            if closest_price and min_diff < 2000:
                price_change = (closest_price - signal_price) / signal_price * 100
                if direction == "UP":
                    correct[horizon] += 1 if price_change > 0 else 0
                else:
                    correct[horizon] += 1 if price_change < 0 else 0
                total[horizon] += 1
                pred["horizon_results"][horizon] = {
                    "price": closest_price,
                    "change_pct": price_change,
                    "correct": (price_change > 0 if direction == "UP" else price_change < 0),
                }
                pred["resolved"] = True

    # Summary
    print(f"\n{'='*80}")
    print("SCAN SUMMARY")
    print(f"{'='*80}")
    print(f"  Duration: {elapsed:.0f}s")
    print(f"  Total predictions: {len(state['predictions'])}")
    print(f"  Resolved: {sum(1 for p in state['predictions'] if p['resolved'])}")

    print(f"\n  Accuracy by horizon:")
    for h in PREDICTION_HORIZONS:
        if total[h] > 0:
            acc = correct[h] / total[h] * 100
            print(f"    {h}s: {correct[h]}/{total[h]} = {acc:.1f}% {'*** EDGE ***' if acc > 60 else ''}")
        else:
            print(f"    {h}s: no data")

    print(f"\n{'='*80}")
    print("VERDICT")
    print(f"{'='*80}")

    best_horizon = None
    best_acc = 0
    for h in PREDICTION_HORIZONS:
        if total[h] > 5:
            acc = correct[h] / total[h] * 100
            if acc > best_acc:
                best_acc = acc
                best_horizon = h

    if best_horizon and best_acc > 60:
        print(f"  *** EDGE DETECTED at {best_horizon}s horizon: {best_acc:.1f}% accuracy ***")
        print(f"  Order book imbalance > {IMBALANCE_THRESHOLD*100:.0f}% predicts direction")
        print(f"  Executable: trade on imbalance signal, close after {best_horizon}s")
    elif best_horizon:
        print(f"  NO EDGE: best accuracy {best_acc:.1f}% at {best_horizon}s (need >60%)")
        print(f"  Order book imbalance is not predictive at these horizons")
    else:
        print(f"  INSUFFICIENT DATA — need more predictions and resolution time")

    # Save
    with open("orderbook_imbalance_results.json", "w") as f:
        json.dump({
            "duration_s": elapsed,
            "total_predictions": len(state["predictions"]),
            "accuracy_by_horizon": {
                str(h): {"correct": correct[h], "total": total[h],
                         "accuracy": correct[h]/total[h]*100 if total[h] > 0 else 0}
                for h in PREDICTION_HORIZONS
            },
            "predictions": [p for p in state["predictions"] if p["resolved"]][:50],
        }, f, indent=2, default=str)


if __name__ == "__main__":
    import sys
    if "--continuous" in sys.argv:
        RUN_DURATION = 0
        print("CONTINUOUS MODE")
    run_scan()
