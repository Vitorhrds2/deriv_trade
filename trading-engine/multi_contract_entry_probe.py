"""
D70 — Multi-Contract Entry Spot Consistency Probe
===================================================
Hipotese: Comprar 2+ contratos no mesmo simbolo simultaneamente. Todos
recebem o mesmo entry_spot? Se nao, ha discrepancia exploravel — sempre
comprar o contrato com entry_spot favoravel.

D64 testou 1 contrato vs tick. Isto testa consistencia entre multiplos
contratos concorrentes no mesmo simbolo.

Metodo:
  1. Comprar N contratos CALL 5-tick em 1HZ10V simultaneamente (batch)
  2. Poll POC para cada contract_id
  3. Comparar entry_spot de todos os contratos
  4. Se entry_spots diferem, ha discrepancia
  5. Repetir M trials

Uso: python3 multi_contract_entry_probe.py [--trials=20] [--batch=3]
"""
import argparse
import asyncio
import json
import os
import sys
import time
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
CONTRACT_TYPE = "CALL"

RESULTS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "multi_contract_entry_results.jsonl")
STATS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "multi_contract_entry_stats.json")


async def buy_one(client, batch_idx):
    try:
        prop = await client.send_request({
            "proposal": 1,
            "amount": STAKE,
            "basis": "stake",
            "contract_type": CONTRACT_TYPE,
            "currency": "USD",
            "underlying_symbol": SYMBOL,
            "duration": DURATION,
            "duration_unit": DURATION_UNIT,
        })
        if "error" in prop:
            return {"batch_idx": batch_idx, "error": f"proposal: {prop['error'].get('message')}"}

        buy = await client.buy_contract(prop["proposal"]["id"], price=STAKE)
        if "error" in buy:
            return {"batch_idx": batch_idx, "error": f"buy: {buy['error'].get('message')}"}

        return {
            "batch_idx": batch_idx,
            "contract_id": buy["buy"]["contract_id"],
            "buy_price": float(buy["buy"]["buy_price"]),
            "proposal_spot": float(prop["proposal"].get("spot", 0)),
        }
    except Exception as e:
        return {"batch_idx": batch_idx, "error": str(e)}


async def get_entry_spot(client, contract_id, max_wait=30):
    t0 = time.time()
    while time.time() - t0 < max_wait:
        await asyncio.sleep(0.5)
        try:
            poc = await client.send_request({
                "proposal_open_contract": 1,
                "contract_id": contract_id,
            })
            poc_data = poc.get("proposal_open_contract", {})
            entry = poc_data.get("entry_spot")
            if entry is not None and float(entry) > 0:
                return {
                    "entry_spot": float(entry),
                    "entry_tick": poc_data.get("entry_tick"),
                    "purchase_time": poc_data.get("purchase_time"),
                    "is_sold": poc_data.get("is_sold", 0),
                    "is_won": poc_data.get("is_won", 0),
                    "profit": float(poc_data.get("profit", 0)),
                }
        except:
            pass
    return {"entry_spot": None, "timeout": True}


async def run_trial(client, trial_num, batch_size):
    rec = {"trial": trial_num, "batch_size": batch_size, "ts": datetime.now(timezone.utc).isoformat()}

    buy_results = []
    for i in range(batch_size):
        b = await buy_one(client, i)
        buy_results.append(b)
        await asyncio.sleep(0.3)

    valid_buys = [b for b in buy_results if "error" not in b]
    errors = [b for b in buy_results if "error" in b]

    if errors:
        rec["buy_errors"] = [e["error"] for e in errors]

    if len(valid_buys) < 2:
        rec["error"] = f"Apenas {len(valid_buys)} buys validos (precisa >=2)"
        print(f"  [#{trial_num}] {rec['error']}")
        return rec

    rec["contracts"] = [{"batch_idx": b["batch_idx"], "contract_id": b["contract_id"],
                          "buy_price": b["buy_price"], "proposal_spot": b["proposal_spot"]}
                         for b in valid_buys]

    await asyncio.sleep(1)

    entry_tasks = [get_entry_spot(client, b["contract_id"]) for b in valid_buys]
    entry_results = await asyncio.gather(*entry_tasks)

    entry_spots = []
    for i, er in enumerate(entry_results):
        rec["contracts"][i]["entry_spot"] = er.get("entry_spot")
        rec["contracts"][i]["is_won"] = er.get("is_won")
        rec["contracts"][i]["profit"] = er.get("profit")
        if er.get("entry_spot") is not None and er["entry_spot"] > 0:
            entry_spots.append(er["entry_spot"])

    if len(entry_spots) >= 2:
        all_same = all(abs(e - entry_spots[0]) < 0.001 for e in entry_spots)
        spread = max(entry_spots) - min(entry_spots)
        rec["all_same"] = all_same
        rec["spread"] = spread
        rec["entry_spots"] = entry_spots

        spots_str = ", ".join(f"{s:.2f}" for s in entry_spots)
        if all_same:
            print(f"  [#{trial_num}] {len(entry_spots)} contracts: ALL SAME entry_spot={entry_spots[0]:.2f}")
        else:
            print(f"  [#{trial_num}] {len(entry_spots)} contracts: DIFFERENT entry_spots=[{spots_str}] spread={spread:.4f}")
            if spread > 0.01:
                print(f"    *** DISCREPANCIA: spread={spread:.4f} entre contratos simultaneos!")
    else:
        rec["error"] = f"Apenas {len(entry_spots)} entry_spots validos"
        print(f"  [#{trial_num}] {rec['error']}")

    return rec


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--trials", type=int, default=20)
    parser.add_argument("--batch", type=int, default=3, help="Contratos simultaneos por trial")
    args = parser.parse_args()

    if not APP_ID:
        print("ERRO: DERIV_APP_ID nao encontrado.")
        return

    print("=" * 90)
    print(f"D70 — Multi-Contract Entry Spot Consistency Probe")
    print(f"  Symbol: {SYMBOL} | Contract: {CONTRACT_TYPE} {DURATION}t")
    print(f"  Batch size: {args.batch} contracts/trial | Trials: {args.trials}")
    print(f"  Stake: ${STAKE}/contract = ${STAKE*args.batch}/trial")
    print("=" * 90)

    client = DerivClient(app_id=APP_ID, api_token=TOKEN, use_demo=True)
    await client.connect()
    print(f"  Conectado. Conta: {client.account_id}")

    all_results = []
    for i in range(args.trials):
        rec = await run_trial(client, i, args.batch)
        all_results.append(rec)
        with open(RESULTS_FILE, "a") as f:
            f.write(json.dumps(rec, default=str) + "\n")
        await asyncio.sleep(2)

    print(f"\n{'='*80}")
    print(f"  ANALISE FINAL")
    print(f"{'='*80}")

    valid = [r for r in all_results if "error" not in r and r.get("entry_spots")]
    print(f"  Trials: {len(all_results)} | Validos: {len(valid)}")

    all_same_count = sum(1 for r in valid if r.get("all_same"))
    diff_count = sum(1 for r in valid if not r.get("all_same"))
    print(f"\n  Entry spots identicos: {all_same_count}/{len(valid)}")
    print(f"  Entry spots diferentes: {diff_count}/{len(valid)}")

    if valid:
        spreads = [r["spread"] for r in valid if r.get("spread") is not None]
        if spreads:
            print(f"\n  Spread (max-min entry_spot por trial):")
            print(f"    Mean: {statistics.mean(spreads):.6f}")
            print(f"    Median: {statistics.median(spreads):.6f}")
            print(f"    Max: {max(spreads):.6f}")
            nonzero = sum(1 for s in spreads if s > 0.001)
            print(f"    Trials com spread > 0.001: {nonzero}/{len(spreads)}")

        if all_same_count == len(valid):
            print(f"\n  TODOS os trials tiveram entry_spots identicos.")
            print(f"  Contratos simultaneos no mesmo simbolo recebem o mesmo entry_spot.")
            print(f"  Nao ha discrepancia exploravel.")
        elif diff_count > 0:
            print(f"\n  *** {diff_count} trials com entry_spots DIFERENTES!")
            print(f"  Contratos simultaneos podem receber entry_spots diferentes.")
            if any(r["spread"] > 0.01 for r in valid):
                print(f"  Spread > 0.01 em alguns trials — pode ser exploravel!")
            else:
                print(f"  Spread pequeno (< 0.01) — provavelmente ruido de tick, nao exploravel.")

        profits = []
        for r in valid:
            for c in r.get("contracts", []):
                if c.get("profit") is not None:
                    profits.append(c["profit"])
        if profits:
            total_pnl = sum(profits)
            wins = sum(1 for p in profits if p > 0)
            print(f"\n  P&L: ${total_pnl:+.2f} ({len(profits)} contracts, WR={wins/len(profits)*100:.0f}%)")

    stats = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "n_trials": len(all_results),
        "valid": len(valid),
        "all_same": all_same_count,
        "different": diff_count,
        "spreads": spreads if valid else [],
    }
    with open(STATS_FILE, "w") as f:
        json.dump(stats, f, indent=2, default=str)
    print(f"\n  Stats salvas em {STATS_FILE}")

    await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
