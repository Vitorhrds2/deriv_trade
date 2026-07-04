"""
D19 — On-chain signals como signal direcional BTC.

Hipotese: metricas on-chain (NVT ratio, hash rate, transaction volume)
predizem movimentos de preco do BTC quando em extremos.

Mecanismo:
- NVT alto (Network Value to Transaction) = mercado sobreavaliado vs atividade real -> bearish
- NVT baixo = mercado subavaliado vs atividade real -> bullish
- Hash rate crescendo = mineradores confiantes -> bullish
- Transaction volume alto = adocao/uso real -> bullish

Data sources (todas gratuitas, sem API key):
- CoinGecko: BTC price + market cap + total volume (365 dias)
- NVT calculado: market_cap / total_volume (proxy para Network Value to Transaction)

Teste:
1. Fetch 365 dias de NVT + price
2. Classificar NVT em quintis
3. Para cada quintil, medir retorno do BTC nos N dias seguintes (1d, 3d, 7d, 14d)
4. Backtest: long quando NVT < Q20%, short quando NVT > Q80%
5. Veredito: IC95% no retorno medio por quintil
"""
import argparse
import json
import sys
import time
import urllib.request
import urllib.parse
from datetime import datetime, timedelta

try:
    from stats_utils import bootstrap_ci, wilson_ci, mean
except ImportError:
    print("ERRO: stats_utils.py nao encontrado. Execute do diretorio trading-engine/")
    sys.exit(1)


def fetch_coingecko_btc_full(days=365):
    """Fetch BTC daily prices, market caps, and total volumes from CoinGecko (free, no API key)."""
    url = f"https://api.coingecko.com/api/v3/coins/bitcoin/market_chart?vs_currency=usd&days={days}&interval=daily"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read())
    result = []
    prices = data.get("prices", [])
    mcap = data.get("market_caps", [])
    volumes = data.get("total_volumes", [])
    for i in range(len(prices)):
        ts_ms, price = prices[i]
        dt = datetime.utcfromtimestamp(ts_ms / 1000)
        mc = mcap[i][1] if i < len(mcap) else None
        vol = volumes[i][1] if i < len(volumes) else None
        nvt = mc / vol if mc and vol and vol > 0 else None
        result.append({
            "date": dt.strftime("%Y-%m-%d"),
            "price": price,
            "market_cap": mc,
            "volume": vol,
            "nvt": nvt,
        })
    return result


def merge_by_date(*series_list):
    """Merge multiple series by date string. Returns list of dicts with all values."""
    merged = {}
    for i, series in enumerate(series_list):
        key = ["price", "nvt", "hashrate", "tx_volume"][i] if i < 4 else f"col_{i}"
        for point in series:
            d = point["date"]
            if d not in merged:
                merged[d] = {"date": d}
            merged[d][key] = point["value"]
    return sorted(merged.values(), key=lambda x: x["date"])


def compute_forward_returns(data, horizons=(1, 3, 7, 14)):
    """Compute forward returns for each row based on price column."""
    prices = [(d["date"], d.get("price")) for d in data]
    for i, row in enumerate(data):
        for h in horizons:
            if i + h < len(prices) and prices[i][1] and prices[i + h][1]:
                fwd_price = prices[i + h][1]
                cur_price = prices[i][1]
                row[f"fwd_ret_{h}d"] = (fwd_price - cur_price) / cur_price * 100
            else:
                row[f"fwd_ret_{h}d"] = None
    return data


def backtest_nvt_quintiles(data, horizon=7):
    """Split NVT into quintiles, measure forward returns per quintile."""
    valid = [d for d in data if d.get("nvt") is not None and d.get(f"fwd_ret_{horizon}d") is not None]
    if len(valid) < 20:
        return None

    valid.sort(key=lambda x: x["nvt"])
    n = len(valid)
    quintile_size = n // 5

    results = {}
    for q in range(5):
        start = q * quintile_size
        end = (q + 1) * quintile_size if q < 4 else n
        chunk = valid[start:end]
        returns = [c[f"fwd_ret_{horizon}d"] for c in chunk]
        lo, avg, hi = bootstrap_ci(returns, n_boot=5000)
        nvt_vals = [c["nvt"] for c in chunk]
        results[f"Q{q+1}"] = {
            "n": len(chunk),
            "nvt_range": f"{min(nvt_vals):.1f}-{max(nvt_vals):.1f}",
            "avg_return": avg,
            "ci95": (lo, hi),
            "wins": sum(1 for r in returns if r > 0),
            "wr": sum(1 for r in returns if r > 0) / len(returns) if returns else 0,
        }
    return results


def backtest_signal(data, condition_key, condition_fn, horizon=7):
    """Backtest a binary signal: when condition_fn(row) is True, take position."""
    valid = [d for d in data if d.get(f"fwd_ret_{horizon}d") is not None and condition_fn(d)]
    if len(valid) < 5:
        return None
    returns = [d[f"fwd_ret_{horizon}d"] for d in valid]
    lo, avg, hi = bootstrap_ci(returns, n_boot=5000)
    wins = sum(1 for r in returns if r > 0)
    return {
        "n": len(valid),
        "avg_return": avg,
        "ci95": (lo, hi),
        "wr": wins / len(returns) if returns else 0,
        "wr_ci": wilson_ci(wins, len(returns)),
    }


def main():
    parser = argparse.ArgumentParser(description="D19 — On-chain signal scan (NVT, hash rate, tx volume)")
    parser.add_argument("--days", type=int, default=365, help="Historical window in days")
    parser.add_argument("--horizon", type=int, default=7, help="Forward return horizon in days")
    args = parser.parse_args()

    print("=" * 100)
    print(f"D19 — On-chain Signal Scan | {args.days} dias | horizonte={args.horizon}d")
    print("=" * 100)

    # 1. Fetch BTC data (price + market cap + volume -> NVT)
    print("\n[1/3] Fetching BTC data from CoinGecko (price + market cap + volume -> NVT)...")
    try:
        btc_data = fetch_coingecko_btc_full(args.days)
        print(f"  OK: {len(btc_data)} dias | {btc_data[0]['date']} -> {btc_data[-1]['date']} | ${btc_data[0]['price']:.0f} -> ${btc_data[-1]['price']:.0f}")
        nvt_vals = [d["nvt"] for d in btc_data if d.get("nvt") is not None]
        if nvt_vals:
            print(f"  NVT range: {min(nvt_vals):.2f} - {max(nvt_vals):.2f} | mediana: {sorted(nvt_vals)[len(nvt_vals)//2]:.2f}")
    except Exception as e:
        print(f"  ERRO: {e}")
        sys.exit(1)

    # 2. Compute forward returns
    print("\n[2/3] Computing forward returns...")
    data = compute_forward_returns(btc_data, horizons=(1, 3, 7, 14))
    valid_count = sum(1 for d in data if d.get("nvt") is not None and d.get(f"fwd_ret_{args.horizon}d") is not None)
    print(f"  {len(data)} dias totais, {valid_count} com NVT + forward return")

    # 3. Analysis
    print(f"\n[3/3] Analise — quintis de NVT vs forward return ({args.horizon}d)")

    # NVT quintile analysis
    print("\n" + "=" * 80)
    print("NVT QUINTIL ANALYSIS")
    print("=" * 80)
    for h in (1, 3, 7, 14):
        results = backtest_nvt_quintiles(data, horizon=h)
        if results:
            print(f"\nHorizonte: {h}d")
            print(f"  {'Quintil':<8} {'N':<6} {'NVT range':<20} {'Retorno%':<12} {'IC95%':<30} {'WR%':<8}")
            print("  " + "-" * 84)
            for q, r in results.items():
                ci_str = f"[{r['ci95'][0]:.2f}%, {r['ci95'][1]:.2f}%]"
                print(f"  {q:<8} {r['n']:<6} {r['nvt_range']:<20} {r['avg_return']:<12.2f} {ci_str:<30} {r['wr']*100:<8.1f}")

    # Signal backtests
    print("\n" + "=" * 80)
    print("SIGNAL BACKTESTS")
    print("=" * 80)

    nvt_values = [d["nvt"] for d in data if d.get("nvt") is not None]
    if nvt_values:
        nvt_median = sorted(nvt_values)[len(nvt_values) // 2]
        nvt_q20 = sorted(nvt_values)[int(len(nvt_values) * 0.2)]
        nvt_q80 = sorted(nvt_values)[int(len(nvt_values) * 0.8)]

        signals = [
            ("NVT < Q20 (bullish - subavaliado)", lambda d: d.get("nvt") is not None and d["nvt"] < nvt_q20),
            ("NVT > Q80 (bearish - sobreavaliado)", lambda d: d.get("nvt") is not None and d["nvt"] > nvt_q80),
            ("NVT < mediana (bullish)", lambda d: d.get("nvt") is not None and d["nvt"] < nvt_median),
            ("NVT > mediana (bearish)", lambda d: d.get("nvt") is not None and d["nvt"] > nvt_median),
        ]

        for label, fn in signals:
            for h in (1, 3, 7, 14):
                result = backtest_signal(data, "nvt", fn, horizon=h)
                if result:
                    ci_str = f"[{result['ci95'][0]:.2f}%, {result['ci95'][1]:.2f}%]"
                    wr_ci_str = f"[{result['wr_ci'][0]*100:.1f}%, {result['wr_ci'][1]*100:.1f}%]"
                    print(f"\n  {label} | {h}d")
                    print(f"    N={result['n']} | Retorno medio={result['avg_return']:.2f}% IC95%{ci_str} | WR={result['wr']*100:.1f}% IC95%{wr_ci_str}")

    # Volume signal (total volume as proxy for on-chain activity)
    vol_values = [d.get("volume") for d in data if d.get("volume") is not None]
    if vol_values:
        vol_median = sorted(vol_values)[len(vol_values) // 2]
        print(f"\n  Volume mediano: ${vol_median/1e9:.1f}B")

        vol_q20 = sorted(vol_values)[int(len(vol_values) * 0.2)]
        vol_q80 = sorted(vol_values)[int(len(vol_values) * 0.8)]

        for label, fn in [
            (f"Volume < Q20 (${vol_q20/1e9:.1f}B) -> bearish (baixa atividade)", lambda d: d.get("volume") is not None and d["volume"] < vol_q20),
            (f"Volume > Q80 (${vol_q80/1e9:.1f}B) -> bullish (alta atividade)", lambda d: d.get("volume") is not None and d["volume"] > vol_q80),
        ]:
            for h in (3, 7, 14):
                result = backtest_signal(data, "volume", fn, horizon=h)
                if result:
                    ci_str = f"[{result['ci95'][0]:.2f}%, {result['ci95'][1]:.2f}%]"
                    wr_ci_str = f"[{result['wr_ci'][0]*100:.1f}%, {result['wr_ci'][1]*100:.1f}%]"
                    print(f"\n  {label} | {h}d")
                    print(f"    N={result['n']} | Retorno medio={result['avg_return']:.2f}% IC95%{ci_str} | WR={result['wr']*100:.1f}% IC95%{wr_ci_str}")

    # Save samples
    samples = [{"date": d["date"], "price": d.get("price"), "nvt": d.get("nvt"),
                "market_cap": d.get("market_cap"), "volume": d.get("volume"),
                "fwd_ret_7d": d.get("fwd_ret_7d")} for d in data]
    with open("onchain_signal_samples.json", "w") as f:
        json.dump(samples, f, indent=2)
    print(f"\nAmostras salvas em onchain_signal_samples.json")

    # Verdict
    print("\n" + "=" * 100)
    print("VEREDITO PRELIMINAR")
    print("=" * 100)

    # Check if Q1 (low NVT) has positive returns and Q5 (high NVT) has negative
    q_results = backtest_nvt_quintiles(data, horizon=args.horizon)
    if q_results:
        q1 = q_results.get("Q1", {})
        q5 = q_results.get("Q5", {})
        edge_found = q1.get("avg_return", 0) > 0 and q1.get("ci95", (0, 0))[0] > 0
        inverse_edge = q5.get("avg_return", 0) < 0 and q5.get("ci95", (0, 0))[1] < 0

        if edge_found and inverse_edge:
            print(f"  SINAL ENCONTRADO: NVT baixo -> retorno positivo ({q1['avg_return']:.2f}%), NVT alto -> retorno negativo ({q5['avg_return']:.2f}%)")
        elif edge_found:
            print(f"  SINAL PARCIAL: NVT baixo -> retorno positivo ({q1['avg_return']:.2f}%), IC95% nao cruza zero")
        elif inverse_edge:
            print(f"  SINAL PARCIAL: NVT alto -> retorno negativo ({q5['avg_return']:.2f}%), IC95% nao cruza zero")
        else:
            print(f"  SEM EDGE: NVT quintis nao separam retornos de forma significativa")
            print(f"    Q1 retorno={q1.get('avg_return', 0):.2f}% | Q5 retorno={q5.get('avg_return', 0):.2f}%")
            print(f"    IC95% Q1=[{q1.get('ci95', (0,0))[0]:.2f}%, {q1.get('ci95', (0,0))[1]:.2f}%] | Q5=[{q5.get('ci95', (0,0))[0]:.2f}%, {q5.get('ci95', (0,0))[1]:.2f}%]")
    else:
        print("  Dados insuficientes para veredito")

    print("\n  NOTA: NVT aqui e um proxy (market_cap / total_volume CoinGecko),")
    print("  nao o NVT classico (market_cap / on-chain tx volume em USD).")
    print("  Para validacao seria necessario:")
    print("  1. Out-of-sample test (treinar em 2022-2023, testar em 2024-2025)")
    print("  2. NVT classico com on-chain tx volume (requer Glassnode/CryptoQuant API key)")
    print("  3. Exchange inflow/outflow (requer CryptoQuant/Glassnode API key)")


if __name__ == "__main__":
    main()
