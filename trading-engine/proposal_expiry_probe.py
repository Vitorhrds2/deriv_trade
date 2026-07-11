"""
D74 — Proposal Expiry Window (Free Optionality)
================================================
Quanto tempo um proposal_id permanece valido antes do buy?
Se >5s, voce pode capturar a proposal, esperar o tick mover a seu favor,
e so entao comprar. Isso e optionality gratuita no proposal ID.

Metodologia:
  1. Solicitar proposal CALL 5-tick 1HZ10V
  2. Registrar timestamp da proposal
  3. Esperar N segundos (1, 2, 3, 5, 10, 15, 20, 30)
  4. Tentar buy com o proposal_id
  5. Se buy suceder, verificar se entry_spot e o tick ATUAL (nao o tick da proposal)
  6. Se entry_spot for o tick atual, e o tick moveu a favor, ganhamos optionality

Teste A/B:
  - Grupo A (imediato): buy imediatamente apos proposal
  - Grupo B (delayed): buy apos N segundos
  - Comparar WR e EV entre grupos

Se entry_spot for sempre o tick da proposal (T+1), nao ha optionality.
Se entry_spot for o tick do buy, e o delay permite escolher, ha edge.
"""
import argparse
import asyncio
import json
import os
import sys
import time
import statistics
import random
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
DELAYS = [0, 1, 2, 3, 5, 10, 15, 20, 30]

RESULTS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "proposal_expiry_results.jsonl")


async def subscribe_ticks(client, symbol):
    """Subscribe to tick stream and store latest tick."""
    latest = {"tick": None, "epoch": None, "ts": None}

    async def on_tick(data):
        t = data.get("tick")
        if t and "quote" in t:
            latest["tick"] = float(t["quote"])
            latest["epoch"] = t.get("epoch")
            latest["ts"] = time.time()

    await client.subscribe_ticks(symbol, on_tick)
    return latest


async def test_delay(client, delay_s, trial_num, tick_state):
    """Test buy with delay after proposal."""
    rec = {
        "trial": trial_num,
        "delay_s": delay_s,
        "ts": datetime.now(timezone.utc).isoformat(),
    }

    # Get proposal
    prop = await client.send_request({
        "proposal": 1,
        "amount": STAKE,
        "basis": "stake",
        "contract_type": "CALL",
        "currency": "USD",
        "underlying_symbol": SYMBOL,
        "duration": DURATION,
        "duration_unit": DURATION_UNIT,
    })

    if "error" in prop:
        rec["error"] = f"proposal: {prop['error'].get('message')}"
        return rec

    proposal_id = prop["proposal"]["id"]
    proposal_spot = float(prop["proposal"].get("spot", 0))
    proposal_ts = time.time()
    tick_at_proposal = tick_state["tick"]
    rec["proposal_spot"] = proposal_spot
    rec["tick_at_proposal"] = tick_at_proposal

    # Wait
    if delay_s > 0:
        await asyncio.sleep(delay_s)

    tick_at_buy = tick_state["tick"]
    tick_moved = tick_at_buy - tick_at_proposal if tick_at_buy and tick_at_proposal else 0
    rec["tick_at_buy"] = tick_at_buy
    rec["tick_moved"] = tick_moved

    # Try to buy
    buy = await client.buy_contract(proposal_id, price=STAKE)

    if "error" in buy:
        rec["buy_error"] = buy["error"].get("message", "")
        rec["buy_succeeded"] = False
        print(f"  [#{trial_num} delay={delay_s}s] BUY FAILED: {rec['buy_error']} "
              f"tick_moved={tick_moved:.2f}")
        return rec

    rec["buy_succeeded"] = True
    contract_id = buy["buy"]["contract_id"]
    buy_price = float(buy["buy"]["buy_price"])
    rec["contract_id"] = contract_id
    rec["buy_price"] = buy_price

    # Wait for settle
    t0 = time.time()
    while time.time() - t0 < 120:
        await asyncio.sleep(0.5)
        poc = await client.send_request({
            "proposal_open_contract": 1,
            "contract_id": contract_id,
        })
        poc_data = poc.get("proposal_open_contract", {})
        if poc_data.get("is_sold", 0):
            await asyncio.sleep(1.0)
            poc2 = await client.send_request({
                "proposal_open_contract": 1,
                "contract_id": contract_id,
            })
            poc2_data = poc2.get("proposal_open_contract", poc_data)
            profit = float(poc2_data.get("profit", 0))
            is_won = poc2_data.get("is_won")
            if is_won is None:
                is_won = 1 if profit > 0 else 0
            entry_spot = float(poc2_data.get("entry_spot", 0) or 0)
            exit_spot = float(poc2_data.get("exit_tick", 0) or 0)

            rec["profit"] = profit
            rec["is_won"] = int(is_won)
            rec["entry_spot"] = entry_spot
            rec["exit_spot"] = exit_spot
            rec["entry_matches_proposal"] = abs(entry_spot - proposal_spot) < 0.01
            rec["entry_matches_buy_tick"] = abs(entry_spot - tick_at_buy) < 0.01 if tick_at_buy else None

            won_str = "WON" if is_won else "LOST"
            print(f"  [#{trial_num} delay={delay_s}s] {won_str} "
                  f"profit=${profit:+.4f} entry={entry_spot:.2f} "
                  f"proposal_spot={proposal_spot:.2f} tick_moved={tick_moved:.2f} "
                  f"entry=proposal={rec['entry_matches_proposal']} "
                  f"entry=buy_tick={rec['entry_matches_buy_tick']}")
            return rec

    rec["timeout"] = True
    print(f"  [#{trial_num} delay={delay_s}s] TIMEOUT")
    return rec


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
    parser = argparse.ArgumentParser()
    parser.add_argument("--trials-per-delay", type=int, default=10)
    args = parser.parse_args()

    print("=" * 90)
    print("D74 — Proposal Expiry Window (Free Optionality)")
    print(f"  Symbol: {SYMBOL} | Duration: {DURATION}{DURATION_UNIT} | Stake: ${STAKE}")
    print(f"  Delays: {DELAYS}s | Trials per delay: {args.trials_per_delay}")
    print("=" * 90)

    client = DerivClient(app_id=APP_ID, api_token=TOKEN, use_demo=True)
    await client.connect()
    print(f"  Conectado. Conta: {client.account_id}")

    tick_state = await subscribe_ticks(client, SYMBOL)
    await asyncio.sleep(2)
    print(f"  Tick inicial: {tick_state['tick']}")

    all_results = []
    total_trials = len(DELAYS) * args.trials_per_delay
    trial_num = 0

    for delay in DELAYS:
        print(f"\n  --- Delay {delay}s ---")
        for _ in range(args.trials_per_delay):
            rec = await test_delay(client, delay, trial_num, tick_state)
            all_results.append(rec)
            with open(RESULTS_FILE, "a") as f:
                f.write(json.dumps(rec, default=str) + "\n")
            trial_num += 1
            await asyncio.sleep(1)

    # Analysis
    print(f"\n{'='*90}")
    print("  ANALISE FINAL")
    print(f"{'='*90}")

    # 1. Proposal validity window
    print("\n  1. JANELA DE VALIDADE DO PROPOSAL:")
    for delay in DELAYS:
        delay_results = [r for r in all_results if r.get("delay_s") == delay and "error" not in r]
        succeeded = [r for r in delay_results if r.get("buy_succeeded")]
        failed = [r for r in delay_results if r.get("buy_error")]
        success_rate = len(succeeded) / len(delay_results) if delay_results else 0
        print(f"    delay={delay:2d}s: {len(succeeded)}/{len(delay_results)} buy sucedeu "
              f"({success_rate*100:.0f}%)")
        if failed:
            errors = set(r["buy_error"] for r in failed)
            print(f"      erros: {errors}")

    # 2. Entry spot analysis
    print("\n  2. ENTRY SPOT MATCH:")
    for delay in DELAYS:
        delay_results = [r for r in all_results if r.get("delay_s") == delay
                         and r.get("buy_succeeded") and r.get("entry_spot")]
        if not delay_results:
            continue
        matches_proposal = sum(1 for r in delay_results if r.get("entry_matches_proposal"))
        matches_buy = sum(1 for r in delay_results if r.get("entry_matches_buy_tick"))
        n = len(delay_results)
        print(f"    delay={delay:2d}s: entry=proposal {matches_proposal}/{n} | "
              f"entry=buy_tick {matches_buy}/{n}")

    # 3. WR and EV by delay
    print("\n  3. WR E EV POR DELAY:")
    for delay in DELAYS:
        delay_results = [r for r in all_results if r.get("delay_s") == delay
                         and r.get("profit") is not None]
        if len(delay_results) < 3:
            continue
        profits = [r["profit"] for r in delay_results]
        wins = sum(1 for p in profits if p > 0)
        wr = wins / len(profits)
        ev = statistics.mean(profits)
        ev_mean, ci_lo, ci_hi = bootstrap_ci(profits)
        print(f"    delay={delay:2d}s: N={len(profits)} WR={wr*100:.0f}% "
              f"EV=${ev:+.4f} CI95%[${ci_lo:+.4f},${ci_hi:+.4f}]")

    # 4. Tick movement analysis
    print("\n  4. TICK MOVEMENT DURING DELAY:")
    for delay in DELAYS:
        delay_results = [r for r in all_results if r.get("delay_s") == delay
                         and r.get("tick_moved") is not None]
        if not delay_results:
            continue
        moves = [r["tick_moved"] for r in delay_results]
        avg_move = statistics.mean(abs(m) for m in moves)
        favorable = sum(1 for r in delay_results if r.get("is_won"))
        print(f"    delay={delay:2d}s: avg|move|={avg_move:.3f} "
              f"WR={favorable}/{len(delay_results)}")

    # 5. Verdict
    print(f"\n  VEREDITO:")
    delay0 = [r for r in all_results if r.get("delay_s") == 0 and r.get("profit") is not None]
    delay_max = [r for r in all_results if r.get("delay_s") == max(DELAYS)
                 and r.get("profit") is not None and r.get("buy_succeeded")]

    if delay0 and delay_max:
        ev0 = statistics.mean([r["profit"] for r in delay0])
        ev_max = statistics.mean([r["profit"] for r in delay_max])
        diff = ev_max - ev0
        print(f"    EV delay=0s: ${ev0:+.4f} | EV delay={max(DELAYS)}s: ${ev_max:+.4f} | diff=${diff:+.4f}")

        # Check if entry_spot matches buy tick (not proposal tick)
        entry_matches = [r for r in all_results if r.get("entry_matches_buy_tick") is True
                         and r.get("delay_s", 0) > 0]
        if entry_matches:
            print(f"    *** {len(entry_matches)} contratos com entry_spot = tick do buy (nao da proposal)")
            print(f"    Optionality confirmada — entry_spot e o tick do momento do buy, nao da proposal")
        else:
            print(f"    Entry_spot sempre = proposal spot — sem optionality no delay")
    else:
        print(f"    Dados insuficientes para conclusao")

    await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
