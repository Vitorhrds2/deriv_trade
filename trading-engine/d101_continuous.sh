#!/bin/bash
# D101 continuous wrapper — runs barrier proximity edge in a loop
cd "$(dirname "$0")"
# Load .env
if [ -f .env ]; then
    export $(grep -v '^#' .env | xargs)
fi
while true; do
    echo "=== D101 batch started at $(date -u) ===" >> d101_continuous.log
    python3 d101_barrier_proximity_edge.py --trials 10 --symbol 1HZ10V --output d101_barrier_proximity_results.json >> d101_continuous.log 2>&1
    echo "=== D101 batch ended at $(date -u), sleeping 300s ===" >> d101_continuous.log
    sleep 300
done
