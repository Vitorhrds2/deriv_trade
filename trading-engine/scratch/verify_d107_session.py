import json
from collections import Counter

d = json.load(open("trading-engine/d107_rate_limit_winner_holding_state.json"))
contracts = list(d["contracts"].values())

close_reasons = Counter([c.get("close_reason") for c in contracts if c.get("lifecycle") == "closed_target"])
print("Close reasons for targets across all 186 contracts:")
for reason, count in close_reasons.most_common():
    print(f"  {reason}: {count}")

new_session = contracts[93:]
print("\n--- New session since upgrade (from trial 94 onwards) ---")
print("Total contracts in upgraded session:", len(new_session))
new_lc = Counter([c.get("lifecycle") for c in new_session])
print("Lifecycles in upgraded session:", new_lc)
new_targets = Counter([c.get("close_reason") for c in new_session if c.get("lifecycle") == "closed_target"])
print("Close reasons in upgraded session:")
for reason, count in new_targets.most_common():
    print(f"  {reason}: {count}")

pnl_realized = 0.0
for c in new_session:
    if c.get("lifecycle") == "closed_target":
        sold = float(c.get("sold_for") or 0.0)
        buy = float(c.get("buy_price") or 1.08)
        pnl_realized += (sold - buy)
    elif c.get("lifecycle") == "closed_loser":
        # Sold for 1.00 (stake), fee was lost
        fee = float(c.get("cancellation_fee") or 0.08)
        pnl_realized -= fee

print(f"Calculated Net PnL of upgraded session: +${pnl_realized:.2f} USD")
print(f"Session Realized PnL reported by bot: +${d.get('session_realized_pnl'):.2f} USD")
print(f"Total Fees Paid in session: ${d.get('cancellation_fees'):.2f} USD")
