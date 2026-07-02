#!/usr/bin/env bash
# Roda NA VM do binance-recorder. Instala o watcher de saude (health_notify.py)
# como servico systemd recorder-notify. Precisa de ALERT_WEBHOOK_URL no ~/te/.env.
# Restart=on-failure (nao reinicia apos o termino normal do recorder). Idempotente.
cd ~/te || exit 1
mkdir -p logs
chmod +x ~/te/health_notify.py 2>/dev/null || true

if ! grep -q '^ALERT_WEBHOOK_URL=' ~/te/.env 2>/dev/null; then
  echo "AVISO: ALERT_WEBHOOK_URL nao esta no ~/te/.env -> o servico vai sair ate ser definido."
fi

echo "== systemd unit recorder-notify =="
sudo tee /etc/systemd/system/recorder-notify.service >/dev/null <<'UNIT'
[Unit]
Description=Binance recorder health notifier (webhook)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/home/ubuntu/te
ExecStart=/usr/bin/python3 -u /home/ubuntu/te/health_notify.py --label binance-recorder --proc-pattern binance_tick_recorder.py --watch-dir /home/ubuntu/te/data/binance_ticks --stall-min 6 --log /home/ubuntu/te/logs/recorder.out --interval 60
Restart=on-failure
RestartSec=20
StandardOutput=append:/home/ubuntu/te/logs/notify.out
StandardError=append:/home/ubuntu/te/logs/notify.err

[Install]
WantedBy=multi-user.target
UNIT

sudo systemctl daemon-reload
sudo systemctl enable recorder-notify >/dev/null 2>&1
sudo systemctl restart recorder-notify
sleep 5
echo "== recorder-notify: $(systemctl is-active recorder-notify) =="
tail -n 12 ~/te/logs/notify.out 2>/dev/null
