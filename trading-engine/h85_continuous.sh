#!/bin/bash
# H85 continuous wrapper — runs Velocity SWIFT subscriber in a loop
cd "$(dirname "$0")/h85_drift"
while true; do
    echo "=== H85 batch started at $(date -u) ===" >> h85_continuous.log
    npx tsx h85_swift_subscriber.ts >> h85_continuous.log 2>&1
    echo "=== H85 batch ended at $(date -u), sleeping 60s ===" >> h85_continuous.log
    sleep 60
done
