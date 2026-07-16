param(
    [string]$KeyPath = "C:\Users\FDS\.aws\shadow-ab-demo-20260702.pem",
    [string]$HostName = "63.181.37.35",
    [string]$RemoteDir = "/home/ubuntu/te",
    [string]$StateJson = "strategy_guardv2_1000_stress_state.json",
    [string]$EventsJsonl = "strategy_guardv2_1000_stress_events.jsonl",
    [string]$PidFile = "logs/guardv2_1000_stress.pid",
    [int]$IntervalSeconds = 5,
    [int]$SshTimeoutSeconds = 12
)

$ErrorActionPreference = "Continue"
$Host.UI.RawUI.WindowTitle = "GuardV2_Frankfurt_Heartbeat"

function Invoke-RemoteSnapshot {
    $remote = @"
cd $RemoteDir || exit 2
python3 - <<'PY'
import json, pathlib, subprocess, time, collections

state_path = pathlib.Path("$StateJson")
events_path = pathlib.Path("$EventsJsonl")
pid_path = pathlib.Path("$PidFile")
pid = pid_path.read_text().strip() if pid_path.exists() else ""
alive = bool(pid) and subprocess.call(["ps", "-p", pid], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL) == 0

s = json.load(open(state_path))
m = s["models"][s["current_model_index"]]
model_id = m.get("id")
counts = collections.Counter()
last_event = None
last_settled = None
latencies = []
region = "unknown"

if events_path.exists():
    for raw in events_path.read_text(errors="ignore").splitlines():
        if not raw.strip():
            continue
        try:
            row = json.loads(raw)
        except Exception:
            continue
        if row.get("event") == "infra_region_switch":
            region = row.get("to_region") or region
            continue
        if row.get("model_id") != model_id:
            continue
        counts[row.get("event")] += 1
        if row.get("event") in {"signal","buy","settled","block_guard_pause","loss_streak_pause","pivot","hard_drawdown_stop","runtime_timeout","error"}:
            last_event = row
        if row.get("event") == "settled":
            last_settled = row
        if row.get("event") == "buy" and row.get("latency_ms") is not None:
            latencies.append(float(row["latency_ms"]))

blocked_until = float(m.get("blocked_until_ts") or 0.0)
blocked_remaining = max(0.0, blocked_until - time.time())
payload = {
    "now": time.strftime("%H:%M:%SZ", time.gmtime()),
    "pid": pid,
    "alive": alive,
    "updated_at": s.get("updated_at"),
    "region": region,
    "model": model_id,
    "status": s.get("status"),
    "model_status": m.get("status"),
    "phase": m.get("phase"),
    "trades": m.get("trades"),
    "wins": m.get("wins"),
    "losses": m.get("losses"),
    "pnl": m.get("pnl"),
    "peak": m.get("peak_pnl"),
    "dd": m.get("max_drawdown"),
    "blocked_reason": m.get("blocked_reason"),
    "blocked_remaining": round(blocked_remaining, 1),
    "lat_last": round(latencies[-1], 3) if latencies else None,
    "lat_avg": round(sum(latencies)/len(latencies), 3) if latencies else None,
    "signals": counts.get("signal", 0),
    "buys": counts.get("buy", 0),
    "settled": counts.get("settled", 0),
    "last_event": (last_event or {}).get("event"),
    "last_profit": (last_settled or {}).get("profit"),
    "last_contract": (last_settled or {}).get("contract_id"),
    "last_ts": (last_event or {}).get("ts"),
}
print(json.dumps(payload, sort_keys=True))
PY
"@

    $psi = New-Object System.Diagnostics.ProcessStartInfo
    $psi.FileName = "ssh.exe"
    $psi.UseShellExecute = $false
    $psi.RedirectStandardInput = $true
    $psi.RedirectStandardOutput = $true
    $psi.RedirectStandardError = $true
    $psi.Arguments = "-i `"$KeyPath`" -o BatchMode=yes -o ConnectTimeout=8 -o ServerAliveInterval=5 -o ServerAliveCountMax=1 -o StrictHostKeyChecking=no -o UserKnownHostsFile=NUL -o LogLevel=ERROR ubuntu@$HostName `"sed 's/\r$//' | bash`""

    $proc = New-Object System.Diagnostics.Process
    $proc.StartInfo = $psi
    [void]$proc.Start()
    $proc.StandardInput.WriteLine($remote)
    $proc.StandardInput.Close()

    if (-not $proc.WaitForExit($SshTimeoutSeconds * 1000)) {
        try { $proc.Kill() } catch {}
        throw "ssh_timeout_${SshTimeoutSeconds}s"
    }

    $stdout = $proc.StandardOutput.ReadToEnd()
    $stderr = $proc.StandardError.ReadToEnd()
    if ($proc.ExitCode -ne 0) {
        throw "ssh_exit_$($proc.ExitCode): $stderr"
    }
    $line = $stdout -split "`r?`n" | Where-Object { $_.Trim().Length -gt 0 } | Select-Object -Last 1
    if (-not $line) {
        throw "empty_snapshot"
    }
    return ($line | ConvertFrom-Json)
}

Write-Host "GuardV2 Frankfurt heartbeat | host=$HostName | refresh=${IntervalSeconds}s | ctrl+c para sair" -ForegroundColor Cyan
Write-Host "Cada linha nova confirma que o monitor local esta vivo. O runner pode ficar em pausa, mas o heartbeat continua." -ForegroundColor DarkGray

while ($true) {
    try {
        $d = Invoke-RemoteSnapshot
        $pnl = "{0:N2}" -f ([double]$d.pnl)
        $dd = "{0:N2}" -f ([double]$d.dd)
        $lat = if ($null -ne $d.lat_last) { "$($d.lat_last)ms avg=$($d.lat_avg)ms" } else { "n/a" }
        $line = "{0} alive={1} pid={2} {3} {4}/{5} W/L={6}/{7} pnl={8} dd={9} block={10} rem={11}s lat={12} last={13} profit={14}" -f `
            $d.now, $d.alive, $d.pid, $d.region, $d.trades, 1000, $d.wins, $d.losses, $pnl, $dd, $d.blocked_reason, $d.blocked_remaining, $lat, $d.last_event, $d.last_profit
        if ([double]$d.pnl -ge 0) {
            Write-Host $line -ForegroundColor Green
        } else {
            Write-Host $line -ForegroundColor Yellow
        }
    } catch {
        $stamp = (Get-Date).ToUniversalTime().ToString("HH:mm:ssZ")
        Write-Host "$stamp monitor_error=$_" -ForegroundColor Red
    }
    Start-Sleep -Seconds $IntervalSeconds
}
