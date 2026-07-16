param(
    [string]$KeyPath = "C:\Users\FDS\.aws\shadow-ab-demo-20260702.pem",
    [string]$HostName = "63.181.37.35",
    [string]$RemoteDir = "/home/ubuntu/te",
    [string]$StateJson = "strategy_rotation_pnl500_state.json",
    [string]$EventsJsonl = "strategy_rotation_pnl500_events.jsonl",
    [string]$PidFile = "logs/rotation_pnl500.pid",
    [int]$IntervalSeconds = 5,
    [int]$SshTimeoutSeconds = 12
)

$ErrorActionPreference = "Continue"
$Host.UI.RawUI.WindowTitle = "Rotation_PnL500_Frankfurt"

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
rotation = s.get("rotation", {})
counts = collections.Counter()
last_event = None
last_settled = None
latencies = []
switches = []

if events_path.exists():
    for raw in events_path.read_text(errors="ignore").splitlines():
        if not raw.strip():
            continue
        try:
            row = json.loads(raw)
        except Exception:
            continue
        event = row.get("event")
        counts[event] += 1
        if event in {"signal","buy","settled","block_guard_pause","loss_streak_pause","rotation_switch_out","rotation_switch_in","rotation_global_drawdown_stop","rotation_target_pnl_reached","rotation_target_trades_reached","runtime_timeout","error"}:
            last_event = row
        if event == "settled":
            last_settled = row
        if event == "buy" and row.get("latency_ms") is not None:
            latencies.append(float(row["latency_ms"]))
        if event in {"rotation_switch_out", "rotation_switch_in"}:
            switches.append(row)

blocked_until = float(m.get("blocked_until_ts") or 0.0)
blocked_remaining = max(0.0, blocked_until - time.time())
recent = [float(x) for x in m.get("recent_profits", [])[-8:]]
payload = {
    "now": time.strftime("%H:%M:%SZ", time.gmtime()),
    "pid": pid,
    "alive": alive,
    "updated_at": s.get("updated_at"),
    "status": s.get("status"),
    "model": m.get("id"),
    "model_status": m.get("status"),
    "phase": m.get("phase"),
    "model_trades": m.get("trades"),
    "model_wins": m.get("wins"),
    "model_losses": m.get("losses"),
    "model_pnl": m.get("pnl"),
    "model_peak": m.get("peak_pnl"),
    "model_dd": m.get("max_drawdown"),
    "global_trades": rotation.get("global_trades", 0),
    "global_pnl": rotation.get("global_pnl", 0.0),
    "global_peak": rotation.get("global_peak_pnl", 0.0),
    "global_dd": rotation.get("global_max_drawdown", 0.0),
    "target_trades": rotation.get("target_trades"),
    "target_pnl": rotation.get("target_pnl"),
    "switch_count": len(rotation.get("switches", [])),
    "blocked_reason": m.get("blocked_reason"),
    "blocked_remaining": round(blocked_remaining, 1),
    "recent8": round(sum(recent), 4) if recent else None,
    "lat_last": round(latencies[-1], 3) if latencies else None,
    "lat_avg": round(sum(latencies)/len(latencies), 3) if latencies else None,
    "signals": counts.get("signal", 0),
    "buys": counts.get("buy", 0),
    "settled": counts.get("settled", 0),
    "last_event": (last_event or {}).get("event"),
    "last_profit": (last_settled or {}).get("profit"),
    "last_contract": (last_settled or {}).get("contract_id"),
    "last_ts": (last_event or {}).get("ts"),
    "last_switch": switches[-1] if switches else None,
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

Write-Host "Rotation PnL500 Frankfurt | host=$HostName | refresh=${IntervalSeconds}s | Ctrl+C para sair" -ForegroundColor Cyan
Write-Host "Troca de modelo: devolucao de pico >= 25 ou pnl dos ultimos 8 trades <= -15. Real money bloqueado." -ForegroundColor DarkGray

while ($true) {
    try {
        $d = Invoke-RemoteSnapshot
        $gpnl = "{0:N2}" -f ([double]$d.global_pnl)
        $gdd = "{0:N2}" -f ([double]$d.global_dd)
        $mpnl = "{0:N2}" -f ([double]$d.model_pnl)
        $mdd = "{0:N2}" -f ([double]$d.model_dd)
        $lat = if ($null -ne $d.lat_last) { "$($d.lat_last)ms avg=$($d.lat_avg)ms" } else { "n/a" }
        $recent = if ($null -ne $d.recent8) { $d.recent8 } else { "n/a" }
        $line = "{0} alive={1} pid={2} global={3}/{4} pnl={5}/{6} dd={7} switches={8} | model={9} {10}tr pnl={11} dd={12} W/L={13}/{14} recent8={15} block={16} rem={17}s lat={18} last={19} profit={20}" -f `
            $d.now, $d.alive, $d.pid, $d.global_trades, $d.target_trades, $gpnl, $d.target_pnl, $gdd, $d.switch_count, $d.model, $d.model_trades, $mpnl, $mdd, $d.model_wins, $d.model_losses, $recent, $d.blocked_reason, $d.blocked_remaining, $lat, $d.last_event, $d.last_profit
        if ([double]$d.global_pnl -ge 0) {
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
