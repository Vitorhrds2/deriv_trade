"""
D36 — IV Anomaly Reversion Test: Are the anomalies real or stale quotes?

Test methodology:
  1. Fetch current IV for the 6 instruments we have paper positions on
  2. Compare current IV vs entry IV vs fair IV
  3. If IV moved toward fair IV → anomaly is reverting (REAL EDGE)
  4. If IV unchanged → likely stale quote (NO EDGE)
  5. If IV moved away from fair → anomaly widening (could be real dislocation)

Also re-computes fair IV with fresh data to see if the "fair" reference changed.
"""
import json
import urllib.request
from datetime import datetime, timezone
from collections import defaultdict

# The 6 instruments we have paper positions on
POSITIONS = [
    {"instrument": "BTC-25JUN27-70000-C", "direction": "SELL", "entry_iv": 43.2, "fair_iv": 35.6, "entry_price": 0.1430},
    {"instrument": "BTC-31JUL26-82000-P", "direction": "SELL", "entry_iv": 40.4, "fair_iv": 36.6, "entry_price": 0.2855},
    {"instrument": "BTC-25DEC26-62000-C", "direction": "SELL", "entry_iv": 42.6, "fair_iv": 34.8, "entry_price": 0.1340},
    {"instrument": "ETH-25SEP26-1300-C", "direction": "BUY", "entry_iv": 62.0, "fair_iv": 106.2, "entry_price": 0.2995},
    {"instrument": "ETH-10JUL26-1300-C", "direction": "SELL", "entry_iv": 106.8, "fair_iv": 62.6, "entry_price": 0.2685},
    {"instrument": "ETH-31JUL26-1450-C", "direction": "BUY", "entry_iv": 63.7, "fair_iv": 85.6, "entry_price": 0.2065},
]


def fetch_json(url, timeout=15):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode())


def fetch_option_data(currency):
    """Fetch all option quotes for a currency from Deribit."""
    url = f"https://www.deribit.com/api/v2/public/get_book_summary_by_currency?currency={currency}&kind=option"
    data = fetch_json(url)
    options = {}
    for opt in data.get("result", []):
        name = opt.get("instrument_name", "")
        if not name:
            continue
        options[name] = {
            "bid": float(opt.get("bid_price", 0) or 0),
            "ask": float(opt.get("ask_price", 0) or 0),
            "iv": float(opt.get("mark_iv", 0) or 0),
            "oi": float(opt.get("open_interest", 0) or 0),
            "volume": float(opt.get("volume", 0) or 0),
            "underlying": float(opt.get("underlying_price", 0) or 0),
        }
    return options


def build_surface_for_currency(options_dict, currency):
    """Build IV surface from fetched options."""
    surface = defaultdict(lambda: defaultdict(dict))
    for name, opt in options_dict.items():
        parts = name.split("-")
        if len(parts) != 4 or not name.startswith(currency):
            continue
        expiry = parts[1]
        strike = float(parts[2])
        otype = parts[3]
        
        if opt["iv"] <= 0 or opt["oi"] < 10:
            continue
        
        surface[expiry][strike][otype] = {
            "instrument_name": name,
            "iv": opt["iv"],
            "bid": opt["bid"],
            "ask": opt["ask"],
            "oi": opt["oi"],
            "volume": opt["volume"],
        }
    return surface


def compute_fair_iv(surface, expiry, strike, otype):
    """Compute fair IV from neighbors."""
    neighbors = []
    
    if expiry in surface:
        for s in surface[expiry]:
            if s != strike and otype in surface[expiry][s]:
                neighbors.append({"iv": surface[expiry][s][otype]["iv"], "distance": abs(s - strike)})
    
    for other_expiry in surface:
        if other_expiry != expiry and strike in surface[other_expiry]:
            if otype in surface[other_expiry][strike]:
                neighbors.append({"iv": surface[other_expiry][strike][otype]["iv"], "distance": 0})
    
    if not neighbors:
        return None
    
    neighbors.sort(key=lambda x: x["distance"])
    nearest = neighbors[:8]
    total_w = 0
    weighted_iv = 0
    for n in nearest:
        w = 1 / (n["distance"] + 1)
        weighted_iv += n["iv"] * w
        total_w += w
    return weighted_iv / total_w if total_w > 0 else None


def run_test():
    print("=" * 80)
    print("D36 — IV Anomaly Reversion Test")
    print("=" * 80)
    print(f"  Checking {len(POSITIONS)} paper positions for IV reversion")
    print(f"  If IV moved toward fair → REAL EDGE (anomaly reverting)")
    print(f"  If IV unchanged → STALE QUOTE (no real mispricing)")
    print()
    
    # Fetch current data
    btc_options = fetch_option_data("BTC")
    eth_options = fetch_option_data("ETH")
    
    btc_surface = build_surface_for_currency(btc_options, "BTC")
    eth_surface = build_surface_for_currency(eth_options, "ETH")
    
    print(f"  {'Instrument':<30s} {'Dir':>5s} {'Entry IV':>8s} {'Fair IV':>8s} {'Now IV':>8s} {'Now Fair':>8s} {'Dev Now':>8s} {'Verdict':>12s}")
    print(f"  {'-'*30} {'-'*5} {'-'*8} {'-'*8} {'-'*8} {'-'*8} {'-'*8} {'-'*12}")
    
    results = []
    real_edge_count = 0
    stale_count = 0
    widened_count = 0
    
    for pos in POSITIONS:
        instrument = pos["instrument"]
        currency = "BTC" if instrument.startswith("BTC") else "ETH"
        options = btc_options if currency == "BTC" else eth_options
        surface = btc_surface if currency == "BTC" else eth_surface
        
        current = options.get(instrument, {})
        current_iv = current.get("iv", 0)
        current_bid = current.get("bid", 0)
        current_ask = current.get("ask", 0)
        current_oi = current.get("oi", 0)
        
        # Parse instrument to get expiry/strike/type
        parts = instrument.split("-")
        expiry = parts[1]
        strike = float(parts[2])
        otype = parts[3]
        
        # Recompute fair IV with fresh data
        new_fair_iv = compute_fair_iv(surface, expiry, strike, otype)
        if new_fair_iv is None:
            new_fair_iv = pos["fair_iv"]  # fallback to old fair
        
        entry_iv = pos["entry_iv"]
        old_fair = pos["fair_iv"]
        entry_dev = entry_iv - old_fair
        current_dev = current_iv - new_fair_iv
        
        # Determine verdict
        if current_iv == 0:
            verdict = "EXPIRED/GONE"
        elif abs(current_dev) < 1.0:
            verdict = "REVERTED"
            real_edge_count += 1
        elif abs(current_dev) < abs(entry_dev):
            verdict = "REVERTING"
            real_edge_count += 1
        elif current_iv == entry_iv:
            verdict = "STALE"
            stale_count += 1
        elif abs(current_dev) > abs(entry_dev):
            verdict = "WIDENED"
            widened_count += 1
        else:
            verdict = "UNCLEAR"
        
        # P&L estimation
        iv_change = current_iv - entry_iv
        if pos["direction"] == "BUY":
            # Bought cheap IV, profit if IV rises
            est_pnl = iv_change * 0.01  # approx vega
        else:
            # Sold rich IV, profit if IV falls
            est_pnl = -iv_change * 0.01
        
        print(f"  {instrument:<30s} {pos['direction']:>5s} {entry_iv:>8.1f} {old_fair:>8.1f} "
              f"{current_iv:>8.1f} {new_fair_iv:>8.1f} {current_dev:>+8.1f} {verdict:>12s}")
        
        results.append({
            "instrument": instrument,
            "direction": pos["direction"],
            "entry_iv": entry_iv,
            "old_fair_iv": old_fair,
            "current_iv": current_iv,
            "new_fair_iv": new_fair_iv,
            "entry_deviation": entry_dev,
            "current_deviation": current_dev,
            "iv_change": iv_change,
            "est_pnl": est_pnl,
            "current_bid": current_bid,
            "current_ask": current_ask,
            "current_oi": current_oi,
            "verdict": verdict,
        })
    
    # Summary
    print(f"\n{'='*80}")
    print("SUMMARY")
    print(f"{'='*80}")
    print(f"  Total positions: {len(POSITIONS)}")
    print(f"  Reverted/Reverting (REAL EDGE): {real_edge_count}")
    print(f"  Stale quotes (NO EDGE): {stale_count}")
    print(f"  Widened (dislocation increasing): {widened_count}")
    
    if real_edge_count > stale_count:
        print(f"\n  *** ANOMALIES ARE REAL — IV is reverting toward fair value ***")
        print(f"  This suggests the IV surface has temporary mispricings that correct.")
        print(f"  Paper bot should capture this edge by settling when dev < 1 vol point.")
    elif stale_count > real_edge_count:
        print(f"\n  *** ANOMALIES ARE STALE QUOTES — IV unchanged, no real mispricing ***")
        print(f"  The 'mispricing' was just outdated mark IV that hasn't been updated.")
        print(f"  Need to filter: only trade when current bid/ask reflect the anomaly.")
    else:
        print(f"\n  MIXED RESULTS — some anomalies real, some stale. Need more data.")
    
    # Save
    with open("iv_anomaly_reversion_test_results.json", "w") as f:
        json.dump(results, f, indent=2)
    
    return results


if __name__ == "__main__":
    run_test()
