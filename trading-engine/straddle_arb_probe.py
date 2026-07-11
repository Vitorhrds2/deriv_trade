"""
D86 — CALL+PUT Simultaneous Arbitrage (Straddle)
==================================================
Se ask_CALL + ask_PUT < payout, comprar ambos garante lucro independente
da direcao. Classico arbitrage de straddle.

Metodologia:
  1. Solicitar proposals CALL e PUT simultaneamente
  2. Verificar se ask_CALL + ask_PUT < payout
  3. Se sim, comprar ambos = profit garantido
  4. Repetir N vezes para ver se a condicao persiste

Tambem testa:
  - CALLE + PUTE (European style)
  - Diferentes durations (5t, 10t, 15t, 1m, 5m)
  - Diferentes simbolos (1HZ10V, 1HZ50V, 1HZ100V, R_100)

Se ask_CALL + ask_PUT sempre = payout (ou > payout), nao ha arbitrage.
Se < payout em qualquer caso, ha edge.
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

STAKE = 1.00
SYMBOLS = ["1HZ10V", "1HZ50V", "1HZ100V", "R_10", "R_25", "R_50", "R_75", "R_100"]
DURATIONS = [(5, "t"), (10, "t"), (15, "t"), (1, "m"), (5, "m")]
PAIRS = [("CALL", "PUT"), ("CALLE", "PUTE")]
N_SAMPLES = 10  # samples per config

RESULTS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            "straddle_arb_results.json")


async def get_proposal(client, contract_type, symbol, duration, duration_unit):
    res = await client.send_request({
        "proposal": 1,
        "amount": STAKE,
        "basis": "stake",
        "contract_type": contract_type,
        "currency": "USD",
        "underlying_symbol": symbol,
        "duration": duration,
        "duration_unit": duration_unit,
    })
    if "error" in res:
        return None
    return res["proposal"]


async def main():
    print("=" * 90)
    print("D86 — CALL+PUT Simultaneous Arbitrage (Straddle)")
    print(f"  Symbols: {', '.join(SYMBOLS)}")
    print(f"  Pairs: {PAIRS}")
    print(f"  Durations: {DURATIONS}")
    print(f"  Samples per config: {N_SAMPLES}")
    print("=" * 90)

    client = DerivClient(app_id=APP_ID, api_token=TOKEN, use_demo=True)
    await client.connect()
    print(f"  Conectado. Conta: {client.account_id}")

    all_results = []
    arb_candidates = []

    for sym in SYMBOLS:
        print(f"\n{'='*60}")
        print(f"  {sym}")
        print(f"{'='*60}")

        for call_type, put_type in PAIRS:
            for dur, unit in DURATIONS:
                for sample in range(N_SAMPLES):
                    # Get both proposals as close together as possible
                    call_prop, put_prop = await asyncio.gather(
                        get_proposal(client, call_type, sym, dur, unit),
                        get_proposal(client, put_type, sym, dur, unit),
                    )

                    if not call_prop or not put_prop:
                        continue

                    call_ask = float(call_prop["ask_price"])
                    put_ask = float(put_prop["ask_price"])
                    call_payout = float(call_prop.get("payout", 0))
                    put_payout = float(put_prop.get("payout", 0))

                    total_ask = call_ask + put_ask
                    total_payout = call_payout + put_payout  # one wins, one loses
                    # Actually: one wins payout, one loses stake
                    # Profit = payout - total_ask (winner pays out, loser loses)
                    # If CALL wins: +call_payout - call_ask - put_ask
                    # If PUT wins: +put_payout - call_ask - put_ask
                    # For guaranteed profit: min(call_payout, put_payout) > total_ask

                    min_payout = min(call_payout, put_payout)
                    spread = min_payout - total_ask
                    is_arb = spread > 0

                    rec = {
                        "symbol": sym,
                        "call_type": call_type,
                        "put_type": put_type,
                        "duration": dur,
                        "duration_unit": unit,
                        "sample": sample,
                        "call_ask": call_ask,
                        "put_ask": put_ask,
                        "total_ask": total_ask,
                        "call_payout": call_payout,
                        "put_payout": put_payout,
                        "min_payout": min_payout,
                        "spread": spread,
                        "is_arb": is_arb,
                    }
                    all_results.append(rec)

                    if is_arb:
                        arb_candidates.append(rec)
                        print(f"  *** ARB! {call_type}+{put_type} {dur}{unit}: "
                              f"total_ask=${total_ask:.4f} min_payout=${min_payout:.4f} "
                              f"spread=${spread:+.4f}")

                    await asyncio.sleep(0.2)

                # Print summary for this config
                config_results = [r for r in all_results
                                  if r["symbol"] == sym and r["call_type"] == call_type
                                  and r["duration"] == dur and r["duration_unit"] == unit]
                if config_results:
                    avg_spread = sum(r["spread"] for r in config_results) / len(config_results)
                    min_spread = min(r["spread"] for r in config_results)
                    max_spread = max(r["spread"] for r in config_results)
                    n_arb = sum(1 for r in config_results if r["is_arb"])
                    print(f"  {call_type}+{put_type} {dur}{unit}: "
                          f"avg_spread=${avg_spread:+.4f} "
                          f"min=${min_spread:+.4f} max=${max_spread:+.4f} "
                          f"arb={n_arb}/{len(config_results)}")

    # Verdict
    print(f"\n{'='*90}")
    print("  VEREDITO FINAL — STRADDLE ARBITRAGE")
    print(f"{'='*90}")

    if arb_candidates:
        print(f"\n  *** {len(arb_candidates)} oportunidades de ARBITRAGE encontradas! ***")
        for r in arb_candidates[:10]:
            print(f"    {r['symbol']} {r['call_type']}+{r['put_type']} "
                  f"{r['duration']}{r['duration_unit']}: spread=${r['spread']:+.4f}")
    else:
        print(f"\n  0/{len(all_results)} oportunidades de arbitrage.")
        print(f"  ask_CALL + ask_PUT >= min(payout) em 100% das amostras.")
        print(f"  Deriv precifica corretamente o straddle — sem arbitrage.")

        # Show worst spread (closest to arb)
        worst = min(all_results, key=lambda r: r["spread"])
        print(f"\n  Menor spread (mais proximo de arb): "
              f"{worst['symbol']} {worst['call_type']}+{worst['put_type']} "
              f"{worst['duration']}{worst['duration_unit']}: ${worst['spread']:+.4f}")

    with open(RESULTS_FILE, "w") as f:
        json.dump(all_results, f, indent=2, default=str)
    print(f"\n  Resultados salvos em {RESULTS_FILE}")

    await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
