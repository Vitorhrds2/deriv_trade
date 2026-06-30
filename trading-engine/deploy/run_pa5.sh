#!/usr/bin/env bash
# Lanca o coletor PA5 DESACOPLADO (nohup) com um teto rigido de tempo e, ao terminar,
# publica um email via SNS e AUTO-PARA a instancia (para de cobrar compute).
#
# Args: $1 = horas (default 48)  $2 = horizontes (default "5,15")  $3 = min_move (default 8)
# Variaveis de ambiente esperadas (injetadas pelo deploy):
#   PA5_SNS_TOPIC_ARN  -> ARN do topico SNS para o email de conclusao (opcional)
#   AWS_DEFAULT_REGION -> regiao (para o awscli)
set -euo pipefail
cd ~/te

HOURS="${1:-48}"
HORIZON="${2:-5,15}"
MINMOVE="${3:-8}"
OUT="data/pa5/windows.jsonl"
SUMMARY="data/pa5/summary.json"
EMAILBODY="data/pa5/email_body.txt"
mkdir -p data/pa5 logs

# Margem de seguranca: o `timeout` mata o coletor um pouco depois do alvo, garantindo
# que ele encerre mesmo se uma janela travar. O proprio coletor ja respeita --hours.
HARD_SECONDS=$(python3 -c "print(int(float('$HOURS')*3600)+600)")

cat > ~/te/pa5_wrapper.sh <<WRAP
#!/usr/bin/env bash
set -uo pipefail
cd ~/te
echo "[wrapper] inicio \$(date -u +%FT%TZ) | hours=$HOURS horizon=$HORIZON min_move=$MINMOVE"
timeout ${HARD_SECONDS}s python3 -u pa5_collector.py \\
    --hours "$HOURS" --horizon "$HORIZON" --min-move "$MINMOVE" \\
    --out "$OUT" --summary "$SUMMARY" --email-body "$EMAILBODY" \\
    >> logs/pa5_collector.out 2>&1
RC=\$?
echo "[wrapper] coletor terminou rc=\$RC \$(date -u +%FT%TZ)"

SUBJECT="PA5 coleta finalizada (rc=\$RC) - \$(hostname)"
BODY="\$( [ -f "$EMAILBODY" ] && cat "$EMAILBODY" || echo 'sem corpo de email' )"
if [ -n "\${PA5_SNS_TOPIC_ARN:-}" ]; then
  echo "[wrapper] publicando no SNS \$PA5_SNS_TOPIC_ARN"
  aws sns publish --topic-arn "\$PA5_SNS_TOPIC_ARN" --subject "\$SUBJECT" --message "\$BODY" \\
      >> logs/pa5_collector.out 2>&1 || echo "[wrapper] FALHA ao publicar SNS (ver IAM role)"
else
  echo "[wrapper] PA5_SNS_TOPIC_ARN nao setado -> sem email"
fi

echo "[wrapper] auto-stop da instancia em 30s..."
sleep 30
sudo shutdown -h now
WRAP
chmod +x ~/te/pa5_wrapper.sh

# exporta o ARN/regiao para o wrapper herdar
export PA5_SNS_TOPIC_ARN AWS_DEFAULT_REGION
nohup ~/te/pa5_wrapper.sh > logs/pa5_wrapper.out 2>&1 &
PID=$!
echo "PA5 coletor lancado: PID=$PID | teto=${HARD_SECONDS}s (~$HOURS h)"
sleep 4
echo "== primeiras linhas =="
tail -n 8 logs/pa5_collector.out 2>/dev/null || echo "(ainda sem log)"
