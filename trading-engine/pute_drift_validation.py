"""
D82 — PUTE Directional Drift Validation
=========================================
D77 encontrou PUTE com P(win)=69% (1m) e 92% (5m) em Monte Carlo com 5000 ticks.
Pode ser viés de amostra (downtrend no período) ou drift real.

D46 (N=190k) não encontrou viés direcional significativo.
Mas D46 testou CALL/PUT, não CALLE/PUTE especificamente.

Validação: executar 20 trades reais PUTE 5t e medir WR.
Break-even: 52.1% (payout 1.920).

Se WR > 55% com N=20, vale investigar mais.
Se WR ~50%, confirmado viés de amostra.
"""
import asyncio
import json
import os
import sys
import time
import random
import statistics
from datetime import datetime, timezone

from dotenv import load_dotenv

for _p in [os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")]:
    if os.path.exists(_p):
        load_dotenv(_p)
        break

from deriv_client import DerivClient

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

APP_ID = os.getenv("DERIV_APP_ID")
TOKEN = os.getenv("DERIV_API_TOKEN")

SYMBOL = "1HZ10V"
STAKE = 1.00
DURATION = 5
DURATION_UNIT = "t"
N_TRIALS = 20

RESULTS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            "pute_drift_validation_results.jsonl")
STATS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                          "pute_drift_validation_stats.json")


def bootstrap_ci(data, n_boot=5000, confidence=0.95):
    if len(data) < 2:
        return 0, 0, 0
    means = []
    for _ in range(n_boot):
        sample = [random.choice(data) for _ in range(len(data))]
        means.append(statistics.mean(sample))
    means.sort()
    alpha = (1 - confidence) / 2
    lo = means[int(n_boot * alpha)]
    hi = means[int(n_boot * (1 - alpha))]
    return statistics.mean(data), lo, hi


async def main():
    print("=" * 90)
    print("D82 — PUTE Directional Drift Validation")
    print(f"  Symbol: {SYMBOL} | Duration: {DURATION}{DURATION_UNIT} | Stake: ${STAKE}")
    print(f"  Trials: {N_TRIALS} | Break-even WR: 52.1% (payout 1.920)")
    print("=" * 90)

    client = DerivClient(app_id=APP_ID, api_token=TOKEN, use_demo=True)
    await client.connect()
    print(f"  Conectado. Conta: {client.account_id}")

    results = []

    for i in range(N_TRIALS):
        rec = {"trial": i, "ts": datetime.now(timezone.utc).isoformat()}

        prop = await client.send_request({
            "proposal": 1,
            "amount": STAKE,
            "basis": "stake",
            "contract_type": "PUTE",
            "currency": "USD",
            "underlying_symbol": SYMBOL,
            "duration": DURATION,
            "duration_unit": DURATION_UNIT,
        })

        if "error" in prop:
            rec["error"] = prop["error"].get("message", "")
            print(f"  [#{i}] proposal erro: {rec['error']}")
            results.append(rec)
            await asyncio.sleep(1)
            continue

        proposal_id = prop["proposal"]["id"]
        payout = float(prop["proposal"].get("payout", 0))
        rec["payout"] = payout

        buy = await client.buy_contract(proposal_id, price=STAKE)
        if "error" in buy:
            rec["error"] = buy["error"].get("message", "")
            print(f"  [#{i}] buy erro: {rec['error']}")
            results.append(rec)
            await asyncio.sleep(1)
            continue

        contract_id = buy["buy"]["contract_id"]
        rec["contract_id"] = contract_id

        # Wait for settle
        t0 = time.time()
        while time.time() - t0 < 30:
            await asyncio.sleep(0.5)
            poc = await client.send_request({
                "proposal_open_contract": 1,
                "contract_id": contract_id,
            })
            poc_data = poc.get("proposal_open_contract", {})
            if poc_data.get("is_sold", 0):
                await asyncio.sleep(0.5)
                poc2 = await client.send_request({
                    "proposal_open_contract": 1,
                    "contract_id": contract_id,
                })
                poc2_data = poc2.get("proposal_open_contract", poc_data)
                profit = float(poc2_data.get("profit", 0))
                is_won = poc2_data.get("is_won")
                if is_won is None:
                    is_won = 1 if profit > 0 else 0
                rec["profit"] = profit
                rec["is_won"] = int(is_won)
                won_str = "WON" if is_won else "LOST"
                print(f"  [#{i}] {won_str} profit=${profit:+.4f}")
                break

        results.append(rec)
        with open(RESULTS_FILE, "a") as f:
            f.write(json.dumps(rec, default=str) + "\n")
        await asyncio.sleep(1)

    # Analysis
    valid = [r for r in results if r.get("profit") is not None]
    profits = [r["profit"] for r in valid]
    wins = sum(1 for p in profits if p > 0)
    wr = wins / len(profits) if profits else 0
    ev = statistics.mean(profits) if profits else 0
    ev_mean, ci_lo, ci_hi = bootstrap_ci(profits)

    print(f"\n{'='*90}")
    print("  VEREDITO FINAL — PUTE DIRECTIONAL DRIFT")
    print(f"{'='*90}")
    print(f"  N={len(valid)} WR={wr*100:.0f}% EV=${ev:+.4f}")
    print(f"  CI95%[${ci_lo:+.4f},${ci_hi:+.4f}]")
    print(f"  Break-even WR: 52.1%")

    if wr > 0.55 and ci_lo > 0:
        print(f"  *** DRIFT CONFIRMADO — PUTE tem edge direcional!")
    elif wr > 0.55:
        print(f"  Sinal positivo mas CI cruza zero — precisa mais N")
    else:
        print(f"  WR ~50% — viés de amostra confirmado, sem drift real")

    stats = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "n": len(valid),
        "wr": wr,
        "ev": ev,
        "ci95": [ci_lo, ci_hi],
    }
    with open(STATS_FILE, "w") as f:
        json.dump(stats, f, indent=2)

    await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
