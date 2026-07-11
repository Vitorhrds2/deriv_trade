"""
D69 — Long-Duration Resale Probe
=================================
Hipotese: D58 so testou tick contracts (resale rejeitado: "Resale not
offered on this contract"). O veredito notou que "resale pode existir
para duracoes maiores (1d+)". Se sell funciona para contratos longos,
a hipotese early-sell (HYP-SELL-01, refutada com hindsight bias) pode
ser re-testada com capacidade real de venda.

Metodo:
  1. Para cada duracao (1m, 5m, 15m, 1h, 4h, 1d):
     a. Comprar CALL com essa duracao
     b. Imediatamente tentar sell (price=0)
     c. Registrar se sell foi aceito ou rejeitado
     d. Se aceito, registrar sell_price vs buy_price
  2. Se sell funciona em alguma duracao, testar early-sell optionality

Uso: python3 long_duration_resale_probe.py
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
STAKE = 1.00
CONTRACT_TYPE = "CALL"

DURATIONS = [
    (1, "m", "1 minute"),
    (5, "m", "5 minutes"),
    (15, "m", "15 minutes"),
    (60, "m", "1 hour"),
    (240, "m", "4 hours"),
    (1440, "m", "1 day"),
]

RESULTS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "long_duration_resale_results.jsonl")
STATS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "long_duration_resale_stats.json")


async def test_duration(client, duration, unit, label, trial_num):
    rec = {
        "trial": trial_num,
        "duration": duration,
        "duration_unit": unit,
        "label": label,
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
            "duration_unit": unit,
        })
        if "error" in prop:
            rec["error"] = f"proposal: {prop['error'].get('message')}"
            print(f"  [{label}] proposal erro: {rec['error']}")
            return rec

        p = prop["proposal"]
        rec["ask_price"] = float(p.get("ask_price", 0))
        rec["payout"] = float(p.get("payout", 0))
        rec["spot"] = float(p.get("spot", 0))

        buy = await client.buy_contract(p["id"], price=STAKE)
        if "error" in buy:
            rec["error"] = f"buy: {buy['error'].get('message')}"
            print(f"  [{label}] buy erro: {rec['error']}")
            return rec

        contract_id = buy["buy"]["contract_id"]
        rec["contract_id"] = contract_id
        rec["buy_price"] = float(buy["buy"]["buy_price"])

        await asyncio.sleep(2)

        sell = await client.sell_contract(contract_id, price=0)

        if "error" in sell:
            rec["sell_error"] = sell["error"].get("message")
            rec["sell_accepted"] = False
            print(f"  [{label}] SELL REJEITADO: {rec['sell_error']}")
        else:
            rec["sell_accepted"] = True
            rec["sell_price"] = float(sell["sell"].get("sold_for", 0))
            rec["sell_profit"] = rec["sell_price"] - rec["buy_price"]
            print(f"  [{label}] SELL ACEITO: sell_price=${rec['sell_price']:.4f} "
                  f"profit=${rec['sell_profit']:+.4f} (buy=${rec['buy_price']:.4f})")

        poc = await client.send_request({
            "proposal_open_contract": 1,
            "contract_id": contract_id,
        })
        poc_data = poc.get("proposal_open_contract", {})
        rec["is_sold"] = poc_data.get("is_sold", 0)
        rec["is_valid_to_sell"] = poc_data.get("is_valid_to_sell", 0)
        rec["bid_price"] = poc_data.get("bid_price")
        rec["underlying"] = poc_data.get("underlying")

        if not rec.get("sell_accepted"):
            if rec["bid_price"] is not None:
                print(f"    bid_price={rec['bid_price']} is_valid_to_sell={rec['is_valid_to_sell']}")

        return rec

    except Exception as e:
        rec["error"] = f"exception: {e}"
        print(f"  [{label}] EXC: {e}")
        return rec


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--trials", type=int, default=2, help="Trials per duration")
    args = parser.parse_args()

    if not APP_ID:
        print("ERRO: DERIV_APP_ID nao encontrado.")
        return

    print("=" * 90)
    print(f"D69 — Long-Duration Resale Probe")
    print(f"  Symbol: {SYMBOL} | Contract: {CONTRACT_TYPE}")
    print(f"  Durations: {[d[2] for d in DURATIONS]}")
    print(f"  Stake: ${STAKE} | Trials per duration: {args.trials}")
    print("=" * 90)

    client = DerivClient(app_id=APP_ID, api_token=TOKEN, use_demo=True)
    await client.connect()
    print(f"  Conectado. Conta: {client.account_id}")

    all_results = []
    for dur, unit, label in DURATIONS:
        print(f"\n  --- Duration: {label} ---")
        for t in range(args.trials):
            rec = await test_duration(client, dur, unit, label, t)
            all_results.append(rec)
            with open(RESULTS_FILE, "a") as f:
                f.write(json.dumps(rec, default=str) + "\n")
            await asyncio.sleep(1)

    print(f"\n{'='*80}")
    print(f"  ANALISE FINAL")
    print(f"{'='*80}")

    valid = [r for r in all_results if "error" not in r]
    print(f"  Tests: {len(all_results)} | Validos: {len(valid)}")

    accepted = [r for r in valid if r.get("sell_accepted")]
    rejected = [r for r in valid if not r.get("sell_accepted")]

    print(f"\n  Sell aceito: {len(accepted)}/{len(valid)}")
    print(f"  Sell rejeitado: {len(rejected)}/{len(valid)}")

    if accepted:
        print(f"\n  Duracoes com sell aceito:")
        for r in accepted:
            print(f"    {r['label']}: sell_price=${r['sell_price']:.4f} "
                  f"profit=${r['sell_profit']:+.4f} (buy=${r['buy_price']:.4f})")

    if rejected:
        print(f"\n  Duracoes com sell rejeitado:")
        rej_by_dur = {}
        for r in rejected:
            rej_by_dur.setdefault(r["label"], []).append(r.get("sell_error", "unknown"))
        for label, errors in rej_by_dur.items():
            print(f"    {label}: {errors[0]}")

    bid_prices = [(r["label"], r.get("bid_price")) for r in valid if r.get("bid_price") is not None]
    if bid_prices:
        print(f"\n  Bid prices disponiveis (POC):")
        for label, bp in bid_prices[:10]:
            print(f"    {label}: bid_price={bp}")

    if accepted:
        print(f"\n  *** RESELL FUNCIONA em {len(accepted)} duracoes!")
        print(f"  Hipotese early-sell pode ser re-testada com capacidade real de venda.")
    else:
        print(f"\n  Sell rejeitado em TODAS as duracoes testadas.")
        print(f"  Deriv nao oferece resale em nenhum contract duration (tick a 1d).")
        print(f"  Hipotese early-sell permanece refutada — sem capacidade de venda real.")

    stats = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "n_tests": len(all_results),
        "valid": len(valid),
        "accepted": len(accepted),
        "rejected": len(rejected),
        "durations": list(set((r["duration"], r["duration_unit"], r["label"]) for r in valid)),
    }
    with open(STATS_FILE, "w") as f:
        json.dump(stats, f, indent=2, default=str)
    print(f"\n  Stats salvas em {STATS_FILE}")

    await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
