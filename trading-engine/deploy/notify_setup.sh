#!/usr/bin/env bash
# Roda NA VM. Instala o notificador (alert_notify.py) como servico systemd
# anomaly-notify (24/7, auto-restart, boot). Idempotente. Precisa de
# ALERT_WEBHOOK_URL no ~/te/.env. Sem deps externas (urllib puro).
cd ~/te || exit 1
mkdir -p logs
chmod +x ~/te/alert_notify.py 2>/dev/null || true

if ! grep -q '^ALERT_WEBHOOK_URL=' ~/te/.env 2>/dev/null; then
  echo "AVISO: ALERT_WEBHOOK_URL nao esta no ~/te/.env -> o servico vai sair ate ser definido."
fi

echo "== systemd unit anomaly-notify =="
sudo tee /etc/systemd/system/anomaly-notify.service >/dev/null <<'UNIT'
[Unit]
Description=Deriv anomaly alert notifier (webhook)
After=network-online.target anomaly-monitor.service
Wants=network-online.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/home/ubuntu/te
ExecStart=/usr/bin/python3 -u /home/ubuntu/te/alert_notify.py
Restart=always
RestartSec=15
StandardOutput=append:/home/ubuntu/te/logs/notify.out
StandardError=append:/home/ubuntu/te/logs/notify.err

[Install]
WantedBy=multi-user.target
UNIT

sudo systemctl daemon-reload
sudo systemctl enable anomaly-notify >/dev/null 2>&1
sudo systemctl restart anomaly-notify
sleep 4
echo "== anomaly-notify: $(systemctl is-active anomaly-notify) =="
tail -n 12 ~/te/logs/notify.out 2>/dev/null
