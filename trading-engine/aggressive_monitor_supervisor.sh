#!/bin/bash
# Supervisor: restarts any dead tmux session.
# D42/D43/D45 intentionally EXCLUDED (concluded/refuted/redundant).
# hft_bot REMOVED 2026-07-08 (refutado, N=34/N=12 IC95% negativo).
# early_sell_multi REMOVED 2026-07-08 (re-refutado, N=187x10 combos).
# D40 REMOVED 2026-07-14 (refutado: WR=0%@24h, EV=-1.49%, CI<0).
# D44 REMOVED 2026-07-14 (refutado: EV=-$0.05, CI<0 em 8h/24h/72h).
# D41 REMOVED 2026-07-14 (refutado por fees: WR=58-77% real mas EV=+0.01% << 0.2% fees).
# D52/D95 REMOVIDOS 2026-07-17 (refutados: EV IC95% inteiramente negativo).
# D101/D90 REMOVIDOS 2026-07-17 (refutados/inconclusivos, processos não ativos).
# iv_anomaly_bot/options_bot/twap_bot MOVIDOS 2026-07-17 para us-east-2 (Deribit MiFID II EU restriction).
SESSIONS=(
  "d37_outflow:python3 exchange_outflow_scan.py --continuous:d37_outflow.log"
  "unlock_bot:python3 unlock_short_bot.py:unlock_bot.log"
  "status_api:python3 status_api.py:status_api.log"
  "basis_bot:python3 basis_paper_bot.py:basis_bot.log"
  "d55_paper:python3 hyperliquid_paper_bot.py --position-usd 1000:d55_paper.log"
  "d34_cascade:python3 d34_cascade_ws.py --continuous:d34_cascade_ws.log"
  "h85_swift:bash h85_continuous.sh:h85_drift/h85_continuous.log"
)
cd /home/ubuntu/trading-engine
while true; do
  for entry in "${SESSIONS[@]}"; do
    IFS=':' read -r name cmd logfile <<< "$entry"
    if ! tmux has-session -t $name 2>/dev/null; then
      echo "[$(date -u)] Restarting $name..."
      tmux new-session -d -s $name "PYTHONUNBUFFERED=1 $cmd 2>&1 | tee -a $logfile"
    fi
  done
  sleep 60
done
