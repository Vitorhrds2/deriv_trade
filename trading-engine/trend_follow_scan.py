#!/usr/bin/env python3
"""
D14: BTC Trend Following (Multi-Day Momentum).

Hypothesis: BTC exhibits momentum at multi-day timeframes. A trend-following
strategy using moving average crossovers or breakout signals can capture
directional moves that exceed transaction costs.

D14a — Fetch BTC daily candles from Binance (full history)
D14b — Backtest multiple trend-following strategies:
       - MA crossover (fast/slow)
       - Breakout (N-day high/low)
       - Time series momentum (return over lookback)
D14c — Walk-forward validation (70/30 split)
D14d — Calculate Sharpe, win rate, max drawdown after fees

All data via Binance public API. Read-only, no trading.
"""
import argparse
import json
import math
import os
import time
import urllib.request
from datetime import datetime, timezone

BINANCE_API = "https://api.binance.com/api/v3"
UA = {"User-Agent": "trend-follow-scan/1.0 (research; read-only)"}


def binance_get(endpoint: str, params: dict = None, timeout: int = 15) -> dict:
    url = f"{BINANCE_API}/{endpoint}"
    if params:
        query = "&".join(f"{k}={v}" for k, v in params.items())
        url += f"?{query}"
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


def fetch_daily_candles(symbol: str, limit: int = 1000) -> list:
    """Fetch daily OHLCV from Binance spot."""
    result = binance_get("klines", {
        "symbol": symbol,
        "interval": "1d",
        "limit": limit,
    })
    candles = []
    for c in result:
        candles.append({
            "timestamp": c[0],
            "open": float(c[1]),
            "high": float(c[2]),
            "low": float(c[3]),
            "close": float(c[4]),
            "volume": float(c[5]),
        })
    return candles


def mean(x):
    return sum(x) / len(x) if x else 0


def std(x):
    if len(x) < 2:
        return 0
    m = mean(x)
    return math.sqrt(sum((xi - m) ** 2 for xi in x) / (len(x) - 1))


def sma(values, window):
    """Simple moving average."""
    result = []
    for i in range(len(values)):
        if i < window - 1:
            result.append(None)
        else:
            result.append(mean(values[i-window+1:i+1]))
    return result


def ema(values, window):
    """Exponential moving average."""
    result = []
    multiplier = 2 / (window + 1)
    for i in range(len(values)):
        if i == 0:
            result.append(values[0])
        else:
            prev = result[-1]
            result.append(values[i] * multiplier + prev * (1 - multiplier))
    return result


# ─── Strategy backtests ──────────────────────────────────────────────────────

def backtest_ma_crossover(candles, fast_window, slow_window, fee_bps=10):
    """MA crossover: long when fast > slow, flat when fast < slow."""
    closes = [c["close"] for c in candles]
    fast_ma = sma(closes, fast_window)
    slow_ma = sma(closes, slow_window)

    position = 0  # 0=flat, 1=long
    trades = []
    entry_idx = 0
    entry_price = 0

    for i in range(slow_window, len(closes)):
        if fast_ma[i] is None or slow_ma[i] is None:
            continue

        if position == 0:
            if fast_ma[i] > slow_ma[i]:
                position = 1
                entry_idx = i
                entry_price = closes[i]
        elif position == 1:
            if fast_ma[i] < slow_ma[i]:
                # Exit
                exit_price = closes[i]
                pnl_bps = (exit_price - entry_price) / entry_price * 10000 - fee_bps * 2
                trades.append({
                    "entry_idx": entry_idx,
                    "exit_idx": i,
                    "pnl_bps": pnl_bps,
                    "days_held": i - entry_idx,
                    "direction": "long",
                })
                position = 0

    # Close at end
    if position == 1 and len(closes) > 0:
        exit_price = closes[-1]
        pnl_bps = (exit_price - entry_price) / entry_price * 10000 - fee_bps * 2
        trades.append({
            "entry_idx": entry_idx,
            "exit_idx": len(closes) - 1,
            "pnl_bps": pnl_bps,
            "days_held": len(closes) - 1 - entry_idx,
            "direction": "long",
        })

    return trades


def backtest_breakout(candles, lookback, fee_bps=10):
    """Donchian breakout: long when close > N-day high, exit when close < N-day low."""
    closes = [c["close"] for c in candles]
    highs = [c["high"] for c in candles]
    lows = [c["low"] for c in candles]

    position = 0
    trades = []
    entry_idx = 0
    entry_price = 0

    for i in range(lookback, len(closes)):
        # N-day high/low (excluding current day)
        n_high = max(highs[i-lookback:i])
        n_low = min(lows[i-lookback:i])

        if position == 0:
            if closes[i] > n_high:
                position = 1
                entry_idx = i
                entry_price = closes[i]
        elif position == 1:
            if closes[i] < n_low:
                exit_price = closes[i]
                pnl_bps = (exit_price - entry_price) / entry_price * 10000 - fee_bps * 2
                trades.append({
                    "entry_idx": entry_idx,
                    "exit_idx": i,
                    "pnl_bps": pnl_bps,
                    "days_held": i - entry_idx,
                    "direction": "long",
                })
                position = 0

    if position == 1 and len(closes) > 0:
        exit_price = closes[-1]
        pnl_bps = (exit_price - entry_price) / entry_price * 10000 - fee_bps * 2
        trades.append({
            "entry_idx": entry_idx,
            "exit_idx": len(closes) - 1,
            "pnl_bps": pnl_bps,
            "days_held": len(closes) - 1 - entry_idx,
            "direction": "long",
        })

    return trades


def backtest_tsmom(candles, lookback, fee_bps=10):
    """Time series momentum: long if return over lookback > 0, flat if < 0."""
    closes = [c["close"] for c in candles]

    position = 0
    trades = []
    entry_idx = 0
    entry_price = 0

    for i in range(lookback, len(closes)):
        lookback_return = (closes[i] - closes[i - lookback]) / closes[i - lookback]

        if position == 0:
            if lookback_return > 0:
                position = 1
                entry_idx = i
                entry_price = closes[i]
        elif position == 1:
            if lookback_return < 0:
                exit_price = closes[i]
                pnl_bps = (exit_price - entry_price) / entry_price * 10000 - fee_bps * 2
                trades.append({
                    "entry_idx": entry_idx,
                    "exit_idx": i,
                    "pnl_bps": pnl_bps,
                    "days_held": i - entry_idx,
                    "direction": "long",
                })
                position = 0

    if position == 1 and len(closes) > 0:
        exit_price = closes[-1]
        pnl_bps = (exit_price - entry_price) / entry_price * 10000 - fee_bps * 2
        trades.append({
            "entry_idx": entry_idx,
            "exit_idx": len(closes) - 1,
            "pnl_bps": pnl_bps,
            "days_held": len(closes) - 1 - entry_idx,
            "direction": "long",
        })

    return trades


def backtest_dual_ma_with_short(candles, fast_window, slow_window, fee_bps=10):
    """MA crossover with short: long when fast > slow, short when fast < slow."""
    closes = [c["close"] for c in candles]
    fast_ma = sma(closes, fast_window)
    slow_ma = sma(closes, slow_window)

    position = 0  # 0=flat, 1=long, -1=short
    trades = []
    entry_idx = 0
    entry_price = 0

    for i in range(slow_window, len(closes)):
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
                # Exit long, enter short
                exit_price = closes[i]
                pnl_bps = (exit_price - entry_price) / entry_price * 10000 - fee_bps * 2
                trades.append({"entry_idx": entry_idx, "exit_idx": i, "pnl_bps": pnl_bps,
                               "days_held": i - entry_idx, "direction": "long"})
                # Enter short
                position = -1
                entry_idx = i
                entry_price = closes[i]
        elif position == -1:
            if fast_ma[i] > slow_ma[i]:
                # Exit short, enter long
                exit_price = closes[i]
                pnl_bps = (entry_price - exit_price) / entry_price * 10000 - fee_bps * 2
                trades.append({"entry_idx": entry_idx, "exit_idx": i, "pnl_bps": pnl_bps,
                               "days_held": i - entry_idx, "direction": "short"})
                # Enter long
                position = 1
                entry_idx = i
                entry_price = closes[i]

    # Close at end
    if position == 1 and len(closes) > 0:
        exit_price = closes[-1]
        pnl_bps = (exit_price - entry_price) / entry_price * 10000 - fee_bps * 2
        trades.append({"entry_idx": entry_idx, "exit_idx": len(closes) - 1, "pnl_bps": pnl_bps,
                       "days_held": len(closes) - 1 - entry_idx, "direction": "long"})
    elif position == -1 and len(closes) > 0:
        exit_price = closes[-1]
        pnl_bps = (entry_price - exit_price) / entry_price * 10000 - fee_bps * 2
        trades.append({"entry_idx": entry_idx, "exit_idx": len(closes) - 1, "pnl_bps": pnl_bps,
                       "days_held": len(closes) - 1 - entry_idx, "direction": "short"})

    return trades


def summarize_trades(trades, name):
    if not trades:
        return {"name": name, "n_trades": 0, "total_pnl_bps": 0, "win_rate": 0,
                "sharpe": 0, "max_dd_bps": 0, "avg_hold_days": 0}

    pnls = [t["pnl_bps"] for t in trades]
    total_pnl = sum(pnls)
    wins = sum(1 for p in pnls if p > 0)
    win_rate = wins / len(pnls) * 100
    avg_pnl = mean(pnls)
    s = std(pnls)
    avg_hold = mean([t["days_held"] for t in trades])

    # Annualized Sharpe: ~252 trading days / avg hold days = trades per year
    trades_per_year = 252 / max(1, avg_hold)
    sharpe = (avg_pnl / s * math.sqrt(trades_per_year)) if s > 0 else 0

    # Max drawdown
    cumulative = [0]
    for p in pnls:
        cumulative.append(cumulative[-1] + p)
    peak = cumulative[0]
    max_dd = 0
    for c in cumulative:
        if c > peak:
            peak = c
        dd = peak - c
        if dd > max_dd:
            max_dd = dd

    # Buy & hold comparison
    return {
        "name": name,
        "n_trades": len(trades),
        "total_pnl_bps": total_pnl,
        "avg_pnl_bps": avg_pnl,
        "win_rate": win_rate,
        "sharpe": sharpe,
        "max_dd_bps": max_dd,
        "avg_hold_days": avg_hold,
        "trades": trades,
    }


def run_scan(output_file: str, symbols: list, limit: int):
    print("D14: BTC Trend Following Scan (Multi-Day Momentum)")
    print(f"Symbols: {', '.join(symbols)}")
    print(f"Candles: {limit} daily")
    print(f"API: Binance public (no API key)")
    print(f"{'='*80}\n")

    all_results = {}

    for symbol in symbols:
        print(f"\n  [{symbol}]")
        candles = fetch_daily_candles(symbol, limit)
        print(f"    Fetched {len(candles)} daily candles")
        if len(candles) < 100:
            print(f"    Skipping — insufficient data")
            continue

        # Buy & hold benchmark
        closes = [c["close"] for c in candles]
        bh_pnl_bps = (closes[-1] - closes[0]) / closes[0] * 10000
        bh_return_pct = bh_pnl_bps / 100
        n_days = len(candles)
        bh_annual = ((closes[-1] / closes[0]) ** (365.25 / n_days) - 1) * 100 if closes[0] > 0 else 0
        # Buy & hold Sharpe (daily returns)
        daily_returns = [(closes[i] / closes[i-1] - 1) for i in range(1, len(closes))]
        bh_sharpe = (mean(daily_returns) / std(daily_returns) * math.sqrt(365.25)) if std(daily_returns) > 0 else 0
        print(f"    Buy & Hold: {bh_return_pct:+.1f}% over {n_days}d ({bh_annual:+.1f}% annualized), Sharpe={bh_sharpe:.2f}")

        # Walk-forward: 70% in-sample, 30% out-of-sample
        split = int(len(candles) * 0.7)
        train = candles[:split]
        test = candles[split:]
        print(f"    Walk-forward: train={len(train)}d, test={len(test)}d")

        # ─── Strategy configs to test ──────────────────────────────────────
        strategies = []

        # MA crossover (long only)
        for fast in [5, 10, 20]:
            for slow in [20, 50, 100, 200]:
                if fast >= slow:
                    continue
                strategies.append(("MA_cross_long", f"SMA({fast}/{slow}) long-only",
                                   lambda c, f=fast, s=slow: backtest_ma_crossover(c, f, s)))

        # MA crossover (long + short)
        for fast in [5, 10, 20]:
            for slow in [20, 50, 100, 200]:
                if fast >= slow:
                    continue
                strategies.append(("MA_cross_ls", f"SMA({fast}/{slow}) long+short",
                                   lambda c, f=fast, s=slow: backtest_dual_ma_with_short(c, f, s)))

        # Donchian breakout
        for lb in [10, 20, 50, 100]:
            strategies.append(("breakout", f"Donchian({lb}) long-only",
                               lambda c, l=lb: backtest_breakout(c, l)))

        # Time series momentum
        for lb in [10, 20, 30, 60, 90]:
            strategies.append(("tsmom", f"TSMOM({lb}) long-only",
                               lambda c, l=lb: backtest_tsmom(c, l)))

        # ─── Run all strategies on train + test ────────────────────────────
        train_results = []
        test_results = []

        for strat_type, name, func in strategies:
            train_trades = func(train)
            test_trades = func(test)
            train_summary = summarize_trades(train_trades, name)
            test_summary = summarize_trades(test_trades, name)
            train_summary["type"] = strat_type
            test_summary["type"] = strat_type
            train_results.append(train_summary)
            test_results.append(test_summary)

        # ─── Find best strategies on train set ─────────────────────────────
        train_results.sort(key=lambda x: x["sharpe"], reverse=True)
        print(f"\n    Top 5 strategies (in-sample/train):")
        print(f"    {'Strategy':30s} {'N':>4s} {'WR':>5s} {'PnL_bps':>9s} {'Sharpe':>7s} {'MaxDD':>8s} {'AvgHold':>8s}")
        print("    " + "-" * 75)
        for r in train_results[:5]:
            if r["n_trades"] > 0:
                print(f"    {r['name']:30s} {r['n_trades']:4d} {r['win_rate']:4.0f}% "
                      f"{r['total_pnl_bps']:+8.0f} {r['sharpe']:6.2f} {r['max_dd_bps']:7.0f} "
                      f"{r['avg_hold_days']:6.1f}d")

        # ─── Show OOS results for top 5 train strategies ───────────────────
        print(f"\n    Out-of-sample (test) results for top 5 train strategies:")
        print(f"    {'Strategy':30s} {'N':>4s} {'WR':>5s} {'PnL_bps':>9s} {'Sharpe':>7s} {'MaxDD':>8s} {'AvgHold':>8s}")
        print("    " + "-" * 75)
        for train_r in train_results[:5]:
            # Find matching test result
            test_r = next((t for t in test_results if t["name"] == train_r["name"]), None)
            if test_r and test_r["n_trades"] > 0:
                print(f"    {test_r['name']:30s} {test_r['n_trades']:4d} {test_r['win_rate']:4.0f}% "
                      f"{test_r['total_pnl_bps']:+8.0f} {test_r['sharpe']:6.2f} {test_r['max_dd_bps']:7.0f} "
                      f"{test_r['avg_hold_days']:6.1f}d")
            else:
                print(f"    {train_r['name']:30s}  no trades in OOS")

        # ─── Best OOS strategy ─────────────────────────────────────────────
        test_results.sort(key=lambda x: x["sharpe"], reverse=True)
        best_oos = None
        for r in test_results:
            if r["n_trades"] >= 3:
                best_oos = r
                break

        if best_oos:
            print(f"\n    Best OOS: {best_oos['name']} — Sharpe={best_oos['sharpe']:.2f}, "
                  f"WR={best_oos['win_rate']:.0f}%, PnL={best_oos['total_pnl_bps']:+.0f}bps, "
                  f"N={best_oos['n_trades']}, MaxDD={best_oos['max_dd_bps']:.0f}bps")

        all_results[symbol] = {
            "n_candles": len(candles),
            "buy_hold_return_pct": bh_return_pct,
            "buy_hold_annual_pct": bh_annual,
            "buy_hold_sharpe": bh_sharpe,
            "train_days": len(train),
            "test_days": len(test),
            "train_results": train_results[:10],
            "test_results": test_results[:10],
            "best_oos": best_oos,
        }

    # Save
    with open(output_file, "w") as f:
        json.dump(all_results, f, indent=2, default=str)

    # ─── Summary ──────────────────────────────────────────────────────────────
    print(f"\n{'='*80}")
    print(f"SUMMARY\n")

    for symbol, data in all_results.items():
        print(f"  {symbol}:")
        print(f"    Buy & Hold: {data['buy_hold_return_pct']:+.1f}% ({data['buy_hold_annual_pct']:+.1f}% annual), "
              f"Sharpe={data['buy_hold_sharpe']:.2f}")
        if data.get("best_oos"):
            b = data["best_oos"]
            print(f"    Best OOS strategy: {b['name']}")
            print(f"      Sharpe={b['sharpe']:.2f}, WR={b['win_rate']:.0f}%, "
                  f"PnL={b['total_pnl_bps']:+.0f}bps, N={b['n_trades']}, MaxDD={b['max_dd_bps']:.0f}bps")
        else:
            print(f"    No valid OOS strategy found")

    print(f"\n  PROFITABILITY ANALYSIS:")
    print(f"  - Trend following captures momentum when it exists")
    print(f"  - BTC momentum is well-documented in academic literature")
    print(f"  - BUT: crypto momentum is volatile — large drawdowns during choppy markets")
    print(f"  - Fees: 10 bps/side × 2 = 20 bps per round trip (spot)")
    print(f"  - Key risk: whipsaw in ranging markets (many small losses)")
    print(f"  - Buy & hold is the benchmark — strategy must beat it risk-adjusted")


def main():
    parser = argparse.ArgumentParser(description="D14 BTC Trend Following Scan")
    parser.add_argument("--output", type=str, default="trend_follow_samples.json")
    parser.add_argument("--symbols", type=str, nargs="+", default=["BTCUSDT", "ETHUSDT", "SOLUSDT"])
    parser.add_argument("--limit", type=int, default=1000, help="Number of daily candles")
    args = parser.parse_args()

    output_path = os.path.join(os.path.dirname(__file__), args.output)
    run_scan(output_path, args.symbols, args.limit)


if __name__ == "__main__":
    main()
