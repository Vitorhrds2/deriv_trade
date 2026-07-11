"""
D65 — Touch/No-Touch Barrier Precision Probe
=============================================
Hipotese: D62 so testou CALL/PUT (barrier=None — implicita). Touch/No-Touch
contratos TEM barrier explicita. Se a barrier tem menos precisao que o tick,
contratos na borda podem ter probabilidade real diferente da precificada.

Metodo:
  1. Para cada simbolo (1HZ10V, 1HZ50V, R_10, R_50, R_100):
     a. Subscrever ticks e registrar precisao (casas decimais)
     b. Solicitar proposals ONTOUCH/NOTOUCH com diferentes barriers
     c. Registrar: spot, barrier, ask_price, payout, payout_ratio
     d. Comparar precisao do tick vs precisao da barrier
  2. Se barrier tem menos precisao, contar quantos ticks caem exatamente na barrier
  3. Repetir N rounds

Uso: python3 touch_notouch_barrier_probe.py [--rounds=20]
"""
import argparse
import asyncio
import json
import os
import sys
import time
from collections import Counter, defaultdict
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
CONTRACT_TYPES = ["ONETOUCH", "NOTOUCH"]
STAKE = 1.00
DURATION = 5
DURATION_UNIT = "t"
BARRIER_OFFSETS_PCT = [0.01, 0.05, 0.10, 0.50, 1.00]

RESULTS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "touch_barrier_results.jsonl")
STATS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "touch_barrier_stats.json")

tick_values = {sym: [] for sym in SYMBOLS}


def count_decimals(value):
    s = f"{value:.15f}".rstrip("0")
    if "." not in s:
        return 0
    return len(s.split(".")[1])


async def collect_ticks(client, symbol, duration_s=8):
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


async def probe_barrier(client, symbol, contract_type, barrier_pct, round_num, current_spot):
    barriers_to_try = []
    for offset in [barrier_pct, -barrier_pct]:
        b = current_spot * (1 + offset)
        barriers_to_try.append(b)

    results = []
    for barrier in barriers_to_try:
        try:
            resp = await client.send_request({
                "proposal": 1,
                "amount": STAKE,
                "basis": "stake",
                "contract_type": contract_type,
                "currency": "USD",
                "underlying_symbol": symbol,
                "duration": DURATION,
                "duration_unit": DURATION_UNIT,
                "barrier": str(round(barrier, 4)),
            })
            if "error" in resp:
                results.append({"symbol": symbol, "ct": contract_type, "barrier_pct": barrier_pct,
                                "barrier": barrier, "round": round_num,
                                "error": resp["error"].get("message")})
                continue

            p = resp["proposal"]
            spot = float(p.get("spot", 0))
            ask_price = float(p.get("ask_price", 0))
            payout = float(p.get("payout", 0))
            actual_barrier = p.get("barrier")
            payout_ratio = payout / STAKE

            spot_decimals = count_decimals(spot)
            barrier_decimals = count_decimals(float(actual_barrier)) if actual_barrier else None

            rec = {
                "round": round_num,
                "symbol": symbol,
                "contract_type": contract_type,
                "barrier_requested": barrier,
                "barrier_actual": actual_barrier,
                "barrier_pct": barrier_pct,
                "spot": spot,
                "spot_decimals": spot_decimals,
                "barrier_decimals": barrier_decimals,
                "ask_price": ask_price,
                "payout": payout,
                "payout_ratio": payout_ratio,
                "ts": datetime.now(timezone.utc).isoformat(),
            }
            results.append(rec)
            with open(RESULTS_FILE, "a") as f:
                f.write(json.dumps(rec) + "\n")

        except Exception as e:
            results.append({"symbol": symbol, "ct": contract_type, "barrier_pct": barrier_pct,
                            "round": round_num, "error": str(e)})
        await asyncio.sleep(0.15)
    return results


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--rounds", type=int, default=20)
    args = parser.parse_args()

    if not APP_ID:
        print("ERRO: DERIV_APP_ID nao encontrado.")
        return

    print("=" * 90)
    print(f"D65 — Touch/No-Touch Barrier Precision Probe")
    print(f"  Symbols: {SYMBOLS}")
    print(f"  Contract types: {CONTRACT_TYPES} (ONTOUCH=Touch, NOTOUCH=No-Touch)")
    print(f"  Duration: {DURATION} {DURATION_UNIT} | Barrier offsets: {BARRIER_OFFSETS_PCT}")
    print(f"  Stake: ${STAKE} | Rounds: {args.rounds}")
    print("=" * 90)

    client = DerivClient(app_id=APP_ID, api_token=TOKEN, use_demo=True)
    await client.connect()
    print(f"  Conectado. Conta: {client.account_id}")

    print(f"\n  Fase 1: Coletar ticks para analisar precisao...")
    for sym in SYMBOLS:
        ticks = await collect_ticks(client, sym, duration_s=8)
        if ticks:
            tick_values[sym] = ticks
            dec_counter = Counter(count_decimals(t) for t in ticks)
            print(f"    {sym}: {len(ticks)} ticks, precisao: {dict(dec_counter)}")
        await asyncio.sleep(0.5)

    print(f"\n  Fase 2: Probe barriers em {args.rounds} rounds...")
    all_results = []
    for r in range(args.rounds):
        if r % 5 == 0:
            print(f"\n  --- Round {r+1}/{args.rounds} ---")
        for sym in SYMBOLS:
            spot_resp = await client.send_request({"ticks_history": sym, "count": 1, "end": "latest", "style": "ticks"})
            hist = spot_resp.get("history", {})
            prices = hist.get("prices", [])
            current_spot = float(prices[0]) if prices else 0
            if current_spot == 0:
                prop_resp = await client.send_request({
                    "proposal": 1, "amount": STAKE, "basis": "stake",
                    "contract_type": "CALL", "currency": "USD",
                    "underlying_symbol": sym, "duration": DURATION, "duration_unit": DURATION_UNIT,
                })
                if "proposal" in prop_resp:
                    current_spot = float(prop_resp["proposal"].get("spot", 0))
            if current_spot == 0:
                continue

            for ct in CONTRACT_TYPES:
                for bpct in BARRIER_OFFSETS_PCT:
                    results = await probe_barrier(client, sym, ct, bpct, r, current_spot)
                    for rec in results:
                        if "error" not in rec:
                            all_results.append(rec)
                            if r == 0:
                                ba = rec.get("barrier_actual", "N/A")
                                bd = rec.get("barrier_decimals", 0)
                                sd = rec.get("spot_decimals", 0)
                                match = "MATCH" if sd == bd else f"MISMATCH (spot={sd} barrier={bd})"
                                print(f"    [{sym}/{ct}] barrier_req={rec['barrier_requested']:.2f} "
                                      f"barrier_actual={ba} ({bd}d) spot={rec['spot']:.2f} ({sd}d) {match} "
                                      f"ratio={rec['payout_ratio']:.4f}")
                await asyncio.sleep(0.3)
        await asyncio.sleep(0.5)

    print(f"\n{'='*80}")
    print(f"  ANALISE FINAL")
    print(f"{'='*80}")

    valid = [r for r in all_results if "error" not in r]
    errors = [r for r in all_results if "error" in r]
    print(f"  Proposals: {len(all_results)} | Validas: {len(valid)} | Erros: {len(errors)}")

    if errors:
        error_msgs = Counter(r["error"] for r in errors)
        print(f"  Erros comuns: {dict(error_msgs.most_common(5))}")

    by_symbol = defaultdict(list)
    for rec in valid:
        by_symbol[rec["symbol"]].append(rec)

    precision_mismatches = 0
    total_compared = 0

    for sym, records in sorted(by_symbol.items()):
        print(f"\n  --- {sym} ---")
        tick_decs = Counter(count_decimals(t) for t in tick_values.get(sym, []))
        tick_mode = tick_decs.most_common(1)[0][0] if tick_decs else 0

        barrier_decs = [r["barrier_decimals"] for r in records if r.get("barrier_decimals") is not None]
        spot_decs = [r["spot_decimals"] for r in records]

        barrier_dec_counter = Counter(barrier_decs)
        spot_dec_counter = Counter(spot_decs)

        print(f"    Tick precision: {dict(tick_decs)} (mode={tick_mode}d)")
        print(f"    Spot precision: {dict(spot_dec_counter)}")
        print(f"    Barrier precision: {dict(barrier_dec_counter)}")

        barrier_mode = barrier_dec_counter.most_common(1)[0][0] if barrier_decs else 0
        spot_mode = spot_dec_counter.most_common(1)[0][0] if spot_decs else 0

        print(f"    Mode: tick={tick_mode}d spot={spot_mode}d barrier={barrier_mode}d")

        if barrier_mode < tick_mode:
            total_compared += 1
            precision_mismatches += 1
            print(f"    *** MISMATCH: barrier tem MENOS precisao que tick!")
            tick_at_barrier = 0
            for t in tick_values.get(sym, []):
                for r in records:
                    if r.get("barrier_actual"):
                        bv = float(r["barrier_actual"])
                        if abs(t - bv) < 10**(-tick_mode):
                            tick_at_barrier += 1
            if tick_values.get(sym):
                pct_at = (tick_at_barrier / len(tick_values[sym])) * 100
                print(f"    Ticks exatamente na barrier: {tick_at_barrier}/{len(tick_values[sym])} ({pct_at:.1f}%)")
        elif barrier_mode == tick_mode:
            total_compared += 1
            print(f"    OK: barrier e tick tem mesma precisao ({tick_mode}d)")
        else:
            total_compared += 1
            print(f"    Barrier tem MAIS precisao que tick? Inesperado.")

        barrier_requested = [r["barrier_requested"] for r in records]
        barrier_actual = [float(r["barrier_actual"]) for r in records if r.get("barrier_actual")]
        if barrier_requested and barrier_actual:
            diffs = [abs(r - a) for r, a in zip(barrier_requested, barrier_actual)]
            if diffs:
                import statistics
                print(f"    Barrier requested vs actual: mean_diff={statistics.mean(diffs):.6f}")

        payout_ratios = [r["payout_ratio"] for r in records]
        if payout_ratios:
            print(f"    Payout ratio: mean={statistics.mean(payout_ratios):.4f} "
                  f"std={statistics.stdev(payout_ratios) if len(payout_ratios) > 1 else 0:.4f}")

    print(f"\n  Resumo:")
    print(f"    Symbols comparados: {total_compared}")
    print(f"    Precision mismatches: {precision_mismatches}")

    if precision_mismatches > 0:
        print(f"\n  *** {precision_mismatches} simbolos com barrier menos precisa que tick!")
    else:
        print(f"\n  Barrier e tick tem a mesma precisao em todos os simbolos.")
        print(f"  Nao ha arredondamento de barrier exploravel em Touch/No-Touch.")

    stats = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "total_proposals": len(all_results),
        "valid": len(valid),
        "errors": len(errors),
        "precision_mismatches": precision_mismatches,
        "tick_precisions": {sym: dict(Counter(count_decimals(t) for t in tick_values[sym])) for sym in SYMBOLS},
    }
    with open(STATS_FILE, "w") as f:
        json.dump(stats, f, indent=2, default=str)
    print(f"\n  Stats salvas em {STATS_FILE}")

    await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
