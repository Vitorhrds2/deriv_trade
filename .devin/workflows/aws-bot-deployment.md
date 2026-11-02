---
description: How to deploy and manage trading bots on AWS eu-central-1b for Deriv strategies
---

# AWS Bot Deployment

## Connection

```bash
ssh -o StrictHostKeyChecking=no -o ConnectTimeout=15 -i /Users/vitorhrds/Downloads/hft-aws-key.pem ubuntu@18.199.174.178
```

## Tmux Sessions (as of Jul 15, 2026)

| Session | Script | Status |
|---|---|---|
| d52_cancellation | d52_continuous.py | Running |
| d95_cancellation | d95_continuous.py | Running |
| d90_earlysell | d90_earlysell_probe.py | Running |
| d101_barrier | d101_barrier_proximity_edge.py | Running |
| d37_outflow | exchange_outflow_scan.py | Running (read-only) |
| anomaly_monitor | synthetic_anomaly_monitor.py | Running (read-only) |
| d106_pricing | d106_pricing_anomaly_monitor.py | Running (trades) |
| aggressive_supervisor | — | Running |
| status_api | status_api.py | Running |
| telegram_relay | telegram_anomaly_relay.py | Running |

## Deploying a New Bot

1. Copy script to AWS: `scp -i /Users/vitorhrds/Downloads/hft-aws-key.pem script.py ubuntu@18.199.174.178:~/trading-engine/`
2. SSH in and create tmux session: `tmux new -s dXX_name`
3. Run: `cd ~/trading-engine && PYTHONUNBUFFERED=1 python3 script.py 2>&1 | tee dXX.log`
4. Detach: `Ctrl+B, D`
5. Monitor: `tmux capture-pane -t dXX_name -p | tail -30`

## Checking Bot Status

```bash
# List sessions
tmux ls

# Check specific bot output
tmux capture-pane -t dXX_name -p | tail -50

# Check process
ps aux | grep dXX | grep -v grep

# Check results file
wc -l ~/trading-engine/dXX_results.jsonl
tail -5 ~/trading-engine/dXX_results.jsonl
```

## Stopping a Bot

```bash
# Kill specific tmux session
tmux kill-session -t dXX_name

# Or send Ctrl+C to the pane
tmux send-keys -t dXX_name C-c
```
