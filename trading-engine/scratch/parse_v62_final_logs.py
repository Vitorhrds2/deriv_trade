import re

log_file = "hft_trades_remote.log"
VERSION_MARK = "V6.2 Ultra-Momentum + Filtro de Velocidade + Horário de Ouro"

with open(log_file, "r") as f:
    lines = f.readlines()

# Acha a PRIMEIRA ocorrencia da versao final (SAFETY_TIMEOUT=1800 + golden hour) -- restarts
# subsequentes com o MESMO banner sao a mesma config, so reconexao apos WS cair.
start_idx = None
for i, line in enumerate(lines):
    if VERSION_MARK in line:
        start_idx = i
        break

if start_idx is None:
    print(f"Marca de versao '{VERSION_MARK}' nao encontrada.")
    raise SystemExit(1)

print(f"Inicio da amostra V6.2 final: linha {start_idx + 1} -> {lines[start_idx].strip()}\n")

trades = []
restarts = 0
for line in lines[start_idx:]:
    if VERSION_MARK in line:
        restarts += 1
    m_auto = re.search(r"([\d\-: T.]+) - HFT_SNIPER:INFO:.*TRADE ENCERRADO AUTOMATICAMENTE! Lucro: \$\s*([-\d.]+) \| Direção: (\w+)", line)
    m_forced = re.search(r"([\d\-: T.]+) - HFT_SNIPER:INFO:.*TRADE ENCERRADO! Retorno: \$[-\d.]+ \| Lucro: \$\s*([-\d.]+) \| Direção: (\w+)", line)
    if m_auto:
        trades.append({"ts": m_auto.group(1).strip(), "profit": float(m_auto.group(2)), "dir": m_auto.group(3), "auto": True})
    elif m_forced:
        trades.append({"ts": m_forced.group(1).strip(), "profit": float(m_forced.group(2)), "dir": m_forced.group(3), "auto": False})

print(f"Numero de (re)starts com a mesma versao final: {restarts}")
print(f"Total de trades: {len(trades)}\n")

for t in trades:
    tag = "AUTO(SL/TP nativo)" if t["auto"] else "FORCADO(timeout 30min)"
    print(f"{t['ts']} | {t['dir']:5s} | Lucro: ${t['profit']:+.2f} | {tag}")

n = len(trades)
wins = sum(1 for t in trades if t["profit"] > 0)
losses = n - wins
pnl = sum(t["profit"] for t in trades)
n_auto = sum(1 for t in trades if t["auto"])
n_forced = n - n_auto

print("\n--- RESUMO (V6.2 final: SAFETY_TIMEOUT=1800s + Horario de Ouro) ---")
print(f"Total Trades: {n}")
if n:
    print(f"Wins: {wins} | Losses: {losses} | Win Rate: {wins/n*100:.2f}%")
    print(f"Fechamento automatico (SL/TP nativo): {n_auto} ({n_auto/n*100:.1f}%)")
    print(f"Fechamento forcado (rede de seguranca 30min): {n_forced} ({n_forced/n*100:.1f}%)")
print(f"Total PnL: ${pnl:.2f}")
