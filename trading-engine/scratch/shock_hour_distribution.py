import re
from collections import Counter

log_file = "hft_trades_remote.log"

# Log grava em hora LOCAL do servidor (UTC-3, confirmado pela mensagem "fora do horario de
# ouro (UTC 22:25)" batendo com timestamp local 19:25:58 do mesmo evento). Converte pra UTC
# somando 3h, pra comparar com GOLDEN_HOUR_START_UTC=12/END_UTC=18.
pattern = re.compile(r"^(\d{4}-\d{2}-\d{2})[ T](\d{2}):(\d{2}):(\d{2})[.,]\d+.*GATILHO ACIONADO! Direção: (\w+) \| Salto: ([-\d.]+)")

hours_utc = Counter()
rows = []
with open(log_file, "r") as f:
    for line in f:
        m = pattern.search(line)
        if not m:
            continue
        date, hh, mm, ss, direction, shock = m.groups()
        hour_local = int(hh)
        hour_utc = (hour_local + 3) % 24
        hours_utc[hour_utc] += 1
        rows.append((date, f"{hh}:{mm}:{ss}", hour_utc, direction, float(shock)))

print(f"Total de GATILHOs ACIONADOs no historico completo: {len(rows)}\n")
print("--- Distribuicao por hora UTC (todo o historico, antes e depois do filtro existir) ---")
for h in range(24):
    n = hours_utc.get(h, 0)
    marker = " <- dentro do Horario de Ouro (12-18 UTC)" if 12 <= h < 18 else ""
    print(f"UTC {h:02d}h: {'#' * n} ({n}){marker}")

n_in_golden = sum(n for h, n in hours_utc.items() if 12 <= h < 18)
n_total = sum(hours_utc.values())
print(f"\nGatilhos dentro do Horario de Ouro: {n_in_golden}/{n_total} ({n_in_golden/n_total*100:.1f}%)" if n_total else "sem dados")
print("(Se a janela 12-18 UTC fosse aleatoria/sem relacao com a distribuicao real, esperar-se-ia ~25% = 6/24h)")

print("\n--- Todos os gatilhos (data, hora local, hora UTC, direcao, salto) ---")
for r in rows:
    print(r)
