import random

SIMULATIONS = 100000
STARTING_BANKROLL = 12.0
BASE_STAKE = 1.0
PAYOUT_MULTIPLIER = 0.099 # Lucro de 9.9%
MARTINGALE_MULTIPLIER = 11.0

# A verdadeira taxa de vitória do contrato DIGITDIFF. 
# Embora nosso oráculo tenha achado "96%" no passado, aquilo era ruído estatístico (variância).
# No futuro, a probabilidade sempre regride para a média matemática perfeita de 90%.
TRUE_WIN_RATE = 0.90 

def run_simulation():
    bankroll = STARTING_BANKROLL
    stake = BASE_STAKE
    trades = 0
    
    while bankroll >= stake and trades < 1000:
        trades += 1
        
        # Sorteio do resultado baseado na probabilidade real
        if random.random() < TRUE_WIN_RATE:
            # WIN
            profit = stake * PAYOUT_MULTIPLIER
            bankroll += profit
            
            # Juros compostos simulados igual ao bot
            nova_base = max(1.0, min(10.0, int(bankroll / 11.0)))
            stake = nova_base
        else:
            # LOSS
            bankroll -= stake
            stake *= MARTINGALE_MULTIPLIER
            
    # Retorna True se a banca quebrou antes de 1000 trades
    return bankroll < stake

busted_count = 0
for _ in range(SIMULATIONS):
    if run_simulation():
        busted_count += 1

busted_probability = (busted_count / SIMULATIONS) * 100

print("="*50)
print(f"ANÁLISE DE RISCO DE RUÍNA (MONTE CARLO - {SIMULATIONS} Simulações)")
print("="*50)
print(f"Banca Inicial: ${STARTING_BANKROLL:.2f}")
print(f"Win Rate Real (Regressão à Média): {TRUE_WIN_RATE*100}%")
print(f"Martingale: {MARTINGALE_MULTIPLIER}x")
print("-" * 50)
print(f"CHANCE DE QUEBRAR A BANCA: {busted_probability:.2f}%")
print("="*50)

if busted_probability > 90:
    print("CONCLUSÃO MATEMÁTICA: Estratégia fatal. A quebra não é uma questão de 'SE', mas de 'QUANDO'.")
