import json

lines = open('trading-engine/d107_rate_limit_winner_holding_results.jsonl').readlines()
trials = {}
for l in lines:
    try:
        obj = json.loads(l)
    except Exception:
        continue
    t = obj.get('trial')
    if t and 256 <= t <= 316:
        if t not in trials:
            trials[t] = []
        trials[t].append(obj)

print(f"Trials in range 256-316: {len(trials)}")
up_count = 0
down_count = 0
for t in sorted(trials.keys()):
    evs = trials[t]
    buy = next((e for e in evs if e.get('event') == 'buy_confirmed'), None)
    sell = next((e for e in evs if e.get('event') == 'sell_confirmed'), None)
    cancel = next((e for e in evs if e.get('event') == 'cancel_confirmed'), None)
    direction = buy.get('direction') if buy else 'UNK'
    sym = buy.get('symbol') if buy else 'UNK'
    if direction == 'MULTUP': up_count += 1
    elif direction == 'MULTDOWN': down_count += 1
    
    if sell:
        cr = sell.get('close_reason') or 'unknown'
        pnl = sell.get('realized_pnl') or 0.0
        entry = sell.get('entry_spot')
        exit_s = sell.get('current_spot')
        print(f"Trial {t:3d}: {sym:7s} {direction:8s} | SOLD {cr:30s} | Entry {entry} -> Exit {exit_s} | PnL ${pnl:+.2f}")
    elif cancel:
        fee = cancel.get('cancellation_fee') or 0.0
        entry = cancel.get('entry_spot')
        exit_s = cancel.get('current_spot')
        diff = (exit_s - entry) if (exit_s and entry) else 0.0
        print(f"Trial {t:3d}: {sym:7s} {direction:8s} | CANCEL fee ${fee:.2f} | Entry {entry} -> Exit {exit_s} (diff {diff:+.2f})")
    else:
        print(f"Trial {t:3d}: {sym:7s} {direction:8s} | Open/Unresolved")

print(f"\nSummary in range 256-316: MULTUP={up_count}, MULTDOWN={down_count}")
