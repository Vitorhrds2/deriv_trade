"""D97 — Payout Curve Deep Scan.

Hipotese
--------
D86 testou straddle arb em 5 duracoes/8 simbolos e encontrou house margin consistente.
Mas nao testou sistematicamente TODOS os durations, TODOS os contract types, TODOS os
simbolos, e multiplas stake sizes. Se qualquer combinacao de parametros produzir um
payout ratio anormalmente alto (mispricing), e exploravel.

Adicionalmente, testa se o payout ratio varia com stake size (scaling exploit) e se
o payout ratio muda ao longo do tempo (transient mispricing).

Testa:
  - 35 contract types x 5 durations x 10 symbols x 3 stake sizes = ~5250 cells
  - Para cada cell: payout_ratio = payout / ask_price
  - Flag cells onde payout_ratio > media + 2*std (anomalo)
  - Flag cells onde payout_ratio varia com stake size (scaling exploit)

Uso
---
    python d97_payout_curve_scan.py
    python d97_payout_curve_scan.py --symbols 1HZ10V,R_10 --max-duration 50

Output: d97_payout_curve_results.json
"""
import argparse
import asyncio
import json
import math
import os
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from deriv_client import DerivClient

SYMBOLS_DEFAULT = [
    "1HZ10V", "1HZ25V", "1HZ50V", "1HZ100V",
    "R_10", "R_25", "R_50", "R_100",
    "JD10", "JD50", "JD100",
]

# Contract types que aceitam duration em ticks
CONTRACT_TYPES_TICKS = [
    "CALL", "PUT", "CALLE", "PUTE",
    "DIGITEVEN", "DIGITODD",
    "DIGITOVER", "DIGITUNDER",
    "DIGITDIFF", "DIGITMATCH",
    "EXPIRYMISS", "EXPIRYRANGE",
    "EXPIRYMISSE", "EXPIRYRANGEE",
    "RESETCALL", "RESETPUT",
    "RUNHIGH", "RUNLOW",
    "TICKHIGH", "TICKLOW",
    "UPORDOWN",
    "ONETOUCH", "NOTOUCH",
]

BARRIER_CONTRACTS = {
    "DIGITOVER": "5",
    "DIGITUNDER": "4",
    "DIGITDIFF": "0",
    "DIGITMATCH": "0",
    "UPORDOWN": "5",
    "ONETOUCH": "5",
    "NOTOUCH": "5",
}

DURATIONS_TICKS = [1, 2, 3, 5, 10, 15, 25, 50, 100]
STAKE_SIZES = [1.0, 10.0, 100.0]


async def get_payout_ratio(client, symbol, contract_type, duration, stake, barrier=None):
    """Retorna (payout_ratio, payout, ask_price) ou None se erro."""
    payload = {
        "proposal": 1,
        "amount": stake,
        "basis": "stake",
        "contract_type": contract_type,
        "currency": "USD",
        "underlying_symbol": symbol,
        "duration": duration,
        "duration_unit": "t",
    }
    if barrier is not None:
        payload["barrier"] = str(barrier)

    try:
        res = await client.send_request(payload)
    except Exception:
        return None
    if "error" in res:
        return None
    p = res.get("proposal", {})
    payout = p.get("payout")
    ask = p.get("ask_price")
    if not payout or not ask:
        return None
    return {
        "payout_ratio": payout / ask,
        "payout": payout,
        "ask_price": ask,
        "stake": stake,
    }


async def scan_symbol(client, symbol, durations, stakes, max_cells=None):
    """Escaneia payout ratios para um simbolo."""
    results = []
    cell_count = 0
    for ct in CONTRACT_TYPES_TICKS:
        barrier = BARRIER_CONTRACTS.get(ct)
        for dur in durations:
            for stake in stakes:
                if max_cells and cell_count >= max_cells:
                    return results
                r = await get_payout_ratio(client, symbol, ct, dur, stake, barrier)
                if r:
                    r["contract_type"] = ct
                    r["duration"] = dur
                    r["symbol"] = symbol
                    results.append(r)
                    cell_count += 1
                    if cell_count % 50 == 0:
                        print(f"  {symbol}: {cell_count} cells scanned", flush=True)
                await asyncio.sleep(0.15)  # Rate limit safety
    return results


def analyze_payout_curve(results):
    """Analisa resultados em busca de anomalias."""
    if not results:
        return None

    ratios = [r["payout_ratio"] for r in results]
    n = len(ratios)
    mean_ratio = sum(ratios) / n
    var = sum((r - mean_ratio) ** 2 for r in ratios) / n
    std = math.sqrt(var)

    # Cells anomalias (payout ratio > mean + 2*std)
    threshold = mean_ratio + 2 * std
    anomalies = [r for r in results if r["payout_ratio"] > threshold]
    anomalies.sort(key=lambda r: r["payout_ratio"], reverse=True)

    # Stake-dependence: agrupa por (symbol, contract_type, duration) e checa variacao entre stakes
    stake_groups = defaultdict(list)
    for r in results:
        key = (r["symbol"], r["contract_type"], r["duration"])
        stake_groups[key].append(r)

    stake_anomalies = []
    for key, group in stake_groups.items():
        if len(group) < 2:
            continue
        ratios_by_stake = {g["stake"]: g["payout_ratio"] for g in group}
        ratio_values = list(ratios_by_stake.values())
        if max(ratio_values) - min(ratio_values) > 0.001:  # 0.1% difference
            stake_anomalies.append({
                "symbol": key[0],
                "contract_type": key[1],
                "duration": key[2],
                "ratios_by_stake": {str(k): round(v, 6) for k, v in sorted(ratios_by_stake.items())},
                "max_diff": round(max(ratio_values) - min(ratio_values), 6),
            })

    # Duration curve: para cada (symbol, contract_type), como payout_ratio varia com duration?
    duration_curves = defaultdict(list)
    for r in results:
        if r["stake"] == 1.0:  # Usa stake base
            key = (r["symbol"], r["contract_type"])
            duration_curves[key].append((r["duration"], r["payout_ratio"]))

    duration_anomalies = []
    for key, curve in duration_curves.items():
        if len(curve) < 3:
            continue
        curve.sort()
        ratios = [c[1] for c in curve]
        # Procura por pico nao-monotono (payout ratio que sobe e depois desce)
        for i in range(1, len(ratios) - 1):
            if ratios[i] > ratios[i - 1] and ratios[i] > ratios[i + 1]:
                diff = ratios[i] - max(ratios[i - 1], ratios[i + 1])
                if diff > 0.001:
                    duration_anomalies.append({
                        "symbol": key[0],
                        "contract_type": key[1],
                        "duration_peak": curve[i][0],
                        "payout_ratio_peak": round(ratios[i], 6),
                        "neighbors": [round(ratios[i - 1], 6), round(ratios[i + 1], 6)],
                        "diff": round(diff, 6),
                    })

    return {
        "n_cells": n,
        "mean_payout_ratio": round(mean_ratio, 6),
        "std_payout_ratio": round(std, 6),
        "anomaly_threshold": round(threshold, 6),
        "n_anomalies": len(anomalies),
        "top_anomalies": [
            {
                "symbol": a["symbol"],
                "contract_type": a["contract_type"],
                "duration": a["duration"],
                "stake": a["stake"],
                "payout_ratio": round(a["payout_ratio"], 6),
                "payout": a["payout"],
                "ask_price": a["ask_price"],
            }
            for a in anomalies[:20]
        ],
        "stake_dependence": stake_anomalies[:20],
        "n_stake_anomalies": len(stake_anomalies),
        "duration_curve_anomalies": duration_anomalies[:20],
        "n_duration_anomalies": len(duration_anomalies),
    }


async def main():
    parser = argparse.ArgumentParser(description="D97 Payout Curve Deep Scan")
    parser.add_argument("--symbols", default=",".join(SYMBOLS_DEFAULT))
    parser.add_argument("--max-duration", type=int, default=100)
    parser.add_argument("--output", default="d97_payout_curve_results.json")
    parser.add_argument("--app-id", default=os.getenv("DERIV_APP_ID", "1089"))
    args = parser.parse_args()

    symbols = [s.strip() for s in args.symbols.split(",") if s.strip()]
    durations = [d for d in DURATIONS_TICKS if d <= args.max_duration]

    print(f"D97 — Payout Curve Deep Scan", flush=True)
    print(f"Symbols: {symbols}", flush=True)
    print(f"Durations: {durations}", flush=True)
    print(f"Stakes: {STAKE_SIZES}", flush=True)
    print(f"Contract types: {len(CONTRACT_TYPES_TICKS)}", flush=True)
    total_cells = len(symbols) * len(CONTRACT_TYPES_TICKS) * len(durations) * len(STAKE_SIZES)
    print(f"Max cells: ~{total_cells}", flush=True)

    client = DerivClient(app_id=args.app_id, use_demo=False)
    await client.connect()
    await asyncio.sleep(1)

    all_results = []
    for sym in symbols:
        print(f"\n--- Scanning {sym} ---", flush=True)
        results = await scan_symbol(client, sym, durations, STAKE_SIZES)
        all_results.extend(results)
        print(f"  {sym}: {len(results)} valid cells", flush=True)

    await client.disconnect()

    analysis = analyze_payout_curve(all_results)

    output = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "hypothesis": "D97",
        "description": "Payout curve deep scan across durations, contract types, symbols, stakes",
        "symbols_tested": len(symbols),
        "total_cells": len(all_results),
        "analysis": analysis,
        "raw_results": all_results,
    }

    with open(args.output, "w") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    print(f"\n=== SUMMARY ===", flush=True)
    if analysis:
        print(f"Cells: {analysis['n_cells']}", flush=True)
        print(f"Mean payout ratio: {analysis['mean_payout_ratio']:.4f}", flush=True)
        print(f"Anomalies (payout ratio > mean+2std): {analysis['n_anomalies']}", flush=True)
        print(f"Stake-dependence anomalies: {analysis['n_stake_anomalies']}", flush=True)
        print(f"Duration curve anomalies: {analysis['n_duration_anomalies']}", flush=True)
        if analysis["top_anomalies"]:
            print(f"\nTop 5 anomalies:", flush=True)
            for a in analysis["top_anomalies"][:5]:
                print(f"  {a['symbol']} {a['contract_type']} dur={a['duration']} stake=${a['stake']} "
                      f"ratio={a['payout_ratio']:.4f} payout=${a['payout']}", flush=True)
        if analysis["stake_dependence"]:
            print(f"\nStake-dependence (payout varies with stake):", flush=True)
            for s in analysis["stake_dependence"][:5]:
                print(f"  {s['symbol']} {s['contract_type']} dur={s['duration']} "
                      f"ratios={s['ratios_by_stake']}", flush=True)
    print(f"\nResults saved to {args.output}", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
