import re

log_file = "hft_trades_remote_today.log"
start_parsing = False
pnl = 0.0
trades = 0
wins = 0
losses = 0
trade_list = []

with open(log_file, "r") as f:
    for line in f:
        # Pega a inicializacao de hoje apos 2026-06-30 10:00:00 (onde apliquei a blindagem imortal e o novo RR 60/35)
        # O restart deve ter ocorrido depois disso
        if "INICIANDO BOT HFT - ARBITRAGEM SINTÉTICA (V6.0 Momentum Rider)" in line and "2026-06-30" in line:
            # So vamos resetar se for o restart correto (depois das 10h UTC).
            # Mas como o horario no log pode estar em UTC, vamos checar a string:
            match_time = re.search(r'2026-06-30 (\d{2}):', line)
            if match_time and int(match_time.group(1)) >= 10:
                start_parsing = True
                pnl = 0.0
                trades = 0
                wins = 0
                losses = 0
                trade_list = []
            
        if not start_parsing:
            continue
            
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

print("--- ÚLTIMAS 10 TRADES DE HOJE ---")
for t in trade_list[-10:]:
    print(t)
    
print("\n--- RESUMO DO DIA (V6.1) ---")
print(f"Total Trades: {trades}")
print(f"Wins: {wins}")
print(f"Losses: {losses}")
if trades > 0:
    print(f"Win Rate: {(wins/trades)*100:.2f}%")
print(f"Total PnL: ${pnl:.2f}")
