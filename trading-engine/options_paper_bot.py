"""
HYP-OPTBUY-01 — Paper Trading Bot for Crypto Options Buy-Side (Inverse VRP)

Buys ATM straddles on Deribit (paper mode) at target DTEs and tracks P&L to expiry.
No real trades, no auth, no capital. Read-only market data + simulated positions.

Strategy:
  - For BTC and ETH, target DTEs: 5, 12, 26 (weekly, biweekly, monthly)
  - Each day, check if a new expiry at target DTE is available
  - If yes, "buy" ATM straddle (call + put at nearest strike to spot) at ask price
  - Track position in JSON file (options_paper_positions.json)
  - On expiry day, fetch settlement price and calculate P&L
  - Running stats: EV, WR, bootstrap CI, per-asset and per-DTE breakdown

Usage:
  python3 options_paper_bot.py                    # run once (one cycle)
  python3 options_paper_bot.py --loop --interval-h 6  # daemon mode, every 6h
  python3 options_paper_bot.py --report           # just print current stats
"""

import argparse
import json
import math
import os
import sys
import time
import urllib.request
import urllib.error
from datetime import datetime, timezone, timedelta

try:
    from stats_utils import bootstrap_ci, wilson_ci
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

    def wilson_ci(k, n, ci=0.95):
        if n == 0:
            return (0.0, 0.0)
        z = 1.96
        p = k / n
        denom = 1 + z * z / n
        center = (p + z * z / (2 * n)) / denom
        spread = z * math.sqrt((p * (1 - p) + z * z / (4 * n)) / n) / denom
        return (max(0, center - spread), min(1, center + spread))


POSITIONS_FILE = os.path.join(os.path.dirname(__file__), "options_paper_positions.json")
LOG_FILE = os.path.join(os.path.dirname(__file__), "options_paper_bot.log")

TARGET_DTES = [5, 12, 26]
ASSETS = ["BTC", "ETH"]
DERIBIT_TAKER_FEE = 0.0003  # 0.03% of notional
DTE_TOLERANCE = 1  # accept expiry within ±1 day of target


def log(msg):
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    line = f"[{ts}] {msg}"
    print(line, flush=True)


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


def fetch_binance_price(symbol="BTCUSDT"):
    url = f"https://api.binance.com/api/v3/ticker/price?symbol={symbol}"
    data = fetch_json(url)
    return float(data.get("price", 0))


def parse_expiry(exp_str):
    try:
        return datetime.strptime(exp_str, "%d%b%y").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def find_atm_straddle(options, target_dte, now_utc):
    """Find ATM straddle for nearest expiry matching target_dte."""
    by_expiry = {}
    for opt in options:
        name = opt.get("instrument_name", "")
        parts = name.split("-")
        if len(parts) != 4:
            continue
        _, exp_str, strike_str, opt_type = parts
        strike = float(strike_str)
        ask = float(opt.get("ask_price", 0) or 0)
        bid = float(opt.get("bid_price", 0) or 0)
        volume = float(opt.get("volume", 0) or 0)
        oi = float(opt.get("open_interest", 0) or 0)
        underlying = float(opt.get("underlying_price", 0) or 0)
        mark_iv = float(opt.get("mark_iv", 0) or 0)

        if ask <= 0:
            continue

        if exp_str not in by_expiry:
            by_expiry[exp_str] = {"calls": [], "puts": [], "underlying": underlying}
        if opt_type == "C":
            by_expiry[exp_str]["calls"].append({
                "strike": strike, "ask": ask, "bid": bid, "volume": volume,
                "oi": oi, "instrument": name, "mark_iv": mark_iv,
            })
        elif opt_type == "P":
            by_expiry[exp_str]["puts"].append({
                "strike": strike, "ask": ask, "bid": bid, "volume": volume,
                "oi": oi, "instrument": name, "mark_iv": mark_iv,
            })

    best = None
    best_dte_diff = float("inf")

    for exp_str, opts in by_expiry.items():
        calls = opts["calls"]
        puts = opts["puts"]
        if not calls or not puts:
            continue

        exp_date = parse_expiry(exp_str)
        if not exp_date:
            continue

        dte = (exp_date - now_utc).days
        if dte < 1:
            continue

        dte_diff = abs(dte - target_dte)
        if dte_diff > DTE_TOLERANCE:
            continue
        if dte_diff >= best_dte_diff:
            continue

        underlying = opts["underlying"]
        if underlying <= 0:
            continue

        # Find ATM strike (closest to underlying)
        all_strikes = set(c["strike"] for c in calls) & set(p["strike"] for p in puts)
        if not all_strikes:
            continue

        atm_strike = min(all_strikes, key=lambda s: abs(s - underlying))

        call = next((c for c in calls if c["strike"] == atm_strike), None)
        put = next((p for p in puts if p["strike"] == atm_strike), None)
        if not call or not put:
            continue

        # Skip if very illiquid (OI < 10 on both legs)
        if call["oi"] < 10 and put["oi"] < 10:
            continue

        straddle_ask_btc = call["ask"] + put["ask"]
        straddle_cost_usd = straddle_ask_btc * underlying
        avg_iv = (call["mark_iv"] + put["mark_iv"]) / 2 if call["mark_iv"] > 0 and put["mark_iv"] > 0 else 0

        best = {
            "expiry_str": exp_str,
            "expiry_ts": exp_date.isoformat(),
            "dte": dte,
            "strike": atm_strike,
            "call_instrument": call["instrument"],
            "put_instrument": put["instrument"],
            "call_ask_btc": call["ask"],
            "put_ask_btc": put["ask"],
            "straddle_ask_btc": straddle_ask_btc,
            "straddle_cost_usd": straddle_cost_usd,
            "underlying_price": underlying,
            "avg_iv": avg_iv,
            "call_oi": call["oi"],
            "put_oi": put["oi"],
            "target_dte": target_dte,
        }
        best_dte_diff = dte_diff

    return best


def load_positions():
    if os.path.exists(POSITIONS_FILE):
        with open(POSITIONS_FILE) as f:
            return json.load(f)
    return {"open": [], "closed": []}


def save_positions(data):
    with open(POSITIONS_FILE, "w") as f:
        json.dump(data, f, indent=2)


def position_key(asset, expiry_str, strike):
    return f"{asset}-{expiry_str}-{strike}"


def open_new_positions(positions, now_utc):
    """Check for new straddles to buy at target DTEs."""
    open_keys = set(position_key(p["asset"], p["expiry_str"], p["strike"]) for p in positions["open"])

    new_count = 0
    for asset in ASSETS:
        try:
            options = fetch_deribit_options(asset)
            if not options:
                log(f"  {asset}: sem dados da Deribit")
                continue

            for target_dte in TARGET_DTES:
                straddle = find_atm_straddle(options, target_dte, now_utc)
                if not straddle:
                    continue

                key = position_key(asset, straddle["expiry_str"], straddle["strike"])
                if key in open_keys:
                    continue

                # Taker fee: entry on both legs (0.03% * notional * 2 legs)
                # Notional per leg ≈ underlying price
                entry_fee = DERIBIT_TAKER_FEE * straddle["underlying_price"] * 2
                total_cost = straddle["straddle_cost_usd"] + entry_fee

                pos = {
                    "key": key,
                    "asset": asset,
                    "expiry_str": straddle["expiry_str"],
                    "expiry_ts": straddle["expiry_ts"],
                    "dte_at_entry": straddle["dte"],
                    "target_dte": target_dte,
                    "strike": straddle["strike"],
                    "call_instrument": straddle["call_instrument"],
                    "put_instrument": straddle["put_instrument"],
                    "call_ask_btc": straddle["call_ask_btc"],
                    "put_ask_btc": straddle["put_ask_btc"],
                    "straddle_ask_btc": straddle["straddle_ask_btc"],
                    "straddle_cost_usd": straddle["straddle_cost_usd"],
                    "entry_fee_usd": entry_fee,
                    "total_cost_usd": total_cost,
                    "underlying_at_entry": straddle["underlying_price"],
                    "avg_iv_at_entry": straddle["avg_iv"],
                    "entry_ts": now_utc.isoformat(),
                    "status": "open",
                }

                positions["open"].append(pos)
                open_keys.add(key)
                new_count += 1
                log(f"  [NEW] {asset} DTE={straddle['dte']} K={straddle['strike']:.0f} "
                    f"cost=${total_cost:.2f} IV={straddle['avg_iv']:.1f}% "
                    f"OI={straddle['call_oi']:.0f}/{straddle['put_oi']:.0f}")

        except Exception as e:
            log(f"  {asset}: ERRO ao buscar opções: {e}")

    return new_count


def check_expiries(positions, now_utc):
    """Check if any open positions have expired; settle them."""
    settled = 0
    still_open = []

    for pos in positions["open"]:
        exp_date = datetime.fromisoformat(pos["expiry_ts"])
        if now_utc < exp_date:
            still_open.append(pos)
            continue

        # Expired — fetch settlement price
        asset = pos["asset"]
        binance_sym = f"{asset}USDT"
        try:
            settle_price = fetch_binance_price(binance_sym)
        except Exception as e:
            log(f"  [SETTLE FAIL] {pos['key']}: {e}")
            still_open.append(pos)
            continue

        # Straddle payoff = |S_T - K| in USD per 1 unit
        payoff_usd = abs(settle_price - pos["strike"])
        # Exit fee: 0.03% * notional * 2 legs (if exercised) — but straddle always has
        # one ITM leg, so only that leg settles. Fee on settlement ≈ 0.03% * |S_T - K|
        exit_fee = DERIBIT_TAKER_FEE * abs(settle_price - pos["strike"])
        net_pnl = payoff_usd - pos["total_cost_usd"] - exit_fee
        roi_pct = (net_pnl / pos["total_cost_usd"]) * 100 if pos["total_cost_usd"] > 0 else 0

        pos["status"] = "closed"
        pos["settle_price"] = settle_price
        pos["payoff_usd"] = payoff_usd
        pos["exit_fee_usd"] = exit_fee
        pos["net_pnl_usd"] = net_pnl
        pos["roi_pct"] = roi_pct
        pos["settle_ts"] = now_utc.isoformat()
        pos["win"] = net_pnl > 0

        positions["closed"].append(pos)
        settled += 1

        result = "WIN" if net_pnl > 0 else "LOSS"
        log(f"  [SETTLED {result}] {pos['key']} "
            f"S_T={settle_price:.2f} K={pos['strike']:.0f} "
            f"payoff=${payoff_usd:.2f} cost=${pos['total_cost_usd']:.2f} "
            f"P&L=${net_pnl:+.2f} ROI={roi_pct:+.1f}%")

    positions["open"] = still_open
    return settled


def print_report(positions):
    """Print current stats."""
    closed = positions["closed"]
    open_pos = positions["open"]

    log(f"\n{'='*80}")
    log(f"HYP-OPTBUY-01 — Paper Trading Report")
    log(f"{'='*80}")
    log(f"  Open positions: {len(open_pos)}")
    log(f"  Closed positions: {len(closed)}")

    if not closed:
        log(f"  Nenhum position settled ainda. Aguardando expiries...")
        if open_pos:
            log(f"\n  Posições abertas:")
            for p in open_pos:
                exp_date = datetime.fromisoformat(p["expiry_ts"])
                days_left = (exp_date - datetime.now(timezone.utc)).days
                log(f"    {p['asset']} DTE={p['dte_at_entry']} K={p['strike']:.0f} "
                    f"cost=${p['total_cost_usd']:.2f} IV={p['avg_iv_at_entry']:.1f}% "
                    f"days_left={days_left}")
        return

    # Overall stats
    pnls = [p["net_pnl_usd"] for p in closed]
    wins = [p for p in closed if p["net_pnl_usd"] > 0]
    n = len(pnls)
    ev = sum(pnls) / n
    lo, mean, hi = bootstrap_ci(pnls)
    wr = len(wins) / n * 100
    wr_lo, wr_hi = wilson_ci(len(wins), n)

    log(f"\n  === OVERALL ===")
    log(f"  N={n} | EV=${ev:+.2f} | IC95%=[${lo:+.2f}, ${hi:+.2f}]")
    log(f"  WR={wr:.1f}% | Wilson CI=[{wr_lo*100:.1f}%, {wr_hi*100:.1f}%]")
    log(f"  Total P&L: ${sum(pnls):+.2f}")

    # Per asset
    for asset in ASSETS:
        asset_closed = [p for p in closed if p["asset"] == asset]
        if not asset_closed:
            continue
        asset_pnls = [p["net_pnl_usd"] for p in asset_closed]
        asset_wins = [p for p in asset_closed if p["net_pnl_usd"] > 0]
        a_n = len(asset_pnls)
        a_ev = sum(asset_pnls) / a_n
        a_lo, a_mean, a_hi = bootstrap_ci(asset_pnls)
        a_wr = len(asset_wins) / a_n * 100
        log(f"\n  === {asset} (N={a_n}) ===")
        log(f"  EV=${a_ev:+.2f} | IC95%=[${a_lo:+.2f}, ${a_hi:+.2f}] | WR={a_wr:.1f}%")

    # Per DTE
    for target_dte in TARGET_DTES:
        dte_closed = [p for p in closed if p["target_dte"] == target_dte]
        if not dte_closed:
            continue
        dte_pnls = [p["net_pnl_usd"] for p in dte_closed]
        dte_wins = [p for p in dte_closed if p["net_pnl_usd"] > 0]
        d_n = len(dte_pnls)
        d_ev = sum(dte_pnls) / d_n
        d_lo, d_mean, d_hi = bootstrap_ci(dte_pnls)
        d_wr = len(dte_wins) / d_n * 100
        log(f"\n  === DTE={target_dte} (N={d_n}) ===")
        log(f"  EV=${d_ev:+.2f} | IC95%=[${d_lo:+.2f}, ${d_hi:+.2f}] | WR={d_wr:.1f}%")

    # Verdict check
    log(f"\n  === VERDICT CHECK ===")
    if n >= 30:
        if lo > 0:
            log(f"  >>> EDGE VALIDADO (N={n}, IC95% não cruza zero)")
        elif hi < 0:
            log(f"  >>> REFUTADO (N={n}, IC95% totalmente negativo)")
        else:
            log(f"  >>> INCONCLUSIVO (N={n}, IC95% cruza zero — need more data)")
    else:
        log(f"  >>> AGUARDANDO (N={n}/30 mínimo para veredito preliminar)")


def run_cycle():
    now = datetime.now(timezone.utc)
    log(f"\n{'='*80}")
    log(f"Cycle start — {now.strftime('%Y-%m-%d %H:%M UTC')}")
    log(f"{'='*80}")

    positions = load_positions()

    # 1. Settle expired positions
    settled = check_expiries(positions, now)
    log(f"  Settled: {settled}")

    # 2. Open new positions at target DTEs
    new = open_new_positions(positions, now)
    log(f"  New positions: {new}")

    # 3. Save
    save_positions(positions)

    # 4. Report
    print_report(positions)

    log(f"\nCycle complete.\n")


def main():
    ap = argparse.ArgumentParser(description="HYP-OPTBUY-01 Paper Trading Bot")
    ap.add_argument("--loop", action="store_true", help="Daemon mode")
    ap.add_argument("--interval-h", type=float, default=6, help="Hours between cycles in loop mode")
    ap.add_argument("--report", action="store_true", help="Just print current report")
    args = ap.parse_args()

    if args.report:
        positions = load_positions()
        print_report(positions)
        return

    if args.loop:
        log("Starting daemon mode. Press Ctrl+C to stop.")
        while True:
            try:
                run_cycle()
            except Exception as e:
                log(f"ERROR in cycle: {e}")
            sleep_s = int(args.interval_h * 3600)
            log(f"Sleeping {sleep_s}s ({args.interval_h}h) until next cycle...")
            time.sleep(sleep_s)
    else:
        run_cycle()


if __name__ == "__main__":
    main()
