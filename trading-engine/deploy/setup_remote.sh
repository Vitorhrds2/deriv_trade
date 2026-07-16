#!/usr/bin/env bash
set -euo pipefail

APP=/home/ec2-user/d17
echo "[setup] python: $(python3 --version)"
echo "[setup] app dir: $APP"

if [ ! -f "$APP/sim100.env" ]; then
  echo "[setup] ERRO: $APP/sim100.env nao existe. Crie-o com DISCORD_WEBHOOK_URL antes de rodar." >&2
  exit 1
fi
chmod 600 "$APP/sim100.env"

sudo cp "$APP/deploy/d17-sim10k.service" /etc/systemd/system/d17-sim10k.service
sudo cp "$APP/deploy/d17-sim100.service" /etc/systemd/system/d17-sim100.service
sudo systemctl daemon-reload
sudo systemctl enable --now d17-sim10k.service
sudo systemctl enable --now d17-sim100.service

sleep 4
echo "=== status d17-sim10k ==="
systemctl --no-pager --lines=0 status d17-sim10k.service || true
echo "=== status d17-sim100 ==="
systemctl --no-pager --lines=0 status d17-sim100.service || true
