# Encerra a VM do monitor e limpa tudo (instancia, SG, key pair, .pem, state).
$ErrorActionPreference = "Continue"
$env:Path = [Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [Environment]::GetEnvironmentVariable("Path", "User")
$env:AWS_PAGER = ""
$awsdir = Join-Path $env:USERPROFILE ".aws"
$STATE  = Join-Path $awsdir "anomaly-monitor.state.json"
if (-not (Test-Path $STATE)) { Write-Host "Sem state; nada a encerrar."; return }
$st = Get-Content $STATE | ConvertFrom-Json

Write-Host "Terminando $($st.instanceId) em $($st.region)..."
aws ec2 terminate-instances --region $st.region --instance-ids $st.instanceId | Out-Null
aws ec2 wait instance-terminated --region $st.region --instance-ids $st.instanceId
aws ec2 delete-security-group --region $st.region --group-id $st.securityGroupId 2>$null
aws ec2 delete-key-pair --region $st.region --key-name $st.keyName 2>$null
if (Test-Path $st.keyPath) { Remove-Item $st.keyPath -Force }
Remove-Item $STATE -Force
Write-Host "Encerrado e limpo (instancia, SG, key pair, .pem, state)."
