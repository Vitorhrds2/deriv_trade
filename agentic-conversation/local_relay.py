#!/usr/bin/env python3
"""Relay HTTP para o Devin Local (rodar no Macbook).

Expoe o Devin Local (ou qualquer processo/agente local) para o bot Telegram:

  POST /message         -> grava input em ~/.devin-local-relay/inbox.jsonl
  GET  /events?since=N  -> retorna outputs de ~/.devin-local-relay/outbox.jsonl
  GET  /status          -> status + tamanho da inbox pendente

O processo local (Devin CLI, script, outro agente) consome a inbox e escreve
respostas na outbox (uma linha JSON por evento: {"message": "..."}).

Uso:
  python local_relay.py --port 8787
  RELAY_TOKEN=segredo python local_relay.py --port 8787   # com autenticacao

Exponha a porta via Tailscale/ngrok e configure LOCAL_DEVIN_URL no bot.
"""
import argparse
import json
import os
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

STATE = Path.home() / ".devin-local-relay"
INBOX = STATE / "inbox.jsonl"
OUTBOX = STATE / "outbox.jsonl"
TOKEN = os.environ.get("RELAY_TOKEN", "")


def _read_outbox() -> list[dict]:
    if not OUTBOX.exists():
        return []
    events = []
    for line in OUTBOX.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            events.append({"message": line})
    return events


class Handler(BaseHTTPRequestHandler):
    def _authorized(self) -> bool:
        if not TOKEN:
            return True
        return self.headers.get("Authorization", "") == f"Bearer {TOKEN}"

    def _json(self, code: int, payload: dict) -> None:
        body = json.dumps(payload).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        if not self._authorized():
            return self._json(401, {"error": "unauthorized"})
        parsed = urlparse(self.path)
        if parsed.path == "/status":
            pending = len(INBOX.read_text().splitlines()) if INBOX.exists() else 0
            return self._json(200, {"status": "ok", "pending": pending})
        if parsed.path == "/events":
            since = int(parse_qs(parsed.query).get("since", ["0"])[0])
            events = _read_outbox()
            return self._json(
                200, {"events": events[since:], "cursor": len(events)}
            )
        self._json(404, {"error": "not found"})

    def do_POST(self) -> None:
        if not self._authorized():
            return self._json(401, {"error": "unauthorized"})
        if urlparse(self.path).path != "/message":
            return self._json(404, {"error": "not found"})
        length = int(self.headers.get("Content-Length", "0"))
        try:
            payload = json.loads(self.rfile.read(length) or b"{}")
        except json.JSONDecodeError:
            return self._json(400, {"error": "invalid json"})
        message = payload.get("message", "")
        if not message:
            return self._json(400, {"error": "campo 'message' obrigatorio"})
        with INBOX.open("a") as f:
            f.write(json.dumps({"message": message, "ts": time.time()}) + "\n")
        self._json(200, {"ok": True})

    def log_message(self, fmt: str, *args) -> None:
        print(f"[relay] {self.address_string()} {fmt % args}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8787)
    parser.add_argument("--host", default="0.0.0.0")
    args = parser.parse_args()
    STATE.mkdir(parents=True, exist_ok=True)
    print(f"Relay em http://{args.host}:{args.port} | inbox: {INBOX} | outbox: {OUTBOX}")
    ThreadingHTTPServer((args.host, args.port), Handler).serve_forever()
