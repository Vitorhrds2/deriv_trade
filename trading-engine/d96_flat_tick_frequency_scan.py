"""D96 — Tick History Flat Frequency + RNG Deep Analysis.

Hipotese
--------
O flat_tick_bot rodou apenas 4 trades em JD100 e obteve 0 jackpots. Mas a amostra
e irrisoria para concluir. Jump Indices (JD10/JD25/JD50/JD75/JD100) tem periodos
"planos" entre saltos. Se P(tick == tick_anterior) > 11.11% para qualquer simbolo,
o straddle CALLE+PUTE em 1-tick e lucrativo:
  - Non-flat round: uma perna ganha (+$0.80), outra perde (-$1.00) = -$0.20
  - Flat round: ambas ganham (+$0.80 + $0.80) = +$1.60
  - Breakeven: P(flat) * 1.60 = (1 - P(flat)) * 0.20 => P(flat) > 11.11%

Adicionalmente, roda testes estatisticos comprehensivos no tick history:
  - Autocorrelacao (lag 1-10)
  - Ljung-Box test
  - Hurst exponent (R/S analysis)
  - Runs test
  - Spectral density (FFT)
  - Tick interval distribution

Se qualquer teste mostrar desvio de aleatoriedade pura, pode haver padrao exploravel.

Uso
---
    python d96_flat_tick_frequency_scan.py
    python d96_flat_tick_frequency_scan.py --symbols 1HZ10V,1HZ100V,R_10 --count 50000

Output: d96_flat_tick_results.json
"""
import argparse
import asyncio
import json
import math
import os
import sys
import time
from collections import Counter
from datetime import datetime, timezone

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from deriv_client import DerivClient

SYMBOLS_DEFAULT = [
    "1HZ10V", "1HZ25V", "1HZ50V", "1HZ75V", "1HZ100V",
    "R_10", "R_25", "R_50", "R_75", "R_100",
    "JD10", "JD25", "JD50", "JD75", "JD100",
    "BOOM1000", "CRASH1000",
]

BREAKEVEN_P_FLAT = 0.1111


async def fetch_ticks(client, symbol, count):
    """Pagina ticks_history para baixar ate `count` ticks."""
    times, prices = [], []
    end = "latest"
    remaining = count
    while remaining > 0:
        c = min(1000, remaining)
        try:
            res = await client.send_request({
                "ticks_history": symbol, "end": end,
                "count": c, "style": "ticks",
            })
        except Exception as e:
            print(f"  [{symbol}] erro fetching ticks: {e}", flush=True)
            break
        hist = res.get("history") or {}
        ps, ts = hist.get("prices") or [], hist.get("times") or []
        if not ps:
            break
        times = list(ts) + times
        prices = list(ps) + prices
        remaining -= len(ps)
        if len(ps) < c:
            break
        end = int(ts[0]) - 1
        await asyncio.sleep(0.3)
    return times, prices


def analyze_flat_frequency(prices):
    """Mede P(tick == tick_anterior) e estatisticas relacionadas."""
    n = len(prices)
    if n < 2:
        return None
    flat_count = 0
    changes = []
    for i in range(1, n):
        diff = float(prices[i]) - float(prices[i - 1])
        if diff == 0:
            flat_count += 1
        changes.append(diff)
    p_flat = flat_count / (n - 1)
    non_flat = (n - 1) - flat_count

    # Wilson CI para P(flat)
    z = 1.96
    p_hat = p_flat
    n_total = n - 1
    denom = 1 + z * z / n_total
    center = (p_hat + z * z / (2 * n_total)) / denom
    margin = z * math.sqrt((p_hat * (1 - p_hat) + z * z / (4 * n_total)) / n_total) / denom
    ci_lo = max(0, center - margin)
    ci_hi = min(1, center + margin)

    # EV do straddle
    # Assumindo payout_per_win = $0.80 (profit), loss = -$1.00
    # Flat: +$1.60, Non-flat: -$0.20
    ev_per_round = p_flat * 1.60 + (1 - p_flat) * (-0.20)
    ev_ci_lo = ci_lo * 1.60 + (1 - ci_lo) * (-0.20)
    ev_ci_hi = ci_hi * 1.60 + (1 - ci_hi) * (-0.20)

    return {
        "n_ticks": n,
        "n_pairs": n - 1,
        "flat_count": flat_count,
        "non_flat_count": non_flat,
        "p_flat": round(p_flat, 6),
        "p_flat_ci95": [round(ci_lo, 6), round(ci_hi, 6)],
        "breakeven_p_flat": BREAKEVEN_P_FLAT,
        "exceeds_breakeven": ci_lo > BREAKEVEN_P_FLAT,
        "ev_per_round": round(ev_per_round, 4),
        "ev_ci95": [round(ev_ci_lo, 4), round(ev_ci_hi, 4)],
        "verdict": "EDGE" if ci_lo > BREAKEVEN_P_FLAT else ("INCONCLUSIVE" if ci_hi > BREAKEVEN_P_FLAT else "REFUTED"),
    }


def analyze_autocorrelation(changes, max_lag=10):
    """Autocorrelacao dos sinais de direcao (up=1, down=0, flat=skip)."""
    bits = [1 if c > 0 else 0 for c in changes if c != 0]
    n = len(bits)
    if n < 20:
        return None
    mean = sum(bits) / n
    results = []
    for lag in range(1, min(max_lag + 1, n // 4)):
        cov = sum((bits[i] - mean) * (bits[i + lag] - mean) for i in range(n - lag))
        var = sum((b - mean) ** 2 for b in bits)
        if var == 0:
            results.append({"lag": lag, "acf": 0})
        else:
            acf = cov / var
            results.append({"lag": lag, "acf": round(acf, 4)})
    return results


def analyze_ljung_box(bits, max_lag=10):
    """Ljung-Box test para independencia serial."""
    n = len(bits)
    if n < 20:
        return None
    mean = sum(bits) / n
    if mean == 0 or mean == 1:
        return {"Q": 0, "df": max_lag, "p_value": 1.0}
    acfs = []
    for lag in range(1, max_lag + 1):
        cov = sum((bits[i] - mean) * (bits[i + lag] - mean) for i in range(n - lag))
        var = sum((b - mean) ** 2 for b in bits)
        acf = cov / var if var > 0 else 0
        acfs.append(acf)
    Q = n * (n + 2) * sum(acf ** 2 / (n - k) for k, acf in enumerate(acfs, 1))
    # Aproximacao chi-square com df = max_lag
    df = max_lag
    # p-value aproximado (chi2 survival function)
    # Usando aproximacao Wilson-Hilferty para chi2
    if df > 0:
        x = Q / df
        h = 2 / (9 * df)
        z = (x ** (1/3) - (1 - h)) / math.sqrt(h)
        # Phi(-z) = p-value
        p_value = 0.5 * (1 + math.erf(-z / math.sqrt(2)))
    else:
        p_value = 1.0
    return {"Q": round(Q, 2), "df": df, "p_value": round(p_value, 6)}


def analyze_hurst(changes):
    """Hurst exponent via R/S analysis simplificado."""
    abs_changes = [abs(c) for c in changes if c != 0]
    n = len(abs_changes)
    if n < 64:
        return None
    rs_values = []
    log_ns = []
    for block_size in [16, 32, 64, 128, 256]:
        if block_size > n // 2:
            continue
        num_blocks = n // block_size
        rs_list = []
        for b in range(num_blocks):
            block = abs_changes[b * block_size:(b + 1) * block_size]
            mean = sum(block) / len(block)
            cumdev = 0
            max_dev = -float("inf")
            min_dev = float("inf")
            for val in block:
                cumdev += (val - mean)
                max_dev = max(max_dev, cumdev)
                min_dev = min(min_dev, cumdev)
            R = max_dev - min_dev
            S = math.sqrt(sum((v - mean) ** 2 for v in block) / len(block))
            if S > 0:
                rs_list.append(R / S)
        if rs_list:
            rs_values.append(sum(rs_list) / len(rs_list))
            log_ns.append(math.log(block_size))
    if len(rs_values) < 3:
        return None
    # Regressao linear log(R/S) = H * log(N) + c
    log_rs = [math.log(rs) for rs in rs_values]
    n_pts = len(log_rs)
    sum_x = sum(log_ns)
    sum_y = sum(log_rs)
    sum_xy = sum(x * y for x, y in zip(log_ns, log_rs))
    sum_x2 = sum(x ** 2 for x in log_ns)
    H = (n_pts * sum_xy - sum_x * sum_y) / (n_pts * sum_x2 - sum_x ** 2)
    return {"hurst": round(H, 4), "interpretation": "mean-reverting" if H < 0.45 else ("trending" if H > 0.55 else "random")}


def analyze_runs(changes):
    """Runs test (Wald-Wolfowitz) para aleatoriedade de direcao."""
    bits = [1 if c > 0 else 0 for c in changes if c != 0]
    n = len(bits)
    if n < 20:
        return None
    n1 = sum(bits)
    n0 = n - n1
    if n1 == 0 or n0 == 0:
        return {"runs": 1, "z": 0, "n": n}
    # Conta runs
    runs = 1
    for i in range(1, n):
        if bits[i] != bits[i - 1]:
            runs += 1
    expected = 2 * n1 * n0 / n + 1
    variance = 2 * n1 * n0 * (2 * n1 * n0 - n) / (n * n * (n - 1))
    if variance <= 0:
        return {"runs": runs, "z": 0, "n": n, "expected": round(expected, 2)}
    z = (runs - expected) / math.sqrt(variance)
    return {"runs": runs, "expected_runs": round(expected, 2), "z": round(z, 4), "n": n}


def analyze_tick_intervals(times):
    """Distribuicao de intervalos entre ticks."""
    if len(times) < 10:
        return None
    intervals = []
    for i in range(1, len(times)):
        dt = int(times[i]) - int(times[i - 1])
        if dt >= 0:
            intervals.append(dt)
    if not intervals:
        return None
    counter = Counter(intervals)
    n = len(intervals)
    mean = sum(intervals) / n
    sorted_intervals = sorted(intervals)
    median = sorted_intervals[n // 2]
    return {
        "n": n,
        "mean_interval_s": round(mean, 3),
        "median_interval_s": median,
        "min_interval_s": min(intervals),
        "max_interval_s": max(intervals),
        "distribution": {str(k): v for k, v in sorted(counter.items())[:10]},
    }


def analyze_price_change_distribution(changes):
    """Distribuicao de magnitudes de mudanca de preco."""
    abs_changes = [abs(c) for c in changes]
    n = len(abs_changes)
    if n == 0:
        return None
    zero_count = sum(1 for c in changes if c == 0)
    mean = sum(abs_changes) / n
    sorted_c = sorted(abs_changes)
    median = sorted_c[n // 2]
    p95 = sorted_c[int(n * 0.95)]
    return {
        "n": n,
        "zero_count": zero_count,
        "zero_pct": round(zero_count / n * 100, 4),
        "mean_abs_change": round(mean, 8),
        "median_abs_change": round(median, 8),
        "p95_abs_change": round(p95, 8),
        "max_abs_change": round(max(abs_changes), 8),
    }


async def scan_symbol(client, symbol, count):
    print(f"\n--- {symbol} ---", flush=True)
    times, prices = await fetch_ticks(client, symbol, count)
    if len(prices) < 100:
        print(f"  {symbol}: apenas {len(prices)} ticks, pulando", flush=True)
        return {"symbol": symbol, "error": f"insufficient ticks: {len(prices)}"}

    changes = [float(prices[i]) - float(prices[i - 1]) for i in range(1, len(prices))]

    flat_analysis = analyze_flat_frequency(prices)
    acf = analyze_autocorrelation(changes)
    bits = [1 if c > 0 else 0 for c in changes if c != 0]
    ljung = analyze_ljung_box(bits)
    hurst = analyze_hurst(changes)
    runs = analyze_runs(changes)
    intervals = analyze_tick_intervals(times)
    change_dist = analyze_price_change_distribution(changes)

    result = {
        "symbol": symbol,
        "n_ticks": len(prices),
        "flat_analysis": flat_analysis,
        "autocorrelation": acf,
        "ljung_box": ljung,
        "hurst": hurst,
        "runs_test": runs,
        "tick_intervals": intervals,
        "change_distribution": change_dist,
    }

    p_flat = flat_analysis["p_flat"] if flat_analysis else 0
    verdict = flat_analysis["verdict"] if flat_analysis else "N/A"
    print(f"  P(flat)={p_flat:.4f} | verdict={verdict} | n={len(prices)}", flush=True)
    if hurst:
        print(f"  Hurst={hurst['hurst']:.4f} ({hurst['interpretation']})", flush=True)
    if runs:
        print(f"  Runs z={runs.get('z', 0):.3f} (expected={runs.get('expected_runs', '?')})", flush=True)
    if ljung:
        print(f"  Ljung-Box Q={ljung['Q']:.1f} p={ljung['p_value']:.4f}", flush=True)

    return result


async def main():
    parser = argparse.ArgumentParser(description="D96 Flat Tick Frequency + RNG Analysis")
    parser.add_argument("--symbols", default=",".join(SYMBOLS_DEFAULT))
    parser.add_argument("--count", type=int, default=50000)
    parser.add_argument("--output", default="d96_flat_tick_results.json")
    parser.add_argument("--app-id", default=os.getenv("DERIV_APP_ID", "1089"))
    args = parser.parse_args()

    symbols = [s.strip() for s in args.symbols.split(",") if s.strip()]
    print(f"D96 — Flat Tick Frequency + RNG Deep Analysis", flush=True)
    print(f"Symbols: {symbols}", flush=True)
    print(f"Ticks per symbol: {args.count}", flush=True)
    print(f"Breakeven P(flat): {BREAKEVEN_P_FLAT:.4f} (11.11%)", flush=True)

    client = DerivClient(app_id=args.app_id, use_demo=False)
    await client.connect()
    await asyncio.sleep(1)

    results = []
    for sym in symbols:
        try:
            r = await scan_symbol(client, sym, args.count)
            results.append(r)
        except Exception as e:
            print(f"  ERROR {sym}: {e}", flush=True)
            results.append({"symbol": sym, "error": str(e)})

    await client.disconnect()

    output = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "hypothesis": "D96",
        "description": "Flat tick frequency + RNG deep analysis",
        "breakeven_p_flat": BREAKEVEN_P_FLAT,
        "symbols_tested": len(results),
        "results": results,
        "summary": {},
    }

    edges = [r for r in results if r.get("flat_analysis", {}).get("exceeds_breakeven")]
    inconclusive = [r for r in results if r.get("flat_analysis", {}).get("verdict") == "INCONCLUSIVE"]
    refuted = [r for r in results if r.get("flat_analysis", {}).get("verdict") == "REFUTED"]

    output["summary"] = {
        "edges_found": len(edges),
        "inconclusive": len(inconclusive),
        "refuted": len(refuted),
        "edge_symbols": [r["symbol"] for r in edges],
        "inconclusive_symbols": [r["symbol"] for r in inconclusive],
    }

    with open(args.output, "w") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)
    print(f"\n=== SUMMARY ===", flush=True)
    print(f"Edges: {len(edges)} | Inconclusive: {len(inconclusive)} | Refuted: {len(refuted)}", flush=True)
    if edges:
        print(f"EDGE SYMBOLS: {[r['symbol'] for r in edges]}", flush=True)
    print(f"Results saved to {args.output}", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
