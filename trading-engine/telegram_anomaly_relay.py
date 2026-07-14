"""Telegram alert relay for anomaly monitors.

Tails JSONL evidence files from synthetic_anomaly_monitor.py and
d106_pricing_anomaly_monitor.py and sends push notifications to Telegram
for HIGH/CRITICAL anomalies.

Designed to be extremely lightweight: polls files every 5s, sends one
HTTP POST per new anomaly. ~10MB RAM, near-zero CPU.

Usage:
    python telegram_anomaly_relay.py

Credentials come from environment variables:
    TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
"""
import json
import os
import sys
import time
import urllib.request
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

# JSONL files to watch
WATCH_FILES = [
    "logs/anomaly_monitor/anomalies.jsonl",
    "logs/d106_pricing_anomalies.jsonl",
]

# Only alert on these severities (skip INFO/LOW to avoid spam)
ALERT_SEVERITIES = {"HIGH", "CRITICAL"}

# Poll interval (seconds)
POLL_INTERVAL = 5.0

# Rate limit: max 1 message per 30s per anomaly klass+symbol (avoid spam)
COOLDOWN_SECONDS = 30.0

# Max message length for Telegram
MAX_MSG_LEN = 4000


def send_telegram(text):
    """Send a message to Telegram. Returns True on success."""
    if not BOT_TOKEN or not CHAT_ID:
        print(f"  [relay] WARNING: TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID not set", flush=True)
        return False
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = json.dumps({
        "chat_id": CHAT_ID,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }).encode()
    req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status == 200
    except Exception as e:
        print(f"  [relay] Telegram send failed: {e}", flush=True)
        return False


def format_alert(record):
    """Format a JSONL anomaly record as a Telegram message."""
    sev = record.get("severity", "?")
    klass = record.get("klass", "?")
    symbol = record.get("symbol", "?")
    msg = record.get("message", "")
    iso = record.get("iso", "")
    stats = record.get("stats", {})

    # Emoji by severity
    icon = {"CRITICAL": "🔴", "HIGH": "🟠", "MEDIUM": "🟡", "INFO": "⚪"}.get(sev, "⚪")

    lines = [
        f"{icon} <b>{sev}</b> — {klass}",
        f"<b>Symbol:</b> {symbol}",
        f"<b>Time:</b> {iso}",
        f"<b>Detail:</b> {msg}",
    ]

    # Add key stats (limit to 5 fields)
    if stats:
        stat_lines = []
        for k, v in list(stats.items())[:5]:
            if isinstance(v, float):
                stat_lines.append(f"  {k}: {v:.4f}")
            else:
                stat_lines.append(f"  {k}: {v}")
        if stat_lines:
            lines.append("<b>Stats:</b>\n" + "\n".join(stat_lines))

    text = "\n".join(lines)
    if len(text) > MAX_MSG_LEN:
        text = text[:MAX_MSG_LEN - 20] + "\n... (truncated)"
    return text


def tail_jsonl(path, last_pos):
    """Read new lines from a JSONL file since last position.
    Returns (new_records, new_position)."""
    p = Path(path)
    if not p.exists():
        return [], last_pos

    try:
        size = p.stat().st_size
    except OSError:
        return [], last_pos

    # File was truncated/rotated — start from beginning
    if size < last_pos:
        last_pos = 0

    if size == last_pos:
        return [], last_pos

    records = []
    try:
        with open(path, "r") as f:
            f.seek(last_pos)
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
            new_pos = f.tell()
    except OSError:
        return [], last_pos

    return records, new_pos


def main():
    print(f">>> Telegram Anomaly Relay", flush=True)
    print(f"    Bot token: {'set' if BOT_TOKEN else 'MISSING'}", flush=True)
    print(f"    Chat ID: {'set' if CHAT_ID else 'MISSING'}", flush=True)
    print(f"    Watching: {WATCH_FILES}", flush=True)
    print(f"    Alert severities: {ALERT_SEVERITIES}", flush=True)
    print(f"    Poll interval: {POLL_INTERVAL}s", flush=True)
    print(f"    Cooldown: {COOLDOWN_SECONDS}s per klass+symbol", flush=True)
    print(flush=True)

    if not BOT_TOKEN or not CHAT_ID:
        print("  FATAL: credentials not set. Export TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID.", flush=True)
        sys.exit(1)

    # Send startup message
    send_telegram(
        "🟢 <b>Anomaly Relay Online</b>\n"
        f"Monitoring {len(WATCH_FILES)} JSONL files\n"
        f"Alerts: {', '.join(sorted(ALERT_SEVERITIES))}\n"
        f"Poll: every {POLL_INTERVAL}s"
    )

    # Track file positions
    positions = {f: 0 for f in WATCH_FILES}

    # Cooldown tracker: (klass, symbol) -> last_send_time
    cooldowns = {}

    total_sent = 0
    total_seen = 0

    while True:
        for filepath in WATCH_FILES:
            records, new_pos = tail_jsonl(filepath, positions[filepath])
            positions[filepath] = new_pos

            for record in records:
                total_seen += 1
                sev = record.get("severity", "")
                klass = record.get("klass", "")
                symbol = record.get("symbol", "")

                # Skip low-severity
                if sev not in ALERT_SEVERITIES:
                    continue

                # Check cooldown
                key = (klass, symbol)
                now = time.time()
                last_sent = cooldowns.get(key, 0)
                if now - last_sent < COOLDOWN_SECONDS:
                    continue

                # Send alert
                text = format_alert(record)
                ok = send_telegram(text)
                if ok:
                    total_sent += 1
                    cooldowns[key] = now
                    print(f"  [sent] {sev} {klass} {symbol} (#{total_sent})", flush=True)
                else:
                    print(f"  [fail] {sev} {klass} {symbol}", flush=True)

        # Heartbeat every ~5 minutes
        if total_seen > 0 and total_seen % 60 == 0:
            print(f"  [heartbeat] seen={total_seen} sent={total_sent}", flush=True)

        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()
