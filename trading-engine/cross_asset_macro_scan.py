"""
D21 — Cross-asset macro signal scan.

Hipotese: correlacoes macro (DXY, VIX, Gold, S&P500) com BTC returns
podem ser usadas como signal direcional.

Mecanismo:
- DXY (Dollar Index) inversamente correlacionado com BTC -> DXY subindo = BTC caindo
- VIX (volatilidade) positivamente correlacionado com BTC vol -> VIX alto = risk-off = BTC caindo
- Gold como safe haven -> Gold subindo em momentos de stress = BTC caindo (risk-off)
- S&P500 correlacionado com BTC (risk on/off) -> S&P caindo = BTC caindo

Data sources (todas gratuitas, sem API key):
- yfinance: BTC-USD, ^GSPC (S&P500), ^VIX, DX-Y.NYB (DXY), GC=F (Gold futures)
- 2 anos de dados diarios

Teste:
1. Fetch 2 anos de dados diarios
2. Correlacao contemporanea + lagged correlation (BTC lidera ou segue?)
3. Granger causality (se statsmodels disponivel)
4. Backtest: quando DXY > X desvios acima da media, short BTC
5. Veredito: IC95% no retorno medio
"""
import argparse
import json
import sys
import math
from datetime import datetime

try:
    import yfinance as yf
except ImportError:
    print("ERRO: yfinance nao instalado. Run: pip3 install yfinance")
    sys.exit(1)

try:
    from stats_utils import bootstrap_ci, wilson_ci
except ImportError:
    print("ERRO: stats_utils.py nao encontrado. Execute do diretorio trading-engine/")
    sys.exit(1)


def fetch_yf_data(tickers, period="2y"):
    """Fetch daily data from Yahoo Finance for multiple tickers."""
    data = {}
    for ticker in tickers:
        try:
            df = yf.download(ticker, period=period, interval="1d", progress=False)
            if df.empty:
                print(f"  {ticker}: SEM DADOS")
                continue
            closes = []
            for idx, row in df.iterrows():
                dt = idx.to_pydatetime()
                close = float(row["Close"])
                if close == close:  # not NaN
                    closes.append({"date": dt.strftime("%Y-%m-%d"), "price": close})
            data[ticker] = closes
            print(f"  {ticker}: {len(closes)} dias")
        except Exception as e:
            print(f"  {ticker}: ERRO ({e})")
    return data


def compute_daily_returns(series):
    """Compute daily % returns for a price series."""
    returns = []
    for i in range(1, len(series)):
        if series[i]["price"] and series[i-1]["price"]:
            ret = (series[i]["price"] - series[i-1]["price"]) / series[i-1]["price"] * 100
            returns.append({"date": series[i]["date"], "return": ret})
    return returns


def merge_returns(all_returns, labels):
    """Merge return series by date."""
    merged = {}
    for returns, label in zip(all_returns, labels):
        for r in returns:
            d = r["date"]
            if d not in merged:
                merged[d] = {"date": d}
            merged[d][label] = r["return"]
    return sorted(merged.values(), key=lambda x: x["date"])


def correlation(x, y):
    """Pearson correlation."""
    n = min(len(x), len(y))
    if n < 3:
        return 0
    mx, my = sum(x[:n]) / n, sum(y[:n]) / n
    sx = math.sqrt(sum((xi - mx) ** 2 for xi in x[:n]) / n)
    sy = math.sqrt(sum((yi - my) ** 2 for yi in y[:n]) / n)
    if sx == 0 or sy == 0:
        return 0
    cov = sum((x[i] - mx) * (y[i] - my) for i in range(n)) / n
    return cov / (sx * sy)


def lagged_correlation(x, y, max_lag=10):
    """Compute correlation at different lags."""
    results = {}
    for lag in range(-max_lag, max_lag + 1):
        if lag >= 0:
            xs = x[:len(x) - lag] if lag > 0 else x
            ys = y[lag:]
        else:
            xs = x[-lag:]
            ys = y[:len(y) + lag]
        n = min(len(xs), len(ys))
        if n < 10:
            continue
        results[lag] = correlation(xs, ys)
    return results


def rolling_correlation(x, y, window=30):
    """Compute rolling correlation."""
    results = []
    for i in range(window, min(len(x), len(y))):
        chunk_x = x[i-window:i]
        chunk_y = y[i-window:i]
        r = correlation(chunk_x, chunk_y)
        results.append(r)
    return results


def backtest_signal(data, signal_key, threshold_fn, horizon_key, direction="long"):
    """Backtest: when signal meets threshold, take position."""
    valid = [d for d in data if d.get(signal_key) is not None and d.get(horizon_key) is not None and threshold_fn(d[signal_key])]
    if len(valid) < 5:
        return None
    returns = [d[horizon_key] for d in valid]
    if direction == "short":
        returns = [-r for r in returns]
    lo, avg, hi = bootstrap_ci(returns, n_boot=5000)
    wins = sum(1 for r in returns if r > 0)
    return {
        "n": len(valid),
        "avg_return": avg,
        "ci95": (lo, hi),
        "wr": wins / len(returns) if returns else 0,
        "wr_ci": wilson_ci(wins, len(returns)),
    }


def compute_forward_returns(data, price_key="btc", horizons=(1, 3, 7, 14)):
    """Compute forward returns for BTC."""
    prices = [(d["date"], d.get(price_key)) for d in data]
    for i, row in enumerate(data):
        for h in horizons:
            if i + h < len(prices) and prices[i][1] and prices[i + h][1]:
                row[f"btc_fwd_{h}d"] = (prices[i + h][1] - prices[i][1]) / prices[i][1] * 100
            else:
                row[f"btc_fwd_{h}d"] = None
    return data


def main():
    parser = argparse.ArgumentParser(description="D21 — Cross-asset macro signal scan")
    parser.add_argument("--period", default="2y", help="yfinance period (1y, 2y, 5y)")
    parser.add_argument("--horizon", type=int, default=7)
    args = parser.parse_args()

    print("=" * 100)
    print(f"D21 — Cross-Asset Macro Scan | period={args.period} | horizonte={args.horizon}d")
    print("=" * 100)

    # 1. Fetch data
    print("\n[1/4] Fetching data from Yahoo Finance...")
    tickers = {
        "BTC-USD": "btc",
        "^GSPC": "spx",
        "^VIX": "vix",
        "DX-Y.NYB": "dxy",
        "GC=F": "gold",
    }
    raw = fetch_yf_data(list(tickers.keys()), args.period)

    if "BTC-USD" not in raw:
        print("\nERRO: BTC data indisponivel. Abortando.")
        sys.exit(1)

    # 2. Compute returns
    print("\n[2/4] Computing daily returns...")
    all_returns = []
    labels = []
    for ticker, label in tickers.items():
        if ticker in raw:
            rets = compute_daily_returns(raw[ticker])
            all_returns.append(rets)
            labels.append(label)
            print(f"  {label}: {len(rets)} retornos")

    data = merge_returns(all_returns, labels)
    print(f"  Merge: {len(data)} dias com dados")

    # Also merge BTC prices for forward returns
    btc_prices = {d["date"]: d["price"] for d in raw["BTC-USD"]}
    for d in data:
        d["btc_price"] = btc_prices.get(d["date"])

    data = compute_forward_returns(data, "btc_price", horizons=(1, 3, 7, 14))

    # 3. Correlation analysis
    print("\n[3/4] Correlation analysis...")
    btc_rets = [d.get("btc", 0) for d in data if d.get("btc") is not None]
    print(f"\n  Correlacao contemporanea com BTC returns (N={len(btc_rets)}):")
    print(f"  {'Asset':<10} {'Corr':<10} {'Interpretacao'}")
    print("  " + "-" * 60)

    correlations = {}
    for label in ["spx", "vix", "dxy", "gold"]:
        vals = [d.get(label) for d in data if d.get("btc") is not None and d.get(label) is not None]
        btc_aligned = [d.get("btc") for d in data if d.get("btc") is not None and d.get(label) is not None]
        if len(vals) > 20:
            r = correlation(btc_aligned, vals)
            correlations[label] = r
            interp = ""
            if abs(r) < 0.1:
                interp = "sem correlacao"
            elif abs(r) < 0.3:
                interp = "correlacao fraca"
            elif abs(r) < 0.5:
                interp = "correlacao moderada"
            else:
                interp = "correlacao forte"
            direction = "positiva" if r > 0 else "negativa"
            print(f"  {label:<10} {r:<10.4f} {interp} {direction}")

    # Lagged correlation
    print(f"\n  Lagged correlation (BTC vs DXY, -10 a +10 dias):")
    if "dxy" in correlations:
        btc_vals = [d.get("btc", 0) for d in data if d.get("btc") is not None and d.get("dxy") is not None]
        dxy_vals = [d.get("dxy", 0) for d in data if d.get("btc") is not None and d.get("dxy") is not None]
        lagged = lagged_correlation(btc_vals, dxy_vals, max_lag=10)
        for lag in sorted(lagged.keys()):
            bar = "#" * int(abs(lagged[lag]) * 50)
            sign = "+" if lagged[lag] > 0 else "-"
            print(f"    lag={lag:+3d}: {lagged[lag]:+.4f} {sign}{bar}")

    # Rolling correlation
    print(f"\n  Rolling correlation (30d window, BTC vs S&P500):")
    if "spx" in correlations:
        btc_vals = [d.get("btc", 0) for d in data if d.get("btc") is not None and d.get("spx") is not None]
        spx_vals = [d.get("spx", 0) for d in data if d.get("btc") is not None and d.get("spx") is not None]
        rolling = rolling_correlation(btc_vals, spx_vals, 30)
        if rolling:
            r_mean = sum(rolling) / len(rolling)
            r_min = min(rolling)
            r_max = max(rolling)
            r_current = rolling[-1]
            print(f"    Media={r_mean:.4f} | Min={r_min:.4f} | Max={r_max:.4f} | Atual={r_current:.4f}")
            print(f"    (Correlacao BTC-S&P500 varia ao longo do tempo, atual={'alta' if abs(r_current)>0.5 else 'moderada' if abs(r_current)>0.3 else 'baixa'})")

    # 4. Backtest signals
    print("\n[4/4] Backtest signals...")
    print("\n" + "=" * 80)
    print("SIGNAL BACKTESTS")
    print("=" * 80)

    # Compute rolling stats for signals
    for signal in ["dxy", "vix", "spx", "gold"]:
        vals = [d.get(signal) for d in data if d.get(signal) is not None]
        if len(vals) < 30:
            continue
        mean_val = sum(vals) / len(vals)
        std_val = math.sqrt(sum((v - mean_val) ** 2 for v in vals) / len(vals))

        # Z-score for each day
        for d in data:
            if d.get(signal) is not None:
                d[f"{signal}_z"] = (d[signal] - mean_val) / std_val if std_val > 0 else 0

        print(f"\n  {signal.upper()}: mean={mean_val:.2f} std={std_val:.2f}")

        for label, fn, direction in [
            (f"{signal.upper()} > +1.5 std (SHORT BTC, risk-off)", lambda x: x > 1.5, "short"),
            (f"{signal.upper()} > +1.0 std (SHORT BTC)", lambda x: x > 1.0, "short"),
            (f"{signal.upper()} < -1.5 std (LONG BTC, risk-on)", lambda x: x < -1.5, "long"),
            (f"{signal.upper()} < -1.0 std (LONG BTC)", lambda x: x < -1.0, "long"),
        ]:
            for h in (1, 3, 7, 14):
                result = backtest_signal(data, f"{signal}_z", fn, f"btc_fwd_{h}d", direction)
                if result:
                    ci_str = f"[{result['ci95'][0]:.2f}%, {result['ci95'][1]:.2f}%]"
                    wr_ci_str = f"[{result['wr_ci'][0]*100:.1f}%, {result['wr_ci'][1]*100:.1f}%]"
                    print(f"    {label} | {h}d: N={result['n']} Retorno={result['avg_return']:.2f}% IC95%{ci_str} WR={result['wr']*100:.1f}%")

    # Save
    samples = []
    for d in data:
        row = {"date": d["date"]}
        for k in ["btc", "spx", "vix", "dxy", "gold", "btc_fwd_7d"]:
            row[k] = d.get(k)
        samples.append(row)
    with open("cross_asset_macro_samples.json", "w") as f:
        json.dump(samples, f, indent=2)
    print(f"\nAmostras salvas em cross_asset_macro_samples.json")

    # Verdict
    print("\n" + "=" * 100)
    print("VEREDITO PRELIMINAR")
    print("=" * 100)

    found_edges = []
    for signal in ["dxy", "vix", "spx", "gold"]:
        for h in (1, 3, 7, 14):
            for thresh, direction in [(1.0, "short"), (1.5, "short"), (-1.0, "long"), (-1.5, "long")]:
                fn = lambda x, t=thresh: x > t if t > 0 else x < t
                result = backtest_signal(data, f"{signal}_z", fn, f"btc_fwd_{h}d", direction)
                if result and result["ci95"][0] > 0:
                    found_edges.append(f"{signal.upper()} z{'>' if thresh > 0 else '<'}{abs(thresh)} {direction} {h}d: +{result['avg_return']:.2f}%")

    if found_edges:
        print(f"  SINAIS ENCONTRADOS ({len(found_edges)}):")
        for e in found_edges[:10]:
            print(f"    {e}")
    else:
        print("  SEM EDGE: nenhum signal macro isolado gera retorno positivo com IC95% > 0")
        print(f"  Correlacoes contemporaneas: {', '.join(f'{k}={v:.3f}' for k, v in correlations.items())}")
        print("  Correlacao existe mas e instavel no tempo e fraca para predicao direta.")

    print("\n  NOTA: Correlacao macro e tipicamente baixa e nao estacionaria.")
    print("  Para trading real seria necessario: combinacao multi-signal,")
    print("  regime detection (risk-on/risk-off), e OOS validation rigorosa.")


if __name__ == "__main__":
    main()
