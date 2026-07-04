"""
D35 — Funding Rate Prediction Scan

AGGRESSIVE HYPOTHESIS: Binance funding rate (charged every 8h at 00:00/08:00/16:00 UTC)
can be predicted from market signals minutes before it's posted. If we know the direction
before it's official, we can enter positions to collect funding.

Signals to test:
  1. Premium Index (perp vs mark) — Binance publishes this in real-time
  2. Basis (perp vs spot) — wider basis = higher funding likely
  3. Open Interest changes — rising OI + high basis = funding will be high
  4. Recent funding momentum — if last 3 fundings were positive, next likely positive

Test methodology:
  1. Fetch premium index + funding history for top 20 perps
  2. At T-5min before funding time, predict: will funding be > or < recent average?
  3. If predicted positive → go long perp (receive funding when short pays)
     Actually: if funding positive, LONGS pay SHORTS. So go SHORT to collect.
  4. Close position at T+1min after funding. Net = funding collected - fees - slippage

Key insight: premium_index is the REAL-TIME proxy for funding rate.
Binance formula: funding_rate = clamp(premium_index + interest_rate, -0.75%, 0.75%)
So premium_index IS the funding rate before it's posted!
"""
import json
import time
import urllib.request
from datetime import datetime, timezone, timedelta

FEE_PCT = 0.08  # futures taker roundtrip (0.04% x 2)
MIN_FUNDING_TO_TRADE = 0.02  # 0.02% minimum funding to bother (after fees)
TOP_N = 20  # top 20 perps by volume


def fetch_json(url, timeout=10):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode())


def fetch_premium_index():
    """Fetch real-time premium index for all USDT perps."""
    url = "https://fapi.binance.com/fapi/v1/premiumIndex"
    data = fetch_json(url)
    results = {}
    for d in data:
        sym = d["symbol"]
        if sym.endswith("USDT"):
            results[sym] = {
                "mark_price": float(d["markPrice"]),
                "index_price": float(d["indexPrice"]),
                "last_funding_rate": float(d.get("lastFundingRate", 0)),
                "next_funding_time": int(d.get("nextFundingTime", 0)),
                "premium_index": float(d.get("p", 0)),  # THIS is the real-time funding proxy
            }
    return results


def fetch_funding_history(symbol, limit=30):
    """Fetch recent funding rate history."""
    url = f"https://fapi.binance.com/fapi/v1/fundingRate?symbol={symbol}&limit={limit}"
    data = fetch_json(url)
    return [{"time": d["fundingTime"], "rate": float(d["fundingRate"])} for d in data]


def fetch_top_symbols(n=20):
    """Get top USDT perps by volume."""
    url = "https://fapi.binance.com/fapi/v1/ticker/24hr"
    data = fetch_json(url)
    usdt = [d for d in data if d["symbol"].endswith("USDT")]
    usdt.sort(key=lambda x: float(x["quoteVolume"]), reverse=True)
    return [d["symbol"] for d in usdt[:n]]


def fetch_spot_prices():
    url = "https://api.binance.com/api/v3/ticker/price"
    data = fetch_json(url)
    return {d["symbol"]: float(d["price"]) for d in data if d["symbol"].endswith("USDT")}


def run_scan():
    print("=" * 80)
    print("D35 — Funding Rate Prediction Scan")
    print("=" * 80)
    print(f"  Testing if premium_index predicts funding rate")
    print(f"  Binance formula: funding = clamp(premium_index + 0.01%, -0.75%, 0.75%)")
    print(f"  Strategy: at T-5min, if premium > threshold, SHORT to collect positive funding")
    print(f"  Fee: {FEE_PCT}% roundtrip | Min funding: {MIN_FUNDING_TO_TRADE}%")
    print()

    top_syms = fetch_top_symbols(TOP_N)
    print(f"  Top {len(top_syms)} symbols: {', '.join(top_syms[:5])}...")

    # Fetch current premium index
    premiums = fetch_premium_index()
    spot_prices = fetch_spot_prices()

    print(f"\n  Current premium index (real-time funding proxy):")
    print(f"  {'Symbol':<14s} {'Premium%':>10s} {'Last Fund%':>10s} {'Basis%':>10s} {'Next Funding':>20s}")
    print(f"  {'-'*14} {'-'*10} {'-'*10} {'-'*10} {'-'*20}")

    opportunities = []
    now = datetime.now(timezone.utc)

    for sym in top_syms:
        if sym not in premiums or sym not in spot_prices:
            continue

        p = premiums[sym]
        spot = spot_prices[sym]
        mark = p["mark_price"]
        premium_pct = p["premium_index"] * 100
        last_fund_pct = p["last_funding_rate"] * 100
        basis_pct = (mark - spot) / spot * 100

        next_fund_ts = p["next_funding_time"]
        if next_fund_ts > 0:
            next_fund = datetime.fromtimestamp(next_fund_ts / 1000, tz=timezone.utc)
            time_to_fund = next_fund - now
            time_str = f"{time_to_fund.total_seconds()/3600:.1f}h"
        else:
            time_str = "N/A"

        # Predicted funding = premium_index + 0.01% (interest rate)
        predicted_funding_pct = premium_pct + 0.01

        # Strategy: if predicted funding > fees, SHORT to collect
        if abs(predicted_funding_pct) > MIN_FUNDING_TO_TRADE + FEE_PCT:
            if predicted_funding_pct > 0:
                # Positive funding: longs pay shorts → go SHORT to collect
                side = "SHORT"
                profit_pct = predicted_funding_pct - FEE_PCT
            else:
                # Negative funding: shorts pay longs → go LONG to collect
                side = "LONG"
                profit_pct = abs(predicted_funding_pct) - FEE_PCT

            opportunities.append({
                "symbol": sym,
                "side": side,
                "premium_pct": premium_pct,
                "predicted_funding_pct": predicted_funding_pct,
                "last_funding_pct": last_fund_pct,
                "basis_pct": basis_pct,
                "profit_pct": profit_pct,
                "time_to_funding": time_str,
                "annualized_pct": profit_pct * 3 * 365,  # 3 fundings/day
            })

        print(f"  {sym:<14s} {premium_pct:>+10.4f} {last_fund_pct:>+10.4f} {basis_pct:>+10.4f} {time_str:>20s}")

    # Sort by profit
    opportunities.sort(key=lambda x: x["profit_pct"], reverse=True)

    print(f"\n{'='*80}")
    print(f"OPPORTUNITIES (predicted funding > fees)")
    print(f"{'='*80}")

    if not opportunities:
        print("  No opportunities right now. Premium index is too small to cover fees.")
    else:
        print(f"  {'Symbol':<14s} {'Side':<6s} {'Pred.Fund%':>10s} {'Profit%':>10s} {'Annual%':>10s} {'To Fund':>10s}")
        print(f"  {'-'*14} {'-'*6} {'-'*10} {'-'*10} {'-'*10} {'-'*10}")
        for o in opportunities:
            print(f"  {o['symbol']:<14s} {o['side']:<6s} {o['predicted_funding_pct']:>+10.4f} "
                  f"{o['profit_pct']:>+10.4f} {o['annualized_pct']:>+10.1f} {o['time_to_funding']:>10s}")

    # Now test historical accuracy: does premium_index predict actual funding?
    print(f"\n{'='*80}")
    print("HISTORICAL ACCURACY TEST")
    print("=" * 80)

    correct = 0
    total = 0
    test_results = []

    for sym in top_syms[:10]:
        try:
            history = fetch_funding_history(sym, limit=30)
            if len(history) < 5:
                continue

            # Check: does last_funding_rate direction match premium_index direction?
            p = premiums.get(sym, {})
            current_premium = p.get("premium_index", 0)
            last_fund = p.get("last_funding_rate", 0)

            # The REAL test: fetch funding history and compare each funding with
            # the premium index that preceded it (we can't get historical premium,
            # but we can test if funding rates are autocorrelated / predictable)
            rates = [h["rate"] for h in history]

            # Test momentum: if last 3 fundings were positive, is next positive?
            for i in range(3, len(rates)):
                last3_positive = all(r > 0 for r in rates[i-3:i])
                last3_negative = all(r < 0 for r in rates[i-3:i])
                actual_positive = rates[i] > 0

                if last3_positive:
                    total += 1
                    if actual_positive:
                        correct += 1
                elif last3_negative:
                    total += 1
                    if not actual_positive:
                        correct += 1

            # Also test: is current premium_index direction = last_funding direction?
            if current_premium != 0 and last_fund != 0:
                match = (current_premium > 0) == (last_fund > 0)
                test_results.append({
                    "symbol": sym,
                    "premium_direction": "POS" if current_premium > 0 else "NEG",
                    "last_fund_direction": "POS" if last_fund > 0 else "NEG",
                    "match": match,
                })

        except Exception as e:
            print(f"  Error fetching history for {sym}: {e}")

    if total > 0:
        momentum_accuracy = correct / total * 100
        print(f"\n  Momentum test (last 3 fundings predict next):")
        print(f"    Accuracy: {momentum_accuracy:.1f}% | N={total}")
        if momentum_accuracy > 60:
            print(f"    *** FUNDING MOMENTUM IS REAL — predictable from history ***")
        elif momentum_accuracy > 55:
            print(f"    Weak signal — may be tradeable with low fees")
        else:
            print(f"    No momentum edge — funding direction is not autocorrelated")

    if test_results:
        matches = sum(1 for t in test_results if t["match"])
        print(f"\n  Premium index vs last funding direction:")
        print(f"    Match rate: {matches}/{len(test_results)} = {matches/len(test_results)*100:.1f}%")
        print(f"    (Premium index is the real-time funding proxy — if it matches,")
        print(f"     we can predict funding direction minutes before it's posted)")

    # Save
    with open("funding_prediction_scan_results.json", "w") as f:
        json.dump({
            "opportunities": opportunities,
            "momentum_accuracy": correct / total * 100 if total > 0 else None,
            "momentum_n": total,
            "premium_match_rate": matches / len(test_results) * 100 if test_results else None,
        }, f, indent=2)

    return opportunities


if __name__ == "__main__":
    run_scan()
