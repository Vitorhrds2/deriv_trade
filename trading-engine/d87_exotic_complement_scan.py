import argparse
import asyncio
import json
import os
import re
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
DEFAULT_SYMBOLS = ["1HZ10V", "1HZ50V", "1HZ100V", "R_10", "R_50", "R_100"]
DEFAULT_DURATIONS = ["5t", "10t", "15t", "1m", "5m"]
PAIR_SPECS = {
    "touch": ("ONETOUCH", "NOTOUCH", "single"),
    "expiry": ("EXPIRYRANGE", "EXPIRYMISS", "double"),
    "range": ("RANGE", "UPORDOWN", "double"),
}

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_RESULTS = os.path.join(BASE_DIR, "d87_exotic_complement_results.jsonl")
DEFAULT_STATS = os.path.join(BASE_DIR, "d87_exotic_complement_stats.json")


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


async def current_spot(client, symbol):
    response = await client.send_request({
        "ticks_history": symbol,
        "count": 1,
        "end": "latest",
        "style": "ticks",
    })
    prices = response.get("history", {}).get("prices", [])
    if prices:
        return float(prices[-1])
    return None


def barrier_variants(spot, pair_kind, offset_pct):
    offset = spot * offset_pct
    if pair_kind == "single":
        return [
            {"side": "up", "barrier": f"+{offset:.2f}", "barrier2": None},
            {"side": "down", "barrier": f"-{offset:.2f}", "barrier2": None},
        ]
    return [{
        "side": "both",
        "barrier": f"+{offset:.2f}",
        "barrier2": f"-{offset:.2f}",
    }]


async def get_proposal(client, symbol, contract_type, duration, duration_unit, barriers):
    payload = {
        "proposal": 1,
        "amount": STAKE,
        "basis": "stake",
        "contract_type": contract_type,
        "currency": "USD",
        "underlying_symbol": symbol,
        "duration": duration,
        "duration_unit": duration_unit,
        "barrier": barriers["barrier"],
    }
    if barriers.get("barrier2") is not None:
        payload["barrier2"] = barriers["barrier2"]
    response = await client.send_request(payload)
    if "error" in response:
        return None, response["error"].get("message", "unknown error")
    proposal = response.get("proposal", {})
    ask = as_float(proposal.get("ask_price"))
    payout = as_float(proposal.get("payout"))
    if ask is None or payout is None or ask <= 0 or payout <= 0:
        return None, "proposal sem ask_price/payout valido"
    return proposal, None


def append_jsonl(path, record):
    with open(path, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")


async def scan(args):
    durations = [parse_duration(item) for item in parse_csv(args.durations)]
    symbols = parse_csv(args.symbols)
    pair_names = parse_csv(args.pairs)
    offsets = [float(item) for item in parse_csv(args.offset_pcts)]
    unknown = sorted(set(pair_names) - set(PAIR_SPECS))
    if unknown:
        raise ValueError(f"pares desconhecidos: {', '.join(unknown)}")

    client = DerivClient(app_id=APP_ID, api_token=TOKEN, use_demo=True)
    await client.connect()
    records = []
    try:
        print("=" * 100)
        print("D87 — Exotic Complementary Contract Arbitrage")
        print(f"Symbols: {symbols}")
        print(f"Pairs: {pair_names} | Durations: {durations} | Offsets: {offsets}")
        print(f"Rounds: {args.rounds} | Stake per leg: ${STAKE:.2f}")
        print("Read-only: no buy/sell requests")
        print("=" * 100)

        for symbol in symbols:
            for duration, duration_unit in durations:
                for round_num in range(args.rounds):
                    spot = await current_spot(client, symbol)
                    if spot is None or spot <= 0:
                        print(f"{symbol} {duration}{duration_unit} round={round_num}: sem spot")
                        continue
                    for pair_name in pair_names:
                        call_type, put_type, pair_kind = PAIR_SPECS[pair_name]
                        for offset_pct in offsets:
                            for barrier in barrier_variants(spot, pair_kind, offset_pct):
                                left, right = await asyncio.gather(
                                    get_proposal(client, symbol, call_type, duration, duration_unit, barrier),
                                    get_proposal(client, symbol, put_type, duration, duration_unit, barrier),
                                )
                                left_prop, left_error = left
                                right_prop, right_error = right
                                record = {
                                    "ts": datetime.now(timezone.utc).isoformat(),
                                    "symbol": symbol,
                                    "duration": duration,
                                    "duration_unit": duration_unit,
                                    "round": round_num,
                                    "pair": pair_name,
                                    "left_type": call_type,
                                    "right_type": put_type,
                                    "barrier_side": barrier["side"],
                                    "barrier_requested": barrier["barrier"],
                                    "barrier2_requested": barrier.get("barrier2"),
                                    "offset_pct": offset_pct,
                                    "spot_reference": spot,
                                    "left_error": left_error,
                                    "right_error": right_error,
                                }
                                if left_prop and right_prop:
                                    left_ask = as_float(left_prop.get("ask_price"))
                                    right_ask = as_float(right_prop.get("ask_price"))
                                    left_payout = as_float(left_prop.get("payout"))
                                    right_payout = as_float(right_prop.get("payout"))
                                    total_ask = left_ask + right_ask
                                    min_payout = min(left_payout, right_payout)
                                    record.update({
                                        "left_ask": left_ask,
                                        "right_ask": right_ask,
                                        "left_payout": left_payout,
                                        "right_payout": right_payout,
                                        "left_spot": as_float(left_prop.get("spot")),
                                        "right_spot": as_float(right_prop.get("spot")),
                                        "left_longcode": left_prop.get("longcode"),
                                        "right_longcode": right_prop.get("longcode"),
                                        "total_ask": total_ask,
                                        "min_payout": min_payout,
                                        "guaranteed_spread": min_payout - total_ask,
                                        "is_raw_candidate": min_payout > total_ask,
                                    })
                                    print(
                                        f"{symbol} {pair_name} {duration}{duration_unit} "
                                        f"{barrier['side']} off={offset_pct:.4f}: "
                                        f"spread=${record['guaranteed_spread']:+.5f}"
                                    )
                                else:
                                    print(
                                        f"{symbol} {pair_name} {duration}{duration_unit} "
                                        f"{barrier['side']}: quote error"
                                    )
                                records.append(record)
                                append_jsonl(args.output, record)
                                await asyncio.sleep(args.delay)
    finally:
        await client.disconnect()

    valid = [r for r in records if "guaranteed_spread" in r]
    candidates = [r for r in valid if r["is_raw_candidate"]]
    by_pair = defaultdict(list)
    for record in valid:
        by_pair[record["pair"]].append(record["guaranteed_spread"])
    summary = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "n_records": len(records),
        "n_valid": len(valid),
        "n_errors": len(records) - len(valid),
        "n_raw_candidates": len(candidates),
        "min_spread": min((r["guaranteed_spread"] for r in valid), default=None),
        "max_spread": max((r["guaranteed_spread"] for r in valid), default=None),
        "mean_spread": (
            sum(r["guaranteed_spread"] for r in valid) / len(valid) if valid else None
        ),
        "by_pair": {
            pair: {
                "n": len(spreads),
                "min_spread": min(spreads),
                "mean_spread": sum(spreads) / len(spreads),
                "raw_candidates": sum(1 for value in spreads if value > 0),
            }
            for pair, spreads in sorted(by_pair.items())
        },
        "method": "read-only min(payout_left,payout_right) - ask_left - ask_right",
    }
    with open(args.stats, "w", encoding="utf-8") as handle:
        json.dump(summary, handle, indent=2, ensure_ascii=False, default=str)
    print("=" * 100)
    print(f"D87 summary: valid={len(valid)} raw_candidates={len(candidates)}")
    if valid:
        print(f"Spread min=${summary['min_spread']:+.5f} mean=${summary['mean_spread']:+.5f}")
    print(f"Results: {args.output}")
    print(f"Stats: {args.stats}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbols", default=",".join(DEFAULT_SYMBOLS))
    parser.add_argument("--durations", default=",".join(DEFAULT_DURATIONS))
    parser.add_argument("--pairs", default=",".join(PAIR_SPECS))
    parser.add_argument("--offset-pcts", default="0.005,0.01")
    parser.add_argument("--rounds", type=int, default=3)
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
