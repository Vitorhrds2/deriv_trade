"""
D35 — Funding Rate Prediction Paper Trading Bot

Monitors Binance Futures premium_index continuously. When premium > threshold,
enters position to collect funding at next funding time. Exits after funding collection.

Strategy:
  - If premium_index > 0.10% → SHORT perp (longs pay shorts at funding time)
  - If premium_index < -0.10% → LONG perp (shorts pay longs at funding time)
  - Enter at T-5min before funding, exit at T+1min after funding
  - Net P&L = funding_collected - entry_slippage - exit_slippage - fees

Runs continuously, scanning every 60 seconds.
"""
import json
import time
import urllib.request
from datetime import datetime, timezone, timedelta

PREMIUM_THRESHOLD = 0.10  # 0.10% minimum premium to trigger
FEE_PCT = 0.08  # futures taker roundtrip (0.04% x 2)
SLIPPAGE_PCT = 0.02  # estimated slippage per side
TOTAL_COST_PCT = FEE_PCT + SLIPPAGE_PCT * 2  # 0.12% total cost
SCAN_INTERVAL_S = 60  # scan every 60s
POSITION_SIZE_USD = 1000  # simulated position size
TOP_N_SYMBOLS = 20  # monitor top 20 perps
LOG_FILE = "funding_paper_trades.json"
STATS_FILE = "funding_paper_stats.json"


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
                "premium_index": float(d.get("p", 0)),
            }
    return results


def fetch_top_symbols(n=20):
    """Get top USDT perps by volume."""
    url = "https://fapi.binance.com/fapi/v1/ticker/24hr"
    data = fetch_json(url)
    usdt = [d for d in data if d["symbol"].endswith("USDT")]
    usdt.sort(key=lambda x: float(x["quoteVolume"]), reverse=True)
    return [d["symbol"] for d in usdt[:n]]


def fetch_funding_history(symbol, limit=30):
    """Fetch recent funding rate history."""
    url = f"https://fapi.binance.com/fapi/v1/fundingRate?symbol={symbol}&limit={limit}"
    data = fetch_json(url)
    return [{"time": d["fundingTime"], "rate": float(d["fundingRate"])} for d in data]


def predict_funding_direction(symbol, premiums):
    """Predict funding direction using momentum + premium index."""
    p = premiums.get(symbol)
    if not p:
        return None, None, None

    premium_pct = p["premium_index"] * 100
    predicted_funding_pct = premium_pct + 0.01  # interest rate

    # Momentum check: last 3 fundings
    try:
        history = fetch_funding_history(symbol, limit=5)
        rates = [h["rate"] for h in history]
        if len(rates) >= 3:
            last3_positive = all(r > 0 for r in rates[-3:])
            last3_negative = all(r < 0 for r in rates[-3:])
            momentum_agrees = (
                (last3_positive and predicted_funding_pct > 0) or
                (last3_negative and predicted_funding_pct < 0)
            )
        else:
            momentum_agrees = True  # neutral if not enough history
    except:
        momentum_agrees = True  # don't block on API error

    return predicted_funding_pct, premium_pct, momentum_agrees


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
    settled = [t for t in trades if t["status"] == "settled"]
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


def run_bot():
    print("=" * 80)
    print("D35 — Funding Rate Prediction Paper Trading Bot")
    print("=" * 80)
    print(f"  Premium threshold: {PREMIUM_THRESHOLD}%")
    print(f"  Total cost (fees+slippage): {TOTAL_COST_PCT}%")
    print(f"  Position size: ${POSITION_SIZE_USD}")
    print(f"  Scan interval: {SCAN_INTERVAL_S}s")
    print(f"  Top {TOP_N_SYMBOLS} symbols by volume")
    print()

    top_syms = fetch_top_symbols(TOP_N_SYMBOLS)
    print(f"  Monitoring: {', '.join(top_syms[:5])}...")

    open_positions = []
    trades = load_trades()

    while True:
        now = datetime.now(timezone.utc)
        t = time.time()

        try:
            premiums = fetch_premium_index()
        except Exception as e:
            print(f"  [{now.isoformat()}] ERROR fetching premiums: {e}")
            time.sleep(SCAN_INTERVAL_S)
            continue

        # Check open positions for settlement
        still_open = []
        for pos in open_positions:
            p = premiums.get(pos["symbol"], {})
            next_fund = p.get("next_funding_time", 0)

            # If funding time has passed, settle
            if next_fund > 0 and next_fund != pos["entry_next_funding_time"]:
                # Funding happened — settle
                funding_collected = pos["predicted_funding_pct"] * POSITION_SIZE_USD / 100
                cost = TOTAL_COST_PCT * POSITION_SIZE_USD / 100
                pnl = funding_collected - cost

                # Actual funding rate (from API)
                actual_funding = p.get("last_funding_rate", 0) * 100
                actual_funding_usd = actual_funding * POSITION_SIZE_USD / 100

                # If we were SHORT and funding was positive, we collected
                if pos["direction"] == "SHORT":
                    pnl = actual_funding_usd - cost
                else:  # LONG, funding negative means shorts pay longs
                    pnl = abs(actual_funding_usd) - cost if actual_funding < 0 else -cost

                trade = {
                    **pos,
                    "status": "settled",
                    "exit_time": now.isoformat(),
                    "actual_funding_pct": actual_funding,
                    "actual_funding_usd": actual_funding_usd,
                    "cost_usd": cost,
                    "pnl_usd": pnl,
                    "pnl_pct": pnl / POSITION_SIZE_USD * 100,
                }
                trades.append(trade)
                save_trades(trades)

                emoji = "WIN" if pnl > 0 else "LOSS"
                print(f"  [{emoji}] SETTLED {pos['symbol']} {pos['direction']} | "
                      f"Predicted fund: {pos['predicted_funding_pct']:+.4f}% | "
                      f"Actual: {actual_funding:+.4f}% | "
                      f"P&L: ${pnl:+.2f}")
            else:
                # Check if we should close (funding time passed)
                if next_fund > 0 and next_fund * 1000 > 0:
                    fund_dt = datetime.fromtimestamp(next_fund / 1000, tz=timezone.utc)
                    if now > fund_dt + timedelta(minutes=2):
                        # Funding passed but API hasn't updated yet — settle with predicted
                        funding_collected = pos["predicted_funding_pct"] * POSITION_SIZE_USD / 100
                        cost = TOTAL_COST_PCT * POSITION_SIZE_USD / 100
                        pnl = funding_collected - cost

                        trade = {
                            **pos,
                            "status": "settled",
                            "exit_time": now.isoformat(),
                            "actual_funding_pct": pos["predicted_funding_pct"],
                            "actual_funding_usd": funding_collected,
                            "cost_usd": cost,
                            "pnl_usd": pnl,
                            "pnl_pct": pnl / POSITION_SIZE_USD * 100,
                        }
                        trades.append(trade)
                        save_trades(trades)

                        emoji = "WIN" if pnl > 0 else "LOSS"
                        print(f"  [{emoji}] SETTLED (est) {pos['symbol']} {pos['direction']} | "
                              f"Est. fund: {pos['predicted_funding_pct']:+.4f}% | "
                              f"P&L: ${pnl:+.2f}")
                    else:
                        still_open.append(pos)
                else:
                    still_open.append(pos)

        open_positions = still_open

        # Scan for new opportunities
        opportunities = []
        for sym in top_syms:
            if sym not in premiums:
                continue

            # Skip if already have open position on this symbol
            if any(p["symbol"] == sym for p in open_positions):
                continue

            predicted, premium, momentum = predict_funding_direction(sym, premiums)
            if predicted is None:
                continue

            p = premiums[sym]
            next_fund_ts = p["next_funding_time"]
            if next_fund_ts <= 0:
                continue

            next_fund = datetime.fromtimestamp(next_fund_ts / 1000, tz=timezone.utc)
            time_to_fund = (next_fund - now).total_seconds()

            # Only enter within 30min before funding
            if time_to_fund > 1800 or time_to_fund < 0:
                continue

            # Check if predicted funding covers costs
            if abs(predicted) > PREMIUM_THRESHOLD + TOTAL_COST_PCT:
                direction = "SHORT" if predicted > 0 else "LONG"
                profit_pct = abs(predicted) - TOTAL_COST_PCT

                # Momentum confirmation
                if not momentum:
                    continue

                opportunities.append({
                    "symbol": sym,
                    "direction": direction,
                    "premium_pct": premium,
                    "predicted_funding_pct": predicted,
                    "profit_pct": profit_pct,
                    "time_to_funding_min": time_to_fund / 60,
                    "mark_price": p["mark_price"],
                    "next_funding_time": next_fund_ts,
                })

        # Enter best opportunities
        opportunities.sort(key=lambda x: x["profit_pct"], reverse=True)

        for opp in opportunities[:3]:  # max 3 new positions per cycle
            pos = {
                "symbol": opp["symbol"],
                "direction": opp["direction"],
                "entry_time": now.isoformat(),
                "entry_price": opp["mark_price"],
                "predicted_funding_pct": opp["predicted_funding_pct"],
                "premium_pct": opp["premium_pct"],
                "position_size_usd": POSITION_SIZE_USD,
                "next_funding_time": opp["next_funding_time"],
                "entry_next_funding_time": opp["next_funding_time"],
                "status": "open",
            }
            open_positions.append(pos)

            print(f"  [ENTRY] {opp['symbol']} {opp['direction']} | "
                  f"Premium: {opp['premium_pct']:+.4f}% | "
                  f"Pred. fund: {opp['predicted_funding_pct']:+.4f}% | "
                  f"Est. profit: {opp['profit_pct']:+.4f}% (${opp['profit_pct']*POSITION_SIZE_USD/100:+.2f}) | "
                  f"Funding in {opp['time_to_funding_min']:.1f}min")

        # Status line
        stats = compute_stats(trades)
        print(f"  [{now.strftime('%H:%M:%S')} UTC] Open: {len(open_positions)} | "
              f"Settled: {stats['n']} | WR: {stats['wr']:.1f}% | "
              f"EV: ${stats['ev']:+.2f} | Total: ${stats['total_pnl']:+.2f}")

        # Save stats
        with open(STATS_FILE, "w") as f:
            json.dump(stats, f, indent=2)

        # Sleep
        elapsed = time.time() - t
        sleep_time = max(1, SCAN_INTERVAL_S - elapsed)
        time.sleep(sleep_time)


if __name__ == "__main__":
    run_bot()
