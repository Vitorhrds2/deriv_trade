"""
D57 — Stake Size Non-Linearity Probe
=====================================
Hipotese: o ask_price da Deriv pode nao escalar perfeitamente linear com o
stake. Se houver arredondamento ou descontinuidade em certos tamanhos, o
payout efetivo pode variar, criando uma edge onde certos stakes tem payout
ratio melhor que outros.

Metodo:
  1. Para cada contract_type (CALL, PUT) em varios simbolos sinteticos,
     solicitar proposals com uma grade de stakes (de $0.35 a $100.00)
  2. Para cada proposal, registrar: stake, ask_price, payout, payout_ratio
  3. Verificar se payout_ratio = payout/stake e constante ou varia
  4. Se variar, identificar stakes otimos e calcular edge potencial
  5. Repetir N rodadas para capturar variacao temporal
  6. Bonferroni: corrigir para multiplos testes

Uso: python3 stake_nonlinearity_probe.py [--rounds=20] [--live]
"""
import argparse
import asyncio
import json
import math
import os
import statistics
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

SYMBOLS = ["1HZ10V", "1HZ50V", "R_10", "R_50", "R_100"]
CONTRACT_TYPES = ["CALL", "PUT"]
STAKES = [0.35, 0.36, 0.40, 0.50, 0.75, 1.00, 2.00, 5.00, 10.00, 25.00, 50.00, 100.00]
DURATION = 5
DURATION_UNIT = "t"

RESULTS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "stake_nonlinearity_results.jsonl")
STATS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "stake_nonlinearity_stats.json")


async def probe_stakes(client, symbol, contract_type, round_num):
    results = []
    for stake in STAKES:
        try:
            resp = await client.send_request({
                "proposal": 1,
                "amount": stake,
                "basis": "stake",
                "contract_type": contract_type,
                "currency": "USD",
                "underlying_symbol": symbol,
                "duration": DURATION,
                "duration_unit": DURATION_UNIT,
            })
            if "error" in resp:
                results.append({
                    "round": round_num, "symbol": symbol, "contract_type": contract_type,
                    "stake": stake, "error": resp["error"].get("message", "unknown"),
                })
                print(f"  [{symbol}/{contract_type}] stake=${stake:.2f} -> ERRO: {resp['error'].get('message', '?')}")
                continue

            p = resp["proposal"]
            ask_price = float(p.get("ask_price", 0))
            payout = float(p.get("payout", 0))
            spot = float(p.get("spot", 0))
            payout_ratio = payout / stake if stake > 0 else 0
            effective_payout_ratio = payout / ask_price if ask_price > 0 else 0

            rec = {
                "round": round_num,
                "symbol": symbol,
                "contract_type": contract_type,
                "stake": stake,
                "ask_price": ask_price,
                "payout": payout,
                "payout_ratio": payout_ratio,
                "effective_payout_ratio": effective_payout_ratio,
                "spot": spot,
                "ts": datetime.now(timezone.utc).isoformat(),
            }
            results.append(rec)
            with open(RESULTS_FILE, "a") as f:
                f.write(json.dumps(rec) + "\n")
            print(f"  [{symbol}/{contract_type}] stake=${stake:.2f} ask=${ask_price:.4f} "
                  f"payout=${payout:.4f} ratio={payout_ratio:.6f}")

            await asyncio.sleep(0.15)
        except Exception as e:
            print(f"  [{symbol}/{contract_type}] stake=${stake:.2f} -> EXC: {e}")
            results.append({
                "round": round_num, "symbol": symbol, "contract_type": contract_type,
                "stake": stake, "error": str(e),
            })
            await asyncio.sleep(1)

    return results


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--rounds", type=int, default=20)
    parser.add_argument("--live", action="store_true")
    args = parser.parse_args()

    if not APP_ID:
        print("ERRO: DERIV_APP_ID nao encontrado.")
        return

    print("=" * 90)
    print(f"D57 — Stake Size Non-Linearity Probe")
    print(f"  Symbols: {SYMBOLS}")
    print(f"  Contract types: {CONTRACT_TYPES}")
    print(f"  Stakes: {STAKES}")
    print(f"  Rounds: {args.rounds}")
    print(f"  Duration: {DURATION} {DURATION_UNIT}")
    print("=" * 90)

    client = DerivClient(app_id=APP_ID, api_token=TOKEN, use_demo=True)
    await client.connect()
    print(f"  Conectado. Conta: {client.account_id}")

    all_results = []
    for r in range(args.rounds):
        print(f"\n{'='*80}")
        print(f"  ROUND {r+1}/{args.rounds}")
        print(f"{'='*80}")
        for symbol in SYMBOLS:
            for ct in CONTRACT_TYPES:
                print(f"\n  --- {symbol} / {ct} ---")
                results = await probe_stakes(client, symbol, ct, r)
                all_results.extend(results)
            await asyncio.sleep(0.5)
        await asyncio.sleep(2)

    print(f"\n{'='*80}")
    print(f"  ANALISE FINAL")
    print(f"{'='*80}")

    by_group = {}
    for rec in all_results:
        if "error" in rec:
            continue
        key = f"{rec['symbol']}_{rec['contract_type']}"
        by_group.setdefault(key, {}).setdefault(rec["stake"], []).append(rec["payout_ratio"])

    significant_deviations = []
    for group, stake_data in sorted(by_group.items()):
        print(f"\n  --- {group} ---")
        ratios_per_stake = {}
        for stake in sorted(stake_data.keys()):
            ratios = stake_data[stake]
            mean_r = statistics.mean(ratios)
            std_r = statistics.stdev(ratios) if len(ratios) > 1 else 0
            ratios_per_stake[stake] = {"mean": mean_r, "std": std_r, "n": len(ratios)}
            print(f"    stake=${stake:.2f}: payout_ratio={mean_r:.6f} +/- {std_r:.6f} (N={len(ratios)})")

        all_means = [v["mean"] for v in ratios_per_stake.values()]
        if len(all_means) >= 2:
            grand_mean = statistics.mean(all_means)
            grand_std = statistics.stdev(all_means) if len(all_means) > 1 else 0
            max_dev = max(abs(m - grand_mean) for m in all_means)
            max_stake = sorted(ratios_per_stake.keys(), key=lambda s: abs(ratios_per_stake[s]["mean"] - grand_mean), reverse=True)[0]
            print(f"    Grand mean: {grand_mean:.6f} | Max deviation: {max_dev:.6f} at stake=${max_stake:.2f}")
            if max_dev > 0.001:
                significant_deviations.append({
                    "group": group,
                    "grand_mean": grand_mean,
                    "max_deviation": max_dev,
                    "best_stake": max_stake,
                    "best_ratio": ratios_per_stake[max_stake]["mean"],
                })

    if significant_deviations:
        print(f"\n  *** {len(significant_deviations)} grupos com desvios > 0.001:")
        for d in significant_deviations:
            print(f"    {d['group']}: best_stake=${d['best_stake']:.2f} ratio={d['best_ratio']:.6f} "
                  f"(dev={d['max_deviation']:.6f})")
    else:
        print(f"\n  Nenhuma desvio > 0.001 encontrado. Payout ratio e linear com stake.")

    stats = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "total_proposals": len(all_results),
        "errors": sum(1 for r in all_results if "error" in r),
        "groups": len(by_group),
        "significant_deviations": significant_deviations,
        "summary": {g: {str(s): v for s, v in sd.items()} for g, sd in by_group.items()},
    }
    with open(STATS_FILE, "w") as f:
        json.dump(stats, f, indent=2)
    print(f"\n  Stats salvas em {STATS_FILE}")

    await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
