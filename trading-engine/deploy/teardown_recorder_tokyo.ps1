# Baixa os dados gravados e DESTROI os recursos AWS do gravador.
# Lida com instancia PARADA (auto-stop apos 24h): liga, espera, pega o novo IP, baixa, destroi.
# Le o estado de ~/.aws/tokyo-recorder.state.json.
$ErrorActionPreference = "Continue"
$env:Path = [Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [Environment]::GetEnvironmentVariable("Path","User")

$STATE = Join-Path $env:USERPROFILE ".aws\tokyo-recorder.state.json"
if (-not (Test-Path $STATE)) { throw "Estado nao encontrado: $STATE" }
$st = Get-Content $STATE -Raw | ConvertFrom-Json
$IP = $st.ip; $KEY = $st.keyPath; $IID = $st.instanceId; $SG = $st.securityGroupId; $KEYNAME = $st.keyName; $REGION = $st.region

Write-Host "== 0a. Reautorizando SSH do seu IP atual (residencial muda) ==" -ForegroundColor Cyan
try {
  $myip = (Invoke-WebRequest -UseBasicParsing https://checkip.amazonaws.com).Content.Trim()
  aws ec2 authorize-security-group-ingress --region $REGION --group-id $SG --protocol tcp --port 22 --cidr "$myip/32" 2>$null | Out-Null
  Write-Host "  SSH liberado p/ $myip/32"
} catch { Write-Host "  (aviso) nao consegui reautorizar IP: $_" -ForegroundColor Yellow }

Write-Host "== 0. Estado da instancia ==" -ForegroundColor Cyan
$state = aws ec2 describe-instances --region $REGION --instance-ids $IID --query "Reservations[0].Instances[0].State.Name" --output text
Write-Host "  $IID = $state"
if ($state -eq "stopped") {
  Write-Host "  Instancia parada (auto-stop). Ligando p/ baixar os dados..."
  aws ec2 start-instances --region $REGION --instance-ids $IID | Out-Null
  aws ec2 wait instance-running --region $REGION --instance-ids $IID
  Start-Sleep -Seconds 30   # SSH subir
  $IP = aws ec2 describe-instances --region $REGION --instance-ids $IID --query "Reservations[0].Instances[0].PublicIpAddress" --output text
  Write-Host "  novo IP: $IP"
} elseif ($state -ne "running") {
  Write-Host "  Instancia em '$state' — pulando download." -ForegroundColor Yellow
}

$dest = "C:\Users\Usuario\Documents\deriv_trade-h1\trading-engine\data\binance_ticks_tokyo"
New-Item -ItemType Directory -Force -Path $dest | Out-Null
if ($state -eq "running" -or $state -eq "stopped") {
  Write-Host "== 1. Baixando dados + log (scp -r) ==" -ForegroundColor Cyan
  try {
    scp -i $KEY -o StrictHostKeyChecking=accept-new -r "ubuntu@${IP}:te/data/binance_ticks/*" "$dest\"
    scp -i $KEY -o StrictHostKeyChecking=accept-new "ubuntu@${IP}:te/logs/recorder.out" "$dest\recorder.out"
    Write-Host "  Dados salvos em $dest"
    Get-ChildItem $dest | Select-Object Name,Length | Format-Table -AutoSize
  } catch { Write-Host "  (aviso) falha ao baixar: $_" -ForegroundColor Yellow }
}

Write-Host "== 2. Terminando a instancia $IID =="
aws ec2 terminate-instances --region $REGION --instance-ids $IID --query "TerminatingInstances[0].CurrentState.Name" --output text
aws ec2 wait instance-terminated --region $REGION --instance-ids $IID
Write-Host "== 3. Apagando security group $SG =="
aws ec2 delete-security-group --region $REGION --group-id $SG
Write-Host "== 4. Apagando key pair $KEYNAME =="
aws ec2 delete-key-pair --region $REGION --key-name $KEYNAME
Write-Host "== 5. Removendo artefatos locais (.pem + estado) =="
if (Test-Path $KEY)   { Remove-Item $KEY -Force }
if (Test-Path $STATE) { Remove-Item $STATE -Force }

Write-Host ""
Write-Host "== TEARDOWN COMPLETO ==" -ForegroundColor Green
Write-Host "  Dados em: $dest"
