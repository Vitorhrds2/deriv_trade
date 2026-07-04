#!/usr/bin/env python3
"""
D15: Combined Funding Signal + Trend Following.

Hypothesis: Using funding rate as a filter for trend following improves
risk-adjusted returns. Specifically:
- Only enter LONG when SMA(10) > SMA(50) AND funding is not extremely positive
  (avoid long when market is overleveraged long)
- Only enter SHORT when SMA(10) < SMA(50) AND funding is positive
  (short when trend is down AND longs are crowded)

D13 showed: short side of funding signal works (WR 37-43% at 72h)
D14 showed: SMA(10/50) long+short has Sharpe 1.16 OOS (but N=7)

This test combines both signals to see if the combination improves:
- Win rate
- Sharpe
- Drawdown
- Number of trades (quality over quantity)

D15a — Fetch funding + daily candles for BTC/ETH
D15b — Backtest 4 variants:
       1. Pure trend (SMA 10/50 long+short) — baseline
       2. Trend + funding filter (skip trades when funding contradicts)
       3. Funding-only signal (from D13)
       4. Trend + extreme funding boost (size up when funding confirms)
D15c — Walk-forward 70/30, compare Sharpe/WR/MaxDD

All data via Binance public API. Read-only.
"""
import argparse
import json
import math
import os
import time
import urllib.request
from datetime import datetime, timezone

BINANCE_FAPI = "https://fapi.binance.com"
BINANCE_SAPI = "https://api.binance.com/api/v3"
UA = {"User-Agent": "combined-signal-scan/1.0 (research; read-only)"}


def http_get(url, timeout=15):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


def fetch_funding(symbol, limit=500):
    data = http_get(f"{BINANCE_FAPI}/fapi/v1/fundingRate?symbol={symbol}&limit={limit}")
    return [(r["fundingTime"], float(r["fundingRate"])) for r in data]


def fetch_daily_candles(symbol, limit=1000):
    data = http_get(f"{BINANCE_SAPI}/klines?symbol={symbol}&interval=1d&limit={limit}")
    return [{"ts": c[0], "open": float(c[1]), "high": float(c[2]),
             "low": float(c[3]), "close": float(c[4]), "volume": float(c[5])} for c in data]


def mean(x):
    return sum(x) / len(x) if x else 0


def std(x):
    if len(x) < 2:
        return 0
    m = mean(x)
    return math.sqrt(sum((xi - m) ** 2 for xi in x) / (len(x) - 1))


def sma(values, window):
    result = []
    for i in range(len(values)):
        if i < window - 1:
            result.append(None)
        else:
            result.append(mean(values[i - window + 1:i + 1]))
    return result


def get_funding_at_time(funding_data, timestamp_ms):
    """Get the most recent funding rate before the given timestamp."""
    best = None
    for ft, fr in funding_data:
        if ft <= timestamp_ms:
            best = fr
        else:
            break
    return best


def get_funding_percentile(funding_rates, current_rate, side):
    """Get percentile of current funding rate. side='pos' for positive, 'neg' for negative."""
    if side == "pos":
        pos_rates = sorted([f for f in funding_rates if f > 0])
        if not pos_rates:
            return 50
        idx = sum(1 for r in pos_rates if r <= current_rate)
        return idx / len(pos_rates) * 100
    else:
        neg_rates = sorted([f for f in funding_rates if f < 0])
        if not neg_rates:
            return 50
        idx = sum(1 for r in neg_rates if r <= current_rate)
        return idx / len(neg_rates) * 100


def backtest_pure_trend(candles, fast_w, slow_w, fee_bps=10):
    """SMA crossover long+short — baseline from D14."""
    closes = [c["close"] for c in candles]
    fast_ma = sma(closes, fast_w)
    slow_ma = sma(closes, slow_w)

    position = 0
    trades = []
    entry_idx = 0
    entry_price = 0

    for i in range(slow_w, len(closes)):
        if fast_ma[i] is None or slow_ma[i] is None:
            continue

        if position == 0:
            if fast_ma[i] > slow_ma[i]:
                position = 1
                entry_idx = i
                entry_price = closes[i]
            elif fast_ma[i] < slow_ma[i]:
                position = -1
                entry_idx = i
                entry_price = closes[i]
        elif position == 1:
            if fast_ma[i] < slow_ma[i]:
                exit_price = closes[i]
                pnl = (exit_price - entry_price) / entry_price * 10000 - fee_bps * 2
                trades.append({"pnl_bps": pnl, "days_held": i - entry_idx, "direction": "long"})
                position = -1
                entry_idx = i
                entry_price = closes[i]
        elif position == -1:
            if fast_ma[i] > slow_ma[i]:
                exit_price = closes[i]
                pnl = (entry_price - exit_price) / entry_price * 10000 - fee_bps * 2
                trades.append({"pnl_bps": pnl, "days_held": i - entry_idx, "direction": "short"})
                position = 1
                entry_idx = i
                entry_price = closes[i]

    if position == 1:
        pnl = (closes[-1] - entry_price) / entry_price * 10000 - fee_bps * 2
        trades.append({"pnl_bps": pnl, "days_held": len(closes) - 1 - entry_idx, "direction": "long"})
    elif position == -1:
        pnl = (entry_price - closes[-1]) / entry_price * 10000 - fee_bps * 2
        trades.append({"pnl_bps": pnl, "days_held": len(closes) - 1 - entry_idx, "direction": "short"})

    return trades


def backtest_trend_with_funding_filter(candles, funding_data, fast_w, slow_w,
                                       funding_threshold_pct=75, fee_bps=10):
    """SMA crossover + funding filter:
    - Long: SMA fast > slow AND funding NOT extremely positive (pct < threshold)
    - Short: SMA fast < slow AND funding IS positive (pct > 50, or just > 0)
    - Skip trades where funding contradicts the trend signal
    """
    closes = [c["close"] for c in candles]
    fast_ma = sma(closes, fast_w)
    slow_ma = sma(closes, slow_w)

    all_funding_rates = [f[1] for f in funding_data]

    position = 0
    trades = []
    entry_idx = 0
    entry_price = 0
    skipped_long = 0
    skipped_short = 0

    for i in range(slow_w, len(closes)):
        if fast_ma[i] is None or slow_ma[i] is None:
            continue

        current_funding = get_funding_at_time(funding_data, candles[i]["ts"])

        if position == 0:
            if fast_ma[i] > slow_ma[i]:
                # Long signal — check funding
                if current_funding is not None and current_funding > 0:
                    funding_pct = get_funding_percentile(all_funding_rates, current_funding, "pos")
                    if funding_pct > funding_threshold_pct:
                        skipped_long += 1
                    else:
                        position = 1
                        entry_idx = i
                        entry_price = closes[i]
                else:
                    position = 1
                    entry_idx = i
                    entry_price = closes[i]
            elif fast_ma[i] < slow_ma[i]:
                # Short signal — check funding (only short when funding is positive = longs crowded)
                if current_funding is not None and current_funding > 0:
                    position = -1
                    entry_idx = i
                    entry_price = closes[i]
                else:
                    skipped_short += 1
        elif position == 1:
            if fast_ma[i] < slow_ma[i]:
                exit_price = closes[i]
                pnl = (exit_price - entry_price) / entry_price * 10000 - fee_bps * 2
                trades.append({"pnl_bps": pnl, "days_held": i - entry_idx, "direction": "long"})
                # Check if we should enter short
                current_funding = get_funding_at_time(funding_data, candles[i]["ts"])
                if current_funding is not None and current_funding > 0:
                    position = -1
                    entry_idx = i
                    entry_price = closes[i]
                else:
                    position = 0
        elif position == -1:
            if fast_ma[i] > slow_ma[i]:
                exit_price = closes[i]
                pnl = (entry_price - exit_price) / entry_price * 10000 - fee_bps * 2
                trades.append({"pnl_bps": pnl, "days_held": i - entry_idx, "direction": "short"})
                # Check if we should enter long
                current_funding = get_funding_at_time(funding_data, candles[i]["ts"])
                if current_funding is not None and current_funding > 0:
                    funding_pct = get_funding_percentile(all_funding_rates, current_funding, "pos")
                    if funding_pct <= funding_threshold_pct:
                        position = 1
                        entry_idx = i
                        entry_price = closes[i]
                else:
                    position = 1
                    entry_idx = i
                    entry_price = closes[i]

    if position == 1:
        pnl = (closes[-1] - entry_price) / entry_price * 10000 - fee_bps * 2
        trades.append({"pnl_bps": pnl, "days_held": len(closes) - 1 - entry_idx, "direction": "long"})
    elif position == -1:
        pnl = (entry_price - closes[-1]) / entry_price * 10000 - fee_bps * 2
        trades.append({"pnl_bps": pnl, "days_held": len(closes) - 1 - entry_idx, "direction": "short"})

    return trades, skipped_long, skipped_short


def backtest_funding_only(candles, funding_data, horizon_hours=72, fee_bps=5):
    """Funding-only signal from D13: short when funding positive, exit after 72h."""
    closes_by_ts = {c["ts"]: c["close"] for c in candles}
    all_closes = [(c["ts"], c["close"]) for c in candles]

    trades = []

    for ft, fr in funding_data:
        if fr <= 0:
            continue  # Only short side (D13 showed long side doesn't work)

        # Find entry price (nearest daily close at or before funding time)
        entry_price = None
        entry_ts = None
        for ts, price in all_closes:
            if ts <= ft:
                entry_price = price
                entry_ts = ts
            else:
                break

        if entry_price is None:
            continue

        # Exit after horizon_hours
        exit_ts = ft + horizon_hours * 3600 * 1000
        exit_price = None
        for ts, price in all_closes:
            if ts >= exit_ts:
                exit_price = price
                break
        if exit_price is None:
            exit_price = all_closes[-1][1]

        pnl = (entry_price - exit_price) / entry_price * 10000 - fee_bps * 2
        trades.append({"pnl_bps": pnl, "days_held": horizon_hours / 24, "direction": "short"})

    return trades


def summarize(trades, name):
    if not trades:
        return {"name": name, "n_trades": 0, "total_pnl_bps": 0, "win_rate": 0,
                "sharpe": 0, "max_dd_bps": 0, "avg_hold_days": 0, "avg_pnl_bps": 0}

    pnls = [t["pnl_bps"] for t in trades]
    total = sum(pnls)
    wins = sum(1 for p in pnls if p > 0)
    wr = wins / len(pnls) * 100
    avg = mean(pnls)
    s = std(pnls)
    avg_hold = mean([t["days_held"] for t in trades])
    tpy = 252 / max(1, avg_hold)
    sharpe = (avg / s * math.sqrt(tpy)) if s > 0 else 0

    cum = [0]
    for p in pnls:
        cum.append(cum[-1] + p)
    peak = cum[0]
    max_dd = 0
    for c in cum:
        if c > peak:
            peak = c
        dd = peak - c
        if dd > max_dd:
            max_dd = dd

    long_trades = [t for t in trades if t["direction"] == "long"]
    short_trades = [t for t in trades if t["direction"] == "short"]
    long_wr = (sum(1 for t in long_trades if t["pnl_bps"] > 0) / len(long_trades) * 100) if long_trades else 0
    short_wr = (sum(1 for t in short_trades if t["pnl_bps"] > 0) / len(short_trades) * 100) if short_trades else 0

    return {
        "name": name, "n_trades": len(trades), "total_pnl_bps": total,
        "avg_pnl_bps": avg, "win_rate": wr, "sharpe": sharpe,
        "max_dd_bps": max_dd, "avg_hold_days": avg_hold,
        "n_long": len(long_trades), "n_short": len(short_trades),
        "long_wr": long_wr, "short_wr": short_wr,
    }


def run_scan(output_file, symbols, limit):
    print("D15: Combined Funding Signal + Trend Following")
    print(f"Symbols: {', '.join(symbols)}")
    print(f"API: Binance public (no API key)")
    print(f"{'='*80}\n")

    all_results = {}

    for symbol in symbols:
        print(f"\n  [{symbol}]")
        candles = fetch_daily_candles(symbol, limit)
        funding = fetch_funding(symbol, 500)
        print(f"    Candles: {len(candles)}d, Funding events: {len(funding)}")

        if len(candles) < 200 or len(funding) < 50:
            print(f"    Skipping — insufficient data")
            continue

        # Walk-forward
        split = int(len(candles) * 0.7)
        train_c = candles[:split]
        test_c = candles[split:]
        train_f = [f for f in funding if f[0] <= train_c[-1]["ts"]]
        test_f = [f for f in funding if f[0] >= test_c[0]["ts"]]
        print(f"    Train: {len(train_c)}d, Test: {len(test_c)}d")

        # Buy & hold benchmark
        closes = [c["close"] for c in candles]
        bh_ret = (closes[-1] - closes[0]) / closes[0] * 100
        daily_rets = [(closes[i] / closes[i - 1] - 1) for i in range(1, len(closes))]
        bh_sharpe = (mean(daily_rets) / std(daily_rets) * math.sqrt(365.25)) if std(daily_rets) > 0 else 0
        print(f"    Buy & Hold: {bh_ret:+.1f}%, Sharpe={bh_sharpe:.2f}")

        results = {}

        # Strategy 1: Pure trend (baseline)
        for label, data in [("train", train_c), ("test", test_c)]:
            trades = backtest_pure_trend(data, 10, 50)
            results[f"pure_trend_{label}"] = summarize(trades, "Pure SMA(10/50) long+short")

        # Strategy 2: Trend + funding filter (75th percentile)
        for label, data, fdata in [("train", train_c, train_f), ("test", test_c, test_f)]:
            trades, sk_l, sk_s = backtest_trend_with_funding_filter(data, fdata, 10, 50, 75)
            s = summarize(trades, "Trend + funding filter (75th pct)")
            s["skipped_long"] = sk_l
            s["skipped_short"] = sk_s
            results[f"trend_funding_filter_{label}"] = s

        # Strategy 3: Trend + funding filter (90th percentile — more extreme)
        for label, data, fdata in [("train", train_c, train_f), ("test", test_c, test_f)]:
            trades, sk_l, sk_s = backtest_trend_with_funding_filter(data, fdata, 10, 50, 90)
            s = summarize(trades, "Trend + funding filter (90th pct)")
            s["skipped_long"] = sk_l
            s["skipped_short"] = sk_s
            results[f"trend_funding_filter_90_{label}"] = s

        # Strategy 4: Funding-only (baseline from D13)
        for label, data, fdata in [("train", train_c, train_f), ("test", test_c, test_f)]:
            trades = backtest_funding_only(data, fdata, 72)
            results[f"funding_only_{label}"] = summarize(trades, "Funding-only short (72h)")

        # Print comparison
        print(f"\n    {'Strategy':40s} {'N':>4s} {'WR':>5s} {'PnL':>9s} {'Sharpe':>7s} {'MaxDD':>8s} {'L_wr':>5s} {'S_wr':>5s}")
        print("    " + "-" * 90)

        for key in ["pure_trend", "trend_funding_filter", "trend_funding_filter_90", "funding_only"]:
            for phase in ["train", "test"]:
                k = f"{key}_{phase}"
                if k in results:
                    r = results[k]
                    if r["n_trades"] > 0:
                        print(f"    {r['name']+' ['+phase+']':40s} {r['n_trades']:4d} {r['win_rate']:4.0f}% "
                              f"{r['total_pnl_bps']:+8.0f} {r['sharpe']:6.2f} {r['max_dd_bps']:7.0f} "
                              f"{r.get('long_wr', 0):4.0f}% {r.get('short_wr', 0):4.0f}%")
                    else:
                        print(f"    {r['name']+' ['+phase+']':40s}  no trades")

        # Key comparison: OOS pure trend vs OOS combined
        oos_pure = results.get("pure_trend_test", {})
        oos_combined = results.get("trend_funding_filter_test", {})
        oos_combined90 = results.get("trend_funding_filter_90_test", {})

        print(f"\n    OOS COMPARISON:")
        if oos_pure.get("n_trades", 0) > 0:
            print(f"      Pure trend:       Sharpe={oos_pure['sharpe']:.2f}, WR={oos_pure['win_rate']:.0f}%, "
                  f"N={oos_pure['n_trades']}, MaxDD={oos_pure['max_dd_bps']:.0f}bps")
        if oos_combined.get("n_trades", 0) > 0:
            print(f"      Trend+funding 75: Sharpe={oos_combined['sharpe']:.2f}, WR={oos_combined['win_rate']:.0f}%, "
                  f"N={oos_combined['n_trades']}, MaxDD={oos_combined['max_dd_bps']:.0f}bps, "
                  f"skipped={oos_combined.get('skipped_long',0)+oos_combined.get('skipped_short',0)}")
        if oos_combined90.get("n_trades", 0) > 0:
            print(f"      Trend+funding 90: Sharpe={oos_combined90['sharpe']:.2f}, WR={oos_combined90['win_rate']:.0f}%, "
                  f"N={oos_combined90['n_trades']}, MaxDD={oos_combined90['max_dd_bps']:.0f}bps, "
                  f"skipped={oos_combined90.get('skipped_long',0)+oos_combined90.get('skipped_short',0)}")

        all_results[symbol] = {
            "buy_hold_return_pct": bh_ret,
            "buy_hold_sharpe": bh_sharpe,
            "n_candles": len(candles),
            "n_funding": len(funding),
            "train_days": len(train_c),
            "test_days": len(test_c),
            "results": results,
        }

    # Save
    with open(output_file, "w") as f:
        json.dump(all_results, f, indent=2, default=str)

    # Summary
    print(f"\n{'='*80}")
    print(f"SUMMARY\n")

    for symbol, data in all_results.items():
        print(f"  {symbol}:")
        print(f"    Buy & Hold: {data['buy_hold_return_pct']:+.1f}%, Sharpe={data['buy_hold_sharpe']:.2f}")
        oos_pure = data["results"].get("pure_trend_test", {})
        oos_comb = data["results"].get("trend_funding_filter_test", {})
        oos_comb90 = data["results"].get("trend_funding_filter_90_test", {})

        if oos_pure.get("n_trades", 0) > 0 and oos_comb.get("n_trades", 0) > 0:
            delta_sharpe = oos_comb["sharpe"] - oos_pure["sharpe"]
            delta_wr = oos_comb["win_rate"] - oos_pure["win_rate"]
            delta_dd = oos_comb["max_dd_bps"] - oos_pure["max_dd_bps"]
            print(f"    Pure trend OOS:       Sharpe={oos_pure['sharpe']:.2f}, WR={oos_pure['win_rate']:.0f}%, "
                  f"N={oos_pure['n_trades']}, MaxDD={oos_pure['max_dd_bps']:.0f}bps")
            print(f"    Combined OOS (75th):  Sharpe={oos_comb['sharpe']:.2f}, WR={oos_comb['win_rate']:.0f}%, "
                  f"N={oos_comb['n_trades']}, MaxDD={oos_comb['max_dd_bps']:.0f}bps")
            print(f"    Delta: Sharpe {delta_sharpe:+.2f}, WR {delta_wr:+.0f}pp, MaxDD {delta_dd:+.0f}bps")
            if oos_comb90.get("n_trades", 0) > 0:
                print(f"    Combined OOS (90th):  Sharpe={oos_comb90['sharpe']:.2f}, WR={oos_comb90['win_rate']:.0f}%, "
                      f"N={oos_comb90['n_trades']}, MaxDD={oos_comb90['max_dd_bps']:.0f}bps")

    print(f"\n  PROFITABILITY ANALYSIS:")
    print(f"  - D13 showed funding signal works on short side (WR 37-43%) at 72h")
    print(f"  - D14 showed SMA(10/50) long+short has Sharpe 1.16 OOS (N=7)")
    print(f"  - D15 tests if combining both improves risk-adjusted returns")
    print(f"  - Key question: does filtering out trend trades when funding")
    print(f"    contradicts the signal improve win rate and Sharpe?")
    print(f"  - Fees: 10 bps/side × 2 = 20 bps per round trip (spot)")


def main():
    parser = argparse.ArgumentParser(description="D15 Combined Funding + Trend Following")
    parser.add_argument("--output", type=str, default="combined_signal_samples.json")
    parser.add_argument("--symbols", type=str, nargs="+", default=["BTCUSDT", "ETHUSDT", "SOLUSDT"])
    parser.add_argument("--limit", type=int, default=1000)
    args = parser.parse_args()

    output_path = os.path.join(os.path.dirname(__file__), args.output)
    run_scan(output_path, args.symbols, args.limit)


if __name__ == "__main__":
    main()
