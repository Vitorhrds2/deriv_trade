"""
D22 — CEX liquidation cascade scan (historical approach).

Hipotese: grandes movimentos de preco em curto prazo (proxy para liquidation cascades)
predizem reversoes. Quando BTC cai >X% em 1-5 minutos, tende a reverter (bounce).
Quando sobe >X% rapidamente, tende a cair (pullback).

Mecanismo:
- Liquidation cascade: preco cai -> longs liquidados -> selling pressure -> mais queda
- Apos cascade exaustivo, preco tende a reverter (oversold)
- Simetrico para short squeeze

Data source (gratuito, publico, sem API key):
- Binance Futures REST API: BTCUSDT 1m klines (velas de 1 minuto)
- https://fapi.binance.com/fapi/v1/klines?symbol=BTCUSDT&interval=1m&limit=1500

Teste:
1. Fetch 1500 velas de 1m (~25 horas)
2. Detectar velas com |retorno| > threshold (1σ, 2σ, 3σ acima da media)
3. Medir retorno nos 1m, 5m, 15m, 30m, 60m seguintes
4. Veredito: grandes moves predizem reversao?
"""
import argparse
import json
import sys
import math
import urllib.request
from datetime import datetime

try:
    from stats_utils import bootstrap_ci, wilson_ci
except ImportError:
    print("ERRO: stats_utils.py nao encontrado. Execute do diretorio trading-engine/")
    sys.exit(1)


def fetch_klines(symbol="BTCUSDT", interval="1m", limit=1500):
    """Fetch kline data from Binance Futures REST API (free, no auth)."""
    url = f"https://fapi.binance.com/fapi/v1/klines?symbol={symbol}&interval={interval}&limit={limit}"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read())
    candles = []
    for k in data:
        candles.append({
            "open_time": k[0],
            "open": float(k[1]),
            "high": float(k[2]),
            "low": float(k[3]),
            "close": float(k[4]),
            "volume": float(k[5]),
            "close_time": k[6],
            "time": datetime.utcfromtimestamp(k[0] / 1000).strftime("%Y-%m-%d %H:%M"),
        })
    return candles


def compute_returns(candles):
    """Compute 1-minute returns for each candle."""
    for i in range(1, len(candles)):
        prev_close = candles[i - 1]["close"]
        cur_close = candles[i]["close"]
        if prev_close > 0:
            candles[i]["return_1m"] = (cur_close - prev_close) / prev_close * 100
        else:
            candles[i]["return_1m"] = 0.0
    candles[0]["return_1m"] = 0.0
    return candles


def compute_forward_returns(candles, horizons=(1, 5, 15, 30, 60)):
    """Compute forward returns for each candle at given horizons (in minutes)."""
    for i, c in enumerate(candles):
        for h in horizons:
            if i + h < len(candles):
                fwd_close = candles[i + h]["close"]
                cur_close = c["close"]
                if cur_close > 0:
                    c[f"fwd_{h}m"] = (fwd_close - cur_close) / cur_close * 100
                else:
                    c[f"fwd_{h}m"] = None
            else:
                c[f"fwd_{h}m"] = None
    return candles


def detect_large_moves(candles, threshold_std=2.0):
    """Detect candles with returns > threshold_std standard deviations."""
    returns = [c["return_1m"] for c in candles if c.get("return_1m") is not None]
    if len(returns) < 10:
        return [], [], 0, 0

    mean_ret = sum(returns) / len(returns)
    std_ret = math.sqrt(sum((r - mean_ret) ** 2 for r in returns) / len(returns))

    threshold = mean_ret + threshold_std * std_ret
    threshold_neg = mean_ret - threshold_std * std_ret

    large_up = [c for c in candles if c.get("return_1m") is not None and c["return_1m"] > threshold]
    large_down = [c for c in candles if c.get("return_1m") is not None and c["return_1m"] < threshold_neg]

    return large_up, large_down, mean_ret, std_ret


def analyze_moves(events, label, horizons=(1, 5, 15, 30, 60)):
    """Analyze forward returns after large move events."""
    if not events:
        return

    print(f"\n  {label} | N={len(events)}")
    print(f"    {'Horizon':<10} {'N':<6} {'Retorno%':<12} {'IC95%':<30} {'WR%':<10} {'WR IC95%':<20}")
    print("    " + "-" * 88)

    for h in horizons:
        returns = [c[f"fwd_{h}m"] for c in events if c.get(f"fwd_{h}m") is not None]
        if len(returns) < 3:
            print(f"    {h}m{'':<7} {'insufficient data'}")
            continue

        lo, avg, hi = bootstrap_ci(returns, n_boot=5000)
        wins = sum(1 for r in returns if r > 0)
        wr = wins / len(returns) if returns else 0
        wr_lo, wr_hi = wilson_ci(wins, len(returns))

        ci_str = f"[{lo:.4f}%, {hi:.4f}%]"
        wr_ci_str = f"[{wr_lo*100:.1f}%, {wr_hi*100:.1f}%]"
        print(f"    {h}m{'':<7} {len(returns):<6} {avg:<12.4f} {ci_str:<30} {wr*100:<10.1f} {wr_ci_str:<20}")


def main():
    parser = argparse.ArgumentParser(description="D22 — CEX liquidation cascade scan (historical kline approach)")
    parser.add_argument("--symbol", default="BTCUSDT", help="Binance Futures symbol")
    parser.add_argument("--limit", type=int, default=1500, help="Number of 1m candles (max 1500)")
    parser.add_argument("--threshold-std", type=float, default=2.0, help="Threshold in std devs for 'large move'")
    args = parser.parse_args()

    print("=" * 100)
    print(f"D22 — CEX Liquidation Cascade Scan (Historical) | {args.symbol} | {args.limit} velas 1m | threshold={args.threshold_std}σ")
    print("=" * 100)

    # 1. Fetch klines
    print(f"\n[1/3] Fetching {args.limit} 1m candles from Binance Futures...")
    try:
        candles = fetch_klines(args.symbol, "1m", args.limit)
        print(f"  OK: {len(candles)} velas | {candles[0]['time']} -> {candles[-1]['time']}")
        print(f"  Price: ${candles[0]['close']:.2f} -> ${candles[-1]['close']:.2f}")
    except Exception as e:
        print(f"  ERRO: {e}")
        sys.exit(1)

    # 2. Compute returns
    print("\n[2/3] Computing returns...")
    candles = compute_returns(candles)
    candles = compute_forward_returns(candles, horizons=(1, 5, 15, 30, 60))

    returns = [c["return_1m"] for c in candles if c.get("return_1m") is not None]
    mean_ret = sum(returns) / len(returns)
    std_ret = math.sqrt(sum((r - mean_ret) ** 2 for r in returns) / len(returns))
    max_ret = max(returns)
    min_ret = min(returns)

    print(f"  1m returns: mean={mean_ret:.6f}% std={std_ret:.4f}% max={max_ret:.4f}% min={min_ret:.4f}%")
    print(f"  Threshold {args.threshold_std}σ: >{mean_ret + args.threshold_std * std_ret:.4f}% (up) / <{mean_ret - args.threshold_std * std_ret:.4f}% (down)")

    # 3. Detect and analyze large moves
    print(f"\n[3/3] Detecting large moves (>{args.threshold_std}σ) and analyzing forward returns...")

    # Test multiple thresholds
    print("\n" + "=" * 100)
    print("LARGE MOVE ANALYSIS — proxy for liquidation cascades")
    print("=" * 100)

    for thresh in [1.0, 1.5, 2.0, 2.5, 3.0]:
        large_up, large_down, _, _ = detect_large_moves(candles, thresh)

        print(f"\n{'='*80}")
        print(f"Threshold: {thresh}σ")
        print(f"{'='*80}")

        # Large UP move -> expect PULLBACK (short signal)
        if large_up:
            analyze_moves(large_up, f"Large UP (>{thresh}σ) -> expect PULLBACK")

        # Large DOWN move -> expect BOUNCE (long signal)
        if large_down:
            analyze_moves(large_down, f"Large DOWN (<-{thresh}σ) -> expect BOUNCE")

        if not large_up and not large_down:
            print(f"  Nenhum evento encontrado neste threshold")

    # Volume analysis
    print("\n" + "=" * 100)
    print("VOLUME-WEIGHTED ANALYSIS")
    print("=" * 100)

    # High volume + large down move = likely liquidation cascade
    volumes = [c["volume"] for c in candles]
    vol_median = sorted(volumes)[len(volumes) // 2]
    vol_q80 = sorted(volumes)[int(len(volumes) * 0.8)]

    for thresh in [1.5, 2.0]:
        _, large_down, _, _ = detect_large_moves(candles, thresh)
        if not large_down:
            continue

        high_vol_down = [c for c in large_down if c["volume"] > vol_q80]
        low_vol_down = [c for c in large_down if c["volume"] <= vol_median]

        if high_vol_down:
            analyze_moves(high_vol_down, f"Large DOWN ({thresh}σ) + HIGH VOLUME (>Q80) -> BOUNCE")
        if low_vol_down:
            analyze_moves(low_vol_down, f"Large DOWN ({thresh}σ) + LOW VOLUME (<median) -> BOUNCE")

    # Save samples
    samples = []
    for c in candles:
        row = {
            "time": c["time"],
            "close": c["close"],
            "return_1m": c.get("return_1m"),
            "volume": c["volume"],
            "fwd_5m": c.get("fwd_5m"),
            "fwd_15m": c.get("fwd_15m"),
            "fwd_30m": c.get("fwd_30m"),
            "fwd_60m": c.get("fwd_60m"),
        }
        samples.append(row)
    with open("cex_liquidation_samples.json", "w") as f:
        json.dump(samples, f, indent=2)
    print(f"\nAmostras salvas em cex_liquidation_samples.json")

    # Verdict
    print("\n" + "=" * 100)
    print("VEREDITO PRELIMINAR")
    print("=" * 100)

    found_edges = []
    for thresh in [1.5, 2.0, 2.5, 3.0]:
        large_up, large_down, _, _ = detect_large_moves(candles, thresh)

        # Check bounce after large down
        if large_down:
            for h in [1, 5, 15, 30, 60]:
                returns_fwd = [c[f"fwd_{h}m"] for c in large_down if c.get(f"fwd_{h}m") is not None]
                if len(returns_fwd) >= 3:
                    lo, avg, hi = bootstrap_ci(returns_fwd, n_boot=5000)
                    if lo > 0:
                        found_edges.append(f"DOWN {thresh}σ -> bounce {h}m: +{avg:.4f}% IC95%[{lo:.4f}%, {hi:.4f}%]")

        # Check pullback after large up
        if large_up:
            for h in [1, 5, 15, 30, 60]:
                returns_fwd = [c[f"fwd_{h}m"] for c in large_up if c.get(f"fwd_{h}m") is not None]
                if len(returns_fwd) >= 3:
                    lo, avg, hi = bootstrap_ci(returns_fwd, n_boot=5000)
                    if hi < 0:
                        found_edges.append(f"UP {thresh}σ -> pullback {h}m: {avg:.4f}% IC95%[{lo:.4f}%, {hi:.4f}%]")

    if found_edges:
        print(f"  SINAIS ENCONTRADOS ({len(found_edges)}):")
        for e in found_edges:
            print(f"    {e}")
    else:
        print("  SEM EDGE: grandes movimentos de 1m nao predizem reversao com IC95% > 0")
        print(f"  ({len(candles)} velas de 1m, threshold ate 3σ)")

        # Show best candidate
        best = None
        for thresh in [2.0, 2.5, 3.0]:
            _, large_down, _, _ = detect_large_moves(candles, thresh)
            if large_down:
                for h in [5, 15, 30]:
                    returns_fwd = [c[f"fwd_{h}m"] for c in large_down if c.get(f"fwd_{h}m") is not None]
                    if len(returns_fwd) >= 3:
                        lo, avg, hi = bootstrap_ci(returns_fwd, n_boot=5000)
                        if best is None or avg > best[1]:
                            best = (f"DOWN {thresh}σ -> {h}m: {avg:.4f}% IC95%[{lo:.4f}%, {hi:.4f}%] (N={len(returns_fwd)})", avg)

        if best:
            print(f"  Melhor candidato (nao significante): {best[0]}")

    print(f"\n  NOTA: {args.limit} velas = ~{args.limit//60}h de dados. Para validacao seria necessario:")
    print("  1. Coletar dias/semanas de dados 1m (via multiple fetches ou Binance data archive)")
    print("  2. Distinguir liquidation cascades reais (via WS forceOrder) de grandes moves normais")
    print("  3. Testar com dados de tick (não velas) para capturar moves intra-minuto")
    print("  4. OOS test rigoroso")


if __name__ == "__main__":
    main()
