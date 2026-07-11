"""
D68 — Tick Arrival Jitter Probe
================================
Hipotese: Ticks sinteticos chegam a exatamente 1 segundo de intervalo?
D60 testou ticks faltantes (gap detection), mas nao jitter sub-segundo.
Se ha jitter no relogio de geracao de ticks, voce pode prever quando o
proximo tick chega e timingar o buy para capturar entry_spot favoravel.

Metodo:
  1. Subscrever ticks de 1HZ10V por 10 minutos
  2. Registrar timestamp local preciso de cada tick recebido
  3. Calcular inter-arrival times (delta entre ticks consecutivos)
  4. Verificar se sao exatamente 1.000s ou ha jitter
  5. Se ha jitter, verificar se e autocorrelacionado (previsivel)
  6. Registrar epoch do tick vs timestamp local para medir latencia

Uso: python3 tick_arrival_jitter_probe.py [--duration=600]
"""
import argparse
import asyncio
import json
import os
import sys
import time
import statistics
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

SYMBOL = "1HZ10V"

RESULTS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tick_arrival_jitter_results.jsonl")
STATS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tick_arrival_jitter_stats.json")

tick_log = []


def on_tick(data):
    t = data.get("tick")
    if not t or "quote" not in t:
        return
    local_ts = time.time()
    tick_log.append({
        "quote": float(t["quote"]),
        "epoch": int(t.get("epoch", 0)),
        "local_ts": local_ts,
        "local_ts_str": datetime.now(timezone.utc).isoformat(),
    })


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--duration", type=int, default=600, help="Duracao em segundos (default 600 = 10min)")
    args = parser.parse_args()

    if not APP_ID:
        print("ERRO: DERIV_APP_ID nao encontrado.")
        return

    print("=" * 90)
    print(f"D68 — Tick Arrival Jitter Probe")
    print(f"  Symbol: {SYMBOL} | Duration: {args.duration}s ({args.duration/60:.0f}min)")
    print("=" * 90)

    client = DerivClient(app_id=APP_ID, api_token=TOKEN, use_demo=True)
    await client.connect()
    print(f"  Conectado. Conta: {client.account_id}")

    await client.subscribe_ticks(SYMBOL, on_tick)
    print(f"  Subscrito a {SYMBOL}. Coletando ticks por {args.duration}s...")
    await asyncio.sleep(args.duration)

    await client.send_request({"forget_all": "ticks"})
    print(f"  Coleta finalizada. {len(tick_log)} ticks recebidos.")

    if len(tick_log) < 10:
        print("  ERRO: Ticks insuficientes para analise.")
        await client.disconnect()
        return

    inter_arrivals = []
    epoch_diffs = []
    latencies = []

    for i in range(1, len(tick_log)):
        delta_local = tick_log[i]["local_ts"] - tick_log[i-1]["local_ts"]
        delta_epoch = tick_log[i]["epoch"] - tick_log[i-1]["epoch"]
        inter_arrivals.append(delta_local)
        epoch_diffs.append(delta_epoch)

        latency = tick_log[i]["local_ts"] - tick_log[i]["epoch"]
        latencies.append(latency)

    print(f"\n{'='*80}")
    print(f"  ANALISE FINAL")
    print(f"{'='*80}")

    print(f"\n  Inter-arrival times (local timestamp):")
    print(f"    N: {len(inter_arrivals)}")
    print(f"    Mean: {statistics.mean(inter_arrivals):.6f}s")
    print(f"    Median: {statistics.median(inter_arrivals):.6f}s")
    print(f"    Std: {statistics.stdev(inter_arrivals):.6f}s")
    print(f"    Min: {min(inter_arrivals):.6f}s")
    print(f"    Max: {max(inter_arrivals):.6f}s")

    near_1s = sum(1 for d in inter_arrivals if 0.95 <= d <= 1.05)
    print(f"    Dentro de [0.95, 1.05]s: {near_1s}/{len(inter_arrivals)} ({near_1s/len(inter_arrivals)*100:.1f}%)")

    jitter = [d - 1.0 for d in inter_arrivals if 0.5 <= d <= 1.5]
    if jitter:
        print(f"\n  Jitter (delta - 1.0s, apenas deltas proximos a 1s):")
        print(f"    N: {len(jitter)}")
        print(f"    Mean: {statistics.mean(jitter)*1000:.3f}ms")
        print(f"    Std: {statistics.stdev(jitter)*1000:.3f}ms")
        print(f"    Min: {min(jitter)*1000:.3f}ms")
        print(f"    Max: {max(jitter)*1000:.3f}ms")

    print(f"\n  Epoch diffs (server-side):")
    print(f"    Mean: {statistics.mean(epoch_diffs):.3f}s")
    print(f"    Std: {statistics.stdev(epoch_diffs):.3f}s")
    print(f"    Unique values: {sorted(set(epoch_diffs))[:10]}")

    print(f"\n  Latencia (local_ts - epoch):")
    print(f"    Mean: {statistics.mean(latencies)*1000:.1f}ms")
    print(f"    Median: {statistics.median(latencies)*1000:.1f}ms")
    print(f"    Std: {statistics.stdev(latencies)*1000:.1f}ms")
    print(f"    Min: {min(latencies)*1000:.1f}ms")
    print(f"    Max: {max(latencies)*1000:.1f}ms")

    if len(inter_arrivals) >= 20:
        lag1_autocorr = 0
        mean_ia = statistics.mean(inter_arrivals)
        num = sum((inter_arrivals[i] - mean_ia) * (inter_arrivals[i+1] - mean_ia) for i in range(len(inter_arrivals)-1))
        den = sum((d - mean_ia) ** 2 for d in inter_arrivals)
        if den > 0:
            lag1_autocorr = num / den
        print(f"\n  Autocorrelacao lag-1 dos inter-arrivals: {lag1_autocorr:.4f}")
        if abs(lag1_autocorr) > 0.2:
            print(f"    *** Jitter e AUTOCORRELACIONADO — pode ser previsivel!")
        else:
            print(f"    Jitter nao e autocorrelacionado — e ruido branco.")

    std_ms = statistics.stdev(inter_arrivals) * 1000 if len(inter_arrivals) > 1 else 0
    if std_ms < 50:
        print(f"\n  CONCLUSAO: Ticks chegam com jitter < {std_ms:.1f}ms (muito regular).")
        print(f"  Nao ha jitter previsivel para explorar no timing do buy.")
    elif std_ms < 200:
        print(f"\n  CONCLUSAO: Jitter moderado ({std_ms:.1f}ms) — provavelmente ruido de rede.")
        print(f"  Dificil de explorar para timing de buy.")
    else:
        print(f"\n  CONCLUSAO: Jitter alto ({std_ms:.1f}ms) — investigar se e previsivel.")

    with open(RESULTS_FILE, "w") as f:
        for t in tick_log:
            f.write(json.dumps(t) + "\n")

    stats = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "n_ticks": len(tick_log),
        "duration_s": args.duration,
        "inter_arrival": {
            "mean": statistics.mean(inter_arrivals),
            "median": statistics.median(inter_arrivals),
            "std": statistics.stdev(inter_arrivals) if len(inter_arrivals) > 1 else 0,
            "min": min(inter_arrivals),
            "max": max(inter_arrivals),
        },
        "epoch_diffs": {
            "mean": statistics.mean(epoch_diffs),
            "std": statistics.stdev(epoch_diffs) if len(epoch_diffs) > 1 else 0,
            "unique": sorted(set(epoch_diffs))[:10],
        },
        "latency_ms": {
            "mean": statistics.mean(latencies) * 1000,
            "median": statistics.median(latencies) * 1000,
            "std": statistics.stdev(latencies) * 1000 if len(latencies) > 1 else 0,
            "min": min(latencies) * 1000,
            "max": max(latencies) * 1000,
        },
    }
    with open(STATS_FILE, "w") as f:
        json.dump(stats, f, indent=2, default=str)
    print(f"\n  Stats salvas em {STATS_FILE}")

    await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
