param([int]$DelaySeconds = 0, [switch]$Notify)

# Verificacao de saude do monitor de anomalias sinteticas.
#   pwsh -ExecutionPolicy Bypass -File monitor_check.ps1                 # status agora
#   pwsh -ExecutionPolicy Bypass -File monitor_check.ps1 -DelaySeconds 1800 -Notify   # timer 30min
# Le hunt.pid/hunt.out/hunt.err/anomalies.jsonl e emite um VERDICT. Nao opera nada.

if ($DelaySeconds -gt 0) { Start-Sleep -Seconds $DelaySeconds }

$h = "c:\Users\Usuario\Documents\deriv_trade-synthetic\trading-engine\logs\anomaly_monitor"

$np = (Get-Content "$h\hunt.pid" -ErrorAction SilentlyContinue | Select-Object -First 1)
if ($np) { $np = "$np".Trim() }
$proc = if ($np) { Get-Process -Id ([int]$np) -ErrorAction SilentlyContinue } else { $null }

$out = Get-Content "$h\hunt.out" -ErrorAction SilentlyContinue
$hb  = [string]($out | Where-Object { $_ -match '^\s+\. ' } | Select-Object -Last 1)
$rc  = ([regex]::Match($hb, 'rc=(\d+)')).Groups[1].Value; if (-not $rc) { $rc = '0' }
$hbt = ([regex]::Match($hb, '\d\d:\d\d:\d\d')).Value
$age = -1
if ($hbt) {
    try { $age = [int]((Get-Date) - [datetime]::ParseExact($hbt, 'HH:mm:ss', $null)).TotalSeconds } catch { $age = -1 }
}

$err = (Get-Content "$h\hunt.err" -ErrorAction SilentlyContinue | Measure-Object -Line).Lines
$jl  = Get-Content "$h\anomalies.jsonl" -ErrorAction SilentlyContinue
$nA  = ($jl | Measure-Object -Line).Lines
$objs = if ($nA) { $jl | ForEach-Object { $_ | ConvertFrom-Json } } else { @() }
$brk  = if ($nA) { (($objs | Group-Object klass | ForEach-Object { "$($_.Name)=$($_.Count)" }) -join ' | ') } else { '(nenhum)' }
$ev    = ($objs | Where-Object { $_.klass -eq 'EV_EDGE' } | Measure-Object).Count
$stall = ($objs | Where-Object { $_.klass -eq 'FEED_STALL' } | Measure-Object).Count

$up = if ($proc) { [int]((Get-Date) - $proc.StartTime).TotalMinutes } else { 0 }

if     (-not $proc)                  { $verdict = "PARADO -- processo morreu" }
elseif ($err -gt 0)                  { $verdict = "ATENCAO -- hunt.err tem $err linha(s)" }
elseif ($ev  -gt 0)                  { $verdict = "ACHOU EV_EDGE ($ev) -- revisar ANTES de qualquer operacao" }
elseif ($age -ge 0 -and $age -gt 90) { $verdict = "ATENCAO -- ultima batida ha ${age}s (loop pode ter travado)" }
elseif ($stall -gt 0)                { $verdict = "OK c/ ressalva -- houve $stall FEED_STALL (WS caiu/reconectou)" }
else                                 { $verdict = "OK -- vivo, ingerindo, sem EV_EDGE" }

$lines = @(
    "=== monitor_check  $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') ===",
    "VERDICT: $verdict",
    "pid=$np  alive=$([bool]$proc)  up_min=$up  rc=$rc  err=$err  hb_age_s=$age",
    "alertas=$nA  [$brk]",
    "ultima_batida: $hb"
)
$report = ($lines -join "`r`n")
Write-Output $report

if ($DelaySeconds -gt 0) {
    $rf = Join-Path $h ("timer_check_{0}.txt" -f (Get-Date -Format 'yyyyMMdd_HHmmss'))
    $report | Set-Content -Path $rf -Encoding UTF8
}
if ($Notify) {
    try {
        Add-Type -AssemblyName PresentationFramework
        [void][System.Windows.MessageBox]::Show($report, 'Monitor sintetico -- verificacao 30 min')
    } catch { }
}
