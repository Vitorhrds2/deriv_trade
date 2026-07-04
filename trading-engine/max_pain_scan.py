"""
D39 — Options Max Pain Magnet (Deribit expiry day price manipulation)

Tese: No dia de expiry de opções, o preço do underlying tende a gravitar
em direção ao "max pain" strike — o preço onde o máximo de opções expira
worthless, beneficiando option writers (market makers). MMs têm incentivo
e capital para empurrar o preço toward max pain.

Método:
  1. Fetch Deribit options OI para próximo expiry (BTC e ETH)
  2. Computar max pain: para cada possível settlement price, somar
     payout total aos holders. Max pain = preço com menor payout total.
  3. Comparar max pain vs preço atual
  4. Se |preço - max_pain| > 2%, sinal: preço vai mover toward max pain
  5. Backtest histórico: em expiries passados, preço convergiu para max pain?

Aggressiveness: max pain é um fenômeno bem documentado em equities options.
Se funciona em crypto, é edge estrutural (não depende de velocidade).
"""
import json
import math
import urllib.request
from datetime import datetime, timezone
from collections import defaultdict

DERIBIT_BASE = "https://www.deribit.com/api/v2/public"


def fetch_json(url, timeout=15):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode())


def fetch_options(currency="BTC"):
    """Fetch all option data for a currency."""
    url = f"{DERIBIT_BASE}/get_book_summary_by_currency?currency={currency}&kind=option"
    data = fetch_json(url)
    options = []
    for opt in data.get("result", []):
        name = opt.get("instrument_name", "")
        parts = name.split("-")
        if len(parts) != 4:
            continue
        try:
            strike = float(parts[2])
            otype = parts[3]
            expiry_str = parts[1]
            # Parse expiry
            day = int(expiry_str[:2])
            month_str = expiry_str[2:5]
            year = int("20" + expiry_str[5:7])
            months = {"JAN":1,"FEB":2,"MAR":3,"APR":4,"MAY":5,"JUN":6,
                      "JUL":7,"AUG":8,"SEP":9,"OCT":10,"NOV":11,"DEC":12}
            expiry_dt = datetime(year, months[month_str], day, 8, 0, 0, tzinfo=timezone.utc)
        except:
            continue

        oi = float(opt.get("open_interest", 0) or 0)
        if oi <= 0:
            continue

        options.append({
            "instrument": name,
            "currency": currency,
            "expiry_str": expiry_str,
            "expiry_dt": expiry_dt,
            "strike": strike,
            "otype": otype,
            "oi": oi,
            "iv": float(opt.get("mark_iv", 0) or 0),
            "underlying": float(opt.get("underlying_price", 0) or 0),
        })
    return options


def compute_max_pain(options, expiry_str):
    """Compute max pain for a given expiry.
    Max pain = settlement price that minimizes total payout to option holders.
    """
    expiry_opts = [o for o in options if o["expiry_str"] == expiry_str]
    if not expiry_opts:
        return None

    strikes = sorted(set(o["strike"] for o in expiry_opts))
    if not strikes:
        return None

    # For each possible settlement price, compute total holder payout
    pain_by_strike = {}
    
    for settlement in strikes:
        total_payout = 0
        for opt in expiry_opts:
            if opt["otype"] == "C":
                # Call payout: max(S - K, 0) * OI
                payout = max(settlement - opt["strike"], 0) * opt["oi"]
            else:
                # Put payout: max(K - S, 0) * OI
                payout = max(opt["strike"] - settlement, 0) * opt["oi"]
            total_payout += payout
        pain_by_strike[settlement] = total_payout

    # Max pain = strike with minimum total payout
    max_pain = min(pain_by_strike, key=pain_by_strike.get)
    min_payout = pain_by_strike[max_pain]
    
    return {
        "max_pain": max_pain,
        "min_payout": min_payout,
        "pain_curve": {str(k): v for k, v in sorted(pain_by_strike.items())},
    }


def fetch_current_price(currency="BTC"):
    """Fetch current underlying price."""
    perp = f"{currency}-PERPETUAL"
    url = f"{DERIBIT_BASE}/get_index_price?index_name={currency}"
    try:
        data = fetch_json(url)
        return float(data.get("result", {}).get("index_price", 0))
    except:
        # Fallback: use option underlying
        return 0


def run_scan():
    print("=" * 80)
    print("D39 — Options Max Pain Magnet Scanner")
    print("=" * 80)
    print("  Tese: Price gravitates toward max pain on expiry day")
    print("  Method: Compute max pain from Deribit OI, compare to spot")
    print("  Signal: |spot - max_pain| > 2% → trade toward max pain")
    print()

    for currency in ["BTC", "ETH"]:
        print(f"\n{'='*80}")
        print(f"  {currency} Max Pain Analysis")
        print(f"{'='*80}")

        options = fetch_options(currency)
        print(f"  Total options: {len(options)}")

        # Group by expiry
        by_expiry = defaultdict(list)
        for opt in options:
            by_expiry[opt["expiry_str"]].append(opt)

        # Sort expiries by date
        expiry_dates = sorted(by_expiry.keys(), key=lambda e: by_expiry[e][0]["expiry_dt"])
        
        now = datetime.now(timezone.utc)
        
        # Current price
        spot = fetch_current_price(currency)
        if spot == 0 and options:
            spot = options[0]["underlying"]
        print(f"  Current spot: ${spot:,.2f}")

        print(f"\n  {'Expiry':>10s} {'Days':>5s} {'Max Pain':>12s} {'Spot':>12s} {'Diff%':>8s} {'Signal':>15s} {'Total OI':>12s}")
        print(f"  {'-'*10} {'-'*5} {'-'*12} {'-'*12} {'-'*8} {'-'*15} {'-'*12}")

        results = []
        
        for expiry in expiry_dates[:6]:  # next 6 expiries
            expiry_opts = by_expiry[expiry]
            expiry_dt = expiry_opts[0]["expiry_dt"]
            days_to_expiry = (expiry_dt - now).total_seconds() / (24 * 3600)
            
            if days_to_expiry < -1:
                continue

            mp = compute_max_pain(options, expiry)
            if not mp:
                continue

            max_pain = mp["max_pain"]
            total_oi = sum(o["oi"] for o in expiry_opts)
            
            if spot > 0:
                diff_pct = (spot - max_pain) / spot * 100
            else:
                diff_pct = 0

            # Signal
            if days_to_expiry <= 1 and abs(diff_pct) > 2:
                signal = f"→ {'BUY' if max_pain > spot else 'SELL'}"
            elif days_to_expiry <= 7 and abs(diff_pct) > 5:
                signal = f"→ {'BUY' if max_pain > spot else 'SELL'} (weak)"
            else:
                signal = "neutral"

            print(f"  {expiry:>10s} {days_to_expiry:>5.1f} ${max_pain:>10,.0f} ${spot:>10,.2f} {diff_pct:>+7.2f}% {signal:>15s} {total_oi:>10,.0f}")

            results.append({
                "currency": currency,
                "expiry": expiry,
                "expiry_dt": expiry_dt.isoformat(),
                "days_to_expiry": days_to_expiry,
                "max_pain": max_pain,
                "spot": spot,
                "diff_pct": diff_pct,
                "total_oi": total_oi,
                "signal": signal,
                "pain_curve": mp["pain_curve"],
            })

        # Detailed analysis for nearest expiry
        if results:
            nearest = results[0]
            print(f"\n  Nearest expiry detail: {nearest['expiry']} ({nearest['days_to_expiry']:.1f}d)")
            print(f"  Max pain: ${nearest['max_pain']:,.0f} | Spot: ${nearest['spot']:,.2f} | Diff: {nearest['diff_pct']:+.2f}%")
            
            # Show pain curve around max pain
            curve = nearest["pain_curve"]
            mp_strike = nearest["max_pain"]
            nearby = sorted(float(k) for k in curve.keys() if abs(float(k) - mp_strike) / mp_strike < 0.15)
            print(f"\n  Pain curve (strikes near max pain):")
            for s in nearby[:10]:
                payout = curve[str(s)] if str(s) in curve else curve.get(s, 0)
                bar_len = int(payout / max(curve.values()) * 40) if max(curve.values()) > 0 else 0
                marker = " *** MAX PAIN ***" if s == mp_strike else ""
                print(f"    ${s:>10,.0f} | {'#'*bar_len}{marker}")

    # Verdict
    print(f"\n{'='*80}")
    print("VERDICT")
    print(f"{'='*80}")
    
    # Check if any expiry is today/tomorrow with significant diff
    today_signals = [r for r in results if r["days_to_expiry"] <= 1 and abs(r["diff_pct"]) > 2]
    
    if today_signals:
        print(f"  *** EXPIRY DAY SIGNAL DETECTED ***")
        for s in today_signals:
            direction = "BUY" if s["max_pain"] > s["spot"] else "SELL"
            print(f"  {s['currency']}: {direction} | Max pain ${s['max_pain']:,.0f} vs spot ${s['spot']:,.2f} ({s['diff_pct']:+.2f}%)")
        print(f"\n  If price converges to max pain by expiry, edge = {abs(today_signals[0]['diff_pct']):.2f}%")
        print(f"  Less fees (0.1% taker roundtrip) = net {abs(today_signals[0]['diff_pct']) - 0.1:.2f}%")
    else:
        nearest_expiry = min(results, key=lambda r: r["days_to_expiry"]) if results else None
        if nearest_expiry:
            print(f"  Nearest expiry: {nearest_expiry['expiry']} ({nearest_expiry['days_to_expiry']:.1f}d)")
            print(f"  Max pain: ${nearest_expiry['max_pain']:,.0f} | Spot: ${nearest_expiry['spot']:,.2f}")
            print(f"  Diff: {nearest_expiry['diff_pct']:+.2f}% — {'magnet effect expected' if abs(nearest_expiry['diff_pct']) > 2 else 'price near max pain already'}")
        print(f"\n  No expiry-day signal today. Need to track over multiple expiries")
        print(f"  for backtest: does price converge to max pain on expiry days?")

    # Save
    with open("max_pain_scan_results.json", "w") as f:
        json.dump({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "results": results,
        }, f, indent=2, default=str)

    return results


if __name__ == "__main__":
    run_scan()
