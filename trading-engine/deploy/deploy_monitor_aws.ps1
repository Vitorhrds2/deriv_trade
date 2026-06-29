# Envia o monitor + .env p/ a VM provisionada e o sobe como servico systemd.
# Le ~/.aws/anomaly-monitor.state.json (criado por provision_monitor_aws.ps1).
$ErrorActionPreference = "Stop"
$env:Path = [Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [Environment]::GetEnvironmentVariable("Path", "User")
$awsdir = Join-Path $env:USERPROFILE ".aws"
$STATE  = Join-Path $awsdir "anomaly-monitor.state.json"
if (-not (Test-Path $STATE)) { throw "Sem state ($STATE). Rode provision_monitor_aws.ps1 antes." }
$st  = Get-Content $STATE | ConvertFrom-Json
$IP  = $st.ip
$KEY = $st.keyPath
$src = "c:\Users\Usuario\Documents\deriv_trade-synthetic\trading-engine"

# .env (token Deriv): tenta o worktree synthetic, senao o repo principal
$envfile = Join-Path $src ".env"
if (-not (Test-Path $envfile)) { $envfile = "c:\Users\Usuario\Documents\Deriv_trade\trading-engine\.env" }
if (-not (Test-Path $envfile)) { throw "Nao achei .env com o token Deriv (synthetic nem repo principal)." }
Write-Host "  .env: $envfile"

# Args do monitor (a SUA config do PID 20836). Edite aqui se quiser mudar.
$MARGS = "--symbols 1HZ10V,1HZ100V,R_10,R_25,R_50,R_75,R_100,BOOM1000,CRASH1000 --contracts DIGITEVEN,DIGITODD,DIGITOVER:5,DIGITUNDER:4,DIGITDIFF:0,CALL,PUT --prime 5000 --ev-interval 15 --vet-sample 30000"
$run = "#!/usr/bin/env bash`ncd /home/ubuntu/te`nexec python3 -u synthetic_anomaly_monitor.py $MARGS`n"
$runpath = Join-Path $env:TEMP "run_monitor.sh"
[IO.File]::WriteAllText($runpath, ($run -replace "`r", ""))

$sshopt = @("-i", $KEY, "-o", "StrictHostKeyChecking=no", "-o", "UserKnownHostsFile=/dev/null")

Write-Host "== mkdir remoto =="
& ssh @sshopt "ubuntu@$IP" "mkdir -p ~/te/logs"

Write-Host "== scp codigo + scripts =="
& scp @sshopt "$src\synthetic_anomaly_monitor.py" "$src\anomaly_stats.py" "$src\deriv_client.py" "$src\requirements.txt" "$src\deploy\monitor_setup.sh" "$runpath" "ubuntu@${IP}:te/"

Write-Host "== scp .env =="
& scp @sshopt "$envfile" "ubuntu@${IP}:te/.env"

Write-Host "== setup + systemd (na VM) =="
& ssh @sshopt "ubuntu@$IP" "cd ~/te && sed -i 's/\r`$//' run_monitor.sh monitor_setup.sh && bash monitor_setup.sh"

Write-Host ""
Write-Host "== DEPLOY OK -> monitor como servico systemd (24/7, auto-restart, boot) ==" -ForegroundColor Green
Write-Host "  Checar : ssh -i `"$KEY`" ubuntu@$IP 'systemctl status anomaly-monitor --no-pager; tail -n 25 ~/te/logs/monitor.out'"
Write-Host "  Parar  : ssh -i `"$KEY`" ubuntu@$IP 'sudo systemctl stop anomaly-monitor'"
Write-Host "  Alertas: scp -i `"$KEY`" ubuntu@${IP}:~/te/logs/anomaly_monitor/anomalies.jsonl ."
