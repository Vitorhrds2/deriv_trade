# Baixa os logs da VM e DESTROI os recursos AWS (instancia, SG, key pair).
# Le o estado de ~/.aws/tokyo-arb.state.json.
$ErrorActionPreference = "Continue"
$env:Path = [Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [Environment]::GetEnvironmentVariable("Path","User")

$STATE = Join-Path $env:USERPROFILE ".aws\tokyo-arb.state.json"
if (-not (Test-Path $STATE)) { throw "Estado nao encontrado: $STATE" }
$st = Get-Content $STATE -Raw | ConvertFrom-Json
$IP = $st.ip; $KEY = $st.keyPath; $IID = $st.instanceId; $SG = $st.securityGroupId; $KEYNAME = $st.keyName; $REGION = $st.region

Write-Host "== 1. Baixando logs da VM (best-effort) ==" -ForegroundColor Cyan
$dest = "C:\Users\Usuario\Documents\deriv_trade-h1\trading-engine\logs"
New-Item -ItemType Directory -Force -Path $dest | Out-Null
try {
  scp -i $KEY -o StrictHostKeyChecking=accept-new "ubuntu@${IP}:te/logs/tokyo_arb_live.out" "$dest\tokyo_arb_live.out"
  scp -i $KEY -o StrictHostKeyChecking=accept-new "ubuntu@${IP}:te/logs/tokyo_rtt.out"      "$dest\tokyo_rtt.out"
  scp -i $KEY -o StrictHostKeyChecking=accept-new "ubuntu@${IP}:te/logs/tokyo_account.out"  "$dest\tokyo_account.out"
  Write-Host "  Logs salvos em $dest"
} catch { Write-Host "  (aviso) falha ao baixar logs: $_" }

Write-Host "== 2. Terminando a instancia $IID ==" -ForegroundColor Cyan
aws ec2 terminate-instances --region $REGION --instance-ids $IID --query "TerminatingInstances[0].CurrentState.Name" --output text
aws ec2 wait instance-terminated --region $REGION --instance-ids $IID
Write-Host "  Instancia terminada."

Write-Host "== 3. Apagando security group $SG =="
aws ec2 delete-security-group --region $REGION --group-id $SG
Write-Host "== 4. Apagando key pair $KEYNAME =="
aws ec2 delete-key-pair --region $REGION --key-name $KEYNAME

Write-Host "== 5. Removendo artefatos locais (.pem + estado) =="
if (Test-Path $KEY)   { Remove-Item $KEY -Force }
if (Test-Path $STATE) { Remove-Item $STATE -Force }

Write-Host ""
Write-Host "== TEARDOWN COMPLETO ==" -ForegroundColor Green
Write-Host "  Instancia, SG e key pair removidos. .pem e estado locais apagados."
Write-Host "  >>> FALTA VOCE: deletar a ACCESS KEY ROOT no console AWS (IAM > Security credentials)."
