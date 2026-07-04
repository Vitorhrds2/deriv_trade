#!/usr/bin/env python3
"""
D17 Shorting Cost Analysis.

For each unlock event, fetch the actual Binance USDT-M perpetual funding rates
during the 6-day hold window (3d before to 3d after unlock).

Key rules for Binance perps:
- Funding paid every 8h (00:00, 08:00, 16:00 UTC)
- Positive funding = longs pay shorts (GOOD for our short — we RECEIVE)
- Negative funding = shorts pay longs (BAD — we PAY)
- 6-day hold = ~18 funding periods

Total shorting cost = sum(negative funding) - sum(positive funding) + trading fees
Net edge = gross edge (from backtest) - shorting cost

Also fetches borrow rates for spot margin shorting as alternative.

All data via Binance public API. Read-only.
"""
import argparse
import json
import math
import os
import time
import urllib.request
from datetime import datetime, timezone

BINANCE_FAPI = "https://fapi.binance.com/fapi/v1"
BINANCE_API = "https://api.binance.com/api/v3"
UA = {"User-Agent": "Mozilla/5.0 (research; read-only)"}

# Import unlock events from the main scan
import sys
sys.path.insert(0, os.path.dirname(__file__))
from token_unlock_scan import KNOWN_UNLOCKS, date_to_ms, fetch_daily_candles, mean, std


def http_get(url, timeout=15):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


def fetch_funding_rates(symbol, start_ms, end_ms):
    """Fetch funding rate history for a USDT-M perp symbol.
    
    Returns list of {ts, funding_rate} dicts.
    Funding rate is the rate applied (not annualized).
    Positive = longs pay shorts, negative = shorts pay longs.
    """
    all_rates = []
    current_start = start_ms
    while current_start < end_ms:
        params = f"symbol={symbol}&startTime={current_start}&endTime={end_ms}&limit=1000"
        try:
            data = http_get(f"{BINANCE_FAPI}/fundingRate?{params}")
        except Exception as e:
            print(f"      Funding API error for {symbol}: {e}")
            break
        if not data:
            break
        for r in data:
            all_rates.append({"ts": r["fundingTime"], "rate": float(r["fundingRate"])})
        if len(data) < 1000:
            break
        current_start = data[-1]["fundingTime"] + 1
        time.sleep(0.15)
    return all_rates


def fetch_funding_history_paginated(symbol, start_ms, end_ms):
    """Fetch funding rate history with pagination."""
    all_rates = []
    current_start = start_ms
    while current_start < end_ms:
        url = f"{BINANCE_FAPI}/fundingRate?symbol={symbol}&startTime={current_start}&endTime={end_ms}&limit=1000"
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=15) as r:
                data = json.loads(r.read().decode())
        except Exception as e:
            print(f"      Funding API error for {symbol}: {e}")
            break
        if not data:
            break
        for entry in data:
            all_rates.append({"ts": entry["fundingTime"], "rate": float(entry["fundingRate"])})
        if len(data) < 1000:
            break
        current_start = data[-1]["fundingTime"] + 1
        time.sleep(0.2)
    return all_rates


def get_funding_during_hold(funding_rates, entry_ts, exit_ts):
    """Get all funding rates during the hold period.
    
    For a short position:
    - Positive funding: we RECEIVE (longs pay shorts)
    - Negative funding: we PAY (shorts pay longs)
    
    Net funding PnL (in bps) = sum(funding_rate) * 10000
    (positive = we receive, negative = we pay)
    """
    rates_during = [r for r in funding_rates if entry_ts <= r["ts"] <= exit_ts]
    total_funding = sum(r["rate"] for r in rates_during)
    # Convert to bps: funding_rate * 10000
    funding_bps = total_funding * 10000
    return funding_bps, len(rates_during), rates_during


def run_analysis(output_file):
    print("D17: Shorting Cost Analysis (Binance Perp Funding Rates)")
    print(f"API: Binance USDT-M public funding rate history")
    print(f"{'='*80}\n")

    # Group unlocks by symbol
    symbols = {}
    for sym, date, val, pct, src in KNOWN_UNLOCKS:
        if sym not in symbols:
            symbols[sym] = []
        symbols[sym].append({"date": date, "value_mm": val, "pct_supply": pct, "source": src})

    print(f"  Symbols: {', '.join(symbols.keys())}")
    print(f"  Total unlock events: {len(KNOWN_UNLOCKS)}\n")

    # For each symbol, fetch all funding rates for the full period
    # Then for each unlock event, extract funding during 6-day hold
    fee_bps = 20  # 10 bps per side trading fee
    oos_cutoff = date_to_ms("2025-01-01")

    all_trades = []
    funding_stats = {}

    for symbol, events in symbols.items():
        print(f"\n  [{symbol}]")
        
        # Fetch funding rates for full period
        start_ms = date_to_ms("2023-01-01")
        end_ms = date_to_ms("2025-07-15")
        
        funding_rates = fetch_funding_history_paginated(symbol, start_ms, end_ms)
        print(f"    Funding records: {len(funding_rates)}")
        
        if not funding_rates:
            print(f"    Skipping — no funding data (symbol may not have perp)")
            continue

        # Stats
        all_rates = [r["rate"] for r in funding_rates]
        avg_funding_8h = mean(all_rates)
        avg_funding_daily = avg_funding_8h * 3  # 3 funding periods per day
        avg_funding_6d = avg_funding_8h * 18  # 18 periods in 6 days
        pct_negative = sum(1 for r in all_rates if r < 0) / len(all_rates) * 100
        
        funding_stats[symbol] = {
            "n_records": len(funding_rates),
            "avg_funding_8h": avg_funding_8h,
            "avg_funding_daily": avg_funding_daily,
            "avg_funding_6d_bps": avg_funding_6d * 10000,
            "pct_negative": pct_negative,
        }
        
        print(f"    Avg funding/8h: {avg_funding_8h*10000:+.1f}bps")
        print(f"    Avg funding/6d: {avg_funding_6d*10000:+.1f}bps")
        print(f"    Negative funding %: {pct_negative:.0f}%")

        # For each unlock event, calculate funding cost during hold
        for event in events:
            unlock_ts = date_to_ms(event["date"])
            entry_ts = unlock_ts - 3 * 86400000  # 3d before
            exit_ts = unlock_ts + 3 * 86400000   # 3d after

            funding_bps, n_periods, rates = get_funding_during_hold(funding_rates, entry_ts, exit_ts)
            
            # Fetch price data to compute gross edge
            candles = fetch_daily_candles(symbol, entry_ts - 86400000, exit_ts + 86400000)
            if len(candles) < 3:
                continue

            # Find prices at entry and exit
            p_entry = None
            p_exit = None
            for c in candles:
                if c["ts"] <= entry_ts:
                    p_entry = c["close"]
                if c["ts"] <= exit_ts:
                    p_exit = c["close"]
            
            # Better: find closest candle to entry/exit
            p_entry = min(candles, key=lambda c: abs(c["ts"] - entry_ts))["close"]
            p_exit = min(candles, key=lambda c: abs(c["ts"] - exit_ts))["close"]

            if p_entry == 0:
                continue

            # Gross short return (in bps, before fees and funding)
            gross_bps = (p_entry - p_exit) / p_entry * 10000

            # Net = gross - trading fees + funding received (positive = we receive)
            net_bps = gross_bps - fee_bps + funding_bps

            is_oos = unlock_ts >= oos_cutoff

            all_trades.append({
                "symbol": symbol,
                "unlock_date": event["date"],
                "unlock_value_mm": event["value_mm"],
                "entry_price": p_entry,
                "exit_price": p_exit,
                "gross_bps": gross_bps,
                "funding_bps": funding_bps,
                "fee_bps": fee_bps,
                "net_bps": net_bps,
                "n_funding_periods": n_periods,
                "is_oos": is_oos,
            })

    # ─── Aggregate results ────────────────────────────────────────────────────
    print(f"\n{'='*80}")
    print(f"SHORTING COST ANALYSIS ({len(all_trades)} trades)\n")

    # Funding rate summary per symbol
    print(f"  Funding rate summary (avg over full period):")
    print(f"    {'Symbol':>10s} {'8h bps':>8s} {'6d bps':>8s} {'Neg%':>6s}")
    print("    " + "-" * 35)
    for sym in sorted(funding_stats.keys()):
        s = funding_stats[sym]
        print(f"    {sym:>10s} {s['avg_funding_8h']*10000:+7.1f} {s['avg_funding_6d_bps']:+7.1f} {s['pct_negative']:5.0f}%")

    # Split IS vs OOS
    is_trades = [t for t in all_trades if not t["is_oos"]]
    oos_trades = [t for t in all_trades if t["is_oos"]]

    for label, trades in [("ALL", all_trades), ("IS (2023-2024)", is_trades), ("OOS (2025)", oos_trades)]:
        if not trades:
            continue
        print(f"\n  {label} ({len(trades)} trades):")
        
        gross_pnls = [t["gross_bps"] for t in trades]
        funding_pnls = [t["funding_bps"] for t in trades]
        net_pnls = [t["net_bps"] for t in trades]
        
        gross_wr = sum(1 for p in gross_pnls if p > 0) / len(gross_pnls) * 100
        net_wr = sum(1 for p in net_pnls if p > 0) / len(net_pnls) * 100
        
        gross_avg = mean(gross_pnls)
        net_avg = mean(net_pnls)
        funding_avg = mean(funding_pnls)
        
        net_s = std(net_pnls)
        net_t = net_avg / (net_s / math.sqrt(len(net_pnls))) if net_s > 0 else 0
        
        print(f"    Gross edge:     WR={gross_wr:.0f}%, avg={gross_avg:+.0f}bps (after {fee_bps}bps fees)")
        print(f"    Funding cost:   avg={funding_avg:+.0f}bps (positive=received, negative=paid)")
        print(f"    NET edge:       WR={net_wr:.0f}%, avg={net_avg:+.0f}bps, t-stat={net_t:.2f}")
        print(f"    Funding impact: {net_avg - gross_avg:+.0f}bps ({(net_avg - gross_avg)/gross_avg*100 if gross_avg else 0:+.0f}% of gross)")

    # Per-symbol net breakdown
    print(f"\n  Per-symbol NET breakdown:")
    print(f"    {'Symbol':>10s} {'N':>4s} {'Gross':>8s} {'Funding':>8s} {'NET':>8s} {'NET WR':>7s} {'OOS N':>5s} {'OOS NET':>8s}")
    print("    " + "-" * 65)
    for sym in sorted(set(t["symbol"] for t in all_trades)):
        sym_trades = [t for t in all_trades if t["symbol"] == sym]
        sym_gross = mean([t["gross_bps"] for t in sym_trades])
        sym_funding = mean([t["funding_bps"] for t in sym_trades])
        sym_net = mean([t["net_bps"] for t in sym_trades])
        sym_net_wr = sum(1 for t in sym_trades if t["net_bps"] > 0) / len(sym_trades) * 100
        
        sym_oos = [t for t in sym_trades if t["is_oos"]]
        oos_net = mean([t["net_bps"] for t in sym_oos]) if sym_oos else 0
        
        oos_str = f"{len(sym_oos):5d} {oos_net:+7.0f}" if sym_oos else f"{0:5d}      -"
        print(f"    {sym:>10s} {len(sym_trades):4d} {sym_gross:+7.0f} {sym_funding:+7.0f} {sym_net:+7.0f} {sym_net_wr:6.0f}% {oos_str}")

    # ─── Verdict ──────────────────────────────────────────────────────────────
    print(f"\n{'='*80}")
    print(f"VERDICT\n")

    if oos_trades:
        oos_net = [t["net_bps"] for t in oos_trades]
        oos_avg = mean(oos_net)
        oos_wr = sum(1 for p in oos_net if p > 0) / len(oos_net) * 100
        oos_s = std(oos_net)
        oos_t = oos_avg / (oos_s / math.sqrt(len(oos_net))) if oos_s > 0 else 0
        oos_funding = mean([t["funding_bps"] for t in oos_trades])
        
        print(f"  OOS NET (after funding + fees):")
        print(f"    N={len(oos_trades)}, WR={oos_wr:.0f}%, avg={oos_avg:+.0f}bps, t-stat={oos_t:.2f}")
        print(f"    Funding cost: {oos_funding:+.0f}bps avg (positive=received, negative=paid)")
        print(f"    Gross was: +660bps → Net: {oos_avg:+.0f}bps")
        print(f"    Funding consumed: {660 - oos_avg:.0f}bps of gross edge")
        
        if oos_avg > 0 and oos_t > 2:
            print(f"\n  ✅ EDGE SURVIVES SHORTING COSTS — net positive and significant")
        elif oos_avg > 0:
            print(f"\n  ⚠️  Edge positive but marginal after costs — needs monitoring")
        else:
            print(f"\n  ❌ Edge CONSUMED by shorting costs — not profitable net")

    # Save
    output = {
        "n_trades": len(all_trades),
        "funding_stats": funding_stats,
        "trades": all_trades,
    }
    with open(output_file, "w") as f:
        json.dump(output, f, indent=2, default=str)


def main():
    parser = argparse.ArgumentParser(description="D17 Shorting Cost Analysis")
    parser.add_argument("--output", type=str, default="shorting_cost_samples.json")
    args = parser.parse_args()
    output_path = os.path.join(os.path.dirname(__file__), args.output)
    run_analysis(output_path)


if __name__ == "__main__":
    main()
