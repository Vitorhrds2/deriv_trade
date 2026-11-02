#!/bin/bash
# D95 continuous batch runner wrapper
cd "$(dirname "$0")"
while true; do
    echo "=== D95 batch started at $(date -u) ===" >> d95_continuous.log
    python3 d95_continuous.py >> d95_continuous.log 2>&1
    echo "=== D95 batch ended at $(date -u), sleeping 30s ===" >> d95_continuous.log
    sleep 30
done
