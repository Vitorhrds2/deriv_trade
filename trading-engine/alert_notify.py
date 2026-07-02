#!/usr/bin/env python3
"""Sidecar de notificacao: vigia o anomalies.jsonl do monitor e dispara um
webhook (Discord / Slack / generico) para cada alerta novo. Sem libs externas
(usa urllib) -> nao precisa instalar nada na VM.

Config por variaveis de ambiente (lidas tambem do ~/te/.env):
  ALERT_WEBHOOK_URL   URL do webhook (OBRIGATORIO).
  ALERT_MIN_SEVERITY  INFO|WARNING|CRITICAL (default WARNING; abaixo disso ignora,
                      p/ nao notificar blips INFO/EV_EDGE_REJECTED).
  ALERT_EVIDENCE      caminho do jsonl (default ~/te/logs/anomaly_monitor/anomalies.jsonl).
"""
import json
import os
import sys
import time
import urllib.request
from pathlib import Path

SEV_ORDER = {"INFO": 0, "WARNING": 1, "CRITICAL": 2}


def load_env(path):
    """Carrega um .env simples (KEY=VALUE) sem depender de python-dotenv."""
    p = Path(path)
    if not p.exists():
        return
    for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def build_payload(url, alert):
    sev = alert.get("severity", "?")
    klass = alert.get("klass", "?")
    key = alert.get("key", "")
    sym = alert.get("symbol", "")
    head = f"[{sev}] {klass}" + (f" | {sym} {key}".rstrip() if (sym or key) else "")
    text = f"{head}\n{alert.get('message', '')}".strip()
    if "discord.com/api/webhooks" in url:
        return {"content": text[:1900]}
    if "hooks.slack.com" in url:
        return {"text": text}
    return {"text": text, "alert": alert}


def post(url, alert):
    data = json.dumps(build_payload(url, alert)).encode("utf-8")
    # Discord/Cloudflare devolve 403 p/ o User-Agent padrao do urllib -> mandamos um proprio.
    req = urllib.request.Request(url, data=data, headers={
        "Content-Type": "application/json",
        "User-Agent": "DerivAnomalyMonitor/1.0 (+https://github.com/Vitorhrds2/deriv_trade)",
    })
    with urllib.request.urlopen(req, timeout=15) as r:
        return r.status


def main():
    here = Path(__file__).resolve().parent
    load_env(here / ".env")
    url = os.getenv("ALERT_WEBHOOK_URL", "").strip()
    if not url:
        print("ALERT_WEBHOOK_URL nao definido (em ~/te/.env). Saindo.", flush=True)
        sys.exit(1)
    min_sev = SEV_ORDER.get(os.getenv("ALERT_MIN_SEVERITY", "WARNING").upper(), 1)
    evidence = os.getenv("ALERT_EVIDENCE", str(here / "logs" / "anomaly_monitor" / "anomalies.jsonl"))

    try:
        post(url, {"severity": "INFO", "klass": "NOTIFIER_ONLINE",
                   "message": "Notificador de anomalias ONLINE (Deriv monitor @AWS). "
                              f"min_severity={os.getenv('ALERT_MIN_SEVERITY', 'WARNING').upper()}."})
        print("boot notification enviada", flush=True)
    except Exception as e:
        print(f"FALHA no boot notify (cheque a URL): {e}", flush=True)

    pos = 0
    inode = None
    print(f"vigiando {evidence} (min_sev={min_sev})", flush=True)
    while True:
        try:
            p = Path(evidence)
            if p.exists():
                st = p.stat()
                if inode != st.st_ino or st.st_size < pos:
                    inode, pos = st.st_ino, 0  # arquivo novo ou truncado/rotacionado
                if st.st_size > pos:
                    with p.open("r", encoding="utf-8", errors="replace") as f:
                        f.seek(pos)
                        for line in f:
                            line = line.strip()
                            if not line:
                                continue
                            try:
                                a = json.loads(line)
                            except Exception:
                                continue
                            sev = SEV_ORDER.get(str(a.get("severity", "INFO")).upper(), 0)
                            if sev < min_sev:
                                continue
                            try:
                                post(url, a)
                                print(f"notificado: {a.get('klass')} {a.get('severity')}", flush=True)
                            except Exception as e:
                                print(f"FALHA POST: {e}", flush=True)
                        pos = f.tell()
        except Exception as e:
            print(f"loop erro: {e}", flush=True)
        time.sleep(3)


if __name__ == "__main__":
    main()
