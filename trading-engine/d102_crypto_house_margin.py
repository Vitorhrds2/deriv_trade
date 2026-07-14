"""D102 — Crypto Contract House Margin Scan.

Hipotese
--------
Todos os testes ate agora foram em sinteticos (R_, 1HZ) e forex (frx). Contratos
crypto (cryBTCUSD, cryETHUSD, cryLTCUSD, etc.) NUNCA foram testados. Crypto tem:
  1. Dados de mercado reais (nao RNG)
  2. Volatilidade mais alta e variavel
  3. Market 24/7 (sem gap de sessao)
  4. Possivel lag do feed da Deriv vs exchanges reais

Se a Deriv precifica crypto com house margin diferente (menor, ou com lag),
pode haver edge. Testa:
  1. Scan payout ratios para CALL/PUT/CALLE/PUTE em cryBTCUSD, cryETHUSD
  2. Compara house margin vs sinteticos (~4%) e forex (~12%)
  3. Compara P(win) empirica (via ticks_history) vs implied P (1/payout_ratio)
  4. Se house margin crypto < 2%, ou P_emp > implied P com IC95%, flag

Uso
---
    python d102_crypto_house_margin.py
    python d102_crypto_house_margin.py --symbols cryBTCUSD,cryETHUSD --chunks 40
"""
import argparse
import asyncio
import json
import math
import os
import re
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
DEFAULT_SYMBOLS = ["cryBTCUSD", "cryETHUSD", "cryLTCUSD", "cryXRPUSD", "cryDSHUSD"]
DEFAULT_TYPES = ["CALL", "PUT", "CALLE", "PUTE"]
DEFAULT_DURATIONS = ["1d", "2d", "3d", "5d", "7d", "14d", "30d"]


def parse_duration(value):
    match = re.fullmatch(r"(\d+)([tsmhd])", value.strip().lower())
    if not match:
        raise argparse.ArgumentTypeError(f"invalid: {value}")
    return int(match.group(1)), match.group(2)


def parse_csv(value):
    return [item.strip() for item in value.split(",") if item.strip()]


def as_float(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def wilson_lower(wins, n, z=1.96):
    if n <= 0:
        return 0.0
    p = wins / n
    denom = 1.0 + z * z / n
    center = p + z * z / (2.0 * n)
    margin = z * math.sqrt(p * (1.0 - p) / n + z * z / (4.0 * n * n))
    return (center - margin) / denom


def median_tick_seconds(times):
    deltas = [times[i] - times[i - 1] for i in range(1, len(times)) if times[i] > times[i - 1]]
    return statistics.median(deltas) if deltas else 1.0


def duration_ticks(duration, duration_unit, tick_seconds):
    if duration_unit == "t":
        return max(1, duration)
    seconds = duration * {"s": 1, "m": 60, "h": 3600, "d": 86400}[duration_unit]
    return max(1, round(seconds / tick_seconds))


def empirical_probability(prices, n_ticks, is_up):
    wins = 0
    n = 0
    for start in range(0, len(prices) - n_ticks, n_ticks):
        entry = prices[start]
        final = prices[start + n_ticks]
        if final == entry:
            continue
        wins += int((final > entry) == is_up)
        n += 1
    return wins, n


async def fetch_prices(client, symbol, chunks):
    rows = []
    end = "latest"
    for _ in range(chunks):
        try:
            response = await asyncio.wait_for(client.send_request({
                "ticks_history": symbol,
                "adjust_start_time": 1,
                "count": 5000,
                "end": end,
                "style": "ticks",
            }), timeout=60)
        except Exception:
            break
        if "error" in response:
            break
        history = response.get("history", {})
        prices = history.get("prices", [])
        times = history.get("times", [])
        if not prices or not times:
            break
        rows.extend((float(t), float(p)) for t, p in zip(times, prices))
        end = times[0] - 1
        await asyncio.sleep(0.35)
    rows.sort(key=lambda item: item[0])
    return [p for _, p in rows], [t for t, _ in rows]


async def get_proposal(client, symbol, contract_type, duration, duration_unit):
    payload = {
        "proposal": 1,
        "amount": STAKE,
        "basis": "stake",
        "contract_type": contract_type,
        "currency": "USD",
        "underlying_symbol": symbol,
        "duration": duration,
        "duration_unit": duration_unit,
    }
    try:
        response = await asyncio.wait_for(client.send_request(payload), timeout=30)
    except Exception as e:
        return None, str(e)
    if "error" in response:
        return None, response["error"].get("message", "unknown")
    proposal = response.get("proposal", {})
    ask = as_float(proposal.get("ask_price"))
    payout = as_float(proposal.get("payout"))
    if ask is None or payout is None or ask <= 0 or payout <= 0:
        return None, "no ask/payout"
    return proposal, None


async def main():
    parser = argparse.ArgumentParser(description="D102 Crypto House Margin Scan")
    parser.add_argument("--symbols", default=",".join(DEFAULT_SYMBOLS))
    parser.add_argument("--types", default=",".join(DEFAULT_TYPES))
    parser.add_argument("--durations", default=",".join(DEFAULT_DURATIONS))
    parser.add_argument("--chunks", type=int, default=40)
    parser.add_argument("--mc", type=int, default=10000)
    parser.add_argument("--output", default="d102_crypto_house_margin_results.json")
    parser.add_argument("--app-id", default=os.getenv("DERIV_APP_ID", "1089"))
    parser.add_argument("--api-token", default=os.getenv("DERIV_API_TOKEN", ""))
    args = parser.parse_args()

    if not args.api_token:
        print("ERROR: DERIV_API_TOKEN required", flush=True)
        return

    symbols = parse_csv(args.symbols)
    contract_types = parse_csv(args.types)
    durations = [parse_duration(d) for d in parse_csv(args.durations)]

    print(f"D102 — Crypto Contract House Margin Scan", flush=True)
    print(f"Symbols: {symbols}", flush=True)
    print(f"Types: {contract_types} | Durations: {durations} | chunks={args.chunks}", flush=True)

    client = DerivClient(app_id=args.app_id, api_token=args.api_token, use_demo=True)
    await client.connect()
    await asyncio.sleep(2)

    results = []
    for sym in symbols:
        prices, times = await fetch_prices(client, sym, args.chunks)
        if len(prices) < 500:
            print(f"  {sym}: insufficient ticks ({len(prices)})", flush=True)
            continue
        tick_s = median_tick_seconds(times)
        print(f"  {sym}: {len(prices)} ticks, median_dt={tick_s:.3f}s", flush=True)

        for dur, dur_unit in durations:
            n_ticks = duration_ticks(dur, dur_unit, tick_s)
            for ct in contract_types:
                proposal, error = await get_proposal(client, sym, ct, dur, dur_unit)
                record = {
                    "ts": datetime.now(timezone.utc).isoformat(),
                    "symbol": sym,
                    "contract_type": ct,
                    "duration": dur,
                    "duration_unit": dur_unit,
                    "n_ticks": n_ticks,
                    "error": error,
                }
                if proposal:
                    ask = as_float(proposal.get("ask_price"))
                    payout = as_float(proposal.get("payout"))
                    gross_return = payout / ask
                    implied_p = 1.0 / gross_return
                    is_up = ct in ("CALL", "CALLE")
                    wins, n_windows = empirical_probability(prices, n_ticks, is_up)
                    p_emp = wins / n_windows if n_windows else 0
                    p_lo = wilson_lower(wins, n_windows)
                    ev = p_emp * gross_return - 1.0
                    ev_lo = p_lo * gross_return - 1.0
                    house_margin = 1.0 - implied_p * gross_return  # should be ~0 for fair

                    record.update({
                        "ask_price": ask,
                        "payout": payout,
                        "gross_return": gross_return,
                        "implied_probability": implied_p,
                        "wins": wins,
                        "n_windows": n_windows,
                        "p_emp": p_emp,
                        "p_emp_lo": p_lo,
                        "ev": ev,
                        "ev_lo": ev_lo,
                        "house_margin": house_margin,
                        "longcode": proposal.get("longcode", ""),
                    })
                    print(f"    {ct:6s} {dur}{dur_unit}: Pemp={p_emp:.4f} implied={implied_p:.4f} "
                          f"EV={ev:+.4f} EVlo={ev_lo:+.4f} margin={house_margin:.4f}", flush=True)
                else:
                    print(f"    {ct:6s} {dur}{dur_unit}: ERROR: {error}", flush=True)

                results.append(record)
                await asyncio.sleep(0.25)

    await client.disconnect()

    # Analysis
    valid = [r for r in results if "ev" in r]
    candidates = [r for r in valid if r["ev_lo"] > 0 and r["n_windows"] >= 50]

    by_symbol = {}
    for r in valid:
        s = r["symbol"]
        if s not in by_symbol:
            by_symbol[s] = []
        by_symbol[s].append(r)

    print(f"\n=== SUMMARY ===", flush=True)
    print(f"Total cells: {len(results)} | Valid: {len(valid)} | Gate candidates: {len(candidates)}", flush=True)

    for sym, rows in sorted(by_symbol.items()):
        margins = [r["house_margin"] for r in rows]
        evs = [r["ev"] for r in rows]
        ev_los = [r["ev_lo"] for r in rows]
        print(f"\n  {sym}:", flush=True)
        print(f"    N={len(rows)} | mean_margin={statistics.mean(margins):.4f} | "
              f"mean_EV={statistics.mean(evs):+.4f} | best_EVlo={max(ev_los):+.4f}", flush=True)

    # Compare with synthetics
    all_margins = [r["house_margin"] for r in valid]
    if all_margins:
        print(f"\n  Overall: mean_house_margin={statistics.mean(all_margins):.4f}", flush=True)
        print(f"  (Synthetics ~0.04, Forex ~0.12 for comparison)", flush=True)
    else:
        print(f"\n  No valid results — all proposals returned errors", flush=True)
        print(f"  Crypto contracts may not support the requested durations/types", flush=True)

    if candidates:
        print(f"\n  *** GATE CANDIDATES ({len(candidates)}) ***", flush=True)
        for c in candidates:
            print(f"    {c['symbol']} {c['contract_type']} {c['duration']}{c['duration_unit']}: "
                  f"EVlo={c['ev_lo']:+.4f} Pemp={c['p_emp']:.4f} implied={c['implied_probability']:.4f}", flush=True)
    else:
        print(f"\n  No gate candidates (all EVlo <= 0)", flush=True)

    output = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "hypothesis": "D102",
        "description": "Crypto contract house margin scan",
        "symbols": symbols,
        "types": contract_types,
        "durations": [f"{d}{u}" for d, u in durations],
        "n_cells": len(results),
        "n_valid": len(valid),
        "n_gate_candidates": len(candidates),
        "by_symbol": {
            sym: {
                "n": len(rows),
                "mean_margin": statistics.mean([r["house_margin"] for r in rows]),
                "mean_ev": statistics.mean([r["ev"] for r in rows]),
                "best_ev_lo": max([r["ev_lo"] for r in rows]),
            }
            for sym, rows in sorted(by_symbol.items())
        },
        "overall_mean_margin": statistics.mean(all_margins) if all_margins else 0,
        "results": results,
    }

    with open(args.output, "w") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)
    print(f"\nResults saved to {args.output}", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
