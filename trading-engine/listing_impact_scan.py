#!/usr/bin/env python3
"""
D18: Binance Listing Announcement Impact Analysis.

Hypothesis: Binance listing announcements create a price pump for the
listed token. If the effect is large and consistent enough, buying at
listing announcement and selling after a short hold could be profitable.

Two sub-hypotheses:
1. Pre-listing: Buy at announcement, sell at listing time (capture the pump)
2. Post-listing: Buy at listing, sell after 1-7 days (capture post-listing momentum)

Approach:
- Fetch Binance listing announcements from public API
  (https://www.binance.com/bapi/apex/v1/public/apex/cms/article/list/query?type=1)
- Parse token symbols from announcement titles
- Fetch price data for listed tokens from Binance
- Analyze price performance in windows around listing time
- Backtest: buy at listing, hold 1h/4h/1d/3d/7d, calculate returns

All data via Binance public API. Read-only.
"""
import argparse
import json
import math
import os
import re
import time
import urllib.request
from datetime import datetime, timezone

BINANCE_API = "https://api.binance.com/api/v3"
BINANCE_ANNOUNCE = "https://www.binance.com/bapi/apex/v1/public/apex/cms/article/list/query"
UA = {"User-Agent": "Mozilla/5.0 (research; read-only)"}


def http_get(url, timeout=15):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


def fetch_listing_announcements(pages=10, page_size=50):
    """Fetch Binance listing announcements from public API."""
    all_articles = []
    for page in range(1, pages + 1):
        url = f"{BINANCE_ANNOUNCE}?type=1&pageNo={page}&pageSize={page_size}"
        try:
            data = http_get(url)
            if data.get("data") and data["data"].get("catalogs"):
                for catalog in data["data"]["catalogs"]:
                    for article in catalog.get("articles", []):
                        all_articles.append(article)
        except Exception as e:
            print(f"    Error fetching page {page}: {e}")
            break
        time.sleep(0.3)

    return all_articles


def parse_symbol_from_title(title):
    """Extract trading pair symbol from announcement title.
    Examples:
    'Binance Will List XXX (XXX)' → XXXUSDT
    'Binance Futures Will Launch USDⓈ-Margined XXXUSDT Perpetual Contract' → XXXUSDT
    """
    # Pattern 1: "Binance Will List XXX (XXX)" → spot listing
    m = re.search(r'(?:Will List|Lists)\s+\w+\s*\((\w+)\)', title)
    if m:
        token = m.group(1).upper()
        return f"{token}USDT", "spot"

    # Pattern 2: "XXXUSDT Perpetual Contract" → futures listing
    m = re.search(r'(\w+USDT)\s+Perpetual', title)
    if m:
        return m.group(1).upper(), "futures"

    # Pattern 3: "XXX/USDT" pair
    m = re.search(r'(\w+)/USDT', title)
    if m:
        return f"{m.group(1).upper()}USDT", "unknown"

    # Pattern 4: "XXXUSDC" or "XXXUSDT" anywhere
    m = re.search(r'\b(\w{2,10}USDT)\b', title)
    if m:
        return m.group(1).upper(), "unknown"

    return None, None


def fetch_candles(symbol, interval="1h", limit=500, start_time=None, end_time=None):
    """Fetch klines for a symbol."""
    params = f"symbol={symbol}&interval={interval}&limit={limit}"
    if start_time:
        params += f"&startTime={start_time}"
    if end_time:
        params += f"&endTime={end_time}"
    try:
        data = http_get(f"{BINANCE_API}/klines?{params}")
        return [{"ts": c[0], "open": float(c[1]), "high": float(c[2]),
                 "low": float(c[3]), "close": float(c[4]), "volume": float(c[5])} for c in data]
    except Exception:
        return []


def fetch_daily_candles(symbol, start_ms, end_ms):
    """Fetch daily candles between timestamps."""
    all_candles = []
    current_start = start_ms
    while current_start < end_ms:
        params = f"symbol={symbol}&interval=1d&startTime={current_start}&endTime={end_ms}&limit=1000"
        try:
            data = http_get(f"{BINANCE_API}/klines?{params}")
        except Exception:
            break
        if not data:
            break
        for c in data:
            all_candles.append({"ts": c[0], "close": float(c[4]), "open": float(c[1]),
                                "high": float(c[2]), "low": float(c[3]), "volume": float(c[5])})
        if len(data) < 1000:
            break
        current_start = data[-1][0] + 86400000
        time.sleep(0.15)
    return all_candles


def mean(x):
    return sum(x) / len(x) if x else 0


def std(x):
    if len(x) < 2:
        return 0
    m = mean(x)
    return math.sqrt(sum((xi - m) ** 2 for xi in x) / (len(x) - 1))


def run_scan(output_file):
    print("D18: Binance Listing Announcement Impact Analysis")
    print(f"API: Binance public announcements + price data")
    print(f"{'='*80}\n")

    # Fetch announcements
    print("  Fetching Binance listing announcements...")
    articles = fetch_listing_announcements(pages=10, page_size=50)
    print(f"    Got {len(articles)} announcements")

    # Parse symbols
    listings = []
    for article in articles:
        symbol, listing_type = parse_symbol_from_title(article["title"])
        if symbol:
            listings.append({
                "symbol": symbol,
                "type": listing_type,
                "title": article["title"],
                "release_date_ms": article["releaseDate"],
                "release_date": datetime.fromtimestamp(article["releaseDate"] / 1000, tz=timezone.utc).strftime("%Y-%m-%d %H:%M"),
            })

    # Filter: only listings from 2023 onwards (older pairs likely delisted)
    cutoff_ms = int(datetime(2023, 1, 1, tzinfo=timezone.utc).timestamp() * 1000)
    listings = [l for l in listings if l["release_date_ms"] >= cutoff_ms]

    # Deduplicate by symbol (keep earliest listing)
    seen = {}
    for l in listings:
        if l["symbol"] not in seen or l["release_date_ms"] < seen[l["symbol"]]["release_date_ms"]:
            seen[l["symbol"]] = l
    listings = sorted(seen.values(), key=lambda x: x["release_date_ms"])

    print(f"    Parsed {len(listings)} unique listing events")
    print(f"    Types: spot={sum(1 for l in listings if l['type']=='spot')}, "
          f"futures={sum(1 for l in listings if l['type']=='futures')}, "
          f"unknown={sum(1 for l in listings if l['type']=='unknown')}")

    # Show sample
    print(f"\n    Sample listings:")
    for l in listings[:5]:
        print(f"      {l['release_date']} {l['symbol']:15s} [{l['type']}] {l['title'][:60]}...")
    if len(listings) > 5:
        print(f"      ... and {len(listings)-5} more")

    # Fetch BTC benchmark (fetch full recent range in one shot)
    print(f"\n  Fetching BTC benchmark...")
    if listings:
        btc_start = min(l["release_date_ms"] for l in listings) - 7 * 86400000
        btc_end = max(l["release_date_ms"] for l in listings) + 31 * 86400000
    else:
        btc_start = int(datetime(2023, 1, 1, tzinfo=timezone.utc).timestamp() * 1000)
        btc_end = int(datetime(2025, 7, 1, tzinfo=timezone.utc).timestamp() * 1000)
    # Fetch in 1-year chunks to avoid API limits
    btc_candles = []
    chunk_start = btc_start
    while chunk_start < btc_end:
        chunk_end = min(chunk_start + 366 * 86400000, btc_end)
        chunk = fetch_daily_candles("BTCUSDT", chunk_start, chunk_end)
        btc_candles.extend(chunk)
        chunk_start = chunk_end + 86400000
        time.sleep(0.2)
    print(f"    BTC candles: {len(btc_candles)}")

    # Analysis windows (hours after listing)
    hour_windows = [1, 4, 12, 24, 72, 168]  # 1h, 4h, 12h, 1d, 3d, 7d
    day_windows = [1, 3, 7, 14, 30]

    results = []
    errors = 0

    for i, listing in enumerate(listings):
        if (i + 1) % 10 == 0:
            print(f"    Processing {i+1}/{len(listings)}...")

        listing_ts = listing["release_date_ms"]

        # Fetch daily candles around listing (1 day before to 31 days after)
        start_ts = listing_ts - 86400000
        end_ts = listing_ts + 31 * 86400000
        candles_1d = fetch_daily_candles(listing["symbol"], start_ts, end_ts)

        if len(candles_1d) < 3:
            errors += 1
            continue

        # Also try hourly candles for short-term analysis
        candles_1h = fetch_candles(listing["symbol"], "1h", 1000, listing_ts, listing_ts + 7 * 86400000)
        if not candles_1h:
            candles_1h = []

        result = {
            "symbol": listing["symbol"],
            "type": listing["type"],
            "listing_date": listing["release_date"],
            "listing_ts": listing_ts,
            "n_candles_1h": len(candles_1h),
        }

        # Get price at listing time
        if candles_1h:
            # Find first candle at or after listing
            listing_candle = None
            for c in candles_1h:
                if c["ts"] >= listing_ts:
                    listing_candle = c
                    break
            if listing_candle is None:
                listing_candle = candles_1h[0]

            entry_price = listing_candle["open"]
            result["entry_price"] = entry_price

            # Returns at each hourly window
            for w in hour_windows:
                target_ts = listing_ts + w * 3600000
                exit_price = None
                for c in candles_1h:
                    if c["ts"] >= target_ts:
                        exit_price = c["close"]
                        break
                if exit_price is None and candles_1h:
                    exit_price = candles_1h[-1]["close"]
                if exit_price and entry_price:
                    result[f"ret_{w}h"] = (exit_price - entry_price) / entry_price * 100
                else:
                    result[f"ret_{w}h"] = None

        # Daily returns (using daily candles already fetched above)
        if len(candles_1d) >= 2:
            entry_1d = None
            for c in candles_1d:
                if c["ts"] >= listing_ts:
                    entry_1d = c["close"]
                    break
            if entry_1d is None:
                entry_1d = candles_1d[0]["close"]

            for w in day_windows:
                target_ts = listing_ts + w * 86400000
                exit_price = None
                for c in candles_1d:
                    if c["ts"] >= target_ts:
                        exit_price = c["close"]
                        break
                if exit_price is None and candles_1d:
                    exit_price = candles_1d[-1]["close"]
                if exit_price and entry_1d:
                    result[f"ret_{w}d"] = (exit_price - entry_1d) / entry_1d * 100
                else:
                    result[f"ret_{w}d"] = None

            # BTC benchmark
            btc_entry = None
            for c in btc_candles:
                if c["ts"] >= listing_ts:
                    btc_entry = c["close"]
                    break
            if btc_entry is None:
                btc_entry = get_price_at(btc_candles, listing_ts)

            if btc_entry:
                for w in day_windows:
                    target_ts = listing_ts + w * 86400000
                    btc_exit = None
                    for c in btc_candles:
                        if c["ts"] >= target_ts:
                            btc_exit = c["close"]
                            break
                    if btc_exit is None:
                        btc_exit = get_price_at(btc_candles, target_ts)
                    if btc_exit and result.get(f"ret_{w}d") is not None:
                        btc_ret = (btc_exit - btc_entry) / btc_entry * 100
                        result[f"btc_{w}d"] = btc_ret
                        result[f"excess_{w}d"] = result[f"ret_{w}d"] - btc_ret
                    else:
                        result[f"btc_{w}d"] = None
                        result[f"excess_{w}d"] = None

        results.append(result)
        time.sleep(0.2)

    print(f"\n  Processed: {len(results)} listings, {errors} errors (no price data)")

    # ─── Aggregate analysis ──────────────────────────────────────────────────
    print(f"\n{'='*80}")
    print(f"AGGREGATE ANALYSIS\n")

    # Hourly returns (post-listing)
    print(f"  Post-listing returns (hourly):")
    print(f"    {'Window':>8s} {'N':>5s} {'Avg ret':>8s} {'WR':>5s} {'Median':>8s}")
    print("    " + "-" * 35)
    for w in hour_windows:
        rets = [r[f"ret_{w}h"] for r in results if r.get(f"ret_{w}h") is not None]
        if rets:
            wr = sum(1 for r in rets if r > 0) / len(rets) * 100
            med = sorted(rets)[len(rets) // 2]
            print(f"    {w:+8d}h {len(rets):5d} {mean(rets):+7.1f}% {wr:4.0f}% {med:+7.1f}%")

    # Daily returns (post-listing)
    print(f"\n  Post-listing returns (daily, vs BTC):")
    print(f"    {'Window':>8s} {'N':>5s} {'Token':>8s} {'BTC':>8s} {'Excess':>8s} {'WR':>5s} {'t-stat':>7s}")
    print("    " + "-" * 55)
    for w in day_windows:
        rets = [r[f"ret_{w}d"] for r in results if r.get(f"ret_{w}d") is not None]
        excess = [r[f"excess_{w}d"] for r in results if r.get(f"excess_{w}d") is not None]
        btc_rets = [r[f"btc_{w}d"] for r in results if r.get(f"btc_{w}d") is not None]
        if rets:
            wr = sum(1 for r in rets if r > 0) / len(rets) * 100
            m_ex = mean(excess) if excess else 0
            s_ex = std(excess) if excess else 0
            t_stat = m_ex / (s_ex / math.sqrt(len(excess))) if s_ex > 0 and excess else 0
            print(f"    {w:+8d}d {len(rets):5d} {mean(rets):+7.1f}% {mean(btc_rets):+7.1f}% "
                  f"{m_ex:+7.1f}% {wr:4.0f}% {t_stat:6.2f}")

    # Split by listing type
    for label, subset in [("SPOT", [r for r in results if r["type"] == "spot"]),
                          ("FUTURES", [r for r in results if r["type"] == "futures"])]:
        if not subset:
            continue
        print(f"\n  {label} listings ({len(subset)} events):")
        print(f"    {'Window':>8s} {'N':>5s} {'Avg ret':>8s} {'WR':>5s} {'Excess':>8s}")
        print("    " + "-" * 40)
        for w in day_windows:
            rets = [r[f"ret_{w}d"] for r in subset if r.get(f"ret_{w}d") is not None]
            excess = [r[f"excess_{w}d"] for r in subset if r.get(f"excess_{w}d") is not None]
            if rets:
                wr = sum(1 for r in rets if r > 0) / len(rets) * 100
                print(f"    {w:+8d}d {len(rets):5d} {mean(rets):+7.1f}% {wr:4.0f}% "
                      f"{mean(excess):+7.1f}%" if excess else f"    {w:+8d}d {len(rets):5d} {mean(rets):+7.1f}% {wr:4.0f}%")

    # ─── Backtest: buy at listing, hold N days ───────────────────────────────
    print(f"\n{'='*80}")
    print(f"BACKTEST: Buy at listing, hold N days\n")

    fee_bps = 20  # 10 bps per side
    for hold_days in [1, 3, 7]:
        trades = []
        for r in results:
            ret = r.get(f"ret_{hold_days}d")
            if ret is not None:
                pnl_bps = ret * 100 - fee_bps  # convert % to bps, subtract fees
                trades.append({"symbol": r["symbol"], "type": r["type"], "pnl_bps": pnl_bps})

        if trades:
            pnls = [t["pnl_bps"] for t in trades]
            wins = sum(1 for p in pnls if p > 0)
            wr = wins / len(pnls) * 100
            avg = mean(pnls)
            s = std(pnls)
            t_stat = avg / (s / math.sqrt(len(pnls))) if s > 0 else 0

            print(f"  Hold {hold_days}d: N={len(trades)}, WR={wr:.0f}%, avg={avg:+.0f}bps, t-stat={t_stat:.2f}")

    # ─── Short backtest: fade the pump (short at +1h, cover at +24h) ─────────
    print(f"\n  Fade strategy: Short at +1h, cover at +24h")
    fade_trades = []
    for r in results:
        r1h = r.get("ret_1h")
        r24h = r.get("ret_24h")
        if r1h is not None and r24h is not None and r.get("entry_price"):
            # Short return = -(return from 1h to 24h)
            p_1h = r["entry_price"] * (1 + r1h / 100)
            p_24h = r["entry_price"] * (1 + r24h / 100)
            if p_1h > 0:
                short_ret = (p_1h - p_24h) / p_1h * 10000 - fee_bps
                fade_trades.append({"symbol": r["symbol"], "pnl_bps": short_ret})

    if fade_trades:
        pnls = [t["pnl_bps"] for t in fade_trades]
        wins = sum(1 for p in pnls if p > 0)
        wr = wins / len(pnls) * 100
        avg = mean(pnls)
        s = std(pnls)
        t_stat = avg / (s / math.sqrt(len(pnls))) if s > 0 else 0
        print(f"  Fade: N={len(fade_trades)}, WR={wr:.0f}%, avg={avg:+.0f}bps, t-stat={t_stat:.2f}")

    # Save
    output = {
        "n_listings": len(results),
        "n_errors": errors,
        "results": results,
    }
    with open(output_file, "w") as f:
        json.dump(output, f, indent=2, default=str)

    print(f"\n  PROFITABILITY ANALYSIS:")
    print(f"  - Listing announcements are public → market should price them in")
    print(f"  - Key question: is there a post-listing pump that can be captured?")
    print(f"  - Or: does the pump happen pre-listing (buy at announcement)?")
    print(f"  - Fees: {fee_bps}bps round trip (10bps/side)")
    print(f"  - Risk: listing effect may be already arbitraged by faster participants")


def get_price_at(candles, target_ts):
    best = None
    best_diff = float("inf")
    for c in candles:
        diff = abs(c["ts"] - target_ts)
        if diff < best_diff:
            best_diff = diff
            best = c["close"]
    return best


def main():
    parser = argparse.ArgumentParser(description="D18 Binance Listing Impact Analysis")
    parser.add_argument("--output", type=str, default="listing_impact_samples.json")
    args = parser.parse_args()
    output_path = os.path.join(os.path.dirname(__file__), args.output)
    run_scan(output_path)


if __name__ == "__main__":
    main()
