import re

log_file = "hft_trades_remote.log"
start_parsing = False
pnl = 0.0
trades = 0
wins = 0
losses = 0

print("Trades list:")
with open(log_file, "r") as f:
    for line in f:
        if "INICIANDO BOT HFT - ARBITRAGEM SINTÉTICA (V6.0 Momentum Rider)" in line and "10:06:" in line:
            start_parsing = True
            pnl = 0.0
            trades = 0
            wins = 0
            losses = 0
            
        if not start_parsing:
            continue
            
        if "TRADE ENCERRADO" in line:
            print(line.strip())
            match = re.search(r'Lucro: \$\s*([-\d.]+)', line)
            if match:
                profit = float(match.group(1))
                pnl += profit
                trades += 1
                if profit > 0:
                    wins += 1
                else:
                    losses += 1

print("\n--- RESUMO ---")
print(f"Total Trades: {trades}")
print(f"Wins: {wins}")
print(f"Losses: {losses}")
if trades > 0:
    print(f"Win Rate: {(wins/trades)*100:.2f}%")
print(f"Total PnL: ${pnl:.2f}")
