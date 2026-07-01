"""
Auditoria estatistica retroativa do hft_arbitrage_bot (V4.0 -> V6.2).

Fase 1 do Mega Brain 2.0: aplica o MESMO crivo estatistico que reprovou H1/H3/T4
(Wilson CI no win rate, bootstrap CI no EV/trade) em cima das trades REAIS ja
executadas pelo hft_bot (conta demo), agrupadas por versao/parametro. Isso nunca
tinha sido feito -- o bot foi calibrado manualmente, nao passou pelo mesmo gate.

Fontes: todos os hft_trades*.log (consolidados e deduplicados por contract_id).
"""
import glob
import re
import os
from stats_utils import summarize, wilson_ci, bootstrap_diff_ci

LOG_DIR = os.path.dirname(os.path.abspath(__file__))

VERSION_RE = re.compile(r"INICIANDO BOT HFT - ARBITRAGEM (?:DE LATÊNCIA|SINTÉTICA)(?: \((.+?)\))?")
# Grupo (ALIGNED/ANTI) e opcional -- logs anteriores ao shadow A/B (2026-07-01) nao tem esse
# campo, e nesse caso o grupo e implicitamente ALIGNED (bot so testava a direcao do choque).
TRIGGER_RE = re.compile(r"GATILHO ACIONADO! Direção: (UP|DOWN)(?: \| Grupo: (ALIGNED|ANTI))?(?: \| Ordem: \w+)? \| Salto: (-?[\d.]+) em (\d+)ms")
ORDER_OK_RE = re.compile(r"ORDEM EXECUTADA! ID: (\d+) \| Execution Time: (\d+)ms")
ORDER_REJECTED_RE = re.compile(r"Ordem rejeitada: (.+)")
CLOSE_RE = re.compile(r"TRADE ENCERRADO(?: AUTOMATICAMENTE)?! (?:Retorno: \$(-?[\d.]+) \| )?Lucro: \$(-?[\d.]+) \| Direção: (UP|DOWN)(?: \| Grupo: (ALIGNED|ANTI))?")
CLOSE_REASON_RE = re.compile(r"(Take Profit Atingido|Stop Loss.*?Atingido|Timeout Atingido|Gatilho de Fechamento Atingido|Rede de segurança acionada)")
TS_RE = re.compile(r"^(\d{4}-\d{2}-\d{2}[ T][\d:.]+)")


def parse_log(path):
    """Retorna lista de trades: {version, ts, direction, jump, formation_ms, exec_ms, contract_id, close_reason, profit}."""
    trades = []
    current_version = "V4.0 (desconhecida)"
    pending = None  # trade sendo construida

    with open(path, "r", errors="ignore") as f:
        for line in f:
            vm = VERSION_RE.search(line)
            if vm:
                current_version = vm.group(1) or "V4.0"
                continue

            tm = TRIGGER_RE.search(line)
            if tm:
                ts_m = TS_RE.search(line)
                pending = {
                    "version": current_version,
                    "ts": ts_m.group(1) if ts_m else None,
                    "direction": tm.group(1),
                    "group": tm.group(2) or "ALIGNED",
                    "jump": float(tm.group(3)),
                    "formation_ms": int(tm.group(4)),
                    "exec_ms": None,
                    "contract_id": None,
                    "close_reason": None,
                    "profit": None,
                }
                continue

            om = ORDER_OK_RE.search(line)
            if om and pending is not None:
                pending["contract_id"] = om.group(1)
                pending["exec_ms"] = int(om.group(2))
                continue

            rm = ORDER_REJECTED_RE.search(line)
            if rm and pending is not None:
                # ordem rejeitada -> descarta o pending (nunca virou trade real)
                pending = None
                continue

            crm = CLOSE_REASON_RE.search(line)
            if crm and pending is not None:
                pending["close_reason"] = crm.group(1)
                continue

            cm = CLOSE_RE.search(line)
            if cm and pending is not None:
                pending["profit"] = float(cm.group(2))
                if cm.group(4):
                    pending["group"] = cm.group(4)
                if pending["contract_id"] is not None:
                    trades.append(pending)
                pending = None
                continue

    return trades


def main():
    all_trades = {}  # contract_id -> trade (dedupe entre arquivos sobrepostos)
    files = sorted(glob.glob(os.path.join(LOG_DIR, "hft_trades*.log")))
    print(f"Arquivos de log encontrados: {[os.path.basename(f) for f in files]}")

    for path in files:
        for t in parse_log(path):
            all_trades[t["contract_id"]] = t  # ultima ocorrencia vence (arquivos mais novos por ultimo, ordem alfabetica ja ajuda)

    trades = sorted(all_trades.values(), key=lambda t: t["ts"] or "")
    print(f"\nTotal de trades REAIS unicas (deduplicadas por contract_id): {len(trades)}\n")

    print(f"{'Timestamp':<28} {'Versao':<45} {'Dir':<5} {'Jump':>8} {'Exec(ms)':>9} {'Fecho':<30} {'Lucro':>8}")
    for t in trades:
        print(f"{str(t['ts']):<28} {t['version']:<45} {t['direction']:<5} {t['jump']:>8.2f} "
              f"{str(t['exec_ms']):>9} {str(t['close_reason']):<30} {t['profit']:>8.2f}")

    # Agrupar por versao
    by_version = {}
    for t in trades:
        by_version.setdefault(t["version"], []).append(t)

    print("\n" + "=" * 70)
    print("RESUMO ESTATISTICO POR VERSAO (Wilson CI + bootstrap CI)")
    print("=" * 70)
    results = []
    for version, ts in by_version.items():
        profits = [t["profit"] for t in ts]
        results.append(summarize(version, profits))

    all_profits = [t["profit"] for t in trades]
    overall = summarize("TODAS AS VERSOES (V4-V6.2 combinadas)", all_profits)

    # Subset so V6.x (momentum rider em diante) - a familia de parametro mais proxima do que roda hoje
    v6_profits = [t["profit"] for t in trades if t["version"].startswith("V6")]
    if v6_profits:
        summarize("Apenas V6.x (Momentum Rider + Ultra-Momentum)", v6_profits)

    # CAVEAT DE ROTULAGEM: o banner "INICIANDO BOT HFT (Vx.y)" so e reimpresso quando o
    # PROCESSO reinicia. Entre 06-30 e 07-01 o codigo foi atualizado (threshold 50->45) sem
    # um restart imediato que reimprimisse o banner -- todas essas trades ficaram rotuladas
    # "V6.0 Momentum Rider" mesmo com o parametro V6.2 (threshold 45) ja ativo. Isolamos essas
    # trades pelo unico jeito confiavel: |jump| < 50 SO e possivel com threshold=45 (prova
    # empirica de que o V6.2 ja estava rodando), e usamos o timestamp da primeira ocorrencia
    # como corte para incluir tambem as trades >=50 que vieram depois dela na mesma janela.
    proof_v62 = [t for t in trades if abs(t["jump"]) < 50.0]
    if proof_v62:
        cutover_ts = min(t["ts"] for t in proof_v62)
        v62_equiv = [t for t in trades if t["ts"] and t["ts"] >= cutover_ts]
        print(f"\n[Rotulagem por banner e ambigua entre versoes V6.x -- ver nota no codigo]")
        print(f"Corte empirico (1a trade so possivel com threshold=45): {cutover_ts}")
        summarize(f"V6.2-equivalente por parametro (threshold=45, N={len(v62_equiv)}, desde {cutover_ts})",
                   [t["profit"] for t in v62_equiv])

    # Shadow A/B (ativo desde 2026-07-01 em hft_arbitrage_bot.py): cada gatilho sorteia 50/50
    # entre ALIGNED (segue o choque, comportamento historico) e ANTI (controle nulo, contra o
    # choque). Trades anteriores a essa data ficam 100% em ALIGNED por definicao (parse_log usa
    # esse default quando o log nao tem o campo "Grupo").
    aligned_profits = [t["profit"] for t in trades if t.get("group", "ALIGNED") == "ALIGNED"]
    anti_profits = [t["profit"] for t in trades if t.get("group") == "ANTI"]

    print("\n" + "=" * 70)
    print("SHADOW A/B — ALIGNED vs ANTI (controle nulo ao vivo)")
    print("=" * 70)
    if anti_profits:
        summarize(f"ALIGNED (N={len(aligned_profits)})", aligned_profits)
        summarize(f"ANTI (N={len(anti_profits)})", anti_profits)
        diff_lo, diff_point, diff_hi = bootstrap_diff_ci(aligned_profits, anti_profits)
        print(f"\nDiferenca EV(ALIGNED) - EV(ANTI) = ${diff_point:.4f}  IC95% [${diff_lo:.4f}, ${diff_hi:.4f}]")
        if diff_lo <= 0 <= diff_hi:
            print("-> IC cruza zero: SEM diferenca estatistica entre seguir e ir contra o choque.")
            print("   Consistente com a hipotese de que o problema e estrutural (latencia de")
            print("   execucao, ja confirmado por H3), nao a direcao do sinal.")
        elif diff_point > 0:
            print("-> ALIGNED estatisticamente melhor que ANTI: ha sinal direcional real, o")
            print("   gargalo (se houver) e so de execucao/timing, nao de escolha de direcao.")
        else:
            print("-> ANTI estatisticamente melhor que ALIGNED: o choque tende a reverter, nao")
            print("   continuar -- inverteria a logica atual do bot (momentum -> mean reversion).")
    else:
        print("Nenhuma trade com grupo ANTI ainda encontrada nos logs (shadow A/B recem-ativado).")
        print(f"Amostra atual: {len(aligned_profits)} ALIGNED / 0 ANTI. Precisa rodar mais tempo")
        print("ao vivo (ver docs/hft_v62_audit_report.md) para acumular N em ambos os grupos.")

    return trades, results, overall


if __name__ == "__main__":
    main()
