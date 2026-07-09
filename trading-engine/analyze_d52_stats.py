#!/usr/bin/env python3
"""Analyze D52 deal cancellation with stats_utils IC95%."""
import json
from stats_utils import bootstrap_ci, wilson_ci

trades = []
with open("/home/ubuntu/trading-engine/deal_cancellation_live_results.jsonl") as f:
    for line in f:
        line = line.strip()
        if line:
            try:
                trades.append(json.loads(line))
            except:
                pass

# Per-trade net P&L
nets = [float(t.get("realized_value", 0)) - float(t.get("fee", 0)) for t in trades]
n = len(nets)
mean = sum(nets) / n
ci = bootstrap_ci(nets)
wins = sum(1 for x in nets if x > 0)
wr_ci = wilson_ci(wins, n)

print(f"N={n} | Net P&L=${sum(nets):.2f} | EV/trade=${mean:.2f}")
print(f"EV IC95%: [${ci[0]:.2f}, ${ci[1]:.2f}]")
print(f"WR (net>0): {wins}/{n} = {wins/n*100:.1f}% | Wilson IC95%: [{wr_ci[0]*100:.1f}%, {wr_ci[1]*100:.1f}%]")
print()

# Cancel rate
cancelled = sum(1 for t in trades if "cancel" in str(t.get("action", "")))
print(f"Cancel rate: {cancelled}/{n} = {cancelled/n*100:.1f}%")
print()

# Expired trades analysis
expired_trades = [t for t in trades if "expired" in str(t.get("action", ""))]
expired_profits = [float(t.get("profit_at_action", 0)) for t in expired_trades]
if expired_trades:
    print(f"Expired trades ({len(expired_trades)}): avg profit at expiry=${sum(expired_profits)/len(expired_trades):.2f}")
    exp_fees = sum(float(t.get("fee", 0)) for t in expired_trades)
    print(f"  Fees wasted: ${exp_fees:.2f}")

# Cancelled trades analysis
cancelled_trades = [t for t in trades if "cancel" in str(t.get("action", ""))]
canc_nets = [float(t.get("realized_value", 0)) - float(t.get("fee", 0)) for t in cancelled_trades]
if cancelled_trades:
    print(f"Cancelled trades ({len(cancelled_trades)}): avg net=${sum(canc_nets)/len(canc_nets):.2f}")

# The real question: what would happen WITHOUT cancellation?
# Without cancellation: expired trades keep their profit, cancelled trades would have
# been held to expiry with whatever P&L they had at cancellation time (bid_price - buy_price)
print()
print("=== COUNTERFACTUAL: What if NO cancellation was bought? ===")
# For cancelled trades: they would have been held to expiry
# We don't know the final P&L, but we know the bid at cancellation time
# If they cancelled, profit was negative. Without cancel, they'd hold and maybe recover or get worse
# This is unknowable without hindsight, but we can estimate:
# The cancellation saves (stake - bid) when profit < 0
# Without it, they'd have the profit at expiry (unknowable)
# So the edge is: fee paid vs expected savings from cancelling losing trades

print()
print("=== EXPLOIT ANALYSIS ===")
print(f"Fee per trade: $0.44 (fixed)")
print(f"Avg savings when cancelled: ${sum(float(t.get('realized_value',0)) for t in cancelled_trades)/len(cancelled_trades):.2f}")
print(f"Cancel rate: {cancelled/n*100:.1f}%")
print(f"Expected savings per trade: ${sum(nets)/n:.2f}")
print(f"EV IC95%: [${ci[0]:.2f}, ${ci[1]:.2f}]")
if ci[0] > 0:
    print("STATUS: STATISTICALLY SIGNIFICANT EDGE")
elif ci[1] > 0:
    print("STATUS: INCONCLUSIVO (IC95% cruza zero)")
else:
    print("STATUS: NO EDGE")
