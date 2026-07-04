"""
D29 — Basis-Funding Disconnect Paper Trading Bot

Runs every 8 hours (aligned with Binance funding periods at 00:00, 08:00, 16:00 UTC).
Scans all USDT perpetual futures for carry trade opportunities where:
  - Basis (perp vs spot) and funding rate both favor the same direction
  - Net profit per 8h > roundtrip fees (0.14%)

When a disconnect is found, records a paper trade:
  - Entry: spot + perp position at current prices
  - Exit: at next funding period (8h later) or when basis converges
  - Tracks P&L from basis convergence + funding payments - fees

Usage:
  python3 basis_paper_bot.py
  python3 basis_paper_bot.py --once   # single scan and exit
"""
import argparse
import json
import os
import time
import urllib.request
from datetime import datetime, timezone, timedelta

TRADE_LOG = "basis_paper_trades.json"
STATS_LOG = "basis_paper_stats.json"
ROUNDTRIP_FEE_PCT = 0.14  # spot 0.1% + futures 0.04%
MIN_PROFIT_PCT = 0.01  # minimum net profit per 8h to enter trade
MAX_TRADES_PER_CYCLE = 3  # max simultaneous positions


def fetch_json(url, timeout=15):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode())


def fetch_spot_prices():
    url = "https://api.binance.com/api/v3/ticker/price"
    data = fetch_json(url)
    prices = {}
    for d in data:
        if d["symbol"].endswith("USDT"):
            prices[d["symbol"]] = float(d["price"])
    return prices


def fetch_futures_data():
    """Fetch mark prices and funding rates for all USDT perps."""
    # Mark prices
    url1 = "https://fapi.binance.com/fapi/v1/premiumIndex"
    data1 = fetch_json(url1)
    marks = {}
    funding = {}
    for d in data1:
        sym = d["symbol"]
        if sym.endswith("USDT"):
            marks[sym] = float(d["markPrice"])
            funding[sym] = float(d.get("lastFundingRate", 0))

    return marks, funding


def fetch_top_symbols(limit=30):
    """Get top USDT perps by volume."""
    url = "https://fapi.binance.com/fapi/v1/ticker/24hr"
    data = fetch_json(url)
    usdt_perps = [d for d in data if d["symbol"].endswith("USDT")]
    usdt_perps.sort(key=lambda x: float(x["quoteVolume"]), reverse=True)
    return [d["symbol"] for d in usdt_perps[:limit]]


def load_trades():
    if os.path.exists(TRADE_LOG):
        with open(TRADE_LOG) as f:
            return json.load(f)
    return []


def save_trades(trades):
    with open(TRADE_LOG, "w") as f:
        json.dump(trades, f, indent=2)


def compute_stats(trades):
    settled = [t for t in trades if t.get("status") == "settled"]
    if not settled:
        return {"n": 0, "wr": 0, "ev": 0, "total_pnl": 0}
    wins = [t for t in settled if t["pnl_pct"] > 0]
    pnls = [t["pnl_pct"] for t in settled]
    return {
        "n": len(settled),
        "wr": len(wins) / len(settled) * 100,
        "ev_pct": sum(pnls) / len(settled),
        "total_pnl_pct": sum(pnls),
        "wins": len(wins),
        "losses": len(settled) - len(wins),
        "best_pct": max(pnls),
        "worst_pct": min(pnls),
        "avg_duration_h": sum(t.get("duration_h", 8) for t in settled) / len(settled),
    }


def scan_and_trade(once=False):
    """Scan for basis-funding disconnects and record paper trades."""
    now = datetime.now(timezone.utc)
    print(f"\n{'='*80}")
    print(f"D29 — Basis-Funding Disconnect Paper Bot | {now.isoformat()}")
    print(f"{'='*80}")

    # Fetch data
    print("  Fetching spot prices...")
    spot_prices = fetch_spot_prices()

    print("  Fetching futures mark prices + funding rates...")
    marks, funding = fetch_futures_data()

    top_syms = fetch_top_symbols(30)
    print(f"  Top symbols: {len(top_syms)}")

    # Analyze each symbol
    opportunities = []
    for sym in top_syms:
        if sym not in spot_prices or sym not in marks:
            continue

        spot = spot_prices[sym]
        mark = marks[sym]
        fund_rate = funding.get(sym, 0)

        basis_pct = (mark - spot) / spot * 100
        fund_pct_8h = fund_rate * 100  # funding rate is per 8h

        # LONG carry: contango (basis > 0) + negative funding (receive)
        # Profit = basis convergence + |funding| - fees
        if basis_pct > 0 and fund_rate < 0:
            side = "LONG"
            profit_8h = basis_pct + abs(fund_pct_8h) - ROUNDTRIP_FEE_PCT
        # SHORT carry: backwardation (basis < 0) + positive funding (receive when short)
        elif basis_pct < 0 and fund_rate > 0:
            side = "SHORT"
            profit_8h = abs(basis_pct) + fund_pct_8h - ROUNDTRIP_FEE_PCT
        else:
            continue

        if profit_8h > MIN_PROFIT_PCT:
            opportunities.append({
                "symbol": sym,
                "spot": spot,
                "mark": mark,
                "basis_pct": basis_pct,
                "fund_pct_8h": fund_pct_8h,
                "side": side,
                "profit_8h_pct": profit_8h,
                "annualized_pct": profit_8h * 3 * 365,  # 3 funding periods/day * 365
            })

    opportunities.sort(key=lambda x: x["profit_8h_pct"], reverse=True)

    print(f"\n  Disconnects found: {len(opportunities)}")
    for o in opportunities[:10]:
        print(f"    {o['symbol']:12s} | {o['side']:5s} | Basis: {o['basis_pct']:+.4f}% | "
              f"Fund: {o['fund_pct_8h']:+.4f}% | Profit/8h: {o['profit_8h_pct']:+.4f}% | "
              f"Annual: {o['annualized_pct']:+.1f}%")

    # Record paper trades (up to MAX_TRADES_PER_CYCLE)
    all_trades = load_trades()

    # Check if we have open trades to settle
    open_trades = [t for t in all_trades if t.get("status") == "open"]
    for t in open_trades:
        # Settle: check current prices
        sym = t["symbol"]
        if sym in spot_prices and sym in marks:
            current_spot = spot_prices[sym]
            current_mark = marks[sym]
            current_basis = (current_mark - current_spot) / current_spot * 100

            if t["side"] == "LONG":
                # Long perp: profit = basis convergence + funding received
                basis_convergence = t["entry_basis_pct"] - current_basis  # basis shrinks
                funding_received = abs(t["entry_fund_pct"])
                pnl_pct = basis_convergence + funding_received - ROUNDTRIP_FEE_PCT
            else:
                # Short perp: profit = basis convergence + funding received
                basis_convergence = current_basis - t["entry_basis_pct"]  # basis shrinks (less negative)
                funding_received = t["entry_fund_pct"]
                pnl_pct = basis_convergence + funding_received - ROUNDTRIP_FEE_PCT

            t["status"] = "settled"
            t["exit_basis_pct"] = current_basis
            t["pnl_pct"] = pnl_pct
            t["settled_at"] = now.isoformat()
            t["duration_h"] = (now - datetime.fromisoformat(t["entered_at"])).total_seconds() / 3600
            print(f"  SETTLED: {sym} {t['side']} | P&L: {pnl_pct:+.4f}% | Duration: {t['duration_h']:.1f}h")

    # Enter new trades
    new_trades = []
    for opp in opportunities[:MAX_TRADES_PER_CYCLE]:
        trade = {
            "symbol": opp["symbol"],
            "side": opp["side"],
            "entry_spot": opp["spot"],
            "entry_mark": opp["mark"],
            "entry_basis_pct": opp["basis_pct"],
            "entry_fund_pct": opp["fund_pct_8h"],
            "expected_profit_8h_pct": opp["profit_8h_pct"],
            "status": "open",
            "entered_at": now.isoformat(),
        }
        new_trades.append(trade)
        print(f"  ENTER: {opp['symbol']} {opp['side']} | Expected profit/8h: {opp['profit_8h_pct']:+.4f}%")

    all_trades.extend(new_trades)
    save_trades(all_trades)

    # Stats
    stats = compute_stats(all_trades)
    print(f"\n  === RUNNING STATS ===")
    print(f"  Total settled: {stats['n']}")
    if stats["n"] > 0:
        print(f"  Win rate: {stats['wr']:.1f}%")
        print(f"  EV/trade: {stats['ev_pct']:+.4f}%")
        print(f"  Total P&L: {stats['total_pnl_pct']:+.4f}%")
        print(f"  Best: {stats['best_pct']:+.4f}% | Worst: {stats['worst_pct']:+.4f}%")
        print(f"  Avg duration: {stats['avg_duration_h']:.1f}h")

    open_count = len([t for t in all_trades if t.get("status") == "open"])
    print(f"  Open positions: {open_count}")

    with open(STATS_LOG, "w") as f:
        json.dump(stats, f, indent=2)

    return opportunities


def main():
    ap = argparse.ArgumentParser(description="D29 — Basis-Funding Disconnect Paper Bot")
    ap.add_argument("--once", action="store_true", help="Single scan and exit")
    args = ap.parse_args()

    print("D29 — Basis-Funding Disconnect Paper Trading Bot")
    print(f"  Roundtrip fees: {ROUNDTRIP_FEE_PCT}% | Min profit: {MIN_PROFIT_PCT}%/8h")
    print(f"  Mode: {'once' if args.once else 'continuous (every 8h)'}")

    if args.once:
        scan_and_trade(once=True)
    else:
        while True:
            try:
                scan_and_trade(once=False)
            except Exception as e:
                print(f"ERROR: {e}")
                import traceback
                traceback.print_exc()

            # Wait until next funding period (00:00, 08:00, 16:00 UTC)
            now = datetime.now(timezone.utc)
            next_funding = now.replace(minute=0, second=0, microsecond=0)
            if now.hour < 8:
                next_funding = next_funding.replace(hour=8)
            elif now.hour < 16:
                next_funding = next_funding.replace(hour=16)
            else:
                next_funding = (next_funding + timedelta(days=1)).replace(hour=0)

            wait_s = (next_funding - now).total_seconds()
            print(f"\n  Next scan in {wait_s/3600:.1f}h (at {next_funding.isoformat()})")
            time.sleep(min(wait_s, 3600))


if __name__ == "__main__":
    main()
