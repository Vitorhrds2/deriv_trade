import json
import os
import re
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


WEBHOOK = os.getenv("DISCORD_WEBHOOK_URL", "").strip()
LOG_PATH = Path(os.getenv("HFT_LOG_PATH", "hft_trades.log"))
JOB_ID = os.getenv("JOB_ID", "JOB-20260702-001")
HEARTBEAT_SECONDS = int(os.getenv("DISCORD_HEARTBEAT_SECONDS", "300"))

INTERESTING = re.compile(
    r"Guardrails|Found Demo|ABORTANDO|GATILHO|ORDEM|TRADE|SESSION LEDGER|"
    r"KILL SWITCH|rejeitada|Erro no envio|Lucro|Grupo|fora do hor",
    re.IGNORECASE,
)


def load_env_file(path=Path(".env")):
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def post(content):
    if not WEBHOOK:
        print("discord_webhook_missing=true", flush=True)
        return
    body = json.dumps({"content": content[:1900]}).encode("utf-8")
    req = urllib.request.Request(
        WEBHOOK,
        data=body,
        headers={
            "Content-Type": "application/json",
            "User-Agent": "Codex-ShadowMonitor/1.0",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            response.read()
    except Exception as exc:
        print(f"discord_post_error={exc}", flush=True)


def utc_now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def is_golden_hour():
    hour = datetime.now(timezone.utc).hour
    return 12 <= hour < 18


def wait_for_log(path):
    while not path.exists():
        print(f"waiting_for_log={path}", flush=True)
        time.sleep(2)


def main():
    load_env_file()
    global WEBHOOK, LOG_PATH, JOB_ID, HEARTBEAT_SECONDS
    WEBHOOK = os.getenv("DISCORD_WEBHOOK_URL", "").strip()
    LOG_PATH = Path(os.getenv("HFT_LOG_PATH", str(LOG_PATH)))
    JOB_ID = os.getenv("JOB_ID", JOB_ID)
    HEARTBEAT_SECONDS = int(os.getenv("DISCORD_HEARTBEAT_SECONDS", str(HEARTBEAT_SECONDS)))

    post(
        f"[{JOB_ID}] Shadow A/B cloud monitor started. "
        f"golden_hour={is_golden_hour()} now={utc_now()} real_money=blocked"
    )
    last_heartbeat = 0.0
    wait_for_log(LOG_PATH)
    with LOG_PATH.open("r", encoding="utf-8", errors="replace") as fh:
        fh.seek(0, os.SEEK_END)
        while True:
            line = fh.readline()
            now = time.time()
            if line and INTERESTING.search(line):
                post(f"[{JOB_ID}] {line.rstrip()}")
            if now - last_heartbeat >= HEARTBEAT_SECONDS:
                last_heartbeat = now
                post(
                    f"[{JOB_ID}] heartbeat: process collecting, "
                    f"golden_hour={is_golden_hour()} now={utc_now()}"
                )
            if not line:
                time.sleep(1)


if __name__ == "__main__":
    main()
