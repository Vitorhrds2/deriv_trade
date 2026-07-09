#!/usr/bin/env python3
"""Analyze deal cancellation live probe results."""
import json

trades = []
with open("/home/ubuntu/trading-engine/deal_cancellation_live_results.jsonl") as f:
    for line in f:
        line = line.strip()
        if line:
            try:
                trades.append(json.loads(line))
            except:
                pass

print(f"Total trades: {len(trades)}")
fees = [float(t.get("fee", 0)) for t in trades]
realized = [float(t.get("realized_value", 0)) for t in trades]
cancelled = [t for t in trades if "cancel" in str(t.get("action", ""))]
expired = [t for t in trades if "expired" in str(t.get("action", ""))]

total_fee = sum(fees)
total_realized = sum(realized)
net = total_realized - total_fee

print(f"Cancelled: {len(cancelled)} | Expired held: {len(expired)}")
print(f"Total fees paid: ${total_fee:.2f}")
print(f"Total realized (savings from cancel): ${total_realized:.2f}")
print(f"NET P&L: ${net:.2f}")
print(f"Avg fee/trade: ${total_fee/len(trades):.2f}")
print(f"Avg realized/trade: ${total_realized/len(trades):.2f}")
print(f"Avg net/trade: ${net/len(trades):.2f}")
print()

if cancelled:
    canc_realized = [float(t.get("realized_value", 0)) for t in cancelled]
    canc_fees = [float(t.get("fee", 0)) for t in cancelled]
    canc_net = sum(canc_realized) - sum(canc_fees)
    print(f"--- CANCELLED trades ({len(cancelled)}) ---")
    print(f"  Realized: ${sum(canc_realized):.2f} | Fees: ${sum(canc_fees):.2f} | Net: ${canc_net:.2f}")
    print(f"  Avg realized: ${sum(canc_realized)/len(cancelled):.2f} | Avg fee: ${sum(canc_fees)/len(cancelled):.2f}")
    print(f"  Net/trade: ${canc_net/len(cancelled):.2f}")
    wins = sum(1 for r in canc_realized if r > 0)
    print(f"  WR (realized > 0): {wins}/{len(cancelled)} = {wins/len(cancelled)*100:.1f}%")

if expired:
    exp_fees = [float(t.get("fee", 0)) for t in expired]
    print(f"--- EXPIRED trades ({len(expired)}) ---")
    print(f"  Fees wasted: ${sum(exp_fees):.2f} (paid fee, never used cancellation)")

print()
print(f"--- BOTTOM LINE ---")
print(f"Fee per trade: ${fees[0]:.2f}")
if cancelled:
    print(f"Avg savings when cancelled: ${sum(canc_realized)/len(cancelled):.2f}")
print(f"Probability of cancelling: {len(cancelled)/len(trades)*100:.1f}%")
print(f"Expected value per trade: ${net/len(trades):.2f}")

# Check if profitable
if net > 0:
    print(f"STATUS: PROFITABLE (but check IC95%)")
else:
    print(f"STATUS: UNPROFITABLE")
