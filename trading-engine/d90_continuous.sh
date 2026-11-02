#!/bin/bash
# D90 continuous wrapper — runs long duration early sell with more pairs
cd "$(dirname "$0")"
while true; do
    echo "=== D90 batch started at $(date -u) ===" >> d90_continuous.log
    python3 d90_long_duration_early_sell.py \
        --output d90_live_20260712_results.jsonl \
        --state d90_live_20260712_state.json \
        --stats d90_live_20260712_stats.json \
        --threshold 1.5 \
        --pairs 50 \
        --durations 15m,1h \
        --live >> d90_continuous.log 2>&1
    echo "=== D90 batch ended at $(date -u), sleeping 60s ===" >> d90_continuous.log
    sleep 60
done
