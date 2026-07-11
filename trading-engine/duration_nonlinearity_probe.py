"""
D63 — Duration Non-Linearity Probe
===================================
Hipotese: O payout ratio varia com a duracao do contrato de forma nao-linear?
D57 achou que payout varia com stake (arredondamento de cents). Analogamente,
pode haver arredondamento ou descontinuidade em duracoes especificas.

Se contratos de 1 tick tem payout ratio diferente de 5 ticks ou 10 ticks,
pode haver duracao otima onde o payout efetivo e maior.

Metodo:
  1. Para cada simbolo (1HZ10V, 1HZ50V, R_10, R_50, R_100):
     a. Solicitar proposals CALL/PUT em multiplas duracoes (1, 2, 3, 5, 10, 15, 30, 60 ticks)
     b. Registrar: ask_price, payout, payout_ratio
     c. Comparar ratios entre duracoes
  2. Repetir N rounds para capturar variacao
  3. Identificar se ha duracao com ratio sistematicamente melhor

Uso: python3 duration_nonlinearity_probe.py [--rounds=20]
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

SYMBOLS = ["1HZ10V", "1HZ50V", "R_10", "R_50", "R_100"]
CONTRACT_TYPES = ["CALL", "PUT"]
STAKE = 1.00
DURATIONS_TICKS = [1, 2, 3, 5, 10, 15, 30, 60]
DURATION_UNIT = "t"

RESULTS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "duration_nonlinearity_results.jsonl")
STATS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "duration_nonlinearity_stats.json")


async def probe_duration(client, symbol, contract_type, duration, round_num):
    try:
        resp = await client.send_request({
            "proposal": 1,
            "amount": STAKE,
            "basis": "stake",
            "contract_type": contract_type,
            "currency": "USD",
            "underlying_symbol": symbol,
            "duration": duration,
            "duration_unit": DURATION_UNIT,
        })
        if "error" in resp:
            return {"symbol": symbol, "ct": contract_type, "duration": duration,
                    "round": round_num, "error": resp["error"].get("message")}

        p = resp["proposal"]
        ask_price = float(p.get("ask_price", 0))
        payout = float(p.get("payout", 0))
        spot = float(p.get("spot", 0))
        payout_ratio = payout / STAKE

        rec = {
            "round": round_num,
            "symbol": symbol,
            "contract_type": contract_type,
            "duration": duration,
            "ask_price": ask_price,
            "payout": payout,
            "payout_ratio": payout_ratio,
            "spot": spot,
            "ts": datetime.now(timezone.utc).isoformat(),
        }
        with open(RESULTS_FILE, "a") as f:
            f.write(json.dumps(rec) + "\n")
        return rec
    except Exception as e:
        return {"symbol": symbol, "ct": contract_type, "duration": duration,
                "round": round_num, "error": str(e)}


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--rounds", type=int, default=20)
    args = parser.parse_args()

    if not APP_ID:
        print("ERRO: DERIV_APP_ID nao encontrado.")
        return

    print("=" * 90)
    print(f"D63 — Duration Non-Linearity Probe")
    print(f"  Symbols: {SYMBOLS}")
    print(f"  Contract types: {CONTRACT_TYPES}")
    print(f"  Durations (ticks): {DURATIONS_TICKS}")
    print(f"  Stake: ${STAKE} | Rounds: {args.rounds}")
    print("=" * 90)

    client = DerivClient(app_id=APP_ID, api_token=TOKEN, use_demo=True)
    await client.connect()
    print(f"  Conectado. Conta: {client.account_id}")

    all_results = []
    for r in range(args.rounds):
        if r % 5 == 0:
            print(f"\n  --- Round {r+1}/{args.rounds} ---")
        for sym in SYMBOLS:
            for ct in CONTRACT_TYPES:
                for dur in DURATIONS_TICKS:
                    rec = await probe_duration(client, sym, ct, dur, r)
                    if "error" not in rec:
                        all_results.append(rec)
                        if r == 0:
                            print(f"    [{sym}/{ct}] dur={dur:3d}t ask=${rec['ask_price']:.4f} "
                                  f"payout=${rec['payout']:.4f} ratio={rec['payout_ratio']:.6f}")
                    await asyncio.sleep(0.1)
            await asyncio.sleep(0.3)
        await asyncio.sleep(0.5)

    print(f"\n{'='*80}")
    print(f"  ANALISE FINAL")
    print(f"{'='*80}")

    valid = [r for r in all_results if "error" not in r]
    print(f"  Proposals validas: {len(valid)}/{len(all_results)}")

    by_combo = defaultdict(list)
    for rec in valid:
        key = f"{rec['symbol']}/{rec['contract_type']}/dur={rec['duration']}"
        by_combo[key].append(rec["payout_ratio"])

    by_duration = defaultdict(list)
    for rec in valid:
        by_duration[rec["duration"]].append(rec["payout_ratio"])

    print(f"\n  Payout ratio por duracao (agregado, todos simbolos/contract types):")
    import statistics
    for dur in sorted(by_duration.keys()):
        ratios = by_duration[dur]
        mean_r = statistics.mean(ratios)
        std_r = statistics.stdev(ratios) if len(ratios) > 1 else 0
        print(f"    dur={dur:3d}t: mean={mean_r:.6f} std={std_r:.6f} N={len(ratios)}")

    print(f"\n  Por simbolo/contract type:")
    for sym in SYMBOLS:
        for ct in CONTRACT_TYPES:
            print(f"\n    --- {sym}/{ct} ---")
            for dur in DURATIONS_TICKS:
                key = f"{sym}/{ct}/dur={dur}"
                if key in by_combo:
                    ratios = by_combo[key]
                    mean_r = statistics.mean(ratios)
                    std_r = statistics.stdev(ratios) if len(ratios) > 1 else 0
                    print(f"      dur={dur:3d}t: ratio={mean_r:.6f} ±{std_r:.6f} N={len(ratios)}")

    all_ratios = [r["payout_ratio"] for r in valid]
    if all_ratios:
        min_r = min(all_ratios)
        max_r = max(all_ratios)
        print(f"\n  Range global: {min_r:.6f} a {max_r:.6f} (spread={max_r-min_r:.6f})")

        if max_r - min_r > 0.01:
            best_key = max(by_combo, key=lambda k: statistics.mean(by_combo[k]))
            worst_key = min(by_combo, key=lambda k: statistics.mean(by_combo[k]))
            print(f"  *** VARIACAO SIGNIFICATIVA: melhor={best_key} ({statistics.mean(by_combo[best_key]):.6f})")
            print(f"      pior={worst_key} ({statistics.mean(by_combo[worst_key]):.6f})")
            print(f"      Diff: {statistics.mean(by_combo[best_key]) - statistics.mean(by_combo[worst_key]):.6f}")
        else:
            print(f"\n  Payout ratio e ESTAVEL entre duracoes (spread < 0.01).")
            print(f"  Nao ha nao-linearidade de duracao exploravel.")

    stats = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "total_proposals": len(all_results),
        "valid": len(valid),
        "rounds": args.rounds,
        "by_duration": {str(d): {"mean": statistics.mean(by_duration[d]), "std": statistics.stdev(by_duration[d]) if len(by_duration[d]) > 1 else 0, "n": len(by_duration[d])} for d in by_duration},
        "by_combo": {k: {"mean": statistics.mean(v), "std": statistics.stdev(v) if len(v) > 1 else 0, "n": len(v)} for k, v in by_combo.items()},
    }
    with open(STATS_FILE, "w") as f:
        json.dump(stats, f, indent=2, default=str)
    print(f"\n  Stats salvas em {STATS_FILE}")

    await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
