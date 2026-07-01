"""
status_api.py — API HTTP minima (stdlib apenas, sem dependencias novas) para expor o estado
do hft_arbitrage_bot ao dashboard hypothesis-lab-os.

Roda ao lado do bot na mesma instancia EC2, lendo os mesmos hft_trades*.log (somente leitura,
nunca interage com o bot nem com a Deriv). Existe porque o dashboard e um Cloudflare Worker
(nao suporta SSH/subprocess/leitura de arquivo local em request-time) -- essa API expoe os
mesmos dados via fetch() HTTP simples, que o Worker consegue chamar normalmente.

Endpoints:
  GET /api/health       -> {"ok": true}
  GET /api/hft/status   -> sessao tmux viva? log parado ha quanto tempo? ultimas linhas.
  GET /api/hft/trades   -> trades parseadas (reusa audit_hft_trades.parse_log), com resumo
                            separado por grupo do shadow A/B (ALIGNED/ANTI).
"""
import glob
import json
import os
import subprocess
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from audit_hft_trades import LOG_DIR, parse_log

PORT = int(os.getenv("STATUS_API_PORT", "8787"))
# O bot loga com frequencia (tick sync, monitoramento) mesmo sem disparar trade; se o log
# ficar mais que isso sem nenhuma linha nova, e sinal de processo travado/caido.
HEARTBEAT_STALE_SECONDS = 60
TMUX_SESSION_NAME = "hft_bot"


def load_all_trades():
    all_trades = {}
    for path in sorted(glob.glob(os.path.join(LOG_DIR, "hft_trades*.log"))):
        for t in parse_log(path):
            all_trades[t["contract_id"]] = t
    return sorted(all_trades.values(), key=lambda t: t["ts"] or "")


def tmux_session_alive(name=TMUX_SESSION_NAME):
    try:
        res = subprocess.run(["tmux", "has-session", "-t", name], capture_output=True, timeout=3)
        return res.returncode == 0
    except Exception:
        return False


def tail_log_lines(n=20):
    path = os.path.join(LOG_DIR, "hft_trades.log")
    try:
        with open(path, "r", errors="ignore") as f:
            lines = f.readlines()
        return [line.rstrip("\n") for line in lines[-n:]]
    except Exception:
        return []


def last_log_mtime():
    path = os.path.join(LOG_DIR, "hft_trades.log")
    try:
        return os.path.getmtime(path)
    except Exception:
        return None


def summarize_group(trades):
    n = len(trades)
    wins = sum(1 for t in trades if (t.get("profit") or 0) > 0)
    pnl = sum(t.get("profit") or 0 for t in trades)
    return {
        "n": n,
        "wins": wins,
        "win_rate": round(wins / n, 4) if n else 0.0,
        "pnl_total": round(pnl, 2),
        "ev_per_trade": round(pnl / n, 4) if n else 0.0,
    }


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass  # silencia o log padrao do BaseHTTPRequestHandler (ja temos hft_trades.log)

    def _send_json(self, payload, status=200):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        try:
            if self.path == "/api/health":
                self._send_json({"ok": True, "server_time": time.time()})
            elif self.path == "/api/hft/status":
                self._handle_status()
            elif self.path == "/api/hft/trades":
                self._handle_trades()
            else:
                self._send_json({"error": "not found"}, status=404)
        except Exception as e:
            self._send_json({"error": str(e)}, status=500)

    def _handle_status(self):
        mtime = last_log_mtime()
        age = (time.time() - mtime) if mtime else None
        recent = tail_log_lines(20)
        last_error = next((l for l in reversed(recent) if "ERROR" in l), None)
        self._send_json(
            {
                "tmux_session_alive": tmux_session_alive(),
                "log_age_seconds": round(age, 1) if age is not None else None,
                "log_stale": bool(age is not None and age > HEARTBEAT_STALE_SECONDS),
                "last_error_line": last_error,
                "recent_log_lines": recent,
                "server_time": time.time(),
            }
        )

    def _handle_trades(self):
        trades = load_all_trades()
        aligned = [t for t in trades if t.get("group", "ALIGNED") == "ALIGNED"]
        anti = [t for t in trades if t.get("group") == "ANTI"]
        self._send_json(
            {
                "total": summarize_group(trades),
                "aligned": summarize_group(aligned),
                "anti": summarize_group(anti),
                # Ate ~200 trades da pra mandar tudo sem custo real -- o frontend usa isso pra
                # montar uma curva de equity acumulada de verdade (nao so uma amostra recente).
                "recent_trades": trades[-200:],
            }
        )


def main():
    server = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    print(f"status_api rodando em 0.0.0.0:{PORT} (le {LOG_DIR}/hft_trades*.log)")
    server.serve_forever()


if __name__ == "__main__":
    main()
