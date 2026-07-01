import re

log_file = "hft_trades_v62.log"
start_parsing = False
pnl = 0.0
trades = 0
wins = 0
losses = 0
trade_list = []

with open(log_file, "r") as f:
    for line in f:
        # Pega a inicializacao da V6.2 (que tem o RR 80/25 e Threshold 45) ocorrida em 2026-06-30 por volta das 18:08 UTC
        if "INICIANDO BOT HFT - ARBITRAGEM SINTÉTICA" in line:
            # So vamos resetar se for o restart correto. 
            # Como a aws pode estar em UTC, o restart foi às 21:08 UTC ou 18:08 local. Vamos checar se tem 18:08 ou 21:08.
            # actually let's just use the last occurrence of the startup string.
            pass
            
with open(log_file, "r") as f:
    lines = f.readlines()

# Find the LAST initialization
start_idx = 0
for i, line in enumerate(lines):
    if "INICIANDO BOT HFT - ARBITRAGEM SINTÉTICA (V6.0 Momentum Rider)" in line:
        start_idx = i

for line in lines[start_idx:]:
    if "TRADE ENCERRADO" in line:
        trade_list.append(line.strip())
        match = re.search(r'Lucro: \$\s*([-\d.]+)', line)
        if match:
            profit = float(match.group(1))
            pnl += profit
            trades += 1
            if profit > 0:
                wins += 1
            else:
                losses += 1

print("--- TODAS AS TRADES (V6.2 Ultra-Momentum) ---")
for t in trade_list:
    print(t)
    
print("\n--- RESUMO DA SESSÃO ---")
print(f"Total Trades: {trades}")
print(f"Wins: {wins}")
print(f"Losses: {losses}")
if trades > 0:
    print(f"Win Rate: {(wins/trades)*100:.2f}%")
print(f"Total PnL: ${pnl:.2f}")
