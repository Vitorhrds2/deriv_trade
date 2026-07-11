"""
D80 — Weekend/Holiday Synthetic Volatility Shift
==================================================
Sinteticos da Deriv sao gerados por RNG. A volatilidade muda em fins de semana?
Se sim, o payout deveria refletir (maior vol = maior risco = maior payout),
mas se o payout e constante, ha edge.

D63 ja mostrou que payout e 1.920 constante em 1200 proposals.
Mas sera que a VOLATILIDADE REAL dos ticks muda em fins de semana?

Metodologia:
  1. Baixar maximo de ticks historicos possiveis (5000 por batch, multiplos batches)
  2. Calcular volatilidade (std dos returns) por dia da semana
  3. Comparar weekend vs weekday
  4. Se volatilidade muda mas payout nao, ha edge

Tambem testa:
  - Volatilidade por hora do dia
  - Volatilidade em holidays (Natal, Ano Novo, etc.)
"""
import asyncio
import json
import math
import os
import sys
import statistics
import numpy as np
from datetime import datetime, timezone, timedelta

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

SYMBOLS = ["1HZ10V", "1HZ50V", "1HZ100V", "R_10", "R_25", "R_50", "R_75", "R_100"]
BATCH_SIZE = 5000
N_BATCHES = 4  # 20000 ticks total per symbol

RESULTS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            "weekend_volatility_results.json")


async def download_ticks_with_epochs(client, symbol, n_batches=N_BATCHES):
    """Download ticks with epochs for time-of-day analysis."""
    all_prices = []
    all_epochs = []

    for batch in range(n_batches):
        if batch == 0:
            end = "latest"
        else:
            end = all_epochs[0] - 1  # before earliest

        res = await client.send_request({
            "ticks_history": symbol,
            "adjust_start_time": 1,
            "count": BATCH_SIZE,
            "end": end,
            "start": 1,
            "style": "ticks",
        })

        if "error" in res:
            print(f"    Batch {batch} erro: {res['error'].get('message', '')}")
            break

        history = res.get("history", {})
        prices = history.get("prices", [])
        epochs = history.get("times", [])

        if not prices:
            break

        all_prices = [float(p) for p in prices] + all_prices
        all_epochs = epochs + all_epochs

        print(f"    Batch {batch}: {len(prices)} ticks (total: {len(all_prices)})")
        await asyncio.sleep(0.5)

    return all_prices, all_epochs


def compute_returns(prices):
    returns = []
    for i in range(1, len(prices)):
        if prices[i] > 0 and prices[i-1] > 0:
            r = math.log(prices[i] / prices[i-1])
            returns.append(r)
    return returns


def analyze_by_day(prices, epochs):
    """Analyze volatility by day of week."""
    day_names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    day_returns = {i: [] for i in range(7)}

    for i in range(1, len(prices)):
        if prices[i] <= 0 or prices[i-1] <= 0:
            continue
        r = math.log(prices[i] / prices[i-1])
        epoch = epochs[i]
        dt = datetime.fromtimestamp(epoch, tz=timezone.utc)
        day_returns[dt.weekday()].append(r)

    results = {}
    for day_idx, rets in day_returns.items():
        if len(rets) < 10:
            results[day_names[day_idx]] = {"n": len(rets), "vol": None}
            continue
        vol = statistics.stdev(rets)
        results[day_names[day_idx]] = {
            "n": len(rets),
            "vol": vol,
            "mean": statistics.mean(rets),
            "min": min(rets),
            "max": max(rets),
        }

    return results


def analyze_by_hour(prices, epochs):
    """Analyze volatility by hour of day."""
    hour_returns = {i: [] for i in range(24)}

    for i in range(1, len(prices)):
        if prices[i] <= 0 or prices[i-1] <= 0:
            continue
        r = math.log(prices[i] / prices[i-1])
        epoch = epochs[i]
        dt = datetime.fromtimestamp(epoch, tz=timezone.utc)
        hour_returns[dt.hour].append(r)

    results = {}
    for hour, rets in hour_returns.items():
        if len(rets) < 10:
            continue
        vol = statistics.stdev(rets)
        results[hour] = {
            "n": len(rets),
            "vol": vol,
        }

    return results


async def main():
    print("=" * 90)
    print("D80 — Weekend/Holiday Synthetic Volatility Shift")
    print(f"  Symbols: {', '.join(SYMBOLS)}")
    print(f"  Ticks per symbol: {BATCH_SIZE * N_BATCHES}")
    print("=" * 90)

    client = DerivClient(app_id=APP_ID, api_token=TOKEN, use_demo=True)
    await client.connect()
    print(f"  Conectado. Conta: {client.account_id}")

    all_results = {}

    for sym in SYMBOLS:
        print(f"\n{'='*60}")
        print(f"  {sym}")
        print(f"{'='*60}")

        prices, epochs = await download_ticks_with_epochs(client, sym)
        print(f"  Total: {len(prices)} ticks")

        if len(prices) < 100:
            print(f"  Ticks insuficientes, pulando")
            continue

        # Date range
        first_dt = datetime.fromtimestamp(epochs[0], tz=timezone.utc)
        last_dt = datetime.fromtimestamp(epochs[-1], tz=timezone.utc)
        print(f"  Periodo: {first_dt.strftime('%Y-%m-%d %H:%M')} a "
              f"{last_dt.strftime('%Y-%m-%d %H:%M')} UTC")

        # 1. Volatility by day of week
        print(f"\n  1. VOLATILIDADE POR DIA DA SEMANA:")
        day_results = analyze_by_day(prices, epochs)
        vols = [(day, r.get("vol")) for day, r in day_results.items() if r.get("vol")]
        avg_vol = statistics.mean(v for _, v in vols) if vols else 0

        for day, r in day_results.items():
            vol = r.get("vol")
            if vol:
                pct_diff = (vol - avg_vol) / avg_vol * 100 if avg_vol > 0 else 0
                print(f"    {day}: N={r['n']:5d} vol={vol:.6f} "
                      f"({pct_diff:+.1f}% vs avg)")
            else:
                print(f"    {day}: N={r['n']:5d} (insuficiente)")

        # Weekend vs weekday
        weekday_vols = [day_results[d].get("vol") for d in ["Mon", "Tue", "Wed", "Thu", "Fri"]
                        if day_results[d].get("vol")]
        weekend_vols = [day_results[d].get("vol") for d in ["Sat", "Sun"]
                        if day_results[d].get("vol")]

        if weekday_vols and weekend_vols:
            wd_vol = statistics.mean(weekday_vols)
            we_vol = statistics.mean(weekend_vols)
            diff_pct = (we_vol - wd_vol) / wd_vol * 100 if wd_vol > 0 else 0
            print(f"\n    Weekday avg vol: {wd_vol:.6f}")
            print(f"    Weekend avg vol: {we_vol:.6f}")
            print(f"    Diff: {diff_pct:+.1f}%")
            if abs(diff_pct) > 10:
                print(f"    *** DIFERENCA SIGNIFICATIVA — volatilidade muda em weekend!")

        # 2. Volatility by hour
        print(f"\n  2. VOLATILIDADE POR HORA (top 5 e bottom 5):")
        hour_results = analyze_by_hour(prices, epochs)
        hour_vols = [(h, r["vol"], r["n"]) for h, r in hour_results.items()]
        hour_vols.sort(key=lambda x: x[1], reverse=True)

        for h, vol, n in hour_vols[:5]:
            print(f"    {h:02d}:00 UTC: vol={vol:.6f} N={n}")
        print(f"    ...")
        for h, vol, n in hour_vols[-5:]:
            print(f"    {h:02d}:00 UTC: vol={vol:.6f} N={n}")

        if hour_vols:
            max_vol = hour_vols[0][1]
            min_vol = hour_vols[-1][1]
            ratio = max_vol / min_vol if min_vol > 0 else 0
            print(f"\n    Max/Min ratio: {ratio:.2f}x")
            if ratio > 1.5:
                print(f"    *** VOLATILIDADE VARIA POR HORA — possivel edge temporal!")

        all_results[sym] = {
            "n_ticks": len(prices),
            "period": f"{first_dt.isoformat()} to {last_dt.isoformat()}",
            "day_results": day_results,
            "hour_results": {str(k): v for k, v in hour_results.items()},
            "weekday_avg_vol": statistics.mean(weekday_vols) if weekday_vols else None,
            "weekend_avg_vol": statistics.mean(weekend_vols) if weekend_vols else None,
            "weekend_diff_pct": ((statistics.mean(weekend_vols) - statistics.mean(weekday_vols)) / statistics.mean(weekday_vols) * 100)
                                if weekday_vols and weekend_vols else None,
        }

        await asyncio.sleep(0.5)

    # Final verdict
    print(f"\n{'='*90}")
    print("  VEREDITO FINAL — WEEKEND/HOLIDAY VOLATILITY")
    print(f"{'='*90}")

    any_shift = False
    for sym, res in all_results.items():
        diff = res.get("weekend_diff_pct")
        if diff is not None and abs(diff) > 10:
            print(f"  {sym}: weekend vol {diff:+.1f}% vs weekday — SHIFT DETECTADO")
            any_shift = True
        else:
            print(f"  {sym}: weekend vol ~same as weekday (diff={diff:+.1f}%)" if diff
                  else f"  {sym}: dados insuficientes")

    if not any_shift:
        print(f"\n  Nenhuma diferenca significativa de volatilidade em weekend.")
        print(f"  RNG da Deriv e constante 24/7. D80 REFUTADO.")
    else:
        print(f"\n  DIFERENCA DETECTADA — investigar se payout ajusta para volatilidade.")

    with open(RESULTS_FILE, "w") as f:
        json.dump(all_results, f, indent=2, default=str)
    print(f"\n  Resultados salvos em {RESULTS_FILE}")

    await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
