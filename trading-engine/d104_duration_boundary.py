"""D104 — Duration Boundary Pricing Discontinuity.

Hipotese
--------
A Deriv precifica contratos usando uma formula que pode ter discontinuidades
em certas duracoes. Se o payout ratio muda abruptamente entre duracoes
adjacentes (ex: 5t → 6t), pode haver uma "janela" onde o contrato e mais
barato relativo ao fair value.

D97 testou duracoes discretas (1, 5, 10, 25, 50, 100 ticks) mas nao testou
duracoes ADJACENTES. Se a formula tem um "step" em N=6 ou N=11, perderiamos.

Testa:
  1. Para cada simbolo, escanear payout ratio para duracoes 1-100 ticks (todos)
  2. Calcular a derivada discreta (ratio[n+1] - ratio[n])
  3. Flag duracoes onde |derivada| > 2x media (discontinuidade)
  4. Se uma duracao tem ratio anormalmente alto, comprar nela = edge

Uso
---
    python d104_duration_boundary.py --symbols 1HZ10V,R_100 --max-duration 100
"""
import argparse
import asyncio
import json
import math
import os
import statistics
import sys
from datetime import datetime, timezone

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from deriv_client import DerivClient

APP_ID = os.getenv("DERIV_APP_ID", "1089")
TOKEN = os.getenv("DERIV_API_TOKEN", "")
STAKE = 1.0
DEFAULT_SYMBOLS = ["1HZ10V", "1HZ50V", "1HZ100V", "R_10", "R_100"]
DEFAULT_TYPES = ["CALL", "PUT", "CALLE", "PUTE", "DIGITEVEN", "DIGITODD"]


async def get_proposal(client, symbol, contract_type, duration):
    payload = {
        "proposal": 1,
        "amount": STAKE,
        "basis": "stake",
        "contract_type": contract_type,
        "currency": "USD",
        "underlying_symbol": symbol,
        "duration": duration,
        "duration_unit": "t",
    }
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
    return {"ask": float(ask), "payout": float(payout), "ratio": float(payout) / float(ask)}, None


async def main():
    parser = argparse.ArgumentParser(description="D104 Duration Boundary Pricing Discontinuity")
    parser.add_argument("--symbols", default=",".join(DEFAULT_SYMBOLS))
    parser.add_argument("--types", default=",".join(DEFAULT_TYPES))
    parser.add_argument("--max-duration", type=int, default=100)
    parser.add_argument("--output", default="d104_duration_boundary_results.json")
    parser.add_argument("--app-id", default=os.getenv("DERIV_APP_ID", "1089"))
    parser.add_argument("--api-token", default=os.getenv("DERIV_API_TOKEN", ""))
    args = parser.parse_args()

    if not args.api_token:
        print("ERROR: DERIV_API_TOKEN required", flush=True)
        return

    symbols = [s.strip() for s in args.symbols.split(",")]
    contract_types = [t.strip() for t in args.types.split(",")]

    print(f"D104 — Duration Boundary Pricing Discontinuity", flush=True)
    print(f"Symbols: {symbols} | Types: {contract_types} | Max duration: {args.max_duration}t", flush=True)

    client = DerivClient(app_id=args.app_id, api_token=args.api_token, use_demo=True)
    await client.connect()
    await asyncio.sleep(2)

    all_results = {}
    all_discontinuities = []

    for sym in symbols:
        sym_results = {}
        for ct in contract_types:
            print(f"\n  Scanning {sym} {ct}...", flush=True)
            ratios = []
            durations = []

            for dur in range(1, args.max_duration + 1):
                prop, error = await get_proposal(client, sym, ct, dur)
                if error:
                    continue
                ratios.append(prop["ratio"])
                durations.append(dur)
                sym_results[f"{dur}t"] = prop
                if dur % 10 == 0:
                    print(f"    [{dur}/{args.max_duration}] ratio={prop['ratio']:.4f}", flush=True)
                await asyncio.sleep(0.15)

            if len(ratios) < 10:
                print(f"    Insufficient data ({len(ratios)} durations)", flush=True)
                continue

            # Compute discrete derivative
            derivatives = []
            for i in range(1, len(ratios)):
                d = ratios[i] - ratios[i - 1]
                derivatives.append((durations[i], d))

            # Find discontinuities
            abs_derivs = [abs(d) for _, d in derivatives]
            mean_deriv = statistics.mean(abs_derivs) if abs_derivs else 0
            std_deriv = statistics.stdev(abs_derivs) if len(abs_derivs) > 1 else 0

            discontinuities = []
            for dur, d in derivatives:
                if abs(d) > mean_deriv + 2 * std_deriv and abs(d) > 0.01:
                    discontinuities.append({
                        "duration": dur,
                        "derivative": round(d, 6),
                        "ratio_before": round(ratios[durations.index(dur) - 1], 4),
                        "ratio_after": round(ratios[durations.index(dur)], 4),
                        "threshold": round(mean_deriv + 2 * std_deriv, 6),
                    })

            if discontinuities:
                print(f"    *** DISCONTINUITIES found: {len(discontinuities)}", flush=True)
                for disc in discontinuities:
                    print(f"      dur={disc['duration']}t: ratio {disc['ratio_before']:.4f} → "
                          f"{disc['ratio_after']:.4f} (delta={disc['derivative']:+.6f})", flush=True)
                    all_discontinuities.append({
                        "symbol": sym, "contract_type": ct, **disc,
                    })
            else:
                print(f"    No discontinuities (mean_deriv={mean_deriv:.6f}, std={std_deriv:.6f})", flush=True)

            # Check for monotonicity
            is_monotonic = all(ratios[i] >= ratios[i - 1] for i in range(1, len(ratios))) or \
                          all(ratios[i] <= ratios[i - 1] for i in range(1, len(ratios)))
            if not is_monotonic:
                # Find local maxima (potential edge)
                local_maxima = []
                for i in range(1, len(ratios) - 1):
                    if ratios[i] > ratios[i - 1] and ratios[i] > ratios[i + 1]:
                        local_maxima.append((durations[i], ratios[i]))
                if local_maxima:
                    print(f"    Local maxima (potential edge): {local_maxima[:5]}", flush=True)

            # Stats
            print(f"    Range: {min(ratios):.4f} - {max(ratios):.4f} | "
                  f"Mean: {statistics.mean(ratios):.4f} | Std: {statistics.stdev(ratios):.4f}", flush=True)

        all_results[sym] = sym_results

    await client.disconnect()

    # Summary
    print(f"\n=== SUMMARY ===", flush=True)
    print(f"Total discontinuities: {len(all_discontinuities)}", flush=True)
    if all_discontinuities:
        print(f"\nDiscontinuity details:", flush=True)
        for d in all_discontinuities:
            print(f"  {d['symbol']} {d['contract_type']} dur={d['duration']}t: "
                  f"ratio {d['ratio_before']:.4f} → {d['ratio_after']:.4f} "
                  f"(delta={d['derivative']:+.6f})", flush=True)

        # Check if any discontinuity creates positive EV
        # For CALL/PUT: fair ratio = 1/P(win). If ratio > 1/0.5 = 2.0, edge.
        # For DIGITEVEN/ODD: fair ratio = 1/0.5 = 2.0
        edges = [d for d in all_discontinuities if d["ratio_after"] > 2.0]
        if edges:
            print(f"\n*** POTENTIAL EDGES (ratio > 2.0 after discontinuity): {len(edges)} ***", flush=True)
            for e in edges:
                print(f"  {e['symbol']} {e['contract_type']} dur={e['duration']}t: ratio={e['ratio_after']:.4f}", flush=True)
        else:
            print(f"\nNo edges (all ratio_after <= 2.0)", flush=True)
    else:
        print(f"Payout ratio is smooth across all durations — no discontinuity exploitable", flush=True)

    output = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "hypothesis": "D104",
        "description": "Duration boundary pricing discontinuity scan",
        "symbols": symbols,
        "types": contract_types,
        "max_duration": args.max_duration,
        "n_discontinuities": len(all_discontinuities),
        "discontinuities": all_discontinuities,
        "results": all_results,
    }

    with open(args.output, "w") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)
    print(f"\nResults saved to {args.output}", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
