import json

trades = [json.loads(line) for line in open('touch_anomaly_trades.jsonl')]
print(f"Total Live Trades Executed: {len(trades)}")
wins = sum(1 for t in trades if t['result'] == 'won')
wr = wins / len(trades) * 100
total_pnl = sum(t.get('profit', 0) for t in trades)
total_volume = sum(t.get('stake', 0) for t in trades)

print(f"Overall Record: {wins} Wins / {len(trades) - wins} Losses ({wr:.1f}% Win Rate)")
print(f"Total Capital Volume Deployed: ${total_volume:.2f}")
print(f"Total Realized PnL: ${total_pnl:+.2f}")

exp1 = trades[:10]   # 10 trades alternate (2m, stake 2.0)
exp2 = trades[10:40] # 30 trades parallel (2m, stake 5.0)
exp3 = trades[40:50] # 10 trades RDBEAR 3m (3m, stake 5.0)
exp4 = trades[50:60] # 10 trades RDBEAR 5m (5m, stake 5.0)

def print_exp(sub, label):
    w = sum(1 for t in sub if t['result'] == 'won')
    n = len(sub)
    r = w / n * 100 if n > 0 else 0
    p = sum(t.get('profit', 0) for t in sub)
    vol = sum(t.get('stake', 0) for t in sub)
    print(f"\n--- {label} (N={n}) ---")
    print(f"  Wins: {w}/{n} ({r:.1f}%) | PnL: ${p:+.2f} | Volume: ${vol:.2f} | ROI: {p/vol*100:+.1f}%")

print_exp(exp1, "Bateria 1: Alternada 2m ($2 stake)")
print_exp(exp2, "Bateria 2: Paralela 2m ($5 stake)")
print_exp(exp3, "Bateria 3: RDBEAR 3m Calibrada ($5 stake)")
print_exp(exp4, "Bateria 4: RDBEAR 5m Otimizada ($5 stake)")
