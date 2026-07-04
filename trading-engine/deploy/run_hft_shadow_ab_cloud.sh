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

start_process \
  hft_shadow_ab \
  logs/hft_shadow_ab.pid \
  logs/hft_shadow_ab.stdout.log \
  logs/hft_shadow_ab.stderr.log \
  .venv/bin/python3 hft_arbitrage_bot.py

export START_DISCORD_MONITOR="${START_DISCORD_MONITOR:-0}"

if [ "$START_DISCORD_MONITOR" = "1" ]; then
  start_process \
    cloud_shadow_discord_monitor \
    logs/cloud_shadow_discord_monitor.pid \
    logs/cloud_shadow_discord_monitor.stdout.log \
    logs/cloud_shadow_discord_monitor.stderr.log \
    .venv/bin/python3 cloud_shadow_discord_monitor.py
else
  echo "cloud_shadow_discord_monitor=disabled"
fi

echo "bot_pid=$(cat logs/hft_shadow_ab.pid)"
if [ -f logs/cloud_shadow_discord_monitor.pid ]; then
  echo "monitor_pid=$(cat logs/cloud_shadow_discord_monitor.pid)"
fi
