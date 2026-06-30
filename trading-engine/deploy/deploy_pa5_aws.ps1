# Transfere o coletor PA5 p/ a VM, instala deps e sobe o processo desacoplado (48h).
# Le o estado de ~/.aws/pa5-collector.state.json (gerado por provision_pa5_aws.ps1).
# Rode a partir de C:\Users\Usuario\Documents\deriv_trade-polymarket\trading-engine
#
# Args: $1 = horas (default 48)  $2 = horizontes (default "5,15")  $3 = min_move (default 8)
$ErrorActionPreference = "Stop"
$env:Path = [Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [Environment]::GetEnvironmentVariable("Path", "User")

$HOURS   = if ($args.Count -ge 1) { $args[0] } else { "48" }
$HORIZON = if ($args.Count -ge 2) { $args[1] } else { "5,15" }
$MINMOVE = if ($args.Count -ge 3) { $args[2] } else { "8" }

$STATE = Join-Path $env:USERPROFILE ".aws\pa5-collector.state.json"
if (-not (Test-Path $STATE)) { throw "Estado nao encontrado: $STATE (rode provision_pa5_aws.ps1 antes)" }
$st = Get-Content $STATE -Raw | ConvertFrom-Json
$IP = $st.ip; $KEY = $st.keyPath; $TOPIC = $st.topicArn; $REGION = $st.region

Write-Host "== 1. Pastas na VM ==" -ForegroundColor Cyan
ssh -i $KEY -o StrictHostKeyChecking=accept-new "ubuntu@${IP}" "mkdir -p ~/te/deploy ~/te/logs ~/te/data/pa5"

Write-Host "== 2. Enviando codigo (coletor + sonda + stats) =="
scp -i $KEY -o StrictHostKeyChecking=accept-new pa5_collector.py polymarket_lag_probe.py polymarket_arb_stats.py "ubuntu@${IP}:~/te/"
scp -i $KEY deploy/pa5_setup.sh deploy/run_pa5.sh "ubuntu@${IP}:~/te/deploy/"

Write-Host "== 3. Normalizando CRLF -> LF nos .sh =="
ssh -i $KEY "ubuntu@${IP}" "sed -i 's/\r$//' ~/te/deploy/*.sh"

Write-Host "== 4. Setup (deps + selftests + checagem de rede) =="
ssh -i $KEY "ubuntu@${IP}" "bash ~/te/deploy/pa5_setup.sh"

Write-Host "== 5. Subindo o coletor (nohup, ${HOURS}h) + SNS no fim =="
ssh -i $KEY "ubuntu@${IP}" "export PA5_SNS_TOPIC_ARN='$TOPIC'; export AWS_DEFAULT_REGION='$REGION'; bash ~/te/deploy/run_pa5.sh '$HOURS' '$HORIZON' '$MINMOVE'"

Write-Host ""
Write-Host "== ATIVO ==" -ForegroundColor Green
Write-Host "  Acompanhar:        ssh -i `"$KEY`" ubuntu@$IP 'tail -f ~/te/logs/pa5_collector.out'"
Write-Host "  Sumario parcial:   ssh -i `"$KEY`" ubuntu@$IP 'cat ~/te/data/pa5/summary.json'"
Write-Host "  No fim (~48h): email via SNS + auto-stop. Depois rode .\deploy\teardown_pa5_aws.ps1"
Write-Host "  >>> Pode DESLIGAR o PC: a coleta segue na AWS." -ForegroundColor Yellow
