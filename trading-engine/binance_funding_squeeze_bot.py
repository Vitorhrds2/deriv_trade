#!/usr/bin/env python3
"""Binance Negative Funding Squeeze Paper Bot (D110)
=================================================
Exploits extreme negative funding rates on Binance USDT-Margined Futures.

When funding is deeply negative (<= -0.25% per 8h, or -273% annualized),
crowded short sellers pay huge fees to long holders every 8 hours.
This creates a structural asymmetry:
1. Long holders receive the funding payout from shorts directly.
2. Short covering / margin liquidations trigger rapid upward price expansion (Short Squeeze).

Strategy Parameters:
- Entry trigger: fundingRate <= -0.25% per 8h AND 24h volume >= $5M
- Max positions: 3 simultaneous
- Allocation per position: $1,000 notional (paper)
- Take Profit: +8.0%
- Stop Loss: -5.0%
- Time Stop: 24 hours
"""

import json
import os
import sys
import time
import urllib.request
from datetime import datetime, timezone

DATA_DIR = os.path.dirname(os.path.abspath(__file__))
STATE_FILE = os.path.join(DATA_DIR, "binance_funding_squeeze_state.json")
TRADES_FILE = os.path.join(DATA_DIR, "binance_funding_squeeze_trades.json")

MIN_FUNDING_RATE = -0.0025  # <= -0.25% per 8h
MIN_VOLUME_USD = 5_000_000  # >= $5M 24h volume
MAX_POSITIONS = 3
POSITION_NOTIONAL = 1000.0  # $1,000 per trade
TAKE_PROFIT_PCT = 8.0       # +8%
STOP_LOSS_PCT = -5.0        # -5%
MAX_HOLD_SECONDS = 86400    # 24h
CHECK_INTERVAL_SECONDS = 60 # 1 minute checks

# Intelligent Cooldown Parameters
COOLDOWN_TP_SECONDS = 14400    # 4 hours minimum base cooldown post Take-Profit
COOLDOWN_SL_SECONDS = 21600    # 6 hours base cooldown post Stop-Loss
COOLDOWN_TIME_SECONDS = 7200   # 2 hours base cooldown post Time-Stop


def fetch_json(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (QuantSqueeze/1.0)"})
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read().decode())


def check_intelligent_cooldown(symbol: str, cooldown_info: dict, current_mark: float, now_ts: float) -> tuple[bool, str]:
    """
    Evaluates whether a symbol is still under intelligent cooldown.
    After Take-Profit: waits at least 4 hours, and ensures price has stopped dumping
    (not below 15m SMA20, and last 15m candle not dumping).
    After Stop-Loss: waits at least 6 hours and requires stabilization above 15m SMA20.
    """
    exit_time = cooldown_info.get("exit_time", 0)
    base_duration = cooldown_info.get("base_duration", COOLDOWN_TP_SECONDS)
    elapsed = now_ts - exit_time
    exit_reason = str(cooldown_info.get("exit_reason", ""))
    
    # 1. Base time buffer: Must wait at least base_duration
    if elapsed < base_duration:
        remaining_m = (base_duration - elapsed) / 60
        return True, f"cooldown_timer_active ({remaining_m:.1f}m left, {exit_reason})"
        
    # 2. Intelligent Price Action Gate for Post-TP (Anti-Falling Knife / Squeeze Exhaustion Protection)
    if "take_profit" in exit_reason:
        try:
            klines = fetch_json(f"https://fapi.binance.com/fapi/v1/klines?symbol={symbol}&interval=15m&limit=20")
            if klines and len(klines) >= 10:
                closes = [float(k[4]) for k in klines]
                sma20 = sum(closes) / len(closes)
                last_open = float(klines[-1][1])
                last_close = float(klines[-1][4])
                
                # If current price is below the 15m average, price is still dumping post-pump
                if current_mark < sma20:
                    return True, f"post_tp_dump_protection (mark ${current_mark:.4f} < 15m SMA20 ${sma20:.4f})"
                
                # If last 15m candle is a heavy red candle (> 1.5% drop), wait for stabilization
                if last_open > 0 and (last_open - last_close) / last_open > 0.015:
                    return True, "post_tp_candle_dumping (last 15m candle dropped >1.5%)"
        except Exception as e:
            if elapsed < base_duration + 900:
                return True, f"cooldown_kline_fetch_error ({e})"

    # 3. Intelligent Price Action Gate for Post-SL (Structural Downtrend Protection)
    if "stop_loss" in exit_reason:
        try:
            klines = fetch_json(f"https://fapi.binance.com/fapi/v1/klines?symbol={symbol}&interval=15m&limit=20")
            if klines and len(klines) >= 10:
                closes = [float(k[4]) for k in klines]
                sma20 = sum(closes) / len(closes)
                if current_mark < sma20:
                    return True, f"post_sl_downtrend_protection (mark ${current_mark:.4f} < 15m SMA20 ${sma20:.4f})"
        except Exception:
            pass

    return False, "cooldown_cleared"

def load_json(filepath, default):
    if os.path.exists(filepath):
        try:
            with open(filepath, "r") as f:
                return json.load(f)
        except Exception:
            pass
    return default

def save_json(filepath, data):
    tmp = filepath + ".tmp"
    with open(tmp, "w") as f:
        json.dump(data, f, indent=2)
    os.replace(tmp, filepath)

def get_market_data():
    """Fetch current premiumIndex and 24hr tickers."""
    premium_data = fetch_json("https://fapi.binance.com/fapi/v1/premiumIndex")
    ticker_data = fetch_json("https://fapi.binance.com/fapi/v1/ticker/24hr")
    
    tickers = {t["symbol"]: t for t in ticker_data}
    markets = []
    
    for p in premium_data:
        sym = p["symbol"]
        if not sym.endswith("USDT"):
            continue
        rate = float(p.get("lastFundingRate", 0))
        mark = float(p.get("markPrice", 0))
        t = tickers.get(sym, {})
        vol = float(t.get("quoteVolume", 0))
        chg_24h = float(t.get("priceChangePercent", 0))
        
        markets.append({
            "symbol": sym,
            "funding_rate": rate,
            "annualized_rate": rate * 3 * 365 * 100,
            "mark_price": mark,
            "quote_volume": vol,
            "chg_24h": chg_24h,
            "next_funding_time": int(p.get("nextFundingTime", 0))
        })
    return markets

def run_loop():
    print(f"[{datetime.now(timezone.utc).isoformat()}] Binance Negative Funding Squeeze Bot (D110) starting...")
    print(f"Trigger: Funding <= {MIN_FUNDING_RATE*100:.2f}%/8h | Min Vol: ${MIN_VOLUME_USD/1e6:.1f}M | Max Pos: {MAX_POSITIONS}")

    state = load_json(STATE_FILE, {"open_positions": [], "total_pnl": 0.0, "realized_trades": 0})
    trades_log = load_json(TRADES_FILE, [])

    while True:
        try:
            now_dt = datetime.now(timezone.utc)
            now_ts = now_dt.timestamp()
            markets = get_market_data()
            market_map = {m["symbol"]: m for m in markets}

            # 1. Update and evaluate open positions
            open_positions = state.get("open_positions", [])
            remaining_positions = []

            for pos in open_positions:
                sym = pos["symbol"]
                if sym not in market_map:
                    remaining_positions.append(pos)
                    continue

                m = market_map[sym]
                current_price = m["mark_price"]
                entry_price = pos["entry_price"]
                ret_pct = (current_price - entry_price) / entry_price * 100.0
                pnl_usd = (current_price - entry_price) * pos["quantity"]
                hold_time = now_ts - pos["entry_time"]

                pos["current_price"] = current_price
                pos["unrealized_pnl_pct"] = ret_pct
                pos["unrealized_pnl_usd"] = pnl_usd

                # Check exit triggers
                should_exit = False
                exit_reason = ""

                if ret_pct >= TAKE_PROFIT_PCT:
                    should_exit = True
                    exit_reason = f"take_profit_{ret_pct:+.2f}%"
                elif ret_pct <= STOP_LOSS_PCT:
                    should_exit = True
                    exit_reason = f"stop_loss_{ret_pct:+.2f}%"
                elif hold_time >= MAX_HOLD_SECONDS:
                    should_exit = True
                    exit_reason = f"time_stop_{hold_time/3600:.1f}h"

                if should_exit:
                    pos["exit_time"] = now_ts
                    pos["exit_price"] = current_price
                    pos["realized_pnl_usd"] = pnl_usd
                    pos["realized_pnl_pct"] = ret_pct
                    pos["exit_reason"] = exit_reason
                    trades_log.append(pos)
                    state["total_pnl"] += pnl_usd
                    state["realized_trades"] += 1

                    # Register Intelligent Cooldown
                    if "take_profit" in exit_reason:
                        base_dur = COOLDOWN_TP_SECONDS
                    elif "stop_loss" in exit_reason:
                        base_dur = COOLDOWN_SL_SECONDS
                    else:
                        base_dur = COOLDOWN_TIME_SECONDS

                    state.setdefault("cooldowns", {})[sym] = {
                        "symbol": sym,
                        "exit_time": now_ts,
                        "exit_time_iso": now_dt.isoformat(),
                        "exit_price": current_price,
                        "exit_reason": exit_reason,
                        "base_duration": base_dur,
                    }

                    print(f"[{now_dt.strftime('%H:%M:%S')}] [CLOSED] {sym} | Reason: {exit_reason} | PnL: ${pnl_usd:+.2f} ({ret_pct:+.2f}%) | Cooldown armed: {base_dur/3600:.1f}h")
                else:
                    remaining_positions.append(pos)

            state["open_positions"] = remaining_positions

            # 2. Check for new qualifying candidates
            cooldowns = state.setdefault("cooldowns", {})
            # Prune expired cooldowns (> 24h)
            for s in list(cooldowns.keys()):
                if now_ts - cooldowns[s].get("exit_time", 0) > 86400:
                    del cooldowns[s]

            if len(remaining_positions) < MAX_POSITIONS:
                open_syms = {p["symbol"] for p in remaining_positions}
                candidates = []
                for m in markets:
                    sym = m["symbol"]
                    if sym in open_syms:
                        continue
                    if m["funding_rate"] > MIN_FUNDING_RATE or m["quote_volume"] < MIN_VOLUME_USD:
                        continue

                    # Check intelligent cooldown
                    if sym in cooldowns:
                        in_cd, cd_reason = check_intelligent_cooldown(sym, cooldowns[sym], m["mark_price"], now_ts)
                        if in_cd:
                            continue
                        else:
                            del cooldowns[sym]
                            print(f"[{now_dt.strftime('%H:%M:%S')}] [COOLDOWN CLEARED] {sym} | Reason: {cd_reason}")

                    candidates.append(m)

                # Sort by most negative funding first
                candidates.sort(key=lambda x: x["funding_rate"])

                slots_available = MAX_POSITIONS - len(remaining_positions)
                for cand in candidates[:slots_available]:
                    sym = cand["symbol"]
                    price = cand["mark_price"]
                    qty = POSITION_NOTIONAL / price if price > 0 else 0
                    new_pos = {
                        "symbol": sym,
                        "entry_time": now_ts,
                        "entry_time_iso": now_dt.isoformat(),
                        "entry_price": price,
                        "entry_funding_rate": cand["funding_rate"],
                        "entry_funding_rate_pct": cand["funding_rate"] * 100,
                        "annualized_rate": cand["annualized_rate"],
                        "quantity": qty,
                        "notional": POSITION_NOTIONAL,
                        "current_price": price,
                        "unrealized_pnl_usd": 0.0,
                        "unrealized_pnl_pct": 0.0,
                    }
                    state["open_positions"].append(new_pos)
                    print(f"[{now_dt.strftime('%H:%M:%S')}] [ENTRY LONG] {sym} | Mark: ${price:.6f} | Funding: {cand['funding_rate']*100:+.4f}%/8h ({cand['annualized_rate']:+.1f}%/yr) | Notional: ${POSITION_NOTIONAL:.0f}")

            # Persist state
            save_json(STATE_FILE, state)
            save_json(TRADES_FILE, trades_log)

            # Log periodic status
            open_count = len(state["open_positions"])
            tot_pnl = state.get("total_pnl", 0.0)
            print(f"[{now_dt.strftime('%H:%M:%S')}] Positions Open: {open_count}/{MAX_POSITIONS} | Realized PnL: ${tot_pnl:+.2f} | Realized Trades: {state['realized_trades']}")
            for p in state["open_positions"]:
                print(f"    -> {p['symbol']}: Entry=${p['entry_price']:.6f} | Mark=${p.get('current_price', 0):.6f} | PnL=${p.get('unrealized_pnl_usd', 0):+.2f} ({p.get('unrealized_pnl_pct', 0):+.2f}%) | Funding={p['entry_funding_rate_pct']:+.4f}%")
            if cooldowns:
                cd_summary = [f"{s} ({cd.get('exit_reason', '')[:12]}, {max(0, (cd.get('base_duration', 0) - (now_ts - cd.get('exit_time', 0)))/60):.0f}m)" for s, cd in cooldowns.items()]
                print(f"    [Active Cooldowns]: {', '.join(cd_summary)}")

        except Exception as e:
            print(f"[{datetime.now(timezone.utc).strftime('%H:%M:%S')}] Loop error: {e}")

        time.sleep(CHECK_INTERVAL_SECONDS)

if __name__ == "__main__":
    run_loop()
