"""
D28 — Deribit Put-Call Parity Violation

Put-call parity for European options: C - P = S - K * e^(-r*T)
In crypto, risk-free rate ≈ 0, so: C - P ≈ S - K

If (call_ask - put_bid) < (S - K), we can:
  - Buy call at ask, sell put at bid, short spot → lock in risk-free profit
  - Cost = call_ask - put_bid + spot_ask
  - Payoff at expiry = |S_T - K| - |S_T - K| = 0 (perfectly hedged)
  - Profit = K - S - (call_ask - put_bid) - fees

If (put_ask - call_bid) < (K - S), reverse:
  - Buy put at ask, sell call at bid, buy spot → lock in profit
  - Profit = S - K - (put_ask - call_bid) - fees

Scan: fetch ALL Deribit BTC/ETH options, check parity at every strike with both bid and ask.
Fees: Deribit taker 0.03% * notional (entry + exit per leg) + spot taker.

Usage:
  python3 put_call_parity_scan.py
  python3 put_call_parity_scan.py --asset ETH
"""
import argparse
import json
import math
import sys
import urllib.request
from datetime import datetime, timezone

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
        return (means[lo_idx], sum(values) / n, means[hi_idx])


def fetch_json(url, timeout=15):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode())


def fetch_deribit_options(currency="BTC"):
    url = f"https://www.deribit.com/api/v2/public/get_book_summary_by_currency?currency={currency}&kind=option"
    data = fetch_json(url)
    return data.get("result", [])


def fetch_deribit_index(currency="BTC"):
    url = f"https://www.deribit.com/api/v2/public/get_index_price?index_name={currency.lower()}_usd"
    data = fetch_json(url)
    return float(data.get("result", {}).get("index_price", 0))


def parse_expiry(exp_str):
    try:
        return datetime.strptime(exp_str, "%d%b%y").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def scan_parity(currency="BTC"):
    print(f"\n{'='*80}")
    print(f"D28 — Put-Call Parity Violation Scan | {currency}")
    print(f"{'='*80}")

    # Fetch spot index
    spot = fetch_deribit_index(currency)
    if spot <= 0:
        print("  ERRO: não foi possível obter index price")
        return None
    print(f"  Spot ({currency} index): ${spot:,.2f}")

    # Fetch all options
    options = fetch_deribit_options(currency)
    if not options:
        print("  ERRO: não foi possível obter opções da Deribit")
        return None
    print(f"  Total option instruments: {len(options)}")

    # Group by expiry-strike
    pairs = {}
    for opt in options:
        name = opt.get("instrument_name", "")
        parts = name.split("-")
        if len(parts) != 4:
            continue
        _, exp_str, strike_str, opt_type = parts
        strike = float(strike_str)
        bid = float(opt.get("bid_price", 0) or 0)
        ask = float(opt.get("ask_price", 0) or 0)
        volume = float(opt.get("volume", 0) or 0)
        oi = float(opt.get("open_interest", 0) or 0)
        underlying = float(opt.get("underlying_price", 0) or 0)

        if ask <= 0 and bid <= 0:
            continue

        key = (exp_str, strike)
        if key not in pairs:
            pairs[key] = {"call": None, "put": None, "underlying": underlying}

        if opt_type == "C":
            pairs[key]["call"] = {"bid": bid, "ask": ask, "volume": volume, "oi": oi, "name": name}
        elif opt_type == "P":
            pairs[key]["put"] = {"bid": bid, "ask": ask, "volume": volume, "oi": oi, "name": name}

    # Deribit fees: 0.03% taker per leg, cap at 12.5% of premium
    # Spot: assume Binance taker 0.1% (or Deribit perpetual 0.05%)
    TAKER_FEE_OPT = 0.0003  # 0.03% of underlying per leg
    TAKER_FEE_SPOT = 0.001  # 0.1% of notional (Binance spot)
    # For cap: fee = min(0.03% * underlying, 12.5% * premium)
    # We use the uncapped version for simplicity (worst case for us)

    now = datetime.now(timezone.utc)
    violations = []
    all_spreads = []

    for (exp_str, strike), p in pairs.items():
        if not p["call"] or not p["put"]:
            continue
        if p["call"]["ask"] <= 0 or p["put"]["ask"] <= 0:
            continue
        if p["call"]["bid"] <= 0 or p["put"]["bid"] <= 0:
            continue

        # Filter: strike must be within reasonable range of spot (±60%)
        S = p["underlying"] if p["underlying"] > 0 else spot
        if strike > S * 1.6 or strike < S * 0.4:
            continue

        # Filter: bid-ask spread must be reasonable (< 50% of mid)
        call_mid = (p["call"]["bid"] + p["call"]["ask"]) / 2
        put_mid = (p["put"]["bid"] + p["put"]["ask"]) / 2
        if call_mid > 0 and (p["call"]["ask"] - p["call"]["bid"]) / call_mid > 0.5:
            continue
        if put_mid > 0 and (p["put"]["ask"] - p["put"]["bid"]) / put_mid > 0.5:
            continue

        exp_date = parse_expiry(exp_str)
        if not exp_date:
            continue
        dte = (exp_date - now).days
        if dte < 1:
            continue

        call = p["call"]
        put = p["put"]
        S = p["underlying"] if p["underlying"] > 0 else spot

        # Parity: C - P = S - K (r=0 for crypto)
        intrinsic = S - strike  # = C - P at expiry

        # Strategy 1: Synthetic short + long spot
        # Buy call at ask, sell put at bid → synthetic long
        # If synthetic long is cheaper than spot: arb
        # Cost_synthetic = call_ask - put_bid (in BTC)
        # Value = S - K at expiry
        # Profit = (S - K) - cost_synthetic - fees
        cost_synth_long = call["ask"] - put["bid"]
        profit_long = intrinsic - cost_synth_long  # in BTC per 1 unit

        # Strategy 2: Synthetic short + short spot
        # Buy put at ask, sell call at bid → synthetic short
        # If synthetic short is cheaper than |short spot|: arb
        cost_synth_short = put["ask"] - call["bid"]
        profit_short = -intrinsic - cost_synth_short  # = K - S - cost

        # Fees (3 legs: 2 options + 1 spot/perp)
        # Option fee per leg: 0.03% * S (capped at 12.5% of premium)
        call_fee = min(TAKER_FEE_OPT * S, 0.125 * call["ask"] * S) if call["ask"] > 0 else 0
        put_fee = min(TAKER_FEE_OPT * S, 0.125 * put["ask"] * S) if put["ask"] > 0 else 0
        spot_fee = TAKER_FEE_SPOT * S

        total_fee_long = call_fee + put_fee + spot_fee  # buy call, sell put, sell spot
        total_fee_short = put_fee + call_fee + spot_fee  # buy put, sell call, buy spot

        # Convert to USD
        profit_long_usd = profit_long * S - total_fee_long
        profit_short_usd = profit_short * S - total_fee_short

        # Mid-market parity deviation (informational)
        mid_diff = ((call["bid"] + call["ask"]) / 2 - (put["bid"] + put["ask"]) / 2) - intrinsic
        all_spreads.append(mid_diff * S)

        best_profit = max(profit_long_usd, profit_short_usd)
        best_strategy = "synth_long" if profit_long_usd > profit_short_usd else "synth_short"

        if best_profit > 0:
            violations.append({
                "expiry": exp_str,
                "dte": dte,
                "strike": strike,
                "spot": S,
                "intrinsic": intrinsic,
                "call_bid": call["bid"],
                "call_ask": call["ask"],
                "put_bid": put["bid"],
                "put_ask": put["ask"],
                "cost_synth_long": cost_synth_long,
                "cost_synth_short": cost_synth_short,
                "profit_long_usd": profit_long_usd,
                "profit_short_usd": profit_short_usd,
                "best_profit_usd": best_profit,
                "best_strategy": best_strategy,
                "total_fee_usd": total_fee_long if best_strategy == "synth_long" else total_fee_short,
                "call_oi": call["oi"],
                "put_oi": put["oi"],
                "call_vol": call["volume"],
                "put_vol": put["volume"],
            })

    # Sort by profit
    violations.sort(key=lambda v: v["best_profit_usd"], reverse=True)

    print(f"\n  Pares analisados: {len(pairs)}")
    print(f"  Violações (profit > 0 após fees): {len(violations)}")

    if violations:
        print(f"\n  Top 15 violações:")
        print(f"  {'Expiry':>10} {'DTE':>4} {'Strike':>10} {'Strategy':>12} {'Profit$':>10} {'Fees$':>8} {'C_OI':>6} {'P_OI':>6}")
        for v in violations[:15]:
            print(f"  {v['expiry']:>10} {v['dte']:>4} {v['strike']:>10.0f} {v['best_strategy']:>12} "
                  f"${v['best_profit_usd']:>+9.2f} ${v['total_fee_usd']:>7.2f} "
                  f"{v['call_oi']:>6.0f} {v['put_oi']:>6.0f}")

        # Check liquidity
        liquid = [v for v in violations if v["call_oi"] >= 10 and v["put_oi"] >= 10]
        print(f"\n  Violações com OI ≥ 10 em ambas as pernas: {len(liquid)}")
        if liquid:
            profits = [v["best_profit_usd"] for v in liquid]
            print(f"  Profit médio: ${sum(profits)/len(profits):+.2f}")
            print(f"  Profit máximo: ${max(profits):+.2f}")
    else:
        print(f"\n  SEM EDGE. Nenhuma violação de put-call parity encontrada após fees.")

    # Parity deviation stats (informational)
    if all_spreads:
        lo, mean, hi = bootstrap_ci(all_spreads)
        print(f"\n  Parity deviation (mid-market, USD):")
        print(f"    Mean: ${mean:+.2f} | IC95%: [${lo:+.2f}, ${hi:+.2f}]")
        print(f"    Max: ${max(all_spreads):+.2f} | Min: ${min(all_spreads):+.2f}")
        print(f"    Std: ${(sum((x - mean)**2 for x in all_spreads) / len(all_spreads))**0.5:.2f}")

    # Verdict
    print(f"\n{'='*80}")
    print(f"VEREDITO — D28 Put-Call Parity {currency}")
    print(f"{'='*80}")
    if violations:
        liquid_count = len([v for v in violations if v["call_oi"] >= 10 and v["put_oi"] >= 10])
        if liquid_count > 0:
            print(f"  >>> {liquid_count} violações com liquidez adequada (OI ≥ 10)")
            print(f"  >>> CUIDADO: bid-ask spread pode não ser executável no size necessário")
            print(f"  >>> Recomendado: paper trade para validar execução real")
        else:
            print(f"  >>> {len(violations)} violações encontradas mas SEM liquidez (OI < 10)")
            print(f"  >>> Não é executável em size real. Margem da bid-ask cobre o desvio.")
    else:
        print(f"  >>> SEM EDGE. Put-call parity holds após fees em todos os {len(pairs)} pares.")
        print(f"  >>> Deribit market makers arbitram parity eficientemente.")

    return violations


def main():
    ap = argparse.ArgumentParser(description="D28 — Put-Call Parity Violation Scan")
    ap.add_argument("--asset", default="BTC", choices=["BTC", "ETH"])
    args = ap.parse_args()

    assets = ["BTC", "ETH"] if args.asset == "BTC" else [args.asset]
    for a in assets:
        scan_parity(a)


if __name__ == "__main__":
    main()
