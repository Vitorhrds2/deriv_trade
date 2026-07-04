#!/usr/bin/env python3
"""
D11: Options IV Mispricing Scan (Deribit).

Hypothesis: If implied volatility (IV) on Deribit options is systematically
mispriced relative to historical realized volatility (RV), there may be an
edge in selling overpriced IV or buying underpriced IV.

D11a — Compare ATM IV vs historical RV for BTC and ETH
D11b — Analyze IV term structure (near vs far expiry)
D11c — Analyze IV skew (put vs call IV at same strike)
D11d — Check if IV persistently overestimates RV (vol risk premium)

All data via Deribit public API (no API key needed). Read-only.
"""
import argparse
import json
import math
import os
import time
import urllib.request
from datetime import datetime, timezone, timedelta
from typing import Optional

DERIBIT_API = "https://www.deribit.com/api/v2/public"
UA = {"User-Agent": "options-iv-scan/1.0 (research; read-only)"}


def deribit_get(method: str, params: dict = None, timeout: int = 15) -> dict:
    url = f"{DERIBIT_API}/{method}"
    if params:
        query = "&".join(f"{k}={v}" for k, v in params.items())
        url += f"?{query}"
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


def _mean(x):
    return sum(x) / len(x) if x else 0


def get_index_price(currency: str) -> float:
    result = deribit_get("get_index_price", {"index_name": f"{currency.lower()}_usd"})
    return result.get("result", {}).get("index_price", 0)


def get_historical_volatility(currency: str) -> list:
    result = deribit_get("get_historical_volatility", {"currency": currency})
    data = result.get("result", {})
    if isinstance(data, list):
        return data
    return data.get("data", [])


def get_volatility_index_data(currency: str, resolution: str = "1D") -> list:
    end_ts = int(time.time() * 1000)
    start_ts = end_ts - 90 * 24 * 3600 * 1000  # 90 days
    result = deribit_get("get_volatility_index_data", {
        "currency": currency,
        "start_timestamp": start_ts,
        "end_timestamp": end_ts,
        "resolution": resolution,
    })
    data = result.get("result", {})
    if isinstance(data, list):
        return data
    return data.get("data", [])


def get_instruments(currency: str) -> list:
    result = deribit_get("get_instruments", {
        "currency": currency,
        "kind": "option",
        "expired": "false",
    })
    return result.get("result", [])


def get_orderbook(instrument_name: str) -> dict:
    result = deribit_get("get_order_book", {"instrument_name": instrument_name})
    return result.get("result", {})


def get_ticker(instrument_name: str) -> dict:
    result = deribit_get("get_ticker", {"instrument_name": instrument_name})
    return result.get("result", {})


def get_book_summary(currency: str) -> list:
    """Get summary data for all options of a currency (includes mark_iv, mark_price, bid/ask)."""
    result = deribit_get("get_book_summary_by_currency", {
        "currency": currency,
        "kind": "option",
    })
    return result.get("result", [])


def parse_option_name(name: str) -> dict:
    """Parse Deribit option name like 'BTC-27JUN25-100000-C'."""
    parts = name.split("-")
    if len(parts) != 4:
        return None
    currency, expiry, strike, opt_type = parts
    return {
        "currency": currency,
        "expiry": expiry,
        "strike": float(strike),
        "type": opt_type,  # C or P
        "name": name,
    }


def black_scholes(s, k, t, r, sigma, option_type="C"):
    """Black-Scholes option price."""
    if t <= 0 or sigma <= 0:
        return max(0, s - k) if option_type == "C" else max(0, k - s)
    d1 = (math.log(s / k) + (r + 0.5 * sigma ** 2) * t) / (sigma * math.sqrt(t))
    d2 = d1 - sigma * math.sqrt(t)
    if option_type == "C":
        return s * _norm_cdf(d1) - k * math.exp(-r * t) * _norm_cdf(d2)
    else:
        return k * math.exp(-r * t) * _norm_cdf(-d2) - s * _norm_cdf(-d1)


def _norm_cdf(x):
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def implied_vol_bisection(market_price, s, k, t, r, option_type="C"):
    """Calculate implied volatility using bisection method."""
    if market_price <= 0 or t <= 0:
        return None
    lo, hi = 0.001, 5.0
    for _ in range(100):
        mid = (lo + hi) / 2
        price = black_scholes(s, k, t, r, mid, option_type)
        if abs(price - market_price) < 0.01:
            return mid
        if price < market_price:
            lo = mid
        else:
            hi = mid
    return mid


def run_scan(output_file: str, currencies: list):
    print("D11: Options IV Mispricing Scan (Deribit)")
    print(f"Currencies: {', '.join(currencies)}")
    print(f"API: Deribit public (no API key)")
    print(f"{'='*80}\n")

    all_results = {}

    for currency in currencies:
        print(f"\n  [{currency}]")
        spot = get_index_price(currency)
        print(f"    Spot: ${spot:,.2f}")

        # D11a: Historical volatility
        hv_data = get_historical_volatility(currency)
        rv_1d = rv_7d = rv_30d = 0
        if hv_data:
            # hv_data is [[timestamp, vol_value], ...] — hourly historical vol
            latest = hv_data[-1] if hv_data else None
            if latest and len(latest) >= 2:
                rv_current = latest[1] if latest[1] else 0
                # Use last 24 entries as 1d, last 168 as 7d, last 720 as 30d
                rv_1d = _mean([d[1] for d in hv_data[-24:] if len(d) >= 2]) if len(hv_data) >= 24 else rv_current
                rv_7d = _mean([d[1] for d in hv_data[-168:] if len(d) >= 2]) if len(hv_data) >= 168 else rv_current
                rv_30d = _mean([d[1] for d in hv_data[-720:] if len(d) >= 2]) if len(hv_data) >= 720 else (_mean([d[1] for d in hv_data if len(d) >= 2]) if hv_data else 0)
                print(f"    Historical RV: current={rv_current:.1f}%  7d_avg={rv_7d:.1f}%  30d_avg={rv_30d:.1f}%")
            else:
                print(f"    Historical RV: data format unexpected")
        else:
            print(f"    Historical RV: N/A")

        # D11a: Volatility index (DVOL)
        dvol_data = get_volatility_index_data(currency, "1D")
        dvol_current = dvol_avg_30d = 0
        if dvol_data:
            latest_dvol = dvol_data[-1] if dvol_data else None
            if latest_dvol and len(latest_dvol) >= 2:
                dvol_current = latest_dvol[1] if isinstance(latest_dvol[1], (int, float)) else 0
                dvol_avg_30d = sum(d[1] for d in dvol_data[-30:] if len(d) >= 2 and isinstance(d[1], (int, float))) / max(1, len(dvol_data[-30:]))
                print(f"    DVOL (implied vol index): current={dvol_current:.1f}%  30d_avg={dvol_avg_30d:.1f}%")
            else:
                dvol_current = dvol_avg_30d = 0
        else:
            dvol_current = dvol_avg_30d = 0
            print(f"    DVOL: N/A")

        # Vol risk premium: IV - RV
        if dvol_current and rv_30d:
            vrp = dvol_current - rv_30d
            print(f"    Vol Risk Premium (IV-RV): {vrp:.1f}%")
        else:
            vrp = None

        # D11b/c: Get option instruments and build IV surface
        instruments = get_instruments(currency)
        print(f"    Active option instruments: {len(instruments)}")

        # Get book summary for all options at once (batch)
        book_summary = get_book_summary(currency)
        summary_by_name = {s["instrument_name"]: s for s in book_summary}
        print(f"    Book summary entries: {len(book_summary)}")

        # Group by expiry
        by_expiry = {}
        for inst in instruments:
            parsed = parse_option_name(inst["instrument_name"])
            if not parsed:
                continue
            exp_ts = inst.get("expiration_timestamp", 0)
            parsed["expiration_timestamp"] = exp_ts
            parsed["settlement_period"] = inst.get("settlement_period", "")
            exp_key = parsed["expiry"]
            if exp_key not in by_expiry:
                by_expiry[exp_key] = []
            by_expiry[exp_key].append(parsed)

        # Sort expiries by timestamp
        sorted_expiries = sorted(by_expiry.keys(), key=lambda e: by_expiry[e][0]["expiration_timestamp"])

        # For each expiry, find ATM calls and puts, get their IV from book summary
        iv_surface = []
        now_ms = int(time.time() * 1000)

        for i, expiry in enumerate(sorted_expiries[:8]):  # top 8 nearest expiries
            options = by_expiry[expiry]
            exp_ts = options[0]["expiration_timestamp"]
            t_to_exp = (exp_ts - now_ms) / (1000 * 365.25 * 24 * 3600)  # years

            if t_to_exp <= 0:
                continue

            # Find ATM strike (closest to spot)
            calls = [o for o in options if o["type"] == "C"]
            puts = [o for o in options if o["type"] == "P"]

            if not calls or not puts:
                continue

            atm_call = min(calls, key=lambda o: abs(o["strike"] - spot))
            atm_put = min(puts, key=lambda o: abs(o["strike"] - spot))

            # Get IV from book summary
            atm_data = {}
            for opt in [atm_call, atm_put]:
                summary = summary_by_name.get(opt["name"], {})
                iv = summary.get("mark_iv", 0) or 0
                mark_price = summary.get("mark_price", 0) or 0
                best_bid = summary.get("best_bid_price", 0) or 0
                best_ask = summary.get("best_ask_price", 0) or 0
                opt["iv"] = iv
                opt["mark_price"] = mark_price
                opt["best_bid"] = best_bid
                opt["best_ask"] = best_ask
                opt["t_to_exp"] = t_to_exp
                atm_data[opt["type"]] = opt

            call_iv = atm_data.get("C", {}).get("iv", 0)
            put_iv = atm_data.get("P", {}).get("iv", 0)
            atm_iv = (call_iv + put_iv) / 2 if call_iv and put_iv else (call_iv or put_iv or 0)

            # IV skew (put IV - call IV)
            skew = put_iv - call_iv if call_iv and put_iv else None

            days_to_exp = t_to_exp * 365.25
            print(f"    Expiry {expiry} ({days_to_exp:.0f}d): ATM IV={atm_iv:.1f}%  "
                  f"Call IV={call_iv:.1f}%  Put IV={put_iv:.1f}%  Skew={skew:.1f}%" if skew is not None
                  else f"    Expiry {expiry} ({days_to_exp:.0f}d): ATM IV={atm_iv:.1f}%")

            iv_surface.append({
                "expiry": expiry,
                "days_to_exp": days_to_exp,
                "t_to_exp_years": t_to_exp,
                "atm_strike": atm_call["strike"],
                "call_iv": call_iv,
                "put_iv": put_iv,
                "atm_iv": atm_iv,
                "skew": skew,
                "call_mark": atm_data.get("C", {}).get("mark_price", 0),
                "put_mark": atm_data.get("P", {}).get("mark_price", 0),
                "call_bid": atm_data.get("C", {}).get("best_bid", 0),
                "call_ask": atm_data.get("C", {}).get("best_ask", 0),
                "put_bid": atm_data.get("P", {}).get("best_bid", 0),
                "put_ask": atm_data.get("P", {}).get("best_ask", 0),
            })

        # D11b: Term structure analysis
        if len(iv_surface) >= 2:
            near_iv = iv_surface[0]["atm_iv"]
            far_iv = iv_surface[-1]["atm_iv"]
            term_slope = far_iv - near_iv
            print(f"\n    Term structure: near={near_iv:.1f}% → far={far_iv:.1f}% (slope={term_slope:+.1f}%)")
            if term_slope > 0:
                print(f"    → Contango (far IV > near IV) — market expects vol increase")
            else:
                print(f"    → Backwardation (near IV > far IV) — near-term stress priced in")

        # D11c: Skew analysis
        skews = [s["skew"] for s in iv_surface if s["skew"] is not None]
        if skews:
            avg_skew = sum(skews) / len(skews)
            print(f"    Avg put-call skew: {avg_skew:.1f}%")
            if avg_skew > 2:
                print(f"    → Put IV > Call IV — downside protection in demand (crash hedging)")
            elif avg_skew < -2:
                print(f"    → Call IV > Put IV — upside speculation in demand")
            else:
                print(f"    → Skew near zero — balanced market")

        # D11d: Vol risk premium analysis
        print(f"\n    Vol Risk Premium Analysis:")
        if vrp is not None:
            print(f"    IV (DVOL)={dvol_current:.1f}%  RV(30d)={rv_30d:.1f}%  VRP={vrp:.1f}%")
            if vrp > 5:
                print(f"    → IV significantly > RV — selling vol (short options) may be profitable")
                print(f"    → BUT: short vol = tail risk (unlimited loss potential)")
            elif vrp < -5:
                print(f"    → IV < RV — buying vol (long options) may be profitable")
                print(f"    → BUT: long vol = theta decay (time decay works against you)")
            else:
                print(f"    → IV ≈ RV — vol is fairly priced, no clear edge")

            # Estimate: if we sell straddle at ATM IV and realized vol is RV,
            # profit = (IV² - RV²) * t * notional / 2
            if vrp > 0:
                # Simplified: selling 1 ATM straddle
                # Profit ≈ (IV² - RV²) / 2 * t * spot * 1%
                t_30d = 30 / 365.25
                theoretical_profit_pct = (dvol_current**2 - rv_30d**2) / 10000 / 2 * t_30d * 100
                print(f"    Theoretical straddle sell profit (30d): ~{theoretical_profit_pct:.2f}% of notional")
                print(f"    On $10k notional: ~${theoretical_profit_pct * 100:.0f}")
                print(f"    Fees: ~0.03% taker × 2 legs = 0.06% = $6")
                print(f"    Net: ~${theoretical_profit_pct * 100 - 6:.0f}")
        else:
            print(f"    Insufficient data for VRP analysis")

        # Bid-ask spread analysis
        if iv_surface:
            print(f"\n    Bid-Ask Spreads (ATM options):")
            for s in iv_surface[:4]:
                call_spread = s["call_ask"] - s["call_bid"] if s["call_ask"] and s["call_bid"] else 0
                put_spread = s["put_ask"] - s["put_bid"] if s["put_ask"] and s["put_bid"] else 0
                call_spread_pct = (call_spread / s["call_mark"] * 100) if s["call_mark"] else 0
                put_spread_pct = (put_spread / s["put_mark"] * 100) if s["put_mark"] else 0
                print(f"    {s['expiry']:10s}: Call spread={call_spread:.4f} ({call_spread_pct:.1f}%)  "
                      f"Put spread={put_spread:.4f} ({put_spread_pct:.1f}%)")

        all_results[currency] = {
            "spot": spot,
            "rv_1d": rv_1d,
            "rv_7d": rv_7d,
            "rv_30d": rv_30d,
            "dvol_current": dvol_current,
            "dvol_avg_30d": dvol_avg_30d,
            "vol_risk_premium": vrp,
            "iv_surface": iv_surface,
            "n_instruments": len(instruments),
        }

    # Save
    with open(output_file, "w") as f:
        json.dump(all_results, f, indent=2, default=str)

    # ─── Summary ──────────────────────────────────────────────────────────────
    print(f"\n{'='*80}")
    print(f"SUMMARY\n")

    for currency, data in all_results.items():
        print(f"  {currency}:")
        print(f"    Spot: ${data['spot']:,.2f}")
        print(f"    RV 30d: {data['rv_30d']:.1f}%")
        print(f"    IV (DVOL): {data['dvol_current']:.1f}%")
        vrp = data.get("vol_risk_premium")
        if vrp is not None:
            print(f"    Vol Risk Premium: {vrp:.1f}%")
        if data["iv_surface"]:
            near = data["iv_surface"][0]
            far = data["iv_surface"][-1]
            print(f"    Term: {near['atm_iv']:.1f}% (near {near['days_to_exp']:.0f}d) → "
                  f"{far['atm_iv']:.1f}% (far {far['days_to_exp']:.0f}d)")
            skews = [s["skew"] for s in data["iv_surface"] if s["skew"] is not None]
            if skews:
                print(f"    Skew: {sum(skews)/len(skews):.1f}% avg")

    print(f"\n  PROFITABILITY ANALYSIS:")
    print(f"  - Vol risk premium (IV > RV) is the main edge source for vol selling")
    print(f"  - But: short vol = tail risk (March 2020, May 2021, Nov 2022 = -50%+ in days)")
    print(f"  - Bid-ask spreads on options: 5-15% of option price = significant cost")
    print(f"  - Deribit fees: 0.03% of underlying for taker, 0.01% for maker")
    print(f"  - Settlement risk: options settle at expiry, margin requirements vary")
    print(f"  - Theoretical edge exists (VRP is well documented in traditional markets)")
    print(f"  - BUT: requires active delta hedging (otherwise it's a directional bet)")
    print(f"  - Delta hedging costs: trading fees + slippage on each rebalance")


def main():
    parser = argparse.ArgumentParser(description="D11 Options IV Mispricing Scan")
    parser.add_argument("--output", type=str, default="options_iv_samples.json")
    parser.add_argument("--currencies", type=str, nargs="+", default=["BTC", "ETH"])
    args = parser.parse_args()

    output_path = os.path.join(os.path.dirname(__file__), args.output)
    run_scan(output_path, args.currencies)


if __name__ == "__main__":
    main()
