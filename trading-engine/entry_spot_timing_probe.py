"""
D64 — Entry Spot Timing Probe
===============================
Hipotese: Quando exatamente o entry_spot e capturado relativo ao buy request?
Se o entry_spot e o tick ANTERIOR ao momento do buy (e nao o tick atual),
pode haver uma janela onde o spot ja conhecido e diferente do que sera usado.

Se o spot usado para entry e o tick que estava vigente quando o proposal
foi solicitado (e nao quando o buy foi confirmado), pode haver staleness
favoravel: ver um tick, pedir proposal, esperar o proximo tick ir a favor,
comprar com entry_spot ainda no tick antigo.

Metodo:
  1. Subscrever ticks de 1HZ10V
  2. A cada tick recebido:
     a. Registrar tick_quote e timestamp preciso
     b. Imediatamente solicitar proposal (CALL 5 ticks)
     c. Registrar spot do proposal
     d. Imediatamente comprar
     e. Registrar entry_spot do contrato (via POC poll)
  3. Comparar: tick_no_momento_do_buy vs spot_do_proposal vs entry_spot_do_contrato
  4. Se entry_spot != tick_no_momento_do_buy, ha delay ou staleness
  5. Repetir N trials

Uso: python3 entry_spot_timing_probe.py [--n=30]
"""
import argparse
import asyncio
import json
import os
import sys
import time
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
DURATION = 5
DURATION_UNIT = "t"

RESULTS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "entry_spot_timing_results.jsonl")
STATS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "entry_spot_timing_stats.json")

latest_tick = {"quote": None, "epoch": None, "local_ts": None}


def on_tick(data):
    t = data.get("tick")
    if not t or "quote" not in t:
        return
    latest_tick["quote"] = float(t["quote"])
    latest_tick["epoch"] = int(t.get("epoch", 0))
    latest_tick["local_ts"] = time.time()


async def run_trial(client, trial_num):
    rec = {
        "trial": trial_num,
        "ts": datetime.now(timezone.utc).isoformat(),
    }

    try:
        while latest_tick["quote"] is None:
            await asyncio.sleep(0.1)

        tick_before_proposal = latest_tick["quote"]
        tick_epoch_before = latest_tick["epoch"]
        ts_before_proposal = time.time()

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
        ts_after_proposal = time.time()

        if "error" in prop:
            rec["error"] = f"proposal: {prop['error'].get('message')}"
            print(f"  [#{trial_num}] proposal erro: {rec['error']}")
            return rec

        proposal_spot = float(prop["proposal"].get("spot", 0))
        proposal_id = prop["proposal"]["id"]
        proposal_latency_ms = (ts_after_proposal - ts_before_proposal) * 1000

        tick_before_buy = latest_tick["quote"]
        tick_epoch_before_buy = latest_tick["epoch"]
        ts_before_buy = time.time()

        buy = await client.buy_contract(proposal_id, price=STAKE)
        ts_after_buy = time.time()

        if "error" in buy:
            rec["error"] = f"buy: {buy['error'].get('message')}"
            print(f"  [#{trial_num}] buy erro: {rec['error']}")
            return rec

        contract_id = buy["buy"]["contract_id"]
        buy_price = float(buy["buy"]["buy_price"])
        buy_latency_ms = (ts_after_buy - ts_before_buy) * 1000

        tick_after_buy = latest_tick["quote"]
        tick_epoch_after_buy = latest_tick["epoch"]

        await asyncio.sleep(0.3)

        poc = await client.send_request({
            "proposal_open_contract": 1,
            "contract_id": contract_id,
        })

        entry_spot = None
        if "proposal_open_contract" in poc:
            entry_spot = float(poc["proposal_open_contract"].get("entry_spot", 0) or 0)

        rec["tick_before_proposal"] = tick_before_proposal
        rec["tick_epoch_before_proposal"] = tick_epoch_before
        rec["proposal_spot"] = proposal_spot
        rec["proposal_latency_ms"] = round(proposal_latency_ms, 1)
        rec["tick_before_buy"] = tick_before_buy
        rec["tick_epoch_before_buy"] = tick_epoch_before_buy
        rec["buy_latency_ms"] = round(buy_latency_ms, 1)
        rec["tick_after_buy"] = tick_after_buy
        rec["tick_epoch_after_buy"] = tick_epoch_after_buy
        rec["entry_spot"] = entry_spot
        rec["buy_price"] = buy_price
        rec["contract_id"] = contract_id

        spot_vs_tick_proposal = proposal_spot - tick_before_proposal
        entry_vs_tick_buy = entry_spot - tick_before_buy if entry_spot else None
        entry_vs_proposal_spot = (entry_spot - proposal_spot) if entry_spot else None
        entry_vs_tick_after = (entry_spot - tick_after_buy) if entry_spot else None

        rec["spot_vs_tick_proposal"] = round(spot_vs_tick_proposal, 6)
        rec["entry_vs_tick_buy"] = round(entry_vs_tick_buy, 6) if entry_vs_tick_buy is not None else None
        rec["entry_vs_proposal_spot"] = round(entry_vs_proposal_spot, 6) if entry_vs_proposal_spot is not None else None
        rec["entry_vs_tick_after"] = round(entry_vs_tick_after, 6) if entry_vs_tick_after is not None else None

        ticks_moved_during_buy = tick_epoch_after_buy - tick_epoch_before if tick_epoch_after_buy and tick_epoch_before else None
        rec["ticks_moved_during_buy"] = ticks_moved_during_buy

        entry_str = f"{entry_spot:.2f}" if entry_spot else "N/A"
        diff_str = f"{entry_vs_tick_buy:+.2f}" if entry_vs_tick_buy is not None else "N/A"
        print(f"  [#{trial_num}] tick_proposal={tick_before_proposal:.2f} spot_proposal={proposal_spot:.2f} "
              f"tick_buy={tick_before_buy:.2f} entry={entry_str} "
              f"entry_vs_tick_buy={diff_str} "
              f"ticks_moved={ticks_moved_during_buy}")

        return rec

    except Exception as e:
        rec["error"] = f"exception: {e}"
        print(f"  [#{trial_num}] EXC: {e}")
        return rec


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--n", type=int, default=30)
    args = parser.parse_args()

    if not APP_ID:
        print("ERRO: DERIV_APP_ID nao encontrado.")
        return

    print("=" * 90)
    print(f"D64 — Entry Spot Timing Probe")
    print(f"  Symbol: {SYMBOL} | Contract: {CONTRACT_TYPE} | Duration: {DURATION} {DURATION_UNIT}")
    print(f"  Stake: ${STAKE} | Trials: {args.n}")
    print("=" * 90)

    client = DerivClient(app_id=APP_ID, api_token=TOKEN, use_demo=True)
    await client.connect()
    print(f"  Conectado. Conta: {client.account_id}")

    await client.subscribe_ticks(SYMBOL, on_tick)
    print(f"  Subscrito a {SYMBOL}. Aguardando ticks...")
    await asyncio.sleep(3)

    all_results = []
    for i in range(args.n):
        rec = await run_trial(client, i)
        all_results.append(rec)
        with open(RESULTS_FILE, "a") as f:
            f.write(json.dumps(rec, default=str) + "\n")
        await asyncio.sleep(1.5)

    print(f"\n{'='*80}")
    print(f"  ANALISE FINAL")
    print(f"{'='*80}")

    valid = [r for r in all_results if "error" not in r and r.get("entry_spot") is not None and r["entry_spot"] > 0]
    print(f"  Trials: {len(all_results)} | Validos: {len(valid)}")

    import statistics

    entry_vs_tick_buy = [r["entry_vs_tick_buy"] for r in valid if r.get("entry_vs_tick_buy") is not None]
    entry_vs_proposal = [r["entry_vs_proposal_spot"] for r in valid if r.get("entry_vs_proposal_spot") is not None]
    entry_vs_tick_after = [r["entry_vs_tick_after"] for r in valid if r.get("entry_vs_tick_after") is not None]
    spot_vs_tick = [r["spot_vs_tick_proposal"] for r in valid if r.get("spot_vs_tick_proposal") is not None]
    ticks_moved = [r["ticks_moved_during_buy"] for r in valid if r.get("ticks_moved_during_buy") is not None]

    if entry_vs_tick_buy:
        print(f"\n  Entry spot vs tick no momento do buy:")
        print(f"    Mean: {statistics.mean(entry_vs_tick_buy):+.4f}")
        print(f"    Median: {statistics.median(entry_vs_tick_buy):+.4f}")
        print(f"    Std: {statistics.stdev(entry_vs_tick_buy):.4f}" if len(entry_vs_tick_buy) > 1 else "")
        nonzero = sum(1 for v in entry_vs_tick_buy if abs(v) > 0.01)
        print(f"    Nao-zero (|diff|>0.01): {nonzero}/{len(entry_vs_tick_buy)}")

    if entry_vs_proposal:
        print(f"\n  Entry spot vs spot do proposal:")
        print(f"    Mean: {statistics.mean(entry_vs_proposal):+.4f}")
        print(f"    Median: {statistics.median(entry_vs_proposal):+.4f}")

    if entry_vs_tick_after:
        print(f"\n  Entry spot vs tick apos buy:")
        print(f"    Mean: {statistics.mean(entry_vs_tick_after):+.4f}")
        print(f"    Median: {statistics.median(entry_vs_tick_after):+.4f}")

    if ticks_moved:
        print(f"\n  Ticks que mudaram durante o buy (epoch diff):")
        print(f"    Mean: {statistics.mean(ticks_moved):.1f}")
        print(f"    Median: {statistics.median(ticks_moved):.1f}")
        zero_moved = sum(1 for t in ticks_moved if t == 0)
        print(f"    0 ticks moved (mesmo tick): {zero_moved}/{len(ticks_moved)}")

    if entry_vs_tick_buy:
        all_zero = all(abs(v) < 0.001 for v in entry_vs_tick_buy)
        if all_zero:
            print(f"\n  Entry spot = tick no momento do buy em TODOS os trials.")
            print(f"  Nao ha staleness — entry_spot e capturado no tick atual.")
        else:
            consistent_diff = all(abs(v - entry_vs_tick_buy[0]) < 0.01 for v in entry_vs_tick_buy)
            if consistent_diff:
                print(f"\n  *** DIFFERENCA CONSISTENTE: entry_spot - tick_buy = {entry_vs_tick_buy[0]:+.4f}")
                print(f"      Entry spot e sistematicamente diferente do tick no momento do buy!")
            else:
                print(f"\n  Diferenca variavel — entry_spot depende do timing exato do buy.")

    stats = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "n_trials": len(all_results),
        "valid": len(valid),
        "entry_vs_tick_buy": entry_vs_tick_buy,
        "entry_vs_proposal": entry_vs_proposal,
        "entry_vs_tick_after": entry_vs_tick_after,
        "spot_vs_tick": spot_vs_tick,
        "ticks_moved_during_buy": ticks_moved,
    }
    with open(STATS_FILE, "w") as f:
        json.dump(stats, f, indent=2, default=str)
    print(f"\n  Stats salvas em {STATS_FILE}")

    await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
