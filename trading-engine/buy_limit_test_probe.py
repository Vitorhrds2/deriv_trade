"""
D81 — Buy Limit Order Test
============================
Pode-se comprar com price < ask_price na Deriv? Se sim, age como limit order.
D58 testou sell limit, mas buy limit nunca foi testado.

Metodologia:
  1. Solicitar proposal CALL 5t 1HZ10V
  2. Obter ask_price
  3. Tentar buy com price = ask_price * 0.50 (50% do ask)
  4. Tentar buy com price = ask_price * 0.80
  5. Tentar buy com price = ask_price * 0.95
  6. Tentar buy com price = 0.01 (quase gratis)
  7. Para cada tentativa, verificar:
     - Buy sucedeu? A que preco?
     - Se sucedeu, qual o payout? E o profit no settlement?

Se buy com price < ask suceder, e optionality gratuita:
  - Comprar barato quando ask esta alto
  - O contrato ainda paga payout completo no win

Cuidado: se o buy falhar, o proposal_id pode expirar.
"""
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
DURATION = 5
DURATION_UNIT = "t"
N_TRIALS = 5

# Price fractions to test (fraction of ask_price)
PRICE_FRACTIONS = [0.01, 0.10, 0.25, 0.50, 0.75, 0.90, 0.95, 1.00]

RESULTS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            "buy_limit_test_results.jsonl")


async def main():
    print("=" * 90)
    print("D81 — Buy Limit Order Test")
    print(f"  Symbol: {SYMBOL} | Duration: {DURATION}{DURATION_UNIT} | Stake: ${STAKE}")
    print(f"  Price fractions: {PRICE_FRACTIONS}")
    print(f"  Trials per fraction: {N_TRIALS}")
    print("=" * 90)

    client = DerivClient(app_id=APP_ID, api_token=TOKEN, use_demo=True)
    await client.connect()
    print(f"  Conectado. Conta: {client.account_id}")

    all_results = []

    for fraction in PRICE_FRACTIONS:
        print(f"\n  --- Price fraction {fraction:.2f}x ask ---")
        for trial in range(N_TRIALS):
            rec = {
                "fraction": fraction,
                "trial": trial,
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
                print(f"    [{fraction:.2f}x #{trial}] proposal erro: {rec['error']}")
                all_results.append(rec)
                continue

            proposal_id = prop["proposal"]["id"]
            ask_price = float(prop["proposal"]["ask_price"])
            payout = float(prop["proposal"].get("payout", 0))
            limit_price = round(ask_price * fraction, 2)

            rec["ask_price"] = ask_price
            rec["payout"] = payout
            rec["limit_price"] = limit_price

            # Try buy with limit price
            buy = await client.send_request({
                "buy": proposal_id,
                "price": limit_price,
            })

            if "error" in buy:
                rec["buy_error"] = buy["error"].get("message", "")
                rec["buy_succeeded"] = False
                print(f"    [{fraction:.2f}x #{trial}] BUY FAILED: {rec['buy_error']} "
                      f"(ask=${ask_price:.4f} limit=${limit_price:.4f})")
                all_results.append(rec)
                with open(RESULTS_FILE, "a") as f:
                    f.write(json.dumps(rec, default=str) + "\n")
                await asyncio.sleep(1)
                continue

            rec["buy_succeeded"] = True
            buy_price = float(buy["buy"]["buy_price"])
            contract_id = buy["buy"]["contract_id"]
            rec["actual_buy_price"] = buy_price
            rec["contract_id"] = contract_id
            rec["discount"] = ask_price - buy_price
            rec["discount_pct"] = (ask_price - buy_price) / ask_price * 100 if ask_price > 0 else 0

            print(f"    [{fraction:.2f}x #{trial}] BUY OK! "
                  f"ask=${ask_price:.4f} paid=${buy_price:.4f} "
                  f"discount=${rec['discount']:.4f} ({rec['discount_pct']:.1f}%)")

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
                    rec["payout_received"] = buy_price + profit
                    won_str = "WON" if is_won else "LOST"
                    print(f"      -> {won_str} profit=${profit:+.4f} "
                          f"(paid=${buy_price:.4f} payout=${buy_price + profit:.4f})")
                    break

            all_results.append(rec)
            with open(RESULTS_FILE, "a") as f:
                f.write(json.dumps(rec, default=str) + "\n")
            await asyncio.sleep(1)

    # Analysis
    print(f"\n{'='*90}")
    print("  ANALISE FINAL — BUY LIMIT ORDER")
    print(f"{'='*90}")

    print("\n  1. TAXA DE SUCESSO POR FRACTION:")
    for fraction in PRICE_FRACTIONS:
        frac_results = [r for r in all_results if r.get("fraction") == fraction]
        succeeded = [r for r in frac_results if r.get("buy_succeeded")]
        failed = [r for r in frac_results if r.get("buy_error")]
        success_rate = len(succeeded) / len(frac_results) if frac_results else 0
        print(f"    {fraction:.2f}x: {len(succeeded)}/{len(frac_results)} sucedeu "
              f"({success_rate*100:.0f}%)")
        if failed:
            errors = set(r["buy_error"] for r in failed)
            print(f"      erros: {errors}")

    print("\n  2. DISCOUNT ALCANCADO:")
    for fraction in PRICE_FRACTIONS:
        succeeded = [r for r in all_results if r.get("fraction") == fraction
                     and r.get("buy_succeeded")]
        if succeeded:
            discounts = [r["discount"] for r in succeeded]
            avg_disc = sum(discounts) / len(discounts)
            print(f"    {fraction:.2f}x: avg discount=${avg_disc:.4f} "
                  f"(paid ${succeeded[0]['actual_buy_price']:.4f} "
                  f"vs ask ${succeeded[0]['ask_price']:.4f})")

    print("\n  3. VEREDITO:")
    any_discount = any(r.get("discount", 0) > 0.01 for r in all_results if r.get("buy_succeeded"))
    if any_discount:
        print(f"    *** BUY LIMIT FUNCIONA — pode comprar com price < ask_price!")
        print(f"    Optionality gratuita: comprar barato, receber payout completo")
        # Calculate EV
        won_with_discount = [r for r in all_results
                              if r.get("buy_succeeded") and r.get("discount", 0) > 0.01
                              and r.get("is_won") is not None]
        if won_with_discount:
            profits = [r["profit"] for r in won_with_discount]
            avg_profit = sum(profits) / len(profits)
            print(f"    EV com discount: ${avg_profit:+.4f} (N={len(profits)})")
    else:
        print(f"    Buy limit NAO funciona — Deriv sempre cobra ask_price completa")
        print(f"    Ou rejeita buy com price < ask")

    await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
