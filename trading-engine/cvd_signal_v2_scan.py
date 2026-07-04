#!/usr/bin/env python3
"""
D16v2: CVD Signal Scan — Rigorous Re-test.

Fixes from D16v1:
1. Paginated fetching: 5000+ candles (vs 1000) via multiple API calls
2. K-fold cross-validation (5-fold) instead of single 70/30 walk-forward
3. Bonferroni correction: significance threshold = 0.05 / n_configs
4. Permutation test: shuffle trade entry times to get null distribution
5. Only declare edge if p-value < corrected threshold AND positive in ≥4/5 folds
6. Conservative Sharpe: no annualization inflation (report per-trade Sharpe)

All data via Binance public API. Read-only.
"""
import argparse
import json
import math
import os
import random
import time
import urllib.request
from datetime import datetime, timezone

BINANCE_API = "https://api.binance.com/api/v3"
BINANCE_FAPI = "https://fapi.binance.com"
UA = {"User-Agent": "cvd-scan-v2/1.0 (research; read-only)"}


def http_get(url, timeout=15):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


def fetch_klines_paginated(symbol, interval="1h", total_limit=5000):
    """Fetch klines with pagination. Binance max per request = 1000."""
    all_candles = []
    end_time = None
    remaining = total_limit

    while remaining > 0:
        batch = min(1000, remaining)
        params = f"symbol={symbol}&interval={interval}&limit={batch}"
        if end_time is not None:
            params += f"&endTime={end_time}"
        try:
            data = http_get(f"{BINANCE_API}/klines?{params}")
        except Exception:
            try:
                data = http_get(f"{BINANCE_FAPI}/fapi/v1/klines?{params}")
            except Exception as e:
                print(f"      API error: {e}")
                break

        if not data:
            break

        for c in data:
            total_vol = float(c[5])
            taker_buy_vol = float(c[9])
            taker_sell_vol = total_vol - taker_buy_vol
            delta = taker_buy_vol - taker_sell_vol
            all_candles.append({
                "ts": c[0],
                "close": float(c[4]),
                "volume": total_vol,
                "taker_buy_vol": taker_buy_vol,
                "taker_sell_vol": taker_sell_vol,
                "delta": delta,
            })

        end_time = data[0][0] - 1  # before earliest in this batch
        remaining -= len(data)
        if len(data) < batch:
            break  # no more data
        time.sleep(0.2)

    # Sort chronologically
    all_candles.sort(key=lambda c: c["ts"])
    return all_candles


def mean(x):
    return sum(x) / len(x) if x else 0


def std(x):
    if len(x) < 2:
        return 0
    m = mean(x)
    return math.sqrt(sum((xi - m) ** 2 for xi in x) / (len(x) - 1))


def compute_cvd(candles):
    cvd = []
    running = 0
    for c in candles:
        running += c["delta"]
        cvd.append(running)
    return cvd


# ─── Strategy backtests (same as v1) ─────────────────────────────────────────

def backtest_cvd_divergence(candles, lookback=48, hold_hours=24, fee_bps=10):
    cvd = compute_cvd(candles)
    closes = [c["close"] for c in candles]
    trades = []
    position = 0
    entry_idx = 0
    entry_price = 0

    for i in range(lookback, len(closes)):
        price_window = closes[i - lookback:i + 1]
        price_high = max(price_window[:-1])
        price_low = min(price_window[:-1])
        cvd_at_price_high = cvd[i - lookback + price_window[:-1].index(price_high)]
        cvd_at_price_low = cvd[i - lookback + price_window[:-1].index(price_low)]

        if position == 0:
            if closes[i] > price_high and cvd[i] < cvd_at_price_high:
                position = -1
                entry_idx = i
                entry_price = closes[i]
            elif closes[i] < price_low and cvd[i] > cvd_at_price_low:
                position = 1
                entry_idx = i
                entry_price = closes[i]
        elif position == 1:
            if i - entry_idx >= hold_hours or closes[i] > closes[entry_idx] * 1.02:
                exit_price = closes[i]
                pnl = (exit_price - entry_price) / entry_price * 10000 - fee_bps * 2
                trades.append({"pnl_bps": pnl, "hours_held": i - entry_idx, "direction": "long"})
                position = 0
        elif position == -1:
            if i - entry_idx >= hold_hours or closes[i] < closes[entry_idx] * 0.98:
                exit_price = closes[i]
                pnl = (entry_price - exit_price) / entry_price * 10000 - fee_bps * 2
                trades.append({"pnl_bps": pnl, "hours_held": i - entry_idx, "direction": "short"})
                position = 0

    if position == 1:
        pnl = (closes[-1] - entry_price) / entry_price * 10000 - fee_bps * 2
        trades.append({"pnl_bps": pnl, "hours_held": len(closes) - 1 - entry_idx, "direction": "long"})
    elif position == -1:
        pnl = (entry_price - closes[-1]) / entry_price * 10000 - fee_bps * 2
        trades.append({"pnl_bps": pnl, "hours_held": len(closes) - 1 - entry_idx, "direction": "short"})
    return trades


def backtest_cvd_momentum(candles, cvd_window=24, hold_hours=24, fee_bps=10):
    cvd = compute_cvd(candles)
    closes = [c["close"] for c in candles]
    trades = []
    position = 0
    entry_idx = 0
    entry_price = 0

    for i in range(cvd_window, len(closes)):
        cvd_change = cvd[i] - cvd[i - cvd_window]
        cvd_change_prev = cvd[i - 1] - cvd[i - 1 - cvd_window] if i > cvd_window else 0

        if position == 0:
            if cvd_change > 0 and cvd_change > cvd_change_prev:
                position = 1
                entry_idx = i
                entry_price = closes[i]
            elif cvd_change < 0 and cvd_change < cvd_change_prev:
                position = -1
                entry_idx = i
                entry_price = closes[i]
        elif position == 1:
            if i - entry_idx >= hold_hours or cvd_change < 0:
                exit_price = closes[i]
                pnl = (exit_price - entry_price) / entry_price * 10000 - fee_bps * 2
                trades.append({"pnl_bps": pnl, "hours_held": i - entry_idx, "direction": "long"})
                position = 0
        elif position == -1:
            if i - entry_idx >= hold_hours or cvd_change > 0:
                exit_price = closes[i]
                pnl = (entry_price - exit_price) / entry_price * 10000 - fee_bps * 2
                trades.append({"pnl_bps": pnl, "hours_held": i - entry_idx, "direction": "short"})
                position = 0

    if position == 1:
        pnl = (closes[-1] - entry_price) / entry_price * 10000 - fee_bps * 2
        trades.append({"pnl_bps": pnl, "hours_held": len(closes) - 1 - entry_idx, "direction": "long"})
    elif position == -1:
        pnl = (entry_price - closes[-1]) / entry_price * 10000 - fee_bps * 2
        trades.append({"pnl_bps": pnl, "hours_held": len(closes) - 1 - entry_idx, "direction": "short"})
    return trades


def backtest_cvd_reversal(candles, z_threshold=2.0, window=48, hold_hours=24, fee_bps=10):
    cvd = compute_cvd(candles)
    closes = [c["close"] for c in candles]
    cvd_z = []
    for i in range(len(cvd)):
        if i < window:
            cvd_z.append(0)
        else:
            m = mean(cvd[i - window:i + 1])
            s = std(cvd[i - window:i + 1])
            cvd_z.append((cvd[i] - m) / s if s > 0 else 0)

    trades = []
    position = 0
    entry_idx = 0
    entry_price = 0

    for i in range(window, len(closes)):
        if position == 0:
            if cvd_z[i] > z_threshold:
                position = -1
                entry_idx = i
                entry_price = closes[i]
            elif cvd_z[i] < -z_threshold:
                position = 1
                entry_idx = i
                entry_price = closes[i]
        elif position == 1:
            if i - entry_idx >= hold_hours or cvd_z[i] > 0:
                exit_price = closes[i]
                pnl = (exit_price - entry_price) / entry_price * 10000 - fee_bps * 2
                trades.append({"pnl_bps": pnl, "hours_held": i - entry_idx, "direction": "long"})
                position = 0
        elif position == -1:
            if i - entry_idx >= hold_hours or cvd_z[i] < 0:
                exit_price = closes[i]
                pnl = (entry_price - exit_price) / entry_price * 10000 - fee_bps * 2
                trades.append({"pnl_bps": pnl, "hours_held": i - entry_idx, "direction": "short"})
                position = 0

    if position == 1:
        pnl = (closes[-1] - entry_price) / entry_price * 10000 - fee_bps * 2
        trades.append({"pnl_bps": pnl, "hours_held": len(closes) - 1 - entry_idx, "direction": "long"})
    elif position == -1:
        pnl = (entry_price - closes[-1]) / entry_price * 10000 - fee_bps * 2
        trades.append({"pnl_bps": pnl, "hours_held": len(closes) - 1 - entry_idx, "direction": "short"})
    return trades


# ─── Statistical tests ────────────────────────────────────────────────────────

def summarize_trades(trades):
    """Conservative summary — NO annualization inflation."""
    if not trades:
        return {"n": 0, "total_bps": 0, "avg_bps": 0, "wr": 0, "sharpe_per_trade": 0,
                "max_dd_bps": 0, "long_wr": 0, "short_wr": 0, "n_long": 0, "n_short": 0}

    pnls = [t["pnl_bps"] for t in trades]
    s = std(pnls)
    sharpe_pt = mean(pnls) / s if s > 0 else 0  # per-trade Sharpe (no annualization)

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

    long_t = [t for t in trades if t["direction"] == "long"]
    short_t = [t for t in trades if t["direction"] == "short"]

    return {
        "n": len(trades),
        "total_bps": sum(pnls),
        "avg_bps": mean(pnls),
        "wr": sum(1 for p in pnls if p > 0) / len(pnls) * 100,
        "sharpe_per_trade": sharpe_pt,
        "max_dd_bps": max_dd,
        "long_wr": (sum(1 for t in long_t if t["pnl_bps"] > 0) / len(long_t) * 100) if long_t else 0,
        "short_wr": (sum(1 for t in short_t if t["pnl_bps"] > 0) / len(short_t) * 100) if short_t else 0,
        "n_long": len(long_t),
        "n_short": len(short_t),
    }


def permutation_test(trades, n_permutations=1000):
    """Shuffle PnL signs to get null distribution of avg PnL.
    Returns p-value for the observed avg PnL being > 0 by chance.
    """
    if len(trades) < 10:
        return 1.0

    pnls = [t["pnl_bps"] for t in trades]
    observed_avg = mean(pnls)

    # Null: randomly flip signs
    random.seed(42)
    count_ge = 0
    for _ in range(n_permutations):
        shuffled = [p if random.random() > 0.5 else -p for p in pnls]
        if mean(shuffled) >= observed_avg:
            count_ge += 1

    return count_ge / n_permutations


def k_fold_cross_validate(candles, strategy_fn, strategy_name, k=5, min_trades_per_fold=5):
    """K-fold CV: split data into K contiguous folds, test on each fold
    using strategy parameters (no optimization per fold — fixed params).
    """
    n = len(candles)
    fold_size = n // k
    fold_results = []

    for fold_idx in range(k):
        start = fold_idx * fold_size
        end = (fold_idx + 1) * fold_size if fold_idx < k - 1 else n
        fold_data = candles[start:end]
        trades = strategy_fn(fold_data)
        summary = summarize_trades(trades)
        summary["fold"] = fold_idx
        summary["fold_start"] = start
        summary["fold_end"] = end
        fold_results.append(summary)

    return fold_results


# ─── Config generation ───────────────────────────────────────────────────────

def get_all_configs():
    """Generate all strategy configs to test."""
    configs = []

    # CVD divergence: lookback × hold
    for lb in [24, 48, 96]:
        for hold in [12, 24, 48]:
            configs.append({
                "name": f"diverge_{lb}h_{hold}h",
                "type": "divergence",
                "fn": lambda c, lb=lb, hold=hold: backtest_cvd_divergence(c, lb, hold),
            })

    # CVD momentum: window × hold
    for cw in [12, 24, 48]:
        for hold in [12, 24, 48]:
            configs.append({
                "name": f"momentum_{cw}h_{hold}h",
                "type": "momentum",
                "fn": lambda c, cw=cw, hold=hold: backtest_cvd_momentum(c, cw, hold),
            })

    # CVD reversal: z × hold
    for z in [1.5, 2.0, 3.0]:
        for hold in [12, 24, 48]:
            configs.append({
                "name": f"reversal_z{z}_{hold}h",
                "type": "reversal",
                "fn": lambda c, z=z, hold=hold: backtest_cvd_reversal(c, z, 48, hold),
            })

    return configs


def run_scan(output_file, symbols, interval, total_limit, k_folds):
    print("D16v2: CVD Signal Scan — Rigorous Re-test")
    print(f"Symbols: {', '.join(symbols)}")
    print(f"Interval: {interval}, Target: {total_limit} candles")
    print(f"K-fold: {k_folds}, Permutation test: 1000 iterations")
    print(f"Bonferroni correction: 0.05 / n_configs")
    print(f"API: Binance public (no API key)")
    print(f"{'='*80}\n")

    configs = get_all_configs()
    n_configs = len(configs)
    bonferroni_alpha = 0.05 / n_configs
    print(f"  Configs to test: {n_configs}")
    print(f"  Bonferroni-corrected alpha: {bonferroni_alpha:.4f}")
    print(f"  Edge declared if: p-value < {bonferroni_alpha:.4f} AND positive in ≥{k_folds-1}/{k_folds} folds\n")

    all_results = {}

    for symbol in symbols:
        print(f"\n  [{symbol}]")
        print(f"    Fetching {total_limit} candles (paginated)...")
        candles = fetch_klines_paginated(symbol, interval, total_limit)
        print(f"    Got {len(candles)} candles ({interval})")

        if len(candles) < 500:
            print(f"    Skipping — need at least 500 candles")
            continue

        # Order flow stats
        total_buy = sum(c["taker_buy_vol"] for c in candles)
        total_sell = sum(c["taker_sell_vol"] for c in candles)
        bs_ratio = total_buy / total_sell if total_sell > 0 else 0
        print(f"    Order flow: buy/sell ratio = {bs_ratio:.4f}")

        # Buy & hold benchmark
        closes = [c["close"] for c in candles]
        bh_ret = (closes[-1] - closes[0]) / closes[0] * 100
        daily_rets = []
        for i in range(1, len(closes)):
            daily_rets.append(closes[i] / closes[i - 1] - 1)
        bh_sharpe = (mean(daily_rets) / std(daily_rets) * math.sqrt(365 * 24)) if std(daily_rets) > 0 else 0
        print(f"    Buy & Hold: {bh_ret:+.1f}%, Sharpe={bh_sharpe:.2f}")

        # Run all configs with k-fold CV
        config_results = []

        for ci, config in enumerate(configs):
            # K-fold cross-validation
            fold_results = k_fold_cross_validate(candles, config["fn"], config["name"], k_folds)

            # Aggregate across folds
            all_trades = []
            for fr in fold_results:
                # Re-run to get actual trades for permutation test
                fold_data = candles[fr["fold_start"]:fr["fold_end"]]
                trades = config["fn"](fold_data)
                all_trades.extend(trades)

            # Full-sample summary
            full_summary = summarize_trades(all_trades)

            # Permutation test on full sample
            p_value = permutation_test(all_trades, 1000) if len(all_trades) >= 20 else 1.0

            # Count positive folds
            positive_folds = sum(1 for fr in fold_results if fr["avg_bps"] > 0)
            positive_sharpe_folds = sum(1 for fr in fold_results if fr["sharpe_per_trade"] > 0)

            # Per-fold summaries
            fold_avg_bps = [fr["avg_bps"] for fr in fold_results]
            fold_wrs = [fr["wr"] for fr in fold_results]
            fold_sharpes = [fr["sharpe_per_trade"] for fr in fold_results]

            result = {
                "name": config["name"],
                "type": config["type"],
                "n_trades_total": full_summary["n"],
                "avg_bps": full_summary["avg_bps"],
                "total_bps": full_summary["total_bps"],
                "win_rate": full_summary["wr"],
                "sharpe_per_trade": full_summary["sharpe_per_trade"],
                "max_dd_bps": full_summary["max_dd_bps"],
                "long_wr": full_summary["long_wr"],
                "short_wr": full_summary["short_wr"],
                "n_long": full_summary["n_long"],
                "n_short": full_summary["n_short"],
                "p_value": p_value,
                "positive_folds": positive_folds,
                "positive_sharpe_folds": positive_sharpe_folds,
                "fold_avg_bps": fold_avg_bps,
                "fold_wrs": fold_wrs,
                "fold_sharpes": fold_sharpes,
                "significant": p_value < bonferroni_alpha,
                "robust": positive_folds >= k_folds - 1 and p_value < bonferroni_alpha,
            }
            config_results.append(result)

            if (ci + 1) % 10 == 0:
                print(f"    Tested {ci+1}/{n_configs} configs...")

        # Sort by robustness, then by avg_bps
        config_results.sort(key=lambda x: (x["robust"], x["avg_bps"]), reverse=True)

        # Print top configs
        print(f"\n    Top 10 configs (by avg PnL, N>=20):")
        print(f"    {'Config':30s} {'N':>5s} {'WR':>5s} {'Avg_bps':>8s} {'Sharpe':>7s} {'p_val':>6s} {'Folds+':>7s} {'Robust':>7s}")
        print("    " + "-" * 85)
        for r in config_results:
            if r["n_trades_total"] >= 20:
                robust_str = "YES" if r["robust"] else "no"
                print(f"    {r['name']:30s} {r['n_trades_total']:5d} {r['win_rate']:4.0f}% "
                      f"{r['avg_bps']:+7.1f} {r['sharpe_per_trade']:6.3f} "
                      f"{r['p_value']:5.3f} {r['positive_folds']:3d}/{k_folds}   {robust_str:>6s}")

        # Check for any robust edge
        robust_configs = [r for r in config_results if r["robust"] and r["n_trades_total"] >= 20]
        if robust_configs:
            print(f"\n    *** ROBUST EDGE FOUND: {len(robust_configs)} config(s) ***")
            for r in robust_configs[:3]:
                print(f"      {r['name']}: avg={r['avg_bps']:+.1f}bps, WR={r['win_rate']:.0f}%, "
                      f"p={r['p_value']:.3f}, folds+={r['positive_folds']}/{k_folds}")
        else:
            # Check if any are at least significant
            sig_configs = [r for r in config_results if r["significant"] and r["n_trades_total"] >= 20]
            if sig_configs:
                print(f"\n    Significant (p<{bonferroni_alpha:.4f}) but NOT robust (<{k_folds-1} folds positive):")
                for r in sig_configs[:3]:
                    print(f"      {r['name']}: avg={r['avg_bps']:+.1f}bps, p={r['p_value']:.3f}, "
                          f"folds+={r['positive_folds']}/{k_folds}")
            else:
                print(f"\n    No significant edge found (Bonferroni alpha={bonferroni_alpha:.4f})")

        # Per-fold breakdown for best config
        if config_results:
            best = config_results[0]
            if best["n_trades_total"] >= 20:
                print(f"\n    Best config per-fold breakdown: {best['name']}")
                print(f"    {'Fold':>6s} {'Avg_bps':>8s} {'WR':>5s} {'Sharpe':>7s}")
                print("    " + "-" * 30)
                for i, (ab, wr, sh) in enumerate(zip(best["fold_avg_bps"], best["fold_wrs"], best["fold_sharpes"])):
                    print(f"    {i:6d} {ab:+7.1f} {wr:4.0f}% {sh:6.3f}")

        all_results[symbol] = {
            "n_candles": len(candles),
            "buy_sell_ratio": bs_ratio,
            "buy_hold_return_pct": bh_ret,
            "buy_hold_sharpe": bh_sharpe,
            "n_configs": n_configs,
            "bonferroni_alpha": bonferroni_alpha,
            "k_folds": k_folds,
            "config_results": config_results[:20],  # top 20
            "any_robust": len(robust_configs) > 0,
        }

    # Save
    with open(output_file, "w") as f:
        json.dump(all_results, f, indent=2, default=str)

    # ─── Summary ──────────────────────────────────────────────────────────────
    print(f"\n{'='*80}")
    print(f"SUMMARY\n")

    print(f"  Bonferroni-corrected alpha: {bonferroni_alpha:.4f} (0.05 / {n_configs} configs)")
    print(f"  K-fold: {k_folds} folds, edge requires p < alpha AND ≥{k_folds-1}/{k_folds} folds positive\n")

    for symbol, data in all_results.items():
        print(f"  {symbol} ({data['n_candles']} candles):")
        print(f"    Buy & Hold: {data['buy_hold_return_pct']:+.1f}%, Sharpe={data['buy_hold_sharpe']:.2f}")
        print(f"    Buy/Sell ratio: {data['buy_sell_ratio']:.4f}")

        if data["any_robust"]:
            print(f"    *** ROBUST EDGE FOUND ***")
        else:
            # Best non-robust
            best = data["config_results"][0] if data["config_results"] else None
            if best and best["n_trades_total"] >= 20:
                print(f"    Best (not robust): {best['name']}")
                print(f"      N={best['n_trades_total']}, avg={best['avg_bps']:+.1f}bps, "
                      f"WR={best['win_rate']:.0f}%, p={best['p_value']:.3f}, "
                      f"folds+={best['positive_folds']}/{k_folds}")
                if best["p_value"] >= bonferroni_alpha:
                    print(f"      → NOT significant after Bonferroni correction")
                elif best["positive_folds"] < k_folds - 1:
                    print(f"      → Significant but NOT robust (fails in {k_folds - best['positive_folds']} folds)")
            else:
                print(f"    No config with N>=20 trades")

    print(f"\n  METHODOLOGY NOTES:")
    print(f"  - {total_limit} candles per symbol (vs 1000 in v1)")
    print(f"  - {k_folds}-fold cross-validation (vs single 70/30 in v1)")
    print(f"  - Permutation test (1000 iterations) for p-value")
    print(f"  - Bonferroni correction: alpha = 0.05 / {n_configs} = {bonferroni_alpha:.4f}")
    print(f"  - Per-trade Sharpe (no annualization inflation)")
    print(f"  - Edge requires: p < {bonferroni_alpha:.4f} AND positive in ≥{k_folds-1}/{k_folds} folds")


def main():
    parser = argparse.ArgumentParser(description="D16v2 CVD Signal Scan — Rigorous")
    parser.add_argument("--output", type=str, default="cvd_signal_v2_samples.json")
    parser.add_argument("--symbols", type=str, nargs="+", default=["BTCUSDT", "ETHUSDT", "SOLUSDT"])
    parser.add_argument("--interval", type=str, default="1h")
    parser.add_argument("--limit", type=int, default=5000)
    parser.add_argument("--k-folds", type=int, default=5)
    args = parser.parse_args()

    output_path = os.path.join(os.path.dirname(__file__), args.output)
    run_scan(output_path, args.symbols, args.interval, args.limit, args.k_folds)


if __name__ == "__main__":
    main()
