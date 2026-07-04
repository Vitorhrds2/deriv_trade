#!/usr/bin/env python3
"""
D12: Statistical Arbitrage Scan (Crypto Pairs Trading).

Hypothesis: If two crypto assets are cointegrated (their spread mean-reverts),
a pairs trading strategy can profit from temporary divergences.

D12a — Fetch historical price data from Binance (free, no API key)
D12b — Test cointegration across all pairs (Engle-Granger / ADF)
D12c — Backtest mean-reversion strategy on cointegrated pairs
D12d — Calculate Sharpe, win rate, max drawdown after fees

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

BINANCE_API = "https://api.binance.com/api/v3"
UA = {"User-Agent": "stat-arb-scan/1.0 (research; read-only)"}

# Default universe: top liquid USDT pairs
DEFAULT_SYMBOLS = [
    "BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "XRPUSDT",
    "ADAUSDT", "AVAXUSDT", "DOGEUSDT", "LINKUSDT", "DOTUSDT",
    "MATICUSDT", "LTCUSDT", "ATOMUSDT", "NEARUSDT", "APTUSDT",
    "ARBUSDT", "OPUSDT", "INJUSDT", "SUIUSDT", "TIAUSDT",
]


def binance_get(endpoint: str, params: dict = None, timeout: int = 15) -> dict:
    url = f"{BINANCE_API}/{endpoint}"
    if params:
        query = "&".join(f"{k}={v}" for k, v in params.items())
        url += f"?{query}"
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


def fetch_klines(symbol: str, interval: str = "1d", limit: int = 500) -> list:
    """Fetch OHLCV candles from Binance."""
    result = binance_get("klines", {
        "symbol": symbol,
        "interval": interval,
        "limit": limit,
    })
    # Each candle: [openTime, open, high, low, close, volume, closeTime, ...]
    return [(c[0], float(c[4])) for c in result]  # (timestamp, close)


def fetch_all_prices(symbols: list, interval: str, limit: int) -> dict:
    """Fetch price history for all symbols."""
    prices = {}
    for i, sym in enumerate(symbols):
        try:
            klines = fetch_klines(sym, interval, limit)
            prices[sym] = klines
            if (i + 1) % 5 == 0:
                print(f"    Fetched {i+1}/{len(symbols)} symbols")
            time.sleep(0.1)  # rate limit
        except Exception as e:
            print(f"    Error fetching {sym}: {e}")
    return prices


# ─── Statistical tests (no scipy dependency) ─────────────────────────────────

def mean(x):
    return sum(x) / len(x) if x else 0


def variance(x):
    m = mean(x)
    return sum((xi - m) ** 2 for xi in x) / (len(x) - 1) if len(x) > 1 else 0


def std(x):
    return math.sqrt(variance(x))


def correlation(x, y):
    if len(x) != len(y) or len(x) < 2:
        return 0
    mx, my = mean(x), mean(y)
    cov = sum((xi - mx) * (yi - my) for xi, yi in zip(x, y)) / (len(x) - 1)
    sx, sy = std(x), std(y)
    if sx == 0 or sy == 0:
        return 0
    return cov / (sx * sy)


def ols_regression(y, x):
    """OLS regression: y = alpha + beta * x + residuals."""
    n = len(y)
    mx, my = mean(x), mean(y)
    cov_xy = sum((xi - mx) * (yi - my) for xi, yi in zip(x, y))
    var_x = sum((xi - mx) ** 2 for xi in x)
    if var_x == 0:
        return 0, my, [0] * n
    beta = cov_xy / var_x
    alpha = my - beta * mx
    residuals = [yi - (alpha + beta * xi) for xi, yi in zip(x, y)]
    return beta, alpha, residuals


def adf_test(residuals: list) -> dict:
    """Augmented Dickey-Fuller test (simplified, no lag terms).
    Tests H0: series has unit root (not stationary)
    vs H1: series is stationary (mean-reverting)
    """
    n = len(residuals)
    if n < 10:
        return {"adf_stat": 0, "p_value": 1.0, "is_stationary": False}

    # First differences
    dy = [residuals[i] - residuals[i-1] for i in range(1, n)]
    y_lag1 = residuals[:-1]

    # Regression: dy = rho * y_lag1 + epsilon
    beta, alpha, eps = ols_regression(dy, y_lag1)

    # ADF statistic = beta / SE(beta)
    se_beta = math.sqrt(variance(eps) / sum((yi - mean(y_lag1)) ** 2 for yi in y_lag1))
    if se_beta == 0:
        return {"adf_stat": 0, "p_value": 1.0, "is_stationary": False}

    adf_stat = beta / se_beta

    # Critical values for ADF (no constant, n=100+)
    # 1%: -2.58, 5%: -1.95, 10%: -1.62
    if adf_stat < -2.58:
        p_value = 0.01
    elif adf_stat < -1.95:
        p_value = 0.05
    elif adf_stat < -1.62:
        p_value = 0.10
    else:
        p_value = 0.5

    return {
        "adf_stat": adf_stat,
        "p_value": p_value,
        "is_stationary": adf_stat < -2.58,
    }


def half_life(residuals: list) -> float:
    """Estimate Ornstein-Uhlenbeck half-life of mean reversion."""
    n = len(residuals)
    if n < 10:
        return float("inf")

    dy = [residuals[i] - residuals[i-1] for i in range(1, n)]
    y_lag1 = residuals[:-1]

    beta, alpha, eps = ols_regression(dy, y_lag1)

    if beta >= 0:
        return float("inf")  # not mean-reverting

    hl = -math.log(2) / beta
    return hl


def zscore(series: list, window: int = 20) -> list:
    """Rolling z-score."""
    result = []
    for i in range(len(series)):
        if i < window:
            result.append(0)
            continue
        window_data = series[i-window:i]
        m = mean(window_data)
        s = std(window_data)
        if s == 0:
            result.append(0)
        else:
            result.append((series[i] - m) / s)
    return result


# ─── Backtest ────────────────────────────────────────────────────────────────

def backtest_pairs_trading(
    prices_a: list, prices_b: list, beta: float, alpha: float,
    entry_z: float = 2.0, exit_z: float = 0.5, stop_z: float = 4.0,
    window: int = 20, fee_bps: float = 10,
) -> dict:
    """Backtest a pairs trading strategy.

    Entry: when z-score of spread > entry_z, short A / long B
           when z-score < -entry_z, long A / short B
    Exit: when |z-score| < exit_z
    Stop: when |z-score| > stop_z

    PnL is calculated in basis points of notional ($1 on each side).
    """
    # Calculate spread
    spread = [a - (alpha + beta * b) for a, b in zip(prices_a, prices_b)]
    z_scores = zscore(spread, window)

    trades = []
    position = 0  # 0=flat, 1=long spread, -1=short spread
    entry_idx = 0

    for i in range(window, len(spread)):
        z = z_scores[i]

        if position == 0:
            if z > entry_z:
                position = -1  # short spread (short $1 A, long $beta B)
                entry_idx = i
            elif z < -entry_z:
                position = 1  # long spread (long $1 A, short $beta B)
                entry_idx = i
        elif position == 1:
            if z > -exit_z or z < -stop_z:
                # Exit: PnL = (delta_A_price - beta * delta_B_price) / total_notional * 10000
                delta_a_price = prices_a[i] - prices_a[entry_idx]
                delta_b_price = prices_b[i] - prices_b[entry_idx]
                total_notional = prices_a[entry_idx] + abs(beta) * prices_b[entry_idx]
                pnl_bps = (delta_a_price - beta * delta_b_price) / total_notional * 10000
                fees = fee_bps * 4
                net_pnl = pnl_bps - fees
                trades.append({
                    "entry_idx": entry_idx,
                    "exit_idx": i,
                    "direction": "long_spread",
                    "pnl_bps": net_pnl,
                    "z_at_entry": z_scores[entry_idx],
                    "z_at_exit": z,
                    "days_held": i - entry_idx,
                })
                position = 0
        elif position == -1:
            if z < exit_z or z > stop_z:
                # Exit: PnL = (-delta_A_price + beta * delta_B_price) / total_notional * 10000
                delta_a_price = prices_a[i] - prices_a[entry_idx]
                delta_b_price = prices_b[i] - prices_b[entry_idx]
                total_notional = prices_a[entry_idx] + abs(beta) * prices_b[entry_idx]
                pnl_bps = (-delta_a_price + beta * delta_b_price) / total_notional * 10000
                fees = fee_bps * 4
                net_pnl = pnl_bps - fees
                trades.append({
                    "entry_idx": entry_idx,
                    "exit_idx": i,
                    "direction": "short_spread",
                    "pnl_bps": net_pnl,
                    "z_at_entry": z_scores[entry_idx],
                    "z_at_exit": z,
                    "days_held": i - entry_idx,
                })
                position = 0

    # Close any open position at end
    if position != 0 and len(spread) > 0:
        delta_a_price = prices_a[-1] - prices_a[entry_idx]
        delta_b_price = prices_b[-1] - prices_b[entry_idx]
        total_notional = prices_a[entry_idx] + abs(beta) * prices_b[entry_idx]
        if position == 1:
            pnl_bps = (delta_a_price - beta * delta_b_price) / total_notional * 10000
        else:
            pnl_bps = (-delta_a_price + beta * delta_b_price) / total_notional * 10000
        fees = fee_bps * 4
        net_pnl = pnl_bps - fees
        trades.append({
            "entry_idx": entry_idx,
            "exit_idx": len(spread) - 1,
            "direction": "long_spread" if position == 1 else "short_spread",
            "pnl_bps": net_pnl,
            "z_at_entry": z_scores[entry_idx],
            "z_at_exit": z_scores[-1],
            "days_held": len(spread) - 1 - entry_idx,
        })

    if not trades:
        return {"n_trades": 0, "total_pnl_bps": 0, "win_rate": 0, "sharpe": 0, "max_dd_bps": 0, "trades": []}

    pnls = [t["pnl_bps"] for t in trades]
    total_pnl = sum(pnls)
    wins = sum(1 for p in pnls if p > 0)
    win_rate = wins / len(pnls) * 100

    # Sharpe (per-trade, annualized assuming ~252 trading days and avg hold ~8 days → ~31 trades/year)
    avg_pnl = mean(pnls)
    std_pnl = std(pnls)
    trades_per_year = 252 / max(1, mean([t["days_held"] for t in trades]))
    sharpe = (avg_pnl / std_pnl * math.sqrt(trades_per_year)) if std_pnl > 0 else 0

    # Max drawdown (in bps)
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

    return {
        "n_trades": len(trades),
        "total_pnl_bps": total_pnl,
        "win_rate": win_rate,
        "sharpe": sharpe,
        "max_dd_bps": max_dd,
        "avg_pnl_per_trade_bps": avg_pnl,
        "avg_hold_days": mean([t["days_held"] for t in trades]),
        "trades": trades,
    }


def run_scan(output_file: str, symbols: list, interval: str, limit: int):
    print("D12: Statistical Arbitrage Scan (Crypto Pairs Trading)")
    print(f"Symbols: {len(symbols)} ({', '.join(symbols[:5])}...)")
    print(f"Interval: {interval}, Limit: {limit} candles")
    print(f"API: Binance public (no API key)")
    print(f"{'='*80}\n")

    # Fetch price data
    print("  Fetching price data...")
    all_prices = fetch_all_prices(symbols, interval, limit)

    # Align timestamps
    print("  Aligning timestamps...")
    # Find common timestamps
    all_ts = set()
    for sym_data in all_prices.values():
        for ts, _ in sym_data:
            all_ts.add(ts)
    common_ts = sorted(all_ts)

    # Build price matrix
    price_dict = {}
    for sym, data in all_prices.items():
        ts_to_price = {ts: price for ts, price in data}
        prices = []
        for ts in common_ts:
            if ts in ts_to_price:
                prices.append(ts_to_price[ts])
            else:
                if prices:
                    prices.append(prices[-1])  # forward fill
                else:
                    prices.append(0)
        price_dict[sym] = prices

    # Filter symbols with enough data
    valid_symbols = [s for s in symbols if s in price_dict and len(price_dict[s]) >= limit * 0.9]
    print(f"  Valid symbols with sufficient data: {len(valid_symbols)}")

    # D12b: Test all pairs for cointegration
    print(f"\n  Testing {len(valid_symbols) * (len(valid_symbols)-1) // 2} pairs for cointegration...")

    cointegrated_pairs = []
    all_pair_results = []

    for i in range(len(valid_symbols)):
        for j in range(i + 1, len(valid_symbols)):
            sym_a = valid_symbols[i]
            sym_b = valid_symbols[j]
            prices_a = price_dict[sym_a]
            prices_b = price_dict[sym_b]

            # Correlation filter (skip low correlation)
            corr = correlation(prices_a, prices_b)
            if abs(corr) < 0.5:
                continue

            # OLS regression
            beta, alpha, residuals = ols_regression(prices_a, prices_b)

            # ADF test on residuals
            adf = adf_test(residuals)

            # Half-life
            hl = half_life(residuals)

            result = {
                "sym_a": sym_a,
                "sym_b": sym_b,
                "correlation": corr,
                "beta": beta,
                "alpha": alpha,
                "adf_stat": adf["adf_stat"],
                "p_value": adf["p_value"],
                "is_stationary": adf["is_stationary"],
                "half_life": hl,
            }

            all_pair_results.append(result)

            if adf["is_stationary"] and hl < 50 and hl > 0 and abs(corr) > 0.6:
                cointegrated_pairs.append(result)
                print(f"    ✓ {sym_a} / {sym_b}: corr={corr:.3f} ADF={adf['adf_stat']:.2f} "
                      f"HL={hl:.1f}d β={beta:.3f}")

    print(f"\n  Cointegrated pairs found: {len(cointegrated_pairs)} / {len(all_pair_results)} tested")

    # D12c: Backtest top cointegrated pairs
    print(f"\n  Backtesting top pairs...")

    # Sort by ADF stat (most negative = most stationary)
    cointegrated_pairs.sort(key=lambda x: x["adf_stat"])

    backtest_results = []
    for pair in cointegrated_pairs[:10]:  # top 10
        sym_a, sym_b = pair["sym_a"], pair["sym_b"]
        prices_a = price_dict[sym_a]
        prices_b = price_dict[sym_b]

        # Walk-forward: use first 70% for training, last 30% for testing
        n = min(len(prices_a), len(prices_b))
        split = int(n * 0.7)

        # Recalculate beta/alpha on training set
        train_a = prices_a[:split]
        train_b = prices_b[:split]
        beta, alpha, residuals = ols_regression(train_a, train_b)

        # Test on out-of-sample
        test_a = prices_a[split:]
        test_b = prices_b[split:]

        if len(test_a) < 30:
            continue

        bt = backtest_pairs_trading(test_a, test_b, beta, alpha,
                                     entry_z=2.0, exit_z=0.5, stop_z=4.0,
                                     window=20, fee_bps=10)

        bt_result = {
            **pair,
            "backtest": bt,
            "train_period": split,
            "test_period": len(test_a),
        }
        backtest_results.append(bt_result)

        if bt["n_trades"] > 0:
            print(f"    {sym_a}/{sym_b}: {bt['n_trades']} trades, "
                  f"WR={bt['win_rate']:.0f}%, PnL={bt['total_pnl_bps']:+.0f}bps, "
                  f"Sharpe={bt['sharpe']:.2f}, MaxDD={bt['max_dd_bps']:.0f}bps")

    # Save
    output = {
        "scan_time": datetime.now(timezone.utc).isoformat(),
        "symbols": valid_symbols,
        "interval": interval,
        "limit": limit,
        "all_pair_results": all_pair_results,
        "cointegrated_pairs": cointegrated_pairs,
        "backtest_results": backtest_results,
    }
    with open(output_file, "w") as f:
        json.dump(output, f, indent=2, default=str)

    # ─── Summary ──────────────────────────────────────────────────────────────
    print(f"\n{'='*80}")
    print(f"SUMMARY\n")

    print(f"  Symbols analyzed: {len(valid_symbols)}")
    print(f"  Pairs tested: {len(all_pair_results)}")
    print(f"  Cointegrated pairs (p<0.01): {len(cointegrated_pairs)}")

    if cointegrated_pairs:
        print(f"\n  Top cointegrated pairs:")
        for p in cointegrated_pairs[:10]:
            print(f"    {p['sym_a']:10s} / {p['sym_b']:10s}  "
                  f"corr={p['correlation']:.3f}  ADF={p['adf_stat']:.2f}  "
                  f"HL={p['half_life']:.1f}d  β={p['beta']:.3f}")

    if backtest_results:
        print(f"\n  Backtest results (out-of-sample, after 40bps fees per round trip):")
        print(f"  {'Pair':25s} {'Trades':>7s} {'WR':>5s} {'PnL_bps':>9s} {'Sharpe':>7s} {'MaxDD_bps':>10s} {'AvgHold':>8s}")
        print("-" * 80)
        for bt in backtest_results:
            b = bt["backtest"]
            if b["n_trades"] > 0:
                pair_name = f"{bt['sym_a']}/{bt['sym_b']}"
                print(f"  {pair_name:25s} {b['n_trades']:7d} {b['win_rate']:4.0f}% "
                      f"{b['total_pnl_bps']:+8.0f} {b['sharpe']:6.2f} {b['max_dd_bps']:9.0f} "
                      f"{b['avg_hold_days']:6.1f}d")
            else:
                print(f"  {bt['sym_a']}/{bt['sym_b']:10s}  no trades")

        # Overall stats
        all_trades_bt = [bt for bt in backtest_results if bt["backtest"]["n_trades"] > 0]
        if all_trades_bt:
            total_pnl = sum(bt["backtest"]["total_pnl_bps"] for bt in all_trades_bt)
            avg_sharpe = mean([bt["backtest"]["sharpe"] for bt in all_trades_bt])
            avg_wr = mean([bt["backtest"]["win_rate"] for bt in all_trades_bt])
            print(f"\n  Overall: avg PnL={total_pnl/len(all_trades_bt):+.0f}bps, "
                  f"avg Sharpe={avg_sharpe:.2f}, avg WR={avg_wr:.0f}%")

    print(f"\n  PROFITABILITY ANALYSIS:")
    print(f"  - Cointegration is necessary but not sufficient for profitability")
    print(f"  - Fees: 10 bps/side × 4 trades per round trip = 40 bps")
    print(f"  - Slippage: ~5-10 bps per trade on majors, more on alts")
    print(f"  - Total cost per round trip: ~50-60 bps")
    print(f"  - Strategy needs spread divergence > 60 bps to profit")
    print(f"  - Risk: cointegration can break (structural change in relationship)")
    print(f"  - Example: LUNA/UST appeared cointegrated before May 2022 collapse")


def main():
    parser = argparse.ArgumentParser(description="D12 Statistical Arbitrage Scan")
    parser.add_argument("--output", type=str, default="stat_arb_samples.json")
    parser.add_argument("--symbols", type=str, nargs="+", default=DEFAULT_SYMBOLS)
    parser.add_argument("--interval", type=str, default="1d", help="1d, 4h, 1h, etc.")
    parser.add_argument("--limit", type=int, default=500, help="Number of candles")
    args = parser.parse_args()

    output_path = os.path.join(os.path.dirname(__file__), args.output)
    run_scan(output_path, args.symbols, args.interval, args.limit)


if __name__ == "__main__":
    main()
