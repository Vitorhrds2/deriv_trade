#!/usr/bin/env python3
"""
unlock_status_api.py — API HTTP para o D17 unlock_short_bot (paper trading).

Roda ao lado do bot na EC2, lendo unlock_short_state.json e unlock_short_trades.json
(readonly, nunca interage com o bot nem com a Binance). Mesmo padrão do status_api.py.

Endpoints:
  GET /api/health            -> {"ok": true}
  GET /api/unlock/status     -> bot rodando? posições abertas, equity, last check
  GET /api/unlock/trades     -> trades fechadas com PnL, equity curve
  GET /api/unlock/schedule   -> próximos unlocks com entry dates
  GET /api/unlock/stats      -> stats agregadas (WR, avg bps, t-stat por período)
"""
import json
import math
import os
import subprocess
import time
from datetime import datetime, timezone, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PORT = int(os.getenv("UNLOCK_API_PORT", "8788"))
TMUX_SESSION = "unlock_bot"
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATE_FILE = os.path.join(BASE_DIR, "unlock_short_state.json")
TRADE_FILE = os.path.join(BASE_DIR, "unlock_short_trades.json")

# Import unlock schedule + config from the bot
import sys
sys.path.insert(0, BASE_DIR)
from unlock_short_bot import (
    KNOWN_UNLOCKS,
    ENTRY_DAYS,
    EXIT_DAYS,
    FEE_BPS,
    STOP_LOSS_PCT,
    MAX_CONCURRENT,
    MAX_POSITION_PCT,
    MIN_UNLOCK_VALUE_MM,
    KELLY_FRACTION,
    ENTRY_TIME_UTC,
    get_historical_stats,
    kelly_position_size,
)


def tmux_alive(name=TMUX_SESSION):
    try:
        res = subprocess.run(["tmux", "has-session", "-t", name], capture_output=True, timeout=3)
        return res.returncode == 0
    except Exception:
        return False


def load_state():
    try:
        with open(STATE_FILE) as f:
            return json.load(f)
    except Exception:
        return {"open_positions": [], "closed_trades": [], "last_check": None}


def load_trades():
    try:
        with open(TRADE_FILE) as f:
            return json.load(f)
    except Exception:
        return []


def mean(x):
    return sum(x) / len(x) if x else 0


def std(x):
    if len(x) < 2:
        return 0
    m = mean(x)
    return math.sqrt(sum((xi - m) ** 2 for xi in x) / (len(x) - 1))


def t_stat(values):
    if len(values) < 2:
        return 0
    m = mean(values)
    s = std(values)
    return m / (s / math.sqrt(len(values))) if s > 0 else 0


def classify_period(unlock_date_str):
    d = unlock_date_str[:10] if isinstance(unlock_date_str, str) else ""
    if d < "2025-01-01":
        return "IS"
    elif d < "2026-01-01":
        return "OOS-2025"
    else:
        return "OOS-2026"


def compute_stats(trades):
    """Compute aggregate stats by period from closed trades."""
    if not trades:
        return {"all": empty_stats(), "is": empty_stats(), "oos25": empty_stats(), "oos26": empty_stats()}

    pnls_all = [t.get("net_pnl", 0) for t in trades]
    pnls_by_period = {"IS": [], "OOS-2025": [], "OOS-2026": []}

    for t in trades:
        ud = t.get("unlock_date", t.get("unlockDate", ""))
        period = classify_period(ud)
        pnls_by_period[period].append(t.get("net_pnl", 0))

    return {
        "all": stats_from_pnls(pnls_all),
        "is": stats_from_pnls(pnls_by_period["IS"]),
        "oos25": stats_from_pnls(pnls_by_period["OOS-2025"]),
        "oos26": stats_from_pnls(pnls_by_period["OOS-2026"]),
    }


def empty_stats():
    return {"n": 0, "wr": 0, "avg_pnl": 0, "total_pnl": 0, "t_stat": 0}


def stats_from_pnls(pnls):
    n = len(pnls)
    if n == 0:
        return empty_stats()
    wins = sum(1 for p in pnls if p > 0)
    return {
        "n": n,
        "wr": round(wins / n * 100, 1),
        "avg_pnl": round(mean(pnls), 2),
        "total_pnl": round(sum(pnls), 2),
        "t_stat": round(t_stat(pnls), 2),
    }


def get_upcoming_unlocks(limit=20):
    now = datetime.now(timezone.utc)
    now_str = now.strftime("%Y-%m-%d")
    upcoming = []
    for sym, date, val, pct, src in KNOWN_UNLOCKS:
        if date >= now_str and val >= MIN_UNLOCK_VALUE_MM:
            unlock_dt = datetime.strptime(date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
            entry_dt = unlock_dt + timedelta(days=ENTRY_DAYS)
            exit_dt = unlock_dt + timedelta(days=EXIT_DAYS)
            days_to = (unlock_dt - now).days
            upcoming.append({
                "symbol": sym,
                "unlock_date": date,
                "unlock_value_mm": val,
                "pct_supply": pct,
                "source": src,
                "entry_date": entry_dt.strftime("%Y-%m-%d"),
                "exit_date": exit_dt.strftime("%Y-%m-%d"),
                "days_until": days_to,
            })
    upcoming.sort(key=lambda x: x["unlock_date"])
    return upcoming[:limit]


def build_equity_curve(trades, starting_equity=10000):
    curve = [{"trade": 0, "equity": starting_equity}]
    eq = starting_equity
    for i, t in enumerate(trades, 1):
        eq += t.get("net_pnl", 0)
        curve.append({"trade": i, "equity": round(eq, 2)})
    return curve


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass

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
            elif self.path == "/api/unlock/status":
                self._handle_status()
            elif self.path == "/api/unlock/trades":
                self._handle_trades()
            elif self.path == "/api/unlock/schedule":
                self._handle_schedule()
            elif self.path == "/api/unlock/stats":
                self._handle_stats()
            else:
                self._send_json({"error": "not found"}, status=404)
        except Exception as e:
            self._send_json({"error": str(e)}, status=500)

    def _handle_status(self):
        state = load_state()
        trades = load_trades()
        open_positions = state.get("open_positions", [])
        closed_trades = state.get("closed_trades", [])

        total_pnl = sum(t.get("net_pnl", 0) for t in closed_trades)
        wins = sum(1 for t in closed_trades if t.get("net_pnl", 0) > 0)
        wr = round(wins / len(closed_trades) * 100, 1) if closed_trades else 0

        self._send_json({
            "connected": True,
            "tmux_session_alive": tmux_alive(),
            "mode": "paper",
            "open_positions": open_positions,
            "open_count": len(open_positions),
            "closed_count": len(closed_trades),
            "total_pnl": round(total_pnl, 2),
            "win_rate": wr,
            "last_check": state.get("last_check"),
            "config": {
                "entry_days": ENTRY_DAYS,
                "exit_days": EXIT_DAYS,
                "fee_bps": FEE_BPS,
                "stop_loss_pct": STOP_LOSS_PCT,
                "max_concurrent": MAX_CONCURRENT,
                "max_position_pct": MAX_POSITION_PCT * 100,
                "min_unlock_value_mm": MIN_UNLOCK_VALUE_MM,
                "kelly_fraction": KELLY_FRACTION,
                "entry_time_utc": ENTRY_TIME_UTC,
            },
            "server_time": time.time(),
        })

    def _handle_trades(self):
        trades = load_trades()
        stats = compute_stats(trades)
        equity_curve = build_equity_curve(trades)

        self._send_json({
            "connected": True,
            "trades": trades,
            "equity_curve": equity_curve,
            "stats": stats,
            "starting_equity": 10000,
            "final_equity": equity_curve[-1]["equity"] if equity_curve else 10000,
            "total_return_pct": round((equity_curve[-1]["equity"] / 10000 - 1) * 100, 1) if equity_curve else 0,
        })

    def _handle_schedule(self):
        upcoming = get_upcoming_unlocks(20)
        self._send_json({
            "connected": True,
            "upcoming": upcoming,
            "config": {
                "entry_days": ENTRY_DAYS,
                "exit_days": EXIT_DAYS,
                "min_unlock_value_mm": MIN_UNLOCK_VALUE_MM,
            },
        })

    def _handle_stats(self):
        trades = load_trades()
        stats = compute_stats(trades)

        # Per-symbol breakdown
        by_symbol = {}
        for t in trades:
            sym = t.get("symbol", "?")
            if sym not in by_symbol:
                by_symbol[sym] = []
            by_symbol[sym].append(t.get("net_pnl", 0))

        per_symbol = []
        for sym, pnls in sorted(by_symbol.items()):
            n = len(pnls)
            wins = sum(1 for p in pnls if p > 0)
            per_symbol.append({
                "symbol": sym,
                "n": n,
                "wr": round(wins / n * 100, 1) if n else 0,
                "avg_pnl": round(mean(pnls), 2),
                "total_pnl": round(sum(pnls), 2),
            })

        self._send_json({
            "connected": True,
            "period_stats": stats,
            "per_symbol": per_symbol,
            "total_trades": len(trades),
        })


def main():
    server = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    print(f"unlock_status_api rodando em 0.0.0.0:{PORT}")
    server.serve_forever()


if __name__ == "__main__":
    main()
