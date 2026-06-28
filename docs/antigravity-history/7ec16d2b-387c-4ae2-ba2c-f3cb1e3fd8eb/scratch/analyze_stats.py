import re
import numpy as np
from collections import defaultdict

log_file = "/Users/vitorhrds/Documents/Github/hypothesis-sniper-lenta/trading-engine/logs/skynet/skynet_global_DEMO.log"

# Tracking streaks
# Key: symbol, Value: current streak of wins
current_streaks = defaultdict(int)
# List of all completed streaks (ends with a loss)
completed_streaks = []

# To project EV, we need to know the payout ratio.
# Stake is 10.0, profit is ~0.96. Rate = 0.096

total_wins = 0
total_losses = 0

loss_stakes = []

win_pattern = re.compile(r"\[([^\]]+)\] ✅ WIN")
loss_pattern = re.compile(r"\[([^\]]+)\] ❌ LOSS.*Prejuízo: \$-([\d\.]+)")

with open(log_file, "r", encoding="utf-8") as f:
    for line in f:
        win_match = win_pattern.search(line)
        if win_match:
            symbol = win_match.group(1)
            current_streaks[symbol] += 1
            total_wins += 1
        
        loss_match = loss_pattern.search(line)
        if loss_match:
            symbol = loss_match.group(1)
            stake_lost = float(loss_match.group(2))
            
            # Record the streak that just ended
            streak = current_streaks[symbol]
            completed_streaks.append(streak)
            loss_stakes.append(stake_lost)
            
            # Reset streak
            current_streaks[symbol] = 0
            total_losses += 1

print("--- ANÁLISE ESTATÍSTICA DO ORÁCULO ---")
total_trades = total_wins + total_losses
win_rate = total_wins / total_trades if total_trades > 0 else 0
print(f"Total Trades: {total_trades}")
print(f"Total Wins: {total_wins}")
print(f"Total Losses: {total_losses}")
print(f"Win Rate Global: {win_rate*100:.2f}%")

print("\n--- ANÁLISE DOS LOSSES (DESVIO PADRÃO) ---")
if completed_streaks:
    avg_streak = np.mean(completed_streaks)
    std_streak = np.std(completed_streaks)
    max_streak = np.max(completed_streaks)
    min_streak = np.min(completed_streaks)
    print(f"Média de vitórias antes de um Loss: {avg_streak:.2f} wins")
    print(f"Desvio Padrão da sequência (Loss timing): {std_streak:.2f} wins")
    print(f"Mínimo (Loss imediato): {min_streak} wins")
    print(f"Máximo (Maior sequência quebrada): {max_streak} wins")
    
    avg_loss_stake = np.mean(loss_stakes)
    std_loss_stake = np.std(loss_stakes)
    print(f"\nTamanho Médio da Stake Perdida (Fase 1 Composta): ${avg_loss_stake:.2f}")
    print(f"Desvio Padrão da Stake Perdida: ${std_loss_stake:.2f}")
else:
    print("Nenhum loss registrado para calcular variância.")

# Projection:
# To reach $10 profit starting from $10 stake at 9.6% return, 
# Stake_n = 10 * (1.096)^n
# Profit_n = Stake_n - 10
# We need Profit_n >= 10 => Stake_n >= 20 => 10 * (1.096)^n >= 20 => 1.096^n >= 2
# n = log(2) / log(1.096) ≈ 7.56 -> 8 wins needed.
print("\n--- PROJEÇÃO MATEMÁTICA (EV) ---")
print("Para atingir Fase 2 (+$10 PnL) com Juros Compostos a 100%, são necessárias 8 Vitórias Seguidas.")
prob_8_wins = win_rate ** 8
print(f"Probabilidade de 8 vitórias seguidas (Baseado no WR atual de {win_rate*100:.2f}%): {prob_8_wins*100:.2f}%")

# Expected Value of a cycle:
# Cost of failure: Average stake lost when failing before 8 wins.
# But wait, failure costs exactly the accumulated stake at that point, which averages to 10 * (1.096)^avg_streak 
# Actually, the real risk is always the initial $10 out of pocket. The rest is accumulated profit. 
# Out of pocket EV:
# 1 cycle costs $10 from balance.
# Success returns the $10 to balance + $10 in pool (but out of pocket is Breakeven).
# Actually, EV = P(success) * (Value of Freeroll Phase) - P(fail) * $10.
# Without Freeroll value, just reaching Phase 2:
ev_breakeven = prob_8_wins * 10 - (1 - prob_8_wins) * 10
print(f"EV Projetado apenas para Atingir a Fase 2 (Ganho de $10 vs Risco Base de $10): ${ev_breakeven:.2f} por ciclo.")
