"""
D32 — Cross-Exchange Latency Arbitrage Scan

AGGRESSIVE HYPOTHESIS: Binance is the fastest crypto exchange. Bybit/OKX lag behind.
If Binance price moves first, we can predict Bybit/OKX price within milliseconds.

Test methodology:
  1. Poll Binance + Bybit + OKX tickers simultaneously every 100ms for 5 minutes
  2. Measure cross-exchange price lag: does Binance lead Bybit/OKX?
  3. If lag > X ms consistently, simulate: buy on lagging exchange when leader moves
  4. Net after fees (0.1% taker each side = 0.2% roundtrip)

If lag is real and > fees, this is FREE MONEY with automated execution.
"""
import json
import time
import urllib.request
from datetime import datetime, timezone
from collections import defaultdict

POLL_INTERVAL_MS = 100  # 100ms polling
DURATION_SECONDS = 300  # 5 minutes
ROUNDTRIP_FEE_PCT = 0.2  # 0.1% taker each side
MIN_LAG_PROFIT_PCT = 0.01  # minimum profit after fees to be interesting
SYMBOLS = ["BTC", "ETH", "SOL"]


def fetch_price(url, symbol_key):
    """Fetch latest price from an exchange API."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=2) as resp:
            data = json.loads(resp.read().decode())
            return float(data[symbol_key])
    except:
        return None


def fetch_all_prices():
    """Fetch prices from 3 exchanges as fast as possible."""
    prices = {}

    # Binance
    try:
        req = urllib.request.Request(
            "https://api.binance.com/api/v3/ticker/price?symbol=BTCUSDT",
            headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=2) as resp:
            prices["BINANCE_BTC"] = float(json.loads(resp.read())["price"])
    except:
        prices["BINANCE_BTC"] = None

    try:
        req = urllib.request.Request(
            "https://api.binance.com/api/v3/ticker/price?symbol=ETHUSDT",
            headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=2) as resp:
            prices["BINANCE_ETH"] = float(json.loads(resp.read())["price"])
    except:
        prices["BINANCE_ETH"] = None

    try:
        req = urllib.request.Request(
            "https://api.binance.com/api/v3/ticker/price?symbol=SOLUSDT",
            headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=2) as resp:
            prices["BINANCE_SOL"] = float(json.loads(resp.read())["price"])
    except:
        prices["BINANCE_SOL"] = None

    # Bybit
    try:
        req = urllib.request.Request(
            "https://api.bybit.com/v5/market/tickers?category=spot&symbol=BTCUSDT",
            headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=2) as resp:
            data = json.loads(resp.read())
            if data["retCode"] == 0:
                prices["BYBIT_BTC"] = float(data["result"]["list"][0]["lastPrice"])
    except:
        prices["BYBIT_BTC"] = None

    try:
        req = urllib.request.Request(
            "https://api.bybit.com/v5/market/tickers?category=spot&symbol=ETHUSDT",
            headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=2) as resp:
            data = json.loads(resp.read())
            if data["retCode"] == 0:
                prices["BYBIT_ETH"] = float(data["result"]["list"][0]["lastPrice"])
    except:
        prices["BYBIT_ETH"] = None

    # OKX
    try:
        req = urllib.request.Request(
            "https://www.okx.com/api/v5/market/ticker?instId=BTC-USDT",
            headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=2) as resp:
            data = json.loads(resp.read())
            if data["code"] == "0":
                prices["OKX_BTC"] = float(data["data"][0]["last"])
    except:
        prices["OKX_BTC"] = None

    try:
        req = urllib.request.Request(
            "https://www.okx.com/api/v5/market/ticker?instId=ETH-USDT",
            headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=2) as resp:
            data = json.loads(resp.read())
            if data["code"] == "0":
                prices["OKX_ETH"] = float(data["data"][0]["last"])
    except:
        prices["OKX_ETH"] = None

    return prices


def analyze_lag(samples, leader, follower, symbol):
    """Analyze if leader exchange predicts follower exchange."""
    pairs = []
    for s in samples:
        lp = s.get(f"{leader}_{symbol}")
        fp = s.get(f"{follower}_{symbol}")
        if lp and fp and lp > 0 and fp > 0:
            pairs.append((s["timestamp"], lp, fp))

    if len(pairs) < 10:
        return {"error": f"insufficient data ({len(pairs)} pairs)"}

    # Measure price divergence
    divergences = []
    lag_signals = 0
    profitable_signals = 0

    for i in range(1, len(pairs)):
        t, lp_now, fp_now = pairs[i]
        _, lp_prev, fp_prev = pairs[i-1]

        # Leader moved
        leader_move_pct = (lp_now - lp_prev) / lp_prev * 100

        # Follower moved
        follower_move_pct = (fp_now - fp_prev) / fp_prev * 100

        # Divergence: how much they differ
        div_pct = abs(lp_now - fp_now) / lp_now * 100
        divergences.append(div_pct)

        # If leader moved > 0.01% and follower hasn't yet → lag signal
        if abs(leader_move_pct) > 0.01:
            lag_signals += 1
            # Did follower catch up in next sample?
            if i + 1 < len(pairs):
                _, _, fp_next = pairs[i + 1]
                follower_catchup_pct = (fp_next - fp_now) / fp_now * 100

                # If leader went up, did follower also go up?
                if leader_move_pct > 0 and follower_catchup_pct > 0:
                    profit = follower_catchup_pct - ROUNDTRIP_FEE_PCT
                    if profit > 0:
                        profitable_signals += 1

                elif leader_move_pct < 0 and follower_catchup_pct < 0:
                    profit = abs(follower_catchup_pct) - ROUNDTRIP_FEE_PCT
                    if profit > 0:
                        profitable_signals += 1

    avg_div = sum(divergences) / len(divergences) if divergences else 0
    max_div = max(divergences) if divergences else 0

    return {
        "symbol": symbol,
        "leader": leader,
        "follower": follower,
        "samples": len(pairs),
        "lag_signals": lag_signals,
        "profitable_signals": profitable_signals,
        "hit_rate": profitable_signals / lag_signals * 100 if lag_signals > 0 else 0,
        "avg_divergence_pct": avg_div,
        "max_divergence_pct": max_div,
        "roundtrip_fee_pct": ROUNDTRIP_FEE_PCT,
        "verdict": "EDGE" if profitable_signals > lag_signals * 0.6 and lag_signals > 5 else "NO_EDGE",
    }


def run_scan():
    print("=" * 80)
    print("D32 — Cross-Exchange Latency Arbitrage Scan")
    print("=" * 80)
    print(f"  Polling every {POLL_INTERVAL_MS}ms for {DURATION_SECONDS}s")
    print(f"  Exchanges: Binance (leader) vs Bybit/OKX (followers)")
    print(f"  Symbols: {SYMBOLS}")
    print(f"  Roundtrip fees: {ROUNDTRIP_FEE_PCT}%")
    print()

    samples = []
    start = time.time()

    for i in range(int(DURATION_SECONDS * 1000 / POLL_INTERVAL_MS)):
        t = time.time()
        prices = fetch_all_prices()
        prices["timestamp"] = t
        samples.append(prices)

        if i % 50 == 0:
            elapsed = t - start
            print(f"  [{elapsed:.1f}s] Sample {i+1}/{int(DURATION_SECONDS*1000/POLL_INTERVAL_MS)} | "
                  f"BINANCE_BTC=${prices.get('BINANCE_BTC', 0):,.2f} "
                  f"BYBIT_BTC=${prices.get('BYBIT_BTC', 0):,.2f} "
                  f"OKX_BTC=${prices.get('OKX_BTC', 0):,.2f}")

        # Sleep for remainder of interval
        elapsed = time.time() - t
        sleep_time = max(0, POLL_INTERVAL_MS / 1000 - elapsed)
        time.sleep(sleep_time)

    print(f"\n  Collected {len(samples)} samples in {time.time()-start:.1f}s")

    # Analyze each pair
    print("\n" + "=" * 80)
    print("ANALYSIS")
    print("=" * 80)

    results = []
    for symbol in SYMBOLS:
        for follower in ["BYBIT", "OKX"]:
            r = analyze_lag(samples, "BINANCE", follower, symbol)
            if "error" not in r:
                results.append(r)
                print(f"\n  {symbol}: Binance → {follower}")
                print(f"    Samples: {r['samples']} | Lag signals: {r['lag_signals']} | "
                      f"Profitable: {r['profitable_signals']}")
                print(f"    Hit rate: {r['hit_rate']:.1f}% | "
                      f"Avg divergence: {r['avg_divergence_pct']:.4f}% | "
                      f"Max divergence: {r['max_divergence_pct']:.4f}%")
                print(f"    VERDICT: {r['verdict']}")
            else:
                print(f"\n  {symbol}: Binance → {follower} | {r['error']}")

    # Summary
    edges = [r for r in results if r["verdict"] == "EDGE"]
    print(f"\n{'='*80}")
    print(f"SUMMARY: {len(edges)}/{len(results)} pairs show potential edge")
    if edges:
        print("  POTENTIAL EDGE DETECTED — needs live testing with WebSocket for precise timing")
        for e in edges:
            print(f"    {e['symbol']} Binance→{e['follower']}: "
                  f"hit rate {e['hit_rate']:.1f}% on {e['lag_signals']} signals")
    else:
        print("  No edge found at 100ms polling granularity.")
        print("  NOTE: Real latency arb needs WebSocket (sub-ms), this scan measures if")
        print("  divergence exceeds fees — if avg_divergence < fees, no point trying.")

    # Save results
    with open("latency_arb_scan_results.json", "w") as f:
        json.dump({"results": results, "samples": len(samples),
                   "duration_s": DURATION_SECONDS}, f, indent=2)

    return results


if __name__ == "__main__":
    run_scan()
