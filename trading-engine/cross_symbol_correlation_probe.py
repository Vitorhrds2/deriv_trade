"""
D56 — Cross-Symbol Tick Correlation Probe
==========================================
Hipotese: indices sinteticos "1Hz" (1HZ10V, 1HZ25V, 1HZ50V, 1HZ100V) e "R_"
(R_10, R_25, R_50, R_75, R_100) podem compartilhar estado de RNG ou ter ticks
correlacionados. Se 1HZ10V prediz 1HZ100V (ou R_10 prediz R_100) com lag
mensuravel, ha edge direcional gratis — comprar CALL/PUT no simbolo Atrasado
sabendo para onde o simbolo Adiantado ja foi.

D46 testou autocorrelacao DENTRO de um simbolo. Aqui testamos correlacao ENTRE
simbolos em varios lags.

Metodo:
  1. Subscrever ticks de todos os simbolos 1Hz e R_ simultaneamente via WS
  2. Registrar (symbol, quote, epoch, local_t) para cada tick
  3. A cada N ticks, computar cross-correlacao de retornos normalizados
     entre todos os pares em lags -5..+5
  4. Reportar pares com correlacao significativa (|r| > 0.1, p < 0.01)
  5. Se encontrado, testar ao vivo: comprar CALL no simbolo B quando simbolo A
     move UP, comparar WR vs 50%

Uso: python3 cross_symbol_correlation_probe.py
"""
import asyncio
import json
import math
import os
import statistics
import sys
import time
from collections import defaultdict, deque
from datetime import datetime, timezone

from dotenv import load_dotenv

for _p in [os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")]:
    if os.path.exists(_p):
        load_dotenv(_p)
        break

from deriv_client import DerivClient
from stats_utils import wilson_ci

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

APP_ID = os.getenv("DERIV_APP_ID")
TOKEN = os.getenv("DERIV_API_TOKEN")

SYMBOLS_1HZ = ["1HZ10V", "1HZ25V", "1HZ50V", "1HZ100V"]
SYMBOLS_R = ["R_10", "R_25", "R_50", "R_75", "R_100"]
ALL_SYMBOLS = SYMBOLS_1HZ + SYMBOLS_R

RESULTS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cross_symbol_correlation_results.jsonl")
STATS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cross_symbol_correlation_stats.json")

MAX_TICKS_PER_SYMBOL = 5000
ANALYSIS_INTERVAL_TICKS = 500
MAX_LAG = 5

tick_buffers = defaultdict(lambda: deque(maxlen=MAX_TICKS_PER_SYMBOL))
tick_count = 0


def on_tick_factory():
    def on_tick(data):
        global tick_count
        t = data.get("tick")
        if not t or "quote" not in t:
            return
        sym = t.get("symbol")
        q = float(t["quote"])
        epoch = int(t.get("epoch", 0))
        local_t = time.time()
        if sym:
            tick_buffers[sym].append({
                "quote": q,
                "epoch": epoch,
                "local_t": local_t,
            })
            tick_count += 1
    return on_tick


def compute_returns(quotes):
    if len(quotes) < 2:
        return []
    returns = []
    for i in range(1, len(quotes)):
        prev = quotes[i - 1]["quote"]
        curr = quotes[i]["quote"]
        if prev != 0:
            returns.append((curr - prev) / prev)
    return returns


def cross_correlate(rets_a, rets_b, max_lag=MAX_LAG):
    results = {}
    n = min(len(rets_a), len(rets_b))
    if n < 30:
        return results
    rets_a = rets_a[-n:]
    rets_b = rets_b[-n:]
    mean_a = statistics.mean(rets_a)
    mean_b = statistics.mean(rets_b)
    std_a = statistics.stdev(rets_a) if len(rets_a) > 1 else 1
    std_b = statistics.stdev(rets_b) if len(rets_b) > 1 else 1
    if std_a == 0 or std_b == 0:
        return results
    for lag in range(-max_lag, max_lag + 1):
        if lag == 0:
            a_slice = rets_a
            b_slice = rets_b
        elif lag > 0:
            a_slice = rets_a[:-lag] if lag < len(rets_a) else []
            b_slice = rets_b[lag:]
        else:
            a_slice = rets_a[-lag:]
            b_slice = rets_b[:lag] if lag < len(rets_b) else []
        m = min(len(a_slice), len(b_slice))
        if m < 30:
            continue
        a_slice = a_slice[-m:]
        b_slice = b_slice[-m:]
        cov = sum((a - mean_a) * (b - mean_b) for a, b in zip(a_slice, b_slice)) / m
        r = cov / (std_a * std_b)
        t_stat = r * math.sqrt(m - 2) / math.sqrt(1 - r * r) if abs(r) < 1 else 0
        p_value = 2 * (1 - _cdf_approx(abs(t_stat), m - 2))
        results[lag] = {"r": round(r, 4), "n": m, "t_stat": round(t_stat, 2), "p_value": round(p_value, 6)}
    return results


def _cdf_approx(t, df):
    if df <= 0:
        return 0.5
    x = t / math.sqrt(df + t * t)
    return 0.5 * (1 + x * (1 + x * x / 3) / math.sqrt(1 + x * x))


async def run_analysis():
    global tick_count
    all_pairs = []
    symbols_with_data = [s for s in ALL_SYMBOLS if len(tick_buffers[s]) > 50]
    if len(symbols_with_data) < 2:
        print(f"  [analysis] Apenas {len(symbols_with_data)} simbolos com dados suficientes, pulando...")
        return

    print(f"\n  [analysis] Analisando {len(symbols_with_data)} simbolos, {tick_count} ticks totais...")
    significant_pairs = []

    for i, sym_a in enumerate(symbols_with_data):
        for sym_b in symbols_with_data[i + 1:]:
            rets_a = compute_returns(list(tick_buffers[sym_a]))
            rets_b = compute_returns(list(tick_buffers[sym_b]))
            if len(rets_a) < 50 or len(rets_b) < 50:
                continue
            corr = cross_correlate(rets_a, rets_b)
            if not corr:
                continue
            best_lag = max(corr.keys(), key=lambda k: abs(corr[k]["r"]))
            best = corr[best_lag]
            pair_record = {
                "pair": f"{sym_a}->{sym_b}",
                "best_lag": best_lag,
                "best_r": best["r"],
                "n": best["n"],
                "p_value": best["p_value"],
                "all_lags": corr,
            }
            all_pairs.append(pair_record)
            if abs(best["r"]) > 0.05 and best["p_value"] < 0.05:
                significant_pairs.append(pair_record)
                direction = "A prediz B" if best_lag > 0 else "B prediz A" if best_lag < 0 else "simultaneo"
                print(f"    *** {sym_a} <-> {sym_b}: lag={best_lag} r={best['r']:+.4f} "
                      f"p={best['p_value']:.4f} N={best['n']} ({direction})")

    if not significant_pairs:
        top = sorted(all_pairs, key=lambda x: abs(x["best_r"]), reverse=True)[:5]
        for p in top:
            print(f"    {p['pair']}: lag={p['best_lag']} r={p['best_r']:+.4f} p={p['p_value']:.4f} N={p['n']}")
        print(f"  [analysis] Nenhuma correlacao significativa (|r|>0.05, p<0.05) em {len(all_pairs)} pares.")
    else:
        print(f"  [analysis] {len(significant_pairs)} pares com correlacao significativa!")

    stats = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "total_ticks": tick_count,
        "symbols_analyzed": len(symbols_with_data),
        "pairs_analyzed": len(all_pairs),
        "significant_pairs": len(significant_pairs),
        "top_pairs": sorted(all_pairs, key=lambda x: abs(x["best_r"]), reverse=True)[:10],
    }
    with open(STATS_FILE, "w") as f:
        json.dump(stats, f, indent=2)
    with open(RESULTS_FILE, "a") as f:
        f.write(json.dumps(stats) + "\n")


async def main():
    if not APP_ID:
        print("ERRO: DERIV_APP_ID nao encontrado.")
        return

    print("=" * 90)
    print(f"D56 — Cross-Symbol Tick Correlation Probe")
    print(f"  Symbols: {ALL_SYMBOLS}")
    print(f"  Max lag: {MAX_LAG} ticks | Analysis every {ANALYSIS_INTERVAL_TICKS} ticks")
    print("=" * 90)

    client = DerivClient(app_id=APP_ID, api_token=TOKEN, use_demo=True)
    await client.connect()
    print(f"  Conectado. Conta: {client.account_id}")

    await client.subscribe_ticks(ALL_SYMBOLS[0], on_tick_factory())
    await asyncio.sleep(1)
    for sym in ALL_SYMBOLS[1:]:
        await client.send_request({"ticks": sym, "subscribe": 1})
        await asyncio.sleep(0.3)

    print(f"  Subscrito a {len(ALL_SYMBOLS)} simbolos. Coletando ticks...\n")

    try:
        last_analysis = 0
        while True:
            await asyncio.sleep(5)
            if tick_count - last_analysis >= ANALYSIS_INTERVAL_TICKS:
                last_analysis = tick_count
                await run_analysis()
    except KeyboardInterrupt:
        print("\n  Parando...")
        await run_analysis()

    await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
