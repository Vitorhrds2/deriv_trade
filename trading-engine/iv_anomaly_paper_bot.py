"""
D36 — IV Surface Anomaly Paper Trading Bot

Scans Deribit IV surface every hour. Filters anomalies by real liquidity,
enters paper trades on the most mispriced options.

Strategy (updated after BS backtest):
  - BUY ONLY: options where IV < fair_IV by > 3 vol points (cheap IV)
  - SELL disabled: backtest proved SELL anomalies are bid-ask spread artifacts
  - Hold until anomaly reverts (IV converges to fair value) or expiry
  - P&L = (exit_price - entry_price) * quantity - fees (real price diff, not vega proxy)
  - Vega computed via Black-Scholes for accurate expected profit estimation

Liquidity filters:
  - bid > 0.001 (not dust)
  - ask < 2.0 (not illiquid deep OTM)
  - OI > 50 (real market interest)
  - volume > 0 (traded recently)
  - bid-ask spread < 50% of mid (reasonable)

Edge concentration (from backtest):
  - BTC long-dated deep OTM calls: 100% WR, +$4,500 in 7 positions
  - Theta decay minimal: after 7d P&L still +$3,512
"""
import json
import math
import time
import urllib.request
from datetime import datetime, timezone
from collections import defaultdict

SCAN_INTERVAL_S = 3600  # scan every hour
MISPRICING_THRESHOLD_IV = 3.0  # 3 vol points minimum
MIN_BID = 0.001
MAX_ASK = 2.0
MIN_OI = 50
MIN_VOLUME = 0
MAX_SPREAD_PCT = 50  # max bid-ask spread as % of mid
MAX_POSITIONS = 10  # max simultaneous paper positions
HOLD_HOURS = 24  # check if anomaly reverted after 24h
CURRENT_COHORT = "capped_v2"
LEGACY_COHORT = "legacy_unbounded"
LOG_FILE = "iv_anomaly_paper_trades.json"
STATS_FILE = "iv_anomaly_paper_stats.json"

# Backtest-proven settings
BUY_ONLY = True  # SELL anomalies are bid-ask spread artifacts (0% WR in backtest)
FEE_PCT = 0.03  # Deribit taker fee per side (0.03%)

# Black-Scholes helpers for accurate vega

def _norm_cdf(x):
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))

def _norm_pdf(x):
    return math.exp(-0.5 * x * x) / math.sqrt(2 * math.pi)

def bs_vega(S, K, T, sigma):
    if T <= 0 or sigma <= 0:
        return 0
    d1 = (math.log(S / K) + 0.5 * sigma * sigma * T) / (sigma * math.sqrt(T))
    return S * _norm_pdf(d1) * math.sqrt(T)

def bs_price(S, K, T, sigma, otype):
    if T <= 0 or sigma <= 0:
        return max(S - K, 0) if otype == "C" else max(K - S, 0)
    d1 = (math.log(S / K) + 0.5 * sigma * sigma * T) / (sigma * math.sqrt(T))
    d2 = d1 - sigma * math.sqrt(T)
    if otype == "C":
        return S * _norm_cdf(d1) - K * _norm_cdf(d2)
    else:
        return K * _norm_cdf(-d2) - S * _norm_cdf(-d1)


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
        strike = float(parts[2])
        option_type = parts[3]

        bid = float(opt.get("bid_price", 0) or 0)
        ask = float(opt.get("ask_price", 0) or 0)
        mid = (bid + ask) / 2 if bid > 0 and ask > 0 else 0
        iv = float(opt.get("mark_iv", 0) or 0)
        oi = float(opt.get("open_interest", 0) or 0)
        volume = float(opt.get("volume", 0) or 0)
        underlying_price = float(opt.get("underlying_price", 0) or 0)

        try:
            expiry_date = datetime.strptime(expiry_str, "%d%b%y").replace(tzinfo=timezone.utc)
        except:
            continue

        # Spread filter
        spread_pct = ((ask - bid) / mid * 100) if mid > 0 else 100

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
            "spread_pct": spread_pct,
        })

    return options


def build_iv_surface(options):
    """Build IV surface grouped by expiry and strike."""
    surface = defaultdict(lambda: defaultdict(dict))
    for opt in options:
        if opt["iv"] <= 0 or opt["oi"] < MIN_OI:
            continue
        surface[opt["expiry_str"]][opt["strike"]][opt["type"]] = opt
    return surface


def find_neighbors(surface, expiry, strike, otype):
    """Find neighboring options in the IV surface."""
    neighbors = []
    if expiry in surface:
        strikes = sorted(surface[expiry].keys())
        for s in strikes:
            if s != strike and otype in surface[expiry][s]:
                dist = abs(s - strike)
                neighbors.append({"iv": surface[expiry][s][otype]["iv"], "distance": dist})

    for other_expiry in surface:
        if other_expiry != expiry and strike in surface[other_expiry]:
            if otype in surface[other_expiry][strike]:
                neighbors.append({"iv": surface[other_expiry][strike][otype]["iv"], "distance": 0})

    return neighbors


def compute_fair_iv(neighbors, max_n=8):
    if not neighbors:
        return None
    neighbors.sort(key=lambda x: x["distance"])
    nearest = neighbors[:max_n]
    total_w = 0
    weighted_iv = 0
    for n in nearest:
        w = 1 / (n["distance"] + 1)
        weighted_iv += n["iv"] * w
        total_w += w
    return weighted_iv / total_w if total_w > 0 else None


def filter_liquid(options):
    """Apply strict liquidity filters."""
    return [
        o for o in options
        if o["bid"] >= MIN_BID
        and o["ask"] <= MAX_ASK
        and o["oi"] >= MIN_OI
        and o["volume"] > MIN_VOLUME
        and o["spread_pct"] < MAX_SPREAD_PCT
        and o["iv"] > 0
        and o["mid"] > 0
    ]


def load_trades():
    try:
        with open(LOG_FILE) as f:
            return json.load(f)
    except:
        return []


def save_trades(trades):
    with open(LOG_FILE, "w") as f:
        json.dump(trades, f, indent=2)


def compute_stats(trades):
    settled = [t for t in trades if t["status"] == "settled" and t.get("validation_cohort") == CURRENT_COHORT]
    if not settled:
        return {"n": 0, "wr": 0, "ev": 0, "total_pnl": 0}
    pnls = [t["pnl_usd"] for t in settled]
    wins = [p for p in pnls if p > 0]
    return {
        "n": len(settled),
        "wr": len(wins) / len(settled) * 100,
        "ev": sum(pnls) / len(pnls),
        "total_pnl": sum(pnls),
    }


def migrate_legacy_trades(trades, now):
    changed = False
    for trade in trades:
        if trade.get("validation_cohort") is not None:
            continue
        trade["validation_cohort"] = LEGACY_COHORT
        if trade.get("status") == "open":
            trade["status"] = "legacy_unbounded"
            trade["invalidated_at"] = now.isoformat()
            trade["invalidated_reason"] = "opened before max-position enforcement"
        changed = True
    return changed


def compute_vega(option, fair_iv):
    """Compute vega using Black-Scholes for accurate expected profit."""
    S = option["underlying_price"]
    K = option["strike"]
    T = (option["expiry_date"] - datetime.now(timezone.utc)).total_seconds() / (365 * 24 * 3600)
    sigma = option["iv"] / 100  # convert from % to decimal
    if T <= 0 or S <= 0 or sigma <= 0:
        return option["mid"] * 0.01  # fallback to rough approximation
    vega = bs_vega(S, K, T, sigma) * 0.01  # per 1 vol point (1% IV)
    return vega


def run_bot():
    print("=" * 80)
    print("D36 — IV Surface Anomaly Paper Trading Bot")
    print("=" * 80)
    print(f"  Scan interval: {SCAN_INTERVAL_S}s (hourly)")
    print(f"  Mispricing threshold: {MISPRICING_THRESHOLD_IV} vol points")
    print(f"  BUY ONLY: {BUY_ONLY} (SELL disabled — backtest proved artifacts)")
    print(f"  Liquidity filters: bid≥{MIN_BID}, ask≤{MAX_ASK}, OI≥{MIN_OI}, spread<{MAX_SPREAD_PCT}%")
    print(f"  Max positions: {MAX_POSITIONS}")
    print(f"  Vega: Black-Scholes (accurate)")
    print()

    while True:
        now = datetime.now(timezone.utc)
        t = time.time()

        print(f"\n{'='*80}")
        print(f"  Scan cycle: {now.isoformat()}")
        print(f"{'='*80}")

        all_trades = load_trades()
        if migrate_legacy_trades(all_trades, now):
            save_trades(all_trades)
        open_positions = [t for t in all_trades if t["status"] == "open" and t.get("validation_cohort") == CURRENT_COHORT]

        # Check if any open positions should be settled (anomaly reverted)
        for currency in ["BTC", "ETH"]:
            try:
                options = fetch_options(currency)
                liquid = filter_liquid(options)
                current_ivs = {o["instrument"]: o for o in liquid}

                for pos in open_positions:
                    if pos["currency"] != currency:
                        continue
                    if pos["instrument"] not in current_ivs:
                        continue

                    current_opt = current_ivs[pos["instrument"]]
                    current_iv = current_opt["iv"]
                    entry_iv = pos["entry_iv"]
                    fair_iv = pos["fair_iv"]
                    deviation_now = current_iv - fair_iv

                    # Check if anomaly reverted (deviation < 1 vol point)
                    if abs(deviation_now) < 1.0:
                        # Settle: P&L based on actual price difference
                        # Deribit prices are in crypto, convert to USD
                        S = current_opt["underlying_price"]
                        exit_price_crypto = current_opt["mid"]
                        exit_price_usd = exit_price_crypto * S
                        entry_price_usd = pos["entry_price"] * pos.get("entry_underlying", S)
                        quantity = pos["quantity"]

                        if pos["direction"] == "BUY":
                            pnl = (exit_price_usd - entry_price_usd) * quantity
                        else:
                            pnl = (entry_price_usd - exit_price_usd) * quantity

                        # Subtract fees (0.03% each side on notional)
                        notional = entry_price_usd * quantity
                        fees = notional * FEE_PCT / 100 * 2
                        pnl -= fees

                        pos["status"] = "settled"
                        pos["exit_time"] = now.isoformat()
                        pos["exit_iv"] = current_iv
                        pos["exit_price"] = exit_price_crypto
                        pos["exit_price_usd"] = exit_price_usd
                        pos["deviation_now"] = deviation_now
                        pos["pnl_usd"] = pnl
                        pos["pnl_pct"] = pnl / notional * 100 if notional > 0 else 0

                        emoji = "WIN" if pnl > 0 else "LOSS"
                        print(f"  [{emoji}] SETTLED {pos['instrument']} | "
                              f"Entry IV: {entry_iv:.1f} → Exit IV: {current_iv:.1f} | "
                              f"P&L: ${pnl:+.4f}")

            except Exception as e:
                print(f"  ERROR checking settlements for {currency}: {e}")

        save_trades(all_trades)

        # Scan for new anomalies
        open_positions = [t for t in all_trades if t["status"] == "open" and t.get("validation_cohort") == CURRENT_COHORT]
        available_slots = max(0, MAX_POSITIONS - len(open_positions))
        new_entries = []
        for currency in ["BTC", "ETH"]:
            try:
                options = fetch_options(currency)
                liquid = filter_liquid(options)
                print(f"  {currency}: {len(options)} total, {len(liquid)} liquid after filters")

                if len(liquid) < 20:
                    continue

                surface = build_iv_surface(liquid)

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

                            deviation = iv - fair_iv

                            if abs(deviation) > MISPRICING_THRESHOLD_IV:
                                # Skip if already have position on this instrument
                                if any(p["instrument"] == opt["instrument"] for p in open_positions):
                                    continue

                                direction = "BUY" if deviation < 0 else "SELL"

                                # BUY ONLY mode: skip SELL signals
                                if BUY_ONLY and direction == "SELL":
                                    continue

                                vega = compute_vega(opt, fair_iv)
                                expected_profit = abs(deviation) * vega

                                anomalies.append({
                                    "currency": currency,
                                    "instrument": opt["instrument"],
                                    "type": otype,
                                    "strike": strike,
                                    "expiry": expiry_str,
                                    "iv": iv,
                                    "fair_iv": fair_iv,
                                    "deviation": deviation,
                                    "direction": direction,
                                    "bid": opt["bid"],
                                    "ask": opt["ask"],
                                    "mid": opt["mid"],
                                    "oi": opt["oi"],
                                    "volume": opt["volume"],
                                    "vega": vega,
                                    "expected_profit": expected_profit,
                                    "underlying": opt["underlying_price"],
                                })

                # Sort by expected profit
                anomalies.sort(key=lambda x: x["expected_profit"], reverse=True)

                # Take top 3 per currency
                remaining_slots = available_slots - len(new_entries)
                for a in anomalies[:max(0, min(3, remaining_slots))]:
                    entry_price = a["ask"] if a["direction"] == "BUY" else a["bid"]
                    quantity = 1.0  # 1 contract

                    trade = {
                        "currency": currency,
                        "instrument": a["instrument"],
                        "type": a["type"],
                        "strike": a["strike"],
                        "expiry": a["expiry"],
                        "direction": a["direction"],
                        "entry_time": now.isoformat(),
                        "entry_price": entry_price,
                        "entry_underlying": a["underlying"],
                        "entry_iv": a["iv"],
                        "fair_iv": a["fair_iv"],
                        "deviation_entry": a["deviation"],
                        "quantity": quantity,
                        "oi": a["oi"],
                        "volume": a["volume"],
                        "vega": a["vega"],
                        "expected_profit": a["expected_profit"],
                        "status": "open",
                        "validation_cohort": CURRENT_COHORT,
                    }
                    new_entries.append(trade)
                    print(f"  [ENTRY] {a['direction']} {a['instrument']} | "
                          f"IV={a['iv']:.1f} vs fair={a['fair_iv']:.1f} (dev={a['deviation']:+.1f}) | "
                          f"Price={entry_price:.4f} | OI={a['oi']:.0f} | "
                          f"Est. profit=${a['expected_profit']:.4f}")

            except Exception as e:
                print(f"  ERROR scanning {currency}: {e}")

        # Add new entries
        all_trades = load_trades()
        all_trades.extend(new_entries)
        save_trades(all_trades)

        # Stats
        stats = compute_stats(all_trades)
        open_count = len([t for t in all_trades if t["status"] == "open" and t.get("validation_cohort") == CURRENT_COHORT])
        print(f"\n  STATS: Open={open_count} | Settled={stats['n']} | "
              f"WR={stats['wr']:.1f}% | EV=${stats['ev']:+.4f} | Total=${stats['total_pnl']:+.4f}")

        with open(STATS_FILE, "w") as f:
            json.dump(stats, f, indent=2)

        # Sleep
        elapsed = time.time() - t
        sleep_time = max(1, SCAN_INTERVAL_S - elapsed)
        print(f"  Next scan in {sleep_time/60:.1f}min...")
        time.sleep(sleep_time)


if __name__ == "__main__":
    run_bot()
