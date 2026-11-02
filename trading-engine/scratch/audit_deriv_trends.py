import json
from collections import Counter

d = json.load(open("trading-engine/d107_rate_limit_winner_holding_state.json"))
contracts = list(d["contracts"].values())
print("Total contracts in state:", len(contracts))

new_session = contracts[93:]
print("New session contracts (1HZ75V):", len(new_session))

multup = [c for c in new_session if c.get("direction") == "MULTUP"]
multdown = [c for c in new_session if c.get("direction") == "MULTDOWN"]

def pnl_of_contract(c):
    lc = c.get("lifecycle")
    if lc == "closed_target":
        return float(c.get("sold_for", 0.0) or 0.0) - float(c.get("buy_price", 0.0) or 1.08)
    elif lc == "closed_loser":
        return -float(c.get("cancellation_fee", 0.0) or 0.08)
    elif lc == "closed_unresolved_loss":
        return float(c.get("sold_for", 0.0) or 0.0) - float(c.get("buy_price", 0.0) or 1.08)
    return 0.0

up_pnls = [pnl_of_contract(c) for c in multup]
down_pnls = [pnl_of_contract(c) for c in multdown]

print(f"MULTUP count: {len(multup)} | Net PnL: ${sum(up_pnls):+.2f} USD | Wins: {sum(1 for p in up_pnls if p > 0)} / {len(multup)}")
print(f"MULTDOWN count: {len(multdown)} | Net PnL: ${sum(down_pnls):+.2f} USD | Wins: {sum(1 for p in down_pnls if p > 0)} / {len(multdown)}")

# Check sequence of directions: was it alternating or following trend?
dirs = [c.get("direction") for c in new_session]
print(f"First 20 directions: {dirs[:20]}")

# Look at average win vs average loss
wins = [pnl_of_contract(c) for c in new_session if pnl_of_contract(c) > 0]
losses = [pnl_of_contract(c) for c in new_session if pnl_of_contract(c) < 0]

print(f"Total Wins: {len(wins)} | Avg Win: +${sum(wins)/max(1, len(wins)):.4f} USD | Total Win $: +${sum(wins):.2f}")
print(f"Total Losses: {len(losses)} | Avg Loss: ${sum(losses)/max(1, len(losses)):.4f} USD | Total Loss $: ${sum(losses):.2f}")
print(f"Net Profit of new session: +${sum(wins) + sum(losses):.2f} USD")

# Look at distribution of hold times and exit prices
print("\nSample of last 10 contracts:")
for c in new_session[-10:]:
    cid = c.get("contract_id")
    direction = c.get("direction")
    lc = c.get("lifecycle")
    cr = c.get("close_reason")
    sold = c.get("sold_for")
    pnl = pnl_of_contract(c)
    peak = c.get("peak_unrealized_pnl")
    print(f"  ID: {cid} | {direction} | LC: {lc} | Reason: {cr} | Sold: {sold} | Peak: {peak} | PnL: ${pnl:+.2f}")
