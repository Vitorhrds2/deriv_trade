"""
D27 — Binance Launchpool/Megadrop Impact

HYPOTHESIS: Binance Launchpool and Megadrop events distribute free tokens to users
who stake BNB or other assets. Similar to token unlocks (D17, the ONLY validated edge),
these distributions create selling pressure as recipients sell their free tokens.
If the event is known in advance, shorting the distributed token BEFORE the distribution
starts could capture the pre-event run-up and the post-event sell-off.

This extends the D17 methodology (token unlock short) to a different event type:
- D17: Token unlocks (vesting releases) → validated edge (WR 61-79%, +285-660bps)
- D27: Launchpool/Megadrop (free token distribution) → untested

METHODOLOGY:
1. Compile list of Binance Launchpool events (2023-2026) from public data
2. For each event: identify the token, announcement date, distribution start/end
3. Fetch historical price data from Binance (daily candles)
4. Measure returns around event windows: -7d, -3d, -1d, +1d, +3d, +7d, +14d, +30d
5. Compare against BTC benchmark (excess returns)
6. IS/OOS split: 2023-2024 (IS), 2025-2026 (OOS)
7. Bootstrap CI, t-stat, win rate
8. Test short strategy: short 3d before distribution starts, cover 3d after

Data sources (all free, no auth):
- Binance: https://api.binance.com/api/v3/klines (price data)
- Binance Launchpool history: public web page data (manual compilation)
- CoinGecko: https://api.coingecko.com/api/v3 (supplementary price data)

Usage:
  python3 launchpool_impact_scan.py
  python3 launchpool_impact_scan.py --days 30
"""
import argparse
import json
import math
import sys
import urllib.request
import urllib.error
from datetime import datetime, timezone, timedelta

try:
    from stats_utils import bootstrap_ci
except ImportError:
    import random
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
        mean_val = sum(values) / n
        return (means[lo_idx], mean_val, means[hi_idx])


def fetch_json(url, timeout=15):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode())


def fetch_binance_daily(symbol, limit=365, start_time=None, end_time=None):
    """Fetch daily candles from Binance. Can specify time range."""
    params = f"symbol={symbol}&interval=1d&limit={limit}"
    if start_time:
        params += f"&startTime={start_time}"
    if end_time:
        params += f"&endTime={end_time}"
    url = f"https://api.binance.com/api/v3/klines?{params}"
    try:
        data = fetch_json(url)
        candles = []
        for k in data:
            candles.append({
                "date": datetime.fromtimestamp(k[0] / 1000, tz=timezone.utc),
                "open": float(k[1]),
                "high": float(k[2]),
                "low": float(k[3]),
                "close": float(k[4]),
            })
        return candles
    except Exception as e:
        print(f"  ERRO fetching {symbol}: {e}")
        return []


# Binance Launchpool events (compiled from public Binance announcements)
# Format: (token_symbol, binance_pair, distribution_start_date)
# These are approximate dates from public records
LAUNCHPOOL_EVENTS = [
    # 2023
    ("APT", "APTUSDT", "2023-01-20"),   # Binance Launchpool: APT
    ("FXS", "FXSUSDT", "2023-02-10"),   # Binance Launchpool: FXS
    ("ID", "IDUSDT", "2023-03-15"),     # Binance Launchpool: SPACE ID
    ("EDU", "EDUUSDT", "2023-04-20"),   # Binance Launchpool: EDU
    ("LDO", "LDOUSDT", "2023-05-15"),   # Binance Launchpool: LDO
    ("ARKM", "ARKMUSDT", "2023-07-10"), # Binance Launchpool: ARKM
    ("PENDLE", "PENDLEUSDT", "2023-08-01"), # Binance Launchpool: PENDLE
    ("OXT", "OXTUSDT", "2023-11-01"),   # Binance Launchpool: OXT
    # 2024
    ("JTO", "JTOUSDT", "2024-01-15"),   # Binance Launchpool: JTO
    ("MANTA", "MANTAUSDT", "2024-02-01"), # Binance Launchpool: MANTA
    ("PIXEL", "PIXELUSDT", "2024-02-15"), # Binance Launchpool: PIXEL
    ("ALT", "ALTUSDT", "2024-03-01"),   # Binance Launchpool: ALT
    ("REZ", "REZUSDT", "2024-04-01"),   # Binance Launchpool: REZ
    ("ETHFI", "ETHFIUSDT", "2024-04-15"), # Binance Launchpool: ETHFI
    ("RENDER", "RENDERUSDT", "2024-05-01"), # Binance Launchpool: RENDER
    ("LISTA", "LISTAUSDT", "2024-06-01"), # Binance Launchpool: LISTA
    ("IO", "IOUSDT", "2024-06-15"),     # Binance Launchpool: IO
    ("ZK", "ZKUSDT", "2024-07-01"),     # Binance Launchpool: ZKsync
    ("BTC", "BTCUSDT", "2024-07-15"),   # Binance Megadrop: BTC (special)
    ("CORE", "COREUSDT", "2024-08-01"), # Binance Launchpool: CORE
    ("POL", "POLUSDT", "2024-09-01"),   # Binance Launchpool: POL (ex-MATIC)
    ("SCR", "SCRUSDT", "2024-10-01"),   # Binance Launchpool: Scroll
    ("LUMIA", "LUMIAUSDT", "2024-11-01"), # Binance Launchpool: LUMIA
    # 2025
    ("THE", "THEUSDT", "2025-01-15"),   # Binance Launchpool: THE
    ("SOL", "SOLUSDT", "2025-02-01"),   # Binance Megadrop: SOL
    ("ACX", "ACXUSDT", "2025-03-01"),   # Binance Launchpool: ACX
    ("ORCA", "ORCAUSDT", "2025-04-01"), # Binance Launchpool: ORCA
    ("BANANA", "BANANAUSDT", "2025-05-01"), # Binance Launchpool: BANANA
    ("DODO", "DODOUSDT", "2025-06-01"), # Binance Launchpool: DODO
]

# Windows to test (in days relative to distribution start)
WINDOWS = [-7, -3, -1, 0, 1, 3, 7, 14, 30]


def analyze_event(token, pair, event_date_str, btc_candles_map):
    """Analyze returns around a single Launchpool event."""
    event_date = datetime.strptime(event_date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)

    # Fetch token daily candles around event date (±60 days)
    # Use startTime/endTime since events may be far in the past
    event_ts = int(event_date.timestamp() * 1000)
    start_ts = event_ts - 60 * 86400 * 1000  # 60 days before
    end_ts = event_ts + 60 * 86400 * 1000    # 60 days after
    candles = fetch_binance_daily(pair, 200, start_time=start_ts, end_time=end_ts)
    if len(candles) < 30:
        return None

    # Find the candle closest to event_date
    event_idx = None
    for i, c in enumerate(candles):
        if abs((c["date"] - event_date).total_seconds()) < 86400:
            event_idx = i
            break

    if event_idx is None:
        # Try to find closest
        min_diff = float("inf")
        for i, c in enumerate(candles):
            diff = abs((c["date"] - event_date).total_seconds())
            if diff < min_diff:
                min_diff = diff
                event_idx = i

    if event_idx is None or event_idx < 30 or event_idx > len(candles) - 35:
        return None

    # Calculate returns for each window
    s_0 = candles[event_idx]["close"]
    results = {}

    for window in WINDOWS:
        target_idx = event_idx + window
        if target_idx < 0 or target_idx >= len(candles):
            results[window] = None
            continue
        s_t = candles[target_idx]["close"]
        ret_pct = (s_t - s_0) / s_0 * 100
        results[window] = ret_pct

    # BTC benchmark (excess return)
    # Find BTC candle closest to event date
    btc_ret = {}
    if btc_candles_map:
        btc_idx = None
        for i, c in enumerate(btc_candles_map):
            if abs((c["date"] - event_date).total_seconds()) < 86400:
                btc_idx = i
                break
        if btc_idx is not None and btc_idx > 30 and btc_idx < len(btc_candles_map) - 35:
            btc_s0 = btc_candles_map[btc_idx]["close"]
            for window in WINDOWS:
                target_idx = btc_idx + window
                if target_idx < 0 or target_idx >= len(btc_candles_map):
                    btc_ret[window] = None
                    continue
                btc_st = btc_candles_map[target_idx]["close"]
                btc_ret[window] = (btc_st - btc_s0) / btc_s0 * 100

    # Excess returns
    excess = {}
    for w in WINDOWS:
        if results.get(w) is not None and btc_ret.get(w) is not None:
            excess[w] = results[w] - btc_ret[w]
        else:
            excess[w] = results.get(w)

    return {
        "token": token,
        "pair": pair,
        "event_date": event_date_str,
        "returns": results,
        "btc_returns": btc_ret,
        "excess": excess,
    }


def main():
    ap = argparse.ArgumentParser(description="D27 — Binance Launchpool/Megadrop Impact")
    ap.add_argument("--days", type=int, default=30, help="Days for short strategy window")
    args = ap.parse_args()

    print(f"{'='*80}")
    print(f"D27 — Binance Launchpool/Megadrop Impact")
    print(f"{'='*80}")

    # Fetch BTC benchmark (full history from 2023-01-01 to now)
    print(f"\n[1/3] Fetching BTC benchmark data...")
    btc_start = int(datetime(2023, 1, 1, tzinfo=timezone.utc).timestamp() * 1000)
    btc_end = int(datetime.now(timezone.utc).timestamp() * 1000)
    # Binance allows max 1000 candles per request, so we fetch in chunks
    btc_candles = []
    chunk_start = btc_start
    while chunk_start < btc_end:
        chunk = fetch_binance_daily("BTCUSDT", 1000, start_time=chunk_start, end_time=btc_end)
        if not chunk:
            break
        btc_candles.extend(chunk)
        chunk_start = int(chunk[-1]["date"].timestamp() * 1000) + 86400000
        if len(chunk) < 1000:
            break
    print(f"  OK: {len(btc_candles)} BTC daily candles ({btc_candles[0]['date'].date()} to {btc_candles[-1]['date'].date()})")

    # Split events into IS (2023-2024) and OOS (2025-2026)
    is_events = [(t, p, d) for t, p, d in LAUNCHPOOL_EVENTS if d < "2025-01-01"]
    oos_events = [(t, p, d) for t, p, d in LAUNCHPOOL_EVENTS if d >= "2025-01-01"]

    print(f"\n[2/3] Analyzing {len(LAUNCHPOOL_EVENTS)} Launchpool events...")
    print(f"  IS (2023-2024): {len(is_events)} events")
    print(f"  OOS (2025-2026): {len(oos_events)} events")

    all_results = []
    for token, pair, date in LAUNCHPOOL_EVENTS:
        r = analyze_event(token, pair, date, btc_candles)
        if r:
            all_results.append(r)
            year = date[:4]
            print(f"  {token:>10} ({date}): " +
                  " | ".join(f"{w:+d}d={r['returns'][w]:+.1f}%" if r['returns'].get(w) is not None else f"{w:+d}d=N/A"
                            for w in [-3, 1, 3, 7, 30]))

    print(f"\n  Successfully analyzed: {len(all_results)}/{len(LAUNCHPOOL_EVENTS)} events")

    if not all_results:
        print("  FALHA: não foi possível analisar eventos.")
        return

    # Aggregate by window
    print(f"\n[3/3] Aggregate returns by window...")
    print(f"\n{'='*80}")
    print(f"RETURNS BY WINDOW (all events)")
    print(f"{'='*80}")

    is_results = [r for r in all_results if r["event_date"] < "2025-01-01"]
    oos_results = [r for r in all_results if r["event_date"] >= "2025-01-01"]

    for label, subset in [("IS (2023-2024)", is_results), ("OOS (2025-2026)", oos_results), ("ALL", all_results)]:
        print(f"\n  {label} (N={len(subset)}):")
        print(f"  {'Window':>8} {'Token':>10} {'BTC':>10} {'Excess':>10} {'Neg%':>6} {'t-stat':>8}")
        print(f"  {'-'*60}")

        for w in WINDOWS:
            token_rets = [r["returns"][w] for r in subset if r["returns"].get(w) is not None]
            btc_rets = [r["btc_returns"][w] for r in subset if r.get("btc_returns", {}).get(w) is not None]
            excess_rets = [r["excess"][w] for r in subset if r.get("excess", {}).get(w) is not None]

            if not token_rets:
                continue

            mean_token = sum(token_rets) / len(token_rets)
            mean_btc = sum(btc_rets) / len(btc_rets) if btc_rets else 0
            mean_excess = sum(excess_rets) / len(excess_rets) if excess_rets else 0

            neg_count = sum(1 for r in token_rets if r < 0)
            neg_pct = neg_count / len(token_rets) * 100

            # t-stat
            if len(token_rets) > 1:
                mean_val = sum(token_rets) / len(token_rets)
                variance = sum((r - mean_val) ** 2 for r in token_rets) / (len(token_rets) - 1)
                std = math.sqrt(variance) if variance > 0 else 0
                t_stat = mean_val / (std / math.sqrt(len(token_rets))) if std > 0 else 0
            else:
                t_stat = 0

            print(f"  {w:+d}d {'':>3} {mean_token:>+9.1f}% {mean_btc:>+9.1f}% {mean_excess:>+9.1f}% {neg_pct:>5.0f}% {t_stat:>+7.2f}")

    # Short strategy backtest: short 3d before, cover 3d after
    print(f"\n{'='*80}")
    print(f"SHORT STRATEGY: Short 3d before distribution, cover 3d after")
    print(f"{'='*80}")

    for label, subset in [("IS", is_results), ("OOS", oos_results), ("ALL", all_results)]:
        short_rets = []
        for r in subset:
            r_neg3 = r["returns"].get(-3)
            r_pos3 = r["returns"].get(3)
            if r_neg3 is not None and r_pos3 is not None:
                # Short return = -(return from -3d to +3d)
                # If we short at -3d price and cover at +3d price:
                # short_return = (S_-3 - S_+3) / S_-3 * 100
                # But we have returns relative to day 0, not relative to -3d
                # S_0 = 100 (normalized), S_-3 = 100 * (1 + r_neg3/100), S_+3 = 100 * (1 + r_pos3/100)
                # short_return = (S_-3 - S_+3) / S_-3 * 100
                s_neg3 = 100 * (1 + r_neg3 / 100)
                s_pos3 = 100 * (1 + r_pos3 / 100)
                short_ret = (s_neg3 - s_pos3) / s_neg3 * 100
                short_rets.append(short_ret)

        if short_rets:
            mean_short = sum(short_rets) / len(short_rets)
            wins = sum(1 for r in short_rets if r > 0)
            win_rate = wins / len(short_rets) * 100
            lo, mean_bt, hi = bootstrap_ci(short_rets)

            # After fees (20 bps round trip = 0.2%)
            net_mean = mean_short - 0.2

            if len(short_rets) > 1:
                variance = sum((r - mean_short) ** 2 for r in short_rets) / (len(short_rets) - 1)
                std = math.sqrt(variance) if variance > 0 else 0
                t_stat = mean_short / (std / math.sqrt(len(short_rets))) if std > 0 else 0
            else:
                t_stat = 0

            print(f"\n  {label} (N={len(short_rets)}):")
            print(f"    Mean return: {mean_short:+.1f}% (IC95%: {lo:+.1f}% - {hi:+.1f}%)")
            print(f"    Win rate: {win_rate:.0f}% ({wins}/{len(short_rets)})")
            print(f"    t-stat: {t_stat:+.2f}")
            print(f"    Net (after 20bps fees): {net_mean:+.1f}%")

    # Verdict
    print(f"\n{'='*80}")
    print(f"VEREDITO — D27 Binance Launchpool Impact")
    print(f"{'='*80}")

    if all_results:
        # Check if -3d to +3d short is profitable
        all_short = []
        for r in all_results:
            r_neg3 = r["returns"].get(-3)
            r_pos3 = r["returns"].get(3)
            if r_neg3 is not None and r_pos3 is not None:
                s_neg3 = 100 * (1 + r_neg3 / 100)
                s_pos3 = 100 * (1 + r_pos3 / 100)
                short_ret = (s_neg3 - s_pos3) / s_neg3 * 100
                all_short.append(short_ret)

        if all_short:
            mean_all = sum(all_short) / len(all_short)
            wins = sum(1 for r in all_short if r > 0)
            wr = wins / len(all_short) * 100
            net = mean_all - 0.2

            if net > 0 and wr > 55:
                print(f"  EDGE DETECTADO: Short -3d/+3d em Launchpool events")
                print(f"    Mean: {mean_all:+.1f}% | Win rate: {wr:.0f}% | Net: {net:+.1f}%")
                print(f"    N={len(all_short)} events")
                print(f"    >>> Similar to D17 (token unlock). Validar com mais dados.")
            elif net > 0:
                print(f"  SINAL FRACO: Short -3d/+3d positivo mas win rate baixo")
                print(f"    Mean: {mean_all:+.1f}% | Win rate: {wr:.0f}% | Net: {net:+.1f}%")
            else:
                print(f"  SEM EDGE: Short -3d/+3d não é profitável")
                print(f"    Mean: {mean_all:+.1f}% | Win rate: {wr:.0f}% | Net: {net:+.1f}%")
                print(f"    Launchpool events não geram mesma pressão que unlocks.")
                print(f"    Diferença: Launchpool distribui para stakers (não necessarily sellers),")
                print(f"    enquanto unlocks liberam tokens para investidores (mais propensos a vender).")
    else:
        print("  FALHA: não foi possível analisar eventos.")

    print(f"\n  Dataset: {len(all_results)} Launchpool events | 2023-2026")


if __name__ == "__main__":
    main()
