#!/usr/bin/env bash
# Roda NA VM do anomaly-monitor. Instala o auto-watcher de saude do PROPRIO monitor
# como systemd monitor-health. Usa o ALERT_WEBHOOK_URL ja presente no ~/te/.env
# (mesmo do anomaly-notify). Sinal principal: heartbeat (monitor.out) parar de crescer.
cd ~/te || exit 1
mkdir -p logs
chmod +x ~/te/health_notify.py 2>/dev/null || true

if ! grep -q '^ALERT_WEBHOOK_URL=' ~/te/.env 2>/dev/null; then
  echo "AVISO: ALERT_WEBHOOK_URL nao esta no ~/te/.env -> o servico vai sair ate ser definido."
fi

echo "== systemd unit monitor-health =="
sudo tee /etc/systemd/system/monitor-health.service >/dev/null <<'UNIT'
[Unit]
Description=Anomaly monitor self-health notifier (webhook)
After=network-online.target anomaly-monitor.service
Wants=network-online.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/home/ubuntu/te
ExecStart=/usr/bin/python3 -u /home/ubuntu/te/health_notify.py --label anomaly-monitor --proc-pattern synthetic_anomaly_monitor.py --watch-dir /home/ubuntu/te/logs --stall-min 3 --log /home/ubuntu/te/logs/monitor.out --interval 60
Restart=always
RestartSec=20
StandardOutput=append:/home/ubuntu/te/logs/monitor_health.out
StandardError=append:/home/ubuntu/te/logs/monitor_health.err

[Install]
WantedBy=multi-user.target
UNIT

sudo systemctl daemon-reload
sudo systemctl enable monitor-health >/dev/null 2>&1
sudo systemctl restart monitor-health
sleep 5
echo "== monitor-health: $(systemctl is-active monitor-health) =="
tail -n 12 ~/te/logs/monitor_health.out 2>/dev/null
