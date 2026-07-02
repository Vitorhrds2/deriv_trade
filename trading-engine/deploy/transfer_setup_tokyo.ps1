# Transfere os arquivos p/ a VM e roda o setup. Le o estado de ~/.aws/tokyo-arb.state.json.
$ErrorActionPreference = "Stop"
$env:Path = [Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [Environment]::GetEnvironmentVariable("Path","User")

$STATE = Join-Path $env:USERPROFILE ".aws\tokyo-arb.state.json"
if (-not (Test-Path $STATE)) { throw "Estado nao encontrado: $STATE (rode provision_tokyo.ps1 antes)." }
$st  = Get-Content $STATE -Raw | ConvertFrom-Json
$IP  = $st.ip
$KEY = $st.keyPath
$U   = "ubuntu@$IP"
$SSHOPT = @("-i", $KEY, "-o", "StrictHostKeyChecking=accept-new", "-o", "ConnectTimeout=10")

$ENGINE  = "C:\Users\Usuario\Documents\deriv_trade-h1\trading-engine"
$ENVFILE = "C:\Users\Usuario\Documents\Deriv_trade\trading-engine\.env"
if (-not (Test-Path $ENVFILE)) { throw ".env nao encontrado em $ENVFILE" }

Write-Host "== Aguardando o SSH responder em $IP (ate ~2.5 min) ==" -ForegroundColor Cyan
$ok = $false
for ($i = 0; $i -lt 30; $i++) {
  ssh @SSHOPT $U "echo ready" 2>$null | Out-Null
  if ($LASTEXITCODE -eq 0) { $ok = $true; break }
  Start-Sleep -Seconds 5
}
if (-not $ok) { throw "SSH nao respondeu a tempo." }
Write-Host "  SSH OK."

Write-Host "== Criando diretorios na VM =="
ssh @SSHOPT $U "mkdir -p ~/te/deploy ~/te/logs"

Write-Host "== Enviando arquivos (scp) =="
$files = @("deriv_client.py","arb_order_test.py","deriv_rtt_probe.py","account_check.py","requirements.txt")
foreach ($f in $files) {
  scp @SSHOPT (Join-Path $ENGINE $f) "${U}:te/"
  if ($LASTEXITCODE -ne 0) { throw "Falha no scp de $f" }
}
scp @SSHOPT (Join-Path $ENGINE "deploy\tokyo_setup.sh")   "${U}:te/deploy/"
scp @SSHOPT (Join-Path $ENGINE "deploy\run_tokyo_test.sh") "${U}:te/deploy/"
scp @SSHOPT $ENVFILE "${U}:te/.env"
Write-Host "  Arquivos enviados."

Write-Host "== Normalizando CRLF->LF e rodando o setup ==" -ForegroundColor Cyan
ssh @SSHOPT $U "cd ~/te && sed -i 's/\r`$//' .env deploy/*.sh && bash deploy/tokyo_setup.sh"
if ($LASTEXITCODE -ne 0) { throw "Setup falhou na VM (exit $LASTEXITCODE)." }

Write-Host ""
Write-Host "== SETUP OK ==" -ForegroundColor Green
Write-Host "  Proximo: rodar o teste (run_tokyo_test.sh)."
