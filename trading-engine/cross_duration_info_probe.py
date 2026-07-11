"""
D67 — Cross-Duration Sequential Info Edge
==========================================
Hipotese: Comprar CALL 5-tick + CALL 10-tick simultaneamente. Apos o
5-tick settle, voce sabe a direcao de 5 dos 10 ticks. Se ha autocorrelacao,
saber os primeiros 5 ticks da edge nos 5 restantes do contrato de 10 ticks.

D46 testou padroes de 3 ticks para mean-reversion. Isto testa informacao
parcial em contratos sobrepostos — uma estrutura diferente.

Se P(10-tick WON | 5-tick WON) != P(10-tick WON | 5-tick LOST), ha edge.
Se forem iguais, ticks sao independentes e nao ha informacao aproveitavel.

Metodo:
  1. Comprar CALL 5-tick e CALL 10-tick simultaneamente em 1HZ10V
  2. Aguardar ambos settle
  3. Registrar: outcome_5t (WON/LOST), outcome_10t (WON/LOST)
  4. Repetir N trials
  5. Comparar P(10t WON | 5t WON) vs P(10t WON | 5t LOST)

Uso: python3 cross_duration_info_probe.py [--n=40]
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
STAKE = 1.00
SHORT_DUR = 5
LONG_DUR = 10
DURATION_UNIT = "t"

RESULTS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cross_duration_info_results.jsonl")
STATS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cross_duration_info_stats.json")


async def buy_call(client, duration, trial_num):
    try:
        prop = await client.send_request({
            "proposal": 1,
            "amount": STAKE,
            "basis": "stake",
            "contract_type": "CALL",
            "currency": "USD",
            "underlying_symbol": SYMBOL,
            "duration": duration,
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
        }
    except Exception as e:
        return {"error": str(e)}


async def wait_settle(client, contract_id, max_wait_s=120):
    t0 = time.time()
    while time.time() - t0 < max_wait_s:
        await asyncio.sleep(0.5)
        try:
            poc = await client.send_request({
                "proposal_open_contract": 1,
                "contract_id": contract_id,
            })
            poc_data = poc.get("proposal_open_contract", {})
            if poc_data.get("is_sold", 0):
                return {
                    "is_sold": 1,
                    "is_won": poc_data.get("is_won", 0),
                    "profit": float(poc_data.get("profit", 0)),
                    "entry_spot": float(poc_data.get("entry_spot", 0) or 0),
                    "exit_spot": float(poc_data.get("exit_tick", 0) or 0),
                    "tick_count": poc_data.get("tick_count"),
                }
        except:
            pass
    return {"is_sold": 0, "timeout": True}


async def run_trial(client, trial_num):
    rec = {"trial": trial_num, "ts": datetime.now(timezone.utc).isoformat()}

    short = await buy_call(client, SHORT_DUR, trial_num)
    await asyncio.sleep(0.2)
    long_ = await buy_call(client, LONG_DUR, trial_num)

    if "error" in short:
        rec["error"] = f"short: {short['error']}"
        return rec
    if "error" in long_:
        rec["error"] = f"long: {long_['error']}"
        return rec

    rec["short_contract_id"] = short["contract_id"]
    rec["long_contract_id"] = long_["contract_id"]
    rec["short_buy_price"] = short["buy_price"]
    rec["long_buy_price"] = long_["buy_price"]

    short_result = await wait_settle(client, short["contract_id"], max_wait_s=30)
    rec["short_won"] = short_result.get("is_won", 0)
    rec["short_profit"] = short_result.get("profit")
    rec["short_entry"] = short_result.get("entry_spot")
    rec["short_exit"] = short_result.get("exit_spot")

    long_result = await wait_settle(client, long_["contract_id"], max_wait_s=60)
    rec["long_won"] = long_result.get("is_won", 0)
    rec["long_profit"] = long_result.get("profit")
    rec["long_entry"] = long_result.get("entry_spot")
    rec["long_exit"] = long_result.get("exit_spot")

    short_str = "WON" if rec["short_won"] else "LOST"
    long_str = "WON" if rec["long_won"] else "LOST"
    se_str = f"{rec['short_entry']:.2f}" if rec.get("short_entry") else "N/A"
    le_str = f"{rec['long_entry']:.2f}" if rec.get("long_entry") else "N/A"
    print(f"  [#{trial_num}] 5t={short_str} 10t={long_str} "
          f"entry_s={se_str} entry_l={le_str}")

    return rec


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--n", type=int, default=40)
    args = parser.parse_args()

    if not APP_ID:
        print("ERRO: DERIV_APP_ID nao encontrado.")
        return

    print("=" * 90)
    print(f"D67 — Cross-Duration Sequential Info Edge")
    print(f"  Symbol: {SYMBOL} | Short: CALL {SHORT_DUR}t | Long: CALL {LONG_DUR}t")
    print(f"  Stake: ${STAKE} | Trials: {args.n}")
    print("=" * 90)

    client = DerivClient(app_id=APP_ID, api_token=TOKEN, use_demo=True)
    await client.connect()
    print(f"  Conectado. Conta: {client.account_id}")

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

    valid = [r for r in all_results if "error" not in r and r.get("short_won") is not None and r.get("long_won") is not None]
    print(f"  Trials: {len(all_results)} | Validos: {len(valid)}")

    short_wins = sum(1 for r in valid if r["short_won"])
    long_wins = sum(1 for r in valid if r["long_won"])
    both_won = sum(1 for r in valid if r["short_won"] and r["long_won"])
    short_won_long_lost = sum(1 for r in valid if r["short_won"] and not r["long_won"])
    short_lost_long_won = sum(1 for r in valid if not r["short_won"] and r["long_won"])
    both_lost = sum(1 for r in valid if not r["short_won"] and not r["long_won"])

    print(f"\n  Matriz de confusao:")
    print(f"                    10t WON    10t LOST")
    print(f"    5t WON:         {both_won:5d}      {short_won_long_lost:5d}")
    print(f"    5t LOST:        {short_lost_long_won:5d}      {both_lost:5d}")

    p_long_given_short_won = both_won / short_wins if short_wins > 0 else 0
    p_long_given_short_lost = short_lost_long_won / (len(valid) - short_wins) if (len(valid) - short_wins) > 0 else 0
    p_long_overall = long_wins / len(valid) if valid else 0

    print(f"\n  P(10t WON | 5t WON)  = {p_long_given_short_won:.3f} ({both_won}/{short_wins})")
    print(f"  P(10t WON | 5t LOST) = {p_long_given_short_lost:.3f} ({short_lost_long_won}/{len(valid)-short_wins})")
    print(f"  P(10t WON) overall   = {p_long_overall:.3f} ({long_wins}/{len(valid)})")

    diff = p_long_given_short_won - p_long_given_short_lost
    print(f"\n  Diff: {diff:+.3f}")

    if abs(diff) < 0.05:
        print(f"\n  Diff < 5% — ticks sao independentes, nao ha info edge.")
    elif diff > 0.1:
        print(f"\n  *** EDGE POSITIVO: saber 5t WON aumenta P(10t WON) em {diff:.1%}")
    elif diff < -0.1:
        print(f"\n  *** EDGE NEGATIVO: saber 5t WON DIMINUI P(10t WON) em {abs(diff):.1%}")
    else:
        print(f"\n  Sinal fraco ({diff:+.1%}) — inconclusivo, precisa mais N.")

    short_profits = [r["short_profit"] for r in valid if r.get("short_profit") is not None]
    long_profits = [r["long_profit"] for r in valid if r.get("long_profit") is not None]
    if short_profits:
        print(f"\n  P&L 5t: ${sum(short_profits):+.2f} ({len(short_profits)} trades)")
    if long_profits:
        print(f"  P&L 10t: ${sum(long_profits):+.2f} ({len(long_profits)} trades)")

    stats = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "n_trials": len(all_results),
        "valid": len(valid),
        "confusion": {"both_won": both_won, "sw_ll": short_won_long_lost, "sl_lw": short_lost_long_won, "both_lost": both_lost},
        "p_long_given_short_won": p_long_given_short_won,
        "p_long_given_short_lost": p_long_given_short_lost,
        "p_long_overall": p_long_overall,
        "diff": diff,
    }
    with open(STATS_FILE, "w") as f:
        json.dump(stats, f, indent=2, default=str)
    print(f"\n  Stats salvas em {STATS_FILE}")

    await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
