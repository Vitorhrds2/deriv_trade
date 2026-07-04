param(
    [string]$KeyPath = "C:\Users\FDS\.aws\shadow-ab-demo-20260702.pem",
    [string]$HostName = "43.206.136.101",
    [string]$RemoteDir = "/home/ubuntu/te",
    [string]$StateJson = "strategy_guardv2_1000_stress_state.json",
    [string]$EventsJsonl = "strategy_guardv2_1000_stress_events.jsonl",
    [string]$PidFile = "logs/guardv2_1000_stress.pid",
    [string]$Title = "GuardV2 1000 Stress Monitor",
    [int]$IntervalSeconds = 5,
    [switch]$Once
)

$ErrorActionPreference = "Continue"
$Host.UI.RawUI.WindowTitle = $Title

function Format-Usd {
    param([object]$Value)
    if ($null -eq $Value) { return "n/a" }
    $number = [double]$Value
    if ($number -ge 0) { return ('+${0:N2}' -f $number) }
    return ('-${0:N2}' -f ([math]::Abs($number)))
}

function Get-RemoteSnapshot {
    $remoteScript = @"
cd $RemoteDir || exit 2
python3 - <<'PY'
import json, pathlib, subprocess, collections, time

state_path = pathlib.Path("$StateJson")
events_path = pathlib.Path("$EventsJsonl")
pid_path = pathlib.Path("$PidFile")

pid = pid_path.read_text().strip() if pid_path.exists() else ""
alive = False
elapsed = ""
if pid:
    try:
        out = subprocess.check_output(["ps", "-p", pid, "-o", "etime=", "-o", "stat="], text=True).strip()
        if out:
            alive = True
            elapsed = " ".join(out.split())
    except Exception:
        pass

if not state_path.exists():
    print(json.dumps({"error": "state_missing", "pid": pid, "alive": alive}))
    raise SystemExit

s = json.load(open(state_path))
idx = s.get("current_model_index")
models = s.get("models") or []
m = models[idx] if isinstance(idx, int) and 0 <= idx < len(models) else {}

counts = collections.Counter()
recent = []
last_settlement = None
latencies = []
material = {
    "signal", "buy", "settled", "block_guard_pause", "loss_streak_pause",
    "passed_30", "passed_100", "passed_1000", "pivot", "hard_drawdown_stop",
    "runtime_timeout", "runner_error"
}

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
        if event == "buy" and row.get("latency_ms") is not None:
            latencies.append(float(row.get("latency_ms")))
        if event == "settled":
            last_settlement = row
        if event in material:
            recent.append(row)

trades = int(m.get("trades") or 0)
wins = int(m.get("wins") or 0)
losses = int(m.get("losses") or 0)
target = int(s.get("target_trades") or 0)
wr = (wins / trades * 100.0) if trades else 0.0
progress = (trades / target * 100.0) if target else 0.0
blocked_until = float(m.get("blocked_until_ts") or 0.0)
blocked_remaining = max(0.0, blocked_until - time.time())

def trimmed(row):
    keep = [
        "ts", "event", "trade_no", "trades", "contract_type", "direction",
        "stake", "profit", "pnl", "contract_id", "reason", "pause_seconds",
        "latency_ms", "move"
    ]
    return {k: row.get(k) for k in keep if k in row}

payload = {
    "now": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    "pid": pid,
    "alive": alive,
    "elapsed": elapsed,
    "job_id": s.get("job_id"),
    "state_status": s.get("status"),
    "updated_at": s.get("updated_at"),
    "model_id": m.get("id"),
    "model_status": m.get("status"),
    "phase": m.get("phase"),
    "stake": s.get("stake_override"),
    "target_trades": target,
    "trades": trades,
    "progress_pct": round(progress, 2),
    "wins": wins,
    "losses": losses,
    "win_rate_pct": round(wr, 2),
    "pnl": m.get("pnl"),
    "peak_pnl": m.get("peak_pnl"),
    "max_drawdown": m.get("max_drawdown"),
    "hard_drawdown_stop": s.get("hard_drawdown_stop"),
    "blocked_reason": m.get("blocked_reason"),
    "blocked_remaining_sec": round(blocked_remaining, 1),
    "last_error": m.get("last_error"),
    "event_counts": dict(counts),
    "latency_last_ms": round(latencies[-1], 3) if latencies else None,
    "latency_avg_ms": round(sum(latencies) / len(latencies), 3) if latencies else None,
    "last_settlement": trimmed(last_settlement) if last_settlement else None,
    "recent_events": [trimmed(row) for row in recent[-8:]],
}
print(json.dumps(payload, sort_keys=True))
PY
"@

    $output = $remoteScript | ssh -i $KeyPath `
        -o BatchMode=yes `
        -o ConnectTimeout=20 `
        -o LogLevel=ERROR `
        -o StrictHostKeyChecking=no `
        -o UserKnownHostsFile=NUL `
        ubuntu@$HostName "sed 's/\r$//' | bash"

    return ($output | Select-Object -Last 1)
}

function Show-Snapshot {
    param([object]$Data)

    Clear-Host
    Write-Host $Title -ForegroundColor Cyan
    Write-Host "Host: $HostName | Refresh: ${IntervalSeconds}s | Ctrl+C para sair"
    Write-Host ""

    if ($Data.error) {
        Write-Host "Erro remoto: $($Data.error) | pid=$($Data.pid) alive=$($Data.alive)" -ForegroundColor Red
        return
    }

    $pnlColor = if ([double]$Data.pnl -ge 0) { "Green" } else { "Red" }
    $aliveColor = if ($Data.alive) { "Green" } else { "Red" }

    Write-Host "Now UTC:       $($Data.now)"
    Write-Host "Updated:       $($Data.updated_at)"
    Write-Host "PID:           $($Data.pid) alive=$($Data.alive) elapsed='$($Data.elapsed)'" -ForegroundColor $aliveColor
    Write-Host "Job:           $($Data.job_id)"
    Write-Host "Model:         $($Data.model_id)"
    Write-Host "Status:        $($Data.state_status) / $($Data.model_status) / $($Data.phase)"
    Write-Host "Stake/Target:  `$$($Data.stake) | $($Data.trades)/$($Data.target_trades) ($($Data.progress_pct)%)"
    Write-Host "W/L/WR:        $($Data.wins)/$($Data.losses) | $($Data.win_rate_pct)%"
    Write-Host "PnL:           $(Format-Usd $Data.pnl)" -ForegroundColor $pnlColor
    Write-Host "Peak/DD/Stop:  $(Format-Usd $Data.peak_pnl) / $(Format-Usd $Data.max_drawdown) / -`$$($Data.hard_drawdown_stop)"
    Write-Host "Blocked:       $($Data.blocked_reason) | remaining $($Data.blocked_remaining_sec)s"
    Write-Host "Latency:       last=$($Data.latency_last_ms)ms avg=$($Data.latency_avg_ms)ms"
    Write-Host "Events:        signal=$($Data.event_counts.signal) buy=$($Data.event_counts.buy) settled=$($Data.event_counts.settled) pauses=$($Data.event_counts.block_guard_pause + $Data.event_counts.loss_streak_pause)"

    if ($Data.last_error) {
        Write-Host "Last error:    $($Data.last_error)" -ForegroundColor Red
    }

    Write-Host ""
    Write-Host "Last settlement:" -ForegroundColor Green
    if ($Data.last_settlement) {
        Write-Host ($Data.last_settlement | ConvertTo-Json -Compress)
    } else {
        Write-Host "(none)"
    }

    Write-Host ""
    Write-Host "Recent events:" -ForegroundColor Yellow
    foreach ($event in $Data.recent_events) {
        Write-Host ($event | ConvertTo-Json -Compress)
    }
}

do {
    try {
        $json = Get-RemoteSnapshot
        $data = $json | ConvertFrom-Json
        Show-Snapshot -Data $data
    } catch {
        Clear-Host
        Write-Host $Title -ForegroundColor Cyan
        Write-Host "Falha ao ler snapshot remoto:" -ForegroundColor Red
        Write-Host $_
    }

    if ($Once) {
        break
    }
    Start-Sleep -Seconds $IntervalSeconds
} while ($true)
