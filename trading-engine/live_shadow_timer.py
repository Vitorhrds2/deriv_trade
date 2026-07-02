#!/usr/bin/env python3
"""Timer de live-shadow -> avisa no webhook (Discord/Slack) quando comeca a
esperar por N eventos, e de novo a cada ciclo (default 7 dias), com a
contagem ATUAL de eventos lida direto do anomalies.jsonl local. Sem libs
externas (urllib puro). Pensado para JOB-2026-07-02-001 (research_library),
mas serve para qualquer live-shadow que precise de "avisa quando o tempo
passou o suficiente para reavaliar".

Config (env, tambem lido do ./.env):
  ALERT_WEBHOOK_URL    webhook (OBRIGATORIO).
Args:
  --label NOME             rotulo nas mensagens (default: live-shadow).
  --evidence PATH          jsonl a contar (default: logs/anomaly_monitor/anomalies.jsonl).
  --klasses-of-interest    klasses que contam p/ o N minimo (default: EV_EDGE,SPIKE_TIMING).
  --min-n N                N minimo combinado das klasses de interesse p/ virar RESULT (default 2).
  --interval-days D        dias entre um aviso e o proximo (default 7).
  --job-id ID              identificador do job/study p/ citar na mensagem.

Posta 1x ao iniciar ("timer iniciado" + snapshot atual) e depois 1x por
ciclo ("tempo passou" + snapshot atualizado + recomendacao). Roda para
sempre (Restart=always no systemd) -- se reiniciar, o ciclo reconta a
partir do boot (aceitavel dado NRestarts=0 historico das outras services).
"""
import argparse
import json
import os
import sys
import time
from collections import Counter
from pathlib import Path
from urllib import request as urlreq


def load_env(path):
    p = Path(path)
    if not p.exists():
        return
    for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def post(url, text):
    payload = {"content": text[:1900], "text": text}
    data = json.dumps(payload).encode("utf-8")
    # User-Agent proprio: Discord/Cloudflare bloqueia (403) o UA padrao do urllib.
    req = urlreq.Request(url, data=data, headers={
        "Content-Type": "application/json",
        "User-Agent": "DerivLiveShadowTimer/1.0 (+https://github.com/Vitorhrds2/deriv_trade)",
    })
    with urlreq.urlopen(req, timeout=15) as r:
        return r.status


def snapshot(evidence_path, klasses_of_interest):
    """Le o jsonl e retorna (total, Counter por klass, n_interesse)."""
    p = Path(evidence_path)
    if not p.exists():
        return 0, Counter(), 0
    counts = Counter()
    total = 0
    for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            a = json.loads(line)
        except Exception:
            continue
        total += 1
        counts[str(a.get("klass", "?"))] += 1
    n_interest = sum(counts.get(k, 0) for k in klasses_of_interest)
    return total, counts, n_interest


def fmt_counts(counts):
    if not counts:
        return "nenhum evento ainda"
    return ", ".join(f"{k}={v}" for k, v in sorted(counts.items(), key=lambda kv: -kv[1]))


def main():
    ap = argparse.ArgumentParser(description="Timer de live-shadow -> webhook")
    ap.add_argument("--label", default="live-shadow")
    ap.add_argument("--evidence", default="")
    ap.add_argument("--klasses-of-interest", default="EV_EDGE,SPIKE_TIMING")
    ap.add_argument("--min-n", type=int, default=2)
    ap.add_argument("--interval-days", type=float, default=7.0)
    ap.add_argument("--job-id", default="JOB-2026-07-02-001")
    args = ap.parse_args()

    here = Path(__file__).resolve().parent
    load_env(here / ".env")
    url = os.getenv("ALERT_WEBHOOK_URL", "").strip()
    if not url:
        print("ALERT_WEBHOOK_URL nao definido (em ./.env). Saindo.", flush=True)
        sys.exit(1)

    evidence = args.evidence or str(here / "logs" / "anomaly_monitor" / "anomalies.jsonl")
    klasses = [k.strip() for k in args.klasses_of_interest.split(",") if k.strip()]
    interval_s = args.interval_days * 86400.0

    total, counts, n_interest = snapshot(evidence, klasses)
    next_dt = time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime(time.time() + interval_s))
    msg = (
        f"[INFO] Timer de live-shadow INICIADO | {args.label} ({args.job_id})\n"
        f"Vigiando: {evidence}\n"
        f"Snapshot agora: {total} eventos totais ({fmt_counts(counts)}); "
        f"klasses de interesse ({'+'.join(klasses)}) = {n_interest} (minimo p/ decisao: {args.min_n}).\n"
        f"Proximo aviso em {args.interval_days:.0f}d (~{next_dt}). "
        f"Ate la, nada a fazer -- so aguardar o feed acumular."
    )
    try:
        post(url, msg)
        print("timer start notification enviada", flush=True)
    except Exception as e:
        print(f"FALHA no timer start notify (cheque a URL): {e}", flush=True)

    print(f"timer ativo: interval={args.interval_days}d evidence={evidence} "
          f"klasses={klasses} min_n={args.min_n}", flush=True)

    while True:
        time.sleep(interval_s)
        total, counts, n_interest = snapshot(evidence, klasses)
        ready = n_interest >= args.min_n
        sev = "WARNING" if ready else "INFO"
        rec = (
            f"N minimo ATINGIDO ({n_interest}>={args.min_n})! Hora de continuar a investigacao: "
            f"puxar os alertas, medir holdout temporal (MATH-2026-07-02-003) e registrar RESULT."
            if ready else
            f"Ainda abaixo do minimo ({n_interest}<{args.min_n}). Continue aguardando "
            f"(proximo aviso em {args.interval_days:.0f}d) ou revise se o gate esta calibrado certo."
        )
        next_dt = time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime(time.time() + interval_s))
        msg = (
            f"[{sev}] Tempo suficiente passou ({args.interval_days:.0f}d) | {args.label} ({args.job_id})\n"
            f"Snapshot agora: {total} eventos totais ({fmt_counts(counts)}); "
            f"klasses de interesse = {n_interest}.\n"
            f"{rec}\n"
            f"Proximo aviso: ~{next_dt} (se ainda nao decidido)."
        )
        try:
            post(url, msg)
            print(f"recheck notification enviada (n_interest={n_interest})", flush=True)
        except Exception as e:
            print(f"FALHA no recheck notify: {e}", flush=True)


if __name__ == "__main__":
    main()
