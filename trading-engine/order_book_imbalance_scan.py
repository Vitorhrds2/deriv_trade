"""
D33 — Order Book Imbalance Alpha Scan

AGGRESSIVE HYPOTHESIS: Order book imbalance (bid volume vs ask volume) predicts
next-second price direction. If bids >> asks, price goes up. Simple, testable.

Test methodology:
  1. Fetch Binance order book depth (top 20 levels) every 1 second for 10 minutes
  2. Compute imbalance ratio: sum(bid_volume) / (sum(bid_volume) + sum(ask_volume))
  3. Measure if imbalance predicts price movement in next 1s, 5s, 10s
  4. Simulate: if imbalance > 0.65 → go long, if < 0.35 → go short
  5. Net after 0.1% taker fee per side

If imbalance predicts direction > 55% of the time after fees, this is tradeable.
"""
import json
import time
import urllib.request
from datetime import datetime, timezone

POLL_INTERVAL_S = 1.0
DURATION_S = 600  # 10 minutes
FEE_PCT = 0.1  # taker fee per side
IMBALANCE_THRESHOLD = 0.60  # 60/40 split to trigger
SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
DEPTH_LEVELS = 20


def fetch_order_book(symbol):
    """Fetch top 20 levels of order book from Binance."""
    try:
        url = f"https://api.binance.com/api/v3/depth?symbol={symbol}&limit={DEPTH_LEVELS}"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=2) as resp:
            data = json.loads(resp.read().decode())
            bids = [(float(p), float(q)) for p, q in data["bids"]]
            asks = [(float(p), float(q)) for p, q in data["asks"]]
            return bids, asks
    except Exception as e:
        return None, None


def fetch_price(symbol):
    try:
        url = f"https://api.binance.com/api/v3/ticker/price?symbol={symbol}"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=2) as resp:
            return float(json.loads(resp.read())["price"])
    except:
        return None


def compute_imbalance(bids, asks):
    """Compute order book imbalance ratio."""
    if not bids or not asks:
        return None

    bid_vol = sum(q for _, q in bids)
    ask_vol = sum(q for _, q in asks)
    total = bid_vol + ask_vol

    if total == 0:
        return None

    return bid_vol / total  # 0.5 = balanced, >0.5 = more bids


def compute_weighted_imbalance(bids, asks):
    """Volume-weighted imbalance (closer levels weighted more)."""
    if not bids or not asks:
        return None

    bid_w = sum(q * (DEPTH_LEVELS - i) for i, (_, q) in enumerate(bids))
    ask_w = sum(q * (DEPTH_LEVELS - i) for i, (_, q) in enumerate(asks))
    total = bid_w + ask_w

    if total == 0:
        return None

    return bid_w / total


def run_scan():
    print("=" * 80)
    print("D33 — Order Book Imbalance Alpha Scan")
    print("=" * 80)
    print(f"  Polling every {POLL_INTERVAL_S}s for {DURATION_S}s")
    print(f"  Symbols: {SYMBOLS}")
    print(f"  Depth: top {DEPTH_LEVELS} levels")
    print(f"  Imbalance threshold: {IMBALANCE_THRESHOLD} (long) / {1-IMBALANCE_THRESHOLD} (short)")
    print(f"  Fee: {FEE_PCT}% per side")
    print()

    # Collect data
    all_data = {sym: [] for sym in SYMBOLS}
    start = time.time()

    for i in range(int(DURATION_S / POLL_INTERVAL_S)):
        t = time.time()

        for sym in SYMBOLS:
            bids, asks = fetch_order_book(sym)
            price = fetch_price(sym)

            imb = compute_imbalance(bids, asks)
            wimb = compute_weighted_imbalance(bids, asks)

            if imb is not None and price is not None:
                # Also compute spread
                best_bid = bids[0][0] if bids else price
                best_ask = asks[0][0] if asks else price
                spread_pct = (best_ask - best_bid) / best_bid * 100

                all_data[sym].append({
                    "timestamp": t,
                    "price": price,
                    "imbalance": imb,
                    "weighted_imbalance": wimb,
                    "spread_pct": spread_pct,
                    "bid_vol": sum(q for _, q in bids),
                    "ask_vol": sum(q for _, q in asks),
                })

        if i % 30 == 0:
            elapsed = t - start
            for sym in SYMBOLS:
                if all_data[sym]:
                    last = all_data[sym][-1]
                    print(f"  [{elapsed:.0f}s] {sym}: price=${last['price']:,.2f} "
                          f"imb={last['imbalance']:.3f} spread={last['spread_pct']:.4f}%")

        # Sleep for remainder
        elapsed = time.time() - t
        time.sleep(max(0, POLL_INTERVAL_S - elapsed))

    # Analyze
    print(f"\n{'='*80}")
    print("ANALYSIS")
    print("=" * 80)

    results = []
    for sym in SYMBOLS:
        data = all_data[sym]
        if len(data) < 20:
            print(f"\n  {sym}: insufficient data ({len(data)} samples)")
            continue

        # Test prediction at different horizons
        horizons = [1, 5, 10]  # seconds
        sym_results = {"symbol": sym, "samples": len(data), "horizons": {}}

        for h in horizons:
            correct_long = 0
            total_long = 0
            correct_short = 0
            total_short = 0
            long_pnls = []
            short_pnls = []

            for i in range(len(data) - h):
                current = data[i]
                future = data[i + h]

                price_now = current["price"]
                price_future = future["price"]
                price_change_pct = (price_future - price_now) / price_now * 100

                imb = current["imbalance"]

                # Long signal: imbalance > threshold
                if imb > IMBALANCE_THRESHOLD:
                    total_long += 1
                    pnl = price_change_pct - FEE_PCT  # pay fee to enter + exit
                    long_pnls.append(pnl)
                    if price_change_pct > 0:
                        correct_long += 1

                # Short signal: imbalance < 1-threshold
                elif imb < (1 - IMBALANCE_THRESHOLD):
                    total_short += 1
                    pnl = -price_change_pct - FEE_PCT
                    short_pnls.append(pnl)
                    if price_change_pct < 0:
                        correct_short += 1

            total_signals = total_long + total_short
            correct = correct_long + correct_short
            all_pnls = long_pnls + short_pnls

            wr = correct / total_signals * 100 if total_signals > 0 else 0
            ev = sum(all_pnls) / len(all_pnls) if all_pnls else 0
            total_pnl = sum(all_pnls)
            wins = sum(1 for p in all_pnls if p > 0)

            h_result = {
                "horizon_s": h,
                "total_signals": total_signals,
                "long_signals": total_long,
                "short_signals": total_short,
                "win_rate": wr,
                "ev_per_trade_pct": ev,
                "total_pnl_pct": total_pnl,
                "wins": wins,
                "losses": total_signals - wins,
            }
            sym_results["horizons"][h] = h_result

            print(f"\n  {sym} | Horizon: {h}s")
            print(f"    Signals: {total_signals} (L:{total_long} S:{total_short})")
            print(f"    Win rate: {wr:.1f}% | EV/trade: {ev:+.4f}% | Total P&L: {total_pnl:+.4f}%")
            print(f"    Wins: {wins} | Losses: {total_signals - wins}")

            # Also test weighted imbalance
            wcorrect = 0
            wtotal = 0
            wpnls = []
            for i in range(len(data) - h):
                current = data[i]
                future = data[i + h]
                price_change_pct = (future["price"] - current["price"]) / current["price"] * 100
                wimb = current["weighted_imbalance"]

                if wimb > IMBALANCE_THRESHOLD:
                    wtotal += 1
                    wpnls.append(price_change_pct - FEE_PCT)
                    if price_change_pct > 0:
                        wcorrect += 1
                elif wimb < (1 - IMBALANCE_THRESHOLD):
                    wtotal += 1
                    wpnls.append(-price_change_pct - FEE_PCT)
                    if price_change_pct < 0:
                        wcorrect += 1

            wwr = wcorrect / wtotal * 100 if wtotal > 0 else 0
            wev = sum(wpnls) / len(wpnls) if wpnls else 0
            print(f"    [Weighted imb] WR: {wwr:.1f}% | EV: {wev:+.4f}% | N: {wtotal}")

        results.append(sym_results)

    # Summary
    print(f"\n{'='*80}")
    print("SUMMARY")
    print("=" * 80)

    any_edge = False
    for r in results:
        for h, hr in r.get("horizons", {}).items():
            if hr["win_rate"] > 55 and hr["ev_per_trade_pct"] > 0 and hr["total_signals"] > 10:
                print(f"  POTENTIAL EDGE: {r['symbol']} {h}s — "
                      f"WR {hr['win_rate']:.1f}%, EV {hr['ev_per_trade_pct']:+.4f}%, "
                      f"N={hr['total_signals']}")
                any_edge = True

    if not any_edge:
        print("  No edge found at 1s polling. Order book imbalance at this granularity")
        print("  does not predict direction after fees.")
        print("  NOTE: Real OBI alpha needs WebSocket + L2 data at sub-second granularity.")

    with open("order_book_imbalance_scan_results.json", "w") as f:
        json.dump(results, f, indent=2, default=str)

    return results


if __name__ == "__main__":
    run_scan()
