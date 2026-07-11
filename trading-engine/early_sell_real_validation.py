"""
D72 — Early-Sell REAL Validation (fase 2 do D71)
=================================================
D71 encontrou edge em simulacao non-hindsight (monitorou bid mas nao vendeu).
D72 valida com sells REAIS: comprar CALL/PUT 5m, monitorar bid, vender
quando bid >= threshold. Comparar profit real do sell vs profit contrafactual
do hold (que nao pode ser observado diretamente, mas pode ser estimado).

Metodologia A/B pareada:
  - Grupo A (sell): comprar, monitorar bid, vender quando bid >= threshold
  - Grupo B (hold): comprar, NAO vender, deixar expirar
  - Alternar A/B por trial (trial par = sell, trial impar = hold)
  - Comparar EV_A vs EV_B (bootstrap diff)

Isto elimina qualquer concern sobre superestimacao do sell price no D71,
porque o sell e executado de verdade e o profit e observado.

Thresholds: 1.30 e 1.50 (melhores do D71, equilibrio trigger rate vs profit)

Uso: python3 early_sell_real_validation.py [--n=40] [--threshold=1.30]
"""
import argparse
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
DURATION_UNIT = "m"
POLL_INTERVAL = 1.5

RESULTS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "early_sell_real_validation_results.jsonl")
STATS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "early_sell_real_validation_stats.json")


async def buy_contract(client, contract_type, trial_num):
    try:
        prop = await client.send_request({
            "proposal": 1,
            "amount": STAKE,
            "basis": "stake",
            "contract_type": contract_type,
            "currency": "USD",
            "underlying_symbol": SYMBOL,
            "duration": DURATION,
            "duration_unit": DURATION_UNIT,
        })
        if "error" in prop:
            return {"error": f"proposal: {prop['error'].get('message')}"}

        buy = await client.buy_contract(prop["proposal"]["id"], price=STAKE)
        if "error" in buy:
            return {"error": f"buy: {buy['error'].get('message')}"}

        return {
            "contract_id": buy["buy"]["contract_id"],
            "buy_price": float(buy["buy"]["buy_price"]),
            "contract_type": contract_type,
        }
    except Exception as e:
        return {"error": str(e)}


async def get_poc(client, contract_id):
    try:
        poc = await client.send_request({
            "proposal_open_contract": 1,
            "contract_id": contract_id,
        })
        return poc.get("proposal_open_contract", {})
    except:
        return {}


async def run_sell_trial(client, trial_num, contract_type, threshold):
    """Grupo A: comprar, monitorar bid, vender quando bid >= threshold."""
    rec = {
        "trial": trial_num,
        "group": "sell",
        "contract_type": contract_type,
        "threshold": threshold,
        "ts": datetime.now(timezone.utc).isoformat(),
    }

    buy = await buy_contract(client, contract_type, trial_num)
    if "error" in buy:
        rec["error"] = buy["error"]
        print(f"  [#{trial_num} SELL {contract_type}] buy erro: {rec['error']}")
        return rec

    contract_id = buy["contract_id"]
    buy_price = buy["buy_price"]
    rec["contract_id"] = contract_id
    rec["buy_price"] = buy_price

    t0 = time.time()
    max_wait = DURATION * 60 + 30
    sold = False
    bid_path = []

    while time.time() - t0 < max_wait:
        poc_data = await get_poc(client, contract_id)

        bid = poc_data.get("bid_price")
        is_sold = poc_data.get("is_sold", 0)

        if bid is not None:
            try:
                bid_val = float(bid)
            except:
                bid_val = None
            if bid_val is not None:
                bid_ratio = bid_val / buy_price if buy_price > 0 else 0
                bid_path.append({
                    "t": round(time.time() - t0, 1),
                    "bid": bid_val,
                    "bid_ratio": round(bid_ratio, 4),
                })

                if not sold and bid_ratio >= threshold:
                    sell_resp = await client.sell_contract(contract_id, price=0)
                    if "error" not in sell_resp:
                        sold_for = float(sell_resp["sell"].get("sold_for", 0))
                        rec["sold"] = True
                        rec["sell_price"] = sold_for
                        rec["sell_profit"] = sold_for - buy_price
                        rec["sell_time"] = round(time.time() - t0, 1)
                        rec["sell_bid_ratio"] = round(bid_ratio, 4)
                        print(f"  [#{trial_num} SELL {contract_type}] SOLD at bid_ratio={bid_ratio:.3f} "
                              f"profit=${rec['sell_profit']:+.4f} t={rec['sell_time']:.0f}s")
                        return rec
                    else:
                        rec["sell_error"] = sell_resp["error"].get("message")

        if is_sold:
            profit = float(poc_data.get("profit", 0))
            rec["sold"] = False
            rec["expired"] = True
            rec["hold_profit"] = profit
            rec["max_bid_ratio"] = max((p["bid_ratio"] for p in bid_path), default=0)
            print(f"  [#{trial_num} SELL {contract_type}] EXPIRED (threshold not hit) "
                  f"hold_profit=${profit:+.4f} max_bid_ratio={rec['max_bid_ratio']:.3f}")
            return rec

        await asyncio.sleep(POLL_INTERVAL)

    rec["sold"] = False
    rec["timeout"] = True
    rec["max_bid_ratio"] = max((p["bid_ratio"] for p in bid_path), default=0)
    print(f"  [#{trial_num} SELL {contract_type}] TIMEOUT")
    return rec


async def run_hold_trial(client, trial_num, contract_type):
    """Grupo B: comprar, NAO vender, deixar expirar."""
    rec = {
        "trial": trial_num,
        "group": "hold",
        "contract_type": contract_type,
        "ts": datetime.now(timezone.utc).isoformat(),
    }

    buy = await buy_contract(client, contract_type, trial_num)
    if "error" in buy:
        rec["error"] = buy["error"]
        print(f"  [#{trial_num} HOLD {contract_type}] buy erro: {rec['error']}")
        return rec

    contract_id = buy["contract_id"]
    buy_price = buy["buy_price"]
    rec["contract_id"] = contract_id
    rec["buy_price"] = buy_price

    t0 = time.time()
    max_wait = DURATION * 60 + 60

    while time.time() - t0 < max_wait:
        poc_data = await get_poc(client, contract_id)
        if poc_data.get("is_sold", 0):
            profit = float(poc_data.get("profit", 0))
            is_won = poc_data.get("is_won")
            if is_won is None:
                is_won = 1 if profit > 0 else 0
            rec["hold_profit"] = profit
            rec["is_won"] = int(is_won)
            won_str = "WON" if is_won else "LOST"
            print(f"  [#{trial_num} HOLD {contract_type}] {won_str} "
                  f"hold_profit=${profit:+.4f}")
            return rec
        await asyncio.sleep(POLL_INTERVAL)

    rec["timeout"] = True
    print(f"  [#{trial_num} HOLD {contract_type}] TIMEOUT")
    return rec


def bootstrap_ci(data, n_boot=10000, confidence=0.95):
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
    parser.add_argument("--n", type=int, default=40)
    parser.add_argument("--threshold", type=float, default=1.30)
    args = parser.parse_args()

    if not APP_ID:
        print("ERRO: DERIV_APP_ID nao encontrado.")
        return

    print("=" * 90)
    print(f"D72 — Early-Sell REAL Validation (A/B pareado)")
    print(f"  Symbol: {SYMBOL} | Duration: {DURATION}{DURATION_UNIT} | Stake: ${STAKE}")
    print(f"  Threshold: {args.threshold} | Trials: {args.n} (A/B alternado)")
    print(f"  Grupo A (sell): vender quando bid >= {args.threshold}x buy")
    print(f"  Grupo B (hold): deixar expirar")
    print(f"  Runtime estimado: {args.n * DURATION}min = {args.n * DURATION / 60:.1f}h")
    print("=" * 90)

    client = DerivClient(app_id=APP_ID, api_token=TOKEN, use_demo=True)
    await client.connect()
    print(f"  Conectado. Conta: {client.account_id}")

    all_results = []
    for i in range(args.n):
        ct = "CALL" if i % 4 < 2 else "PUT"
        if i % 2 == 0:
            rec = await run_sell_trial(client, i, ct, args.threshold)
        else:
            rec = await run_hold_trial(client, i, ct)
        all_results.append(rec)
        with open(RESULTS_FILE, "a") as f:
            f.write(json.dumps(rec, default=str) + "\n")
        await asyncio.sleep(1)

    print(f"\n{'='*80}")
    print(f"  ANALISE FINAL — A/B PAREADO")
    print(f"{'='*80}")

    sell_results = [r for r in all_results if r.get("group") == "sell" and "error" not in r]
    hold_results = [r for r in all_results if r.get("group") == "hold" and "error" not in r]

    sell_valid = []
    for r in sell_results:
        if r.get("sold"):
            sell_valid.append(r["sell_profit"])
        elif r.get("expired"):
            sell_valid.append(r["hold_profit"])
        elif r.get("hold_profit") is not None:
            sell_valid.append(r["hold_profit"])

    hold_valid = [r["hold_profit"] for r in hold_results if r.get("hold_profit") is not None]

    print(f"\n  Grupo A (sell): N={len(sell_valid)}")
    print(f"  Grupo B (hold): N={len(hold_valid)}")

    if len(sell_valid) < 5 or len(hold_valid) < 5:
        print("  Dados insuficientes.")
        await client.disconnect()
        return

    sell_ev = statistics.mean(sell_valid)
    hold_ev = statistics.mean(hold_valid)
    sell_wr = sum(1 for p in sell_valid if p > 0) / len(sell_valid)
    hold_wr = sum(1 for p in hold_valid if p > 0) / len(hold_valid)

    print(f"\n  Sell: EV=${sell_ev:+.4f} WR={sell_wr*100:.1f}% (N={len(sell_valid)})")
    print(f"  Hold: EV=${hold_ev:+.4f} WR={hold_wr*100:.1f}% (N={len(hold_valid)})")

    sold_count = sum(1 for r in sell_results if r.get("sold"))
    expired_count = sum(1 for r in sell_results if r.get("expired"))
    print(f"\n  Sell group: {sold_count} sold, {expired_count} expired (threshold not hit)")

    if sold_count > 0:
        sold_profits = [r["sell_profit"] for r in sell_results if r.get("sold")]
        avg_sell_profit = statistics.mean(sold_profits)
        avg_sell_time = statistics.mean([r["sell_time"] for r in sell_results if r.get("sold")])
        print(f"  Avg sell profit: ${avg_sell_profit:+.4f}")
        print(f"  Avg sell time: {avg_sell_time:.0f}s (of {DURATION*60}s)")

    diffs = []
    min_n = min(len(sell_valid), len(hold_valid))
    for i in range(min_n):
        diffs.append(sell_valid[i] - hold_valid[i])

    mean_diff, ci_lo, ci_hi = bootstrap_ci(diffs)

    print(f"\n  Diff (sell - hold): ${mean_diff:+.4f} CI95%[${ci_lo:+.4f}, ${ci_hi:+.4f}]")

    if ci_lo > 0:
        print(f"\n  *** EDGE CONFIRMADO COM SELLS REAIS!")
        print(f"  Sell no threshold {args.threshold} tem EV positivo vs hold-to-expiry.")
        print(f"  D71 edge validado com execucao real.")
    elif ci_hi < 0:
        print(f"\n  EDGE REFUTADO — sell cedo e pior que hold (com sells reais).")
        print(f"  D71 era falso-positivo (superestimacao do sell price no poll).")
    else:
        print(f"\n  INCONCLUSIVO — CI95% cruza zero.")
        print(f"  Precisa mais N para conclusao.")

    stats = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "n_trials": len(all_results),
        "threshold": args.threshold,
        "sell_n": len(sell_valid),
        "hold_n": len(hold_valid),
        "sell_ev": sell_ev,
        "hold_ev": hold_ev,
        "sell_wr": sell_wr,
        "hold_wr": hold_wr,
        "sold_count": sold_count,
        "expired_count": expired_count,
        "mean_diff": mean_diff,
        "ci95": [ci_lo, ci_hi],
    }
    with open(STATS_FILE, "w") as f:
        json.dump(stats, f, indent=2, default=str)
    print(f"\n  Stats salvas em {STATS_FILE}")

    await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
