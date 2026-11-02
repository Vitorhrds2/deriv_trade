#!/usr/bin/env python3
"""Comprehensive status check for all running hypotheses."""
import json, math, os

def wilson_ci(wins, n, z=1.96):
    if n == 0: return (0, 0)
    p = wins / n
    denom = 1 + z*z/n
    center = (p + z*z/(2*n)) / denom
    spread = z * math.sqrt((p*(1-p) + z*z/(4*n)) / n) / denom
    return (center - spread, center + spread)

print("=" * 80)
print("COMPREHENSIVE HYPOTHESIS STATUS — $(date)")
print("=" * 80)

# D37 — Exchange Outflow
print("\n--- D37 Exchange Outflow ---")
with open('d37_signal_history.json') as f:
    data = json.load(f)
signals = [d for d in data if d.get('direction', 0) != 0]
resolved_sig = [d for d in signals if d.get('resolved')]
print(f"Total signals: {len(data)}, With direction: {len(signals)}, Resolved: {len(resolved_sig)}")
for h in [3600, 14400, 86400]:
    h_key = str(h)
    items = [d for d in resolved_sig if d.get('resolved', {}).get(h_key)]
    if items:
        returns = [d['resolved'][h_key]['return_pct'] * d['direction'] for d in items]
        wins = sum(1 for r in returns if r > 0)
        n = len(returns)
        ev = sum(returns) / n
        ci_lo, ci_hi = wilson_ci(wins, n)
        print(f"  @{h}s: N={n} WR={wins/n*100:.1f}% IC95%=[{ci_lo*100:.1f}%, {ci_hi*100:.1f}%] EV={ev:+.4f}%")

# D52 — Deal Cancellation
print("\n--- D52 Deal Cancellation ---")
with open('deal_cancellation_live_results.jsonl') as f:
    all_lines = [json.loads(l) for l in f.readlines()]
errors = [r for r in all_lines if 'error' in r]
trades = [r for r in all_lines if 'error' not in r and 'fee' in r]
print(f"Total={len(all_lines)} Errors={len(errors)} Valid trades={len(trades)}")
if trades:
    fees = sum(r.get('fee', 0) for r in trades)
    realized = sum(r.get('realized_value', 0) for r in trades)
    net = realized - fees
    cancelled = sum(1 for r in trades if r.get('action', '').startswith('cancelled'))
    print(f"  Cancelled={cancelled} Expired={len(trades)-cancelled}")
    print(f"  Fees=${fees:.2f} Realized=${realized:.2f} Net=${net:.2f} EV=${net/len(trades):.4f}")

# D95 — Deal Cancellation v2
print("\n--- D95 Deal Cancellation v2 ---")
with open('d95_deal_cancellation_live_results.jsonl') as f:
    all_lines = [json.loads(l) for l in f.readlines()]
errors = [r for r in all_lines if 'error' in r]
trades = [r for r in all_lines if 'error' not in r and 'fee' in r]
print(f"Total={len(all_lines)} Errors={len(errors)} Valid trades={len(trades)}")
if trades:
    fees = sum(r.get('fee', 0) for r in trades)
    realized = sum(r.get('realized_value', 0) for r in trades)
    net = realized - fees
    cancelled = sum(1 for r in trades if r.get('action', '').startswith('cancelled'))
    print(f"  Cancelled={cancelled} Expired={len(trades)-cancelled}")
    print(f"  Fees=${fees:.2f} Realized=${realized:.2f} Net=${net:.2f} EV=${net/len(trades):.4f}")

# D90 — Early Sell
print("\n--- D90 Early Sell A/B ---")
with open('d90_live_20260712_results.jsonl') as f:
    results = [json.loads(l) for l in f.readlines()]
sells = [r for r in results if r.get('group') == 'sell']
holds = [r for r in results if r.get('group') == 'hold']
print(f"N={len(results)} Sell={len(sells)} Hold={len(holds)}")
if sells:
    sp = [r.get('profit', 0) for r in sells]
    sw = sum(1 for p in sp if p > 0)
    print(f"  Sell: WR={sw/len(sells)*100:.1f}% PnL=${sum(sp):.2f} EV=${sum(sp)/len(sells):.4f}")
if holds:
    hp = [r.get('profit', 0) for r in holds]
    hw = sum(1 for p in hp if p > 0)
    print(f"  Hold: WR={hw/len(holds)*100:.1f}% PnL=${sum(hp):.2f} EV=${sum(hp)/len(holds):.4f}")
pairs = {}
for r in results:
    pid = r.get('pair_id')
    g = r.get('group')
    if pid not in pairs: pairs[pid] = {}
    pairs[pid][g] = r.get('profit', 0)
paired = [(p['sell'], p['hold']) for p in pairs.values() if 'sell' in p and 'hold' in p]
if paired:
    diffs = [s - h for s, h in paired]
    print(f"  Paired: N={len(paired)} Mean diff={sum(diffs)/len(diffs):.4f}")

# D29 — Basis
print("\n--- D29 Basis Funding ---")
with open('basis_paper_stats.json') as f:
    stats = json.load(f)
print(f"  N={stats['n']} WR={stats['wr']*100:.1f}% IC95%=[{stats['wr_ci95'][0]*100:.1f}%, {stats['wr_ci95'][1]*100:.1f}%]")
print(f"  EV={stats['ev_pct']:+.4f}% IC95%=[{stats['ev_ci95'][0]:+.4f}%, {stats['ev_ci95'][1]:+.4f}%]")
print(f"  Total PnL={stats['total_pnl_pct']:+.4f}%")

# D55 — Hyperliquid
print("\n--- D55 Hyperliquid Funding Arb ---")
try:
    with open('d55_paper.log') as f:
        for line in f:
            if 'CYCLE' in line and 'TOTAL' in line:
                last_cycle = line.strip()
    print(f"  {last_cycle[:200]}")
except:
    print("  No data")

# D17 — Unlock
print("\n--- D17 Token Unlock Short ---")
try:
    with open('unlock_bot.log') as f:
        for line in f:
            if 'Status:' in line:
                last_status = line.strip()
    print(f"  {last_status[:200]}")
except:
    print("  No data")

# D36 — IV Anomaly
print("\n--- D36 IV Surface Anomaly ---")
try:
    with open('iv_anomaly_paper_bot.log') as f:
        for line in f:
            if 'STATS:' in line:
                last_stats = line.strip()
    print(f"  {last_stats[:200]}")
except:
    print("  No data")

# D101 — Barrier
print("\n--- D101 Barrier Proximity ---")
try:
    with open('d101_continuous.log') as f:
        lines = f.readlines()
    running = [l for l in lines if 'Running' in l]
    if running:
        print(f"  {running[-1].strip()[:200]}")
except:
    print("  No data")

# H85 — SWIFT
print("\n--- H85 Velocity SWIFT ---")
try:
    with open('h85_drift/h85_continuous.log') as f:
        for line in f:
            if 'Status' in line and 'total msgs' in line:
                last_status = line.strip()
    print(f"  {last_status[:200]}")
except:
    print("  No data")

print("\n" + "=" * 80)
