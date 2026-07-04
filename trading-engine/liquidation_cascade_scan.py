"""
D34 — Liquidation Cascade Detection & Front-Run Scan

AGGRESSIVE HYPOTHESIS: Binance liquidation events trigger cascading selloffs.
If we can detect the FIRST liquidation in a cascade, we can short and ride the cascade.

Test methodology:
  1. Fetch Binance Futures liquidation orders every 2 seconds for 30 minutes
  2. Detect cascade: 3+ liquidations in 10s with same direction (all LONG liqs = selloff)
  3. Simulate: when cascade detected, short (if long liqs) or long (if short liqs)
  4. Hold for 30s, 60s, 120s — measure if price continues in cascade direction
  5. Net after 0.1% taker fee per side

If cascades predict continuation > 60% of the time after fees, this is very profitable.
"""
import json
import time
import urllib.request
from datetime import datetime, timezone
from collections import deque

POLL_INTERVAL_S = 2
DURATION_S = 1800  # 30 minutes
FEE_PCT = 0.1  # per side
CASCADE_WINDOW_S = 10  # 10 second window
CASCADE_MIN_LIQUIDATIONS = 3  # 3+ in window = cascade
HOLD_PERIODS_S = [30, 60, 120, 300]
SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]


def fetch_liquidations():
    """Fetch recent liquidation orders from Binance Futures."""
    try:
        url = "https://fapi.binance.com/fapi/v1/allForceOrders?limit=50"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=3) as resp:
            return json.loads(resp.read().decode())
    except Exception as e:
        return []


def fetch_price(symbol):
    try:
        url = f"https://fapi.binance.com/fapi/v1/ticker/price?symbol={symbol}"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=2) as resp:
            return float(json.loads(resp.read())["price"])
    except:
        return None


def run_scan():
    print("=" * 80)
    print("D34 — Liquidation Cascade Detection & Front-Run Scan")
    print("=" * 80)
    print(f"  Polling every {POLL_INTERVAL_S}s for {DURATION_S/60:.0f} minutes")
    print(f"  Cascade: {CASCADE_MIN_LIQUIDATIONS}+ liquidations in {CASCADE_WINDOW_S}s same direction")
    print(f"  Hold periods: {HOLD_PERIODS_S}s")
    print(f"  Fee: {FEE_PCT}% per side")
    print()

    # Track liquidations and prices
    liq_history = deque(maxlen=10000)  # (timestamp, symbol, side, price, qty)
    price_history = {sym: deque(maxlen=10000) for sym in SYMBOLS}  # (timestamp, price)
    cascades_detected = []
    cascade_results = []

    start = time.time()

    for i in range(int(DURATION_S / POLL_INTERVAL_S)):
        t = time.time()

        # Fetch liquidations
        liqs = fetch_liquidations()

        for liq in liqs:
            liq_time = liq.get("time", t * 1000) / 1000
            sym = liq.get("symbol", "")
            side = liq.get("side", "")  # BUY = short liquidation, SELL = long liquidation
            price = float(liq.get("price", 0))
            qty = float(liq.get("origQty", 0))

            if sym in SYMBOLS:
                liq_history.append({
                    "timestamp": liq_time,
                    "symbol": sym,
                    "side": side,
                    "price": price,
                    "qty": qty,
                    "notional": price * qty,
                })

        # Fetch prices
        for sym in SYMBOLS:
            price = fetch_price(sym)
            if price:
                price_history[sym].append({"timestamp": t, "price": price})

        # Check for cascades
        for sym in SYMBOLS:
            recent_liqs = [l for l in liq_history
                          if l["symbol"] == sym and t - l["timestamp"] < CASCADE_WINDOW_S]

            long_liqs = [l for l in recent_liqs if l["side"] == "SELL"]  # longs being liquidated
            short_liqs = [l for l in recent_liqs if l["side"] == "BUY"]  # shorts being liquidated

            # Detect cascade
            if len(long_liqs) >= CASCADE_MIN_LIQUIDATIONS:
                total_notional = sum(l["notional"] for l in long_liqs)
                cascade = {
                    "timestamp": t,
                    "symbol": sym,
                    "direction": "SHORT",  # longs liquidated → price drops → short
                    "liquidations": len(long_liqs),
                    "notional_usd": total_notional,
                    "entry_price": fetch_price(sym),
                }
                cascades_detected.append(cascade)
                print(f"\n  [CASCADE] {sym} SHORT signal | {len(long_liqs)} long liquidations | "
                      f"${total_notional:,.0f} notional | entry=${cascade['entry_price']}")

                # Track outcomes at different hold periods
                for hold_s in HOLD_PERIODS_S:
                    cascade["hold_s"] = hold_s
                    cascade["exit_time"] = t + hold_s
                    cascade["status"] = "pending"

            elif len(short_liqs) >= CASCADE_MIN_LIQUIDATIONS:
                total_notional = sum(l["notional"] for l in short_liqs)
                cascade = {
                    "timestamp": t,
                    "symbol": sym,
                    "direction": "LONG",  # shorts liquidated → price rises → long
                    "liquidations": len(short_liqs),
                    "notional_usd": total_notional,
                    "entry_price": fetch_price(sym),
                }
                cascades_detected.append(cascade)
                print(f"\n  [CASCADE] {sym} LONG signal | {len(short_liqs)} short liquidations | "
                      f"${total_notional:,.0f} notional | entry=${cascade['entry_price']}")

                for hold_s in HOLD_PERIODS_S:
                    cascade["hold_s"] = hold_s
                    cascade["exit_time"] = t + hold_s
                    cascade["status"] = "pending"

        # Check pending cascades for settlement
        for c in cascades_detected:
            if c.get("status") == "pending" and t >= c["exit_time"]:
                exit_price = None
                for p in price_history.get(c["symbol"], []):
                    if p["timestamp"] >= c["exit_time"]:
                        exit_price = p["price"]
                        break

                if exit_price and c["entry_price"]:
                    price_change_pct = (exit_price - c["entry_price"]) / c["entry_price"] * 100

                    if c["direction"] == "SHORT":
                        pnl_pct = -price_change_pct - FEE_PCT * 2
                    else:
                        pnl_pct = price_change_pct - FEE_PCT * 2

                    c["exit_price"] = exit_price
                    c["pnl_pct"] = pnl_pct
                    c["status"] = "settled"
                    c["price_change_pct"] = price_change_pct

                    result = {
                        "symbol": c["symbol"],
                        "direction": c["direction"],
                        "hold_s": c["hold_s"],
                        "liquidations": c["liquidations"],
                        "notional_usd": c["notional_usd"],
                        "entry_price": c["entry_price"],
                        "exit_price": exit_price,
                        "pnl_pct": pnl_pct,
                        "price_change_pct": price_change_pct,
                    }
                    cascade_results.append(result)

                    emoji = "WIN" if pnl_pct > 0 else "LOSS"
                    print(f"  [{emoji}] {c['symbol']} {c['direction']} hold={c['hold_s']}s | "
                          f"P&L: {pnl_pct:+.4f}% | price move: {price_change_pct:+.4f}%")

        if i % 60 == 0:
            elapsed = t - start
            total_liqs = len(liq_history)
            settled = [c for c in cascades_detected if c.get("status") == "settled"]
            print(f"  [{elapsed:.0f}s] Liquidations seen: {total_liqs} | "
                  f"Cascades: {len(cascades_detected)} | Settled: {len(settled)}")

        # Sleep
        elapsed = time.time() - t
        time.sleep(max(0, POLL_INTERVAL_S - elapsed))

    # Final analysis
    print(f"\n{'='*80}")
    print("FINAL ANALYSIS")
    print("=" * 80)

    if not cascade_results:
        print("  No cascades detected in the observation period.")
        print("  Liquidation cascades are rare events. Need longer observation window.")
        print("  Consider running this scan for hours/days on AWS to capture events.")
        return []

    # Group by hold period
    for hold_s in HOLD_PERIODS_S:
        results_at_hold = [r for r in cascade_results if r["hold_s"] == hold_s]
        if not results_at_hold:
            continue

        pnls = [r["pnl_pct"] for r in results_at_hold]
        wins = [r for r in results_at_hold if r["pnl_pct"] > 0]
        wr = len(wins) / len(results_at_hold) * 100
        ev = sum(pnls) / len(pnls)

        print(f"\n  Hold: {hold_s}s | N={len(results_at_hold)} | WR={wr:.1f}% | "
              f"EV={ev:+.4f}% | Total P&L={sum(pnls):+.4f}%")

        if wr > 60 and ev > 0:
            print(f"    *** POTENTIAL EDGE — cascade continuation is real ***")

    # Save
    with open("liquidation_cascade_scan_results.json", "w") as f:
        json.dump(cascade_results, f, indent=2)

    return cascade_results


if __name__ == "__main__":
    run_scan()
