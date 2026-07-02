#!/usr/bin/env bash
# Sobe o gravador DESACOPLADO (nohup) p/ rodar mesmo apos o SSH cair.
# Uso: bash run_recorder.sh [SYMBOLS] [RUNTIME_S]
set -euo pipefail
cd ~/te
mkdir -p logs data/binance_ticks

SYMBOLS="${1:-BTCUSDT,ETHUSDT}"
RUNTIME="${2:-86400}"   # 24h

# Se ja houver um rodando, nao duplica.
if [ -f recorder.pid ] && kill -0 "$(cat recorder.pid)" 2>/dev/null; then
  echo "Ja existe um recorder rodando (PID $(cat recorder.pid)). Abortando."
  exit 0
fi

# Subshell desacoplado: roda o gravador ate o max-runtime e, ao terminar, PARA a
# instancia (shutdown=stop por padrao na EC2 -> compute para de cobrar, EBS+dados
# preservados). Protege contra esquecer o teardown com o PC desligado.
nohup bash -c "
  python3 -u \"\$HOME/te/binance_tick_recorder.py\" \
    --symbols '$SYMBOLS' --max-runtime '$RUNTIME' \
    --outdir \"\$HOME/te/data/binance_ticks\"
  echo \"[run_recorder] gravador terminou em \$(date -u) -> parando a instancia em 1min\"
  sudo shutdown -h +1
" > "$HOME/te/logs/recorder.out" 2>&1 &
echo $! > recorder.pid
sleep 3
echo "== recorder PID $(cat recorder.pid) | symbols=$SYMBOLS | runtime=${RUNTIME}s =="
echo "   (ao fim do runtime a VM se AUTO-PARA p/ nao cobrar; dados ficam no EBS)"
tail -n 12 logs/recorder.out || true
