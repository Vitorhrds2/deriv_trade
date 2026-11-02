import json
from datetime import datetime

lines = open('trading-engine/d107_rate_limit_winner_holding_results.jsonl').readlines()
events = []
for l in lines:
    if '19127889519' in l:
        events.append(json.loads(l))

records = []
for ev in events:
    ts = ev.get('timestamp')
    dt = datetime.fromisoformat(ts)
    for p in ev.get('positions', []):
        if p.get('contract_id') == '19127889519':
            records.append({
                'dt': dt,
                'ts': ts,
                'profit': p.get('profit_at_action'),
                'spot': p.get('current_spot'),
                'entry_spot': p.get('entry_spot'),
                'bid': p.get('bid_price_at_action'),
                'is_cancel': p.get('is_valid_to_cancel'),
                'is_sell': p.get('is_valid_to_sell'),
                'classification': p.get('classification')
            })

print(f"Total snapshots for 19127889519: {len(records)}")
start = records[0]
min_profit = min(records, key=lambda x: x['profit'] if x['profit'] is not None else 0)
max_profit = max(records, key=lambda x: x['profit'] if x['profit'] is not None else 0)
end = records[-1]

duration_sec = (end['dt'] - start['dt']).total_seconds()
time_to_min = (min_profit['dt'] - start['dt']).total_seconds()
time_to_max = (max_profit['dt'] - start['dt']).total_seconds()

print(f"Start: {start['ts']} | Spot: {start['spot']} | Profit: ${start['profit']:+.2f} | ValidToCancel: {start['is_cancel']}")
print(f"Max Drawdown: {min_profit['ts']} (+{time_to_min/60:.1f}m) | Spot: {min_profit['spot']} | Profit: ${min_profit['profit']:+.2f} (-{abs(min_profit['profit'])/1.10*100:.1f}%)")
print(f"Peak Profit: {max_profit['ts']} (+{time_to_max/60:.1f}m) | Spot: {max_profit['spot']} | Profit: ${max_profit['profit']:+.2f} (+{max_profit['profit']/1.10*100:.1f}%)")
print(f"End: {end['ts']} (+{duration_sec/60:.1f}m) | Spot: {end['spot']} | Profit: ${end['profit']:+.2f}")
