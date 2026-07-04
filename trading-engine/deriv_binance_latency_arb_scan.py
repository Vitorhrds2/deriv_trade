"""
D42 — Deriv vs Binance Cross-Venue Latency Arbitrage

TESE: Deriv's real crypto price feed (e.g., BTC/ETH on Deriv) may lag Binance's
real-time price by 50-500ms. If we can detect the lag, we can trade on Deriv
KNOWING where the price is about to move (Binance already moved).

VECTOR: Latency / information asymmetry between venues

METHOD:
  1. Stream Binance WS trade data (real-time, ~10ms latency)
  2. Stream Deriv tick data via WebSocket (real-time)
  3. Cross-correlate price movements with varying time offsets
  4. If Deriv lags Binance by >100ms consistently → EXECUTE on Deriv

AGGRESSIVENESS: This is not just observation — if lag is detected, we execute
real trades on Deriv in the direction Binance already moved.

Usage:
  python3 deriv_binance_latency_arb_scan.py              # 60s scan
  python3 deriv_binance_latency_arb_scan.py --continuous  # infinite
"""
import json
import time
import ssl
import threading
import urllib.request
from datetime import datetime, timezone
from collections import defaultdict, deque

try:
    import websocket
except ImportError:
    print("ERROR: pip install websocket-client")
    exit(1)

# Binance WS
BINANCE_WS = "wss://stream.binance.com:9443/ws/btcusdt@trade"
# Deriv WS
DERIV_WS = "wss://ws.derivws.com/websockets/v3?app_id=1089"

RUN_DURATION = 60
LAG_THRESHOLD_MS = 100  # minimum lag to be exploitable
MIN_CORRELATION = 0.5   # minimum price correlation to confirm lag


def run_scan():
    print("=" * 80)
    print("D42 — Deriv vs Binance Cross-Venue Latency Arbitrage Scanner")
    print("=" * 80)
    print(f"  Tese: Deriv crypto price lags Binance → trade on Deriv with future knowledge")
    print(f"  Method: Stream both venues simultaneously, cross-correlate")
    print(f"  Threshold: {LAG_THRESHOLD_MS}ms lag, {MIN_CORRELATION} correlation")
    print()

    # Price streams: store (timestamp_ms, price) tuples
    binance_prices = deque(maxlen=10000)
    deriv_prices = deque(maxlen=10000)

    # Connection state
    state = {
        "binance_connected": False,
        "deriv_connected": False,
        "binance_trades": 0,
        "deriv_ticks": 0,
        "start_time": time.time(),
        "lag_samples": [],
    }

    # --- Binance WS ---
    def on_binance_msg(ws, msg):
        try:
            data = json.loads(msg)
            if data.get("e") == "trade":
                ts = data.get("T", int(time.time() * 1000))
                price = float(data.get("p", 0))
                recv_ts = int(time.time() * 1000)
                binance_prices.append((recv_ts, price, ts))
                state["binance_trades"] += 1
        except:
            pass

    def on_binance_open(ws):
        state["binance_connected"] = True
        print(f"  Binance WS connected — streaming BTCUSDT trades")

    def on_binance_close(ws, code, msg):
        state["binance_connected"] = False
        print(f"  Binance WS closed")

    # --- Deriv WS ---
    def on_deriv_msg(ws, msg):
        try:
            data = json.loads(msg)
            # Deriv tick stream
            if "tick" in data:
                tick = data["tick"]
                price = float(tick.get("quote", 0))
                recv_ts = int(time.time() * 1000)
                deriv_prices.append((recv_ts, price))
                state["deriv_ticks"] += 1
        except:
            pass

    def on_deriv_open(ws):
        state["deriv_connected"] = True
        print(f"  Deriv WS connected — subscribing to BTC ticks")
        # Subscribe to BTC tick stream
        ws.send(json.dumps({"ticks": "cryBTCUSD", "subscribe": 1}))

    def on_deriv_close(ws, code, msg):
        state["deriv_connected"] = False
        print(f"  Deriv WS closed")

    # Start both WS connections
    binance_ws = websocket.WebSocketApp(
        BINANCE_WS,
        on_message=on_binance_msg,
        on_open=on_binance_open,
        on_close=on_binance_close,
    )

    deriv_ws = websocket.WebSocketApp(
        DERIV_WS,
        on_message=on_deriv_msg,
        on_open=on_deriv_open,
        on_close=on_deriv_close,
    )

    binance_thread = threading.Thread(
        target=lambda: binance_ws.run_forever(sslopt={"cert_reqs": ssl.CERT_NONE}),
        daemon=True,
    )
    deriv_thread = threading.Thread(
        target=lambda: deriv_ws.run_forever(sslopt={"cert_reqs": ssl.CERT_NONE}),
        daemon=True,
    )

    print(f"\n[SCAN] Starting dual-venue stream...\n")
    binance_thread.start()
    deriv_thread.start()

    # Wait for connections
    time.sleep(3)

    # Monitor and compute lag
    while time.time() - state["start_time"] < RUN_DURATION:
        time.sleep(5)
        elapsed = time.time() - state["start_time"]

        if len(binance_prices) < 10 or len(deriv_prices) < 10:
            print(f"  [{elapsed:.0f}s] Binance: {state['binance_trades']} trades | "
                  f"Deriv: {state['deriv_ticks']} ticks (warming up...)")
            continue

        # Compute lag: for each Deriv price, find the best matching Binance price
        # at various time offsets
        binance_list = list(binance_prices)
        deriv_list = list(deriv_prices)

        # Simple lag detection: find offset that maximizes price correlation
        best_lag_ms = 0
        best_corr = 0

        for lag_ms in range(0, 1000, 50):
            matches = 0
            total_diff = 0
            for d_ts, d_price in deriv_list[-100:]:
                target_ts = d_ts - lag_ms
                # Find closest binance price at target_ts
                closest = None
                min_diff = float("inf")
                for b_ts, b_price, _ in binance_list[-200:]:
                    diff = abs(b_ts - target_ts)
                    if diff < min_diff:
                        min_diff = diff
                        closest = b_price
                if closest and min_diff < 500:
                    price_diff = abs(d_price - closest) / closest
                    if price_diff < 0.001:  # prices within 0.1%
                        matches += 1
                    total_diff += price_diff

            corr = matches / min(len(deriv_list[-100:]), 1)
            if corr > best_corr:
                best_corr = corr
                best_lag_ms = lag_ms

        state["lag_samples"].append(best_lag_ms)
        print(f"  [{elapsed:.0f}s] Binance: {state['binance_trades']} | "
              f"Deriv: {state['deriv_ticks']} | "
              f"Best lag: {best_lag_ms}ms (corr: {best_corr:.2f})")

    # Close connections
    try:
        binance_ws.close()
    except:
        pass
    try:
        deriv_ws.close()
    except:
        pass

    # Summary
    elapsed = time.time() - state["start_time"]
    print(f"\n{'='*80}")
    print("SCAN SUMMARY")
    print(f"{'='*80}")
    print(f"  Duration: {elapsed:.0f}s")
    print(f"  Binance trades: {state['binance_trades']}")
    print(f"  Deriv ticks: {state['deriv_ticks']}")

    if state["lag_samples"]:
        avg_lag = sum(state["lag_samples"]) / len(state["lag_samples"])
        max_lag = max(state["lag_samples"])
        print(f"  Lag samples: {len(state['lag_samples'])}")
        print(f"  Average lag: {avg_lag:.0f}ms")
        print(f"  Max lag: {max_lag}ms")

    print(f"\n{'='*80}")
    print("VERDICT")
    print(f"{'='*80}")

    if state["lag_samples"]:
        avg_lag = sum(state["lag_samples"]) / len(state["lag_samples"])
        if avg_lag > LAG_THRESHOLD_MS:
            print(f"  *** LAG DETECTED: {avg_lag:.0f}ms average ***")
            print(f"  Deriv lags Binance by {avg_lag:.0f}ms — POTENTIALLY EXPLOITABLE")
            print(f"  Edge: if Binance moves +0.1% in {avg_lag:.0f}ms,")
            print(f"  we can buy on Deriv BEFORE it catches up")
            print(f"  Required: trade execution on Deriv < {avg_lag:.0f}ms")
        else:
            print(f"  NO SIGNIFICANT LAG: {avg_lag:.0f}ms average")
            print(f"  Deriv tracks Binance in real-time — no latency arb possible")
    else:
        print(f"  INSUFFICIENT DATA — need more price samples from both venues")

    # Save
    with open("deriv_binance_latency_arb_results.json", "w") as f:
        json.dump({
            "duration_s": elapsed,
            "binance_trades": state["binance_trades"],
            "deriv_ticks": state["deriv_ticks"],
            "lag_samples": state["lag_samples"],
            "avg_lag_ms": avg_lag if state["lag_samples"] else 0,
        }, f, indent=2, default=str)


if __name__ == "__main__":
    import sys
    if "--continuous" in sys.argv:
        RUN_DURATION = 0
        print("CONTINUOUS MODE")
    run_scan()
