"""
D71 — Early-Sell Real Probe (non-hindsight, paired comparison)
===============================================================
D69 descobriu que sell funciona em duracoes > tick. Isto reabre HYP-SELL-01
(early-sell optionality), refutada anteriormente por hindsight bias na
simulacao original (usava max(bid) do caminho todo — so conhecido no expiry).

Metodologia corrigida (sem hindsight):
  1. Comprar CALL/PUT 5m em 1HZ10V (alternar direcao para evitar bias direcional)
  2. NAO vender — apenas monitorar bid_price via POC polling durante toda a vida
  3. Registrar: buy_price, bid_price path, final outcome (profit do hold)
  4. Para cada threshold predefinido (1.1, 1.3, 1.5, 1.7, 2.0):
     - sell_rule_profit = bid_price[primeiro_hit] - buy_price (se threshold atingido)
     - sell_rule_profit = hold_profit (se threshold NUNCA atingido — regra segura)
     - hold_profit = profit final do contrato (payout - buy_price ou -buy_price)
     - diff = sell_rule_profit - hold_profit (PAREADO por trial)
  5. Bootstrap diff para IC95%

Isto NAO e hindsight porque:
  - Threshold e predefinido antes do trial
  - Regra de sell e mecanica (vender no primeiro bid >= threshold)
  - Comparacao e pareada por trial (mesmo trial, duas estrategias)
  - Nao usamos max(bid) — usamos primeiro(bid >= threshold)

Uso: python3 early_sell_real_probe.py [--n=30]
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
THRESHOLDS = [1.05, 1.10, 1.30, 1.50, 1.70, 2.00]
POLL_INTERVAL = 2.0

RESULTS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "early_sell_real_results.jsonl")
STATS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "early_sell_real_stats.json")


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


async def monitor_contract(client, contract_id, buy_price, trial_num, contract_type):
    path = []
    t0 = time.time()
    max_wait = DURATION * 60 + 60
    final = None

    while time.time() - t0 < max_wait:
        try:
            poc = await client.send_request({
                "proposal_open_contract": 1,
                "contract_id": contract_id,
            })
            poc_data = poc.get("proposal_open_contract", {})

            bid = poc_data.get("bid_price")
            spot = poc_data.get("current_spot")
            is_sold = poc_data.get("is_sold", 0)

            elapsed = time.time() - t0

            if bid is not None:
                try:
                    bid_val = float(bid)
                except:
                    bid_val = None
                if bid_val is not None:
                    path.append({
                        "t": round(elapsed, 1),
                        "bid": bid_val,
                        "bid_ratio": round(bid_val / buy_price, 4) if buy_price > 0 else 0,
                        "spot": float(spot) if spot else None,
                    })

            if is_sold:
                profit = float(poc_data.get("profit", 0))
                is_won = poc_data.get("is_won", 0)
                payout = float(poc_data.get("payout", 0))
                sell_price = float(poc_data.get("sell_price", 0))
                final = {
                    "is_won": is_won,
                    "profit": profit,
                    "payout": payout,
                    "sell_price": sell_price if sell_price > 0 else None,
                    "entry_spot": float(poc_data.get("entry_spot", 0) or 0),
                    "exit_spot": float(poc_data.get("exit_tick", 0) or 0),
                    "elapsed": round(elapsed, 1),
                }
                break
        except:
            pass
        await asyncio.sleep(POLL_INTERVAL)

    if final is None:
        final = {"timeout": True, "profit": None}

    return path, final


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
    mean_val = statistics.mean(data)
    return mean_val, lo, hi


async def run_trial(client, trial_num, contract_type):
    rec = {
        "trial": trial_num,
        "contract_type": contract_type,
        "ts": datetime.now(timezone.utc).isoformat(),
    }

    buy = await buy_contract(client, contract_type, trial_num)
    if "error" in buy:
        rec["error"] = buy["error"]
        print(f"  [#{trial_num} {contract_type}] buy erro: {rec['error']}")
        return rec

    rec["contract_id"] = buy["contract_id"]
    rec["buy_price"] = buy["buy_price"]

    path, final = await monitor_contract(client, buy["contract_id"], buy["buy_price"], trial_num, contract_type)

    rec["bid_path"] = path
    rec["final"] = final
    rec["n_bid_points"] = len(path)

    hold_profit = final.get("profit")
    if hold_profit is not None:
        rec["hold_profit"] = hold_profit
        max_bid = max((p["bid"] for p in path), default=0)
        max_ratio = max((p["bid_ratio"] for p in path), default=0)
        won = "WON" if final.get("is_won") else "LOST"
        print(f"  [#{trial_num} {contract_type}] {won} hold_profit=${hold_profit:+.2f} "
              f"max_bid_ratio={max_ratio:.3f} n_bid={len(path)}")
    else:
        rec["hold_profit"] = None
        print(f"  [#{trial_num} {contract_type}] TIMEOUT — sem final outcome")

    return rec


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--n", type=int, default=30)
    args = parser.parse_args()

    if not APP_ID:
        print("ERRO: DERIV_APP_ID nao encontrado.")
        return

    print("=" * 90)
    print(f"D71 — Early-Sell Real Probe (non-hindsight, paired)")
    print(f"  Symbol: {SYMBOL} | Duration: {DURATION}{DURATION_UNIT} | Stake: ${STAKE}")
    print(f"  Contract types: CALL/PUT alternados | Trials: {args.n}")
    print(f"  Thresholds (bid/buy): {THRESHOLDS}")
    print(f"  Poll interval: {POLL_INTERVAL}s | Runtime estimado: {args.n * DURATION}min = {args.n * DURATION / 60:.1f}h")
    print("=" * 90)

    client = DerivClient(app_id=APP_ID, api_token=TOKEN, use_demo=True)
    await client.connect()
    print(f"  Conectado. Conta: {client.account_id}")

    all_results = []
    for i in range(args.n):
        ct = "CALL" if i % 2 == 0 else "PUT"
        rec = await run_trial(client, i, ct)
        all_results.append(rec)
        with open(RESULTS_FILE, "a") as f:
            f.write(json.dumps(rec, default=str) + "\n")
        await asyncio.sleep(1)

    print(f"\n{'='*80}")
    print(f"  ANALISE FINAL")
    print(f"{'='*80}")

    valid = [r for r in all_results if "error" not in r and r.get("hold_profit") is not None and r.get("bid_path")]
    print(f"  Trials: {len(all_results)} | Validos: {len(valid)}")

    if len(valid) < 5:
        print("  Dados insuficientes para analise.")
        await client.disconnect()
        return

    hold_profits = [r["hold_profit"] for r in valid]
    hold_ev = statistics.mean(hold_profits)
    hold_wr = sum(1 for p in hold_profits if p > 0) / len(hold_profits)
    print(f"\n  Hold-to-expiry: EV=${hold_ev:+.4f} WR={hold_wr*100:.1f}% (N={len(valid)})")

    max_bids = [max((p["bid_ratio"] for p in r["bid_path"]), default=0) for r in valid]
    print(f"  Max bid ratio: mean={statistics.mean(max_bids):.3f} max={max(max_bids):.3f}")

    print(f"\n  Analise por threshold (non-hindsight, pareado):")
    print(f"  {'Threshold':>10s} {'Triggered':>10s} {'Sell EV':>10s} {'Hold EV':>10s} {'Diff':>10s} {'CI95%':>20s} {'Verdict':>10s}")
    print(f"  {'-'*10} {'-'*10} {'-'*10} {'-'*10} {'-'*10} {'-'*20} {'-'*10}")

    threshold_results = {}

    for threshold in THRESHOLDS:
        diffs = []
        sell_profits = []
        triggered = 0

        for r in valid:
            buy_price = r["buy_price"]
            hold_profit = r["hold_profit"]

            sell_price = None
            for p in r["bid_path"]:
                if p["bid_ratio"] >= threshold:
                    sell_price = p["bid"]
                    break

            if sell_price is not None:
                sell_rule_profit = sell_price - buy_price
                triggered += 1
            else:
                sell_rule_profit = hold_profit

            sell_profits.append(sell_rule_profit)
            diff = sell_rule_profit - hold_profit
            diffs.append(diff)

        sell_ev = statistics.mean(sell_profits)
        mean_diff, ci_lo, ci_hi = bootstrap_ci(diffs)
        trigger_pct = triggered / len(valid) * 100

        if ci_lo > 0:
            verdict = "EDGE!"
        elif ci_hi < 0:
            verdict = "negativo"
        else:
            verdict = "neutro"

        print(f"  {threshold:>10.2f} {triggered:>5d}/{len(valid):<4d} {sell_ev:>+10.4f} {hold_ev:>+10.4f} {mean_diff:>+10.4f} [{ci_lo:+.4f},{ci_hi:+.4f}] {verdict:>10s}")

        threshold_results[str(threshold)] = {
            "triggered": triggered,
            "total": len(valid),
            "sell_ev": sell_ev,
            "hold_ev": hold_ev,
            "mean_diff": mean_diff,
            "ci95": [ci_lo, ci_hi],
            "verdict": verdict,
        }

    any_edge = any(v["ci95"][0] > 0 for v in threshold_results.values())
    if any_edge:
        print(f"\n  *** EDGE ENCONTRADO em pelo menos um threshold!")
        print(f"  Sell no momento certo tem EV positivo vs hold-to-expiry.")
        print(f"  PROXIMO PASSO: validar com sells reais (nao apenas simulacao).")
    else:
        all_negative = all(v["ci95"][1] < 0 for v in threshold_results.values())
        if all_negative:
            print(f"\n  TODOS thresholds negativos — sell cedo e pior que hold.")
        else:
            print(f"\n  Nenhum threshold com edge significativo.")
            print(f"  Sell cedo nao tem EV positivo vs hold-to-expiry (sem hindsight bias).")
            print(f"  HYP-SELL-01 permanece refutada — agora com metodologia correta.")

    stats = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "n_trials": len(all_results),
        "valid": len(valid),
        "hold_ev": hold_ev,
        "hold_wr": hold_wr,
        "thresholds": threshold_results,
    }
    with open(STATS_FILE, "w") as f:
        json.dump(stats, f, indent=2, default=str)
    print(f"\n  Stats salvas em {STATS_FILE}")

    await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
