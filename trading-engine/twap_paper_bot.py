"""
D31 — Deribit Settlement TWAP Paper Trading Bot

Runs continuously. Every day at 07:30 UTC (30 min before Deribit 08:00 expiry):
  1. Starts collecting 1m BTC/ETH prices from Binance (TWAP window)
  2. At 07:50 UTC (20 min in), computes forming TWAP for BTC and ETH
  3. Fetches Deribit option quotes for options expiring TODAY
  4. For each option, computes intrinsic value at forming TWAP
  5. If |market_price - intrinsic| > 0.08% (TWAP error + fees), records a paper trade
  6. At 08:00 UTC, records actual settlement price and computes P&L
  7. Logs all trades and running stats

Usage:
  python3 twap_paper_bot.py
  python3 twap_paper_bot.py --once   # run one settlement cycle and exit
"""
import argparse
import json
import math
import os
import threading
import time
import urllib.request
from datetime import datetime, timezone, timedelta

TRADE_LOG = "twap_paper_trades.json"
STATS_LOG = "twap_paper_stats.json"
# BTC e ETH compartilham a mesma janela 07:30-08:00 UTC (ver run_twap_cycle) e agora rodam
# em threads paralelas (main()); esse lock evita race condition no load-modify-save do
# TRADE_LOG/STATS_LOG compartilhado quando os dois ciclos terminam quase ao mesmo tempo.
_trades_lock = threading.Lock()
FEE_PCT = 0.03  # Deribit taker fee % per side
TWAP_ERROR_THRESHOLD = 0.05  # % — 90% of the time within this at 20min
MIN_MISPRICING_PCT = TWAP_ERROR_THRESHOLD + FEE_PCT  # 0.08% total threshold


def fetch_json(url, timeout=15):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode())


def fetch_binance_price(symbol):
    url = f"https://api.binance.com/api/v3/ticker/price?symbol={symbol}"
    data = fetch_json(url)
    return float(data["price"])


def fetch_binance_1m_close(symbol, start_ms, end_ms):
    url = (f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval=1m"
           f"&startTime={start_ms}&endTime={end_ms}&limit=60")
    data = fetch_json(url)
    return [float(k[4]) for k in data]  # close prices


def fetch_deribit_options(currency, expiry_date_str):
    """Fetch option book summary for a given currency."""
    url = f"https://www.deribit.com/api/v2/public/get_book_summary_by_currency?currency={currency}&kind=option"
    data = fetch_json(url)
    options = []
    for opt in data.get("result", []):
        name = opt.get("instrument_name", "")
        parts = name.split("-")
        if len(parts) == 4 and parts[1] == expiry_date_str:
            opt["type"] = parts[2]  # C or P
            opt["strike"] = float(parts[3])
            opt["bid"] = float(opt.get("bid_price", 0) or 0)
            opt["ask"] = float(opt.get("ask_price", 0) or 0)
            opt["mid"] = (opt["bid"] + opt["ask"]) / 2 if opt["bid"] > 0 and opt["ask"] > 0 else 0
            opt["oi"] = float(opt.get("open_interest", 0) or 0)
            opt["volume"] = float(opt.get("volume", 0) or 0)
            options.append(opt)
    return options


def intrinsic_value(option_type, strike, settlement_price):
    """Intrinsic value of option at settlement (per 1 unit of underlying)."""
    if option_type == "C":
        return max(0, settlement_price - strike)
    else:
        return max(0, strike - settlement_price)


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
    wins = [t for t in settled if t["pnl_usd"] > 0]
    pnls = [t["pnl_usd"] for t in settled]
    return {
        "n": len(settled),
        "wr": len(wins) / len(settled) * 100,
        "ev": sum(pnls) / len(settled),
        "total_pnl": sum(pnls),
        "wins": len(wins),
        "losses": len(settled) - len(wins),
        "best_trade": max(pnls),
        "worst_trade": min(pnls),
    }


def run_twap_cycle(currency="BTC", once=False):
    """Run one TWAP settlement cycle for a currency."""
    binance_sym = f"{currency}USDT"
    now = datetime.now(timezone.utc)

    # Deribit daily expiry at 08:00 UTC
    # TWAP window: 07:30 - 08:00 UTC
    next_expiry = now.replace(hour=8, minute=0, second=0, microsecond=0)
    if now >= next_expiry:
        next_expiry += timedelta(days=1)

    twap_start = next_expiry - timedelta(minutes=30)
    expiry_str = next_expiry.strftime("%d%b%y").upper()

    wait_seconds = (twap_start - now).total_seconds()

    if wait_seconds > 0:
        print(f"[{now.isoformat()}] Next {currency} TWAP cycle: {expiry_str} at {twap_start.isoformat()}")
        print(f"  Waiting {wait_seconds/60:.1f} min for TWAP window to start...")
        if once:
            # For testing: simulate with historical data instead of waiting
            print("  --once mode: using historical data from yesterday")
            yesterday = next_expiry - timedelta(days=1)
            expiry_str = yesterday.strftime("%d%b%y").upper()
            twap_start = yesterday - timedelta(minutes=30)
            next_expiry = yesterday
        else:
            # Sleep until 2 min before TWAP start
            sleep_time = max(0, wait_seconds - 120)
            if sleep_time > 0:
                print(f"  Sleeping {sleep_time/60:.1f} min...")
                time.sleep(sleep_time)
            # Active wait with polling
            while datetime.now(timezone.utc) < twap_start:
                time.sleep(5)

    # === TWAP WINDOW: collect 1m prices ===
    print(f"\n[TWAP WINDOW] {currency} | Expiry: {expiry_str} | TWAP: {twap_start.isoformat()} → {next_expiry.isoformat()}")

    # Collect prices every minute
    twap_prices = []
    for minute in range(30):
        t = datetime.now(timezone.utc)
        if t >= next_expiry:
            break
        try:
            price = fetch_binance_price(binance_sym)
            twap_prices.append(price)
            forming_twap = sum(twap_prices) / len(twap_prices)
            print(f"  Min {minute+1:2d}/30 | Price: ${price:,.2f} | Forming TWAP: ${forming_twap:,.2f} | "
                  f"Remaining: {30 - minute - 1}min")
        except Exception as e:
            print(f"  Min {minute+1:2d}/30 | ERROR: {e}")

        if minute < 29:
            # Sleep until next minute
            next_min = t.replace(second=0, microsecond=0) + timedelta(minutes=1)
            sleep_s = (next_min - datetime.now(timezone.utc)).total_seconds()
            if sleep_s > 0:
                time.sleep(sleep_s)

    if len(twap_prices) < 20:
        print(f"  ERROR: Only {len(twap_prices)} prices collected. Need ≥ 20.")
        return None

    # === At minute 20+: compute forming TWAP and find mispriced options ===
    forming_twap_20 = sum(twap_prices[:20]) / 20
    final_twap = sum(twap_prices) / len(twap_prices)

    print(f"\n  Forming TWAP (20min): ${forming_twap_20:,.2f}")
    print(f"  Final TWAP (30min):   ${final_twap:,.2f}")
    print(f"  TWAP error: {abs(forming_twap_20 - final_twap) / final_twap * 100:.4f}%")

    # Fetch expiring options
    print(f"\n  Fetching {currency} options expiring {expiry_str}...")
    options = fetch_deribit_options(currency, expiry_str)
    print(f"  Found {len(options)} options expiring today")

    # Filter: only options with bid > 0 and ask > 0 (tradable)
    tradable = [o for o in options if o["bid"] > 0 and o["ask"] > 0 and o["volume"] > 0]
    print(f"  Tradable (bid>0, ask>0, volume>0): {len(tradable)}")

    if not tradable:
        print("  No tradable options. Skipping.")
        return None

    # For each option, check if mispriced vs forming TWAP intrinsic
    trades_made = []
    for opt in tradable:
        strike = opt["strike"]
        otype = opt["type"]
        mid = opt["mid"]
        bid = opt["bid"]
        ask = opt["ask"]

        # Intrinsic at forming TWAP (20min)
        intrinsic_20 = intrinsic_value(otype, strike, forming_twap_20)
        # Intrinsic at final TWAP (what settlement will be)
        intrinsic_final = intrinsic_value(otype, strike, final_twap)

        # Convert to % of underlying
        intrinsic_20_pct = intrinsic_20 / final_twap * 100
        mid_pct = mid / final_twap * 100

        mispricing_pct = abs(mid_pct - intrinsic_20_pct)

        if mispricing_pct > MIN_MISPRICING_PCT:
            # Determine direction: if market price < intrinsic, BUY; if > intrinsic, SELL
            if mid < intrinsic_20:
                # Option is CHEAP vs intrinsic → BUY at ask
                entry_price = ask
                direction = "BUY"
                # P&L = intrinsic_final - entry_price - fees
                pnl_per_unit = intrinsic_final - entry_price - entry_price * FEE_PCT / 100
            else:
                # Option is EXPENSIVE vs intrinsic → SELL at bid
                entry_price = bid
                direction = "SELL"
                # P&L = entry_price - intrinsic_final - fees
                pnl_per_unit = entry_price - intrinsic_final - entry_price * FEE_PCT / 100

            pnl_usd = pnl_per_unit  # Per 1 unit of underlying (1 BTC or 1 ETH)

            trade = {
                "currency": currency,
                "expiry": expiry_str,
                "instrument": opt["instrument_name"],
                "type": otype,
                "strike": strike,
                "direction": direction,
                "entry_price": entry_price,
                "forming_twap_20": forming_twap_20,
                "final_twap": final_twap,
                "intrinsic_at_20": intrinsic_20,
                "intrinsic_final": intrinsic_final,
                "mispricing_pct": mispricing_pct,
                "pnl_per_unit": pnl_per_unit,
                "pnl_usd": pnl_usd,
                "volume": opt["volume"],
                "oi": opt["oi"],
                "status": "settled",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
            trades_made.append(trade)
            print(f"  TRADE: {direction} {opt['instrument_name']} @ ${entry_price:.4f} | "
                  f"Intrinsic_20: ${intrinsic_20:.4f} | Mispricing: {mispricing_pct:.4f}% | "
                  f"P&L: ${pnl_usd:.4f}")

    if not trades_made:
        print(f"\n  No mispriced options found (threshold: {MIN_MISPRICING_PCT}%)")
    else:
        print(f"\n  Trades made: {len(trades_made)}")
        pnls = [t["pnl_usd"] for t in trades_made]
        wins = [t for t in trades_made if t["pnl_usd"] > 0]
        print(f"  Wins: {len(wins)}/{len(trades_made)} | Total P&L: ${sum(pnls):.4f} | "
              f"Avg: ${sum(pnls)/len(pnls):.4f}")

    # Save trades (locked: BTC/ETH threads podem terminar quase ao mesmo tempo e
    # compartilham o mesmo TRADE_LOG/STATS_LOG)
    with _trades_lock:
        all_trades = load_trades()
        all_trades.extend(trades_made)
        save_trades(all_trades)

        # Print running stats
        stats = compute_stats(all_trades)
        print(f"\n  === RUNNING STATS ({currency}) ===")
        print(f"  Total settled trades: {stats['n']}")
        if stats["n"] > 0:
            print(f"  Win rate: {stats['wr']:.1f}%")
            print(f"  EV/trade: ${stats['ev']:.4f}")
            print(f"  Total P&L: ${stats['total_pnl']:.4f}")
            print(f"  Best: ${stats['best_trade']:.4f} | Worst: ${stats['worst_trade']:.4f}")

        with open(STATS_LOG, "w") as f:
            json.dump(stats, f, indent=2)

    return trades_made


def main():
    ap = argparse.ArgumentParser(description="D31 — Deribit Settlement TWAP Paper Trading Bot")
    ap.add_argument("--once", action="store_true", help="Run one cycle and exit (uses yesterday's data)")
    ap.add_argument("--currency", default="both", choices=["BTC", "ETH", "both"])
    args = ap.parse_args()

    print("=" * 80)
    print("D31 — Deribit Settlement TWAP Paper Trading Bot")
    print("=" * 80)
    print(f"  TWAP window: 07:30-08:00 UTC daily")
    print(f"  Entry point: 20min into TWAP (07:50 UTC)")
    print(f"  Mispricing threshold: {MIN_MISPRICING_PCT}% (TWAP error {TWAP_ERROR_THRESHOLD}% + fees {FEE_PCT}%)")
    print(f"  Mode: {'once' if args.once else 'continuous'}")
    print(f"  Currency: {args.currency}")

    currencies = ["BTC", "ETH"] if args.currency == "both" else [args.currency]

    if args.once:
        # Use historical klines for backtesting yesterday's expiry
        for c in currencies:
            now = datetime.now(timezone.utc)
            yesterday = now - timedelta(days=1)
            expiry_str = yesterday.strftime("%d%b%y").upper()
            twap_start = yesterday - timedelta(minutes=30)

            print(f"\n  --once: backtesting {c} expiry {expiry_str}")

            # Fetch historical 1m klines for TWAP window
            try:
                closes = fetch_binance_1m_close(
                    f"{c}USDT",
                    int(twap_start.timestamp() * 1000),
                    int(yesterday.timestamp() * 1000)
                )
            except Exception as e:
                print(f"  ERROR fetching klines: {e}")
                continue

            if len(closes) < 20:
                print(f"  ERROR: Only {len(closes)} candles. Need ≥ 20.")
                continue

            forming_twap_20 = sum(closes[:20]) / 20
            final_twap = sum(closes) / len(closes)
            twap_error = abs(forming_twap_20 - final_twap) / final_twap * 100

            print(f"  Candles: {len(closes)} | Forming TWAP (20min): ${forming_twap_20:,.2f} | Final TWAP: ${final_twap:,.2f}")
            print(f"  TWAP error: {twap_error:.4f}%")

            # Fetch options that expired yesterday
            options = fetch_deribit_options(c, expiry_str)
            tradable = [o for o in options if o["bid"] > 0 and o["ask"] > 0 and o["volume"] > 0]
            print(f"  Options expiring {expiry_str}: {len(options)} total, {len(tradable)} tradable")

            trades_made = []
            for opt in tradable:
                strike = opt["strike"]
                otype = opt["type"]
                mid = opt["mid"]
                bid = opt["bid"]
                ask = opt["ask"]

                intrinsic_20 = intrinsic_value(otype, strike, forming_twap_20)
                intrinsic_final = intrinsic_value(otype, strike, final_twap)
                intrinsic_20_pct = intrinsic_20 / final_twap * 100
                mid_pct = mid / final_twap * 100
                mispricing_pct = abs(mid_pct - intrinsic_20_pct)

                if mispricing_pct > MIN_MISPRICING_PCT:
                    if mid < intrinsic_20:
                        entry_price = ask
                        direction = "BUY"
                        pnl_per_unit = intrinsic_final - entry_price - entry_price * FEE_PCT / 100
                    else:
                        entry_price = bid
                        direction = "SELL"
                        pnl_per_unit = entry_price - intrinsic_final - entry_price * FEE_PCT / 100

                    trade = {
                        "currency": c,
                        "expiry": expiry_str,
                        "instrument": opt["instrument_name"],
                        "type": otype,
                        "strike": strike,
                        "direction": direction,
                        "entry_price": entry_price,
                        "forming_twap_20": forming_twap_20,
                        "final_twap": final_twap,
                        "intrinsic_at_20": intrinsic_20,
                        "intrinsic_final": intrinsic_final,
                        "mispricing_pct": mispricing_pct,
                        "pnl_per_unit": pnl_per_unit,
                        "pnl_usd": pnl_per_unit,
                        "volume": opt["volume"],
                        "oi": opt["oi"],
                        "status": "settled",
                        "timestamp": now.isoformat(),
                    }
                    trades_made.append(trade)
                    print(f"  TRADE: {direction} {opt['instrument_name']} @ ${entry_price:.4f} | "
                          f"Intrinsic_20: ${intrinsic_20:.4f} | Mispricing: {mispricing_pct:.4f}% | "
                          f"P&L: ${pnl_per_unit:.4f}")

            if not trades_made:
                print(f"  No mispriced options found (threshold: {MIN_MISPRICING_PCT}%)")
            else:
                pnls = [t["pnl_usd"] for t in trades_made]
                wins = [t for t in trades_made if t["pnl_usd"] > 0]
                print(f"  Trades: {len(trades_made)} | Wins: {len(wins)} | Total P&L: ${sum(pnls):.4f}")

            all_trades = load_trades()
            all_trades.extend(trades_made)
            save_trades(all_trades)

            stats = compute_stats(all_trades)
            print(f"  Running stats: N={stats['n']}", end="")
            if stats["n"] > 0:
                print(f" | WR={stats['wr']:.1f}% | EV=${stats['ev']:.4f} | Total=${stats['total_pnl']:.4f}")
            else:
                print()
    else:
        def _run_cycle_safe(c):
            try:
                run_twap_cycle(c, once=False)
            except Exception as e:
                print(f"ERROR in {c} cycle: {e}")
                import traceback
                traceback.print_exc()

        while True:
            # BTC e ETH compartilham a mesma janela 07:30-08:00 UTC -- precisam rodar em
            # paralelo (threads), senao o primeiro consome os 30min inteiros e o segundo
            # comeca a coleta so quando a janela ja fechou (bug observado 2026-07-05/06:
            # ETH coletava so 1 preco em vez de 30).
            threads = [threading.Thread(target=_run_cycle_safe, args=(c,)) for c in currencies]
            for t in threads:
                t.start()
            for t in threads:
                t.join()
            # After both currencies processed, wait until next day
            now = datetime.now(timezone.utc)
            next_run = (now + timedelta(days=1)).replace(hour=7, minute=28, second=0, microsecond=0)
            wait_s = (next_run - now).total_seconds()
            if wait_s > 0:
                print(f"\n  Next cycle in {wait_s/3600:.1f}h. Sleeping...")
                time.sleep(min(wait_s, 3600))  # Sleep max 1h at a time


if __name__ == "__main__":
    main()
