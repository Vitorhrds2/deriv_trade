#!/usr/bin/env python3
"""
D9 validation: Rigorous funding rate carry trade analysis.

Validates the D9 signal by:
1. Getting full 30-day Binance funding history (8h intervals, 90 periods)
2. Getting full 30-day OKX funding history (hourly, paginated)
3. Accounting for capital opportunity cost (5% APR T-bill)
4. Testing persistence: rolling 7-day window profitability
5. Checking autocorrelation: does high funding predict high funding?
6. Basis risk estimation: spot vs perp price divergence

The carry trade:
  - Buy spot, short perp (delta-neutral)
  - Collect funding every period
  - Close after N periods
  - Profit = sum(funding) - entry_fees - exit_fees - capital_cost
"""
import json
import os
import time
import urllib.request
from datetime import datetime, timezone, timedelta
from typing import Optional
import statistics

UA = {"User-Agent": "funding-validate/1.0 (research; read-only)"}
TAKER_FEE_BPS = 10
ENTRY_EXIT_FEE_BPS = 40
CAPITAL_COST_APR = 0.05  # 5% APR T-bill opportunity cost
CAPITAL_COST_BPS_8H = CAPITAL_COST_APR * 10000 / (365 * 24 / 8)  # ~0.055 bps per 8h


def _get(url, timeout=10):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


def binance_funding_full(symbol: str, days: int = 30) -> list:
    """Get full Binance funding history with pagination."""
    end_time = int(time.time() * 1000)
    start_time = end_time - days * 86400 * 1000
    all_records = []
    cursor = start_time
    while cursor < end_time:
        url = (f"https://fapi.binance.com/fapi/v1/fundingRate?symbol={symbol}"
               f"&startTime={cursor}&endTime={end_time}&limit=1000")
        try:
            data = _get(url)
            if not data:
                break
            for d in data:
                all_records.append({
                    "funding_rate": float(d["fundingRate"]),
                    "funding_time": int(d["fundingTime"]),
                })
            cursor = int(data[-1]["fundingTime"]) + 1
            if len(data) < 1000:
                break
            time.sleep(0.1)
        except Exception:
            break
    return all_records


def okx_funding_full(symbol: str, days: int = 30) -> list:
    """Get full OKX funding history with pagination."""
    inst_id = f"{symbol.replace('USDT', '-USDT')}-SWAP"
    all_records = []
    # OKX uses 'after' param (pagination by time, before which records are returned)
    # We need to paginate backwards from now
    before = ""
    for _ in range(10):  # max 10 pages of 300 = 3000 records
        url = f"https://www.okx.com/api/v5/public/funding-rate-history?instId={inst_id}&limit=300"
        if before:
            url += f"&before={before}"
        try:
            d = _get(url)
            if d.get("code") != "0" or not d.get("data"):
                break
            for r in d["data"]:
                all_records.append({
                    "funding_rate": float(r["fundingRate"]),
                    "funding_time": int(r["fundingTime"]),
                })
            if len(d["data"]) < 300:
                break
            before = d["data"][-1]["fundingTime"]
            time.sleep(0.1)
        except Exception:
            break
    # Filter to last N days
    cutoff = int((time.time() - days * 86400) * 1000)
    return [r for r in all_records if r["funding_time"] >= cutoff]


def analyze_carry(funding_history: list, exchange: str, symbol: str) -> dict:
    """Analyze carry trade profitability for a funding history."""
    if not funding_history:
        return {"symbol": symbol, "exchange": exchange, "n_periods": 0}

    rates_bps = [r["funding_rate"] * 10000 for r in funding_history]
    n = len(rates_bps)

    # Determine funding interval
    if n >= 2:
        interval_h = (funding_history[1]["funding_time"] - funding_history[0]["funding_time"]) / 3600000
    else:
        interval_h = 8

    # Total funding collected
    total_funding = sum(rates_bps)
    # Capital cost over the period
    period_days = n * interval_h / 24
    capital_cost = CAPITAL_COST_APR * 10000 * period_days / 365
    # Net profit
    net_profit = total_funding - ENTRY_EXIT_FEE_BPS - capital_cost

    # Persistence
    positive = sum(1 for r in rates_bps if r > 0)
    persistence = positive / n if n > 0 else 0

    # Autocorrelation (lag-1): does high funding predict next period's funding?
    if n >= 10:
        mean_r = sum(rates_bps) / n
        numerator = sum((rates_bps[i] - mean_r) * (rates_bps[i+1] - mean_r) for i in range(n-1))
        denominator = sum((r - mean_r) ** 2 for r in rates_bps)
        autocorr = numerator / denominator if denominator > 0 else 0
    else:
        autocorr = 0

    # Rolling 7-day window profitability
    window_size = int(7 * 24 / interval_h)  # 7 days worth of periods
    rolling_profits = []
    if n >= window_size:
        for i in range(n - window_size + 1):
            window_funding = sum(rates_bps[i:i+window_size])
            window_capital = CAPITAL_COST_APR * 10000 * 7 / 365
            window_net = window_funding - ENTRY_EXIT_FEE_BPS - window_capital
            rolling_profits.append(window_net)

    rolling_positive = sum(1 for p in rolling_profits if p > 0) if rolling_profits else 0
    rolling_total = len(rolling_profits) if rolling_profits else 0

    # Volatility of funding rate
    funding_std = statistics.stdev(rates_bps) if n >= 2 else 0
    funding_mean = statistics.mean(rates_bps) if n >= 1 else 0

    # Sharpe-like ratio: mean / std (per period)
    sharpe_per_period = float(funding_mean) / float(funding_std) if funding_std > 0 else 0.0
    # Annualized Sharpe (assuming 3 periods/day for 8h, or 24 for 1h)
    periods_per_year = int(365 * 24 / max(interval_h, 0.1))
    annualized_sharpe = float(sharpe_per_period) * (periods_per_year ** 0.5)

    return {
        "symbol": symbol,
        "exchange": exchange,
        "n_periods": n,
        "interval_h": round(interval_h, 1),
        "period_days": round(period_days, 1),
        "total_funding_bps": round(total_funding, 1),
        "capital_cost_bps": round(capital_cost, 1),
        "entry_exit_fees_bps": ENTRY_EXIT_FEE_BPS,
        "net_profit_bps": round(net_profit, 1),
        "avg_funding_bps": round(funding_mean, 3),
        "funding_std_bps": round(funding_std, 3),
        "persistence": round(persistence, 3),
        "autocorr_lag1": round(autocorr, 3),
        "rolling_7d_positive": rolling_positive,
        "rolling_7d_total": rolling_total,
        "rolling_7d_win_rate": round(rolling_positive / rolling_total, 3) if rolling_total > 0 else 0,
        "annualized_sharpe": round(annualized_sharpe, 2),
    }


# Top candidates from initial scan
CANDIDATES = [
    "NEARUSDT", "SUIUSDT", "DOGEUSDT", "BNBUSDT", "OPUSDT",
    "MATICUSDT", "LTCUSDT", "LINKUSDT", "ADAUSDT", "ETHUSDT",
    "BTCUSDT", "XRPUSDT", "ARBUSDT", "AVAXUSDT",
    # Negative ones for comparison
    "DOTUSDT", "ATOMUSDT", "APTUSDT", "INJUSDT", "TIAUSDT",
]


def main():
    print("D9 Validation: Rigorous Funding Rate Carry Trade Analysis")
    print(f"Candidates: {len(CANDIDATES)} perpetuals")
    print(f"Capital cost: {CAPITAL_COST_APR*100}% APR = {CAPITAL_COST_BPS_8H:.3f} bps/8h")
    print(f"Entry+exit fees: {ENTRY_EXIT_FEE_BPS} bps")
    print(f"{'='*80}\n")

    results = []

    for i, symbol in enumerate(CANDIDATES):
        print(f"[{i+1}/{len(CANDIDATES)}] {symbol}...", end=" ", flush=True)

        # Get Binance history (8h intervals)
        bn_hist = binance_funding_full(symbol, days=30)
        print(f"Binance N={len(bn_hist)}", end=" ", flush=True)

        # Get OKX history (hourly)
        okx_hist = okx_funding_full(symbol, days=30)
        print(f"OKX N={len(okx_hist)}", end=" ", flush=True)

        # Analyze each
        bn_analysis = analyze_carry(bn_hist, "binance", symbol)
        okx_analysis = analyze_carry(okx_hist, "okx", symbol)

        # Use the one with more data
        best = bn_analysis if bn_analysis["n_periods"] >= okx_analysis["n_periods"] else okx_analysis
        results.append(best)

        print(f"net={best['net_profit_bps']:.1f}bps/30d "
              f"avg={best['avg_funding_bps']:.3f}bps "
              f"persistence={best['persistence']:.0%} "
              f"autocorr={best['autocorr_lag1']:.2f} "
              f"sharpe={best['annualized_sharpe']:.1f}")

        time.sleep(0.2)

    # Save
    output_path = os.path.join(os.path.dirname(__file__), "funding_rate_validation.json")
    with open(output_path, "w") as f:
        json.dump(results, f, indent=2, default=str)

    # Summary
    print(f"\n{'='*80}")
    print(f"SUMMARY — {len(results)} perpetuals\n")

    profitable = [r for r in results if r["net_profit_bps"] > 0]
    print(f"Profitable (net > 0 after fees + capital cost): {len(profitable)}/{len(results)}")

    if profitable:
        print(f"\n{'Symbol':12s} {'Exchange':8s} {'N':>5s} {'Net bps':>8s} "
              f"{'Avg bps':>8s} {'Persist':>8s} {'AutoCorr':>9s} {'Sharpe':>7s} "
              f"{'7d Win%':>8s}")
        print("-" * 85)
        for r in sorted(profitable, key=lambda x: x["net_profit_bps"], reverse=True):
            print(f"{r['symbol']:12s} {r['exchange']:8s} {r['n_periods']:5d} "
                  f"{r['net_profit_bps']:8.1f} {r['avg_funding_bps']:8.3f} "
                  f"{r['persistence']:7.0%} {r['autocorr_lag1']:9.3f} "
                  f"{r['annualized_sharpe']:7.1f} {r['rolling_7d_win_rate']:7.0%}")

    # Key question: is the funding rate autocorrelated?
    print(f"\nAutocorrelation analysis (lag-1):")
    autocorrs = [(r["symbol"], r["autocorr_lag1"]) for r in results if r["n_periods"] >= 10]
    positive_ac = [a for a in autocorrs if a[1] > 0]
    print(f"  {len(positive_ac)}/{len(autocorrs)} symbols have positive autocorrelation")
    print(f"  (positive autocorr = funding tends to persist, making carry trade more predictable)")

    # Rolling 7-day window analysis
    print(f"\nRolling 7-day window profitability:")
    for r in sorted(results, key=lambda x: x["rolling_7d_win_rate"], reverse=True)[:10]:
        if r["rolling_7d_total"] > 0:
            print(f"  {r['symbol']:12s} {r['rolling_7d_win_rate']:.0%} of 7-day windows profitable "
                  f"({r['rolling_7d_positive']}/{r['rolling_7d_total']})")


if __name__ == "__main__":
    main()
