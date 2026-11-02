import json

lines = open("trading-engine/d107_rate_limit_winner_holding_results.jsonl").readlines()
snapshots = []
sells = []
cancels = []

for l in lines:
    try:
        obj = json.loads(l)
        ev = obj.get("event")
        if ev == "sell_confirmed":
            sells.append(obj)
        elif ev == "cancel_confirmed":
            cancels.append(obj)
    except Exception:
        pass

print(f"Total sell_confirmed in file: {len(sells)}")
print(f"Total cancel_confirmed in file: {len(cancels)}")

# Look at new session (trials >= 94)
new_sells = [s for s in sells if s.get("trial", 0) >= 94]
new_cancels = [c for c in cancels if c.get("trial", 0) >= 94]

print(f"New session (1HZ75V): Sells={len(new_sells)} | Cancels={len(new_cancels)}")

# Check market drift during each trade:
# For MULTUP: profit > 0 when current_spot > entry_spot
# For MULTDOWN: profit > 0 when current_spot < entry_spot

# Let's inspect the last 20 sells:
print("\nLast 15 Sells:")
for s in new_sells[-15:]:
    trial = s.get("trial")
    cid = s.get("contract_id")
    action = s.get("action")
    pnl = s.get("realized_pnl")
    entry = s.get("entry_spot")
    current = s.get("current_spot")
    reason = s.get("close_reason")
    profit_pct = (pnl / 1.08) * 100 if pnl else 0
    print(f"  Trial {trial} | {action} | Reason: {reason} | Entry: {entry} -> Exit: {current} | PnL: ${pnl:+.2f} ({profit_pct:+.1f}%)")

print("\nLast 15 Cancels:")
for c in new_cancels[-15:]:
    trial = c.get("trial")
    cid = c.get("contract_id")
    entry = c.get("entry_spot")
    current = c.get("current_spot")
    fee = c.get("cancellation_fee")
    diff = (current - entry) if (current and entry) else 0
    print(f"  Trial {trial} | Entry: {entry} -> Exit: {current} (Diff: {diff:+.2f}) | Fee: -${fee:.2f}")
