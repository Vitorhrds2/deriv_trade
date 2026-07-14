"""D105 — Multi-Leg Digit Combination Arbitrage.

Hipotese
--------
DIGITOVER(N) ganha se digito > N. DIGITUNDER(N+1) ganha se digito < N+1
(ou seja, digito <= N). Juntos cobrem TODOS os digitos 0-9: sempre ganhamos
exatamente um contrato. Se ask_OVER + ask_UNDER < payout de qualquer um,
e arbitragem garantida.

Matematicamente, isso deveria ser impossivel (house margin aplicada por perna).
MAS: se a Deriv tem um bug de pricing onde certas combinacoes de barreira
tem payout desalinhado, pode haver edge.

Testa:
  1. Para cada N de 0 a 8: pedir proposals para DIGITOVER(N) e DIGITUNDER(N+1)
  2. Calcular: combined_ask = ask_OVER + ask_UNDER
  3. Calcular: guaranteed_payout = min(payout_OVER, payout_UNDER)
  4. Se combined_ask < guaranteed_payout → ARBITRAGEM
  5. Tambem testa combinacoes de 3+ pernas (DIGITOVER + DIGITUNDER + DIGITMATCH)
  6. Testa com basis=payout para alinhar payouts

Adicionalmente testa:
  - DIGITOVER(N) + DIGITUNDER(N): cobre tudo exceto digito = N (gap)
  - DIGITOVER(N) + DIGITUNDER(N+2): cobre tudo exceto digito = N+1
  - DIGITEVEN + DIGITODD: cobre todos os digitos (par + impar)

Uso
---
    python d105_multi_leg_digit_arb.py
    python d105_multi_leg_digit_arb.py --symbols 1HZ10V,R_100 --stake 1.0
"""
import argparse
import asyncio
import json
import os
import sys
from datetime import datetime, timezone

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from deriv_client import DerivClient

APP_ID = os.getenv("DERIV_APP_ID", "1089")
TOKEN = os.getenv("DERIV_API_TOKEN", "")
DEFAULT_SYMBOLS = ["1HZ10V", "1HZ50V", "1HZ100V", "R_10", "R_25", "R_50", "R_100"]
DURATIONS = [1, 5, 10, 25, 50, 100]


async def get_proposal(client, symbol, contract_type, duration, barrier=None, basis="stake", amount=1.0):
    payload = {
        "proposal": 1,
        "amount": amount,
        "basis": basis,
        "contract_type": contract_type,
        "currency": "USD",
        "underlying_symbol": symbol,
        "duration": duration,
        "duration_unit": "t",
    }
    if barrier is not None:
        payload["barrier"] = str(barrier)
    try:
        response = await asyncio.wait_for(client.send_request(payload), timeout=30)
    except Exception as e:
        return None, str(e)
    if "error" in response:
        return None, response["error"].get("message", "unknown")
    proposal = response.get("proposal", {})
    ask = proposal.get("ask_price")
    payout = proposal.get("payout")
    if not ask or not payout:
        return None, "no ask/payout"
    return {
        "ask": float(ask),
        "payout": float(payout),
        "ratio": float(payout) / float(ask),
        "longcode": proposal.get("longcode", ""),
    }, None


async def main():
    parser = argparse.ArgumentParser(description="D105 Multi-Leg Digit Combination Arbitrage")
    parser.add_argument("--symbols", default=",".join(DEFAULT_SYMBOLS))
    parser.add_argument("--stake", type=float, default=1.0)
    parser.add_argument("--output", default="d105_multi_leg_digit_arb_results.json")
    parser.add_argument("--app-id", default=os.getenv("DERIV_APP_ID", "1089"))
    parser.add_argument("--api-token", default=os.getenv("DERIV_API_TOKEN", ""))
    args = parser.parse_args()

    if not args.api_token:
        print("ERROR: DERIV_API_TOKEN required", flush=True)
        return

    symbols = [s.strip() for s in args.symbols.split(",")]

    print(f"D105 — Multi-Leg Digit Combination Arbitrage", flush=True)
    print(f"Symbols: {symbols} | Stake: ${args.stake}", flush=True)

    client = DerivClient(app_id=args.app_id, api_token=args.api_token, use_demo=True)
    await client.connect()
    await asyncio.sleep(2)

    all_combos = []

    for sym in symbols:
        for dur in DURATIONS:
            print(f"\n  Scanning {sym} dur={dur}t...", flush=True)

            # Get all digit proposals
            proposals = {}
            for barrier in range(10):
                for ct in ["DIGITOVER", "DIGITUNDER"]:
                    key = f"{ct}_{barrier}"
                    prop, error = await get_proposal(client, sym, ct, dur, barrier=barrier, amount=args.stake)
                    if error:
                        proposals[key] = {"error": error}
                    else:
                        proposals[key] = prop
                    await asyncio.sleep(0.15)

                # Also get DIGITMATCH for each barrier
                prop, error = await get_proposal(client, sym, "DIGITMATCH", dur, barrier=str(barrier), amount=args.stake)
                if error:
                    proposals[f"DIGITMATCH_{barrier}"] = {"error": error}
                else:
                    proposals[f"DIGITMATCH_{barrier}"] = prop
                await asyncio.sleep(0.15)

            # Test 2-leg combinations: DIGITOVER(N) + DIGITUNDER(N+1) = covers all
            for n in range(9):
                over_key = f"DIGITOVER_{n}"
                under_key = f"DIGITUNDER_{n+1}"
                over = proposals.get(over_key, {})
                under = proposals.get(under_key, {})

                if "error" in over or "error" in under:
                    continue

                combined_ask = over["ask"] + under["ask"]
                # Always win exactly one
                guaranteed_payout = min(over["payout"], under["payout"])
                # Weighted payout (prob-weighted)
                p_over = (9 - n) / 10  # P(digit > n)
                p_under = (n + 1) / 10  # P(digit < n+1) = P(digit <= n)
                expected_payout = p_over * over["payout"] + p_under * under["payout"]
                arb = guaranteed_payout - combined_ask
                ev = expected_payout - combined_ask

                combo = {
                    "symbol": sym,
                    "duration": dur,
                    "type": "2-leg-full-cover",
                    "legs": [over_key, under_key],
                    "barrier_n": n,
                    "combined_ask": round(combined_ask, 4),
                    "guaranteed_payout": round(guaranteed_payout, 4),
                    "expected_payout": round(expected_payout, 4),
                    "arb_guaranteed": round(arb, 4),
                    "ev": round(ev, 4),
                    "leg_details": {
                        over_key: {"ask": over["ask"], "payout": over["payout"]},
                        under_key: {"ask": under["ask"], "payout": under["payout"]},
                    },
                }
                all_combos.append(combo)

                if arb > 0:
                    print(f"    *** ARB: OVER({n})+UNDER({n+1}) ask=${combined_ask:.2f} "
                          f"guaranteed=${guaranteed_payout:.2f} ARB=+${arb:.4f}", flush=True)
                elif ev > 0:
                    print(f"    ** POSITIVE EV: OVER({n})+UNDER({n+1}) EV=+${ev:.4f} "
                          f"(guaranteed arb=${arb:.4f})", flush=True)

            # Test DIGITEVEN + DIGITODD (covers all digits)
            even = proposals.get("DIGITMATCH_0", {})  # Not quite right, need DIGITEVEN/DIGITODD
            # Actually DIGITEVEN and DIGITODD are separate contract types
            even_prop, _ = await get_proposal(client, sym, "DIGITEVEN", dur, amount=args.stake)
            odd_prop, _ = await get_proposal(client, sym, "DIGITODD", dur, amount=args.stake)
            await asyncio.sleep(0.3)

            if even_prop and odd_prop:
                combined_ask = even_prop["ask"] + odd_prop["ask"]
                guaranteed_payout = min(even_prop["payout"], odd_prop["payout"])
                expected_payout = 0.5 * even_prop["payout"] + 0.5 * odd_prop["payout"]
                arb = guaranteed_payout - combined_ask
                ev = expected_payout - combined_ask

                combo = {
                    "symbol": sym,
                    "duration": dur,
                    "type": "EVEN+ODD",
                    "legs": ["DIGITEVEN", "DIGITODD"],
                    "combined_ask": round(combined_ask, 4),
                    "guaranteed_payout": round(guaranteed_payout, 4),
                    "expected_payout": round(expected_payout, 4),
                    "arb_guaranteed": round(arb, 4),
                    "ev": round(ev, 4),
                }
                all_combos.append(combo)

                if arb > 0:
                    print(f"    *** ARB: EVEN+ODD ask=${combined_ask:.2f} "
                          f"guaranteed=${guaranteed_payout:.2f} ARB=+${arb:.4f}", flush=True)
                else:
                    print(f"    EVEN+ODD: ask=${combined_ask:.2f} guaranteed=${guaranteed_payout:.2f} "
                          f"arb=${arb:.4f} EV=${ev:.4f}", flush=True)

            # Test 3-leg: DIGITOVER(N) + DIGITUNDER(N+2) + DIGITMATCH(N+1) = covers all
            for n in range(8):
                over_key = f"DIGITOVER_{n}"
                under_key = f"DIGITUNDER_{n+2}"
                match_key = f"DIGITMATCH_{n+1}"
                over = proposals.get(over_key, {})
                under = proposals.get(under_key, {})
                match = proposals.get(match_key, {})

                if "error" in over or "error" in under or "error" in match:
                    continue

                combined_ask = over["ask"] + under["ask"] + match["ask"]
                # Always win exactly one
                payouts = [over["payout"], under["payout"], match["payout"]]
                guaranteed_payout = min(payouts)
                p_over = (9 - n) / 10
                p_under = (n + 2) / 10
                p_match = 1 / 10
                expected_payout = p_over * over["payout"] + p_under * under["payout"] + p_match * match["payout"]
                arb = guaranteed_payout - combined_ask
                ev = expected_payout - combined_ask

                combo = {
                    "symbol": sym,
                    "duration": dur,
                    "type": "3-leg-full-cover",
                    "legs": [over_key, under_key, match_key],
                    "barrier_n": n,
                    "combined_ask": round(combined_ask, 4),
                    "guaranteed_payout": round(guaranteed_payout, 4),
                    "expected_payout": round(expected_payout, 4),
                    "arb_guaranteed": round(arb, 4),
                    "ev": round(ev, 4),
                }
                all_combos.append(combo)

                if arb > 0:
                    print(f"    *** ARB 3-LEG: OVER({n})+MATCH({n+1})+UNDER({n+2}) "
                          f"ask=${combined_ask:.2f} guaranteed=${guaranteed_payout:.2f} ARB=+${arb:.4f}", flush=True)

            # Test with basis=payout to equalize payouts
            if dur == 5:  # Only test one duration for payout basis
                print(f"    Testing basis=payout for {sym}...", flush=True)
                for n in range(9):
                    over_p, _ = await get_proposal(client, sym, "DIGITOVER", dur, barrier=n, basis="payout", amount=10.0)
                    under_p, _ = await get_proposal(client, sym, "DIGITUNDER", dur, barrier=n+1, basis="payout", amount=10.0)
                    await asyncio.sleep(0.3)

                    if over_p and under_p:
                        combined_ask = over_p["ask"] + under_p["ask"]
                        guaranteed_payout = 10.0  # Both pay $10
                        arb = guaranteed_payout - combined_ask

                        if arb > 0:
                            print(f"    *** ARB (payout basis): OVER({n})+UNDER({n+1}) "
                                  f"ask=${combined_ask:.2f} payout=$10.00 ARB=+${arb:.4f}", flush=True)
                            all_combos.append({
                                "symbol": sym,
                                "duration": dur,
                                "type": "2-leg-payout-basis",
                                "legs": [f"DIGITOVER_{n}", f"DIGITUNDER_{n+1}"],
                                "barrier_n": n,
                                "combined_ask": round(combined_ask, 4),
                                "guaranteed_payout": 10.0,
                                "arb_guaranteed": round(arb, 4),
                                "ev": round(arb, 4),
                            })

    await client.disconnect()

    # Analysis
    arbs = [c for c in all_combos if c.get("arb_guaranteed", 0) > 0]
    positive_ev = [c for c in all_combos if c.get("ev", 0) > 0 and c.get("arb_guaranteed", 0) <= 0]

    print(f"\n=== SUMMARY ===", flush=True)
    print(f"Total combinations tested: {len(all_combos)}", flush=True)
    print(f"Guaranteed arbitrage (arb > 0): {len(arbs)}", flush=True)
    print(f"Positive EV (but no guaranteed arb): {len(positive_ev)}", flush=True)

    if arbs:
        print(f"\n*** ARBITRAGE OPPORTUNITIES ***", flush=True)
        for a in arbs:
            print(f"  {a['symbol']} {a['type']} dur={a['duration']}t: "
                  f"ask=${a['combined_ask']:.2f} payout=${a['guaranteed_payout']:.2f} "
                  f"ARB=+${a['arb_guaranteed']:.4f}", flush=True)
    else:
        print(f"\nNo arbitrage — house margin prevents guaranteed profit on all combinations", flush=True)

    if positive_ev:
        print(f"\n** Positive EV combinations (not guaranteed): {len(positive_ev)}", flush=True)
        for p in positive_ev[:10]:
            print(f"  {p['symbol']} {p['type']} dur={p['duration']}t: EV=+${p['ev']:.4f}", flush=True)

    # Best EV per symbol
    by_symbol = {}
    for c in all_combos:
        s = c["symbol"]
        if s not in by_symbol or c.get("ev", -999) > by_symbol[s].get("ev", -999):
            by_symbol[s] = c

    print(f"\nBest EV per symbol:", flush=True)
    for sym, c in sorted(by_symbol.items()):
        print(f"  {sym}: EV=${c.get('ev', 0):.4f} arb=${c.get('arb_guaranteed', 0):.4f} "
              f"({c['type']} dur={c['duration']}t)", flush=True)

    output = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "hypothesis": "D105",
        "description": "Multi-leg digit combination arbitrage",
        "symbols": symbols,
        "n_combinations": len(all_combos),
        "n_arbitrage": len(arbs),
        "n_positive_ev": len(positive_ev),
        "arbitrage": arbs,
        "positive_ev": positive_ev,
        "all_combos": all_combos,
    }

    with open(args.output, "w") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)
    print(f"\nResults saved to {args.output}", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
