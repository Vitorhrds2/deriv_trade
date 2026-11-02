#!/usr/bin/env python3
"""Quick stats analysis for D52 and D95 deal cancellation results."""
import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from stats_utils import bootstrap_ci, wilson_ci

for name, fname in [('D52', 'deal_cancellation_live_results.jsonl'), ('D95', 'd95_deal_cancellation_live_results.jsonl')]:
    if not os.path.exists(fname):
        print(f"=== {name}: no results file ===")
        continue
    trades = []
    with open(fname) as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    t = json.loads(line)
                    if 'error' not in t:
                        trades.append(t)
                except:
                    pass
    nets = [float(t.get('realized_value', 0)) - float(t.get('fee', 0)) for t in trades]
    n = len(nets)
    if n > 0:
        lo, mean, hi = bootstrap_ci(nets, n_boot=2000)
        wins = sum(1 for x in nets if x > 0)
        wr_lo, wr_hi = wilson_ci(wins, n)
        total_fees = sum(float(t.get('fee', 0)) for t in trades)
        total_realized = sum(float(t.get('realized_value', 0)) for t in trades)
        print(f"=== {name} (N={n}) ===")
        print(f"  EV/trade = ${mean:+.4f} IC95%=[${lo:+.4f}, ${hi:+.4f}]")
        print(f"  WR = {wins}/{n} = {wins/n*100:.1f}% IC95%=[{wr_lo*100:.1f}%, {wr_hi*100:.1f}%]")
        print(f"  Total fees = ${total_fees:.2f}")
        print(f"  Total realized = ${total_realized:.2f}")
        print(f"  Net = ${sum(nets):+.2f}")
        if lo > 0:
            print(f"  STATUS: EDGE CONFIRMADO")
        elif hi < 0:
            print(f"  STATUS: SEM EDGE")
        else:
            print(f"  STATUS: INCONCLUSIVO")
        print()
    else:
        print(f"=== {name}: no valid trades ===")
        print()
