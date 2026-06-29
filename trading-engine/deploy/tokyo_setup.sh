#!/usr/bin/env bash
# H3 - Setup do teste de arbitragem de latencia CO-LOCADO.
# Rodar NA VM (AWS ap-northeast-1 / Toquio), depois de colocar os arquivos + .env.
# Uso:  bash deploy/tokyo_setup.sh
set -euo pipefail

cd "$(dirname "$0")/.."   # -> diretorio trading-engine (onde estao os .py e o .env)
echo "Diretorio de trabalho: $(pwd)"

echo
echo "== 1/4. Pacotes de sistema (python3 + venv) =="
if command -v apt-get >/dev/null 2>&1; then
  sudo apt-get update -y && sudo apt-get install -y python3 python3-venv python3-pip
elif command -v dnf >/dev/null 2>&1; then
  sudo dnf install -y python3 python3-pip
elif command -v yum >/dev/null 2>&1; then
  sudo yum install -y python3 python3-pip
else
  echo "!! Gerenciador de pacotes nao reconhecido - instale python3/venv manualmente."
fi

echo
echo "== 2/4. venv + dependencias (websockets, python-dotenv) =="
python3 -m venv .venv
.venv/bin/pip install -q --upgrade pip
.venv/bin/pip install -q websockets python-dotenv
echo "  Python: $(.venv/bin/python3 --version) | venv OK"

echo
echo "== 3/4. Checagem do .env =="
if [ ! -f .env ]; then
  echo "!! FALTA trading-engine/.env. Crie a partir de .env.example com DERIV_APP_ID e DERIV_API_TOKEN (permissao Trade)."
  exit 1
fi
if ! grep -Eq "^DERIV_API_TOKEN=.+" .env; then
  echo "!! .env existe mas DERIV_API_TOKEN esta vazio."
  exit 1
fi
echo "  .env OK."

echo
echo "== 4/4. Confirmacao de CO-LOCACAO (RTT TCP) =="
.venv/bin/python3 - <<'PY'
import socket, time
def rtt(host, port, n=8):
    best = float("inf")
    for _ in range(n):
        t0 = time.perf_counter()
        try:
            s = socket.create_connection((host, port), timeout=5); s.close()
            best = min(best, (time.perf_counter() - t0) * 1000.0)
        except Exception as e:
            print(f"  erro {host}:{port} -> {e}")
            return None
    return best
b = rtt("stream.binance.com", 9443)
d = rtt("api.derivws.com", 443)
print(f"  Binance stream.binance.com:9443 -> min {b:.1f} ms   (ESPERADO ~0.3-5 ms em Toquio; se ~270 ms, regiao ERRADA!)")
print(f"  Deriv   api.derivws.com:443     -> min {d:.1f} ms   (borda Cloudflare; o RTT de app real sai em deriv_rtt_probe.py)")
PY

echo
echo "== Setup OK. Agora rode:  bash deploy/run_tokyo_test.sh =="
