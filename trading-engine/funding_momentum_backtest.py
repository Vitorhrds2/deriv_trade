"""
D35 — Funding Rate Backtest: Test if funding momentum is tradeable after fees

Backtest methodology:
  1. Fetch 30 days of funding history for top 20 perps
  2. For each funding event, simulate: if last 3 fundings were positive → SHORT
     (collect positive funding), if last 3 negative → LONG (collect negative funding)
  3. P&L = funding_collected - fees (0.04% per side = 0.08% roundtrip)
  4. Measure: WR, EV, total P&L, Sharpe ratio, max drawdown

This is the DECISIVE test: 88.7% momentum accuracy was just direction prediction.
This backtest measures if it's PROFITABLE after costs.
"""
import json
import urllib.request
from datetime import datetime, timezone
from collections import defaultdict

FEE_PCT = 0.08  # 0.04% taker x 2 sides
POSITION_SIZE = 1000  # $1000 per trade
TOP_N = 20
DAYS_BACK = 30


def fetch_json(url, timeout=15):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode())


def fetch_top_symbols(n=20):
    url = "https://fapi.binance.com/fapi/v1/ticker/24hr"
    data = fetch_json(url)
    usdt = [d for d in data if d["symbol"].endswith("USDT")]
    usdt.sort(key=lambda x: float(x["quoteVolume"]), reverse=True)
    return [d["symbol"] for d in usdt[:n]]


def fetch_funding_history(symbol, limit=100):
    """Fetch funding rate history (limit=100 gives ~33 days at 3 fundings/day)."""
    url = f"https://fapi.binance.com/fapi/v1/fundingRate?symbol={symbol}&limit={limit}"
    data = fetch_json(url)
    return [{"time": d["fundingTime"], "rate": float(d["fundingRate"])} for d in data]


def backtest_momentum(rates, fee_pct=0.08, position_size=1000):
    """Backtest funding momentum strategy.
    
    Strategy: if last 3 fundings same direction, enter position to collect funding.
    SHORT if last 3 positive (longs pay shorts).
    LONG if last 3 negative (shorts pay longs).
    """
    trades = []
    
    for i in range(3, len(rates)):
        last3 = [rates[j]["rate"] for j in range(i-3, i)]
        actual = rates[i]
        actual_rate = actual["rate"]
        
        last3_positive = all(r > 0 for r in last3)
        last3_negative = all(r < 0 for r in last3)
        
        if last3_positive:
            # SHORT: collect positive funding (longs pay shorts)
            direction = "SHORT"
            funding_collected = actual_rate * position_size  # positive funding, short receives
            fee_cost = fee_pct / 100 * position_size
            pnl = funding_collected - fee_cost
        elif last3_negative:
            # LONG: collect negative funding (shorts pay longs)
            direction = "LONG"
            funding_collected = abs(actual_rate) * position_size  # negative funding, long receives
            fee_cost = fee_pct / 100 * position_size
            pnl = funding_collected - fee_cost
        else:
            continue  # no signal
        
        correct = (direction == "SHORT" and actual_rate > 0) or \
                  (direction == "LONG" and actual_rate < 0)
        
        trades.append({
            "index": i,
            "time": actual["time"],
            "direction": direction,
            "funding_rate": actual_rate,
            "funding_pct": actual_rate * 100,
            "funding_collected_usd": funding_collected,
            "fee_cost_usd": fee_cost,
            "pnl_usd": pnl,
            "pnl_pct": pnl / position_size * 100,
            "correct_direction": correct,
        })
    
    return trades


def backtest_momentum_2(rates, fee_pct=0.08, position_size=1000):
    """Variant: last 2 fundings same direction (more signals, less strict)."""
    trades = []
    
    for i in range(2, len(rates)):
        last2 = [rates[j]["rate"] for j in range(i-2, i)]
        actual = rates[i]
        actual_rate = actual["rate"]
        
        last2_positive = all(r > 0 for r in last2)
        last2_negative = all(r < 0 for r in last2)
        
        if last2_positive:
            direction = "SHORT"
            funding_collected = actual_rate * position_size
            fee_cost = fee_pct / 100 * position_size
            pnl = funding_collected - fee_cost
        elif last2_negative:
            direction = "LONG"
            funding_collected = abs(actual_rate) * position_size
            fee_cost = fee_pct / 100 * position_size
            pnl = funding_collected - fee_cost
        else:
            continue
        
        correct = (direction == "SHORT" and actual_rate > 0) or \
                  (direction == "LONG" and actual_rate < 0)
        
        trades.append({
            "direction": direction,
            "funding_pct": actual_rate * 100,
            "pnl_usd": pnl,
            "pnl_pct": pnl / position_size * 100,
            "correct": correct,
        })
    
    return trades


def backtest_premium_based(rates, fee_pct=0.08, position_size=1000):
    """Variant: always enter in direction of last funding (1-period momentum)."""
    trades = []
    
    for i in range(1, len(rates)):
        prev_rate = rates[i-1]["rate"]
        actual = rates[i]
        actual_rate = actual["rate"]
        
        if prev_rate > 0:
            direction = "SHORT"
            funding_collected = actual_rate * position_size
        else:
            direction = "LONG"
            funding_collected = abs(actual_rate) * position_size
        
        fee_cost = fee_pct / 100 * position_size
        pnl = funding_collected - fee_cost
        correct = (direction == "SHORT" and actual_rate > 0) or \
                  (direction == "LONG" and actual_rate < 0)
        
        trades.append({
            "direction": direction,
            "funding_pct": actual_rate * 100,
            "pnl_usd": pnl,
            "pnl_pct": pnl / position_size * 100,
            "correct": correct,
        })
    
    return trades


def summarize(trades, label):
    if not trades:
        print(f"\n  {label}: No trades")
        return
    
    pnls = [t["pnl_usd"] for t in trades]
    correct = [t for t in trades if t.get("correct_direction", t.get("correct", False))]
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p <= 0]
    
    total_pnl = sum(pnls)
    ev = total_pnl / len(pnls)
    wr_dir = len(correct) / len(trades) * 100
    wr_profit = len(wins) / len(pnls) * 100
    
    # Sharpe approximation (per-trade)
    import math
    mean_pnl = ev
    if len(pnls) > 1:
        variance = sum((p - mean_pnl) ** 2 for p in pnls) / (len(pnls) - 1)
        std = math.sqrt(variance) if variance > 0 else 1
        sharpe = mean_pnl / std if std > 0 else 0
    else:
        sharpe = 0
    
    # Max drawdown
    cumulative = 0
    peak = 0
    max_dd = 0
    for p in pnls:
        cumulative += p
        if cumulative > peak:
            peak = cumulative
        dd = peak - cumulative
        if dd > max_dd:
            max_dd = dd
    
    # Annualized estimate (3 fundings/day × 365 = 1095 fundings/year)
    annual_pnl = ev * 1095
    annual_pct = annual_pnl / POSITION_SIZE * 100
    
    print(f"\n  {label}:")
    print(f"    Trades: {len(trades)}")
    print(f"    Direction WR: {wr_dir:.1f}%")
    print(f"    Profitable WR: {wr_profit:.1f}% ({len(wins)} wins / {len(losses)} losses)")
    print(f"    EV/trade: ${ev:+.4f} ({ev/POSITION_SIZE*100:+.4f}%)")
    print(f"    Total P&L: ${total_pnl:+.2f}")
    print(f"    Sharpe (per-trade): {sharpe:.3f}")
    print(f"    Max drawdown: ${max_dd:.2f}")
    print(f"    Annualized est: ${annual_pnl:+.2f} ({annual_pct:+.1f}% on ${POSITION_SIZE})")
    
    # Best and worst trades
    best = max(pnls)
    worst = min(pnls)
    print(f"    Best trade: ${best:+.4f} | Worst trade: ${worst:+.4f}")
    
    return {
        "label": label,
        "trades": len(trades),
        "wr_direction": wr_dir,
        "wr_profitable": wr_profit,
        "ev_per_trade": ev,
        "total_pnl": total_pnl,
        "sharpe": sharpe,
        "max_drawdown": max_dd,
        "annualized_pnl": annual_pnl,
        "annualized_pct": annual_pct,
    }


def run_backtest():
    print("=" * 80)
    print("D35 — Funding Rate Momentum Backtest (DECISIVE TEST)")
    print("=" * 80)
    print(f"  Testing 3 strategies on top {TOP_N} perps, ~{DAYS_BACK} days history")
    print(f"  Fee: {FEE_PCT}% roundtrip | Position: ${POSITION_SIZE}")
    print()
    
    top_syms = fetch_top_symbols(TOP_N)
    print(f"  Symbols: {', '.join(top_syms[:5])}...")
    
    all_3period = []
    all_2period = []
    all_1period = []
    per_symbol = []
    
    for sym in top_syms:
        try:
            rates = fetch_funding_history(sym, limit=100)
            if len(rates) < 5:
                continue
            
            rates_only = [r["rate"] for r in rates]
            
            t3 = backtest_momentum(rates, FEE_PCT, POSITION_SIZE)
            t2 = backtest_momentum_2(rates, FEE_PCT, POSITION_SIZE)
            t1 = backtest_premium_based(rates, FEE_PCT, POSITION_SIZE)
            
            all_3period.extend(t3)
            all_2period.extend(t2)
            all_1period.extend(t1)
            
            # Per-symbol summary
            if t3:
                sym_pnls = [t["pnl_usd"] for t in t3]
                sym_wr = sum(1 for p in sym_pnls if p > 0) / len(sym_pnls) * 100
                sym_total = sum(sym_pnls)
                per_symbol.append({
                    "symbol": sym,
                    "trades": len(t3),
                    "wr": sym_wr,
                    "total_pnl": sym_total,
                    "avg_funding": sum(rates_only) / len(rates_only) * 100,
                })
            
        except Exception as e:
            print(f"  ERROR {sym}: {e}")
    
    # Overall results
    print(f"\n{'='*80}")
    print(f"OVERALL RESULTS ({len(top_syms)} symbols, ~{DAYS_BACK} days)")
    print(f"{'='*80}")
    
    r3 = summarize(all_3period, "Strategy 1: 3-period momentum (last 3 same direction)")
    r2 = summarize(all_2period, "Strategy 2: 2-period momentum (last 2 same direction)")
    r1 = summarize(all_1period, "Strategy 3: 1-period momentum (follow last funding)")
    
    # Per-symbol breakdown
    print(f"\n{'='*80}")
    print("PER-SYMBOL BREAKDOWN (3-period momentum)")
    print(f"{'='*80}")
    per_symbol.sort(key=lambda x: x["total_pnl"], reverse=True)
    print(f"  {'Symbol':<14s} {'Trades':>6s} {'WR%':>6s} {'Total P&L':>12s} {'Avg Fund%':>10s}")
    print(f"  {'-'*14} {'-'*6} {'-'*6} {'-'*12} {'-'*10}")
    for s in per_symbol:
        print(f"  {s['symbol']:<14s} {s['trades']:>6d} {s['wr']:>6.1f} "
              f"${s['total_pnl']:>+11.2f} {s['avg_funding']:>+10.4f}")
    
    # Verdict
    print(f"\n{'='*80}")
    print("VERDICT")
    print(f"{'='*80}")
    
    best = None
    best_label = ""
    for r, label in [(r3, "3-period"), (r2, "2-period"), (r1, "1-period")]:
        if r and r["ev_per_trade"] > 0 and r["wr_profitable"] > 50:
            print(f"  *** {label}: EDGE CONFIRMED — EV ${r['ev_per_trade']:+.4f}/trade, "
                  f"WR {r['wr_profitable']:.1f}%, Annual {r['annualized_pct']:+.1f}% ***")
            if not best or r["ev_per_trade"] > best["ev_per_trade"]:
                best = r
                best_label = label
        elif r and r["ev_per_trade"] > 0:
            print(f"  {label}: Marginal positive EV but WR < 50% — not reliable")
        else:
            print(f"  {label}: NEGATIVE EV — momentum is not tradeable after fees")
    
    if best:
        print(f"\n  BEST STRATEGY: {best_label}")
        print(f"  Annualized P&L: ${best['annualized_pnl']:+.2f} ({best['annualized_pct']:+.1f}%)")
        print(f"  On $10,000 capital: ${best['annualized_pnl']*10:+.2f}/year")
    else:
        print(f"\n  NO STRATEGY IS PROFITABLE AFTER FEES.")
        print(f"  Funding momentum predicts direction (88.7%) but funding rates")
        print(f"  are too small to cover 0.08% roundtrip fees on most periods.")
        print(f"  Edge may exist during high-volatility periods (funding > 0.1%).")
    
    # Save
    with open("funding_momentum_backtest_results.json", "w") as f:
        json.dump({
            "strategy_3period": r3,
            "strategy_2period": r2,
            "strategy_1period": r1,
            "per_symbol": per_symbol,
        }, f, indent=2)
    
    return best


if __name__ == "__main__":
    run_backtest()
