#!/usr/bin/env python3
"""
D13: Funding Rate as Directional Signal.

Hypothesis: Extreme funding rates predict price reversals.
- When funding is extremely positive (longs pay shorts), market is overleveraged long → price drops
- When funding is extremely negative (shorts pay longs), market is overleveraged short → price rallies
- Trade: take position OPPOSITE to the crowded side when funding exceeds threshold

NOT a carry trade (D9 tested carry — this tests predictive signal).

D13a — Fetch historical funding rates + price data from Binance
D13b — Quantify funding-to-future-return relationship
D13c — Backtest: enter when |funding| > threshold, exit after N hours
D13d — Calculate Sharpe, win rate, PnL after fees

All data via Binance public API. Read-only, no trading.
"""
import argparse
import json
import math
import os
import time
import urllib.request
from datetime import datetime, timezone
from typing import Optional

BINANCE_API = "https://fapi.binance.com"  # Futures API for funding rates
BINANCE_SPOT = "https://api.binance.com/api/v3"  # Spot for price klines
UA = {"User-Agent": "funding-signal-scan/1.0 (research; read-only)"}


def binance_get(endpoint: str, params: dict = None, timeout: int = 15, base: str = None) -> dict:
    api_base = base or BINANCE_API
    url = f"{api_base}/{endpoint}"
    if params:
        query = "&".join(f"{k}={v}" for k, v in params.items())
        url += f"?{query}"
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


def fetch_funding_history(symbol: str, limit: int = 1000) -> list:
    """Fetch funding rate history from Binance (8h intervals)."""
    result = binance_get("fapi/v1/fundingRate", {
        "symbol": symbol,
        "limit": limit,
    })
    # Each: {symbol, fundingTime, fundingRate}
    return [(r["fundingTime"], float(r["fundingRate"])) for r in result]


def fetch_klines(symbol: str, interval: str = "1h", limit: int = 1500) -> list:
    """Fetch OHLCV candles from Binance futures."""
    result = binance_get("fapi/v1/klines", {
        "symbol": symbol,
        "interval": interval,
        "limit": limit,
    })
    return [(c[0], float(c[4])) for c in result]  # (timestamp, close)


def fetch_all_funding_and_prices(symbols: list, price_limit: int = 1500) -> dict:
    """Fetch funding + price for all symbols."""
    data = {}
    for i, sym in enumerate(symbols):
        try:
            funding = fetch_funding_history(sym, 1000)
            # Fetch 1h candles covering the funding period
            # Funding is every 8h, 1000 records = ~333 days
            prices = fetch_klines(sym, "1h", price_limit)
            data[sym] = {"funding": funding, "prices": prices}
            if (i + 1) % 5 == 0:
                print(f"    Fetched {i+1}/{len(symbols)} symbols")
            time.sleep(0.15)
        except Exception as e:
            print(f"    Error fetching {sym}: {e}")
    return data


def mean(x):
    return sum(x) / len(x) if x else 0


def std(x):
    if len(x) < 2:
        return 0
    m = mean(x)
    return math.sqrt(sum((xi - m) ** 2 for xi in x) / (len(x) - 1))


def zscore_value(x, m, s):
    return (x - m) / s if s > 0 else 0


def run_scan(output_file: str, symbols: list):
    print("D13: Funding Rate Directional Signal Scan")
    print(f"Symbols: {len(symbols)} ({', '.join(symbols[:5])}...)")
    print(f"API: Binance public (no API key)")
    print(f"{'='*80}\n")

    print("  Fetching funding rates + price data...")
    all_data = fetch_all_funding_and_prices(symbols)

    # ─── D13b: Analyze funding-to-future-return relationship ──────────────────
    print(f"\n  Analyzing funding signal predictiveness...")

    all_results = []
    fee_bps = 5  # taker fee per side in bps
    fee_round_trip = fee_bps * 2  # entry + exit

    for sym, data in all_data.items():
        funding_data = data["funding"]
        price_data = data["prices"]

        if len(funding_data) < 50 or len(price_data) < 200:
            continue

        # Build price lookup: timestamp → close
        price_map = {ts: price for ts, price in price_data}

        # For each funding event, measure price change over next N hours
        horizons = [1, 4, 8, 24, 48, 72]  # hours after funding event
        threshold_pcts = [50, 75, 90, 95]  # percentile thresholds for "extreme" funding

        funding_rates = [f[1] for f in funding_data]
        fr_mean = mean(funding_rates)
        fr_std = std(funding_rates)

        # Separate positive and negative funding for percentile analysis
        pos_funding = [f for f in funding_rates if f > 0]
        neg_funding = [f for f in funding_rates if f < 0]

        sym_results = {
            "symbol": sym,
            "n_funding_events": len(funding_data),
            "funding_mean": fr_mean,
            "funding_std": fr_std,
            "horizons": {},
        }

        for horizon in horizons:
            horizon_results = {"thresholds": {}}

            for pct in threshold_pcts:
                # Calculate thresholds
                # For positive funding: high percentile = very positive = crowded long
                # For negative funding: low percentile = very negative = crowded short
                if pos_funding:
                    pos_threshold = sorted(pos_funding)[int(len(pos_funding) * pct / 100) - 1]
                else:
                    pos_threshold = float("inf")

                if neg_funding:
                    neg_threshold = sorted(neg_funding)[int(len(neg_funding) * (100 - pct) / 100)]
                else:
                    neg_threshold = float("-inf")

                # Backtest: when funding > pos_threshold → SHORT (expect reversal)
                #           when funding < neg_threshold → LONG (expect reversal)
                long_returns = []  # when we go long (funding very negative)
                short_returns = []  # when we go short (funding very positive)

                for ft, fr in funding_data:
                    # Find price at funding time and at funding time + horizon hours
                    # Price data is 1h candles, funding is every 8h
                    # Find nearest price candle
                    entry_price = None
                    exit_price = None
                    target_exit_ts = ft + horizon * 3600 * 1000

                    # Find closest price before funding time
                    best_diff = float("inf")
                    for pts, pprice in price_data:
                        diff = abs(pts - ft)
                        if diff < best_diff:
                            best_diff = diff
                            entry_price = pprice
                        if pts > ft:
                            break

                    # Find closest price at exit time
                    best_diff = float("inf")
                    for pts, pprice in price_data:
                        diff = abs(pts - target_exit_ts)
                        if diff < best_diff:
                            best_diff = diff
                            exit_price = pprice
                        if pts > target_exit_ts + 3600000:
                            break

                    if entry_price is None or exit_price is None or entry_price == 0:
                        continue

                    price_change_bps = (exit_price - entry_price) / entry_price * 10000

                    if fr > pos_threshold:
                        # Short signal: expect price to drop
                        short_returns.append(-price_change_bps - fee_round_trip)
                    elif fr < neg_threshold:
                        # Long signal: expect price to rise
                        long_returns.append(price_change_bps - fee_round_trip)

                all_returns = long_returns + short_returns
                n_signals = len(all_returns)

                if n_signals < 5:
                    continue

                total_pnl = sum(all_returns)
                avg_pnl = mean(all_returns)
                wins = sum(1 for r in all_returns if r > 0)
                win_rate = wins / n_signals * 100 if n_signals > 0 else 0

                # Sharpe per signal
                s = std(all_returns)
                # Annualized: funding every 8h = 3 signals/day max, but only when extreme
                signals_per_year = n_signals / (len(funding_data) * 8 / 24 / 365.25) if len(funding_data) > 0 else 0
                sharpe = (avg_pnl / s * math.sqrt(signals_per_year)) if s > 0 else 0

                # Split: long vs short
                long_pnl = sum(long_returns) if long_returns else 0
                short_pnl = sum(short_returns) if short_returns else 0
                long_wr = (sum(1 for r in long_returns if r > 0) / len(long_returns) * 100) if long_returns else 0
                short_wr = (sum(1 for r in short_returns if r > 0) / len(short_returns) * 100) if short_returns else 0

                horizon_results["thresholds"][pct] = {
                    "n_signals": n_signals,
                    "n_long": len(long_returns),
                    "n_short": len(short_returns),
                    "total_pnl_bps": total_pnl,
                    "avg_pnl_bps": avg_pnl,
                    "win_rate": win_rate,
                    "sharpe": sharpe,
                    "long_pnl_bps": long_pnl,
                    "short_pnl_bps": short_pnl,
                    "long_wr": long_wr,
                    "short_wr": short_wr,
                    "pos_threshold": pos_threshold,
                    "neg_threshold": neg_threshold,
                }

            sym_results["horizons"][horizon] = horizon_results

        all_results.append(sym_results)

        # Print best result for this symbol
        best_sharpe = -999
        best_config = None
        for h, hdata in sym_results["horizons"].items():
            for pct, r in hdata["thresholds"].items():
                if r["n_signals"] >= 5 and r["sharpe"] > best_sharpe:
                    best_sharpe = r["sharpe"]
                    best_config = (h, pct, r)

        if best_config:
            h, pct, r = best_config
            print(f"    {sym:12s}: best Sharpe={r['sharpe']:.2f} at {h}h/{pct}th percentile "
                  f"(N={r['n_signals']}, WR={r['win_rate']:.0f}%, PnL={r['total_pnl_bps']:+.0f}bps, "
                  f"avg={r['avg_pnl_bps']:+.1f}bps)")

    # Save
    with open(output_file, "w") as f:
        json.dump(all_results, f, indent=2, default=str)

    # ─── Summary ──────────────────────────────────────────────────────────────
    print(f"\n{'='*80}")
    print(f"SUMMARY\n")

    print(f"  Symbols analyzed: {len(all_results)}")

    # Find overall best configurations
    print(f"\n  Top configurations by Sharpe (N>=10):")
    all_configs = []
    for sym_r in all_results:
        for h, hdata in sym_r["horizons"].items():
            for pct, r in hdata["thresholds"].items():
                if r["n_signals"] >= 10:
                    all_configs.append({
                        "symbol": sym_r["symbol"],
                        "horizon_h": h,
                        "pct": pct,
                        **r,
                    })

    all_configs.sort(key=lambda x: x["sharpe"], reverse=True)

    print(f"  {'Symbol':12s} {'Horizon':>8s} {'Pct':>5s} {'N':>5s} {'WR':>5s} "
          f"{'PnL_bps':>9s} {'Avg_bps':>8s} {'Sharpe':>7s} {'L_wr':>5s} {'S_wr':>5s}")
    print("-" * 80)
    for c in all_configs[:15]:
        print(f"  {c['symbol']:12s} {c['horizon_h']:7d}h {c['pct']:4d}th {c['n_signals']:5d} "
              f"{c['win_rate']:4.0f}% {c['total_pnl_bps']:+8.0f} {c['avg_pnl_bps']:+7.1f} "
              f"{c['sharpe']:6.2f} {c['long_wr']:4.0f}% {c['short_wr']:4.0f}%")

    # Aggregate by horizon
    print(f"\n  Aggregate by horizon (all symbols, 90th percentile):")
    for h in [1, 4, 8, 24, 48, 72]:
        configs_at_h = [c for c in all_configs if c["horizon_h"] == h and c["pct"] == 90]
        if configs_at_h:
            avg_sharpe = mean([c["sharpe"] for c in configs_at_h])
            avg_pnl = mean([c["avg_pnl_bps"] for c in configs_at_h])
            avg_wr = mean([c["win_rate"] for c in configs_at_h])
            total_n = sum(c["n_signals"] for c in configs_at_h)
            print(f"    {h:3d}h: N={total_n:4d}, avg Sharpe={avg_sharpe:.2f}, "
                  f"avg PnL/signal={avg_pnl:+.1f}bps, avg WR={avg_wr:.0f}%")

    # Profitability analysis
    print(f"\n  PROFITABILITY ANALYSIS:")
    print(f"  - Funding rate as signal: when funding is extreme, take OPPOSITE side")
    print(f"  - Fees: {fee_bps} bps/side × 2 = {fee_round_trip} bps per round trip")
    print(f"  - Key question: does extreme funding predict reversal?")

    positive_sharpe = sum(1 for c in all_configs if c["sharpe"] > 0)
    total_configs = len(all_configs)
    positive_pnl = sum(1 for c in all_configs if c["total_pnl_bps"] > 0)
    print(f"  - Configs with positive Sharpe: {positive_sharpe}/{total_configs}")
    print(f"  - Configs with positive total PnL: {positive_pnl}/{total_configs}")

    if all_configs:
        best = all_configs[0]
        print(f"\n  BEST: {best['symbol']} {best['horizon_h']}h {best['pct']}th percentile")
        print(f"    Sharpe={best['sharpe']:.2f}, N={best['n_signals']}, "
              f"WR={best['win_rate']:.0f}%, avg PnL={best['avg_pnl_bps']:+.1f}bps")
        print(f"    Long WR={best['long_wr']:.0f}% (funding very negative → buy)")
        print(f"    Short WR={best['short_wr']:.0f}% (funding very positive → sell)")


def main():
    parser = argparse.ArgumentParser(description="D13 Funding Rate Directional Signal")
    parser.add_argument("--output", type=str, default="funding_signal_samples.json")
    parser.add_argument("--symbols", type=str, nargs="+", default=[
        "BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT",
        "ADAUSDT", "DOGEUSDT", "AVAXUSDT", "LINKUSDT", "DOTUSDT",
    ])
    args = parser.parse_args()

    output_path = os.path.join(os.path.dirname(__file__), args.output)
    run_scan(output_path, args.symbols)


if __name__ == "__main__":
    main()
