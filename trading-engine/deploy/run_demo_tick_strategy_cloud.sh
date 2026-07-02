#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."
mkdir -p logs

if [ ! -f .env ]; then
  echo "missing .env"
  exit 1
fi

if [ ! -x .venv/bin/python3 ]; then
  if ! python3 -m venv .venv; then
    echo "python venv unavailable; installing python3-venv"
    sudo apt-get update -y
    sudo apt-get install -y python3-venv python3-pip
    python3 -m venv .venv
  fi
fi

.venv/bin/pip install -q --upgrade pip
.venv/bin/pip install -q -r requirements.txt

start_process() {
  local name="$1"
  local pid_file="$2"
  local stdout_file="$3"
  local stderr_file="$4"
  shift 4

  if [ -f "$pid_file" ] && kill -0 "$(cat "$pid_file")" 2>/dev/null; then
    echo "${name}_already_running=$(cat "$pid_file")"
    return
  fi

  echo "starting ${name}"
  nohup "$@" > "$stdout_file" 2> "$stderr_file" &
  echo $! > "$pid_file"
}

export JOB_ID="${JOB_ID:-JOB-20260702-002}"
export DEMO_TICK_SYMBOL="${DEMO_TICK_SYMBOL:-1HZ100V}"
export DEMO_TICK_STAKE="${DEMO_TICK_STAKE:-1}"
export DEMO_TICK_SIGNAL_STREAK="${DEMO_TICK_SIGNAL_STREAK:-2}"
export DEMO_TICK_MAX_TRADES="${DEMO_TICK_MAX_TRADES:-5}"
export DEMO_TICK_MAX_DEMO_LOSS="${DEMO_TICK_MAX_DEMO_LOSS:-10}"
export DEMO_TICK_MAX_RUNTIME_SECONDS="${DEMO_TICK_MAX_RUNTIME_SECONDS:-900}"
export DEMO_TICK_LOG_PATH="${DEMO_TICK_LOG_PATH:-demo_tick_strategy.log}"
export DEMO_TICK_LEDGER_JSONL="${DEMO_TICK_LEDGER_JSONL:-demo_tick_strategy_trades.jsonl}"
export START_DISCORD_MONITOR="${START_DISCORD_MONITOR:-0}"

start_process \
  demo_tick_strategy \
  logs/demo_tick_strategy.pid \
  logs/demo_tick_strategy.stdout.log \
  logs/demo_tick_strategy.stderr.log \
  .venv/bin/python3 demo_tick_strategy_runner.py

export HFT_LOG_PATH="$DEMO_TICK_LOG_PATH"
export DISCORD_HEARTBEAT_SECONDS="${DISCORD_HEARTBEAT_SECONDS:-300}"

if [ "$START_DISCORD_MONITOR" = "1" ]; then
  start_process \
    demo_tick_strategy_discord_monitor \
    logs/demo_tick_strategy_discord_monitor.pid \
    logs/demo_tick_strategy_discord_monitor.stdout.log \
    logs/demo_tick_strategy_discord_monitor.stderr.log \
    .venv/bin/python3 cloud_shadow_discord_monitor.py
else
  echo "demo_tick_strategy_discord_monitor=disabled"
fi

echo "demo_tick_strategy_pid=$(cat logs/demo_tick_strategy.pid)"
if [ -f logs/demo_tick_strategy_discord_monitor.pid ]; then
  echo "demo_tick_strategy_discord_monitor_pid=$(cat logs/demo_tick_strategy_discord_monitor.pid)"
fi
