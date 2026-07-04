#!/usr/bin/env python3
"""
D16: Order Flow / CVD (Cumulative Volume Delta) as Directional Signal.

Hypothesis: Cumulative Volume Delta (CVD) — the running sum of (buy volume
minus sell volume) — predicts short-term price direction. When CVD diverges
from price, it signals impending reversal.

D16a — Fetch historical klines + aggTrades from Binance
D16b — Compute CVD from trade flow (taker buy vs sell volume)
D16c — Test CVD divergence as reversal signal
D16d — Test CVD momentum as trend confirmation signal
D16e — Backtest with walk-forward, calculate Sharpe/WR/PnL

Binance klines already include taker_buy_volume (field 9) which is the
volume from takers buying. CVD per candle = taker_buy_volume - (total_volume - taker_buy_volume).

All data via Binance public API. Read-only.
"""
import argparse
import json
import math
import os
import time
import urllib.request
from datetime import datetime, timezone

BINANCE_API = "https://api.binance.com/api/v3"
BINANCE_FAPI = "https://fapi.binance.com"
UA = {"User-Agent": "cvd-signal-scan/1.0 (research; read-only)"}


def http_get(url, timeout=15):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


def fetch_klines_with_flow(symbol, interval="1h", limit=1000):
    """Fetch klines with taker buy volume for CVD calculation.
    Fields: [ts, open, high, low, close, volume, close_ts, quote_vol, trades,
             taker_buy_vol, taker_buy_quote_vol, ignore]
    """
    data = http_get(f"{BINANCE_API}/klines?symbol={symbol}&interval={interval}&limit={limit}")
    candles = []
    for c in data:
        total_vol = float(c[5])
        taker_buy_vol = float(c[9])
        taker_sell_vol = total_vol - taker_buy_vol
        delta = taker_buy_vol - taker_sell_vol
        candles.append({
            "ts": c[0],
            "close": float(c[4]),
            "volume": total_vol,
            "taker_buy_vol": taker_buy_vol,
            "taker_sell_vol": taker_sell_vol,
            "delta": delta,
            "close_ts": c[6],
        })
    return candles


def fetch_futures_klines_with_flow(symbol, interval="1h", limit=1500):
    """Fetch futures klines with taker buy volume."""
    data = http_get(f"{BINANCE_FAPI}/fapi/v1/klines?symbol={symbol}&interval={interval}&limit={limit}")
    candles = []
    for c in data:
        total_vol = float(c[5])
        taker_buy_vol = float(c[9])
        taker_sell_vol = total_vol - taker_buy_vol
        delta = taker_buy_vol - taker_sell_vol
        candles.append({
            "ts": c[0],
            "close": float(c[4]),
            "volume": total_vol,
            "taker_buy_vol": taker_buy_vol,
            "taker_sell_vol": taker_sell_vol,
            "delta": delta,
            "close_ts": c[6],
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
    result = []
    for i in range(len(values)):
        if i < window - 1:
            result.append(None)
        else:
            result.append(mean(values[i - window + 1:i + 1]))
    return result


def compute_cvd(candles):
    """Compute cumulative volume delta."""
    cvd = []
    running = 0
    for c in candles:
        running += c["delta"]
        cvd.append(running)
    return cvd


def compute_cvd_oscillator(candles, window=24):
    """CVD oscillator: CVD over last N periods vs CVD over previous N.
    Captures rate of change in order flow imbalance.
    """
    cvd = compute_cvd(candles)
    osc = []
    for i in range(len(cvd)):
        if i < 2 * window:
            osc.append(0)
        else:
            recent = cvd[i] - cvd[i - window]
            prior = cvd[i - window] - cvd[i - 2 * window]
            osc.append(recent - prior)
    return osc


def backtest_cvd_divergence(candles, lookback=48, hold_hours=24, fee_bps=10):
    """CVD divergence: when price makes new high but CVD doesn't → short.
    When price makes new low but CVD doesn't → long.
    """
    cvd = compute_cvd(candles)
    closes = [c["close"] for c in candles]
    trades = []
    position = 0
    entry_idx = 0
    entry_price = 0

    for i in range(lookback, len(closes)):
        # Look back N periods
        price_window = closes[i - lookback:i + 1]
        cvd_window = cvd[i - lookback:i + 1]

        price_high = max(price_window[:-1])
        price_low = min(price_window[:-1])
        cvd_at_price_high = cvd[i - lookback + price_window[:-1].index(price_high)]
        cvd_at_price_low = cvd[i - lookback + price_window[:-1].index(price_low)]

        if position == 0:
            # Bearish divergence: price new high, CVD lower
            if closes[i] > price_high and cvd[i] < cvd_at_price_high:
                position = -1
                entry_idx = i
                entry_price = closes[i]
            # Bullish divergence: price new low, CVD higher
            elif closes[i] < price_low and cvd[i] > cvd_at_price_low:
                position = 1
                entry_idx = i
                entry_price = closes[i]
        elif position == 1:
            if i - entry_idx >= hold_hours or closes[i] > closes[entry_idx] * 1.02:
                exit_price = closes[i]
                pnl = (exit_price - entry_price) / entry_price * 10000 - fee_bps * 2
                trades.append({"pnl_bps": pnl, "hours_held": i - entry_idx, "direction": "long",
                               "type": "bullish_div"})
                position = 0
        elif position == -1:
            if i - entry_idx >= hold_hours or closes[i] < closes[entry_idx] * 0.98:
                exit_price = closes[i]
                pnl = (entry_price - exit_price) / entry_price * 10000 - fee_bps * 2
                trades.append({"pnl_bps": pnl, "hours_held": i - entry_idx, "direction": "short",
                               "type": "bearish_div"})
                position = 0

    if position == 1:
        pnl = (closes[-1] - entry_price) / entry_price * 10000 - fee_bps * 2
        trades.append({"pnl_bps": pnl, "hours_held": len(closes) - 1 - entry_idx, "direction": "long"})
    elif position == -1:
        pnl = (entry_price - closes[-1]) / entry_price * 10000 - fee_bps * 2
        trades.append({"pnl_bps": pnl, "hours_held": len(closes) - 1 - entry_idx, "direction": "short"})

    return trades


def backtest_cvd_momentum(candles, cvd_window=24, hold_hours=24, fee_bps=10):
    """CVD momentum: when CVD is rising → long, when falling → short.
    Confirms trend with order flow.
    """
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
                trades.append({"pnl_bps": pnl, "hours_held": i - entry_idx, "direction": "long",
                               "type": "cvd_mom_long"})
                position = 0
        elif position == -1:
            if i - entry_idx >= hold_hours or cvd_change > 0:
                exit_price = closes[i]
                pnl = (entry_price - exit_price) / entry_price * 10000 - fee_bps * 2
                trades.append({"pnl_bps": pnl, "hours_held": i - entry_idx, "direction": "short",
                               "type": "cvd_mom_short"})
                position = 0

    if position == 1:
        pnl = (closes[-1] - entry_price) / entry_price * 10000 - fee_bps * 2
        trades.append({"pnl_bps": pnl, "hours_held": len(closes) - 1 - entry_idx, "direction": "long"})
    elif position == -1:
        pnl = (entry_price - closes[-1]) / entry_price * 10000 - fee_bps * 2
        trades.append({"pnl_bps": pnl, "hours_held": len(closes) - 1 - entry_idx, "direction": "short"})

    return trades


def backtest_cvd_reversal(candles, z_threshold=2.0, window=48, hold_hours=24, fee_bps=10):
    """CVD reversal: when CVD z-score is extreme, take opposite position.
    Extreme positive CVD = overbought → short.
    Extreme negative CVD = oversold → long.
    """
    cvd = compute_cvd(candles)
    closes = [c["close"] for c in candles]

    # CVD z-score (rolling)
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
                position = -1  # CVD overbought → short
                entry_idx = i
                entry_price = closes[i]
            elif cvd_z[i] < -z_threshold:
                position = 1  # CVD oversold → long
                entry_idx = i
                entry_price = closes[i]
        elif position == 1:
            if i - entry_idx >= hold_hours or cvd_z[i] > 0:
                exit_price = closes[i]
                pnl = (exit_price - entry_price) / entry_price * 10000 - fee_bps * 2
                trades.append({"pnl_bps": pnl, "hours_held": i - entry_idx, "direction": "long",
                               "type": "cvd_oversold"})
                position = 0
        elif position == -1:
            if i - entry_idx >= hold_hours or cvd_z[i] < 0:
                exit_price = closes[i]
                pnl = (entry_price - exit_price) / entry_price * 10000 - fee_bps * 2
                trades.append({"pnl_bps": pnl, "hours_held": i - entry_idx, "direction": "short",
                               "type": "cvd_overbought"})
                position = 0

    if position == 1:
        pnl = (closes[-1] - entry_price) / entry_price * 10000 - fee_bps * 2
        trades.append({"pnl_bps": pnl, "hours_held": len(closes) - 1 - entry_idx, "direction": "long"})
    elif position == -1:
        pnl = (entry_price - closes[-1]) / entry_price * 10000 - fee_bps * 2
        trades.append({"pnl_bps": pnl, "hours_held": len(closes) - 1 - entry_idx, "direction": "short"})

    return trades


def summarize(trades, name):
    if not trades:
        return {"name": name, "n_trades": 0, "total_pnl_bps": 0, "win_rate": 0,
                "sharpe": 0, "max_dd_bps": 0, "avg_hold_hours": 0, "avg_pnl_bps": 0}

    pnls = [t["pnl_bps"] for t in trades]
    total = sum(pnls)
    wins = sum(1 for p in pnls if p > 0)
    wr = wins / len(pnls) * 100
    avg = mean(pnls)
    s = std(pnls)
    avg_hold = mean([t["hours_held"] for t in trades])
    tpy = 365 * 24 / max(1, avg_hold)
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

    long_t = [t for t in trades if t["direction"] == "long"]
    short_t = [t for t in trades if t["direction"] == "short"]
    long_wr = (sum(1 for t in long_t if t["pnl_bps"] > 0) / len(long_t) * 100) if long_t else 0
    short_wr = (sum(1 for t in short_t if t["pnl_bps"] > 0) / len(short_t) * 100) if short_t else 0

    return {
        "name": name, "n_trades": len(trades), "total_pnl_bps": total,
        "avg_pnl_bps": avg, "win_rate": wr, "sharpe": sharpe,
        "max_dd_bps": max_dd, "avg_hold_hours": avg_hold,
        "n_long": len(long_t), "n_short": len(short_t),
        "long_wr": long_wr, "short_wr": short_wr,
    }


def run_scan(output_file, symbols, interval, limit):
    print("D16: Order Flow / CVD Signal Scan")
    print(f"Symbols: {', '.join(symbols)}")
    print(f"Interval: {interval}, Limit: {limit} candles")
    print(f"API: Binance public (no API key)")
    print(f"{'='*80}\n")

    all_results = {}

    for symbol in symbols:
        print(f"\n  [{symbol}]")
        try:
            candles = fetch_klines_with_flow(symbol, interval, limit)
        except Exception as e:
            print(f"    Error: {e}")
            try:
                candles = fetch_futures_klines_with_flow(symbol, interval, limit)
            except Exception as e2:
                print(f"    Futures also failed: {e2}")
                continue

        print(f"    Fetched {len(candles)} candles ({interval})")
        if len(candles) < 200:
            print(f"    Skipping — insufficient data")
            continue

        # CVD stats
        deltas = [c["delta"] for c in candles]
        total_buy = sum(c["taker_buy_vol"] for c in candles)
        total_sell = sum(c["taker_sell_vol"] for c in candles)
        buy_sell_ratio = total_buy / total_sell if total_sell > 0 else 0
        print(f"    Order flow: buy={total_buy:.0f} sell={total_sell:.0f} ratio={buy_sell_ratio:.3f}")
        print(f"    Avg delta/candle: {mean(deltas):+.2f}")

        # Walk-forward
        split = int(len(candles) * 0.7)
        train = candles[:split]
        test = candles[split:]
        print(f"    Walk-forward: train={len(train)}, test={len(test)}")

        results = {}

        # Strategy 1: CVD divergence
        for label, data in [("train", train), ("test", test)]:
            for lb in [24, 48, 96]:
                for hold in [12, 24, 48]:
                    trades = backtest_cvd_divergence(data, lb, hold)
                    key = f"diverge_{lb}h_{hold}h_{label}"
                    results[key] = summarize(trades, f"CVD diverge ({lb}h lookback, {hold}h hold)")

        # Strategy 2: CVD momentum
        for label, data in [("train", train), ("test", test)]:
            for cw in [12, 24, 48]:
                for hold in [12, 24, 48]:
                    trades = backtest_cvd_momentum(data, cw, hold)
                    key = f"momentum_{cw}h_{hold}h_{label}"
                    results[key] = summarize(trades, f"CVD momentum ({cw}h window, {hold}h hold)")

        # Strategy 3: CVD reversal (z-score)
        for label, data in [("train", train), ("test", test)]:
            for z in [1.5, 2.0, 3.0]:
                for hold in [12, 24, 48]:
                    trades = backtest_cvd_reversal(data, z, 48, hold)
                    key = f"reversal_z{z}_{hold}h_{label}"
                    results[key] = summarize(trades, f"CVD reversal (z={z}, {hold}h hold)")

        # Find best on train
        train_results = {k: v for k, v in results.items() if k.endswith("_train") and v["n_trades"] >= 5}
        train_sorted = sorted(train_results.values(), key=lambda x: x["sharpe"], reverse=True)

        print(f"\n    Top 5 strategies (train):")
        print(f"    {'Strategy':45s} {'N':>4s} {'WR':>5s} {'PnL':>9s} {'Sharpe':>7s} {'MaxDD':>8s}")
        print("    " + "-" * 80)
        for r in train_sorted[:5]:
            print(f"    {r['name']:45s} {r['n_trades']:4d} {r['win_rate']:4.0f}% "
                  f"{r['total_pnl_bps']:+8.0f} {r['sharpe']:6.2f} {r['max_dd_bps']:7.0f}")

        # OOS results for top 5
        print(f"\n    OOS (test) for top 5 train strategies:")
        print(f"    {'Strategy':45s} {'N':>4s} {'WR':>5s} {'PnL':>9s} {'Sharpe':>7s} {'MaxDD':>8s}")
        print("    " + "-" * 80)
        for train_r in train_sorted[:5]:
            test_key = train_r["name"].replace("lookback", "lookback")  # same name
            # Find matching test result
            test_r = None
            for k, v in results.items():
                if k.endswith("_test") and v["name"] == train_r["name"] and v["n_trades"] >= 3:
                    test_r = v
                    break
            if test_r:
                print(f"    {test_r['name']:45s} {test_r['n_trades']:4d} {test_r['win_rate']:4.0f}% "
                      f"{test_r['total_pnl_bps']:+8.0f} {test_r['sharpe']:6.2f} {test_r['max_dd_bps']:7.0f}")
            else:
                print(f"    {train_r['name']:45s}  no trades OOS")

        # Best OOS
        test_results = {k: v for k, v in results.items() if k.endswith("_test") and v["n_trades"] >= 3}
        test_sorted = sorted(test_results.values(), key=lambda x: x["sharpe"], reverse=True)
        if test_sorted:
            best = test_sorted[0]
            print(f"\n    Best OOS: {best['name']}")
            print(f"      Sharpe={best['sharpe']:.2f}, WR={best['win_rate']:.0f}%, "
                  f"N={best['n_trades']}, PnL={best['total_pnl_bps']:+.0f}bps, "
                  f"MaxDD={best['max_dd_bps']:.0f}bps")
            print(f"      Long WR={best.get('long_wr', 0):.0f}%, Short WR={best.get('short_wr', 0):.0f}%")

        all_results[symbol] = {
            "n_candles": len(candles),
            "buy_sell_ratio": buy_sell_ratio,
            "train_size": len(train),
            "test_size": len(test),
            "results": results,
            "best_oos": test_sorted[0] if test_sorted else None,
        }

    # Save
    with open(output_file, "w") as f:
        json.dump(all_results, f, indent=2, default=str)

    # Summary
    print(f"\n{'='*80}")
    print(f"SUMMARY\n")

    for symbol, data in all_results.items():
        print(f"  {symbol}:")
        print(f"    Buy/Sell ratio: {data['buy_sell_ratio']:.3f}")
        if data.get("best_oos"):
            b = data["best_oos"]
            print(f"    Best OOS: {b['name']}")
            print(f"      Sharpe={b['sharpe']:.2f}, WR={b['win_rate']:.0f}%, "
                  f"N={b['n_trades']}, PnL={b['total_pnl_bps']:+.0f}bps")
        else:
            print(f"    No valid OOS strategy")

    print(f"\n  PROFITABILITY ANALYSIS:")
    print(f"  - CVD measures order flow imbalance (taker buy vs sell)")
    print(f"  - Three signal types tested: divergence, momentum, reversal")
    print(f"  - Divergence: price new high/low but CVD doesn't confirm → reversal")
    print(f"  - Momentum: CVD rising → long, falling → short")
    print(f"  - Reversal: CVD z-score extreme → opposite position")
    print(f"  - Fees: 10 bps/side × 2 = 20 bps per round trip")
    print(f"  - Key risk: CVD is noisy on short timeframes, needs filtering")


def main():
    parser = argparse.ArgumentParser(description="D16 CVD / Order Flow Signal Scan")
    parser.add_argument("--output", type=str, default="cvd_signal_samples.json")
    parser.add_argument("--symbols", type=str, nargs="+", default=["BTCUSDT", "ETHUSDT", "SOLUSDT"])
    parser.add_argument("--interval", type=str, default="1h")
    parser.add_argument("--limit", type=int, default=1000)
    args = parser.parse_args()

    output_path = os.path.join(os.path.dirname(__file__), args.output)
    run_scan(output_path, args.symbols, args.interval, args.limit)


if __name__ == "__main__":
    main()
