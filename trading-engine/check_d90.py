#!/usr/bin/env python3
"""D90 correct analysis with strategy_profit field."""
import json

with open('d90_live_20260712_results.jsonl') as f:
    results = [json.loads(l) for l in f.readlines()]

sells = [r for r in results if r.get('group') == 'sell']
holds = [r for r in results if r.get('group') == 'hold']

print(f"N={len(results)} Sell={len(sells)} Hold={len(holds)}")

if sells:
    sp = [r.get('strategy_profit', 0) for r in sells]
    sw = sum(1 for p in sp if p > 0)
    print(f"Sell: WR={sw/len(sells)*100:.1f}% PnL=${sum(sp):.2f} EV=${sum(sp)/len(sells):.4f}")

if holds:
    hp = [r.get('strategy_profit', 0) for r in holds]
    hw = sum(1 for p in hp if p > 0)
    print(f"Hold: WR={hw/len(holds)*100:.1f}% PnL=${sum(hp):.2f} EV=${sum(hp)/len(holds):.4f}")

# Paired comparison
pairs = {}
for r in results:
    pid = r.get('pair_id')
    g = r.get('group')
    if pid not in pairs:
        pairs[pid] = {}
    pairs[pid][g] = r.get('strategy_profit', 0)

paired = [(p['sell'], p['hold']) for p in pairs.values() if 'sell' in p and 'hold' in p]
if paired:
    diffs = [s - h for s, h in paired]
    n = len(diffs)
    mean_diff = sum(diffs) / n
    print(f"Paired: N={n} Mean diff (sell-hold)={mean_diff:.4f}")
    # Bootstrap
    import random
    random.seed(42)
    boots = []
    for _ in range(10000):
        sample = random.choices(diffs, k=n)
        boots.append(sum(sample) / n)
    boots.sort()
    ci_lo = boots[int(0.025 * len(boots))]
    ci_hi = boots[int(0.975 * len(boots))]
    print(f"  IC95%=[{ci_lo:.4f}, {ci_hi:.4f}] Crosses zero: {ci_lo < 0 < ci_hi}")

# Show terminal status distribution
print("\nTerminal status distribution:")
from collections import Counter
sell_terminals = Counter(r.get('terminal') for r in sells)
hold_terminals = Counter(r.get('terminal') for r in holds)
print(f"  Sell: {dict(sell_terminals)}")
print(f"  Hold: {dict(hold_terminals)}")
