#!/usr/bin/env bash
# H3 - Executa o teste DECISIVO de fill co-locado (Toquio) e salva os logs.
# Rodar APOS tokyo_setup.sh.   Uso:  bash deploy/run_tokyo_test.sh
set -euo pipefail

cd "$(dirname "$0")/.."   # -> trading-engine
mkdir -p logs
PY=.venv/bin/python3

echo "=================================================================="
echo " A. Latencia REAL de Toquio (sinal Binance + leg de ordem Deriv)"
echo "=================================================================="
$PY deriv_rtt_probe.py 2>&1 | tee logs/tokyo_rtt.out

echo
echo "=================================================================="
echo " B. Conta conectada (TEM que ser DEMO - a trava aborta se nao for)"
echo "=================================================================="
$PY account_check.py 2>&1 | tee logs/tokyo_account.out

echo
echo "=================================================================="
echo " C. Teste de fill --live: 60 ordens DEMO de \$1, aligned vs anti"
echo "    (lookback/hold menores que de casa p/ reagir mais rapido)"
echo "=================================================================="
$PY arb_order_test.py --live --stake 1 --mult 100 \
  --threshold 4 --lookback-ms 200 --hold-s 1.2 --cooldown-s 1.0 \
  --max-trades 60 --max-seconds 600 2>&1 | tee logs/tokyo_arb_live.out

echo
echo "=================================================================="
echo " VEREDITO (ver o fim de logs/tokyo_arb_live.out)"
echo "=================================================================="
echo "  - aligned (P&L medio) > 0          -> ARB destravado pela latencia"
echo "  - IC95% de (aligned-anti) > 0 E MAIOR que o de casa (+0.0041)"
echo "                                     -> janela 'stale' capturada de Toquio"
echo "  - aligned ~ -0.026 e IC cruza zero -> H3 MORTO mesmo co-locado"
echo
echo "Baixe os logs p/ casa (rode no SEU PC):"
echo "  scp -i SUA_KEY.pem ubuntu@SEU_IP:~/te/logs/tokyo_*.out ."
echo
echo ">>> Nao esqueca de TERMINAR a instancia depois (controle de custo)."
