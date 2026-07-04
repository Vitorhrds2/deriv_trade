"""
D36 — Deribit IV Surface Anomaly Scan

AGGRESSIVE HYPOTHESIS: Deribit options IV surface has local mispricings —
strikes or expiries where IV deviates from the smooth surface. If we find a strike
where IV is too low vs neighbors, buying that option is positive EV.

Test methodology:
  1. Fetch all BTC + ETH option quotes from Deribit
  2. Build IV surface: IV(strike, expiry) for all liquid options
  3. For each option, compute "fair IV" = average of neighboring strikes/expiries
  4. Flag options where |IV - fair_IV| > 2% (mispricing threshold)
  5. Simulate: buy mispriced cheap options, sell rich ones
  6. Check if mispricing persists (real edge) or disappears (stale quotes)

Also tests:
  - IV term structure anomalies (short-dated IV vs long-dated IV)
  - Put-Call IV skew anomalies (put IV vs call IV at same strike)
  - Calendar spread arbitrage (same strike, different expiry)
"""
import json
import math
import urllib.request
from datetime import datetime, timezone
from collections import defaultdict

MISPRICING_THRESHOLD_IV = 2.0  # 2 vol points = 2% IV difference
MIN_OI = 10  # minimum open interest to consider
MIN_VOLUME = 0  # minimum volume
FEE_PCT = 0.03  # Deribit taker fee


def fetch_json(url, timeout=15):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode())


def fetch_options(currency):
    """Fetch all option quotes for a currency from Deribit."""
    url = f"https://www.deribit.com/api/v2/public/get_book_summary_by_currency?currency={currency}&kind=option"
    data = fetch_json(url)
    options = []
    for opt in data.get("result", []):
        name = opt.get("instrument_name", "")
        parts = name.split("-")
        if len(parts) != 4:
            continue

        expiry_str = parts[1]
        strike = float(parts[2])  # strike is 3rd part
        option_type = parts[3]  # C or P is 4th part

        bid = float(opt.get("bid_price", 0) or 0)
        ask = float(opt.get("ask_price", 0) or 0)
        mid = (bid + ask) / 2 if bid > 0 and ask > 0 else 0
        iv = float(opt.get("mark_iv", 0) or 0)
        oi = float(opt.get("open_interest", 0) or 0)
        volume = float(opt.get("volume", 0) or 0)
        underlying_price = float(opt.get("underlying_price", 0) or 0)

        # Parse expiry date (format: 04JUL26)
        try:
            expiry_date = datetime.strptime(expiry_str, "%d%b%y").replace(tzinfo=timezone.utc)
        except:
            continue

        options.append({
            "instrument": name,
            "currency": currency,
            "expiry_str": expiry_str,
            "expiry_date": expiry_date,
            "type": option_type,
            "strike": strike,
            "bid": bid,
            "ask": ask,
            "mid": mid,
            "iv": iv,
            "oi": oi,
            "volume": volume,
            "underlying_price": underlying_price,
        })

    return options


def parse_expiry_days(expiry_date, now=None):
    if now is None:
        now = datetime.now(timezone.utc)
    return (expiry_date - now).total_seconds() / 86400


def build_iv_surface(options):
    """Build IV surface grouped by expiry and strike."""
    surface = defaultdict(lambda: defaultdict(dict))

    for opt in options:
        if opt["iv"] <= 0 or opt["oi"] < MIN_OI:
            continue

        expiry = opt["expiry_str"]
        strike = opt["strike"]
        otype = opt["type"]

        surface[expiry][strike][otype] = opt

    return surface


def find_neighbors(surface, expiry, strike, otype):
    """Find neighboring options in the IV surface."""
    neighbors = []

    # Same expiry, neighboring strikes
    if expiry in surface:
        strikes = sorted(surface[expiry].keys())
        for s in strikes:
            if s != strike and otype in surface[expiry][s]:
                dist = abs(s - strike)
                neighbors.append({
                    "iv": surface[expiry][s][otype]["iv"],
                    "distance": dist,
                    "type": "same_expiry_diff_strike",
                })

    # Same strike, neighboring expiries
    for other_expiry in surface:
        if other_expiry != expiry and strike in surface[other_expiry]:
            if otype in surface[other_expiry][strike]:
                neighbors.append({
                    "iv": surface[other_expiry][strike][otype]["iv"],
                    "distance": 0,
                    "type": "same_strike_diff_expiry",
                })

    return neighbors


def compute_fair_iv(neighbors, max_neighbors=8):
    """Compute fair IV as weighted average of nearest neighbors."""
    if not neighbors:
        return None

    # Sort by distance (closest first)
    neighbors.sort(key=lambda x: x["distance"])
    nearest = neighbors[:max_neighbors]

    # Weight by inverse distance (closer = more weight)
    total_weight = 0
    weighted_iv = 0
    for n in nearest:
        w = 1 / (n["distance"] + 1)  # +1 to avoid div by zero
        weighted_iv += n["iv"] * w
        total_weight += w

    return weighted_iv / total_weight if total_weight > 0 else None


def run_scan():
    print("=" * 80)
    print("D36 — Deribit IV Surface Anomaly Scan")
    print("=" * 80)
    print(f"  Mispricing threshold: {MISPRICING_THRESHOLD_IV} vol points")
    print(f"  Min OI: {MIN_OI} | Fee: {FEE_PCT}%")
    print()

    all_anomalies = []

    for currency in ["BTC", "ETH"]:
        print(f"\n  Fetching {currency} options...")
        options = fetch_options(currency)
        print(f"  Total options: {len(options)}")

        # Filter liquid
        liquid = [o for o in options if o["oi"] >= MIN_OI and o["iv"] > 0 and o["bid"] > 0 and o["ask"] > 0]
        print(f"  Liquid (OI≥{MIN_OI}, bid>0, ask>0): {len(liquid)}")

        if len(liquid) < 20:
            print(f"  Not enough liquid options for {currency}")
            continue

        # Build IV surface
        surface = build_iv_surface(liquid)
        print(f"  Expiries: {len(surface)}")

        # Find anomalies
        anomalies = []
        for expiry_str in surface:
            for strike in surface[expiry_str]:
                for otype in ["C", "P"]:
                    if otype not in surface[expiry_str][strike]:
                        continue

                    opt = surface[expiry_str][strike][otype]
                    iv = opt["iv"]

                    neighbors = find_neighbors(surface, expiry_str, strike, otype)
                    fair_iv = compute_fair_iv(neighbors)

                    if fair_iv is None or fair_iv <= 0:
                        continue

                    deviation = iv - fair_iv  # positive = IV too high, negative = too low

                    if abs(deviation) > MISPRICING_THRESHOLD_IV:
                        dte = parse_expiry_days(opt["expiry_date"])

                        anomaly = {
                            "currency": currency,
                            "instrument": opt["instrument"],
                            "type": otype,
                            "strike": strike,
                            "expiry": expiry_str,
                            "dte": dte,
                            "iv": iv,
                            "fair_iv": fair_iv,
                            "deviation": deviation,
                            "action": "BUY" if deviation < 0 else "SELL",
                            "bid": opt["bid"],
                            "ask": opt["ask"],
                            "mid": opt["mid"],
                            "oi": opt["oi"],
                            "volume": opt["volume"],
                            "underlying": opt["underlying_price"],
                        }
                        anomalies.append(anomaly)

        # Sort by deviation magnitude
        anomalies.sort(key=lambda x: abs(x["deviation"]), reverse=True)

        print(f"\n  Anomalies found: {len(anomalies)}")
        print(f"  {'Instrument':<30s} {'IV':>6s} {'FairIV':>6s} {'Dev':>7s} {'Action':>6s} {'OI':>8s} {'Bid':>8s} {'Ask':>8s}")
        print(f"  {'-'*30} {'-'*6} {'-'*6} {'-'*7} {'-'*6} {'-'*8} {'-'*8} {'-'*8}")

        for a in anomalies[:20]:
            print(f"  {a['instrument']:<30s} {a['iv']:>6.1f} {a['fair_iv']:>6.1f} "
                  f"{a['deviation']:>+7.1f} {a['action']:>6s} {a['oi']:>8.0f} "
                  f"{a['bid']:>8.4f} {a['ask']:>8.4f}")

        all_anomalies.extend(anomalies)

    # Put-Call skew analysis
    print(f"\n{'='*80}")
    print("PUT-CALL IV SKEW ANALYSIS")
    print("=" * 80)

    for currency in ["BTC", "ETH"]:
        options = fetch_options(currency)
        liquid = [o for o in options if o["oi"] >= MIN_OI and o["iv"] > 0]

        # Group by expiry
        by_expiry = defaultdict(list)
        for o in liquid:
            by_expiry[o["expiry_str"]].append(o)

        for expiry, opts in sorted(by_expiry.items()):
            # For each strike, compare call IV vs put IV
            by_strike = defaultdict(dict)
            for o in opts:
                by_strike[o["strike"]][o["type"]] = o

            skew_anomalies = []
            for strike, types in by_strike.items():
                if "C" in types and "P" in types:
                    call_iv = types["C"]["iv"]
                    put_iv = types["P"]["iv"]
                    skew = put_iv - call_iv  # positive = put IV > call IV (normal skew)

                    # Flag if skew is abnormally large or reversed
                    if abs(skew) > 5:  # 5 vol points
                        skew_anomalies.append({
                            "currency": currency,
                            "expiry": expiry,
                            "strike": strike,
                            "call_iv": call_iv,
                            "put_iv": put_iv,
                            "skew": skew,
                            "action": "BUY CALL + SELL PUT" if skew > 5 else "BUY PUT + SELL CALL",
                        })

            if skew_anomalies:
                print(f"\n  {currency} {expiry}: {len(skew_anomalies)} skew anomalies")
                for sa in skew_anomalies[:5]:
                    print(f"    K={sa['strike']:>10.1f} | Call IV={sa['call_iv']:.1f} | "
                          f"Put IV={sa['put_iv']:.1f} | Skew={sa['skew']:+.1f} | {sa['action']}")

    # Summary
    print(f"\n{'='*80}")
    print("SUMMARY")
    print("=" * 80)

    buy_opportunities = [a for a in all_anomalies if a["action"] == "BUY"]
    sell_opportunities = [a for a in all_anomalies if a["action"] == "SELL"]

    print(f"  Total anomalies: {len(all_anomalies)}")
    print(f"  BUY signals (IV too low): {len(buy_opportunities)}")
    print(f"  SELL signals (IV too high): {len(sell_opportunities)}")

    if buy_opportunities:
        print(f"\n  TOP BUY opportunities (cheap IV):")
        for a in buy_opportunities[:5]:
            print(f"    {a['instrument']} | IV={a['iv']:.1f} vs fair={a['fair_iv']:.1f} "
                  f"(dev={a['deviation']:+.1f}) | OI={a['oi']:.0f} | ask={a['ask']:.4f}")

    if sell_opportunities:
        print(f"\n  TOP SELL opportunities (rich IV):")
        for a in sell_opportunities[:5]:
            print(f"    {a['instrument']} | IV={a['iv']:.1f} vs fair={a['fair_iv']:.1f} "
                  f"(dev={a['deviation']:+.1f}) | OI={a['oi']:.0f} | bid={a['bid']:.4f}")

    # Save
    with open("iv_surface_anomaly_scan_results.json", "w") as f:
        json.dump(all_anomalies, f, indent=2, default=str)

    return all_anomalies


if __name__ == "__main__":
    run_scan()
