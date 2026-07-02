#!/usr/bin/env bash
# Roda NA VM do anomaly-monitor. Instala o timer de live-shadow como systemd
# live-shadow-timer: avisa no Discord ao iniciar e a cada --interval-days (default 7)
# com a contagem ATUAL de eventos do anomalies.jsonl (JOB-2026-07-02-001).
# Usa o ALERT_WEBHOOK_URL ja presente no ~/te/.env (mesmo do anomaly-notify).
cd ~/te || exit 1
mkdir -p logs
chmod +x ~/te/live_shadow_timer.py 2>/dev/null || true

if ! grep -q '^ALERT_WEBHOOK_URL=' ~/te/.env 2>/dev/null; then
  echo "AVISO: ALERT_WEBHOOK_URL nao esta no ~/te/.env -> o servico vai sair ate ser definido."
fi

echo "== systemd unit live-shadow-timer =="
sudo tee /etc/systemd/system/live-shadow-timer.service >/dev/null <<'UNIT'
[Unit]
Description=Live-shadow recheck timer (JOB-2026-07-02-001) -> Discord webhook
After=network-online.target anomaly-monitor.service
Wants=network-online.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/home/ubuntu/te
ExecStart=/usr/bin/python3 -u /home/ubuntu/te/live_shadow_timer.py --label anomaly-monitor --job-id JOB-2026-07-02-001 --klasses-of-interest EV_EDGE,SPIKE_TIMING --min-n 2 --interval-days 7
Restart=always
RestartSec=30
StandardOutput=append:/home/ubuntu/te/logs/live_shadow_timer.out
StandardError=append:/home/ubuntu/te/logs/live_shadow_timer.err

[Install]
WantedBy=multi-user.target
UNIT

sudo systemctl daemon-reload
sudo systemctl enable live-shadow-timer >/dev/null 2>&1
sudo systemctl restart live-shadow-timer
sleep 5
echo "== live-shadow-timer: $(systemctl is-active live-shadow-timer) =="
tail -n 12 ~/te/logs/live_shadow_timer.out 2>/dev/null
