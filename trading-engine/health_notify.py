#!/usr/bin/env python3
"""Watcher de saude GENERICO -> notifica um webhook (Discord/Slack) quando um
processo cai, encerra, ou os dados estagnam. Sem libs externas (urllib puro).
Pensado p/ a VM do binance-recorder (que NAO tem anomalies.jsonl), mas serve
p/ qualquer processo/diretorio de dados.

Config (env, tambem lido do ./.env):
  ALERT_WEBHOOK_URL    webhook (OBRIGATORIO).
Args:
  --label NOME         rotulo nas mensagens (ex.: binance-recorder).
  --proc-pattern PAD   pgrep -f PAD -> checa se o processo vive (OBRIGATORIO).
  --watch-dir DIR      diretorio cujos arquivos mais novos devem crescer (stall).
  --stall-min N        minutos sem arquivo atualizado = stall (default 6).
  --log PATH           log p/ extrair as ultimas linhas e distinguir termino normal.
  --interval S         intervalo de checagem em segundos (default 60).

So alerta a MORTE depois de ter visto o processo VIVO ao menos uma vez (evita
falso-alarme se subir antes do processo comecar). Sai com 0 apos reportar a morte
(use Restart=on-failure no systemd p/ nao reiniciar em loop).
"""
import argparse
import json
import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path


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
    if "hooks.slack.com" in url:
        payload = {"text": text}
    else:  # discord usa "content"; generico tambem aceita
        payload = {"content": text[:1900], "text": text}
    data = json.dumps(payload).encode("utf-8")
    # User-Agent proprio: Discord/Cloudflare bloqueia (403) o UA padrao do urllib.
    req = urllib.request.Request(url, data=data, headers={
        "Content-Type": "application/json",
        "User-Agent": "DerivHealthNotify/1.0 (+https://github.com/Vitorhrds2/deriv_trade)",
    })
    with urllib.request.urlopen(req, timeout=15) as r:
        return r.status


def proc_alive(pattern):
    try:
        out = subprocess.run(["pgrep", "-f", pattern], capture_output=True, text=True)
        return out.returncode == 0 and out.stdout.strip() != ""
    except Exception:
        return False


def newest_mtime(d):
    p = Path(d)
    if not p.is_dir():
        return None
    mts = [f.stat().st_mtime for f in p.glob("*") if f.is_file()]
    return max(mts) if mts else None


def last_lines(path, n=4):
    try:
        return "\n".join(Path(path).read_text(encoding="utf-8", errors="replace").splitlines()[-n:])
    except Exception:
        return ""


def main():
    ap = argparse.ArgumentParser(description="Watcher de saude -> webhook")
    ap.add_argument("--label", default="instancia")
    ap.add_argument("--proc-pattern", required=True)
    ap.add_argument("--watch-dir", default="")
    ap.add_argument("--stall-min", type=float, default=6.0)
    ap.add_argument("--log", default="")
    ap.add_argument("--interval", type=float, default=60.0)
    args = ap.parse_args()

    here = Path(__file__).resolve().parent
    load_env(here / ".env")
    url = os.getenv("ALERT_WEBHOOK_URL", "").strip()
    if not url:
        print("ALERT_WEBHOOK_URL nao definido (em ./.env). Saindo.", flush=True)
        sys.exit(1)

    extra = f" + dados em {args.watch_dir} (stall>{args.stall_min:.0f}min)" if args.watch_dir else ""
    try:
        post(url, f"[INFO] watcher de saude ONLINE | {args.label} | vigia '{args.proc_pattern}'{extra}.")
        print("boot notification enviada", flush=True)
    except Exception as e:
        print(f"FALHA no boot notify (cheque a URL): {e}", flush=True)

    seen_alive = False
    stalled = False
    print(f"vigiando proc='{args.proc_pattern}' dir='{args.watch_dir}'", flush=True)
    while True:
        alive = proc_alive(args.proc_pattern)
        if alive:
            seen_alive = True
        elif seen_alive:
            tail = last_lines(args.log) if args.log else ""
            low = tail.lower()
            normal = ("terminou" in low) or ("max-runtime" in low) or ("max_runtime" in low) or ("parando a instancia" in low)
            if normal:
                msg = f"[INFO] {args.label}: processo ENCERROU (parece termino normal / fim de runtime)."
            else:
                msg = f"[CRITICAL] {args.label}: processo CAIU inesperadamente."
            if tail:
                msg += f"\nultimas linhas do log:\n{tail}"
            try:
                post(url, msg)
                print("notificado: morte do processo", flush=True)
            except Exception as e:
                print(f"FALHA post morte: {e}", flush=True)
            sys.exit(0)  # processo acabou; encerra limpo (Restart=on-failure nao reinicia)

        if args.watch_dir:
            mt = newest_mtime(args.watch_dir)
            if mt is not None:
                age_min = (time.time() - mt) / 60.0
                if age_min > args.stall_min and not stalled:
                    stalled = True
                    try:
                        post(url, f"[WARNING] {args.label}: STALL de dados -- sem arquivo atualizado ha "
                                  f"{age_min:.1f} min em {args.watch_dir}.")
                        print("notificado: stall", flush=True)
                    except Exception as e:
                        print(f"FALHA post stall: {e}", flush=True)
                elif age_min <= args.stall_min and stalled:
                    stalled = False
                    try:
                        post(url, f"[INFO] {args.label}: dados VOLTARAM a fluir.")
                    except Exception:
                        pass
        time.sleep(args.interval)


if __name__ == "__main__":
    main()
