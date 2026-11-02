import argparse
import asyncio
import copy
import gzip
import json
import os
import sys
from datetime import datetime, timezone

from deriv_client import DerivClient
from rise_fall_youtube_strategy import (
    STRATEGIES,
    backtest_strategy,
    build_strategy_report,
    candles_from_dicts,
    candles_to_dicts,
    pooled_report,
)


PLAYLIST_URL = "https://youtube.com/playlist?list=PLID7aDmxAvGFK2lD6TZLaaNPxBnK4Yuak"
DEFAULT_SYMBOLS = "1HZ100V,R_100,1HZ50V"
DEFAULT_END = "1783999380"


def _cache_path(cache_dir, symbol, end):
    safe_end = str(end).replace(":", "-")
    return os.path.join(cache_dir, f"{symbol}_60s_{safe_end}.json.gz")


def _load_cache(path):
    if not os.path.exists(path):
        return []
    try:
        with gzip.open(path, "rt", encoding="utf-8") as handle:
            payload = json.load(handle)
        return candles_from_dicts(payload.get("candles", []))
    except (OSError, ValueError, KeyError):
        return []


def _save_cache(path, symbol, end, candles):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    payload = {
        "symbol": symbol,
        "granularity_seconds": 60,
        "requested_end": end,
        "retrieved_at": datetime.now(timezone.utc).isoformat(),
        "candles": candles_to_dicts(candles),
    }
    temporary = f"{path}.tmp"
    with gzip.open(temporary, "wt", encoding="utf-8") as handle:
        json.dump(payload, handle, separators=(",", ":"))
    os.replace(temporary, path)


async def _request_candle_page(client, symbol, count, end):
    last_error = None
    for attempt in range(5):
        try:
            response = await client.get_candles(
                symbol,
                count=count,
                granularity=60,
                end=end,
            )
            if "error" not in response:
                return response.get("candles", [])
            last_error = response["error"].get("message", str(response["error"]))
        except Exception as error:
            last_error = str(error)
        await asyncio.sleep(min(2 ** attempt, 8))
    raise RuntimeError(f"{symbol}: falha ao buscar candles: {last_error}")


async def fetch_candles(client, symbol, count, end, delay_seconds, existing=None):
    records = {candle.epoch: record for candle, record in zip(existing or [], candles_to_dicts(existing or []))}
    page_end = min(records) - 1 if records else end
    while len(records) < count:
        page_count = min(1000, count - len(records))
        page = await _request_candle_page(client, symbol, page_count, page_end)
        if not page:
            break
        for record in page:
            records[int(record["epoch"])] = record
        earliest = min(int(record["epoch"]) for record in page)
        page_end = earliest - 1
        print(f"  {symbol}: {len(records):,}/{count:,} candles", flush=True)
        if len(page) < page_count:
            break
        await asyncio.sleep(delay_seconds)
    return candles_from_dicts(records.values())[-count:]


def _parse_symbols(value):
    symbols = []
    for symbol in value.split(","):
        symbol = symbol.strip()
        if symbol and symbol not in symbols:
            symbols.append(symbol)
    if not symbols:
        raise ValueError("informe ao menos um simbolo")
    return symbols


def _strip_trades(report):
    output = copy.deepcopy(report)
    for symbol_report in output["symbols"].values():
        for strategy_report in symbol_report["strategies"].values():
            strategy_report.pop("trades", None)
    return output


def _write_json(path, payload):
    directory = os.path.dirname(os.path.abspath(path))
    os.makedirs(directory, exist_ok=True)
    temporary = f"{path}.tmp"
    with open(temporary, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    os.replace(temporary, path)


def _format_summary(report):
    lines = []
    lines.append("strategy                         N      WR      EV/stake       IC95% EV             verdict")
    lines.append("-" * 102)
    for spec in STRATEGIES:
        result = report["pooled_oos"][spec.name]["observed"]
        interval = result["ev_ci95"]
        lines.append(
            f"{spec.name:<32} {result['n']:>5}  {result['win_rate']*100:>6.2f}%  "
            f"{result['ev_per_stake']:>+10.4f}  "
            f"[{interval[0]:>+8.4f}, {interval[1]:>+8.4f}]  {result['verdict']}"
        )
    return "\n".join(lines)


async def run(args):
    symbols = _parse_symbols(args.symbols)
    cache_dir = os.path.abspath(args.cache_dir)
    candles_by_symbol = {}
    missing = []
    for symbol in symbols:
        path = _cache_path(cache_dir, symbol, args.end)
        cached = [] if args.refresh else _load_cache(path)
        if len(cached) < args.candles:
            missing.append((symbol, path, cached))
            if cached:
                print(f"  {symbol}: estendendo cache {len(cached):,} -> {args.candles:,}", flush=True)
        else:
            candles_by_symbol[symbol] = cached[-args.candles:]
            print(f"  {symbol}: cache {args.candles:,} candles", flush=True)
    if missing and args.offline:
        names = ", ".join(symbol for symbol, _, _ in missing)
        raise RuntimeError(f"cache ausente ou insuficiente em modo offline: {names}")
    if missing:
        client = DerivClient(app_id=args.app_id)
        await client.connect()
        try:
            for symbol, path, cached in missing:
                candles = await fetch_candles(
                    client,
                    symbol,
                    args.candles,
                    args.end,
                    args.delay_seconds,
                    existing=cached,
                )
                if len(candles) < args.candles:
                    raise RuntimeError(
                        f"{symbol}: retornou {len(candles):,}, esperado {args.candles:,} candles"
                    )
                _save_cache(path, symbol, args.end, candles)
                candles_by_symbol[symbol] = candles
        finally:
            await client.disconnect()
    symbol_reports = {}
    for symbol in symbols:
        candles = candles_by_symbol[symbol]
        split_index = int(len(candles) * args.in_sample_fraction)
        split_index = min(max(split_index, 1), len(candles) - 1)
        oos_start_epoch = candles[split_index].epoch
        strategy_reports = {}
        print(f"\n{symbol}: {len(candles):,} candles", flush=True)
        for spec in STRATEGIES:
            trades = backtest_strategy(candles, symbol, spec, payout=args.payout)
            strategy_reports[spec.name] = build_strategy_report(
                trades,
                oos_start_epoch=oos_start_epoch,
                seed=args.seed,
            )
            oos = strategy_reports[spec.name]["out_of_sample"]
            print(
                f"  {spec.name}: N_oos={oos['n']} WR={oos['win_rate']*100:.2f}% "
                f"EV={oos['ev_per_stake']:+.4f} {oos['verdict']}",
                flush=True,
            )
        symbol_reports[symbol] = {
            "data": {
                "n_candles": len(candles),
                "first_epoch": candles[0].epoch,
                "last_epoch": candles[-1].epoch,
                "oos_start_epoch": oos_start_epoch,
                "first_utc": datetime.fromtimestamp(candles[0].epoch, timezone.utc).isoformat(),
                "last_utc": datetime.fromtimestamp(candles[-1].epoch, timezone.utc).isoformat(),
                "oos_start_utc": datetime.fromtimestamp(oos_start_epoch, timezone.utc).isoformat(),
            },
            "strategies": strategy_reports,
        }
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "hypothesis_id": "D87",
        "source": {
            "playlist": PLAYLIST_URL,
            "channel": "Deriv Navigator Academy",
            "videos": 9,
            "duration_seconds": 3922,
            "caption_source": "YouTube automatic English captions",
        },
        "design": {
            "primary_strategy": "mtf_strict_15m",
            "primary_metric": "pooled out-of-sample EV per unit stake",
            "success_criterion": "N>=100 and bootstrap 95% EV CI entirely above zero",
            "entry_timing": "signal at 1m candle close; entry at next 1m candle open",
            "position_policy": "one position at a time per strategy and symbol",
            "controls": ["anti_signal", "random_direction"],
            "payout_multiple": args.payout,
            "break_even_win_rate": 1.0 / args.payout,
            "in_sample_fraction": args.in_sample_fraction,
            "seed": args.seed,
        },
        "symbols": symbol_reports,
        "pooled_oos": {},
    }
    for spec in STRATEGIES:
        report["pooled_oos"][spec.name] = pooled_report(
            symbol_reports,
            spec.name,
            split="out_of_sample",
            seed=args.seed,
        )
    serializable = report if args.include_trades else _strip_trades(report)
    _write_json(args.output, serializable)
    print("\n" + _format_summary(report), flush=True)
    print(f"\nResultado: {os.path.abspath(args.output)}", flush=True)
    return report


def build_parser():
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbols", default=DEFAULT_SYMBOLS)
    parser.add_argument("--candles", type=int, default=60000)
    parser.add_argument("--end", default=DEFAULT_END)
    parser.add_argument("--payout", type=float, default=1.96)
    parser.add_argument("--in-sample-fraction", type=float, default=0.70)
    parser.add_argument("--seed", type=int, default=20260713)
    parser.add_argument("--app-id", default="1089")
    parser.add_argument(
        "--cache-dir",
        default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "rise_fall_youtube"),
    )
    parser.add_argument(
        "--output",
        default=os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            "rise_fall_youtube_backtest_results.json",
        ),
    )
    parser.add_argument("--delay-seconds", type=float, default=0.25)
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--refresh", action="store_true")
    parser.add_argument("--include-trades", action="store_true")
    return parser


def main():
    try:
        asyncio.run(run(build_parser().parse_args()))
    except (RuntimeError, ValueError) as error:
        print(f"ERRO: {error}", file=sys.stderr)
        raise SystemExit(1) from error


if __name__ == "__main__":
    main()
