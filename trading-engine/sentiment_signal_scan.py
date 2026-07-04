"""
D20 — Sentiment + Trends signal scan.

Hipotese: indicadores de sentimento (Fear & Greed Index, Google Trends)
predizem movimentos de BTC quando em extremos, atuando como signal contrarian.

Mecanismo:
- Fear & Greed < 20 (extreme fear) -> mercado oversold -> comprar (bullish)
- Fear & Greed > 80 (extreme greed) -> mercado overbought -> vender (bearish)
- Google Trends alto para "bitcoin" -> atencao publica no pico -> top signal (contrarian)

Data sources (todas gratuitas, sem API key):
- alternative.me: Fear & Greed Index historico (365+ dias)
- Google Trends via pytrends: search interest "bitcoin" historico
- CoinGecko: BTC price historical

Teste:
1. Fetch 365 dias de F&G + Google Trends + BTC price
2. Classificar F&G em quintis
3. Para cada quintil, medir retorno do BTC nos dias seguintes (1d, 3d, 7d, 14d)
4. Backtest: long quando F&G < 25, short quando F&G > 75
5. Veredito: IC95% no retorno medio
"""
import argparse
import json
import sys
import time
import urllib.request
from datetime import datetime

try:
    from stats_utils import bootstrap_ci, wilson_ci
except ImportError:
    print("ERRO: stats_utils.py nao encontrado. Execute do diretorio trading-engine/")
    sys.exit(1)


def fetch_fear_greed(limit=365):
    """Fetch Fear & Greed Index from alternative.me (free, no API key)."""
    url = f"https://api.alternative.me/fng/?limit={limit}&format=json"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read())
    values = []
    for item in data.get("data", []):
        ts = int(item["timestamp"])
        val = int(item["value"])
        classification = item.get("value_classification", "")
        dt = datetime.utcfromtimestamp(ts)
        values.append({"date": dt.strftime("%Y-%m-%d"), "fg": val, "class": classification})
    return values


def fetch_google_trends(keyword="bitcoin", timeframe="today 12-m"):
    """Fetch Google Trends data via pytrends (free, unofficial)."""
    try:
        from pytrends.request import TrendReq
        p = TrendReq(hl="en-US", tz=0)
        p.build_payload([keyword], timeframe=timeframe)
        df = p.interest_over_time()
        values = []
        for idx, row in df.iterrows():
            dt = idx.to_pydatetime()
            val = int(row[keyword]) if keyword in row and not (row[keyword] != row[keyword]) else 0
            values.append({"date": dt.strftime("%Y-%m-%d"), "trends": val})
        return values
    except Exception as e:
        print(f"  Google Trends ERRO: {e}")
        print("  (Google Trends pode bloquear requests frequentes. Continuando sem trends.)")
        return []


def fetch_coingecko_btc_history(days=365):
    """Fetch BTC daily prices from CoinGecko."""
    url = f"https://api.coingecko.com/api/v3/coins/bitcoin/market_chart?vs_currency=usd&days={days}&interval=daily"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read())
    prices = []
    for ts_ms, price in data.get("prices", []):
        dt = datetime.utcfromtimestamp(ts_ms / 1000)
        prices.append({"date": dt.strftime("%Y-%m-%d"), "price": price})
    return prices


def merge_by_date(series_list, keys):
    """Merge multiple series by date string."""
    merged = {}
    for series, key in zip(series_list, keys):
        for point in series:
            d = point["date"]
            if d not in merged:
                merged[d] = {"date": d}
            merged[d][key] = point.get(key)
    return sorted(merged.values(), key=lambda x: x["date"])


def compute_forward_returns(data, horizons=(1, 3, 7, 14)):
    prices = [(d["date"], d.get("price")) for d in data]
    for i, row in enumerate(data):
        for h in horizons:
            if i + h < len(prices) and prices[i][1] and prices[i + h][1]:
                row[f"fwd_ret_{h}d"] = (prices[i + h][1] - prices[i][1]) / prices[i][1] * 100
            else:
                row[f"fwd_ret_{h}d"] = None
    return data


def backtest_quintiles(data, signal_key, horizon=7):
    """Split signal into quintiles, measure forward returns per quintile."""
    valid = [d for d in data if d.get(signal_key) is not None and d.get(f"fwd_ret_{horizon}d") is not None]
    if len(valid) < 20:
        return None
    valid.sort(key=lambda x: x[signal_key])
    n = len(valid)
    qs = n // 5
    results = {}
    for q in range(5):
        start = q * qs
        end = (q + 1) * qs if q < 4 else n
        chunk = valid[start:end]
        returns = [c[f"fwd_ret_{horizon}d"] for c in chunk]
        lo, avg, hi = bootstrap_ci(returns, n_boot=5000)
        vals = [c[signal_key] for c in chunk]
        results[f"Q{q+1}"] = {
            "n": len(chunk),
            "range": f"{min(vals)}-{max(vals)}",
            "avg_return": avg,
            "ci95": (lo, hi),
            "wr": sum(1 for r in returns if r > 0) / len(returns) if returns else 0,
        }
    return results


def backtest_signal(data, fn, horizon=7):
    valid = [d for d in data if d.get(f"fwd_ret_{horizon}d") is not None and fn(d)]
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
    parser = argparse.ArgumentParser(description="D20 — Sentiment + Trends signal scan")
    parser.add_argument("--days", type=int, default=365)
    parser.add_argument("--horizon", type=int, default=7)
    args = parser.parse_args()

    print("=" * 100)
    print(f"D20 — Sentiment + Trends Scan | {args.days} dias | horizonte={args.horizon}d")
    print("=" * 100)

    # 1. Fear & Greed
    print("\n[1/3] Fetching Fear & Greed Index...")
    try:
        fg_data = fetch_fear_greed(args.days)
        print(f"  OK: {len(fg_data)} dias | {fg_data[0]['date']} -> {fg_data[-1]['date']}")
        print(f"  Range: {min(d['fg'] for d in fg_data)}-{max(d['fg'] for d in fg_data)} | Classes: {set(d['class'] for d in fg_data)}")
    except Exception as e:
        print(f"  ERRO: {e}")
        sys.exit(1)

    # 2. Google Trends
    print("\n[2/3] Fetching Google Trends ('bitcoin')...")
    trends_data = fetch_google_trends("bitcoin", "today 12-m")
    if trends_data:
        print(f"  OK: {len(trends_data)} semanas")
    else:
        print("  SEM dados de Google Trends (continuando apenas com F&G)")

    # 3. BTC price
    print("\n[3/3] Fetching BTC price from CoinGecko...")
    try:
        prices = fetch_coingecko_btc_history(args.days)
        print(f"  OK: {len(prices)} dias")
    except Exception as e:
        print(f"  ERRO: {e}")
        sys.exit(1)

    # Merge
    series = [prices, fg_data]
    keys = ["price", "fg"]
    if trends_data:
        series.append(trends_data)
        keys.append("trends")
    data = merge_by_date(series, keys)
    data = compute_forward_returns(data, horizons=(1, 3, 7, 14))
    valid_fg = sum(1 for d in data if d.get("fg") is not None and d.get(f"fwd_ret_{args.horizon}d") is not None)
    print(f"\nMerge: {len(data)} dias, {valid_fg} com F&G + forward return")

    # F&G Quintile analysis
    print("\n" + "=" * 80)
    print("FEAR & GREED QUINTIL ANALYSIS")
    print("=" * 80)
    for h in (1, 3, 7, 14):
        results = backtest_quintiles(data, "fg", horizon=h)
        if results:
            print(f"\nHorizonte: {h}d")
            print(f"  {'Quintil':<8} {'N':<6} {'F&G range':<16} {'Retorno%':<12} {'IC95%':<30} {'WR%':<8}")
            print("  " + "-" * 80)
            for q, r in results.items():
                ci_str = f"[{r['ci95'][0]:.2f}%, {r['ci95'][1]:.2f}%]"
                print(f"  {q:<8} {r['n']:<6} {r['range']:<16} {r['avg_return']:<12.2f} {ci_str:<30} {r['wr']*100:<8.1f}")

    # Signal backtests
    print("\n" + "=" * 80)
    print("SIGNAL BACKTESTS — Fear & Greed")
    print("=" * 80)

    signals = [
        ("F&G < 25 (Extreme Fear -> LONG)", lambda d: d.get("fg") is not None and d["fg"] < 25),
        ("F&G < 30 (Fear -> LONG)", lambda d: d.get("fg") is not None and d["fg"] < 30),
        ("F&G > 75 (Extreme Greed -> SHORT)", lambda d: d.get("fg") is not None and d["fg"] > 75),
        ("F&G > 70 (Greed -> SHORT)", lambda d: d.get("fg") is not None and d["fg"] > 70),
        ("F&G < 50 (Below neutral -> LONG)", lambda d: d.get("fg") is not None and d["fg"] < 50),
        ("F&G > 50 (Above neutral -> SHORT)", lambda d: d.get("fg") is not None and d["fg"] > 50),
    ]

    for label, fn in signals:
        for h in (1, 3, 7, 14):
            result = backtest_signal(data, fn, horizon=h)
            if result:
                ci_str = f"[{result['ci95'][0]:.2f}%, {result['ci95'][1]:.2f}%]"
                wr_ci_str = f"[{result['wr_ci'][0]*100:.1f}%, {result['wr_ci'][1]*100:.1f}%]"
                print(f"\n  {label} | {h}d")
                print(f"    N={result['n']} | Retorno={result['avg_return']:.2f}% IC95%{ci_str} | WR={result['wr']*100:.1f}% IC95%{wr_ci_str}")

    # Google Trends analysis
    if trends_data:
        print("\n" + "=" * 80)
        print("GOOGLE TRENDS ANALYSIS")
        print("=" * 80)
        trends_valid = [d for d in data if d.get("trends") is not None and d.get("fwd_ret_7d") is not None]
        if len(trends_valid) > 20:
            trends_vals = [d["trends"] for d in trends_valid]
            t_median = sorted(trends_vals)[len(trends_vals) // 2]
            t_q20 = sorted(trends_vals)[int(len(trends_vals) * 0.2)]
            t_q80 = sorted(trends_vals)[int(len(trends_vals) * 0.8)]

            for label, fn in [
                (f"Trends < Q20 ({t_q20}) -> LONG", lambda d: d.get("trends") is not None and d["trends"] < t_q20),
                (f"Trends > Q80 ({t_q80}) -> SHORT (contrarian)", lambda d: d.get("trends") is not None and d["trends"] > t_q80),
            ]:
                result = backtest_signal(data, fn, horizon=7)
                if result:
                    ci_str = f"[{result['ci95'][0]:.2f}%, {result['ci95'][1]:.2f}%]"
                    print(f"\n  {label} | 7d")
                    print(f"    N={result['n']} | Retorno={result['avg_return']:.2f}% IC95%{ci_str} | WR={result['wr']*100:.1f}%")
        else:
            print("  Dados insuficientes para analise de Trends")

    # Save
    samples = [{"date": d["date"], "price": d.get("price"), "fg": d.get("fg"),
                "fg_class": None, "trends": d.get("trends"), "fwd_ret_7d": d.get("fwd_ret_7d")} for d in data]
    with open("sentiment_signal_samples.json", "w") as f:
        json.dump(samples, f, indent=2)
    print(f"\nAmostras salvas em sentiment_signal_samples.json")

    # Verdict
    print("\n" + "=" * 100)
    print("VEREDITO PRELIMINAR")
    print("=" * 100)

    q_results = backtest_quintiles(data, "fg", horizon=args.horizon)
    if q_results:
        q1 = q_results.get("Q1", {})
        q5 = q_results.get("Q5", {})
        long_edge = q1.get("avg_return", 0) > 0 and q1.get("ci95", (0, 0))[0] > 0
        short_edge = q5.get("avg_return", 0) < 0 and q5.get("ci95", (0, 0))[1] < 0

        if long_edge and short_edge:
            print(f"  SINAL ENCONTRADO: F&G baixo -> retorno positivo, F&G alto -> retorno negativo")
        elif long_edge:
            print(f"  SINAL PARCIAL (long only): F&G baixo -> retorno positivo ({q1['avg_return']:.2f}%)")
        elif short_edge:
            print(f"  SINAL PARCIAL (short only): F&G alto -> retorno negativo ({q5['avg_return']:.2f}%)")
        else:
            print(f"  SEM EDGE: F&G quintis nao separam retornos de forma significativa")
            print(f"    Q1 (low F&G) retorno={q1.get('avg_return', 0):.2f}% IC95%[{q1.get('ci95', (0,0))[0]:.2f}%, {q1.get('ci95', (0,0))[1]:.2f}%]")
            print(f"    Q5 (high F&G) retorno={q5.get('avg_return', 0):.2f}% IC95%[{q5.get('ci95', (0,0))[0]:.2f}%, {q5.get('ci95', (0,0))[1]:.2f}%]")

    print("\n  NOTA: Sentiment signals sao tipicamente fracos e nao acionaveis isoladamente.")
    print("  Para validacao seria necessario: OOS test, combinacao com outros signals,")
    print("  e teste de transaction costs (spread + slippage em exchange).")


if __name__ == "__main__":
    main()
