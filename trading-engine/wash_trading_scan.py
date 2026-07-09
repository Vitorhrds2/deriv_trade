"""
D41 — Binance WS Trade Duplication / Wash Trading Detector

Tese: Binance pode executar trades internos (wash trading) ou ter padrões
anormais de trade duplication que revelam operações de market makers ou
prop trading internos. Se detectarmos padrões anormais em tempo real
via WebSocket, podemos:
  1. Seguir o flow dos "smart money" internos
  2. Detectar wash trading como signal de manipulação
  3. Identificar trades duplicados como signal de operações grandes

Método:
  1. Conectar ao Binance WebSocket trade stream (wss://stream.binance.com)
  2. Monitorar trades em tempo real para BTCUSDT, ETHUSDT, SOLUSDT
  3. Detectar:
     a. Trade ID duplicados (mesmo trade reportado múltiplas vezes)
     b. Clusters de trades idênticos (mesmo preço, tamanho, direção em < 100ms)
     c. Timestamps anômalos (trades com timestamp futuro ou passado distante)
     d. Volume anômalo (súbito burst de trades vs média)
  4. Medir: após detectar anomalia, preço se move em direção do flow?

Aggressiveness: análise em tempo real sub-100ms via WebSocket. Detectar
padrões que humanos não conseguem ver a olho nu.
"""
import json
import time
import ssl
import urllib.request
from datetime import datetime, timezone
from collections import defaultdict, deque

try:
    import websocket
except ImportError:
    print("ERROR: websocket-client not installed. Run: pip install websocket-client")
    import sys
    sys.exit(1)

import forward_return_tracker as frt

# Achado estrutural do audit 2026-07-08: este script sempre contou anomalias
# por ciclo mas nunca conferiu o que o preço fez depois -- então nunca poderia
# produzir um veredito de EV/WR, não importa quanto tempo rodasse. Ver
# forward_return_tracker.py e docs/aggressive_hypotheses_report.md UPDATE 2026-07-08.
# Horizontes curtos (segundos) pq a tese é microestrutura/HFT, não macro.
FORWARD_RETURN_HORIZONS_S = [10, 30, 60]


def _latest_price_fn(state, symbol):
    """Usa o próprio stream do WS como fonte de preço (sem chamada HTTP extra)."""
    def _fn():
        trades = state["symbols"][symbol]["trades"]
        return trades[-1]["price"] if trades else None
    return _fn


# Binance WebSocket endpoints
WS_BASE = "wss://stream.binance.com:9443/ws"
SYMBOLS = ["btcusdt", "ethusdt", "solusdt"]
RUN_DURATION = 120  # 2 minutes (initial test)

# Anomaly detection thresholds
DUP_TRADE_ID_WINDOW = 1000  # check last 1000 trades for duplicate IDs
CLUSTER_WINDOW_MS = 100  # trades within 100ms
CLUSTER_MIN_TRADES = 5  # 5+ identical trades in 100ms = cluster
VOLUME_BURST_WINDOW = 30  # seconds
VOLUME_BURST_MULT = 10  # 10x average volume = burst
TIMESTAMP_ANOMALY_MS = 5000  # trade timestamp > 5s off from current time


def on_message(ws, message, state):
    """Process each trade message from Binance WS."""
    try:
        msg = json.loads(message)
    except:
        return

    # Combined stream format: {"stream": "btcusdt@trade", "data": {...}}
    if "data" in msg:
        trade = msg["data"]
    else:
        trade = msg

    # Binance trade stream format
    if trade.get("e") != "trade":
        return

    symbol = trade.get("s", "")
    trade_id = trade.get("t", 0)
    price = float(trade.get("p", 0))
    qty = float(trade.get("q", 0))
    buyer_maker = trade.get("m", False)
    ts = trade.get("T", 0)
    now_ms = int(time.time() * 1000)

    state["total_trades"] += 1
    state["symbols"][symbol]["trades"].append({
        "id": trade_id,
        "price": price,
        "qty": qty,
        "buyer_maker": buyer_maker,
        "ts": ts,
        "recv_ts": now_ms,
    })

    # Keep only last N trades per symbol
    if len(state["symbols"][symbol]["trades"]) > 5000:
        state["symbols"][symbol]["trades"] = state["symbols"][symbol]["trades"][-5000:]

    # --- Anomaly Detection ---

    # 1. Duplicate trade IDs
    recent_ids = set(t["id"] for t in state["symbols"][symbol]["trades"][-DUP_TRADE_ID_WINDOW:])
    if trade_id in recent_ids:
        count = sum(1 for t in state["symbols"][symbol]["trades"][-DUP_TRADE_ID_WINDOW:] if t["id"] == trade_id)
        if count > 1:
            state["anomalies"]["dup_ids"] += 1
            if state["anomalies"]["dup_ids"] <= 10:  # log first 10
                print(f"  [DUP_ID] {symbol} trade_id={trade_id} seen {count}x | price={price} qty={qty}")

    # 2. Trade clusters (identical trades in < 100ms)
    recent = state["symbols"][symbol]["trades"][-20:]
    if len(recent) >= CLUSTER_MIN_TRADES:
        # Check if last N trades have same price and similar qty within CLUSTER_WINDOW_MS
        cluster_trades = [t for t in recent if now_ms - t["recv_ts"] < CLUSTER_WINDOW_MS]
        if len(cluster_trades) >= CLUSTER_MIN_TRADES:
            prices = [t["price"] for t in cluster_trades]
            qtys = [t["qty"] for t in cluster_trades]
            # Same price and same direction
            if len(set(prices)) == 1 and len(set(qtys)) <= 2:
                direction = "SELL" if buyer_maker else "BUY"
                # Cooldown: only log once per cluster (skip if last cluster was < 500ms ago)
                last_cluster_ts = state["symbols"][symbol].get("last_cluster_ts", 0)
                if now_ms - last_cluster_ts > 500:
                    state["anomalies"]["clusters"] += 1
                    state["symbols"][symbol]["last_cluster_ts"] = now_ms
                    if state["anomalies"]["clusters"] <= 20:
                        print(f"  [CLUSTER] {symbol} {len(cluster_trades)} trades @ {price} x {qty} in <100ms ({direction})")
                    frt.record(f"d41_signal_history_{symbol}.json", price, 1 if direction == "BUY" else -1,
                               FORWARD_RETURN_HORIZONS_S, meta={"type": "cluster", "n": len(cluster_trades)})

    # 3. Timestamp anomaly
    time_diff = abs(now_ms - ts)
    if time_diff > TIMESTAMP_ANOMALY_MS:
        state["anomalies"]["timestamp_anomalies"] += 1
        if state["anomalies"]["timestamp_anomalies"] <= 5:
            print(f"  [TS_ANOMALY] {symbol} trade ts={ts} vs now={now_ms} (diff={time_diff}ms)")

    # 4. Volume burst detection
    now_s = now_ms // 1000
    state["symbols"][symbol]["volume_timeline"].append((now_s, qty * price))

    # Keep only recent entries -- recent_vol only needs VOLUME_BURST_WINDOW seconds and
    # avg_window_vol only needs the last 100, so 2000 is a generous bound. Unbounded growth
    # here was the root cause of the 2026-07-06 memory leak (344MB RSS after ~24h / 141k trades)
    # and the matching O(n) blowup in the sum() below (full-list scan on every trade).
    if len(state["symbols"][symbol]["volume_timeline"]) > 2000:
        state["symbols"][symbol]["volume_timeline"] = state["symbols"][symbol]["volume_timeline"][-2000:]

    # Compute volume in last VOLUME_BURST_WINDOW seconds
    recent_vol = sum(v for t, v in state["symbols"][symbol]["volume_timeline"] 
                     if now_s - t < VOLUME_BURST_WINDOW)
    
    # Compute average volume per VOLUME_BURST_WINDOW
    if len(state["symbols"][symbol]["volume_timeline"]) > 100:
        all_volumes = [v for _, v in state["symbols"][symbol]["volume_timeline"]]
        avg_window_vol = sum(all_volumes[-100:]) / 10  # rough average per window
        if avg_window_vol > 0 and recent_vol > avg_window_vol * VOLUME_BURST_MULT:
            last_burst_ts = state["symbols"][symbol].get("last_burst_ts", 0)
            if now_s - last_burst_ts > VOLUME_BURST_WINDOW:
                state["anomalies"]["volume_bursts"] += 1
                state["symbols"][symbol]["last_burst_ts"] = now_s
                if state["anomalies"]["volume_bursts"] <= 20:
                    print(f"  [VOL_BURST] {symbol} ${recent_vol:,.0f} in {VOLUME_BURST_WINDOW}s "
                          f"(avg ${avg_window_vol:,.0f}, {recent_vol/avg_window_vol:.1f}x)")
                # Direção proxy: maioria compradora ou vendedora nos últimos 20 trades
                burst_buys = sum(1 for t in recent if not t["buyer_maker"])
                burst_direction = 1 if burst_buys >= len(recent) - burst_buys else -1
                frt.record(f"d41_signal_history_{symbol}.json", price, burst_direction,
                           FORWARD_RETURN_HORIZONS_S, meta={"type": "volume_burst", "mult": recent_vol / avg_window_vol})

    # Log progress + resolve/reporta forward-return pendente (barato: só lê preço
    # do próprio stream, sem chamada de rede -- ver forward_return_tracker.py)
    if state["total_trades"] % 1000 == 0:
        elapsed = time.time() - state["start_time"]
        print(f"  [{elapsed:.0f}s] {state['total_trades']} trades processed | "
              f"anomalies: {state['anomalies']}")
        for sym in state["symbols"]:
            frt.resolve_due(f"d41_signal_history_{sym}.json", _latest_price_fn(state, sym))
    if state["total_trades"] % 50000 == 0:
        for sym in state["symbols"]:
            frt.report(f"d41_signal_history_{sym}.json", FORWARD_RETURN_HORIZONS_S, label_prefix=f"D41 {sym}")


def on_error(ws, error, state):
    print(f"  WS ERROR: {error}")


def on_close(ws, close_status, close_msg, state):
    elapsed = time.time() - state["start_time"]
    print(f"\n  WS closed after {elapsed:.0f}s | {state['total_trades']} trades processed")


def on_open(ws, state):
    print(f"  WebSocket connected — monitoring {len(SYMBOLS)} symbols\n")


def run_scan():
    print("=" * 80)
    print("D41 — Binance WS Trade Duplication / Wash Trading Detector")
    print("=" * 80)
    print(f"  Symbols: {', '.join(SYMBOLS).upper()}")
    print(f"  Duration: {RUN_DURATION}s ({RUN_DURATION//60}min)")
    print(f"  Detection: dup IDs, trade clusters, timestamp anomalies, volume bursts")
    print(f"  Cluster: {CLUSTER_MIN_TRADES}+ identical trades in <{CLUSTER_WINDOW_MS}ms")
    print(f"  Volume burst: {VOLUME_BURST_MULT}x avg in {VOLUME_BURST_WINDOW}s")
    print()

    # Combined stream URL
    streams = "/".join(f"{s}@trade" for s in SYMBOLS)
    ws_url = f"wss://stream.binance.com:9443/stream?streams={streams}"

    state = {
        "total_trades": 0,
        "symbols": {s.upper(): {"trades": [], "volume_timeline": []} for s in SYMBOLS},
        "anomalies": defaultdict(int),
        "start_time": time.time(),
    }

    print(f"[SCAN] Connecting to {ws_url[:80]}...\n")

    # Create WebSocket connection with callbacks
    ws = websocket.WebSocketApp(
        ws_url,
        on_message=lambda ws, msg: on_message(ws, msg, state),
        on_error=lambda ws, err: on_error(ws, err, state),
        on_close=lambda ws, code, msg: on_close(ws, code, msg, state),
        on_open=lambda ws: on_open(ws, state),
    )

    # Run with timeout (skip in continuous mode)
    if RUN_DURATION > 0:
        def timeout_handler():
            time.sleep(RUN_DURATION)
            print(f"\n  Timeout reached ({RUN_DURATION}s), closing...")
            ws.close()

        import threading
        timer = threading.Thread(target=timeout_handler, daemon=True)
        timer.start()

    ws.run_forever(sslopt={"cert_reqs": ssl.CERT_NONE})

    # Summary
    elapsed = time.time() - state["start_time"]
    print(f"\n{'='*80}")
    print("SCAN SUMMARY")
    print(f"{'='*80}")
    print(f"  Duration: {elapsed:.0f}s")
    print(f"  Total trades processed: {state['total_trades']}")
    print(f"  Trades/second: {state['total_trades']/elapsed:.1f}" if elapsed > 0 else "")

    print(f"\n  Anomalies detected:")
    for anomaly, count in state["anomalies"].items():
        print(f"    {anomaly}: {count}")

    # Per-symbol breakdown
    print(f"\n  Per-symbol breakdown:")
    for symbol, data in state["symbols"].items():
        trades = data["trades"]
        if trades:
            prices = [t["price"] for t in trades]
            qtys = [t["qty"] for t in trades]
            buy_count = sum(1 for t in trades if not t["buyer_maker"])
            sell_count = sum(1 for t in trades if t["buyer_maker"])
            buy_vol = sum(t["qty"] for t in trades if not t["buyer_maker"])
            sell_vol = sum(t["qty"] for t in trades if t["buyer_maker"])
            
            print(f"  {symbol}:")
            print(f"    Trades: {len(trades)} | Buys: {buy_count} | Sells: {sell_count}")
            print(f"    Buy volume: {buy_vol:.4f} | Sell volume: {sell_vol:.4f}")
            print(f"    Price range: {min(prices):.2f} - {max(prices):.2f}")
            print(f"    Avg trade size: {sum(qtys)/len(qtys):.6f}")
            
            # Check for suspicious patterns
            unique_ids = len(set(t["id"] for t in trades))
            if unique_ids < len(trades):
                print(f"    *** {len(trades) - unique_ids} DUPLICATE TRADE IDs ***")

    # Verdict
    print(f"\n{'='*80}")
    print("VERDICT")
    print(f"{'='*80}")

    total_anomalies = sum(state["anomalies"].values())
    
    if total_anomalies == 0:
        print(f"  NO ANOMALIES DETECTED in {elapsed:.0f}s ({state['total_trades']} trades)")
        print(f"  Binance trade stream appears clean (no dup IDs, no clusters, no bursts)")
        print(f"  Note: 5min is short — need hours of monitoring for rare anomalies")
    else:
        print(f"  {total_anomalies} ANOMALIES DETECTED in {elapsed:.0f}s:")
        for anomaly, count in state["anomalies"].items():
            pct = count / state["total_trades"] * 100 if state["total_trades"] > 0 else 0
            print(f"    {anomaly}: {count} ({pct:.3f}% of trades)")
        
        if state["anomalies"]["dup_ids"] > 0:
            print(f"\n  *** DUPLICATE TRADE IDS — potential wash trading or API issue ***")
        if state["anomalies"]["clusters"] > 0:
            print(f"\n  *** TRADE CLUSTERS — potential coordinated execution ***")
        if state["anomalies"]["volume_bursts"] > 0:
            print(f"\n  *** VOLUME BURSTS — potential news or whale activity ***")

    # Save
    with open("wash_trading_scan_results.json", "w") as f:
        # Don't save all trades (too large), just summary
        json.dump({
            "duration_s": elapsed,
            "total_trades": state["total_trades"],
            "anomalies": dict(state["anomalies"]),
            "per_symbol": {
                sym: {
                    "trade_count": len(data["trades"]),
                    "unique_ids": len(set(t["id"] for t in data["trades"])),
                    "buy_count": sum(1 for t in data["trades"] if not t["buyer_maker"]),
                    "sell_count": sum(1 for t in data["trades"] if t["buyer_maker"]),
                }
                for sym, data in state["symbols"].items()
            },
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
                print(f"  Scan error: {e}, restarting in 5s...")
                time.sleep(5)
    else:
        run_scan()
