"""
Auditoria estatistica retroativa do hft_arbitrage_bot (V4.0 -> V6.2).

Fase 1 do Mega Brain 2.0: aplica o MESMO crivo estatistico que reprovou H1/H3/T4
(Wilson CI no win rate, bootstrap CI no EV/trade) em cima das trades fechadas ja
executadas pelo hft_bot (conta demo), agrupadas por versao/parametro.

Fontes: todos os hft_trades*.log (consolidados e deduplicados por contract_id).
Opcionalmente exporta JSONL/JSON para virar execution ledger auditavel.
"""
import argparse
import glob
import json
import os
import re
from datetime import datetime, timezone

from stats_utils import bootstrap_diff_ci, summarize

LOG_DIR = os.path.dirname(os.path.abspath(__file__))

VERSION_RE = re.compile(r"INICIANDO BOT HFT - ARBITRAGEM.*?(?: \((.+?)\))?$")
ACCOUNT_RE = re.compile(r"Found (Demo|Real) account: ([A-Z0-9]+)")

# Dire[^:]* aceita tanto logs UTF-8 corretos ("Direcao"/"Direção") quanto mojibake
# ("DireÃ§Ã£o"). MULTUP/MULTDOWN cobre uma versao intermediaria em que direction foi
# sobrescrito antes do log.
TRIGGER_RE = re.compile(
    r"GATILHO ACIONADO! Dire[^:]*: (UP|DOWN|MULTUP|MULTDOWN)"
    r"(?: \| Grupo: (ALIGNED|ANTI))?"
    r"(?: \| Ordem: (\w+))?"
    r" \| Salto: (-?[\d.]+) em (\d+)ms"
)
ORDER_OK_RE = re.compile(
    r"ORDEM EXECUTADA! ID: (\d+) \| Execution Time: (\d+)ms"
    r"(?: \| Stake: \$(-?[\d.]+))?"
)
ORDER_REJECTED_RE = re.compile(r"Ordem rejeitada: (.+)")
CLOSE_RE = re.compile(
    r"TRADE ENCERRADO(?: AUTOMATICAMENTE)?! "
    r"(?:Retorno: \$(-?[\d.]+) \| )?"
    r"Lucro: \$(-?[\d.]+) \| Dire[^:]*: (UP|DOWN|MULTUP|MULTDOWN)"
    r"(?: \| Grupo: (ALIGNED|ANTI))?"
)
CLOSE_REASON_RE = re.compile(
    r"(Take Profit Atingido|Stop Loss.*?Atingido|Timeout Atingido|"
    r"Gatilho de Fechamento Atingido|Rede de seguran..a acionada)"
)
TS_RE = re.compile(r"^(\d{4}-\d{2}-\d{2}[ T][\d:.]+)")


def normalize_direction(raw):
    if raw in ("UP", "MULTUP"):
        return "UP"
    if raw in ("DOWN", "MULTDOWN"):
        return "DOWN"
    return raw


def ts_from_line(line):
    ts_m = TS_RE.search(line)
    return ts_m.group(1) if ts_m else None


def parse_log(path):
    """Retorna (trades, rejects, sessions) extraidos de um arquivo de log HFT."""
    trades = []
    rejects = []
    sessions = []
    current_version = "V4.0 (desconhecida)"
    current_account_type = None
    current_account_id = None
    pending = None

    with open(path, "r", errors="ignore") as f:
        for line in f:
            vm = VERSION_RE.search(line)
            if vm:
                current_version = vm.group(1) or "V4.0"
                continue

            am = ACCOUNT_RE.search(line)
            if am:
                current_account_type = am.group(1).lower()
                current_account_id = am.group(2)
                sessions.append({
                    "ts": ts_from_line(line),
                    "account_type": current_account_type,
                    "account_id": current_account_id,
                    "version": current_version,
                    "log_file": os.path.basename(path),
                })
                continue

            tm = TRIGGER_RE.search(line)
            if tm:
                raw_direction = tm.group(1)
                pending = {
                    "version": current_version,
                    "ts": ts_from_line(line),
                    "direction": normalize_direction(raw_direction),
                    "direction_raw": raw_direction,
                    "group": tm.group(2) or "ALIGNED",
                    "order_type": tm.group(3),
                    "jump": float(tm.group(4)),
                    "formation_ms": int(tm.group(5)),
                    "exec_ms": None,
                    "contract_id": None,
                    "stake": None,
                    "close_reason": None,
                    "profit": None,
                    "account_type": current_account_type,
                    "account_id": current_account_id,
                    "log_file": os.path.basename(path),
                }
                continue

            om = ORDER_OK_RE.search(line)
            if om and pending is not None:
                pending["contract_id"] = om.group(1)
                pending["exec_ms"] = int(om.group(2))
                if om.group(3):
                    pending["stake"] = float(om.group(3))
                continue

            rm = ORDER_REJECTED_RE.search(line)
            if rm and pending is not None:
                pending["status"] = "rejected"
                pending["reject_reason"] = rm.group(1)
                rejects.append(pending)
                pending = None
                continue

            crm = CLOSE_REASON_RE.search(line)
            if crm and pending is not None:
                pending["close_reason"] = crm.group(1)
                continue

            cm = CLOSE_RE.search(line)
            if cm and pending is not None:
                pending["profit"] = float(cm.group(2))
                pending["close_direction_raw"] = cm.group(3)
                pending["close_direction"] = normalize_direction(cm.group(3))
                if cm.group(4):
                    pending["group"] = cm.group(4)
                if pending["contract_id"] is not None:
                    pending["status"] = "closed"
                    trades.append(pending)
                pending = None
                continue

    return trades, rejects, sessions


def load_events(log_dir):
    all_trades = {}
    all_rejects = []
    all_sessions = []
    files = sorted(glob.glob(os.path.join(log_dir, "hft_trades*.log")))

    for path in files:
        trades, rejects, sessions = parse_log(path)
        for trade in trades:
            all_trades[trade["contract_id"]] = trade
        all_rejects.extend(rejects)
        all_sessions.extend(sessions)

    trades = sorted(all_trades.values(), key=lambda t: t["ts"] or "")
    rejects = sorted(all_rejects, key=lambda t: t["ts"] or "")
    sessions = sorted(all_sessions, key=lambda s: s["ts"] or "")
    return files, trades, rejects, sessions


def write_jsonl(path, events):
    with open(path, "w", encoding="utf-8") as f:
        for event in events:
            f.write(json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n")


def count_by(items, key):
    out = {}
    for item in items:
        value = item.get(key) or "unknown"
        out[value] = out.get(value, 0) + 1
    return out


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Audita logs do hft_arbitrage_bot e exporta ledger estruturado."
    )
    parser.add_argument("--log-dir", default=LOG_DIR, help="Diretorio com hft_trades*.log")
    parser.add_argument("--ledger-jsonl", help="Caminho para exportar eventos closed/rejected em JSONL")
    parser.add_argument("--summary-json", help="Caminho para exportar resumo estatistico em JSON")
    args = parser.parse_args(argv)

    files, trades, rejects, sessions = load_events(args.log_dir)
    print(f"Arquivos de log encontrados: {[os.path.basename(f) for f in files]}")
    print(f"\nTotal de trades fechadas unicas (deduplicadas por contract_id): {len(trades)}")
    print(f"Ordens rejeitadas: {len(rejects)}")
    if sessions:
        print(f"Sessoes autenticadas por tipo de conta: {count_by(sessions, 'account_type')}\n")

    print(
        f"{'Timestamp':<28} {'Versao':<45} {'Conta':<7} {'Grupo':<7} "
        f"{'Dir':<5} {'Jump':>8} {'Exec(ms)':>9} {'Fecho':<30} {'Lucro':>8}"
    )
    for t in trades:
        print(
            f"{str(t['ts']):<28} {t['version']:<45} "
            f"{str(t.get('account_type')):<7} {t.get('group', ''):<7} "
            f"{t['direction']:<5} {t['jump']:>8.2f} {str(t['exec_ms']):>9} "
            f"{str(t['close_reason']):<30} {t['profit']:>8.2f}"
        )

    by_version = {}
    for trade in trades:
        by_version.setdefault(trade["version"], []).append(trade)

    print("\n" + "=" * 70)
    print("RESUMO ESTATISTICO POR VERSAO (Wilson CI + bootstrap CI)")
    print("=" * 70)
    results = []
    for version, version_trades in by_version.items():
        profits = [trade["profit"] for trade in version_trades]
        results.append(summarize(version, profits))

    all_profits = [trade["profit"] for trade in trades]
    overall = summarize("TODAS AS VERSOES (V4-V6.2 combinadas)", all_profits)

    v6_profits = [trade["profit"] for trade in trades if trade["version"].startswith("V6")]
    if v6_profits:
        summarize("Apenas V6.x (Momentum Rider + Ultra-Momentum)", v6_profits)

    proof_v62 = [trade for trade in trades if abs(trade["jump"]) < 50.0]
    if proof_v62:
        cutover_ts = min(trade["ts"] for trade in proof_v62)
        v62_equiv = [trade for trade in trades if trade["ts"] and trade["ts"] >= cutover_ts]
        print("\n[Rotulagem por banner e ambigua entre versoes V6.x -- ver nota no codigo]")
        print(f"Corte empirico (1a trade so possivel com threshold=45): {cutover_ts}")
        summarize(
            f"V6.2-equivalente por parametro (threshold=45, N={len(v62_equiv)}, desde {cutover_ts})",
            [trade["profit"] for trade in v62_equiv],
        )

    aligned_profits = [trade["profit"] for trade in trades if trade.get("group", "ALIGNED") == "ALIGNED"]
    anti_profits = [trade["profit"] for trade in trades if trade.get("group") == "ANTI"]

    print("\n" + "=" * 70)
    print("SHADOW A/B - ALIGNED vs ANTI (controle nulo ao vivo)")
    print("=" * 70)
    shadow_ab = {
        "aligned_n": len(aligned_profits),
        "anti_n": len(anti_profits),
    }
    if anti_profits:
        aligned_summary = summarize(f"ALIGNED (N={len(aligned_profits)})", aligned_profits)
        anti_summary = summarize(f"ANTI (N={len(anti_profits)})", anti_profits)
        diff_lo, diff_point, diff_hi = bootstrap_diff_ci(aligned_profits, anti_profits)
        shadow_ab.update({
            "aligned": aligned_summary,
            "anti": anti_summary,
            "diff_point": diff_point,
            "diff_ci": [diff_lo, diff_hi],
        })
        print(f"\nDiferenca EV(ALIGNED) - EV(ANTI) = ${diff_point:.4f}  IC95% [${diff_lo:.4f}, ${diff_hi:.4f}]")
        if diff_lo <= 0 <= diff_hi:
            print("-> IC cruza zero: SEM diferenca estatistica entre seguir e ir contra o choque.")
            print("   Consistente com problema estrutural de execucao/latencia, nao direcao do sinal.")
        elif diff_point > 0:
            print("-> ALIGNED estatisticamente melhor que ANTI: ha sinal direcional real.")
        else:
            print("-> ANTI estatisticamente melhor que ALIGNED: o choque tende a reverter.")
    else:
        print("Nenhuma trade com grupo ANTI ainda encontrada nos logs (shadow A/B recem-ativado).")
        print(f"Amostra atual: {len(aligned_profits)} ALIGNED / 0 ANTI. Precisa rodar mais tempo")
        print("ao vivo (ver docs/hft_v62_audit_report.md) para acumular N em ambos os grupos.")

    ledger_events = []
    for trade in trades:
        event = dict(trade)
        event["event_type"] = "trade_closed"
        ledger_events.append(event)
    for reject in rejects:
        event = dict(reject)
        event["event_type"] = "order_rejected"
        ledger_events.append(event)
    ledger_events = sorted(ledger_events, key=lambda e: e.get("ts") or "")

    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "log_dir": os.path.abspath(args.log_dir),
        "files": [os.path.basename(path) for path in files],
        "sessions": sessions,
        "session_counts": count_by(sessions, "account_type"),
        "trades_total": len(trades),
        "rejects_total": len(rejects),
        "account_trade_counts": count_by(trades, "account_type"),
        "overall": overall,
        "by_version": results,
        "shadow_ab": shadow_ab,
    }

    if args.ledger_jsonl:
        write_jsonl(args.ledger_jsonl, ledger_events)
        print(f"\nLedger JSONL escrito em: {args.ledger_jsonl}")
    if args.summary_json:
        with open(args.summary_json, "w", encoding="utf-8") as f:
            json.dump(summary, f, ensure_ascii=False, indent=2, sort_keys=True)
        print(f"Resumo JSON escrito em: {args.summary_json}")

    return trades, results, overall


if __name__ == "__main__":
    main()
