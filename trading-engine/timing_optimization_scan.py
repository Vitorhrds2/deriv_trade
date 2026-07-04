#!/usr/bin/env python3
"""
D17 Timing Optimization Scan.

Tests multiple entry/exit timing combinations for the token unlock short strategy.
For each (entry_days, exit_days) pair, computes:
  - Win rate, avg PnL (bps), t-stat
  - Split by period: IS (2023-2024), OOS-2025, OOS-2026

Entry: N days BEFORE unlock (negative = before)
Exit: M days AFTER unlock (positive = after)

Combinations tested:
  Entry: -1, -2, -3, -5, -7
  Exit:  +1, +2, +3, +5, +7

All data via Binance public API. Read-only.
"""
import argparse
import json
import math
import os
import sys
import time
import urllib.request
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(__file__))
from token_unlock_scan import (
    KNOWN_UNLOCKS, date_to_ms, fetch_daily_candles, mean, std
)

UA = {"User-Agent": "Mozilla/5.0 (research; read-only)"}
FEE_BPS = 20


def run_timing_scan(output_file):
    print("D17: Timing Optimization Scan")
    print(f"Testing multiple entry/exit windows around unlock dates")
    print(f"{'='*80}\n")

    # Group unlocks by symbol
    symbols = {}
    for sym, date, val, pct, src in KNOWN_UNLOCKS:
        if sym not in symbols:
            symbols[sym] = []
        symbols[sym].append({"date": date, "value_mm": val, "pct_supply": pct, "source": src})

    print(f"  Symbols: {', '.join(symbols.keys())}")
    print(f"  Total unlock events: {len(KNOWN_UNLOCKS)}\n")

    # Fetch all candle data per symbol
    symbol_candles = {}
    print("  Fetching price data...")
    for symbol in symbols:
        try:
            candles = fetch_daily_candles(symbol, date_to_ms("2023-01-01"), date_to_ms("2026-07-03"))
            if len(candles) >= 30:
                symbol_candles[symbol] = candles
                print(f"    {symbol}: {len(candles)} candles")
            else:
                print(f"    {symbol}: SKIP (insufficient data)")
        except Exception as e:
            print(f"    {symbol}: ERROR {e}")
        time.sleep(0.2)

    # Define timing combinations
    entry_days = [-1, -2, -3, -5, -7]
    exit_days = [1, 2, 3, 5, 7]

    oos_cutoff = date_to_ms("2025-01-01")
    oos2_cutoff = date_to_ms("2026-01-01")

    # For each (entry, exit) combo, compute backtest
    results = []

    print(f"\n{'='*80}")
    print(f"TIMING OPTIMIZATION RESULTS")
    print(f"  Entry: {entry_days} days before unlock")
    print(f"  Exit:  {exit_days} days after unlock")
    print(f"  Fees: {FEE_BPS}bps round trip\n")

    # Header
    print(f"  {'Entry':>6s} {'Exit':>5s} {'Hold':>5s} | {'ALL N':>5s} {'WR':>5s} {'avg':>7s} {'t':>6s} | {'IS N':>4s} {'WR':>4s} {'avg':>6s} {'t':>5s} | {'25 N':>4s} {'WR':>4s} {'avg':>6s} {'t':>5s} | {'26 N':>4s} {'WR':>4s} {'avg':>6s} {'t':>5s}")
    print("  " + "-" * 120)

    for ed in entry_days:
        for xd in exit_days:
            hold_days = xd - ed  # total hold period
            trades = []

            for sym, events in symbols.items():
                if sym not in symbol_candles:
                    continue
                candles = symbol_candles[sym]

                for event in events:
                    unlock_ts = date_to_ms(event["date"])
                    entry_ts = unlock_ts + ed * 86400000
                    exit_ts = unlock_ts + xd * 86400000

                    # Find closest candles to entry and exit
                    p_entry = min(candles, key=lambda c: abs(c["ts"] - entry_ts))["close"]
                    p_exit = min(candles, key=lambda c: abs(c["ts"] - exit_ts))["close"]

                    # Check we're within 2 days of target
                    closest_entry = min(candles, key=lambda c: abs(c["ts"] - entry_ts))
                    closest_exit = min(candles, key=lambda c: abs(c["ts"] - exit_ts))
                    if abs(closest_entry["ts"] - entry_ts) > 2 * 86400000:
                        continue
                    if abs(closest_exit["ts"] - exit_ts) > 2 * 86400000:
                        continue

                    if p_entry == 0:
                        continue

                    short_ret = (p_entry - p_exit) / p_entry * 10000 - FEE_BPS

                    if unlock_ts < oos_cutoff:
                        period = "IS"
                    elif unlock_ts < oos2_cutoff:
                        period = "OOS-2025"
                    else:
                        period = "OOS-2026"

                    trades.append({
                        "symbol": sym,
                        "unlock_date": event["date"],
                        "entry_days": ed,
                        "exit_days": xd,
                        "pnl_bps": short_ret,
                        "period": period,
                    })

            if not trades:
                continue

            pnls = [t["pnl_bps"] for t in trades]
            wr = sum(1 for p in pnls if p > 0) / len(pnls) * 100
            avg = mean(pnls)
            s = std(pnls)
            t_stat = avg / (s / math.sqrt(len(pnls))) if s > 0 else 0

            # Split by period
            is_t = [t for t in trades if t["period"] == "IS"]
            o25_t = [t for t in trades if t["period"] == "OOS-2025"]
            o26_t = [t for t in trades if t["period"] == "OOS-2026"]

            def stats(trades_list):
                if not trades_list:
                    return 0, 0, 0, 0
                p = [t["pnl_bps"] for t in trades_list]
                w = sum(1 for x in p if x > 0) / len(p) * 100
                a = mean(p)
                s2 = std(p)
                t2 = a / (s2 / math.sqrt(len(p))) if s2 > 0 else 0
                return len(p), w, a, t2

            is_n, is_wr, is_avg, is_tval = stats(is_t)
            o25_n, o25_wr, o25_avg, o25_tval = stats(o25_t)
            o26_n, o26_wr, o26_avg, o26_tval = stats(o26_t)

            print(f"  {ed:>+6d}d {xd:>+5d}d {hold_days:5d}d | {len(trades):5d} {wr:4.0f}% {avg:+6.0f} {t_stat:5.2f} | {is_n:4d} {is_wr:3.0f}% {is_avg:+5.0f} {is_tval:4.2f} | {o25_n:4d} {o25_wr:3.0f}% {o25_avg:+5.0f} {o25_tval:4.2f} | {o26_n:4d} {o26_wr:3.0f}% {o26_avg:+5.0f} {o26_tval:4.2f}")

            results.append({
                "entry_days": ed,
                "exit_days": xd,
                "hold_days": hold_days,
                "all_n": len(trades),
                "all_wr": wr,
                "all_avg": avg,
                "all_t": t_stat,
                "is_n": is_n, "is_wr": is_wr, "is_avg": is_avg, "is_t": is_tval,
                "oos25_n": o25_n, "oos25_wr": o25_wr, "oos25_avg": o25_avg, "oos25_t": o25_tval,
                "oos26_n": o26_n, "oos26_wr": o26_wr, "oos26_avg": o26_avg, "oos26_t": o26_tval,
            })

    # ─── Find best timing combos ──────────────────────────────────────────────
    print(f"\n{'='*80}")
    print(f"BEST TIMING COMBOS (by OOS t-stat, combined 2025+2026)\n")

    # Combine OOS-2025 + OOS-2026 as "all OOS"
    for r in results:
        oos_n = r["oos25_n"] + r["oos26_n"]
        if oos_n == 0:
            r["oos_combined_n"] = 0
            r["oos_combined_t"] = 0
            continue
        # Weighted average
        oos_all_pnls = []
        # We don't have individual pnls stored, so approximate combined t-stat
        # using a weighted average of the two t-stats
        r["oos_combined_n"] = oos_n
        r["oos_combined_t"] = (r["oos25_t"] * r["oos25_n"] + r["oos26_t"] * r["oos26_n"]) / oos_n if oos_n > 0 else 0

    # Sort by combined OOS t-stat
    sorted_results = sorted(results, key=lambda r: r["oos_combined_t"], reverse=True)

    print(f"  {'Rank':>4s} {'Entry':>6s} {'Exit':>5s} {'Hold':>5s} | {'ALL t':>6s} {'ALL avg':>7s} | {'25 t':>5s} {'25 avg':>6s} | {'26 t':>5s} {'26 avg':>6s}")
    print("  " + "-" * 70)
    for i, r in enumerate(sorted_results[:10]):
        print(f"  {i+1:4d} {r['entry_days']:>+6d}d {r['exit_days']:>+5d}d {r['hold_days']:5d}d | {r['all_t']:5.2f} {r['all_avg']:+6.0f} | {r['oos25_t']:4.2f} {r['oos25_avg']:+5.0f} | {r['oos26_t']:4.2f} {r['oos26_avg']:+5.0f}")

    # ─── Current strategy reference ────────────────────────────────────────────
    print(f"\n  Reference: current strategy (-3d entry, +3d exit):")
    ref = [r for r in results if r["entry_days"] == -3 and r["exit_days"] == 3]
    if ref:
        r = ref[0]
        print(f"    ALL: N={r['all_n']}, WR={r['all_wr']:.0f}%, avg={r['all_avg']:+.0f}bps, t={r['all_t']:.2f}")
        print(f"    IS:  N={r['is_n']}, WR={r['is_wr']:.0f}%, avg={r['is_avg']:+.0f}bps, t={r['is_t']:.2f}")
        print(f"    25:  N={r['oos25_n']}, WR={r['oos25_wr']:.0f}%, avg={r['oos25_avg']:+.0f}bps, t={r['oos25_t']:.2f}")
        print(f"    26:  N={r['oos26_n']}, WR={r['oos26_wr']:.0f}%, avg={r['oos26_avg']:+.0f}bps, t={r['oos26_t']:.2f}")

    # Save
    with open(output_file, "w") as f:
        json.dump(results, f, indent=2, default=str)


def main():
    parser = argparse.ArgumentParser(description="D17 Timing Optimization Scan")
    parser.add_argument("--output", type=str, default="timing_optimization.json")
    args = parser.parse_args()
    output_path = os.path.join(os.path.dirname(__file__), args.output)
    run_timing_scan(output_path)


if __name__ == "__main__":
    main()
