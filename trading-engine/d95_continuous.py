#!/usr/bin/env python3
"""D95 Deal Cancellation (1HZ100V) — continuous batch runner with rate-limit backoff."""
import asyncio, json, os, sys, time
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))
from deriv_client import DerivClient
from stats_utils import bootstrap_ci, wilson_ci

APP_ID = os.getenv("DERIV_APP_ID")
TOKEN = os.getenv("DERIV_API_TOKEN")
BATCH = int(os.getenv("D95_BATCH", "20"))
RESULTS_FILE = os.getenv("D95_RESULTS_FILE", "d95_deal_cancellation_live_results.jsonl")
INTER_TRIAL_S = 15.0
RATE_LIMIT_BACKOFF_S = 120.0
MAX_RETRIES = 5

from d95_deal_cancellation_live_1hz100v import run_trial, CONTRACT_TYPES

async def run_batch():
    client = DerivClient(app_id=APP_ID, api_token=TOKEN, use_demo=True)
    await client.connect()
    existing = 0
    if os.path.exists(RESULTS_FILE):
        with open(RESULTS_FILE) as f:
            existing = sum(1 for line in f if line.strip())
    start_i = existing
    print(f"  Existing trials: {existing}, starting from #{start_i}", flush=True)
    with open(RESULTS_FILE, "a") as f:
        for i in range(start_i, start_i + BATCH):
            ct = CONTRACT_TYPES[i % len(CONTRACT_TYPES)]
            rec = None
            rate_limited = False
            for attempt in range(MAX_RETRIES):
                try:
                    rec = await run_trial(client, i, ct)
                    if "error" in rec and "rate limit" in str(rec["error"]).lower():
                        rate_limited = True
                        print(f"  [{i}] {ct} rate limited (attempt {attempt+1}/{MAX_RETRIES}), waiting {RATE_LIMIT_BACKOFF_S}s...", flush=True)
                        await asyncio.sleep(RATE_LIMIT_BACKOFF_S)
                        continue
                    rate_limited = False
                    break
                except Exception as e:
                    rec = {"trial": i, "error": str(e), "contract_type": ct}
                    if "rate limit" in str(e).lower():
                        rate_limited = True
                        print(f"  [{i}] {ct} rate limited (attempt {attempt+1}/{MAX_RETRIES}), waiting {RATE_LIMIT_BACKOFF_S}s...", flush=True)
                        await asyncio.sleep(RATE_LIMIT_BACKOFF_S)
                        continue
                    rate_limited = False
                    break
            if rate_limited:
                print(f"  [{i}] {ct} skipped after {MAX_RETRIES} rate-limit retries, waiting 180s...", flush=True)
                await asyncio.sleep(180)
                continue
            if rec is None:
                rec = {"trial": i, "error": "max retries exceeded", "contract_type": ct}
            f.write(json.dumps(rec, default=str) + "\n")
            f.flush()
            if "error" in rec:
                print(f"  [{i}] {ct} ERRO: {rec['error']}", flush=True)
            else:
                print(f"  [{i}] {ct} cid={rec.get('contract_id')} fee=${rec.get('fee',0):.2f} action={rec.get('action')} realized=${rec.get('realized_value')}", flush=True)
            await asyncio.sleep(INTER_TRIAL_S)
    await client.disconnect()

    trades = []
    with open(RESULTS_FILE) as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    trades.append(json.loads(line))
                except:
                    pass
    nets = [float(t.get("realized_value", 0)) - float(t.get("fee", 0)) for t in trades if "error" not in t]
    n = len(nets)
    if n > 0:
        lo, mean, hi = bootstrap_ci(nets, n_boot=2000)
        wins = sum(1 for x in nets if x > 0)
        wr_lo, wr_hi = wilson_ci(wins, n)
        print(f"\n=== VERDICT (N={n}) ===", flush=True)
        print(f"EV/trade=${mean:+.4f} IC95%=[${lo:+.4f}, ${hi:+.4f}]", flush=True)
        print(f"WR={wins}/{n}={wins/n*100:.1f}% IC95%=[{wr_lo*100:.1f}%, {wr_hi*100:.1f}%]", flush=True)
        if lo > 0:
            print("STATUS: EDGE CONFIRMADO", flush=True)
        elif hi < 0:
            print("STATUS: SEM EDGE", flush=True)
        else:
            print("STATUS: INCONCLUSIVO", flush=True)

asyncio.run(run_batch())
