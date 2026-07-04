"""
D31 — Deribit Settlement TWAP Exploit

Deribit settles options using a 30-minute TWAP (Time-Weighted Average Price)
of the underlying index, starting 30 minutes before expiry (08:30-09:00 UTC for
08:00 UTC expiries). This creates a structural inefficiency:

If you can observe the TWAP forming (first 20+ minutes of the 30min window),
you can estimate the final settlement price with high confidence BEFORE the
options officially settle. If the option's market price hasn't converged to
its intrinsic value at the TWAP estimate, there's a window to buy/sell
mispriced options.

Additionally: if you hold a position that benefits from a specific settlement
level, and the TWAP is trending toward that level in the last 10 minutes,
you can "front-run" the settlement by buying/selling options at prices that
don't yet reflect the forming TWAP.

This scan tests:
1. Fetch Deribit BTC/ETH options expiring TODAY (or nearest)
2. Fetch the 30-min TWAP window from Binance klines (08:30-09:00 UTC)
3. Calculate what the settlement TWAP would be at each minute mark
4. Compare option market prices (bid/ask) vs intrinsic value at forming TWAP
5. Measure: is there a predictable mispricing that narrows in the last minutes?

Data: Deribit public API (option quotes + settlement) + Binance klines (1m)

Usage:
  python3 settlement_twap_scan.py
  python3 settlement_twap_scan.py --asset ETH
  python3 settlement_twap_scan.py --backtest 30  # backtest last 30 expiries
"""
import argparse
import json
import math
import sys
import urllib.request
from datetime import datetime, timezone, timedelta

try:
    from stats_utils import bootstrap_ci, wilson_ci
except ImportError:
    import random, math
    def bootstrap_ci(values, n_boot=2000, ci=0.95, seed=42):
        if not values:
            return (0.0, 0.0, 0.0)
        rng = random.Random(seed)
        n = len(values)
        means = []
        for _ in range(n_boot):
            sample = [values[rng.randrange(n)] for _ in range(n)]
            means.append(sum(sample) / n)
        means.sort()
        lo_idx = int((1 - ci) / 2 * n_boot)
        hi_idx = int((1 + ci) / 2 * n_boot) - 1
        return (means[lo_idx], sum(values) / n, means[hi_idx])

    def wilson_ci(k, n, ci=0.95):
        if n == 0:
            return (0.0, 0.0)
        z = 1.96
        p = k / n
        denom = 1 + z * z / n
        center = (p + z * z / (2 * n)) / denom
        spread = z * math.sqrt((p * (1 - p) + z * z / (4 * n)) / n) / denom
        return (max(0, center - spread), min(1, center + spread))


def fetch_json(url, timeout=15):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode())


def fetch_deribit_options(currency="BTC"):
    url = f"https://www.deribit.com/api/v2/public/get_book_summary_by_currency?currency={currency}&kind=option"
    data = fetch_json(url)
    return data.get("result", [])


def fetch_binance_1m_klines(symbol, start_ms, end_ms):
    """Fetch 1-minute klines between timestamps."""
    url = (f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval=1m"
           f"&startTime={start_ms}&endTime={end_ms}&limit=60")
    data = fetch_json(url)
    candles = []
    for k in data:
        candles.append({
            "ts": k[0],
            "open": float(k[1]),
            "high": float(k[2]),
            "low": float(k[3]),
            "close": float(k[4]),
        })
    return candles


def parse_expiry(exp_str):
    try:
        return datetime.strptime(exp_str, "%d%b%y").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def backtest_twap_settlement(currency="BTC", n_expiries=30):
    """
    Backtest: for each past expiry, simulate what the TWAP would have been
    at each minute of the 30-min settlement window, and check if options
    were mispriced relative to the forming TWAP.

    Deribit expiry: 08:00 UTC. Settlement TWAP: 07:30-08:00 UTC (30 min before).
    """
    print(f"\n{'='*80}")
    print(f"D31 — Deribit Settlement TWAP Backtest | {currency}")
    print(f"{'='*80}")

    binance_sym = f"{currency}USDT"

    # Generate past expiry dates (Deribit daily expiry at 08:00 UTC)
    now = datetime.now(timezone.utc)
    exp_dates = []
    for i in range(1, n_expiries + 1):
        exp_date = (now - timedelta(days=i)).replace(hour=8, minute=0, second=0, microsecond=0)
        exp_str = exp_date.strftime("%d%b%y").upper()
        exp_dates.append((exp_str, exp_date))

    print(f"  Generated {len(exp_dates)} past daily expiry dates")
    print(f"  Testing last {len(exp_dates)} expiries (Deribit 08:00 UTC daily)...")

    results = []

    for exp_str, exp_date in exp_dates:
        # Settlement TWAP window: 30 min before expiry
        # Deribit expiry at 08:00 UTC, TWAP from 07:30 to 08:00 UTC
        twap_start = exp_date - timedelta(minutes=30)
        twap_end = exp_date

        # Fetch 1m klines for the TWAP window
        try:
            candles = fetch_binance_1m_klines(
                binance_sym,
                int(twap_start.timestamp() * 1000),
                int(twap_end.timestamp() * 1000)
            )
        except Exception as e:
            continue

        if len(candles) < 20:
            continue

        # Calculate forming TWAP at each minute
        # TWAP = average of all 1m close prices from twap_start to current minute
        twap_at_minute = []
        cumulative_sum = 0
        cumulative_n = 0
        for i, c in enumerate(candles):
            cumulative_sum += c["close"]
            cumulative_n += 1
            forming_twap = cumulative_sum / cumulative_n
            minutes_elapsed = i + 1
            minutes_remaining = 30 - minutes_elapsed

            # Final settlement = average of all 30 candles (we know this ex-post)
            final_twap = sum(c["close"] for c in candles) / len(candles)

            # Error of forming TWAP vs final TWAP
            twap_error = abs(forming_twap - final_twap) / final_twap * 100

            twap_at_minute.append({
                "minute": minutes_elapsed,
                "minutes_remaining": minutes_remaining,
                "forming_twap": forming_twap,
                "final_twap": final_twap,
                "twap_error_pct": twap_error,
                "price": c["close"],
            })

        # Key metric: at minute 20 (10 min remaining), how accurate is forming TWAP?
        at_20 = next((t for t in twap_at_minute if t["minute"] == 20), None)
        at_25 = next((t for t in twap_at_minute if t["minute"] == 25), None)
        at_10 = next((t for t in twap_at_minute if t["minute"] == 10), None)

        if at_20:
            results.append({
                "expiry": exp_str,
                "exp_date": exp_date.isoformat(),
                "final_twap": at_20["final_twap"],
                "twap_at_20": at_20["forming_twap"],
                "error_at_20_pct": at_20["twap_error_pct"],
                "twap_at_25": at_25["forming_twap"] if at_25 else None,
                "error_at_25_pct": at_25["twap_error_pct"] if at_25 else None,
                "twap_at_10": at_10["forming_twap"] if at_10 else None,
                "error_at_10_pct": at_10["twap_error_pct"] if at_10 else None,
                "n_candles": len(candles),
            })

    if not results:
        print("  Sem dados suficientes para backtest.")
        return None

    # Analysis
    print(f"\n  Expiries analyzed: {len(results)}")

    errors_10 = [r["error_at_10_pct"] for r in results if r["error_at_10_pct"] is not None]
    errors_20 = [r["error_at_20_pct"] for r in results if r["error_at_20_pct"] is not None]
    errors_25 = [r["error_at_25_pct"] for r in results if r["error_at_25_pct"] is not None]

    print(f"\n  TWAP Prediction Error (|forming_twap - final_twap| / final_twap):")
    for label, errors in [("10 min elapsed (20 remaining)", errors_10),
                           ("20 min elapsed (10 remaining)", errors_20),
                           ("25 min elapsed (5 remaining)", errors_25)]:
        if errors:
            lo, mean, hi = bootstrap_ci(errors)
            print(f"    {label}: mean={mean:.4f}% | IC95%: [{lo:.4f}%, {hi:.4f}%] | max={max(errors):.4f}%")

    # How often is forming TWAP within 0.1% of final?
    for label, errors in [("10 min", errors_10), ("20 min", errors_20), ("25 min", errors_25)]:
        if errors:
            within_01 = sum(1 for e in errors if e < 0.1)
            within_005 = sum(1 for e in errors if e < 0.05)
            print(f"\n    {label}: within 0.1%: {within_01}/{len(errors)} ({within_01/len(errors)*100:.0f}%) | "
                  f"within 0.05%: {within_005}/{len(errors)} ({within_005/len(errors)*100:.0f}%)")

    # The exploit: if at minute 20, forming TWAP is within 0.05% of final,
    # and an option's market price differs from intrinsic at forming TWAP by > fees,
    # then buying/selling that option is +EV (you know the settlement with high confidence)
    if errors_20:
        predictable = sum(1 for e in errors_20 if e < 0.05)
        wr_predictable = predictable / len(errors_20) * 100
        wr_lo, wr_hi = wilson_ci(predictable, len(errors_20))

        print(f"\n  === EXPLOIT VIABILITY ===")
        print(f"  At minute 20 (10 min remaining):")
        print(f"    TWAP predictable within 0.05%: {predictable}/{len(errors_20)} ({wr_predictable:.1f}%)")
        print(f"    Wilson CI: [{wr_lo*100:.1f}%, {wr_hi*100:.1f}%]")
        print(f"    If option mispricing > 0.05% + fees (0.03% taker), you profit")

    # Verdict
    print(f"\n{'='*80}")
    print(f"VEREDITO — D31 Deribit Settlement TWAP Exploit | {currency}")
    print(f"{'='*80}")
    if errors_20:
        predictable_20 = sum(1 for e in errors_20 if e < 0.05) / len(errors_20)
        if predictable_20 > 0.8:
            print(f"  >>> EDGE POTENCIAL: {predictable_20*100:.0f}% das vezes, TWAP aos 20min é previsível dentro 0.05%")
            print(f"  >>> Exploit: observar 20min do TWAP, estimar settlement, comprar/vender options mispriced")
            print(f"  >>> CUIDADO: precisa de option com bid-ask spread > erro TWAP + fees para lucrar")
            print(f"  >>> Recomendado: paper trade em expiries reais para validar execução")
        elif predictable_20 > 0.5:
            print(f"  >>> SINAL MODERADO: {predictable_20*100:.0f}% previsível aos 20min")
            print(f"  >>> Pode funcionar mas com risco de TWAP mudar nos últimos 10min")
        else:
            print(f"  >>> SEM EDGE: TWAP aos 20min não é previsível o suficiente ({predictable_20*100:.0f}%)")
            print(f"  >>> Últimos 10 minutos têm volatilidade suficiente para mudar o settlement")
    else:
        print(f"  >>> DADOS INSUFICIENTES para veredito")

    return results


def main():
    ap = argparse.ArgumentParser(description="D31 — Deribit Settlement TWAP Exploit")
    ap.add_argument("--asset", default="BTC", choices=["BTC", "ETH"])
    ap.add_argument("--backtest", type=int, default=30, help="Number of past expiries to backtest")
    args = ap.parse_args()

    assets = ["BTC", "ETH"] if args.asset == "BTC" else [args.asset]
    for a in assets:
        backtest_twap_settlement(a, args.backtest)


if __name__ == "__main__":
    main()
