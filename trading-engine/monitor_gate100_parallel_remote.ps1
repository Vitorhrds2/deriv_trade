param(
    [string]$KeyPath = "C:\Users\FDS\.aws\shadow-ab-demo-20260702.pem",
    [string]$HostName = "43.206.136.101",
    [string]$RemoteDir = "/home/ubuntu/te",
    [string]$StateJson = "strategy_gate100_parallel_pnl500_state.json",
    [string]$EventsJsonl = "strategy_gate100_parallel_pnl500_events.jsonl",
    [string]$PidFile = "logs/gate100_parallel_pnl500.pid",
    [string]$Title = "Gate100 Parallel PnL500 Remote Monitor",
    [int]$IntervalSeconds = 5
)

$ErrorActionPreference = "Continue"

while ($true) {
    $remote = @"
cd $RemoteDir || exit 2
python3 - <<'PY'
import json, pathlib, time, subprocess, collections
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
events = []
counts = collections.Counter()
if events_path.exists():
    for raw in events_path.read_text().splitlines():
        if not raw.strip():
            continue
        try:
            row = json.loads(raw)
        except Exception:
            continue
        counts[row.get("event")] += 1
        if row.get("event") in {
            "signal","buy","settled","pivot","target_pnl_reached",
            "block_guard_pause","loss_streak_pause","target_pnl_trailing_pause",
            "global_kill_loss","runtime_timeout"
        }:
            events.append({k: row.get(k) for k in [
                "ts","event","model_id","contract_type","stake","contract_id",
                "profit","pnl","global_pnl","trades","wins","losses","reason",
                "trade_no","symbol"
            ] if k in row})
leaderboard = s.get("leaderboard") or []
payload = {
    "now": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    "pid": pid,
    "alive": alive,
    "elapsed": elapsed,
    "updated_at": s.get("updated_at"),
    "job_id": s.get("job_id"),
    "status": s.get("status"),
    "target_pnl": s.get("target_pnl"),
    "stake": s.get("stake_override"),
    "global": s.get("global"),
    "event_counts": dict(counts),
    "leaderboard": leaderboard,
    "recent_events": events[-12:],
}
print(json.dumps(payload, sort_keys=True))
PY
"@

    $json = $remote | ssh -i $KeyPath -o BatchMode=yes -o ConnectTimeout=20 -o StrictHostKeyChecking=no -o UserKnownHostsFile=NUL ubuntu@$HostName "sed 's/\r$//' | bash"
    Clear-Host
    Write-Host $Title -ForegroundColor Cyan
    Write-Host "Host: $HostName | Refresh: ${IntervalSeconds}s | Ctrl+C para sair"
    Write-Host ""
    try {
        $data = $json | Select-Object -Last 1 | ConvertFrom-Json
        if ($data.error) {
            Write-Host "Erro remoto: $($data.error)" -ForegroundColor Red
        } else {
            $globalPnl = [double]$data.global.pnl
            $pnlColor = if ($globalPnl -ge 0) { "Green" } else { "Red" }
            Write-Host "Now UTC:       $($data.now)"
            Write-Host "Updated:       $($data.updated_at)"
            Write-Host "PID:           $($data.pid) alive=$($data.alive) elapsed='$($data.elapsed)'"
            Write-Host "Job:           $($data.job_id)"
            Write-Host "Status:        $($data.status)"
            Write-Host "Target/Stake:  $($data.target_pnl) / $($data.stake)"
            Write-Host "Global PnL:    $($data.global.pnl)" -ForegroundColor $pnlColor
            Write-Host "Global W/L:    $($data.global.wins)/$($data.global.losses) trades=$($data.global.trades) open=$($data.global.open_contracts)"
            Write-Host "Global DD:     $($data.global.max_drawdown)"
            Write-Host "Winner:        $($data.global.winner_model_id)"
            Write-Host "Events:        signal=$($data.event_counts.signal) buy=$($data.event_counts.buy) settled=$($data.event_counts.settled) pivot=$($data.event_counts.pivot)"
            Write-Host ""
            Write-Host "Leaderboard:" -ForegroundColor Green
            foreach ($row in $data.leaderboard) {
                $wr = if ($null -eq $row.wr) { "-" } else { "{0:P1}" -f [double]$row.wr }
                $line = "{0,-58} {1,10} T={2,4} W/L={3,3}/{4,-3} WR={5,6} DD={6,8} {7}" -f `
                    $row.model_id, $row.pnl, $row.trades, $row.wins, $row.losses, $wr, $row.max_drawdown, $row.status
                $color = if ([double]$row.pnl -ge 0) { "Green" } else { "Red" }
                Write-Host $line -ForegroundColor $color
            }
            Write-Host ""
            Write-Host "Recent material events:" -ForegroundColor Yellow
            foreach ($event in $data.recent_events) {
                Write-Host ($event | ConvertTo-Json -Compress)
            }
        }
    } catch {
        Write-Host "Falha ao parsear resposta remota:" -ForegroundColor Red
        Write-Host $json
    }
    Start-Sleep -Seconds $IntervalSeconds
}
