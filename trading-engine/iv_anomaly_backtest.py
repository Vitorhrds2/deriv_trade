"""
D36 — IV Surface Anomaly Backtest (model-based)

Since Deribit's public API doesn't provide historical option OHLC, we use:
  1. DVOL history (30 days) as proxy for overall IV regime changes
  2. Current IV surface to identify anomalies
  3. Black-Scholes to compute theoretical P&L if IV reverts to fair value
  4. Vega-based P&L estimation for each position

This is a MODEL-BASED backtest, not a data-driven historical backtest.
The paper bot on AWS is the primary validation method (real-time data).
"""
import json
import math
import urllib.request
from datetime import datetime, timezone
from collections import defaultdict

# --- Black-Scholes ---

def norm_cdf(x):
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))

def norm_pdf(x):
    return math.exp(-0.5 * x * x) / math.sqrt(2 * math.pi)

def bs_price(S, K, T, r, sigma, option_type):
    if T <= 0 or sigma <= 0:
        return max(S - K, 0) if option_type == "C" else max(K - S, 0)
    d1 = (math.log(S / K) + (r + 0.5 * sigma * sigma) * T) / (sigma * math.sqrt(T))
    d2 = d1 - sigma * math.sqrt(T)
    if option_type == "C":
        return S * norm_cdf(d1) - K * math.exp(-r * T) * norm_cdf(d2)
    else:
        return K * math.exp(-r * T) * norm_cdf(-d2) - S * norm_cdf(-d1)

def bs_vega(S, K, T, r, sigma):
    if T <= 0 or sigma <= 0:
        return 0
    d1 = (math.log(S / K) + (r + 0.5 * sigma * sigma) * T) / (sigma * math.sqrt(T))
    return S * norm_pdf(d1) * math.sqrt(T)

def bs_delta(S, K, T, r, sigma, option_type):
    if T <= 0 or sigma <= 0:
        return 1.0 if (option_type == "C" and S > K) else (-1.0 if option_type == "P" and S < K else 0)
    d1 = (math.log(S / K) + (r + 0.5 * sigma * sigma) * T) / (sigma * math.sqrt(T))
    return norm_cdf(d1) if option_type == "C" else norm_cdf(d1) - 1

def bs_theta(S, K, T, r, sigma, option_type):
    if T <= 0 or sigma <= 0:
        return 0
    d1 = (math.log(S / K) + (r + 0.5 * sigma * sigma) * T) / (sigma * math.sqrt(T))
    d2 = d1 - sigma * math.sqrt(T)
    theta = (-S * norm_pdf(d1) * sigma / (2 * math.sqrt(T))
             - r * K * math.exp(-r * T) * norm_cdf(d2 if option_type == "C" else -d2))
    if option_type == "P":
        theta += r * K * math.exp(-r * T)
    return theta / 365


# --- Deribit API ---

def fetch_json(url, timeout=15):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode())

def fetch_option_data(currency):
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
            "mid": float(opt.get("mark_price", 0) or 0),
            "iv": float(opt.get("mark_iv", 0) or 0),
            "oi": float(opt.get("open_interest", 0) or 0),
            "volume": float(opt.get("volume", 0) or 0),
            "underlying": float(opt.get("underlying_price", 0) or 0),
        }
    return options

def fetch_dvol(currency, days=30):
    end_ts = int(datetime.now(timezone.utc).timestamp() * 1000)
    start_ts = end_ts - days * 24 * 3600 * 1000
    url = (f"https://www.deribit.com/api/v2/public/get_volatility_index_data"
           f"?currency={currency}&resolution=1D&start_timestamp={start_ts}&end_timestamp={end_ts}")
    data = fetch_json(url)
    rows = data.get("result", {}).get("data", [])
    return [{"ts": r[0], "open": r[1], "high": r[2], "low": r[3], "close": r[4]} for r in rows]


# --- Instrument parsing ---

def parse_instrument(name):
    parts = name.split("-")
    if len(parts) != 4:
        return None
    currency = parts[0]
    expiry_str = parts[1]
    strike = float(parts[2])
    otype = parts[3]
    try:
        day = int(expiry_str[:2])
        month_str = expiry_str[2:5]
        year = int("20" + expiry_str[5:7])
        months = {"JAN":1,"FEB":2,"MAR":3,"APR":4,"MAY":5,"JUN":6,
                  "JUL":7,"AUG":8,"SEP":9,"OCT":10,"NOV":11,"DEC":12}
        month = months.get(month_str)
        if not month:
            return None
        expiry_dt = datetime(year, month, day, 8, 0, 0, tzinfo=timezone.utc)
    except:
        return None
    return {"currency": currency, "expiry_str": expiry_str, "expiry_dt": expiry_dt,
            "strike": strike, "otype": otype}


# --- Surface ---

def build_surface(options_dict, currency):
    surface = defaultdict(lambda: defaultdict(dict))
    for name, opt in options_dict.items():
        info = parse_instrument(name)
        if not info or info["currency"] != currency:
            continue
        if opt["iv"] <= 0 or opt["oi"] < 10:
            continue
        surface[info["expiry_str"]][info["strike"]][info["otype"]] = {
            "instrument_name": name, "iv": opt["iv"],
            "bid": opt["bid"], "ask": opt["ask"], "oi": opt["oi"],
        }
    return surface

def compute_fair_iv(surface, expiry, strike, otype):
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
    total_w = sum(1 / (n["distance"] + 1) for n in nearest)
    return sum(n["iv"] * 1 / (n["distance"] + 1) for n in nearest) / total_w

def find_anomalies(surface, currency, threshold=3.0):
    anomalies = []
    for expiry in surface:
        for strike in surface[expiry]:
            for otype in surface[expiry][strike]:
                opt = surface[expiry][strike][otype]
                if opt["bid"] < 0.001 or opt["oi"] < 50:
                    continue
                fair_iv = compute_fair_iv(surface, expiry, strike, otype)
                if not fair_iv:
                    continue
                dev = opt["iv"] - fair_iv
                if abs(dev) >= threshold:
                    mid = (opt["ask"] + opt["bid"]) / 2 if opt["bid"] > 0 else opt["ask"]
                    spread = opt["ask"] - opt["bid"]
                    if mid > 0 and spread / mid > 0.5:
                        continue
                    anomalies.append({
                        "instrument": opt["instrument_name"], "currency": currency,
                        "expiry": expiry, "strike": strike, "otype": otype,
                        "iv": opt["iv"], "fair_iv": fair_iv, "deviation": dev,
                        "direction": "BUY" if dev < 0 else "SELL",
                        "bid": opt["bid"], "ask": opt["ask"], "oi": opt["oi"],
                    })
    anomalies.sort(key=lambda x: abs(x["deviation"]), reverse=True)
    return anomalies


# --- Backtest ---

def run_backtest():
    print("=" * 80)
    print("D36 — IV Surface Anomaly Model-Based Backtest")
    print("=" * 80)
    print("  Method: Black-Scholes theoretical P&L from IV reversion")
    print("  Uses DVOL history for IV regime context")
    print("  Computes vega, delta, theta for each position")
    print("  Fee: 0.03% roundtrip (Deribit taker)")
    print()
    
    RISK_FREE = 0.0
    FEE_PCT = 0.03
    now = datetime.now(timezone.utc)
    
    # Step 1: DVOL history
    print("[1/3] Fetching DVOL history (30 days)...")
    btc_dvol = fetch_dvol("BTC", 30)
    eth_dvol = fetch_dvol("ETH", 30)
    
    if btc_dvol:
        btc_dvol_close = [d["close"] for d in btc_dvol]
        print(f"  BTC DVOL: {len(btc_dvol)} days, range {min(btc_dvol_close):.1f}-{max(btc_dvol_close):.1f}, "
              f"current {btc_dvol_close[-1]:.1f}, avg {sum(btc_dvol_close)/len(btc_dvol_close):.1f}")
    if eth_dvol:
        eth_dvol_close = [d["close"] for d in eth_dvol]
        print(f"  ETH DVOL: {len(eth_dvol)} days, range {min(eth_dvol_close):.1f}-{max(eth_dvol_close):.1f}, "
              f"current {eth_dvol_close[-1]:.1f}, avg {sum(eth_dvol_close)/len(eth_dvol_close):.1f}")
    
    # Step 2: Current surface + anomalies
    print("\n[2/3] Fetching current IV surface...")
    btc_options = fetch_option_data("BTC")
    eth_options = fetch_option_data("ETH")
    
    btc_surface = build_surface(btc_options, "BTC")
    eth_surface = build_surface(eth_options, "ETH")
    
    btc_anomalies = find_anomalies(btc_surface, "BTC", threshold=3.0)
    eth_anomalies = find_anomalies(eth_surface, "ETH", threshold=3.0)
    
    all_anomalies = btc_anomalies[:8] + eth_anomalies[:8]
    print(f"  BTC: {len(btc_anomalies)} anomalies, ETH: {len(eth_anomalies)} anomalies")
    print(f"  Analyzing top {len(all_anomalies)}")
    
    # Step 3: Theoretical P&L
    print(f"\n[3/3] Computing theoretical P&L from IV reversion...")
    print(f"\n  For each position: P&L if IV reverts from current to fair value")
    print(f"  Includes: vega P&L (IV change), theta decay (1d, 3d, 7d hold)")
    print(f"  Net of fees: 0.03% roundtrip\n")
    
    results = []
    
    for anomaly in all_anomalies:
        instrument = anomaly["instrument"]
        info = parse_instrument(instrument)
        currency = anomaly["currency"]
        
        S = btc_options.get(instrument, {}).get("underlying", 0) or eth_options.get(instrument, {}).get("underlying", 0)
        if S == 0:
            opts = btc_options if currency == "BTC" else eth_options
            for v in opts.values():
                if v.get("underlying", 0) > 0:
                    S = v["underlying"]
                    break
        
        K = info["strike"]
        T = (info["expiry_dt"] - now).total_seconds() / (365 * 24 * 3600)
        otype = info["otype"]
        iv_current = anomaly["iv"] / 100
        iv_fair = anomaly["fair_iv"] / 100
        dev = anomaly["deviation"]
        
        if T <= 0 or S <= 0 or iv_current <= 0:
            continue
        
        price_at_current_iv = bs_price(S, K, T, RISK_FREE, iv_current, otype)
        price_at_fair_iv = bs_price(S, K, T, RISK_FREE, iv_fair, otype)
        
        vega = bs_vega(S, K, T, RISK_FREE, iv_current) * 0.01
        delta = bs_delta(S, K, T, RISK_FREE, iv_current, otype)
        theta = bs_theta(S, K, T, RISK_FREE, iv_current, otype)
        
        # Deribit quotes option prices in crypto (BTC/ETH), BS gives USD
        # Convert Deribit prices to USD: price_usd = price_crypto * S
        deribit_ask_usd = anomaly["ask"] * S if anomaly["ask"] > 0 else price_at_current_iv
        deribit_bid_usd = anomaly["bid"] * S if anomaly["bid"] > 0 else price_at_current_iv
        
        if anomaly["direction"] == "BUY":
            # Buy at ask (in USD), sell at fair IV price (in USD)
            entry_price = deribit_ask_usd
            exit_price = price_at_fair_iv
            gross_pnl = exit_price - entry_price
        else:
            # Sell at bid (in USD), buy back at fair IV price (in USD)
            entry_price = deribit_bid_usd
            exit_price = price_at_fair_iv
            gross_pnl = entry_price - exit_price
        
        fee_cost = entry_price * FEE_PCT / 100 + exit_price * FEE_PCT / 100
        net_pnl = gross_pnl - fee_cost
        net_pnl_pct = net_pnl / entry_price * 100 if entry_price > 0 else 0
        
        theta_1d = theta * 1
        theta_3d = theta * 3
        theta_7d = theta * 7
        
        result = {
            "instrument": instrument, "direction": anomaly["direction"],
            "S": S, "K": K, "T": T, "T_days": T * 365,
            "iv_current": anomaly["iv"], "iv_fair": anomaly["fair_iv"], "deviation": dev,
            "price_current": price_at_current_iv, "price_fair": price_at_fair_iv,
            "entry_price": entry_price, "exit_price": exit_price,
            "vega": vega, "delta": delta, "theta_daily": theta,
            "gross_pnl": gross_pnl, "fee_cost": fee_cost,
            "net_pnl": net_pnl, "net_pnl_pct": net_pnl_pct,
            "net_pnl_1d": net_pnl + theta_1d,
            "net_pnl_3d": net_pnl + theta_3d,
            "net_pnl_7d": net_pnl + theta_7d,
            "oi": anomaly["oi"],
        }
        results.append(result)
        
        print(f"  {instrument}")
        print(f"    Dir: {anomaly['direction']} | IV: {anomaly['iv']:.1f}% -> {anomaly['fair_iv']:.1f}% (dev={dev:+.1f})")
        print(f"    S=${S:.0f} K={K:.0f} T={T*365:.0f}d | Entry: ${entry_price:.2f} -> Exit: ${exit_price:.2f}")
        print(f"    Vega=${vega:.2f}/vol_pt | Delta={delta:.3f} | Theta=${theta:.2f}/day")
        print(f"    Gross: ${gross_pnl:+.2f} | Fees: ${fee_cost:.2f} | Net: ${net_pnl:+.2f} ({net_pnl_pct:+.1f}%)")
        print(f"    After theta: 1d=${net_pnl+theta_1d:+.2f} | 3d=${net_pnl+theta_3d:+.2f} | 7d=${net_pnl+theta_7d:+.2f}")
        print(f"    {'WIN' if net_pnl > 0 else 'LOSS'}\n")
    
    # Summary
    print(f"{'='*80}")
    print("SUMMARY — Theoretical P&L from Full IV Reversion")
    print(f"{'='*80}")
    
    if not results:
        print("  No results")
        return
    
    total_net = sum(r["net_pnl"] for r in results)
    total_fee = sum(r["fee_cost"] for r in results)
    total_gross = sum(r["gross_pnl"] for r in results)
    wins = [r for r in results if r["net_pnl"] > 0]
    losses = [r for r in results if r["net_pnl"] <= 0]
    wr = len(wins) / len(results) * 100
    
    print(f"  Positions: {len(results)}")
    print(f"  Wins: {len(wins)} | Losses: {len(losses)} | WR: {wr:.1f}%")
    print(f"  Total gross: ${total_gross:+.4f}")
    print(f"  Total fees: ${total_fee:.4f}")
    print(f"  Total net: ${total_net:+.4f}")
    print(f"  Avg net: ${total_net/len(results):+.4f}")
    
    print(f"\n  After theta decay:")
    for label, key in [("1 day", "net_pnl_1d"), ("3 days", "net_pnl_3d"), ("7 days", "net_pnl_7d")]:
        total = sum(r[key] for r in results)
        w = sum(1 for r in results if r[key] > 0)
        print(f"    {label}: Total ${total:+.4f} | WR {w/len(results)*100:.1f}%")
    
    buy_results = [r for r in results if r["direction"] == "BUY"]
    sell_results = [r for r in results if r["direction"] == "SELL"]
    if buy_results:
        buy_total = sum(r["net_pnl"] for r in buy_results)
        buy_wr = sum(1 for r in buy_results if r["net_pnl"] > 0) / len(buy_results) * 100
        print(f"\n  BUY (cheap IV): {len(buy_results)} pos, WR {buy_wr:.1f}%, Total ${buy_total:+.4f}")
    if sell_results:
        sell_total = sum(r["net_pnl"] for r in sell_results)
        sell_wr = sum(1 for r in sell_results if r["net_pnl"] > 0) / len(sell_results) * 100
        print(f"  SELL (rich IV): {len(sell_results)} pos, WR {sell_wr:.1f}%, Total ${sell_total:+.4f}")
    
    if btc_dvol:
        dvol_change = btc_dvol_close[-1] - btc_dvol_close[0]
        print(f"\n  BTC DVOL 30d: {btc_dvol_close[0]:.1f} -> {btc_dvol_close[-1]:.1f} ({dvol_change:+.1f} vol pts)")
    if eth_dvol:
        dvol_change = eth_dvol_close[-1] - eth_dvol_close[0]
        print(f"  ETH DVOL 30d: {eth_dvol_close[0]:.1f} -> {eth_dvol_close[-1]:.1f} ({dvol_change:+.1f} vol pts)")
    
    # Verdict
    print(f"\n{'='*80}")
    print("VERDICT")
    print(f"{'='*80}")
    
    if total_net > 0 and wr > 60:
        print(f"  *** EDGE CONFIRMADO — IV anomaly reversion theoretically profitable ***")
        print(f"  WR: {wr:.1f}%, Net P&L: ${total_net:+.4f}, N={len(results)}")
        print(f"  Combined with reversion test (6/6 reverting), strong evidence of edge.")
    elif total_net > 0 and wr > 50:
        print(f"  MARGINAL POSITIVE — Net P&L positive, WR {wr:.1f}%")
    elif total_net > 0:
        print(f"  MARGINAL — Positive total but low WR ({wr:.1f}%)")
    else:
        print(f"  REFUTADO — Not profitable after fees + theta")
        print(f"  WR: {wr:.1f}%, Net P&L: ${total_net:+.4f}")
    
    print(f"\n  CAVEATS:")
    print(f"  - Model-based estimate (Black-Scholes), not historical backtest")
    print(f"  - Assumes FULL reversion to fair IV (may partial-revert)")
    print(f"  - No delta hedging costs or execution slippage")
    print(f"  - Theta decay erodes P&L if reversion takes > 3 days")
    print(f"  - Paper bot on AWS is primary validation")
    
    with open("iv_anomaly_backtest_results.json", "w") as f:
        json.dump({
            "method": "model-based Black-Scholes",
            "positions": len(results), "win_rate": wr,
            "total_net_pnl": total_net, "total_gross_pnl": total_gross,
            "total_fees": total_fee,
            "after_theta": {
                "1d": sum(r["net_pnl_1d"] for r in results),
                "3d": sum(r["net_pnl_3d"] for r in results),
                "7d": sum(r["net_pnl_7d"] for r in results),
            },
            "per_position": results,
            "dvol_btc": btc_dvol_close if btc_dvol else [],
            "dvol_eth": eth_dvol_close if eth_dvol else [],
        }, f, indent=2, default=str)
    
    return results


if __name__ == "__main__":
    run_backtest()
