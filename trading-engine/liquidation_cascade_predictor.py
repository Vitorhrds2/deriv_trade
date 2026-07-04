"""
D45 — Binance Liquidation Cascade Predictor

TESE: When price approaches a level with high open interest (liquidation clusters),
forced liquidations create a cascade that amplifies the move. If we can detect
the cascade starting (rapid price drop + spike in liquidations), we can join
the momentum for 30-60s of continued directional move.

VECTOR: Market microstructure / forced selling / cascade dynamics

METHOD:
  1. Stream Binance futures mark price via WebSocket (real-time)
  2. Poll liquidation orders via REST API every 2s
  3. When 3+ liquidations in 10s on same side → cascade detected
  4. Track price movement 10s, 30s, 60s after cascade start
  5. If price continues in cascade direction > 65% → executable edge

AGGRESSIVENESS: Joining liquidation cascades = trading with forced flow.
This is what prop desks do — we're just automating the detection.

Usage:
  python3 liquidation_cascade_scan.py              # 120s scan
  python3 liquidation_cascade_scan.py --continuous  # infinite
"""
import json
import time
import urllib.request
from collections import deque, defaultdict
from datetime import datetime, timezone

try:
    import websocket
except ImportError:
    print("ERROR: pip install websocket-client")
    exit(1)

import ssl
import threading

BINANCE_FAPI = "https://fapi.binance.com/fapi/v1"
WS_BASE = "wss://stream.binance.com:9443/stream"
SYMBOLS = ["btcusdt", "ethusdt", "solusdt"]
RUN_DURATION = 120

# Cascade detection
LIQ_WINDOW_S = 10    # look for liquidations in last 10s
LIQ_MIN_COUNT = 3    # 3+ liquidations in 10s = cascade
PRICE_TRACK_S = 60   # track price for 60s after cascade


def fetch_json(url, timeout=10):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode())


def fetch_liquidations():
    """Fetch recent liquidation orders from Binance Futures."""
    try:
        # Binance doesn't have a public "all liquidations" endpoint,
        # but we can use the forceOrders endpoint (needs auth) or
        # listen to the liquidation stream via WebSocket
        # Fallback: use open interest as proxy
        url = f"{BINANCE_FAPI}/openInterest?symbol=BTCUSDT"
        data = fetch_json(url, timeout=5)
        return data
    except:
        return None


def run_scan():
    print("=" * 80)
    print("D45 — Binance Liquidation Cascade Predictor")
    print("=" * 80)
    print(f"  Symbols: {', '.join(SYMBOLS).upper()}")
    print(f"  Duration: {RUN_DURATION}s")
    print(f"  Detection: {LIQ_MIN_COUNT}+ liquidations in {LIQ_WINDOW_S}s = cascade")
    print(f"  Track: price movement {PRICE_TRACK_S}s after cascade")
    print()

    state = {
        "symbols": {},
        "liquidations": deque(maxlen=1000),  # [{symbol, side, price, qty, ts}]
        "cascades": [],  # [{symbol, direction, start_ts, start_price, prices_after}]
        "start_time": time.time(),
    }

    for s in SYMBOLS:
        state["symbols"][s.upper()] = {
            "price": 0,
            "price_history": deque(maxlen=10000),  # [(ts_ms, price)]
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

            # Mark price stream
            for s in SYMBOLS:
                if f"{s}@markPrice" in stream:
                    sym = s.upper()
                    price = float(payload.get("p", 0))
                    now_ms = int(time.time() * 1000)
                    state["symbols"][sym]["price"] = price
                    state["symbols"][sym]["price_history"].append((now_ms, price))
                    return

            # Liquidation stream: <symbol>@forceOrder
            for s in SYMBOLS:
                if f"{s}@forceOrder" in stream:
                    liq = payload.get("o", payload)
                    side = liq.get("S", "")  # BUY or SELL
                    price = float(liq.get("p", 0))
                    qty = float(liq.get("q", 0))
                    now_ms = int(time.time() * 1000)

                    # In Binance futures: SELL liquidation = long getting liquidated (bearish)
                    # BUY liquidation = short getting liquidated (bullish)
                    direction = "DOWN" if side == "SELL" else "UP"

                    state["liquidations"].append({
                        "symbol": s.upper(),
                        "side": side,
                        "direction": direction,
                        "price": price,
                        "qty": qty,
                        "ts": now_ms,
                    })

                    print(f"  [LIQ] {s.upper()} {side} {qty} @ {price} ({direction})")

                    # Check for cascade
                    check_cascade(s.upper(), direction, price, now_ms, state)

        except Exception as e:
            pass

    def check_cascade(sym, direction, price, now_ms, state):
        recent_liqs = [l for l in state["liquidations"]
                       if l["symbol"] == sym
                       and l["direction"] == direction
                       and now_ms - l["ts"] < LIQ_WINDOW_S * 1000]

        if len(recent_liqs) >= LIQ_MIN_COUNT:
            # Check if we already detected this cascade recently
            recent_cascades = [c for c in state["cascades"]
                               if c["symbol"] == sym
                               and now_ms - c["start_ts"] < 30000]  # 30s cooldown
            if recent_cascades:
                return

            cascade = {
                "symbol": sym,
                "direction": direction,
                "start_ts": now_ms,
                "start_price": price,
                "liq_count": len(recent_liqs),
                "prices_after": [],
            }
            state["cascades"].append(cascade)
            print(f"\n  *** CASCADE DETECTED ***")
            print(f"  {sym} {direction} | {len(recent_liqs)} liquidations in {LIQ_WINDOW_S}s")
            print(f"  Start price: {price}")
            print()

    # Combined stream: markPrice + forceOrder for each symbol
    streams = []
    for s in SYMBOLS:
        streams.append(f"{s}@markPrice@1s")
        streams.append(f"{s}@forceOrder")
    stream_str = "/".join(streams)
    ws_url = f"{WS_BASE}?streams={stream_str}"

    print(f"[SCAN] Connecting to Binance futures WS...\n")

    ws = websocket.WebSocketApp(
        ws_url,
        on_message=on_message,
        on_error=lambda ws, e: print(f"  WS ERROR: {e}"),
        on_open=lambda ws: print(f"  WebSocket connected — monitoring {len(SYMBOLS)} symbols\n"),
    )

    if RUN_DURATION > 0:
        def timeout_handler():
            time.sleep(RUN_DURATION)
            print(f"\n  Timeout reached ({RUN_DURATION}s), closing...")
            ws.close()
        timer = threading.Thread(target=timeout_handler, daemon=True)
        timer.start()

    ws.run_forever(sslopt={"cert_reqs": ssl.CERT_NONE})

    # Resolve cascades
    elapsed = time.time() - state["start_time"]
    now_ms = int(time.time() * 1000)

    resolved = 0
    correct = 0

    for cascade in state["cascades"]:
        sym = cascade["symbol"]
        start_ts = cascade["start_ts"]
        start_price = cascade["start_price"]
        direction = cascade["direction"]

        # Check price at 10s, 30s, 60s after
        for horizon_s in [10, 30, 60]:
            target_ts = start_ts + horizon_s * 1000
            if target_ts > now_ms:
                continue

            prices = state["symbols"][sym]["price_history"]
            closest_price = None
            min_diff = float("inf")
            for ts, price in prices:
                diff = abs(ts - target_ts)
                if diff < min_diff:
                    min_diff = diff
                    closest_price = price

            if closest_price and min_diff < 3000:
                change_pct = (closest_price - start_price) / start_price * 100
                is_correct = (change_pct > 0 if direction == "UP" else change_pct < 0)
                cascade["prices_after"].append({
                    "horizon_s": horizon_s,
                    "price": closest_price,
                    "change_pct": change_pct,
                    "correct": is_correct,
                })
                if horizon_s == 30:  # primary horizon
                    resolved += 1
                    if is_correct:
                        correct += 1

    # Summary
    print(f"\n{'='*80}")
    print("SCAN SUMMARY")
    print(f"{'='*80}")
    print(f"  Duration: {elapsed:.0f}s")
    print(f"  Total liquidations: {len(state['liquidations'])}")
    print(f"  Cascades detected: {len(state['cascades'])}")
    print(f"  Resolved (30s): {resolved}")

    if resolved > 0:
        acc = correct / resolved * 100
        print(f"  Accuracy at 30s: {correct}/{resolved} = {acc:.1f}%")

    if state["cascades"]:
        print(f"\n  Cascade details:")
        for c in state["cascades"]:
            print(f"    {c['symbol']} {c['direction']} | {c['liq_count']} liqs | start={c['start_price']}")
            for pa in c.get("prices_after", []):
                print(f"      {pa['horizon_s']}s: {pa['change_pct']:+.3f}% {'✓' if pa['correct'] else '✗'}")

    print(f"\n{'='*80}")
    print("VERDICT")
    print(f"{'='*80}")

    if resolved >= 5:
        acc = correct / resolved * 100
        if acc > 65:
            print(f"  *** EDGE DETECTED: {acc:.1f}% accuracy at 30s ***")
            print(f"  Liquidation cascades predict continuation")
            print(f"  Executable: join cascade direction, exit after 30s")
        else:
            print(f"  NO EDGE: {acc:.1f}% accuracy (need >65%)")
    elif len(state["cascades"]) > 0:
        print(f"  PARTIAL DATA: {len(state['cascades'])} cascades, {resolved} resolved")
        print(f"  Need more data for statistical significance")
    else:
        print(f"  NO CASCADES in {elapsed:.0f}s")
        print(f"  Liquidation cascades are rare — need hours/days of monitoring")
        print(f"  More likely during high volatility events")

    # Save
    with open("liquidation_cascade_results.json", "w") as f:
        json.dump({
            "duration_s": elapsed,
            "total_liquidations": len(state["liquidations"]),
            "cascades": state["cascades"],
            "resolved": resolved,
            "correct": correct,
        }, f, indent=2, default=str)


if __name__ == "__main__":
    import sys
    if "--continuous" in sys.argv:
        RUN_DURATION = 0
        print("CONTINUOUS MODE — infinite monitoring")
    run_scan()
