# Transfere o gravador p/ a VM, instala deps e sobe o processo desacoplado (24h).
# Le o estado de ~/.aws/tokyo-recorder.state.json (gerado por provision_recorder_tokyo.ps1).
# Rode a partir de C:\Users\Usuario\Documents\deriv_trade-h1\trading-engine
$ErrorActionPreference = "Stop"
$env:Path = [Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [Environment]::GetEnvironmentVariable("Path","User")

$SYMBOLS = if ($args.Count -ge 1) { $args[0] } else { "BTCUSDT,ETHUSDT" }
$RUNTIME = if ($args.Count -ge 2) { $args[1] } else { "86400" }

$STATE = Join-Path $env:USERPROFILE ".aws\tokyo-recorder.state.json"
if (-not (Test-Path $STATE)) { throw "Estado nao encontrado: $STATE (rode provision_recorder_tokyo.ps1 antes)" }
$st = Get-Content $STATE -Raw | ConvertFrom-Json
$IP = $st.ip; $KEY = $st.keyPath

Write-Host "== 1. Pastas na VM ==" -ForegroundColor Cyan
ssh -i $KEY -o StrictHostKeyChecking=accept-new "ubuntu@${IP}" "mkdir -p ~/te/deploy ~/te/logs ~/te/data/binance_ticks"

Write-Host "== 2. Enviando arquivos =="
scp -i $KEY -o StrictHostKeyChecking=accept-new binance_tick_recorder.py "ubuntu@${IP}:~/te/"
scp -i $KEY deploy/recorder_setup.sh deploy/run_recorder.sh "ubuntu@${IP}:~/te/deploy/"

Write-Host "== 3. Normalizando CRLF -> LF nos .sh =="
ssh -i $KEY "ubuntu@${IP}" "sed -i 's/\r$//' ~/te/deploy/*.sh"

Write-Host "== 4. Instalando deps (setup) =="
ssh -i $KEY "ubuntu@${IP}" "bash ~/te/deploy/recorder_setup.sh"

Write-Host "== 5. Subindo o gravador (nohup, ${RUNTIME}s) =="
ssh -i $KEY "ubuntu@${IP}" "bash ~/te/deploy/run_recorder.sh '$SYMBOLS' '$RUNTIME'"

Write-Host ""
Write-Host "== ATIVO ==" -ForegroundColor Green
Write-Host "  Acompanhar ao vivo:  ssh -i `"$KEY`" ubuntu@$IP 'tail -f ~/te/logs/recorder.out'"
Write-Host "  Dados crescem em:    ~/te/data/binance_ticks/ (1 csv por simbolo/hora)"
Write-Host "  Ao terminar (24h):   .\deploy\teardown_recorder_tokyo.ps1  (baixa os dados e destroi tudo)"
