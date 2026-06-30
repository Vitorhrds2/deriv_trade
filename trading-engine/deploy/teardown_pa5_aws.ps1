# Baixa os dados coletados e DESTROI os recursos AWS do coletor PA5.
# Lida com instancia PARADA (auto-stop apos 48h): liga, espera, pega o novo IP, baixa, destroi.
# Tambem remove SNS topic + IAM role/instance-profile. Le ~/.aws/pa5-collector.state.json.
$ErrorActionPreference = "Continue"
$env:Path = [Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [Environment]::GetEnvironmentVariable("Path", "User")

$STATE = Join-Path $env:USERPROFILE ".aws\pa5-collector.state.json"
if (-not (Test-Path $STATE)) { throw "Estado nao encontrado: $STATE" }
$st = Get-Content $STATE -Raw | ConvertFrom-Json
$IP = $st.ip; $KEY = $st.keyPath; $IID = $st.instanceId; $SG = $st.securityGroupId
$KEYNAME = $st.keyName; $REGION = $st.region; $TOPIC = $st.topicArn
$ROLE = $st.roleName; $PROFILE = $st.profileName

Write-Host "== 0a. Reautorizando SSH do seu IP atual ==" -ForegroundColor Cyan
try {
  $myip = (Invoke-WebRequest -UseBasicParsing https://checkip.amazonaws.com).Content.Trim()
  aws ec2 authorize-security-group-ingress --region $REGION --group-id $SG --protocol tcp --port 22 --cidr "$myip/32" 2>$null | Out-Null
  Write-Host "  SSH liberado p/ $myip/32"
} catch { Write-Host "  (aviso) nao consegui reautorizar IP: $_" -ForegroundColor Yellow }

Write-Host "== 0. Estado da instancia ==" -ForegroundColor Cyan
$state = aws ec2 describe-instances --region $REGION --instance-ids $IID --query "Reservations[0].Instances[0].State.Name" --output text
Write-Host "  $IID = $state"
if ($state -eq "stopped") {
  Write-Host "  Parada (auto-stop). Ligando p/ baixar os dados..."
  aws ec2 start-instances --region $REGION --instance-ids $IID | Out-Null
  aws ec2 wait instance-running --region $REGION --instance-ids $IID
  Start-Sleep -Seconds 30
  $IP = aws ec2 describe-instances --region $REGION --instance-ids $IID --query "Reservations[0].Instances[0].PublicIpAddress" --output text
  Write-Host "  novo IP: $IP"
}

$dest = "C:\Users\Usuario\Documents\deriv_trade-polymarket\trading-engine\data\pa5_aws"
New-Item -ItemType Directory -Force -Path $dest | Out-Null
if ($state -eq "running" -or $state -eq "stopped") {
  Write-Host "== 1. Baixando dados (windows.jsonl + summary + logs) ==" -ForegroundColor Cyan
  try {
    scp -i $KEY -o StrictHostKeyChecking=accept-new "ubuntu@${IP}:te/data/pa5/*" "$dest\"
    scp -i $KEY "ubuntu@${IP}:te/logs/pa5_collector.out" "$dest\pa5_collector.out" 2>$null
    Write-Host "  Dados salvos em $dest"
    Get-ChildItem $dest | Select-Object Name, Length | Format-Table -AutoSize
  } catch { Write-Host "  (aviso) falha ao baixar: $_" -ForegroundColor Yellow }
}

Write-Host "== 2. Terminando a instancia $IID =="
aws ec2 terminate-instances --region $REGION --instance-ids $IID --query "TerminatingInstances[0].CurrentState.Name" --output text
aws ec2 wait instance-terminated --region $REGION --instance-ids $IID

Write-Host "== 3. IAM: removendo role do profile + apagando =="
aws iam remove-role-from-instance-profile --instance-profile-name $PROFILE --role-name $ROLE 2>$null | Out-Null
aws iam delete-instance-profile --instance-profile-name $PROFILE 2>$null | Out-Null
aws iam delete-role-policy --role-name $ROLE --policy-name pa5-sns-publish 2>$null | Out-Null
aws iam delete-role --role-name $ROLE 2>$null | Out-Null

Write-Host "== 4. Apagando SNS topic =="
aws sns delete-topic --region $REGION --topic-arn $TOPIC 2>$null | Out-Null

Write-Host "== 5. Apagando security group $SG =="
aws ec2 delete-security-group --region $REGION --group-id $SG 2>$null | Out-Null
Write-Host "== 6. Apagando key pair $KEYNAME =="
aws ec2 delete-key-pair --region $REGION --key-name $KEYNAME 2>$null | Out-Null
Write-Host "== 7. Removendo artefatos locais (.pem + estado) =="
if (Test-Path $KEY)   { Remove-Item $KEY -Force }
if (Test-Path $STATE) { Remove-Item $STATE -Force }

Write-Host ""
Write-Host "== TEARDOWN COMPLETO ==" -ForegroundColor Green
Write-Host "  Dados em: $dest"
