#!/usr/bin/env bash
# Roda NA VM (Ubuntu). Instala deps e instala o monitor como servico systemd
# (24/7, auto-restart se cair, sobe no boot). Idempotente.
# NAO usa `set -e`: numa EC2 nova o cloud-init segura o lock do apt no boot, entao
# reportamos cada passo e usamos DPkg::Lock::Timeout p/ ESPERAR o lock em vez de abortar.
cd ~/te || exit 1
mkdir -p logs

echo "== deps: aguarda apt/cloud-init liberar o lock e instala python3-pip =="
sudo apt-get -o DPkg::Lock::Timeout=300 update -qq
sudo apt-get -o DPkg::Lock::Timeout=300 install -y -qq python3-pip
echo "  apt rc=$?"

echo "== pip: websockets + python-dotenv =="
sudo pip3 install --quiet websockets python-dotenv \
  || sudo pip3 install --quiet --break-system-packages websockets python-dotenv
echo "  pip rc=$?"

echo "== verifica imports =="
python3 -c "import websockets, dotenv; print('  deps OK websockets', websockets.__version__)" || { echo "  FALHA nos imports"; exit 1; }

chmod +x ~/te/run_monitor.sh

echo "== systemd unit =="
sudo tee /etc/systemd/system/anomaly-monitor.service >/dev/null <<'UNIT'
[Unit]
Description=Deriv synthetic anomaly monitor (tripwire)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/home/ubuntu/te
ExecStart=/home/ubuntu/te/run_monitor.sh
Restart=always
RestartSec=15
StandardOutput=append:/home/ubuntu/te/logs/monitor.out
StandardError=append:/home/ubuntu/te/logs/monitor.err

[Install]
WantedBy=multi-user.target
UNIT

sudo systemctl daemon-reload
sudo systemctl enable anomaly-monitor >/dev/null 2>&1 || true
sudo systemctl restart anomaly-monitor
sleep 8

echo "== is-active =="
systemctl is-active anomaly-monitor || true
echo "== status =="
systemctl status anomaly-monitor --no-pager -l | head -n 16 || true
echo "== log (monitor.out, ultimas linhas) =="
tail -n 20 ~/te/logs/monitor.out 2>/dev/null || true
