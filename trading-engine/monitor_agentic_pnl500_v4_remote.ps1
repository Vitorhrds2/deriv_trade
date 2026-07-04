param(
    [string]$KeyPath = "C:\Users\FDS\.aws\shadow-ab-demo-20260702.pem",
    [string]$HostName = "43.206.136.101",
    [string]$RemoteDir = "/home/ubuntu/te",
    [string]$StateJson = "strategy_agentic_pnl500_v4_state.json",
    [string]$EventsJsonl = "strategy_agentic_pnl500_v4_events.jsonl",
    [string]$PidFile = "logs/agentic_pnl500_v4.pid",
    [string]$Title = "Agentic PnL500 Remote Monitor",
    [int]$IntervalSeconds = 5
)

$ErrorActionPreference = "Continue"
$lastEventLines = 0

while ($true) {
    $remote = @"
cd $RemoteDir || exit 2
python3 - <<'PY'
import json, pathlib, time, os, subprocess
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
i = s.get("current_model_index")
m = s["models"][i]
blocked_remaining = max(0.0, float(m.get("blocked_until_ts") or 0) - time.time())
agent_status = m.get("last_agent_status") or {}
rules = agent_status.get("rules") or []
positive_rules = [
    {
        "rule_id": row.get("rule_id"),
        "samples": row.get("samples"),
        "score": row.get("score"),
        "eligible": row.get("eligible"),
        "emitted": row.get("currently_emitted"),
    }
    for row in rules
    if float(row.get("score") or 0) > 0
]
eligible_rules = [
    {
        "rule_id": row.get("rule_id"),
        "samples": row.get("samples"),
        "score": row.get("score"),
        "emitted": row.get("currently_emitted"),
    }
    for row in rules
    if row.get("eligible")
]
positive_rules = sorted(positive_rules, key=lambda row: (float(row.get("score") or 0), int(row.get("samples") or 0)), reverse=True)[:6]
eligible_rules = sorted(eligible_rules, key=lambda row: (float(row.get("score") or 0), int(row.get("samples") or 0)), reverse=True)[:6]
events = []
line_count = 0
material = {"signal","buy","settled","agent_rule_quarantine","block_guard_pause","loss_streak_pause","pivot","target_pnl_reached","runtime_timeout","post100_complete","passed_100","promote_post100_stake"}
if events_path.exists():
    for raw in events_path.read_text().splitlines():
        if not raw.strip():
            continue
        line_count += 1
        try:
            row = json.loads(raw)
        except Exception:
            continue
        if row.get("event") in material:
            events.append({k: row.get(k) for k in [
                "ts","event","model_id","phase","rule_id","agent_rule_id","contract_type","stake",
                "contract_id","buy_price","profit","pnl","trades","wins","losses","reason",
                "score","samples","agent_rule_score","agent_rule_samples"
            ] if k in row})
payload = {
    "now": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    "pid": pid,
    "alive": alive,
    "elapsed": elapsed,
    "updated_at": s.get("updated_at"),
    "job_id": s.get("job_id"),
    "status": s.get("status"),
    "model": m.get("id"),
    "model_status": m.get("status"),
    "phase": m.get("phase"),
    "trades": m.get("trades"),
    "wins": m.get("wins"),
    "losses": m.get("losses"),
    "pnl": m.get("pnl"),
    "peak": m.get("peak_pnl"),
    "max_drawdown": m.get("max_drawdown"),
    "blocked_reason": m.get("blocked_reason"),
    "blocked_remaining_sec": round(blocked_remaining, 1),
    "pivot_reason": m.get("pivot_reason"),
    "agent_emitted_count": agent_status.get("emitted_count"),
    "agent_eligible_count": agent_status.get("eligible_count"),
    "agent_best_rule": agent_status.get("best_rule"),
    "agent_max_samples": max([int(row.get("samples") or 0) for row in rules], default=0),
    "agent_last_consensus": m.get("last_agent_consensus"),
    "agent_positive_rules": positive_rules,
    "agent_eligible_rules": eligible_rules,
    "line_count": line_count,
    "recent_events": events[-8:],
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
            $pnlColor = if ([double]$data.pnl -ge 0) { "Green" } else { "Red" }
            Write-Host "Now UTC:      $($data.now)"
            Write-Host "Updated:      $($data.updated_at)"
            Write-Host "PID:          $($data.pid) alive=$($data.alive) elapsed='$($data.elapsed)'"
            Write-Host "Job:          $($data.job_id)"
            Write-Host "Model:        $($data.model)"
            Write-Host "Status:       $($data.status) / $($data.model_status) / $($data.phase)"
            Write-Host "Trades:       $($data.trades) | W/L $($data.wins)/$($data.losses)"
            Write-Host "PnL:          $($data.pnl)" -ForegroundColor $pnlColor
            Write-Host "Peak/DD:      $($data.peak) / $($data.max_drawdown)"
            Write-Host "Blocked:      $($data.blocked_reason) | remaining $($data.blocked_remaining_sec)s"
            Write-Host "Pivot:        $($data.pivot_reason)"
            Write-Host "Agent gate:   emitted=$($data.agent_emitted_count) eligible=$($data.agent_eligible_count) max_samples=$($data.agent_max_samples)"
            $best = $data.agent_best_rule
            if ($best) {
                Write-Host "Best rule:    $($best.rule_id) samples=$($best.samples) score=$($best.score) eligible=$($best.eligible)"
            }
            if ($data.agent_last_consensus) {
                Write-Host "Consensus:    $($data.agent_last_consensus.key) rules=$($data.agent_last_consensus.rules) score=$($data.agent_last_consensus.score)"
            } else {
                Write-Host "Consensus:    none"
            }
            Write-Host "Event lines:  $($data.line_count)"
            Write-Host ""
            Write-Host "Eligible rules:" -ForegroundColor Green
            foreach ($rule in $data.agent_eligible_rules) {
                Write-Host (($rule | ConvertTo-Json -Compress))
            }
            if (-not $data.agent_eligible_rules -or $data.agent_eligible_rules.Count -eq 0) {
                Write-Host "(none)"
            }
            Write-Host ""
            Write-Host "Positive paper rules:" -ForegroundColor Green
            foreach ($rule in $data.agent_positive_rules) {
                Write-Host (($rule | ConvertTo-Json -Compress))
            }
            if (-not $data.agent_positive_rules -or $data.agent_positive_rules.Count -eq 0) {
                Write-Host "(none)"
            }
            Write-Host ""
            Write-Host "Recent material events:" -ForegroundColor Yellow
            foreach ($event in $data.recent_events) {
                $line = ($event | ConvertTo-Json -Compress)
                Write-Host $line
            }
            $lastEventLines = [int]$data.line_count
        }
    } catch {
        Write-Host "Falha ao parsear resposta remota:" -ForegroundColor Red
        Write-Host $json
    }
    Start-Sleep -Seconds $IntervalSeconds
}
