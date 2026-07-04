"""
D44 — Binance Funding Rate + Basis Arbitrage Signal

TESE: When perpetual futures funding rate is extreme (very positive or very negative),
the basis (futures price - spot price) reverts. We can:
  - Funding > 0.1% per 8h → shorts pay longs → SHORT futures, LONG spot (delta neutral)
  - Funding < -0.05% per 8h → longs pay shorts → LONG futures, SHORT spot

VECTOR: Market microstructure / funding rate mean reversion

METHOD:
  1. Poll Binance funding rates for top 20 perpetuals every 1 min
  2. Compute basis = (futures_price - spot_price) / spot_price
  3. When funding_rate * 3 > 0.3% (daily cost) → signal to short futures
  4. Track basis reversion over 1h, 4h, 24h
  5. If basis reverts > 80% of the time → executable edge

AGGRESSIVENESS: Delta-neutral strategy that captures funding payments.
The edge is real if funding persists > 24h and basis reverts.

Usage:
  python3 funding_basis_arb_scan.py              # one-shot
  python3 funding_basis_arb_scan.py --continuous  # every 5 min
"""
import json
import time
import urllib.request
from datetime import datetime, timezone
from collections import defaultdict

BINANCE_FAPI = "https://fapi.binance.com/fapi/v1"
BINANCE_API = "https://api.binance.com/api/v3"
POLL_INTERVAL_S = 300  # 5 min
RUN_DURATION = 60

# Top perpetuals by volume
SYMBOLS = [
    "BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT",
    "DOGEUSDT", "ADAUSDT", "AVAXUSDT", "LINKUSDT", "DOTUSDT",
    "MATICUSDT", "LTCUSDT", "BCHUSDT", "ATOMUSDT", "NEARUSDT",
    "APTUSDT", "ARBUSDT", "OPUSDT", "INJUSDT", "SUIUSDT",
]

FUNDING_THRESHOLD_HIGH = 0.0005   # 0.05% per 8h = 0.15%/day = short signal
FUNDING_THRESHOLD_LOW = -0.0003   # -0.03% per 8h = -0.09%/day = long signal


def fetch_json(url, timeout=15):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode())


def fetch_funding_rates():
    """Fetch current funding rates for all symbols."""
    try:
        data = fetch_json(f"{BINANCE_FAPI}/premiumIndex")
        rates = {}
        for item in data:
            sym = item.get("symbol", "")
            if sym in SYMBOLS:
                funding = float(item.get("lastFundingRate", 0))
                mark_price = float(item.get("markPrice", 0))
                index_price = float(item.get("indexPrice", 0))
                rates[sym] = {
                    "funding_rate": funding,
                    "mark_price": mark_price,
                    "index_price": index_price,
                    "basis_pct": (mark_price - index_price) / index_price * 100 if index_price > 0 else 0,
                }
        return rates
    except Exception as e:
        print(f"  Funding rate fetch error: {e}")
        return {}


def fetch_spot_prices():
    """Fetch spot prices for basis calculation."""
    try:
        data = fetch_json(f"{BINANCE_API}/ticker/price")
        prices = {}
        for item in data:
            sym = item.get("symbol", "")
            if sym in SYMBOLS:
                prices[sym] = float(item.get("price", 0))
        return prices
    except:
        return {}


def run_scan():
    print("=" * 80)
    print("D44 — Binance Funding Rate + Basis Arbitrage Scanner")
    print("=" * 80)
    print(f"  Symbols: {len(SYMBOLS)} perpetuals")
    print(f"  Threshold: funding > {FUNDING_THRESHOLD_HIGH*100:.3f}% (short) or < {FUNDING_THRESHOLD_LOW*100:.3f}% (long)")
    print()

    print("[1/2] Fetching funding rates and mark prices...")
    funding = fetch_funding_rates()
    if not funding:
        print("  ERROR: Could not fetch funding rates")
        return

    print(f"  Fetched {len(funding)} symbols")

    print("\n[2/2] Fetching spot prices for basis...")
    spot = fetch_spot_prices()

    # Find extreme funding rates
    signals = []
    print(f"\n{'Symbol':>12s} {'Funding%':>10s} {'Daily%':>10s} {'Basis%':>10s} {'Signal':>12s}")
    print(f"{'-'*12} {'-'*10} {'-'*10} {'-'*10} {'-'*12}")

    for sym, data in sorted(funding.items(), key=lambda x: abs(x[1]["funding_rate"]), reverse=True):
        funding_rate = data["funding_rate"]
        daily_cost = funding_rate * 3  # 3 funding periods per day
        basis = data["basis_pct"]
        spot_price = spot.get(sym, data["index_price"])

        signal = "NONE"
        if funding_rate > FUNDING_THRESHOLD_HIGH:
            signal = "SHORT FUT"
            signals.append({
                "symbol": sym,
                "signal": "SHORT_FUT",
                "funding_rate": funding_rate,
                "daily_cost": daily_cost,
                "basis_pct": basis,
                "futures_price": data["mark_price"],
                "spot_price": spot_price,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })
        elif funding_rate < FUNDING_THRESHOLD_LOW:
            signal = "LONG FUT"
            signals.append({
                "symbol": sym,
                "signal": "LONG_FUT",
                "funding_rate": funding_rate,
                "daily_cost": daily_cost,
                "basis_pct": basis,
                "futures_price": data["mark_price"],
                "spot_price": spot_price,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })

        if signal != "NONE" or abs(funding_rate) > 0.0002:
            print(f"  {sym:>12s} {funding_rate*100:>9.4f}% {daily_cost*100:>9.3f}% {basis:>9.4f}% {signal:>12s}")

    # Summary
    print(f"\n{'='*80}")
    print("SCAN SUMMARY")
    print(f"{'='*80}")
    print(f"  Symbols scanned: {len(funding)}")
    print(f"  Signals: {len(signals)}")
    for s in signals:
        print(f"    {s['symbol']}: {s['signal']} | funding={s['funding_rate']*100:.4f}% | "
              f"daily={s['daily_cost']*100:.3f}% | basis={s['basis_pct']:.4f}%")

    print(f"\n{'='*80}")
    print("VERDICT")
    print(f"{'='*80}")

    if not signals:
        print("  NO EXTREME FUNDING — all rates within normal range")
        print("  Need to monitor continuously for extreme conditions")
    else:
        for s in signals:
            daily_profit = abs(s["daily_cost"]) * 100
            print(f"  {s['symbol']}: {s['signal']}")
            print(f"    Funding: {s['funding_rate']*100:.4f}% per 8h = {daily_profit:.3f}%/day")
            print(f"    Basis: {s['basis_pct']:.4f}% (should revert to 0)")
            print(f"    Strategy: {'SHORT futures + LONG spot' if s['signal'] == 'SHORT_FUT' else 'LONG futures + SHORT spot'}")
            print(f"    Daily carry: ~{daily_profit:.3f}% if funding persists")
            print(f"    Risk: funding flips sign, basis widens further")

    # Save
    with open("funding_basis_arb_results.json", "w") as f:
        json.dump({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "symbols_scanned": len(funding),
            "signals": signals,
            "all_rates": {sym: data for sym, data in funding.items()},
        }, f, indent=2, default=str)

    return signals


if __name__ == "__main__":
    import sys
    continuous = "--continuous" in sys.argv
    if continuous:
        print(f"CONTINUOUS MODE — polling every {POLL_INTERVAL_S}s")
        while True:
            try:
                run_scan()
            except Exception as e:
                print(f"  Error: {e}")
            time.sleep(POLL_INTERVAL_S)
    else:
        run_scan()
