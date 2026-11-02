#!/usr/bin/env python3
"""Check D90 details and D52/D95 IC95%."""
import json, random

# D90 — check why profits are 0
print("=== D90 sample records ===")
with open('d90_live_20260712_results.jsonl') as f:
    results = [json.loads(l) for l in f.readlines()]
for r in results[:5]:
    print(json.dumps(r, indent=2)[:400])
    print()

# D52 — bootstrap IC95% on EV
print("=== D52 bootstrap ===")
with open('deal_cancellation_live_results.jsonl') as f:
    all_lines = [json.loads(l) for l in f.readlines()]
trades = [r for r in all_lines if 'error' not in r and 'fee' in r]
if trades:
    nets = [r.get('realized_value', 0) - r.get('fee', 0) for r in trades]
    n = len(nets)
    mean_ev = sum(nets) / n
    random.seed(42)
    boots = []
    for _ in range(10000):
        sample = random.choices(nets, k=n)
        boots.append(sum(sample) / n)
    boots.sort()
    ci_lo = boots[int(0.025 * len(boots))]
    ci_hi = boots[int(0.975 * len(boots))]
    print(f"N={n} EV=${mean_ev:.4f} IC95%=[${ci_lo:.4f}, ${ci_hi:.4f}]")
    print(f"Crosses zero: {ci_lo < 0 < ci_hi}")

# D95 — bootstrap IC95% on EV
print("\n=== D95 bootstrap ===")
with open('d95_deal_cancellation_live_results.jsonl') as f:
    all_lines = [json.loads(l) for l in f.readlines()]
trades = [r for r in all_lines if 'error' not in r and 'fee' in r]
if trades:
    nets = [r.get('realized_value', 0) - r.get('fee', 0) for r in trades]
    n = len(nets)
    mean_ev = sum(nets) / n
    random.seed(42)
    boots = []
    for _ in range(10000):
        sample = random.choices(nets, k=n)
        boots.append(sum(sample) / n)
    boots.sort()
    ci_lo = boots[int(0.025 * len(boots))]
    ci_hi = boots[int(0.975 * len(boots))]
    print(f"N={n} EV=${mean_ev:.4f} IC95%=[${ci_lo:.4f}, ${ci_hi:.4f}]")
    print(f"Crosses zero: {ci_lo < 0 < ci_hi}")
