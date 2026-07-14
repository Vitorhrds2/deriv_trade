"""D103 — Tick Arrival Timing Prediction.

Hipotese
--------
Para indices sinteticos 1HZ (1 tick/segundo) e R_ (1 tick/~2s), o timing exato
de chegada dos ticks pode ser previsivel. Se podemos prever QUANDO o proximo
tick chegara (nao QUAL valor), podemos comprar no momento otimo.

Testa:
  1. Subscrever ticks por 15 min para cada simbolo
  2. Medir distribuicao de intervalos entre ticks (epoch timestamps)
  3. Calcular autocorrelacao de intervalos
  4. Testar se intervalos sao Poisson (exponencial) vs deterministico
  5. Medir jitter (desvio do intervalo mediano)

Uso
---
    python d103_tick_timing_prediction.py --duration-min 15
"""
import argparse
import asyncio
import json
import math
import os
import statistics
import sys
import time
from collections import defaultdict, deque
from datetime import datetime, timezone

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from deriv_client import DerivClient

APP_ID = os.getenv("DERIV_APP_ID", "1089")
TOKEN = os.getenv("DERIV_API_TOKEN", "")

DEFAULT_SYMBOLS = ["1HZ10V", "1HZ50V", "1HZ100V", "R_10", "R_100", "cryBTCUSD"]

tick_buffers = defaultdict(lambda: deque(maxlen=10000))
tick_count = 0


def on_tick_factory():
    def on_tick(data):
        global tick_count
        t = data.get("tick")
        if not t or "quote" not in t:
            return
        sym = t.get("symbol")
        epoch = int(t.get("epoch", 0))
        local_t = time.time()
        if sym:
            tick_buffers[sym].append({
                "epoch": epoch,
                "local_t": local_t,
                "quote": float(t["quote"]),
            })
            tick_count += 1
    return on_tick


def autocorrelation(values, max_lag=20):
    n = len(values)
    if n < max_lag + 10:
        return {}
    mean = statistics.mean(values)
    var = statistics.variance(values) if n > 1 else 1.0
    if var == 0:
        return {}
    results = {}
    for lag in range(1, max_lag + 1):
        cov = sum((values[i] - mean) * (values[i - lag] - mean) for i in range(lag, n)) / (n - lag)
        results[lag] = cov / var
    return results


def is_exponential(intervals):
    if not intervals:
        return None
    mean = statistics.mean(intervals)
    std = statistics.stdev(intervals) if len(intervals) > 1 else 0
    if mean == 0:
        return None
    cv = std / mean
    return {"mean": mean, "std": std, "cv": cv, "is_poisson": 0.9 < cv < 1.1}


async def main():
    parser = argparse.ArgumentParser(description="D103 Tick Arrival Timing Prediction")
    parser.add_argument("--symbols", default=",".join(DEFAULT_SYMBOLS))
    parser.add_argument("--duration-min", type=int, default=15)
    parser.add_argument("--output", default="d103_tick_timing_results.json")
    parser.add_argument("--app-id", default=os.getenv("DERIV_APP_ID", "1089"))
    parser.add_argument("--api-token", default=os.getenv("DERIV_API_TOKEN", ""))
    args = parser.parse_args()

    if not args.api_token:
        print("ERROR: DERIV_API_TOKEN required", flush=True)
        return

    symbols = [s.strip() for s in args.symbols.split(",") if s.strip()]
    duration_s = args.duration_min * 60

    print(f"D103 — Tick Arrival Timing Prediction", flush=True)
    print(f"Symbols: {symbols} | Duration: {args.duration_min}min", flush=True)

    client = DerivClient(app_id=args.app_id, api_token=args.api_token, use_demo=True)
    await client.connect()
    await asyncio.sleep(2)

    # Subscribe using callback pattern (same as D56)
    await client.subscribe_ticks(symbols[0], on_tick_factory())
    await asyncio.sleep(1)
    for sym in symbols[1:]:
        await client.send_request({"ticks": sym, "subscribe": 1})
        await asyncio.sleep(0.3)

    print(f"  Subscribed to {len(symbols)} symbols. Collecting ticks...", flush=True)

    # Collect ticks
    start_time = time.time()
    end_time = start_time + duration_s
    last_report = start_time

    while time.time() < end_time:
        await asyncio.sleep(5)
        if time.time() - last_report > 60:
            last_report = time.time()
            for sym in symbols:
                n = len(tick_buffers[sym])
                print(f"  [{int(time.time() - start_time)}s] {sym}: {n} ticks", flush=True)

    # Unsubscribe
    try:
        await client.send_request({"forget_all": "ticks"})
    except Exception:
        pass

    await client.disconnect()

    # Analysis
    print(f"\n=== ANALYSIS ===", flush=True)
    results = {}
    for sym in symbols:
        data = list(tick_buffers[sym])

        if len(data) < 100:
            print(f"  {sym}: insufficient ticks ({len(data)})", flush=True)
            results[sym] = {"n_ticks": len(data), "error": "insufficient_ticks"}
            continue

        epochs = [d["epoch"] for d in data]
        local_times = [d["local_t"] for d in data]

        # Server-side intervals (epoch-based)
        server_intervals = [epochs[i] - epochs[i - 1] for i in range(1, len(epochs))]
        server_intervals_clean = [x for x in server_intervals if 0 < x < 10]

        # Client-side intervals
        client_intervals = [local_times[i] - local_times[i - 1] for i in range(1, len(local_times))]
        client_intervals_clean = [x for x in client_intervals if 0 < x < 10]

        server_stats = is_exponential(server_intervals_clean)

        # Autocorrelation
        server_acf = autocorrelation(server_intervals_clean, max_lag=10)

        # Tick rate
        total_time = epochs[-1] - epochs[0]
        tick_rate = len(epochs) / total_time if total_time > 0 else 0

        # Interval distribution
        interval_counts = {}
        for iv in server_intervals_clean:
            rounded = round(iv, 1)
            interval_counts[rounded] = interval_counts.get(rounded, 0) + 1
        sorted_intervals = sorted(interval_counts.items(), key=lambda x: -x[1])[:5]

        # Jitter
        median_interval = statistics.median(server_intervals_clean)
        jitters = [abs(iv - median_interval) for iv in server_intervals_clean]
        mean_jitter = statistics.mean(jitters) if jitters else 0
        max_jitter = max(jitters) if jitters else 0

        result = {
            "n_ticks": len(epochs),
            "total_time_s": total_time,
            "tick_rate": round(tick_rate, 4),
            "server_intervals": {
                "mean": round(server_stats["mean"], 4) if server_stats else None,
                "std": round(server_stats["std"], 4) if server_stats else None,
                "cv": round(server_stats["cv"], 4) if server_stats else None,
                "is_poisson": server_stats["is_poisson"] if server_stats else None,
                "median": round(median_interval, 4),
                "mean_jitter": round(mean_jitter, 6),
                "max_jitter": round(max_jitter, 6),
            },
            "top_intervals": [(str(k), v) for k, v in sorted_intervals],
            "autocorrelation": {str(k): round(v, 4) for k, v in server_acf.items()},
            "max_autocorr": max(abs(v) for v in server_acf.values()) if server_acf else 0,
        }
        results[sym] = result

        print(f"\n  {sym}:", flush=True)
        print(f"    N={len(epochs)} ticks over {total_time:.1f}s ({tick_rate:.2f} ticks/s)", flush=True)
        if server_stats:
            print(f"    Server intervals: mean={server_stats['mean']:.4f}s std={server_stats['std']:.4f}s "
                  f"CV={server_stats['cv']:.4f} (Poisson={server_stats['is_poisson']})", flush=True)
        print(f"    Median={median_interval:.4f}s jitter_mean={mean_jitter:.6f}s jitter_max={max_jitter:.6f}s", flush=True)
        print(f"    Top intervals: {sorted_intervals[:3]}", flush=True)
        print(f"    Max |ACF|={result['max_autocorr']:.4f} (lags 1-10)", flush=True)

        if server_acf:
            significant_acf = {k: v for k, v in server_acf.items() if abs(v) > 0.1}
            if significant_acf:
                print(f"    *** Significant ACF (>0.1): {significant_acf}", flush=True)
            else:
                print(f"    No significant autocorrelation — intervals are independent", flush=True)

        # Verdict
        if server_stats and server_stats["is_poisson"]:
            print(f"    VERDICT: Poisson process — timing NOT predictable", flush=True)
        elif result["max_autocorr"] > 0.2:
            print(f"    VERDICT: Timing pattern detected — may be exploitable", flush=True)
        elif mean_jitter < 0.01 * median_interval:
            print(f"    VERDICT: Highly regular (deterministic) — predictable timing", flush=True)
        else:
            print(f"    VERDICT: No exploitable timing pattern", flush=True)

    output = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "hypothesis": "D103",
        "description": "Tick arrival timing prediction",
        "symbols": symbols,
        "duration_min": args.duration_min,
        "results": results,
    }

    with open(args.output, "w") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)
    print(f"\nResults saved to {args.output}", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
