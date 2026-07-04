"""
D25 — Crypto Options Buy-Side (Inverse VRP)

IMPLICATION FROM D23: D23 showed IV < RV for both BTC (-9.7 vol pts) and ETH (-11.9 vol pts).
In TradFi, IV > RV (sell options for premium). In crypto, the INVERSE is true —
this means BUYING options could be positive EV: pay cheap IV, capture expensive RV.

HYPOTHESIS: Buying ATM straddles (call + put at same strike) on Deribit is profitable
because IV is systematically below RV. A straddle pays off when the underlying moves
significantly in EITHER direction — and if RV > IV, the expected payoff exceeds the cost.

METHODOLOGY:
1. Fetch Deribit ATM options (calls + puts) for nearest liquid expiries
2. Calculate straddle cost = call_ask + put_ask (in USD)
3. Fetch Binance historical klines for the same period
4. Simulate straddle payoff at expiry using historical RV paths:
   - For each historical window matching the option's DTE,
   - Calculate |S_T - S_0| (the payoff of a straddle at expiry)
   - Compare against straddle cost
5. Calculate EV = mean(payoff) - cost, with bootstrap CI
6. Net EV = EV - trading costs (taker fees + bid-ask spread)
7. Test across multiple expiries (7d, 14d, 30d, 60d, 90d)

Data sources (all free, no auth):
- Deribit: https://www.deribit.com/api/v2/public/get_book_summary_by_currency
- Binance: https://api.binance.com/api/v3/klines

Usage:
  python3 options_buy_side_scan.py
  python3 options_buy_side_scan.py --asset BTC --days 90
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


def fetch_deribit_options(currency="BTC"):
    """Fetch Deribit order book summary for all options."""
    url = f"https://www.deribit.com/api/v2/public/get_book_summary_by_currency?currency={currency}&kind=option"
    data = fetch_json(url)
    return data.get("result", [])


def fetch_binance_klines(symbol="BTCUSDT", interval="1d", limit=365):
    """Fetch daily klines from Binance."""
    url = f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval={interval}&limit={limit}"
    data = fetch_json(url)
    candles = []
    for k in data:
        candles.append({
            "open_time": k[0],
            "open": float(k[1]),
            "high": float(k[2]),
            "low": float(k[3]),
            "close": float(k[4]),
            "volume": float(k[5]),
        })
    return candles


def fetch_binance_1h_klines(symbol="BTCUSDT", limit=2160):
    """Fetch 1h klines (90 days)."""
    url = f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval=1h&limit={limit}"
    data = fetch_json(url)
    candles = []
    for k in data:
        candles.append({
            "open_time": k[0],
            "open": float(k[1]),
            "high": float(k[2]),
            "low": float(k[3]),
            "close": float(k[4]),
        })
    return candles


def analyze_straddle_buy(asset="BTC", days_history=90):
    """Main analysis: buy ATM straddle and measure EV using historical paths."""
    binance_sym = f"{asset}USDT"
    deribit_cur = asset

    print(f"\n{'='*80}")
    print(f"D25 — Crypto Options Buy-Side (Inverse VRP) | {asset}")
    print(f"{'='*80}")

    # Step 1: Fetch Deribit options data
    print(f"\n[1/4] Fetching {asset} options from Deribit...")
    options = fetch_deribit_options(deribit_cur)
    if not options:
        print("  ERRO: não foi possível obter opções da Deribit.")
        return None

    # Group by expiry, find ATM calls and puts
    by_expiry = {}
    for opt in options:
        instrument = opt.get("instrument_name", "")
        parts = instrument.split("-")
        if len(parts) != 4:
            continue
        _, expiry_str, strike_str, opt_type = parts
        strike = float(strike_str)
        bid = float(opt.get("bid_price", 0) or 0)
        ask = float(opt.get("ask_price", 0) or 0)
        mid = (bid + ask) / 2 if bid > 0 and ask > 0 else ask
        volume = float(opt.get("volume", 0) or 0)
        oi = float(opt.get("open_interest", 0) or 0)

        if ask <= 0:
            continue

        if expiry_str not in by_expiry:
            by_expiry[expiry_str] = {"calls": [], "puts": []}

        underlying_price = float(opt.get("underlying_price", 0) or 0)

        if opt_type == "C":
            by_expiry[expiry_str]["calls"].append({
                "strike": strike, "bid": bid, "ask": ask, "mid": mid,
                "volume": volume, "oi": oi, "instrument": instrument,
                "underlying_price": underlying_price,
            })
        elif opt_type == "P":
            by_expiry[expiry_str]["puts"].append({
                "strike": strike, "bid": bid, "ask": ask, "mid": mid,
                "volume": volume, "oi": oi, "instrument": instrument,
                "underlying_price": underlying_price,
            })

    # Parse expiry dates and find ATM straddles
    expiries = []
    for exp_str, opts in by_expiry.items():
        calls = opts["calls"]
        puts = opts["puts"]
        if not calls or not puts:
            continue

        # Parse expiry date (format: DDMMMYY e.g. 05JUL26)
        try:
            exp_date = datetime.strptime(exp_str, "%d%b%y").replace(tzinfo=timezone.utc)
        except ValueError:
            continue

        days_to_expiry = (exp_date - datetime.now(timezone.utc)).days
        if days_to_expiry < 1 or days_to_expiry > 120:
            continue

        # Find ATM (strike closest to underlying price from API)
        all_opts = calls + puts
        underlying_price = max((o.get("underlying_price", 0) for o in all_opts), default=0)
        if underlying_price <= 0:
            continue
        all_strikes = {}
        for c in calls:
            s = c["strike"]
            if s not in all_strikes:
                all_strikes[s] = {"call": None, "put": None}
            all_strikes[s]["call"] = c
        for p in puts:
            s = p["strike"]
            if s not in all_strikes:
                all_strikes[s] = {"call": None, "put": None}
            all_strikes[s]["put"] = p

        # Find strikes with both call and put
        valid_strikes = {s: v for s, v in all_strikes.items() if v["call"] and v["put"]}
        if not valid_strikes:
            continue

        # Find ATM strike: closest to underlying price, prefer liquid strikes
        best_strike = min(valid_strikes.keys(),
                         key=lambda s: (abs(s - underlying_price),
                                       -(valid_strikes[s]["call"]["volume"] + valid_strikes[s]["call"]["oi"] +
                                         valid_strikes[s]["put"]["volume"] + valid_strikes[s]["put"]["oi"])))

        call = valid_strikes[best_strike]["call"]
        put = valid_strikes[best_strike]["put"]

        straddle_ask_btc = call["ask"] + put["ask"]  # in BTC per 1 unit
        straddle_bid_btc = call["bid"] + put["bid"]

        expiries.append({
            "expiry": exp_str,
            "exp_date": exp_date,
            "dte": days_to_expiry,
            "strike": best_strike,
            "underlying_price": underlying_price,
            "call_ask": call["ask"],
            "put_ask": put["ask"],
            "straddle_ask_btc": straddle_ask_btc,
            "straddle_bid_btc": straddle_bid_btc,
            "volume": call["volume"] + put["volume"],
            "oi": call["oi"] + put["oi"],
        })

    expiries.sort(key=lambda x: x["dte"])
    print(f"  OK: {len(expiries)} expiries com straddle ATM líquido")
    for e in expiries[:10]:
        straddle_usd = e['straddle_ask_btc'] * e['underlying_price']
        print(f"    {e['expiry']} (DTE={e['dte']:3d}) strike={e['strike']:,.0f} "
              f"straddle_ask={e['straddle_ask_btc']:.6f} BTC (${straddle_usd:,.2f}) vol={e['volume']:.0f} OI={e['oi']:.0f}")

    if not expiries:
        print("  SEM expiries válidas.")
        return None

    # Step 2: Fetch Binance historical data
    print(f"\n[2/4] Fetching {binance_sym} daily klines from Binance ({days_history}d)...")
    daily_candles = fetch_binance_klines(binance_sym, "1d", days_history)
    print(f"  OK: {len(daily_candles)} daily candles")

    # Also fetch 1h for more granular path simulation
    print(f"  Fetching 1h klines for path simulation...")
    hourly_candles = fetch_binance_1h_klines(binance_sym, min(days_history * 24, 2160))
    print(f"  OK: {len(hourly_candles)} hourly candles")

    # Step 3: Simulate straddle payoff using historical paths
    print(f"\n[3/4] Simulating straddle payoffs using historical paths...")

    # For each expiry, find all historical windows of the same length
    # and calculate what the straddle payoff would have been
    # Straddle payoff at expiry = max(S_T - K, 0) + max(K - S_T, 0) = |S_T - K|
    # But we need to normalize: the payoff in BTC terms is |S_T - K| / S_0 * stake
    # Actually on Deribit, options are settled in the underlying crypto
    # Payoff per 1 BTC = max(S_T - K, 0) for call, max(K - S_T, 0) for put
    # Straddle payoff = |S_T - K| in USD per 1 BTC
    # Cost = straddle_ask in USD per 1 BTC (actually in BTC, but we convert)

    # Deribit options are priced in BTC. We need to convert.
    # ask_price is in BTC. To get USD cost: ask_price * S_0
    # Payoff in USD = |S_T - K|
    # So EV in USD = mean(|S_T - K|) - straddle_ask * S_0

    # Get current price
    current_price = daily_candles[-1]["close"] if daily_candles else 0
    print(f"  Current {asset} price: ${current_price:,.2f}")

    results = []
    for exp in expiries[:8]:  # Test up to 8 expiries
        dte = exp["dte"]
        strike = exp["strike"]
        straddle_cost_btc = exp["straddle_ask_btc"]
        straddle_cost_usd = straddle_cost_btc * exp["underlying_price"]

        # Find historical windows of dte days
        # For daily candles: window = dte candles
        payoffs_usd = []
        if dte <= len(daily_candles) - 1:
            for i in range(len(daily_candles) - dte):
                s_0 = daily_candles[i]["close"]
                s_t = daily_candles[i + dte]["close"]
                # Straddle payoff = |S_T - K| but K should be ATM at entry
                # Since we're simulating buying ATM straddle, K = S_0
                payoff = abs(s_t - s_0)
                payoffs_usd.append(payoff)

        # Also simulate using hourly data for short-dated options
        if dte <= 7 and len(hourly_candles) > dte * 24:
            hourly_window = dte * 24
            for i in range(0, len(hourly_candles) - hourly_window, 24):  # Non-overlapping
                s_0 = hourly_candles[i]["close"]
                s_t = hourly_candles[i + hourly_window]["close"]
                payoff = abs(s_t - s_0)
                payoffs_usd.append(payoff)

        if len(payoffs_usd) < 10:
            continue

        # Calculate EV
        ev_usd = sum(payoffs_usd) / len(payoffs_usd)
        ev_net = ev_usd - straddle_cost_usd
        lo, mean, hi = bootstrap_ci(payoffs_usd)

        # Net EV after costs
        # Deribit taker fee: 0.03% of notional (both legs entry + exit)
        # Notional ≈ 2 * current_price (call + put)
        taker_fee = 0.0003 * current_price * 2 * 2  # entry + exit, 2 legs
        # Bid-ask spread: already included in using ask_price
        ev_net_after_fees = ev_net - taker_fee

        # ROI
        roi_pct = (ev_net_after_fees / straddle_cost_usd) * 100 if straddle_cost_usd > 0 else 0

        # Win rate: % of paths where payoff > cost
        wins = sum(1 for p in payoffs_usd if p > straddle_cost_usd + taker_fee)
        win_rate = wins / len(payoffs_usd) * 100

        results.append({
            "expiry": exp["expiry"],
            "dte": dte,
            "strike": strike,
            "straddle_cost_usd": straddle_cost_usd,
            "straddle_cost_btc": straddle_cost_btc,
            "ev_payoff_usd": ev_usd,
            "ev_net_usd": ev_net,
            "ev_net_after_fees": ev_net_after_fees,
            "roi_pct": roi_pct,
            "win_rate": win_rate,
            "n_paths": len(payoffs_usd),
            "ci_lo": lo,
            "ci_hi": hi,
            "taker_fee": taker_fee,
        })

        print(f"\n  {exp['expiry']} (DTE={dte:3d}) K={strike:,.0f}:")
        print(f"    Straddle cost: ${straddle_cost_usd:,.2f} ({straddle_cost_btc:.6f} BTC)")
        print(f"    EV payoff: ${ev_usd:,.2f} (IC95%: ${lo:,.2f} - ${hi:,.2f})")
        print(f"    EV net: ${ev_net:,.2f}")
        print(f"    Taker fees: ${taker_fee:,.2f}")
        print(f"    EV net after fees: ${ev_net_after_fees:,.2f}")
        print(f"    ROI: {roi_pct:+.1f}%")
        print(f"    Win rate: {win_rate:.1f}% ({wins}/{len(payoffs_usd)} paths)")

    # Step 4: Verdict
    print(f"\n[4/4] Verdict...")
    print(f"\n{'='*80}")
    print(f"VEREDITO — D25 Options Buy-Side {asset}")
    print(f"{'='*80}")

    if not results:
        print("  FALHA: não foi possível simular payoffs.")
        return None

    profitable = [r for r in results if r["ev_net_after_fees"] > 0]
    if profitable:
        print(f"  {len(profitable)} de {len(results)} expiries com EV net positivo após fees:")
        for r in profitable:
            print(f"    {r['expiry']} (DTE={r['dte']}): EV=${r['ev_net_after_fees']:+,.2f} "
                  f"ROI={r['roi_pct']:+.1f}% WR={r['win_rate']:.0f}% N={r['n_paths']}")
        best = max(profitable, key=lambda r: r["ev_net_after_fees"])
        print(f"\n  >>> EDGE DETECTADO em {best['expiry']} (DTE={best['dte']})")
        print(f"  >>> EV net: ${best['ev_net_after_fees']:+,.2f} | ROI: {best['roi_pct']:+.1f}%")
        print(f"  >>> Win rate: {best['win_rate']:.1f}% | N={best['n_paths']} paths")
        print(f"  >>> CUIDADO: payoffs históricos assumem K=S_0 (ATM straddle).")
        print(f"  >>> Para validação: executar trades reais (ou paper) e comparar.")
    else:
        print(f"  SEM EDGE: nenhuma expiry com EV net positivo após fees.")
        print(f"  {len(results)} expiries testadas, todas com EV negativo.")
        for r in results:
            print(f"    {r['expiry']} (DTE={r['dte']}): EV=${r['ev_net_after_fees']:+,.2f} "
                  f"ROI={r['roi_pct']:+.1f}% WR={r['win_rate']:.0f}%")
        print(f"\n  Possíveis razões:")
        print(f"    - IV < RV mas NÃO suficiente para superar bid-ask spread + fees")
        print(f"    - Path dependence: payoffs históricos não capturam vol de vol")
        print(f"    - Straddle ATM sofre de theta decay (tempo value)")
        print(f"    - D23 mediu IV vs RV point-in-time; histórico pode diferir")

    print(f"\n  Dataset: {len(results)} expiries | {asset} | {days_history}d history")
    return results


def main():
    ap = argparse.ArgumentParser(description="D25 — Crypto Options Buy-Side (Inverse VRP)")
    ap.add_argument("--asset", default="BTC", choices=["BTC", "ETH"], help="Asset to scan")
    ap.add_argument("--days", type=int, default=90, help="Days of historical data")
    args = ap.parse_args()

    print(f"D25 — Crypto Options Buy-Side (Inverse VRP)")
    print(f"Asset: {args.asset} | History: {args.days}d")

    all_results = []
    for asset in [args.asset] if args.asset != "BTC" else ["BTC", "ETH"]:
        r = analyze_straddle_buy(asset, args.days)
        if r:
            all_results.extend(r)

    # Summary
    if all_results:
        print(f"\n{'='*80}")
        print(f"RESUMO GERAL")
        print(f"{'='*80}")
        profitable = [r for r in all_results if r["ev_net_after_fees"] > 0]
        if profitable:
            print(f"  {len(profitable)} de {len(all_results)} expiries profitáveis")
        else:
            print(f"  0 de {len(all_results)} expiries profitáveis após fees")
        for r in all_results:
            print(f"  {r['expiry']:>10} DTE={r['dte']:3d}: EV=${r['ev_net_after_fees']:+,.2f} "
                  f"ROI={r['roi_pct']:+.1f}% WR={r['win_rate']:.0f}%")


if __name__ == "__main__":
    main()
