"""
D75 — Tick Spectral Analysis (FFT / Entropy / Hurst Exponent)
==============================================================
D46 testou apenas padroes de 3 ticks (mean reversion) com N=190k.
Uma analise de dominio de frequencia pode revelar periodicidade ou
nao-aleatoriedade que padroes simples nao capturam.

Analises:
  1. FFT (Fast Fourier Transform) — detectar frequencias dominantes
  2. Entropia de Shannon — medir aleatoriedade dos retornos
  3. Exponente de Hurst — distinguir trending vs mean-reverting vs random
  4. Teste de Ljung-Box — autocorrelacao em multiplos lags
  5. Razao de variancia (VR test) — Lo-MacKinlay

Se o RNG da Deriv tem qualquer artifact periodico, FFT detecta.
Se ha memoria (Hurst != 0.5), ha informacao exploravel.

Simbolos: 1HZ10V, 1HZ50V, 1HZ100V, R_10, R_25, R_50, R_75, R_100
N=10000 ticks por simbolo (10 segundos por simbolo a 1 tick/s)
"""
import asyncio
import json
import math
import os
import sys
import statistics
import numpy as np
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

SYMBOLS = ["1HZ10V", "1HZ50V", "1HZ100V", "R_10", "R_25", "R_50", "R_75", "R_100"]
N_TICKS = 10000

RESULTS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tick_spectral_analysis_results.json")


async def download_ticks(client, symbol, count=N_TICKS):
    """Download ticks in batches if needed."""
    all_prices = []
    all_epochs = []
    remaining = count

    while remaining > 0:
        batch = min(remaining, 5000)
        res = await client.send_request({
            "ticks_history": symbol,
            "adjust_start_time": 1,
            "count": batch,
            "end": "latest" if not all_prices else all_epochs[-1],
            "start": 1,
            "style": "ticks",
        })

        if "error" in res:
            print(f"  Erro baixando ticks {symbol}: {res['error'].get('message', '')}")
            break

        history = res.get("history", {})
        prices = history.get("prices", [])
        epochs = history.get("times", [])

        if not prices:
            break

        all_prices.extend([float(p) for p in prices])
        all_epochs.extend(epochs)
        remaining -= len(prices)

        if len(prices) < batch:
            break

        await asyncio.sleep(0.3)

    return all_prices[:count], all_epochs[:count]


def compute_returns(prices):
    """Compute log returns."""
    returns = []
    for i in range(1, len(prices)):
        if prices[i] > 0 and prices[i-1] > 0:
            r = math.log(prices[i] / prices[i-1])
            returns.append(r)
    return returns


def fft_analysis(returns):
    """FFT to detect dominant frequencies."""
    n = len(returns)
    if n < 64:
        return None

    # Remove mean
    mean = statistics.mean(returns)
    centered = [r - mean for r in returns]

    # FFT
    fft_vals = np.fft.fft(centered)
    magnitudes = np.abs(fft_vals[:n // 2])
    frequencies = np.fft.fftfreq(n, d=1.0)[:n // 2]  # d=1s (1 tick/s)

    # Find top 5 peaks
    top_indices = np.argsort(magnitudes)[-10:][::-1]

    peaks = []
    for idx in top_indices:
        if magnitudes[idx] > 0:
            peaks.append({
                "freq": float(frequencies[idx]),
                "magnitude": float(magnitudes[idx]),
                "period_s": float(1.0 / frequencies[idx]) if frequencies[idx] > 0 else float('inf'),
            })

    # Spectral entropy (normalized)
    power = magnitudes ** 2
    total_power = sum(power)
    if total_power > 0:
        norm_power = [p / total_power for p in power]
        spectral_entropy = -sum(p * math.log(p + 1e-15) for p in norm_power if p > 0)
        max_entropy = math.log(n // 2)
        spectral_entropy_norm = spectral_entropy / max_entropy if max_entropy > 0 else 0
    else:
        spectral_entropy_norm = 0

    return {
        "peaks": peaks[:5],
        "spectral_entropy": float(spectral_entropy_norm),
        "n": n,
    }


def shannon_entropy(returns, n_bins=50):
    """Shannon entropy of return distribution."""
    if len(returns) < 100:
        return None

    min_r = min(returns)
    max_r = max(returns)
    if max_r == min_r:
        return 0

    bins = [0] * n_bins
    for r in returns:
        idx = int((r - min_r) / (max_r - min_r) * (n_bins - 1))
        bins[idx] += 1

    n = len(returns)
    entropy = 0
    for count in bins:
        if count > 0:
            p = count / n
            entropy -= p * math.log2(p)

    max_entropy = math.log2(n_bins)
    return {
        "entropy": float(entropy),
        "max_entropy": float(max_entropy),
        "normalized": float(entropy / max_entropy) if max_entropy > 0 else 0,
    }


def hurst_exponent(prices, max_lag=100):
    """Estimate Hurst exponent using R/S analysis."""
    n = len(prices)
    if n < max_lag * 2:
        return None

    lags = range(2, max_lag)
    rs_values = []

    for lag in lags:
        # Split into chunks of size lag
        n_chunks = n // lag
        if n_chunks < 1:
            continue

        rs_list = []
        for i in range(n_chunks):
            chunk = prices[i * lag:(i + 1) * lag]
            if len(chunk) < 2:
                continue
            mean_chunk = statistics.mean(chunk)
            deviations = [c - mean_chunk for c in chunk]
            cumsum = []
            s = 0
            for d in deviations:
                s += d
                cumsum.append(s)
            if not cumsum:
                continue
            r = max(cumsum) - min(cumsum)
            std = statistics.stdev(chunk) if len(chunk) > 1 else 0
            if std > 0:
                rs_list.append(r / std)

        if rs_list:
            rs_values.append((math.log(lag), math.log(statistics.mean(rs_list))))

    if len(rs_values) < 5:
        return None

    # Linear regression: log(R/S) = H * log(n) + c
    xs = [v[0] for v in rs_values]
    ys = [v[1] for v in rs_values]
    n_pts = len(xs)
    sum_x = sum(xs)
    sum_y = sum(ys)
    sum_xy = sum(x * y for x, y in zip(xs, ys))
    sum_x2 = sum(x * x for x in xs)

    denom = n_pts * sum_x2 - sum_x * sum_x
    if denom == 0:
        return None

    H = (n_pts * sum_xy - sum_x * sum_y) / denom

    return {
        "hurst": float(H),
        "interpretation": "trending" if H > 0.55 else ("mean-reverting" if H < 0.45 else "random walk"),
    }


def variance_ratio_test(returns, q=2, q2=5, q3=10):
    """Lo-MacKinlay variance ratio test."""
    n = len(returns)
    if n < q3 * 10:
        return None

    mu = statistics.mean(returns)
    var1 = statistics.variance(returns)

    results = {}
    for q_val in [q, q2, q3]:
        if n < q_val * 10:
            continue
        # Variance of q-period returns
        q_returns = []
        for i in range(n - q_val + 1):
            q_ret = sum(returns[i:i + q_val])
            q_returns.append(q_ret)

        var_q = statistics.variance(q_returns)
        vr = var_q / (q_val * var1) if var1 > 0 else 0

        # Z-statistic (homoscedastic)
        z = (vr - 1) * math.sqrt(n * q_val) / math.sqrt(2 * (q_val - 1))

        results[f"VR_q{q_val}"] = {
            "vr": float(vr),
            "z_stat": float(z),
            "p_value": float(2 * (1 - 0.5 * (1 + math.erf(abs(z) / math.sqrt(2))))),
            "reject_random_walk": abs(z) > 1.96,
        }

    return results


def ljung_box_test(returns, max_lag=20):
    """Ljung-Box test for autocorrelation at multiple lags."""
    n = len(returns)
    if n < max_lag * 10:
        return None

    mu = statistics.mean(returns)
    var = statistics.variance(returns)

    if var == 0:
        return None

    # Compute autocorrelations
    autocorrs = []
    for lag in range(1, max_lag + 1):
        numerator = sum((returns[i] - mu) * (returns[i + lag] - mu)
                        for i in range(n - lag))
        denominator = sum((r - mu) ** 2 for r in returns)
        if denominator == 0:
            autocorrs.append(0)
        else:
            autocorrs.append(numerator / denominator)

    # Ljung-Box statistic
    Q = n * (n + 2) * sum(rk ** 2 / (n - k) for k, rk in enumerate(autocorrs, 1))

    # Critical value at 0.05 for df=max_lag
    # Approximate: chi-square with max_lag degrees of freedom
    # For df=20, critical value at 0.05 is ~31.41
    critical_value = 31.41  # for df=20, alpha=0.05

    return {
        "Q_statistic": float(Q),
        "critical_value_0.05": float(critical_value),
        "reject_random_walk": Q > critical_value,
        "autocorrelations": [float(r) for r in autocorrs[:10]],
        "max_autocorr": float(max(abs(r) for r in autocorrs)),
        "lag_of_max": int(np.argmax(np.abs(autocorrs)) + 1),
    }


async def main():
    print("=" * 90)
    print("D75 — Tick Spectral Analysis (FFT / Entropy / Hurst / Ljung-Box / VR)")
    print(f"  Symbols: {', '.join(SYMBOLS)}")
    print(f"  Ticks per symbol: {N_TICKS}")
    print("=" * 90)

    client = DerivClient(app_id=APP_ID, api_token=TOKEN, use_demo=True)
    await client.connect()
    print(f"  Conectado. Conta: {client.account_id}")

    all_results = {}

    for sym in SYMBOLS:
        print(f"\n{'='*60}")
        print(f"  {sym}")
        print(f"{'='*60}")

        prices, epochs = await download_ticks(client, sym)
        print(f"  Ticks baixados: {len(prices)}")

        if len(prices) < 100:
            print(f"  Ticks insuficientes, pulando")
            continue

        returns = compute_returns(prices)
        print(f"  Returns calculados: {len(returns)}")

        # 1. FFT
        print(f"\n  1. FFT Analysis:")
        fft_result = fft_analysis(returns)
        if fft_result:
            print(f"     Spectral entropy (normalized): {fft_result['spectral_entropy']:.4f}")
            print(f"     (1.0 = white noise, <1.0 = structured)")
            print(f"     Top 5 frequency peaks:")
            for i, peak in enumerate(fft_result["peaks"]):
                print(f"       {i+1}. freq={peak['freq']:.6f} Hz "
                      f"period={peak['period_s']:.1f}s "
                      f"magnitude={peak['magnitude']:.2f}")

        # 2. Shannon Entropy
        print(f"\n  2. Shannon Entropy:")
        se_result = shannon_entropy(returns)
        if se_result:
            print(f"     Entropy: {se_result['entropy']:.4f} bits")
            print(f"     Max possible: {se_result['max_entropy']:.4f} bits")
            print(f"     Normalized: {se_result['normalized']:.4f}")
            print(f"     (1.0 = uniform/random, <1.0 = structured)")

        # 3. Hurst Exponent (computed on RETURNS, not prices)
        print(f"\n  3. Hurst Exponent (R/S Analysis on returns):")
        hurst_result = hurst_exponent(returns)
        if hurst_result:
            H = hurst_result["hurst"]
            print(f"     H = {H:.4f}")
            print(f"     Interpretation: {hurst_result['interpretation']}")
            print(f"     (H=0.5 random walk, H>0.5 trending, H<0.5 mean-reverting)")
            if abs(H - 0.5) > 0.1:
                print(f"     *** DESVIO SIGNIFICATIVO de 0.5 — possivel nao-aleatoriedade!")

        # 4. Variance Ratio Test
        print(f"\n  4. Variance Ratio Test (Lo-MacKinlay):")
        vr_result = variance_ratio_test(returns)
        if vr_result:
            for key, val in vr_result.items():
                print(f"     {key}: VR={val['vr']:.4f} z={val['z_stat']:.3f} "
                      f"p={val['p_value']:.4f} reject_RW={val['reject_random_walk']}")

        # 5. Ljung-Box Test
        print(f"\n  5. Ljung-Box Test (autocorrelation, lags 1-20):")
        lb_result = ljung_box_test(returns)
        if lb_result:
            print(f"     Q = {lb_result['Q_statistic']:.2f} "
                  f"(critical 0.05 = {lb_result['critical_value_0.05']:.2f})")
            print(f"     Reject random walk: {lb_result['reject_random_walk']}")
            print(f"     Max |autocorr| = {lb_result['max_autocorr']:.4f} at lag {lb_result['lag_of_max']}")
            print(f"     Autocorrs (1-10): {[f'{r:.4f}' for r in lb_result['autocorrelations']]}")

        all_results[sym] = {
            "n_ticks": len(prices),
            "n_returns": len(returns),
            "fft": fft_result,
            "shannon_entropy": se_result,
            "hurst": hurst_result,
            "variance_ratio": vr_result,
            "ljung_box": lb_result,
        }

        await asyncio.sleep(0.5)

    # Final verdict
    print(f"\n{'='*90}")
    print("  VEREDITO FINAL — TICK SPECTRAL ANALYSIS")
    print(f"{'='*90}")

    any_anomaly = False
    for sym, res in all_results.items():
        anomalies = []

        h = res.get("hurst", {})
        if h and abs(h.get("hurst", 0.5) - 0.5) > 0.1:
            anomalies.append(f"Hurst={h['hurst']:.3f} ({h['interpretation']})")

        lb = res.get("ljung_box", {})
        if lb and lb.get("reject_random_walk"):
            anomalies.append(f"Ljung-Box Q={lb['Q_statistic']:.1f}>crit")

        vr = res.get("variance_ratio", {})
        for key, val in vr.items():
            if val.get("reject_random_walk"):
                anomalies.append(f"{key}: z={val['z_stat']:.2f}")

        fft = res.get("fft", {})
        if fft and fft.get("spectral_entropy", 1.0) < 0.8:
            anomalies.append(f"FFT entropy={fft['spectral_entropy']:.3f}")

        if anomalies:
            print(f"\n  *** {sym}: ANOMALIAS DETECTADAS ***")
            for a in anomalies:
                print(f"    - {a}")
            any_anomaly = True
        else:
            print(f"  {sym}: random walk confirmado (sem anomalias)")

    if not any_anomaly:
        print(f"\n  NENHUMA ANOMALIA em nenhum simbolo. RNG da Deriv e indistinguivel")
        print(f"  de random walk por FFT, entropia, Hurst, Ljung-Box e VR test.")
        print(f"  D75 REFUTADO.")
    else:
        print(f"\n  ANOMALIAS DETECTADAS — investigar simbolos especificos para edge.")

    with open(RESULTS_FILE, "w") as f:
        json.dump(all_results, f, indent=2, default=str)
    print(f"\n  Resultados salvos em {RESULTS_FILE}")

    await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
