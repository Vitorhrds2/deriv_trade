"""
D30 — Stablecoin Depeg Mean Reversion

Stablecoins (USDC, USDT, DAI, FRAX) trade near $1.00 but occasionally depeg.
When price < $1.00, buying and waiting for reversion is a mean-reversion trade.
When price > $1.00, shorting (if possible) or selling is the play.

Key question: how often do depegs revert, how fast, and is the profit > fees?

Data sources (all free):
  - Binance: USDCUSDT, FDUSDUSDT, TUSDUSDT spot pairs (proxy for stablecoin vs USDT)
  - Coinbase: not easily fetchable without auth
  - Kraken: public ticker API for USDC/USD, USDT/USD, DAI/USD

Scan: fetch historical klines for stablecoin pairs, identify depeg events
(|price - 1.0| > threshold), measure time-to-reversion and profit.

Usage:
  python3 stablecoin_depeg_scan.py
  python3 stablecoin_depeg_scan.py --threshold 0.005 --days 365
"""
import argparse
import json
import sys
import urllib.request
from datetime import datetime, timezone

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


def fetch_klines(symbol, interval="1h", limit=2160):
    """Fetch hourly klines (up to 90 days)."""
    url = f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval={interval}&limit={limit}"
    data = fetch_json(url)
    candles = []
    for k in data:
        candles.append({
            "ts": k[0],
            "open": float(k[1]),
            "high": float(k[2]),
            "low": float(k[3]),
            "close": float(k[4]),
            "volume": float(k[5]),
        })
    return candles


def fetch_kraken_ticker(pair):
    """Fetch Kraken ticker for stablecoin vs USD."""
    url = f"https://api.kraken.com/0/public/Ticker?pair={pair}"
    data = fetch_json(url)
    result = data.get("result", {})
    if not result:
        return None
    key = list(result.keys())[0]
    info = result[key]
    return {
        "bid": float(info["b"][0]),
        "ask": float(info["a"][0]),
        "last": float(info["c"][0]),
    }


# Binance stablecoin pairs (stablecoin priced in USDT, which is ~$1)
BINANCE_PAIRS = {
    "USDCUSDT": "USDC",
    "FDUSDUSDT": "FDUSD",
    "TUSDUSDT": "TUSD",
    "USDPUSDT": "USDP",
}

# Kraken pairs (stablecoin vs USD fiat)
KRAKEN_PAIRS = {
    "USDCUSD": "USDCUSDT",
    "USDTUSD": "USDTZUSD",
    "DAIUSD": "DAIUSD",
}


def scan_binance_depeg(threshold_pct=0.3, days=90):
    """Scan Binance stablecoin pairs for depeg events."""
    print(f"\n{'='*80}")
    print(f"D30 — Stablecoin Depeg Mean Reversion (Binance)")
    print(f"{'='*80}")
    print(f"  Threshold: {threshold_pct}% (|price - 1.0| > {threshold_pct/100:.4f})")
    print(f"  History: {days} days (hourly candles)")

    limit = min(days * 24, 2160)
    all_events = []

    for pair, name in BINANCE_PAIRS.items():
        print(f"\n  Fetching {pair} ({name})...")
        try:
            candles = fetch_klines(pair, "1h", limit)
        except Exception as e:
            print(f"    ERRO: {e}")
            continue

        if not candles:
            print(f"    Sem dados")
            continue

        print(f"    {len(candles)} candles | range: {candles[0]['close']:.6f} - {max(c['close'] for c in candles):.6f}")

        threshold = 1.0 + threshold_pct / 100
        threshold_low = 1.0 - threshold_pct / 100

        # Find depeg events: consecutive periods where price deviates > threshold
        events = []
        in_depeg = False
        depeg_start = None
        depeg_direction = None
        max_dev = 0
        entry_price = None

        for c in candles:
            price = c["close"]
            dev = price - 1.0

            if abs(dev) > threshold_pct / 100:
                if not in_depeg:
                    in_depeg = True
                    depeg_start = c["ts"]
                    depeg_direction = "above" if dev > 0 else "below"
                    max_dev = abs(dev)
                    entry_price = price
                else:
                    max_dev = max(max_dev, abs(dev))
            else:
                if in_depeg:
                    # Depeg ended — reverted to within threshold
                    in_depeg = False
                    duration_h = (c["ts"] - depeg_start) / 3600000
                    revert_price = price

                    # Profit: if below (buy entry), profit = revert_price - entry_price
                    # If above (sell/short entry), profit = entry_price - revert_price
                    if depeg_direction == "below":
                        profit_pct = (revert_price - entry_price) / entry_price * 100
                    else:
                        profit_pct = (entry_price - revert_price) / entry_price * 100

                    events.append({
                        "stablecoin": name,
                        "pair": pair,
                        "direction": depeg_direction,
                        "entry_price": entry_price,
                        "revert_price": revert_price,
                        "max_dev_pct": max_dev * 100,
                        "duration_h": duration_h,
                        "profit_pct": profit_pct,
                        "start_ts": depeg_start,
                    })

        # Handle ongoing depeg
        if in_depeg:
            last = candles[-1]
            duration_h = (last["ts"] - depeg_start) / 3600000
            if depeg_direction == "below":
                profit_pct = (last["close"] - entry_price) / entry_price * 100
            else:
                profit_pct = (entry_price - last["close"]) / entry_price * 100
            events.append({
                "stablecoin": name,
                "pair": pair,
                "direction": depeg_direction,
                "entry_price": entry_price,
                "revert_price": last["close"],
                "max_dev_pct": max_dev * 100,
                "duration_h": duration_h,
                "profit_pct": profit_pct,
                "start_ts": depeg_start,
                "ongoing": True,
            })

        print(f"    Depeg events: {len(events)}")
        if events:
            reverted = [e for e in events if not e.get("ongoing") and e["profit_pct"] > 0]
            print(f"    Reverted successfully: {len(reverted)}/{len(events)}")
            if reverted:
                profits = [e["profit_pct"] for e in reverted]
                durations = [e["duration_h"] for e in reverted]
                print(f"    Avg profit: {sum(profits)/len(profits):+.4f}%")
                print(f"    Avg duration: {sum(durations)/len(durations):.1f}h")
                print(f"    Max dev: {max(e['max_dev_pct'] for e in reverted):.4f}%")

        all_events.extend(events)

    # Overall stats
    print(f"\n{'='*80}")
    print(f"ANALISE GERAL — {len(all_events)} eventos de depeg")
    print(f"{'='*80}")

    if not all_events:
        print(f"  Nenhum depeg detectado no período. Threshold pode ser muito alto.")
        return all_events

    reverted = [e for e in all_events if not e.get("ongoing")]
    ongoing = [e for e in all_events if e.get("ongoing")]
    wins = [e for e in reverted if e["profit_pct"] > 0]

    n = len(reverted)
    if n == 0:
        print(f"  Todos os {len(ongoing)} depegs ainda em curso (sem reversão ainda)")
        return all_events

    wr = len(wins) / n * 100
    wr_lo, wr_hi = wilson_ci(len(wins), n)

    profits = [e["profit_pct"] for e in reverted]
    durations = [e["duration_h"] for e in reverted]
    max_devs = [e["max_dev_pct"] for e in reverted]

    lo, mean, hi = bootstrap_ci(profits)

    # Binance spot taker fee: 0.1% roundtrip
    FEE = 0.1
    net_profits = [p - FEE for p in profits]
    net_wins = [p for p in net_profits if p > 0]
    net_wr = len(net_wins) / n * 100

    print(f"  Eventos revertidos: {n}")
    print(f"  Eventos em curso: {len(ongoing)}")
    print(f"\n  Win Rate (gross): {wr:.1f}% | Wilson CI: [{wr_lo*100:.1f}%, {wr_hi*100:.1f}%]")
    print(f"  Win Rate (net of 0.1% fee): {net_wr:.1f}%")
    print(f"\n  Profit (gross): mean={mean:+.4f}% | IC95%: [{lo:+.4f}%, {hi:+.4f}%]")
    net_lo, net_mean, net_hi = bootstrap_ci(net_profits)
    print(f"  Profit (net): mean={net_mean:+.4f}% | IC95%: [{net_lo:+.4f}%, {net_hi:+.4f}%]")
    print(f"\n  Duration: mean={sum(durations)/len(durations):.1f}h | max={max(durations):.1f}h | min={min(durations):.1f}h")
    print(f"  Max deviation: mean={sum(max_devs)/len(max_devs):.4f}% | max={max(max_devs):.4f}%")

    # Per stablecoin
    print(f"\n  Per stablecoin:")
    for name in set(e["stablecoin"] for e in reverted):
        sc_events = [e for e in reverted if e["stablecoin"] == name]
        sc_wins = [e for e in sc_events if e["profit_pct"] > 0]
        sc_profits = [e["profit_pct"] for e in sc_events]
        print(f"    {name}: N={len(sc_events)} WR={len(sc_wins)/len(sc_events)*100:.0f}% "
              f"avg_profit={sum(sc_profits)/len(sc_profits):+.4f}% "
              f"avg_duration={sum(e['duration_h'] for e in sc_events)/len(sc_events):.1f}h")

    # Verdict
    print(f"\n{'='*80}")
    print(f"VEREDITO — D30 Stablecoin Depeg Mean Reversion")
    print(f"{'='*80}")
    if net_wr > 80 and net_lo > 0:
        print(f"  >>> EDGE POTENCIAL: WR net={net_wr:.1f}%, IC95% não cruza zero")
        print(f"  >>> Buy depegged stablecoin, hold until reversion to ~$1.00")
        print(f"  >>> Risco: depeg persistente (SVB/USDC Mar 2023 levou dias)")
        print(f"  >>> Recomendado: paper trade com threshold maior (0.5%+) para edge real")
    elif net_wr > 60:
        print(f"  >>> SINAL FRACO: WR net={net_wr:.1f}% — reverte mas profit pode ser marginal")
        print(f"  >>> Fees de 0.1% comem boa parte do profit em depegs pequenos")
    else:
        print(f"  >>> SEM EDGE. Depegs não revertem com frequência suficiente.")
        print(f"  >>> Ou: threshold muito baixo (ruído), ou depegs persistem.")

    return all_events


def scan_kraken_snapshot():
    """Quick Kraken snapshot for current stablecoin prices."""
    print(f"\n  Kraken snapshot (current prices):")
    for pair, kraken_pair in KRAKEN_PAIRS.items():
        try:
            ticker = fetch_kraken_ticker(kraken_pair)
            if ticker:
                mid = (ticker["bid"] + ticker["ask"]) / 2
                dev = (mid - 1.0) * 100
                print(f"    {pair}: ${mid:.6f} (dev: {dev:+.4f}%) | bid={ticker['bid']:.6f} ask={ticker['ask']:.6f}")
        except Exception as e:
            print(f"    {pair}: ERRO ({e})")


def main():
    ap = argparse.ArgumentParser(description="D30 — Stablecoin Depeg Mean Reversion")
    ap.add_argument("--threshold", type=float, default=0.3, help="Depeg threshold in % (default 0.3)")
    ap.add_argument("--days", type=int, default=90, help="Days of history")
    args = ap.parse_args()

    scan_binance_depeg(threshold_pct=args.threshold, days=args.days)
    scan_kraken_snapshot()


if __name__ == "__main__":
    main()
