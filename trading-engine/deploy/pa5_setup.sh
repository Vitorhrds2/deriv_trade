#!/usr/bin/env bash
# Prepara a VM Ubuntu para o coletor PA5. Stdlib apenas (sem websockets/numpy):
# o coletor usa so urllib. Instala awscli (p/ publicar no SNS no fim) e confirma
# acesso as APIs publicas (Polymarket Gamma + Binance).
set -euo pipefail
cd ~/te

echo "== deps =="
sudo apt-get update -qq
sudo apt-get install -y -qq python3 python3-pip awscli >/dev/null
python3 --version

echo "== checagem de conectividade (read-only) =="
python3 - <<'PY'
import json, urllib.request
def get(u):
    return urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": "pa5-setup"}), timeout=15)
b = json.loads(get("https://api.binance.com/api/v3/ticker/price?symbol=BTCUSDT").read())
print("  binance BTCUSDT:", b["price"])
g = get("https://gamma-api.polymarket.com/markets?closed=false&limit=1").read()
print("  polymarket gamma OK:", len(g), "bytes")
PY

echo "== selftests offline =="
python3 polymarket_lag_probe.py --selftest
python3 pa5_collector.py --selftest

echo "== setup OK =="
