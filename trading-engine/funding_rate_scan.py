#!/usr/bin/env python3
"""
D9: Funding rate carry trade scan.

Hypothesis: If perpetual futures funding rates are persistently positive (longs
pay shorts), a carry trade (buy spot + short perp, collect funding every 8h)
can be profitable after trading fees.

Carry trade mechanics:
  1. Buy 1 BTC spot (cost: spot_price + 10 bps taker fee)
  2. Short 1 BTC perp (cost: 10 bps taker fee + margin)
  3. Every 8h, collect funding_rate * position_value
  4. Close both positions (cost: 10 bps + 10 bps = 20 bps)

Break-even: total_funding_collected > 40 bps (entry + exit fees, 20 bps each side)

Tests:
  D9a — Current funding rates across Binance, Bybit, OKX (spot anomalies)
  D9b — 30-day historical funding rate analysis: which perps had persistently
        high funding, and would the carry trade have been profitable?

All data via free public REST APIs (no keys, no auth, read-only).
"""
import argparse
import json
import os
import sys
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone, timedelta
from typing import Optional

UA = {"User-Agent": "funding-scan/1.0 (research; read-only)"}

TAKER_FEE_BPS = 10  # 0.10% per side
ENTRY_EXIT_FEE_BPS = 40  # buy spot + short perp + close both = 4 taker fees

# Top perpetuals to scan
PERPS = [
    "BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "DOGEUSDT",
    "ADAUSDT", "AVAXUSDT", "LINKUSDT", "BNBUSDT", "DOTUSDT",
    "MATICUSDT", "LTCUSDT", "ATOMUSDT", "NEARUSDT", "APTUSDT",
    "ARBUSDT", "OPUSDT", "INJUSDT", "SUIUSDT", "TIAUSDT",
]


def _get(url, timeout=10):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


# ─── Binance funding rates ───────────────────────────────────────────────────

def binance_current_funding(symbol: str) -> Optional[dict]:
    """Binance premiumIndex — current funding rate + next funding time."""
    url = f"https://fapi.binance.com/fapi/v1/premiumIndex?symbol={symbol}"
    try:
        d = _get(url)
        return {
            "exchange": "binance",
            "symbol": d["symbol"],
            "funding_rate": float(d["lastFundingRate"]),
            "next_funding_time": int(d["nextFundingTime"]),
            "mark_price": float(d["markPrice"]),
        }
    except Exception:
        return None


def binance_funding_history(symbol: str, days: int = 30) -> list:
    """Binance funding rate history."""
    end_time = int(time.time() * 1000)
    start_time = end_time - days * 86400 * 1000
    url = (f"https://fapi.binance.com/fapi/v1/fundingRate?symbol={symbol}"
           f"&startTime={start_time}&endTime={end_time}&limit=1000")
    try:
        data = _get(url)
        return [{"funding_rate": float(d["fundingRate"]),
                 "funding_time": int(d["fundingTime"])} for d in data]
    except Exception:
        return []


# ─── Bybit funding rates ─────────────────────────────────────────────────────

def bybit_current_funding(symbol: str) -> Optional[dict]:
    """Bybit v5 tickers for linear — includes funding rate."""
    url = f"https://api.bybit.com/v5/market/tickers?category=linear&symbol={symbol}"
    try:
        d = _get(url)
        if d.get("retCode") == 0 and d.get("result", {}).get("list"):
            t = d["result"]["list"][0]
            return {
                "exchange": "bybit",
                "symbol": t["symbol"],
                "funding_rate": float(t["fundingRate"]),
                "next_funding_time": int(t["nextFundingTime"]) if t.get("nextFundingTime") else 0,
                "mark_price": float(t["markPrice"]),
            }
    except Exception:
        pass
    return None


def bybit_funding_history(symbol: str, days: int = 30) -> list:
    """Bybit v5 funding history."""
    url = (f"https://api.bybit.com/v5/market/funding/history?"
           f"category=linear&symbol={symbol}&limit=200")
    try:
        d = _get(url)
        if d.get("retCode") == 0 and d.get("result", {}).get("list"):
            return [{"funding_rate": float(r["fundingRate"]),
                     "funding_time": int(r["fundingRateTimestamp"])} for r in d["result"]["list"]]
    except Exception:
        pass
    return []


# ─── OKX funding rates ───────────────────────────────────────────────────────

def okx_current_funding(symbol: str) -> Optional[dict]:
    """OKX v5 funding-rate for current."""
    inst_id = f"{symbol.replace('USDT', '-USDT')}-SWAP"
    url = f"https://www.okx.com/api/v5/public/funding-rate?instId={inst_id}"
    try:
        d = _get(url)
        if d.get("code") == "0" and d.get("data"):
            t = d["data"][0]
            return {
                "exchange": "okx",
                "symbol": symbol,
                "funding_rate": float(t["fundingRate"]),
                "next_funding_time": int(t["fundingTime"]) if t.get("fundingTime") else 0,
                "mark_price": 0,  # OKX doesn't include mark price here
            }
    except Exception:
        pass
    return None


def okx_funding_history(symbol: str, days: int = 30) -> list:
    """OKX v5 funding-rate-history."""
    inst_id = f"{symbol.replace('USDT', '-USDT')}-SWAP"
    url = (f"https://www.okx.com/api/v5/public/funding-rate-history?"
           f"instId={inst_id}&limit=300")
    try:
        d = _get(url)
        if d.get("code") == "0" and d.get("data"):
            return [{"funding_rate": float(r["fundingRate"]),
                     "funding_time": int(r["fundingTime"])} for r in d["data"]]
    except Exception:
        pass
    return []


# ─── Analysis ────────────────────────────────────────────────────────────────

@dataclass
class FundingScan:
    symbol: str
    binance_current: Optional[dict] = None
    bybit_current: Optional[dict] = None
    okx_current: Optional[dict] = None
    binance_history: list = field(default_factory=list)
    bybit_history: list = field(default_factory=list)
    okx_history: list = field(default_factory=list)
    # Analysis
    best_exchange: str = ""
    avg_funding_bps_30d: float = 0.0
    total_funding_bps_30d: float = 0.0
    net_carry_bps_30d: float = 0.0  # after entry+exit fees
    positive_periods: int = 0
    total_periods: int = 0
    persistence: float = 0.0  # fraction of periods with positive funding
    timestamp: str = ""


def scan_funding(symbol: str, days: int = 30) -> FundingScan:
    """Full funding analysis for one symbol."""
    result = FundingScan(
        symbol=symbol,
        timestamp=datetime.now(timezone.utc).isoformat(),
    )

    # Current rates
    result.binance_current = binance_current_funding(symbol)
    result.bybit_current = bybit_current_funding(symbol)
    result.okx_current = okx_current_funding(symbol)

    # Historical (30 days)
    result.binance_history = binance_funding_history(symbol, days)
    result.bybit_history = bybit_funding_history(symbol, days)
    result.okx_history = okx_funding_history(symbol, days)

    # Use the exchange with most history for analysis
    histories = {
        "binance": result.binance_history,
        "bybit": result.bybit_history,
        "okx": result.okx_history,
    }
    best_hist = max(histories.items(), key=lambda x: len(x[1]))
    result.best_exchange = best_hist[0]
    hist = best_hist[1]

    if not hist:
        return result

    # Calculate metrics
    funding_bps = [h["funding_rate"] * 10000 for h in hist]
    result.total_periods = len(funding_bps)
    result.positive_periods = sum(1 for f in funding_bps if f > 0)
    result.persistence = result.positive_periods / result.total_periods if result.total_periods > 0 else 0

    result.total_funding_bps_30d = sum(funding_bps)
    result.avg_funding_bps_30d = result.total_funding_bps_30d / result.total_periods if result.total_periods > 0 else 0
    result.net_carry_bps_30d = result.total_funding_bps_30d - ENTRY_EXIT_FEE_BPS

    return result


# ─── Main ────────────────────────────────────────────────────────────────────

def run_scan(output_file: str, days: int = 30):
    print(f"D9: Funding Rate Carry Trade Scan")
    print(f"Symbols: {len(PERPS)} perpetuals")
    print(f"History: {days} days")
    print(f"Exchanges: Binance, Bybit, OKX")
    print(f"Fees: {TAKER_FEE_BPS} bps/side, {ENTRY_EXIT_FEE_BPS} bps entry+exit")
    print(f"Output: {output_file}")
    print(f"{'='*80}\n")

    all_results = []
    profitable = []

    for i, symbol in enumerate(PERPS):
        r = scan_funding(symbol, days)
        all_results.append(asdict(r))

        # Print summary
        n_hist = len(r.binance_history) + len(r.bybit_history) + len(r.okx_history)
        best_n = max(len(r.binance_history), len(r.bybit_history), len(r.okx_history))

        status = ""
        if r.net_carry_bps_30d > 0:
            status = "PROFITABLE!"
            profitable.append(r)
        elif r.total_funding_bps_30d > 0:
            status = "positive gross, net-"
        else:
            status = "negative"

        print(f"  {symbol:12s} ({r.best_exchange:7s}, N={best_n:3d}): "
              f"avg={r.avg_funding_bps_30d:6.2f}bps/8h, "
              f"total={r.total_funding_bps_30d:8.1f}bps, "
              f"net={r.net_carry_bps_30d:8.1f}bps, "
              f"persistence={r.persistence:.0%} ({status})")

        # Current rates
        currents = []
        if r.binance_current:
            currents.append(f"Binance={r.binance_current['funding_rate']*10000:.2f}bps")
        if r.bybit_current:
            currents.append(f"Bybit={r.bybit_current['funding_rate']*10000:.2f}bps")
        if r.okx_current:
            currents.append(f"OKX={r.okx_current['funding_rate']*10000:.2f}bps")
        if currents:
            print(f"    Current: {', '.join(currents)}")

        # Rate limit: ~0.5s per symbol (6 API calls)
        time.sleep(0.3)

    # Save
    with open(output_file, "w") as f:
        json.dump(all_results, f, indent=2, default=str)

    # Summary
    print(f"\n{'='*80}")
    print(f"SUMMARY — {len(all_results)} perpetuals scanned\n")

    if profitable:
        print(f"PROFITABLE carry trades (net > 0 after {ENTRY_EXIT_FEE_BPS}bps fees):")
        for r in sorted(profitable, key=lambda x: x.net_carry_bps_30d, reverse=True):
            print(f"  {r.symbol:12s} net={r.net_carry_bps_30d:.1f}bps/30d "
                  f"(avg={r.avg_funding_bps_30d:.2f}bps/8h, persistence={r.persistence:.0%})")
    else:
        print(f"No profitable carry trades found.")
        print(f"(Need total funding > {ENTRY_EXIT_FEE_BPS}bps in {days}d to overcome entry+exit fees)")

    # Top 5 by total funding
    print(f"\nTop 5 by total funding (gross, before fees):")
    sorted_results = sorted(all_results, key=lambda x: x["total_funding_bps_30d"], reverse=True)
    for r in sorted_results[:5]:
        print(f"  {r['symbol']:12s} total={r['total_funding_bps_30d']:8.1f}bps, "
              f"net={r['net_carry_bps_30d']:8.1f}bps, "
              f"avg={r['avg_funding_bps_30d']:6.2f}bps/8h, "
              f"persistence={r['persistence']:.0%}")

    # Cross-exchange funding arbitrage
    print(f"\nCross-exchange funding rate differences (current):")
    for r in all_results:
        rates = {}
        if r.get("binance_current"):
            rates["binance"] = r["binance_current"]["funding_rate"] * 10000
        if r.get("bybit_current"):
            rates["bybit"] = r["bybit_current"]["funding_rate"] * 10000
        if r.get("okx_current"):
            rates["okx"] = r["okx_current"]["funding_rate"] * 10000
        if len(rates) >= 2:
            max_r = max(rates.values())
            min_r = min(rates.values())
            diff = max_r - min_r
            if abs(diff) > 1.0:  # > 1 bps difference
                print(f"  {r['symbol']:12s} diff={diff:6.2f}bps "
                      f"({max(rates, key=rates.get)}={max_r:.2f} vs "
                      f"{min(rates, key=rates.get)}={min_r:.2f})")


def main():
    parser = argparse.ArgumentParser(description="D9 Funding Rate Carry Trade Scan")
    parser.add_argument("--output", type=str, default="funding_rate_samples.json")
    parser.add_argument("--days", type=int, default=30, help="History lookback in days")
    args = parser.parse_args()

    output_path = os.path.join(os.path.dirname(__file__), args.output)
    run_scan(output_path, args.days)


if __name__ == "__main__":
    main()
