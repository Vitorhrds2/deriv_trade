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

micro_wins = []
for t, evs in sorted(trials.items()):
    sell = next((e for e in evs if e.get('event') == 'sell_confirmed'), None)
    if sell:
        pnl = sell.get('realized_pnl', 0.0)
        cr = sell.get('close_reason', '')
        if 0.10 <= pnl <= 0.30:
            buy = next((e for e in evs if e.get('event') == 'buy_confirmed'), None)
            direction = buy.get('direction') if buy else 'UNK'
            sym = buy.get('symbol') if buy else 'UNK'
            # calculate hold duration
            t_buy = buy.get('timestamp') if buy else None
            t_sell = sell.get('timestamp') if sell else None
            micro_wins.append({
                'trial': t,
                'sym': sym,
                'direction': direction,
                'pnl': pnl,
                'reason': cr,
                'entry': sell.get('entry_spot'),
                'exit': sell.get('current_spot'),
                't_buy': t_buy,
                't_sell': t_sell
            })

print(f"Total micro-profit wins (0.10 - 0.30 USD) in Trials 256-316: {len(micro_wins)}")
for w in micro_wins:
    print(f"Trial {w['trial']}: {w['sym']} {w['direction']} | PnL ${w['pnl']:+.2f} | Reason: {w['reason']} | Entry {w['entry']} -> Exit {w['exit']}")
