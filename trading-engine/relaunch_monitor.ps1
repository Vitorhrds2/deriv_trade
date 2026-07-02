# Relanca o synthetic_anomaly_monitor com o codigo blindado (gate de turnover + auto-vet)
# e R_50 incluido. Encerra instancias antigas do monitor (NAO toca em monitor_squads.py).
# Uso: powershell -ExecutionPolicy Bypass -File relaunch_monitor.ps1
param(
  [string]$Symbols   = "1HZ10V,1HZ100V,R_10,R_25,R_50,R_75,R_100,BOOM1000,CRASH1000",
  [string]$Contracts = "DIGITEVEN,DIGITODD,DIGITOVER:5,DIGITUNDER:4,DIGITDIFF:0,CALL,PUT",
  [int]$Prime        = 5000,
  [int]$EvInterval   = 15,
  [int]$VetSample    = 30000,
  [int]$MaxRuntime   = 28800
)

$ErrorActionPreference = "Stop"
$py = "C:\Users\Usuario\AppData\Local\Programs\Python\Python313\python.exe"
$wd = $PSScriptRoot
$logdir = Join-Path $wd "logs\anomaly_monitor"
New-Item -ItemType Directory -Force -Path $logdir | Out-Null

# Encerra SOMENTE instancias do monitor de anomalia (preserva monitor_squads.py e outros).
Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
  Where-Object { $_.CommandLine -match 'synthetic_anomaly_monitor\.py' } |
  ForEach-Object {
    Write-Host "Parando monitor antigo PID $($_.ProcessId)"
    Stop-Process -Id $_.ProcessId -Force
  }
Start-Sleep -Seconds 1

$argline = "-u synthetic_anomaly_monitor.py --symbols $Symbols --contracts $Contracts " +
           "--prime $Prime --ev-interval $EvInterval --vet-sample $VetSample --max-runtime $MaxRuntime"
$out = Join-Path $logdir "hunt.out"
$err = Join-Path $logdir "hunt.err"

$p = Start-Process -FilePath $py -ArgumentList $argline -WorkingDirectory $wd `
       -RedirectStandardOutput $out -RedirectStandardError $err -WindowStyle Hidden -PassThru
$p.Id | Out-File -Encoding ascii (Join-Path $logdir "hunt.pid")

Write-Host ""
Write-Host "Monitor relancado (codigo blindado + R_50): PID $($p.Id)"
Write-Host "  symbols  : $Symbols"
Write-Host "  contracts: $Contracts"
Write-Host "  auto-vet : $VetSample ticks | ev-interval ${EvInterval}s | runtime ${MaxRuntime}s"
Write-Host "  log      : $out"
Write-Host "  pid file : $(Join-Path $logdir 'hunt.pid')"
