"""
D62 — Barrier Rounding Precision Probe
=======================================
Hipotese: Barriers de HIGHER/LOWER sao calculadas com quantas casas decimais?
O tick e quoted com mais precisao que a barrier? Se a barrier arredonda para
baixo, contratos "na borda" podem ter probabilidade real diferente da
precificada.

Se a barrier tem menos precisao que o tick, contratos proximos da barrier
podem ter edge: a probabilidade real de win pode ser diferente da precificada
porque a barrier efetiva esta arredondada.

Metodo:
  1. Para cada simbolo (1HZ10V, 1HZ50V, R_10, R_50, R_100):
     a. Solicitar proposals HIGHER/LOWER com barrier=spot (at-the-money)
     b. Registrar: spot, barrier, ask_price, payout
     c. Subscrever ticks e registrar precisao do tick (casas decimais)
     d. Comparar precisao do tick vs precisao da barrier
  2. Se barrier tem menos precisao, calcular:
     - Quantos ticks caem exatamente na barrier?
     - Qual a probabilidade real vs precificada?
  3. Repetir N rounds para capturar variacao

Uso: python3 barrier_rounding_probe.py [--rounds=30]
"""
import argparse
import asyncio
import json
import os
import sys
import time
from collections import Counter
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
DURATION = 5
DURATION_UNIT = "t"

RESULTS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "barrier_rounding_results.jsonl")
STATS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "barrier_rounding_stats.json")

tick_precisions = {sym: [] for sym in SYMBOLS}
tick_values = {sym: [] for sym in SYMBOLS}


def count_decimals(value):
    s = f"{value:.15f}".rstrip("0")
    if "." not in s:
        return 0
    return len(s.split(".")[1])


async def collect_ticks(client, symbol, duration_s=10):
    ticks_received = []

    def on_tick(data):
        t = data.get("tick")
        if not t or "quote" not in t:
            return
        q = float(t["quote"])
        ticks_received.append(q)

    client.callbacks["tick"] = on_tick
    client._tick_callback = on_tick
    if symbol not in client._tick_symbols:
        client._tick_symbols.append(symbol)
    await client.send_request({"ticks": symbol, "subscribe": 1})
    await asyncio.sleep(duration_s)
    await client.send_request({"ticks": symbol, "subscribe": 0})
    if "tick" in client.callbacks:
        del client.callbacks["tick"]

    return ticks_received


async def probe_symbol(client, symbol, round_num):
    results = []
    for ct in CONTRACT_TYPES:
        try:
            resp = await client.send_request({
                "proposal": 1,
                "amount": 1.00,
                "basis": "stake",
                "contract_type": ct,
                "currency": "USD",
                "underlying_symbol": symbol,
                "duration": DURATION,
                "duration_unit": DURATION_UNIT,
            })
            if "error" in resp:
                print(f"  [{symbol}/{ct}] erro: {resp['error'].get('message')}")
                results.append({"symbol": symbol, "ct": ct, "round": round_num,
                                "error": resp["error"].get("message")})
                continue

            p = resp["proposal"]
            spot = float(p.get("spot", 0))
            ask_price = float(p.get("ask_price", 0))
            payout = float(p.get("payout", 0))
            barrier = p.get("barrier")
            payout_ratio = payout / 1.00

            spot_decimals = count_decimals(spot)
            barrier_decimals = count_decimals(float(barrier)) if barrier else None

            rec = {
                "round": round_num,
                "symbol": symbol,
                "contract_type": ct,
                "spot": spot,
                "spot_decimals": spot_decimals,
                "barrier": barrier,
                "barrier_decimals": barrier_decimals,
                "ask_price": ask_price,
                "payout": payout,
                "payout_ratio": payout_ratio,
                "ts": datetime.now(timezone.utc).isoformat(),
            }
            results.append(rec)
            with open(RESULTS_FILE, "a") as f:
                f.write(json.dumps(rec) + "\n")

            precision_match = "MATCH" if spot_decimals == barrier_decimals else f"MISMATCH (spot={spot_decimals} barrier={barrier_decimals})"
            print(f"  [{symbol}/{ct}] spot={spot:.{spot_decimals}f} ({spot_decimals}d) "
                  f"barrier={barrier} ({barrier_decimals}d) {precision_match} "
                  f"ratio={payout_ratio:.4f}")

            await asyncio.sleep(0.2)
        except Exception as e:
            print(f"  [{symbol}/{ct}] EXC: {e}")
            results.append({"symbol": symbol, "ct": ct, "round": round_num, "error": str(e)})

    return results


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--rounds", type=int, default=30)
    args = parser.parse_args()

    if not APP_ID:
        print("ERRO: DERIV_APP_ID nao encontrado.")
        return

    print("=" * 90)
    print(f"D62 — Barrier Rounding Precision Probe")
    print(f"  Symbols: {SYMBOLS}")
    print(f"  Contract types: {CONTRACT_TYPES} (HIGHER/LOWER equivalent)")
    print(f"  Duration: {DURATION} {DURATION_UNIT} | Rounds: {args.rounds}")
    print("=" * 90)

    client = DerivClient(app_id=APP_ID, api_token=TOKEN, use_demo=True)
    await client.connect()
    print(f"  Conectado. Conta: {client.account_id}")

    print(f"\n  Fase 1: Coletar ticks para analisar precisao...")
    for sym in SYMBOLS:
        ticks = await collect_ticks(client, sym, duration_s=8)
        if ticks:
            tick_precisions[sym] = [count_decimals(t) for t in ticks]
            tick_values[sym] = ticks
            dec_counter = Counter(tick_precisions[sym])
            print(f"    {sym}: {len(ticks)} ticks, precisao: {dict(dec_counter)}")
            if ticks:
                print(f"      Ex: {ticks[:5]}")
        await asyncio.sleep(0.5)

    print(f"\n  Fase 2: Probe barriers em {args.rounds} rounds...")
    all_results = []
    for r in range(args.rounds):
        if r % 5 == 0:
            print(f"\n  --- Round {r+1}/{args.rounds} ---")
        for sym in SYMBOLS:
            results = await probe_symbol(client, sym, r)
            all_results.extend(results)
        await asyncio.sleep(1)

    print(f"\n{'='*80}")
    print(f"  ANALISE FINAL")
    print(f"{'='*80}")

    valid = [r for r in all_results if "error" not in r]

    by_symbol = {}
    for rec in valid:
        sym = rec["symbol"]
        by_symbol.setdefault(sym, []).append(rec)

    precision_mismatches = 0
    total_compared = 0

    for sym, records in sorted(by_symbol.items()):
        print(f"\n  --- {sym} ---")

        spot_decs = [r["spot_decimals"] for r in records]
        barrier_decs = [r.get("barrier_decimals", 0) for r in records if r.get("barrier_decimals") is not None]

        tick_decs = tick_precisions.get(sym, [])
        tick_dec_counter = Counter(tick_decs)
        spot_dec_counter = Counter(spot_decs)
        barrier_dec_counter = Counter(barrier_decs)

        print(f"    Tick precision: {dict(tick_dec_counter)}")
        print(f"    Spot precision: {dict(spot_dec_counter)}")
        print(f"    Barrier precision: {dict(barrier_dec_counter)}")

        tick_mode = tick_dec_counter.most_common(1)[0][0] if tick_decs else 0
        spot_mode = spot_dec_counter.most_common(1)[0][0] if spot_decs else 0
        barrier_mode = barrier_dec_counter.most_common(1)[0][0] if barrier_decs else 0

        print(f"    Mode: tick={tick_mode}d spot={spot_mode}d barrier={barrier_mode}d")

        if barrier_mode < tick_mode:
            total_compared += 1
            precision_mismatches += 1
            print(f"    *** MISMATCH: barrier tem MENOS precisao que tick!")
            print(f"        Barrier arredonda para {barrier_mode}d mas tick tem {tick_mode}d")
            print(f"        Contratos na borda podem ter probabilidade diferente da precificada.")

            tick_at_barrier = 0
            for t in tick_values.get(sym, []):
                barrier_val = records[0].get("barrier")
                if barrier_val:
                    bv = float(barrier_val)
                    if abs(t - bv) < 10**(-tick_mode):
                        tick_at_barrier += 1
            if tick_values.get(sym):
                pct_at_barrier = (tick_at_barrier / len(tick_values[sym])) * 100
                print(f"        Ticks exatamente na barrier: {tick_at_barrier}/{len(tick_values[sym])} ({pct_at_barrier:.1f}%)")
        elif barrier_mode == tick_mode:
            total_compared += 1
            print(f"    OK: barrier e tick tem mesma precisao ({tick_mode}d)")

        payout_ratios = [r["payout_ratio"] for r in records]
        if payout_ratios:
            import statistics
            print(f"    Payout ratio: mean={statistics.mean(payout_ratios):.6f} "
                  f"std={statistics.stdev(payout_ratios) if len(payout_ratios) > 1 else 0:.6f}")

    print(f"\n  Resumo:")
    print(f"    Symbols comparados: {total_compared}")
    print(f"    Precision mismatches: {precision_mismatches}")

    if precision_mismatches > 0:
        print(f"\n  *** {precision_mismatches} simbolos com barrier menos precisa que tick!")
        print(f"      Potencial edge: contratos na borda da barrier podem ter")
        print(f"      probabilidade real diferente da precificada.")
    else:
        print(f"\n  Barrier e tick tem a mesma precisao em todos os simbolos.")
        print(f"  Nao ha arredondamento de barrier exploravel.")

    stats = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "total_proposals": len(all_results),
        "valid": len(valid),
        "symbols": len(by_symbol),
        "precision_mismatches": precision_mismatches,
        "tick_precisions": {sym: dict(Counter(tick_precisions[sym])) for sym in SYMBOLS},
        "barrier_precisions": {sym: dict(Counter([r.get("barrier_decimals", 0) for r in records if r.get("barrier_decimals") is not None])) for sym, records in by_symbol.items()},
    }
    with open(STATS_FILE, "w") as f:
        json.dump(stats, f, indent=2, default=str)
    print(f"\n  Stats salvas em {STATS_FILE}")

    await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
