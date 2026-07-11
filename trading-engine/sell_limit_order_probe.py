"""
D58 — Sell as Limit Order Probe
================================
Hipotese: o endpoint `sell` da Deriv aceita um parametro `price`. D48/D50
sempre usaram price=0 (market sell). Se enviarmos price > 0, pode funcionar
como limit order — se o bid_price atingir esse valor, o contrato vende a um
preco melhor que o market sell. Se o bid_price nunca atinge, o contrato
expira naturalmente.

Cenario de edge: comprar CALL de 10 ticks, esperar 3-4 ticks, o bid_price
sobe. Se sell com price=bid_atual+epsilon funcionar como limit, podemos
capturar mais valor que market sell (que pode executar abaixo do bid atual
se houver delay).

Metodo:
  1. Comprar CALL/PUT de 10 ticks em 1HZ10V (demo)
  2. Esperar 3 ticks (contrato esta in-the-money ou out-of-the-money)
  3. Consultar POC para obter bid_price atual
  4. Tentar sell com price=bid_price (limit sell)
  5. Comparar com sell com price=0 (market sell) em condicoes identicas
  6. Registrar: sold_for, profit, tempo ate sell, erro/rejeicao
  7. Estatistica: bootstrap CI95% na diferenca limit - market

Uso: python3 sell_limit_order_probe.py [--n=50] [--live]
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
from stats_utils import bootstrap_ci, bootstrap_diff_ci, summarize

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

APP_ID = os.getenv("DERIV_APP_ID")
TOKEN = os.getenv("DERIV_API_TOKEN")

SYMBOL = "1HZ10V"
CONTRACT_TYPE = "CALL"
STAKE = 1.00
DURATION = 10
DURATION_UNIT = "t"
WAIT_TICKS = 3
WAIT_SECONDS = 2

RESULTS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sell_limit_order_results.jsonl")
STATS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sell_limit_order_stats.json")


async def get_poc(client, contract_id):
    resp = await client.send_request({
        "proposal_open_contract": 1,
        "contract_id": contract_id,
    })
    return resp.get("proposal_open_contract", {})


async def run_trial(client, trial_num, use_limit):
    tag = "LIMIT" if use_limit else "MARKET"
    rec = {
        "trial": trial_num,
        "mode": tag,
        "symbol": SYMBOL,
        "contract_type": CONTRACT_TYPE,
        "stake": STAKE,
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
            "duration": DURATION,
            "duration_unit": DURATION_UNIT,
        })
        if "error" in prop:
            rec["error"] = f"proposal: {prop['error'].get('message')}"
            print(f"  [{tag} #{trial_num}] proposal erro: {rec['error']}")
            return rec
        p = prop["proposal"]
        proposal_id = p["id"]
        entry_spot = float(p.get("spot", 0))

        buy = await client.buy_contract(proposal_id, price=STAKE)
        if "error" in buy:
            rec["error"] = f"buy: {buy['error'].get('message')}"
            print(f"  [{tag} #{trial_num}] buy erro: {rec['error']}")
            return rec

        contract_id = buy["buy"]["contract_id"]
        buy_price = float(buy["buy"]["buy_price"])
        rec["buy_price"] = buy_price
        rec["contract_id"] = contract_id

        await asyncio.sleep(WAIT_SECONDS)

        poc = await get_poc(client, contract_id)
        bid_price = float(poc.get("bid_price", 0))
        is_sold = poc.get("is_sold", 0)
        rec["bid_at_sell_attempt"] = bid_price
        rec["is_sold_before_sell"] = is_sold

        if is_sold:
            sold_for = float(poc.get("sold_for", 0))
            profit = sold_for - buy_price
            rec.update({"sold_for": sold_for, "profit": profit, "sell_type": "auto_expired"})
            print(f"  [{tag} #{trial_num}] ja vendido (auto): sold_for=${sold_for:.4f} profit=${profit:+.4f}")
            return rec

        if use_limit and bid_price > 0:
            sell_price = round(bid_price, 2)
        else:
            sell_price = 0

        t0 = time.time()
        sell_resp = await client.sell_contract(contract_id, price=sell_price)
        sell_latency = time.time() - t0

        if "error" in sell_resp:
            rec["error"] = f"sell: {sell_resp['error'].get('message')}"
            rec["sell_latency_ms"] = round(sell_latency * 1000, 1)
            print(f"  [{tag} #{trial_num}] sell erro (price={sell_price}): {rec['error']} "
                  f"({sell_latency*1000:.0f}ms)")
            fallback = await client.sell_contract(contract_id, price=0)
            if "sell" in fallback:
                sold_for = float(fallback["sell"].get("sold_for", 0))
                profit = sold_for - buy_price
                rec.update({"sold_for": sold_for, "profit": profit, "sell_type": "market_fallback"})
                print(f"  [{tag} #{trial_num}] fallback market sell: sold_for=${sold_for:.4f} "
                      f"profit=${profit:+.4f}")
            return rec

        sold_for = float(sell_resp["sell"].get("sold_for", 0))
        profit = sold_for - buy_price
        rec.update({
            "sold_for": sold_for,
            "profit": profit,
            "sell_price_requested": sell_price,
            "sell_latency_ms": round(sell_latency * 1000, 1),
            "sell_type": "limit" if use_limit else "market",
        })
        print(f"  [{tag} #{trial_num}] sell price={sell_price} -> sold_for=${sold_for:.4f} "
              f"profit=${profit:+.4f} ({sell_latency*1000:.0f}ms)")
        return rec

    except Exception as e:
        rec["error"] = f"exception: {e}"
        print(f"  [{tag} #{trial_num}] EXC: {e}")
        return rec


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--n", type=int, default=50)
    parser.add_argument("--live", action="store_true")
    args = parser.parse_args()

    if not APP_ID:
        print("ERRO: DERIV_APP_ID nao encontrado.")
        return

    print("=" * 90)
    print(f"D58 — Sell as Limit Order Probe")
    print(f"  Symbol: {SYMBOL} | Contract: {CONTRACT_TYPE}")
    print(f"  Stake: ${STAKE} | Duration: {DURATION} {DURATION_UNIT}")
    print(f"  Wait: {WAIT_SECONDS}s antes do sell")
    print(f"  Trials: {args.n} (alternating limit/market)")
    print("=" * 90)

    client = DerivClient(app_id=APP_ID, api_token=TOKEN, use_demo=True)
    await client.connect()
    print(f"  Conectado. Conta: {client.account_id}")

    balance_resp = await client.get_balance()
    balance = float(balance_resp.get("balance", {}).get("balance", 0))
    print(f"  Saldo demo: ${balance:.2f}")

    all_results = []
    limit_profits = []
    market_profits = []

    for i in range(args.n):
        use_limit = (i % 2 == 0)
        rec = await run_trial(client, i, use_limit)
        all_results.append(rec)
        with open(RESULTS_FILE, "a") as f:
            f.write(json.dumps(rec) + "\n")
        if "profit" in rec and "error" not in rec:
            if use_limit:
                limit_profits.append(rec["profit"])
            else:
                market_profits.append(rec["profit"])
        await asyncio.sleep(1)

    print(f"\n{'='*80}")
    print(f"  ANALISE FINAL")
    print(f"{'='*80}")

    limit_summary = summarize("LIMIT SELL", limit_profits) if limit_profits else None
    market_summary = summarize("MARKET SELL", market_profits) if market_profits else None

    if limit_profits and market_profits:
        diff_lo, diff_point, diff_hi = bootstrap_diff_ci(limit_profits, market_profits)
        print(f"\n  Diferenca (LIMIT - MARKET): ${diff_point:.4f} "
              f"(IC95% [${diff_lo:.4f}, ${diff_hi:.4f}])")
        if diff_lo > 0:
            print(f"  *** EDGE CONFIRMADO: limit sell e melhor que market sell!")
        elif diff_hi < 0:
            print(f"  *** ANTI-EDGE: limit sell e PIOR que market sell.")
        else:
            print(f"  Sem diferenca significativa (IC cruza zero).")

    limit_errors = sum(1 for r in all_results if r["mode"] == "LIMIT" and "error" in r and "sell:" in r.get("error", ""))
    market_errors = sum(1 for r in all_results if r["mode"] == "MARKET" and "error" in r and "sell:" in r.get("error", ""))
    print(f"\n  Sell errors: LIMIT={limit_errors}/{len([r for r in all_results if r['mode']=='LIMIT'])} "
          f"MARKET={market_errors}/{len([r for r in all_results if r['mode']=='MARKET'])}")

    stats = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "n_trials": len(all_results),
        "limit_summary": limit_summary,
        "market_summary": market_summary,
        "limit_errors": limit_errors,
        "market_errors": market_errors,
        "diff_ci": [diff_lo, diff_point, diff_hi] if limit_profits and market_profits else None,
    }
    with open(STATS_FILE, "w") as f:
        json.dump(stats, f, indent=2, default=str)
    print(f"\n  Stats salvas em {STATS_FILE}")

    await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
