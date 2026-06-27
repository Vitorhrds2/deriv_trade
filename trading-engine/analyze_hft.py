import re

with open("hft_trades.log", "r") as f:
    logs = f.readlines()

profits = []
jumps = []
for line in logs:
    if "Lucro:" in line:
        match = re.search(r"Lucro: \$(-?\d+\.\d+)", line)
        if match:
            profits.append(float(match.group(1)))
            
    if "Salto:" in line:
        match = re.search(r"Salto: (-?\d+\.\d+) em", line)
        if match:
            jumps.append(abs(float(match.group(1))))

print(f"Total de Trades Encerrados: {len(profits)}")
if len(profits) > 0:
    print(f"Lucro Médio: ${sum(profits)/len(profits):.2f}")
    print(f"Lucro Total: ${sum(profits):.2f}")
    print(f"Salto Médio (Absoluto): ${sum(jumps)/len(jumps):.2f}")
    print(f"Maior Lucro: ${max(profits):.2f}")
    print(f"Menor Lucro: ${min(profits):.2f}")
