#!/bin/bash
# D52 continuous batch runner wrapper
cd "$(dirname "$0")"
while true; do
    echo "=== D52 batch started at $(date -u) ===" >> d52_continuous.log
    python3 d52_continuous.py >> d52_continuous.log 2>&1
    echo "=== D52 batch ended at $(date -u), sleeping 30s ===" >> d52_continuous.log
    sleep 30
done
