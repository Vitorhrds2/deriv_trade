#!/usr/bin/env bash
# Instala dependencias do gravador na VM Ubuntu e confirma a latencia ate a Binance.
set -euo pipefail
cd ~/te

echo "== deps (python3-pip + websockets) =="
sudo apt-get update -qq
sudo apt-get install -y -qq python3-pip >/dev/null
pip3 install --quiet --user websockets

echo "== RTT TCP ate a Binance (co-locacao Toquio) =="
python3 - <<'PY'
import socket, time
host = "stream.binance.com"
ts = []
for _ in range(5):
    t = time.time()
    s = socket.create_connection((host, 9443), timeout=5)
    s.close()
    ts.append((time.time() - t) * 1000)
ts.sort()
print(f"  connect {host}:9443 -> mediana {ts[len(ts)//2]:.1f} ms (min {ts[0]:.1f})")
PY

echo "== setup OK =="
