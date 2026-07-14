import argparse
import asyncio
import json
import math
import os
import random
import re
import statistics
import sys
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
STAKE = 1.0
DEFAULT_SYMBOLS = ["1HZ10V", "R_100"]
DEFAULT_TYPES = ["EXPIRYMISSE", "EXPIRYRANGEE", "CALLE", "PUTE"]
DEFAULT_DURATIONS = ["5t", "10t", "15t", "1m", "5m"]
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_RESULTS = os.path.join(BASE_DIR, "d88_e_variant_results.jsonl")
DEFAULT_STATS = os.path.join(BASE_DIR, "d88_e_variant_stats.json")


def parse_duration(value):
    match = re.fullmatch(r"(\d+)([tsmhd])", value.strip().lower())
    if not match:
        raise argparse.ArgumentTypeError(f"duracao invalida: {value}")
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
    denominator = 1.0 + z * z / n
    center = p + z * z / (2.0 * n)
    margin = z * math.sqrt(p * (1.0 - p) / n + z * z / (4.0 * n * n))
    return (center - margin) / denominator


def append_jsonl(path, record):
    with open(path, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")


async def fetch_prices(client, symbol, chunks):
    rows = []
    end = "latest"
    for _ in range(chunks):
        response = await client.send_request({
            "ticks_history": symbol,
            "adjust_start_time": 1,
            "count": 5000,
            "end": end,
            "style": "ticks",
        })
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
    return [price for _, price in rows], [timestamp for timestamp, _ in rows]


def median_tick_seconds(times):
    deltas = [times[i] - times[i - 1] for i in range(1, len(times)) if times[i] > times[i - 1]]
    return statistics.median(deltas) if deltas else 1.0


def duration_ticks(duration, duration_unit, tick_seconds):
    if duration_unit == "t":
        return max(1, duration)
    seconds = duration * {"s": 1, "m": 60, "h": 3600, "d": 86400}[duration_unit]
    return max(1, round(seconds / tick_seconds))


def empirical_probability(prices, n_ticks, contract_type, barrier_pct):
    wins = 0
    n = 0
    for start in range(0, len(prices) - n_ticks, n_ticks):
        entry = prices[start]
        final = prices[start + n_ticks]
        if entry <= 0:
            continue
        relative = final / entry
        if contract_type in ("CALLE", "PUTE"):
            won = relative > 1.0 if contract_type == "CALLE" else relative < 1.0
        else:
            inside = 1.0 - barrier_pct <= relative <= 1.0 + barrier_pct
            won = not inside if contract_type in ("EXPIRYMISS", "EXPIRYMISSE") else inside
        wins += int(won)
        n += 1
    return wins, n


def monte_carlo_probability(prices, n_ticks, contract_type, barrier_pct, simulations, seed):
    if len(prices) < 2:
        return 0.0
    returns = [math.log(prices[i] / prices[i - 1]) for i in range(1, len(prices)) if prices[i] > 0 and prices[i - 1] > 0]
    if not returns:
        return 0.0
    mean_return = statistics.mean(returns)
    demeaned = [value - mean_return for value in returns]
    rng = random.Random(seed)
    wins = 0
    for _ in range(simulations):
        log_move = sum(rng.choice(demeaned) for _ in range(n_ticks))
        relative = math.exp(log_move)
        if contract_type in ("CALLE", "PUTE"):
            won = relative > 1.0 if contract_type == "CALLE" else relative < 1.0
        else:
            inside = 1.0 - barrier_pct <= relative <= 1.0 + barrier_pct
            won = not inside if contract_type in ("EXPIRYMISS", "EXPIRYMISSE") else inside
        wins += int(won)
    return wins / simulations


async def get_proposal(client, symbol, contract_type, duration, duration_unit, spot, barrier_pct):
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
    if contract_type.startswith("EXPIRY"):
        offset = spot * barrier_pct
        payload["barrier"] = f"+{offset:.8f}"
        payload["barrier2"] = f"-{offset:.8f}"
    response = await client.send_request(payload)
    if "error" in response:
        return None, response["error"].get("message", "unknown error")
    proposal = response.get("proposal", {})
    ask = as_float(proposal.get("ask_price"))
    payout = as_float(proposal.get("payout"))
    if ask is None or payout is None or ask <= 0 or payout <= 0:
        return None, "proposal sem ask_price/payout valido"
    return proposal, None


async def scan(args):
    symbols = parse_csv(args.symbols)
    contract_types = parse_csv(args.types)
    durations = [parse_duration(item) for item in parse_csv(args.durations)]
    barrier_pcts = [float(item) for item in parse_csv(args.barrier_pcts)]
    client = DerivClient(app_id=APP_ID, api_token=TOKEN, use_demo=True)
    await client.connect()
    records = []
    try:
        print("=" * 100)
        print("D88 — E-Suffixed Contract Variant Scan")
        print(f"Symbols: {symbols} | Types: {contract_types} | Durations: {durations}")
        print(f"Barrier offsets: {barrier_pcts} | chunks={args.chunks} | MC={args.mc}")
        print("Read-only: no buy/sell requests")
        print("=" * 100)
        for symbol_index, symbol in enumerate(symbols):
            prices, times = await fetch_prices(client, symbol, args.chunks)
            if len(prices) < 100:
                print(f"{symbol}: historico insuficiente ({len(prices)} ticks)")
                continue
            tick_seconds = median_tick_seconds(times)
            spot = prices[-1]
            print(f"{symbol}: {len(prices)} ticks, median_dt={tick_seconds:.3f}s, spot={spot}")
            for duration, duration_unit in durations:
                n_ticks = duration_ticks(duration, duration_unit, tick_seconds)
                for contract_type in contract_types:
                    pcts = barrier_pcts if contract_type.startswith("EXPIRY") else [0.0]
                    for barrier_pct in pcts:
                        proposal, error = await get_proposal(
                            client, symbol, contract_type, duration, duration_unit, spot, barrier_pct
                        )
                        record = {
                            "ts": datetime.now(timezone.utc).isoformat(),
                            "symbol": symbol,
                            "contract_type": contract_type,
                            "duration": duration,
                            "duration_unit": duration_unit,
                            "n_ticks": n_ticks,
                            "tick_seconds": tick_seconds,
                            "barrier_pct": barrier_pct,
                            "spot_reference": spot,
                            "error": error,
                        }
                        if proposal:
                            ask = as_float(proposal.get("ask_price"))
                            payout = as_float(proposal.get("payout"))
                            wins, n_windows = empirical_probability(prices, n_ticks, contract_type, barrier_pct)
                            p_emp = wins / n_windows if n_windows else 0.0
                            p_lo = wilson_lower(wins, n_windows)
                            p_mc = monte_carlo_probability(
                                prices,
                                n_ticks,
                                contract_type,
                                barrier_pct,
                                args.mc,
                                args.seed + symbol_index,
                            )
                            gross_return = payout / ask
                            record.update({
                                "ask_price": ask,
                                "payout": payout,
                                "gross_return": gross_return,
                                "implied_probability": 1.0 / gross_return,
                                "proposal_spot": as_float(proposal.get("spot")),
                                "barrier": proposal.get("barrier"),
                                "barrier2": proposal.get("barrier2"),
                                "longcode": proposal.get("longcode"),
                                "contract_details": proposal.get("contract_details", {}),
                                "wins": wins,
                                "n_windows": n_windows,
                                "p_emp": p_emp,
                                "p_emp_lo": p_lo,
                                "p_mc": p_mc,
                                "ev": p_emp * gross_return - 1.0,
                                "ev_lo": p_lo * gross_return - 1.0,
                                "mc_ev": p_mc * gross_return - 1.0,
                                "dgp_divergence": abs(p_emp - p_mc),
                            })
                            print(
                                f"{symbol} {contract_type} {duration}{duration_unit} "
                                f"bar={barrier_pct:.4f}: Pemp={p_emp:.4f} Pmc={p_mc:.4f} "
                                f"EV={record['ev']:+.4f} EVlo={record['ev_lo']:+.4f}"
                            )
                        else:
                            print(f"{symbol} {contract_type} {duration}{duration_unit}: {error}")
                        records.append(record)
                        append_jsonl(args.output, record)
                        await asyncio.sleep(args.delay)
    finally:
        await client.disconnect()

    valid = [r for r in records if "ev" in r]
    candidates = [
        r for r in valid
        if r["ev_lo"] > 0 and r["n_windows"] >= args.min_windows and r["dgp_divergence"] < args.max_dgp_divergence
    ]
    by_type = defaultdict(list)
    for record in valid:
        by_type[record["contract_type"]].append(record)
    stats = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "n_records": len(records),
        "n_valid": len(valid),
        "n_errors": len(records) - len(valid),
        "n_gate_candidates": len(candidates),
        "gate": {
            "ev_lo_gt": 0,
            "min_windows": args.min_windows,
            "max_dgp_divergence": args.max_dgp_divergence,
        },
        "by_type": {
            contract_type: {
                "n": len(rows),
                "best_ev": max(row["ev"] for row in rows),
                "best_ev_lo": max(row["ev_lo"] for row in rows),
                "mean_ev": statistics.mean(row["ev"] for row in rows),
                "longcodes": sorted({row["longcode"] for row in rows if row.get("longcode")}),
            }
            for contract_type, rows in sorted(by_type.items())
        },
    }
    with open(args.stats, "w", encoding="utf-8") as handle:
        json.dump(stats, handle, indent=2, ensure_ascii=False, default=str)
    print("=" * 100)
    print(f"D88 summary: valid={len(valid)} gate_candidates={len(candidates)}")
    print(f"Results: {args.output}")
    print(f"Stats: {args.stats}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbols", default=",".join(DEFAULT_SYMBOLS))
    parser.add_argument("--types", default=",".join(DEFAULT_TYPES))
    parser.add_argument("--durations", default=",".join(DEFAULT_DURATIONS))
    parser.add_argument("--barrier-pcts", default="0.005,0.01")
    parser.add_argument("--chunks", type=int, default=10)
    parser.add_argument("--mc", type=int, default=10000)
    parser.add_argument("--seed", type=int, default=88)
    parser.add_argument("--min-windows", type=int, default=100)
    parser.add_argument("--max-dgp-divergence", type=float, default=0.03)
    parser.add_argument("--delay", type=float, default=0.25)
    parser.add_argument("--output", default=DEFAULT_RESULTS)
    parser.add_argument("--stats", default=DEFAULT_STATS)
    args = parser.parse_args()
    if not APP_ID:
        print("ERRO: DERIV_APP_ID nao encontrado.")
        return
    asyncio.run(scan(args))


if __name__ == "__main__":
    main()
