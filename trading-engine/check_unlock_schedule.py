#!/usr/bin/env python3
"""Quick check of upcoming unlock schedule and bot state."""
import json, os, sys
from datetime import datetime, timezone, timedelta

sys.path.insert(0, os.path.dirname(__file__))
from unlock_short_bot import get_all_upcoming_unlocks, MIN_UNLOCK_VALUE_MM, ENTRY_DAYS, EXIT_DAYS

now = datetime.now(timezone.utc)
print(f"UTC now: {now.strftime('%Y-%m-%d %H:%M UTC')}")
print(f"Entry: {ENTRY_DAYS}d before, Exit: +{EXIT_DAYS}d after, Min: ${MIN_UNLOCK_VALUE_MM}M")
print()

upcoming = get_all_upcoming_unlocks()
print(f"Upcoming unlocks (>=${MIN_UNLOCK_VALUE_MM}M): {len(upcoming)}")
for u in upcoming[:15]:
    unlock_dt = datetime.strptime(u["unlock_date"], "%Y-%m-%d").replace(tzinfo=timezone.utc)
    days_until = (unlock_dt - now).days
    entry_date = unlock_dt + timedelta(days=ENTRY_DAYS)
    exit_date = unlock_dt + timedelta(days=EXIT_DAYS)
    print(f"  {u['unlock_date']} {u['symbol']:>10s}  ${u['unlock_value_mm']:>6.0f}M  "
          f"entry={entry_date.strftime('%Y-%m-%d')} exit={exit_date.strftime('%Y-%m-%d')} "
          f"({days_until}d until unlock)")

# Check state
state_file = os.path.join(os.path.dirname(__file__), "unlock_short_state.json")
if os.path.exists(state_file):
    with open(state_file) as f:
        state = json.load(f)
    print(f"\nState: {len(state.get('open_positions', []))} open, "
          f"{len(state.get('closed_trades', []))} closed, "
          f"last_check={state.get('last_check', 'never')}")
    for p in state.get("open_positions", []):
        try:
            from unlock_short_bot import get_current_price
            cur = get_current_price(p["symbol"])
            unrl = (p["entry_price"] - cur) * p["quantity"]
            unrl_pct = (p["entry_price"] - cur) / p["entry_price"] * 100
            print(f"  -> OPEN: {p['symbol']} SHORT @ ${p['entry_price']:.4f} | Mark=${cur:.4f} | PnL=${unrl:+.2f} ({unrl_pct:+.2f}%) | Stop=${p.get('stop_loss_price', 0):.4f} | Exit={p['unlock_date']}+3d")
        except Exception:
            print(f"  -> OPEN: {p['symbol']} SHORT @ ${p['entry_price']:.4f} | Notional=${p['notional']:.2f}")
else:
    print("\nNo state file found")

trade_file = os.path.join(os.path.dirname(__file__), "unlock_short_trades.json")
if os.path.exists(trade_file):
    with open(trade_file) as f:
        trades = json.load(f)
    print(f"Trade log: {len(trades)} trades")
    for t in trades[-5:]:
        print(f"  {t['symbol']} {t.get('close_reason','?')} pnl=${t.get('net_pnl',0):+.2f}")
