"""
D66 — Tick Count Settlement Precision Probe
=============================================
Hipotese: Um contrato de 10 ticks sempre settle no exato 10o tick? Ou ha
variabilidade? Se as vezes settle no 9o ou 11o tick, ha edge sistemático.

Se contratos sistematicamente settle em mais ou menos ticks que o solicitado,
o payout efetivo por tick muda — e se o mercado precifica assumindo N exato
mas entrega N±1, ha edge.

Metodo:
  1. Comprar CALL de N ticks (1, 5, 10, 15, 30) em 1HZ10V
  2. Subscrever ticks simultaneamente
  3. Registrar:
     - tick count solicitado (duration)
     - entry_tick_epoch (do POC)
     - exit_tick_epoch (do POC)
     - tick_count_real = exit_epoch - entry_epoch
  4. Comparar tick_count_real vs duration solicitado
  5. Repetir N trials por duracao

Uso: python3 tick_count_settlement_probe.py [--trials=10]
"""
import argparse
import asyncio
import json
import os
import sys
import time
from collections import defaultdict
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
CONTRACT_TYPE = "CALL"
STAKE = 1.00
DURATIONS = [1, 5, 10, 15, 30]
DURATION_UNIT = "t"

RESULTS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tick_count_settlement_results.jsonl")
STATS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tick_count_settlement_stats.json")


async def run_trial(client, duration, trial_num):
    rec = {
        "trial": trial_num,
        "duration_requested": duration,
        "ts": datetime.now(timezone.utc).isoformat(),
    }

    try:
        prop = await client.send_request({
            "proposal": 1,
            "amount": STAKE,
            "basis": "stake",
            "contract_type": CONTRACT_TYPE,
            "currency": "USD",
            "underlying_symbol": SYMBOL,
            "duration": duration,
            "duration_unit": DURATION_UNIT,
        })
        if "error" in prop:
            rec["error"] = f"proposal: {prop['error'].get('message')}"
            return rec

        buy = await client.buy_contract(prop["proposal"]["id"], price=STAKE)
        if "error" in buy:
            rec["error"] = f"buy: {buy['error'].get('message')}"
            return rec

        contract_id = buy["buy"]["contract_id"]
        buy_price = float(buy["buy"]["buy_price"])
        rec["contract_id"] = contract_id
        rec["buy_price"] = buy_price

        buy_ts = time.time()
        max_wait = max(120, duration * 2 + 30)

        entry_tick_epoch = None
        exit_tick_epoch = None
        entry_spot = None
        exit_spot = None
        is_sold = 0
        sold_for = None
        tick_count = None
        contract_status = None

        while time.time() - buy_ts < max_wait:
            await asyncio.sleep(0.3)
            try:
                poc = await client.send_request({
                    "proposal_open_contract": 1,
                    "contract_id": contract_id,
                })
                poc_data = poc.get("proposal_open_contract", {})
                if entry_tick_epoch is None:
                    entry_tick_epoch = poc_data.get("purchase_time")
                    entry_spot = float(poc_data.get("entry_spot", 0) or 0)

                is_sold = poc_data.get("is_sold", 0)
                contract_status = poc_data.get("status", "")

                if is_sold:
                    exit_tick_epoch = poc_data.get("date_expiry") or poc_data.get("sell_time")
                    exit_spot = float(poc_data.get("exit_tick", 0) or 0)
                    sold_for = float(poc_data.get("sold_for", 0))
                    tick_count_str = poc_data.get("tick_count")
                    if tick_count_str is not None:
                        tick_count = int(tick_count_str)
                    break
            except Exception as e:
                pass

        rec["entry_tick_epoch"] = entry_tick_epoch
        rec["exit_tick_epoch"] = exit_tick_epoch
        rec["entry_spot"] = entry_spot
        rec["exit_spot"] = exit_spot
        rec["is_sold"] = is_sold
        rec["sold_for"] = sold_for
        rec["profit"] = (sold_for - buy_price) if sold_for else None
        rec["tick_count_reported"] = tick_count
        rec["contract_status"] = contract_status

        if entry_tick_epoch and exit_tick_epoch:
            epoch_diff = int(exit_tick_epoch) - int(entry_tick_epoch)
            rec["epoch_diff"] = epoch_diff
            rec["tick_diff_vs_requested"] = tick_count - duration if tick_count else None
        else:
            rec["epoch_diff"] = None
            rec["tick_diff_vs_requested"] = None

        tc_str = f"tc={tick_count}" if tick_count else "tc=N/A"
        diff_str = f"diff={tick_count - duration:+d}" if tick_count else "diff=N/A"
        status_str = f"{'WON' if (sold_for and sold_for > buy_price) else 'LOST'}" if sold_for else "N/A"
        entry_str = f"{entry_spot:.2f}" if entry_spot else "N/A"
        exit_str = f"{exit_spot:.2f}" if exit_spot else "N/A"
        profit_str = f"{rec['profit']:+.2f}" if rec.get("profit") is not None else "N/A"
        print(f"  [#{trial_num} dur={duration:2d}t] {tc_str} {diff_str} "
              f"entry={entry_str} exit={exit_str} "
              f"{status_str} profit={profit_str}")

        return rec

    except Exception as e:
        rec["error"] = f"exception: {e}"
        print(f"  [#{trial_num} dur={duration:2d}t] EXC: {e}")
        return rec


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--trials", type=int, default=10)
    args = parser.parse_args()

    if not APP_ID:
        print("ERRO: DERIV_APP_ID nao encontrado.")
        return

    print("=" * 90)
    print(f"D66 — Tick Count Settlement Precision Probe")
    print(f"  Symbol: {SYMBOL} | Contract: {CONTRACT_TYPE}")
    print(f"  Durations: {DURATIONS} ticks | Trials per duration: {args.trials}")
    print(f"  Stake: ${STAKE}")
    print("=" * 90)

    client = DerivClient(app_id=APP_ID, api_token=TOKEN, use_demo=True)
    await client.connect()
    print(f"  Conectado. Conta: {client.account_id}")

    all_results = []
    for dur in DURATIONS:
        print(f"\n  --- Duration: {dur} ticks ---")
        for i in range(args.trials):
            rec = await run_trial(client, dur, i)
            all_results.append(rec)
            with open(RESULTS_FILE, "a") as f:
                f.write(json.dumps(rec, default=str) + "\n")
            await asyncio.sleep(1)

    print(f"\n{'='*80}")
    print(f"  ANALISE FINAL")
    print(f"{'='*80}")

    valid = [r for r in all_results if "error" not in r and r.get("tick_count_reported") is not None]
    print(f"  Trials: {len(all_results)} | Validos com tick_count: {len(valid)}")

    import statistics

    by_duration = defaultdict(list)
    for rec in valid:
        by_duration[rec["duration_requested"]].append(rec)

    print(f"\n  Tick count real vs solicitado:")
    for dur in sorted(by_duration.keys()):
        records = by_duration[dur]
        tick_counts = [r["tick_count_reported"] for r in records]
        diffs = [r["tick_diff_vs_requested"] for r in records if r.get("tick_diff_vs_requested") is not None]

        mean_tc = statistics.mean(tick_counts)
        median_tc = statistics.median(tick_counts)
        exact = sum(1 for d in diffs if d == 0)
        more = sum(1 for d in diffs if d > 0)
        less = sum(1 for d in diffs if d < 0)

        print(f"    dur={dur:2d}t: mean_tc={mean_tc:.1f} median={median_tc:.0f} "
              f"exact={exact}/{len(records)} more={more} less={less}")

        if diffs:
            mean_diff = statistics.mean(diffs)
            if abs(mean_diff) > 0.1:
                print(f"      *** DIFF: mean diff={mean_diff:+.2f} ticks")
                if mean_diff > 0:
                    print(f"      Contratos settle com MAIS ticks que o solicitado!")
                else:
                    print(f"      Contratos settle com MENOS ticks que o solicitado!")

    all_diffs = [r["tick_diff_vs_requested"] for r in valid if r.get("tick_diff_vs_requested") is not None]
    if all_diffs:
        all_exact = all(d == 0 for d in all_diffs)
        if all_exact:
            print(f"\n  Tick count e EXATO em TODOS os trials ({len(all_diffs)}).")
            print(f"  Contratos sempre settle no numero exato de ticks solicitado.")
            print(f"  Nao ha variabilidade de settlement para explorar.")
        else:
            nonzero = sum(1 for d in all_diffs if d != 0)
            print(f"\n  {nonzero}/{len(all_diffs)} trials com tick_count != duration solicitado.")
            print(f"  Mean diff: {statistics.mean(all_diffs):+.2f}")
            if nonzero > len(all_diffs) * 0.1:
                print(f"  *** VARIABILIDADE SIGNIFICATIVA — investigar padrao!")
            else:
                print(f"  Variabilidade baixa — pode ser ruido/rate limit.")

    profits = [r["profit"] for r in valid if r.get("profit") is not None]
    if profits:
        total_pnl = sum(profits)
        wins = sum(1 for p in profits if p > 0)
        print(f"\n  P&L: total=${total_pnl:+.2f} WR={wins}/{len(profits)} ({wins/len(profits)*100:.0f}%)")

    stats = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "n_trials": len(all_results),
        "valid": len(valid),
        "by_duration": {str(d): {
            "tick_counts": [r["tick_count_reported"] for r in by_duration[d]],
            "diffs": [r["tick_diff_vs_requested"] for r in by_duration[d] if r.get("tick_diff_vs_requested") is not None],
        } for d in by_duration},
        "all_diffs": all_diffs,
    }
    with open(STATS_FILE, "w") as f:
        json.dump(stats, f, indent=2, default=str)
    print(f"\n  Stats salvas em {STATS_FILE}")

    await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
