"""Coletor PA5 — roda o A/B PAPER em janelas Up/Down consecutivas por N horas.

Objetivo: rodar 48h numa AWS (read-only, sem capital), varrendo as janelas BTC de 5/15min
e gravando, por janela, os paper-trades aligned/anti + o resultado (begin/close Binance).
No fim escreve um SUMARIO consolidado e (opcionalmente) imprime o corpo de email.

NAO opera. Resolver real = Chainlink (Binance e proxy -> basis/oraculo e risco). Usa so
APIs publicas (Gamma + CLOB + Binance REST), stdlib apenas. Sobrevive a falhas de janela
(try/except por janela) e e idempotente em append (1 linha JSONL por janela coletada).

Uso:
  python pa5_collector.py --selftest
  python pa5_collector.py --hours 48 --asset btc --horizon 5,15 --final-s 30 --min-move 8 \
      --out data/pa5/windows.jsonl --summary data/pa5/summary.json
"""
import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone

import polymarket_lag_probe as probe
from polymarket_arb_stats import boot_diff_ci, wilson_interval

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


def _now():
    return time.time()


def _iso():
    return datetime.now(timezone.utc).isoformat()


def _ensure_parent(path):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)


def append_jsonl(path, record):
    _ensure_parent(path)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def write_summary(path, summary):
    _ensure_parent(path)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)


def consolidate(jsonl_path):
    """Le todas as janelas coletadas e agrega aligned/anti no total (com IC95%)."""
    aligned, anti = [], []
    windows = 0
    if os.path.exists(jsonl_path):
        with open(jsonl_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except Exception:
                    continue
                windows += 1
                for t in rec.get("trades", []):
                    (aligned if t["tag"] == "aligned" else anti).append(t["pnl"])

    def grp(pnls):
        n = len(pnls)
        wins = sum(1 for x in pnls if x > 0)
        lo, hi = wilson_interval(wins, n) if n else (0.0, 0.0)
        return {"n": n, "wins": wins, "wr": (wins / n) if n else 0.0,
                "wr_ci": [lo, hi], "pnl_mean": (sum(pnls) / n) if n else 0.0,
                "pnl_total": sum(pnls)}

    summary = {
        "ts": _iso(), "windows_collected": windows,
        "aligned": grp(aligned), "anti": grp(anti),
    }
    if aligned and anti:
        summary["aligned_minus_anti"] = summary["aligned"]["pnl_mean"] - summary["anti"]["pnl_mean"]
        if len(aligned) >= 5 and len(anti) >= 5:
            lo, hi = boot_diff_ci(aligned, anti)
            summary["diff_ci95"] = [lo, hi]
            summary["verdict"] = ("edge_comprovado" if lo > 0 else
                                  "aligned_pior" if hi < 0 else "cruza_zero")
    return summary


def summary_text(summary):
    a, n = summary["aligned"], summary["anti"]
    lines = [
        "PA5 collector — coleta finalizada",
        f"timestamp: {summary['ts']}",
        f"janelas coletadas: {summary['windows_collected']}",
        f"aligned: n={a['n']} WR={a['wr']*100:.1f}% pnl_medio=${a['pnl_mean']:+.4f} total=${a['pnl_total']:+.2f}",
        f"anti:    n={n['n']} WR={n['wr']*100:.1f}% pnl_medio=${n['pnl_mean']:+.4f} total=${n['pnl_total']:+.2f}",
    ]
    if "aligned_minus_anti" in summary:
        lines.append(f"aligned-anti: ${summary['aligned_minus_anti']:+.4f}/trade")
    if "diff_ci95" in summary:
        lo, hi = summary["diff_ci95"]
        lines.append(f"IC95% (aligned-anti): [{lo:+.4f}, {hi:+.4f}] -> {summary.get('verdict')}")
        if a["pnl_mean"] > 0 and lo > 0:
            lines.append("VEREDITO: edge PAPER positivo e significativo. Validar basis Chainlink antes de capital.")
        else:
            lines.append("VEREDITO: sem edge liquido comprovado (mesmo padrao H1/H3: sinal real, sub-custo).")
    else:
        lines.append("VEREDITO: amostra insuficiente para conclusao A/B.")
    return "\n".join(lines)


def run(args):
    deadline = _now() + args.hours * 3600
    substrs = [f"{args.asset}-updown-{h.strip()}m" for h in args.horizon.split(",") if h.strip()]
    print(f"[{_iso()}] PA5 collector iniciado | ate {datetime.fromtimestamp(deadline, timezone.utc).isoformat()} "
          f"({args.hours}h) | alvos={substrs}")
    print(f"  out={args.out} | summary={args.summary} | final_s={args.final_s} min_move={args.min_move} "
          f"taker={args.taker_rate} fixed=${args.fixed_cost}")
    print("  read-only / PAPER (sem EIP-712). Resolver real=Chainlink; Binance=proxy.")

    done_slugs = set()
    collected = 0
    while _now() < deadline:
        # escolhe a proxima janela (entre os horizontes) que fecha com lead suficiente
        candidates = []
        for sub in substrs:
            try:
                slug, end = probe.next_window(sub, _now(), args.final_s + args.lead_s)
                if slug and slug not in done_slugs:
                    candidates.append((end.timestamp(), slug, end, sub))
            except Exception as e:
                print(f"  ! discover {sub}: {e}")
        if not candidates:
            time.sleep(5); continue
        candidates.sort()
        end_ts, slug, end, sub = candidates[0]
        # nao ultrapassar o deadline: se a janela fecha depois, encerra
        if end_ts > deadline + args.lead_s:
            print(f"[{_iso()}] proxima janela ({slug}) fecha apos o deadline -> encerrando coleta.")
            break

        print(f"[{_iso()}] coletando {slug} (fecha {end.isoformat()}, em {end_ts-_now():.0f}s)")
        try:
            rec = probe.paper_ab_window(
                slug, final_s=args.final_s, sample_s=args.sample_s, guard_s=args.guard_s,
                min_move=args.min_move, taker_rate=args.taker_rate, fixed_cost=args.fixed_cost,
                seed=args.seed, log=(print if args.verbose else (lambda *_: None)),
            )
            append_jsonl(args.out, rec)
            done_slugs.add(slug)
            collected += 1
            s = rec.get("summary", {})
            na = s.get("aligned", {}).get("n", 0)
            nn = s.get("anti", {}).get("n", 0)
            print(f"  -> {slug}: resultado={rec.get('outcome')} | trades aligned={na} anti={nn} "
                  f"| total coletadas={collected}")
        except Exception as e:
            print(f"  ! janela {slug} falhou: {e}")
            done_slugs.add(slug)
            time.sleep(2)

        # consolida o sumario a cada janela (resiliente a interrupcoes)
        try:
            write_summary(args.summary, consolidate(args.out))
        except Exception as e:
            print(f"  ! consolidate: {e}")

    summary = consolidate(args.out)
    write_summary(args.summary, summary)
    txt = summary_text(summary)
    print("\n" + "=" * 78)
    print(txt)
    print("=" * 78)
    if args.email_body:
        _ensure_parent(args.email_body)
        with open(args.email_body, "w", encoding="utf-8") as f:
            f.write(txt + "\n")
        print(f"corpo de email escrito em {args.email_body}")
    return 0


def selftest():
    print("== SELFTEST coletor PA5 (offline) ==")
    import tempfile
    d = tempfile.mkdtemp()
    p = os.path.join(d, "windows.jsonl")
    # 2 janelas sinteticas: aligned ganha mais que anti
    w1 = {"slug": "btc-updown-5m-1", "outcome": "Up", "trades": [
        {"tag": "aligned", "pnl": 0.5}, {"tag": "aligned", "pnl": 0.4},
        {"tag": "anti", "pnl": -0.5}, {"tag": "anti", "pnl": -0.4}]}
    w2 = {"slug": "btc-updown-5m-2", "outcome": "Down", "trades": [
        {"tag": "aligned", "pnl": 0.45}, {"tag": "aligned", "pnl": 0.5}, {"tag": "aligned", "pnl": 0.4},
        {"tag": "anti", "pnl": -0.45}, {"tag": "anti", "pnl": -0.5}, {"tag": "anti", "pnl": -0.4}]}
    append_jsonl(p, w1); append_jsonl(p, w2)
    s = consolidate(p)
    assert s["windows_collected"] == 2, s
    assert s["aligned"]["n"] == 5 and s["anti"]["n"] == 5, s
    assert s["aligned_minus_anti"] > 0, s
    assert "VEREDITO" in summary_text(s)
    print(f"  ok  consolida 2 janelas | aligned-anti={s['aligned_minus_anti']:+.3f}")
    print("  ok  summary_text gera corpo de email")
    print("\n2/2 checagens passaram.")
    return 0


def build_parser():
    p = argparse.ArgumentParser(description="Coletor PA5: A/B paper em janelas Up/Down por N horas (read-only).")
    p.add_argument("--selftest", action="store_true")
    p.add_argument("--hours", type=float, default=48.0, help="duracao total da coleta")
    p.add_argument("--asset", default="btc", help="prefixo do ativo (btc, eth, sol, ...)")
    p.add_argument("--horizon", default="5,15", help="horizontes em minutos, separados por virgula")
    p.add_argument("--final-s", type=float, default=30.0)
    p.add_argument("--sample-s", type=float, default=2.0)
    p.add_argument("--guard-s", type=float, default=1.0)
    p.add_argument("--lead-s", type=float, default=5.0, help="folga minima antes do fim para entrar numa janela")
    p.add_argument("--min-move", type=float, default=8.0)
    p.add_argument("--taker-rate", type=float, default=0.0)
    p.add_argument("--fixed-cost", type=float, default=0.0)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--out", default="data/pa5/windows.jsonl")
    p.add_argument("--summary", default="data/pa5/summary.json")
    p.add_argument("--email-body", default="data/pa5/email_body.txt")
    p.add_argument("--verbose", action="store_true", help="imprime cada paper-trade")
    return p


def main(argv=None):
    args = build_parser().parse_args(argv)
    if args.selftest:
        return selftest()
    return run(args)


if __name__ == "__main__":
    raise SystemExit(main())
