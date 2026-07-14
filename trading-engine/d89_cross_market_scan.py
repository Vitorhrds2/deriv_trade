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

from d90_deriv_client import DerivClient

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

APP_ID = os.getenv("DERIV_APP_ID")
TOKEN = os.getenv("DERIV_API_TOKEN")
STAKE = 1.0
DEFAULT_SYMBOLS = ["1HZ10V", "R_100", "frxEURUSD", "cryBTCUSD"]
DEFAULT_TYPES = ["CALL", "PUT", "CALLE", "PUTE"]
DEFAULT_DURATIONS = ["1t", "5t", "10t", "15t", "1m", "5m"]
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_RESULTS = os.path.join(BASE_DIR, "d89_cross_market_results.jsonl")
DEFAULT_STATS = os.path.join(BASE_DIR, "d89_cross_market_stats.json")


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


def market_class(symbol):
    if symbol.startswith("frx"):
        return "forex"
    if symbol.startswith("cry"):
        return "crypto"
    if symbol.startswith("R_") or symbol.startswith("1HZ"):
        return "synthetic"
    return "other"


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


async def connect_with_retries(client, retries=8):
    for attempt in range(retries):
        try:
            await client.connect()
            return
        except Exception:
            if attempt == retries - 1:
                raise
            await asyncio.sleep(min(2 * (attempt + 1), 15))


async def request_with_retries(client, payload, retries=8):
    last_error = None
    for attempt in range(retries):
        try:
            return await asyncio.wait_for(client.send_request(payload.copy()), timeout=60)
        except Exception as error:
            last_error = error
            if attempt < retries - 1:
                await asyncio.sleep(min(2 * (attempt + 1), 15))
    return {"error": {"message": f"reconexões esgotadas: {last_error}"}}


async def fetch_prices(client, symbol, chunks):
    rows = []
    end = "latest"
    for _ in range(chunks):
        response = await request_with_retries(client, {
            "ticks_history": symbol,
            "adjust_start_time": 1,
            "count": 5000,
            "end": end,
            "style": "ticks",
        })
        if "error" in response:
            print(f"{symbol}: ticks_history: {response['error'].get('message', 'unknown error')}")
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


def direction(contract_type):
    return contract_type in ("CALL", "CALLE")


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


def monte_carlo_probability(prices, n_ticks, is_up, simulations, seed):
    returns = [math.log(prices[i] / prices[i - 1]) for i in range(1, len(prices)) if prices[i] > 0 and prices[i - 1] > 0]
    if not returns:
        return 0.0
    mean_return = statistics.mean(returns)
    demeaned = [value - mean_return for value in returns]
    rng = random.Random(seed)
    wins = 0
    for _ in range(simulations):
        log_move = sum(rng.choice(demeaned) for _ in range(n_ticks))
        if log_move != 0:
            wins += int((log_move > 0) == is_up)
    return wins / simulations


async def get_proposal(client, symbol, contract_type, duration, duration_unit):
    response = await request_with_retries(client, {
        "proposal": 1,
        "amount": STAKE,
        "basis": "stake",
        "contract_type": contract_type,
        "currency": "USD",
        "underlying_symbol": symbol,
        "duration": duration,
        "duration_unit": duration_unit,
    })
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
    client = DerivClient(app_id=APP_ID, api_token=TOKEN, use_demo=True)
    await connect_with_retries(client)
    records = []
    try:
        print("=" * 100)
        print("D89 — Cross-Market Deriv Pricing Scan")
        print(f"Symbols: {symbols}")
        print(f"Market classes: {sorted({market_class(symbol) for symbol in symbols})}")
        print(f"Types: {contract_types} | Durations: {durations} | chunks={args.chunks} | MC={args.mc}")
        print("Read-only: no buy/sell requests")
        print("=" * 100)
        for symbol_index, symbol in enumerate(symbols):
            prices, times = await fetch_prices(client, symbol, args.chunks)
            if len(prices) < args.min_ticks:
                print(f"{symbol}: historico insuficiente ({len(prices)} ticks)")
                continue
            tick_seconds = median_tick_seconds(times)
            print(f"{symbol} [{market_class(symbol)}]: {len(prices)} ticks, median_dt={tick_seconds:.3f}s")
            for duration, duration_unit in durations:
                n_ticks = duration_ticks(duration, duration_unit, tick_seconds)
                for contract_type in contract_types:
                    proposal, error = await get_proposal(
                        client, symbol, contract_type, duration, duration_unit
                    )
                    record = {
                        "ts": datetime.now(timezone.utc).isoformat(),
                        "symbol": symbol,
                        "market_class": market_class(symbol),
                        "contract_type": contract_type,
                        "duration": duration,
                        "duration_unit": duration_unit,
                        "n_ticks": n_ticks,
                        "tick_seconds": tick_seconds,
                        "error": error,
                    }
                    if proposal:
                        ask = as_float(proposal.get("ask_price"))
                        payout = as_float(proposal.get("payout"))
                        is_up = direction(contract_type)
                        wins, n_windows = empirical_probability(prices, n_ticks, is_up)
                        p_emp = wins / n_windows if n_windows else 0.0
                        p_lo = wilson_lower(wins, n_windows)
                        p_mc = monte_carlo_probability(
                            prices, n_ticks, is_up, args.mc, args.seed + symbol_index
                        )
                        gross_return = payout / ask
                        record.update({
                            "ask_price": ask,
                            "payout": payout,
                            "gross_return": gross_return,
                            "implied_probability": 1.0 / gross_return,
                            "proposal_spot": as_float(proposal.get("spot")),
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
                            f"{symbol} {contract_type} {duration}{duration_unit}: "
                            f"Pemp={p_emp:.4f} Pmc={p_mc:.4f} "
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
    by_class = defaultdict(list)
    by_symbol = defaultdict(list)
    for record in valid:
        by_class[record["market_class"]].append(record)
        by_symbol[record["symbol"]].append(record)
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
        "by_class": {
            cls: {
                "n": len(rows),
                "mean_ev": statistics.mean(row["ev"] for row in rows),
                "mean_ev_lo": statistics.mean(row["ev_lo"] for row in rows),
                "best_ev_lo": max(row["ev_lo"] for row in rows),
                "mean_implied_probability": statistics.mean(row["implied_probability"] for row in rows),
            }
            for cls, rows in sorted(by_class.items())
        },
        "by_symbol": {
            symbol: {
                "market_class": rows[0]["market_class"],
                "n": len(rows),
                "mean_ev": statistics.mean(row["ev"] for row in rows),
                "best_ev_lo": max(row["ev_lo"] for row in rows),
            }
            for symbol, rows in sorted(by_symbol.items())
        },
    }
    with open(args.stats, "w", encoding="utf-8") as handle:
        json.dump(stats, handle, indent=2, ensure_ascii=False, default=str)
    print("=" * 100)
    print(f"D89 summary: valid={len(valid)} gate_candidates={len(candidates)}")
    for cls, summary in stats["by_class"].items():
        print(f"{cls}: n={summary['n']} mean_EV={summary['mean_ev']:+.4f} best_EVlo={summary['best_ev_lo']:+.4f}")
    print(f"Results: {args.output}")
    print(f"Stats: {args.stats}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbols", default=",".join(DEFAULT_SYMBOLS))
    parser.add_argument("--types", default=",".join(DEFAULT_TYPES))
    parser.add_argument("--durations", default=",".join(DEFAULT_DURATIONS))
    parser.add_argument("--chunks", type=int, default=10)
    parser.add_argument("--min-ticks", type=int, default=1000)
    parser.add_argument("--min-windows", type=int, default=100)
    parser.add_argument("--max-dgp-divergence", type=float, default=0.03)
    parser.add_argument("--mc", type=int, default=10000)
    parser.add_argument("--seed", type=int, default=89)
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
