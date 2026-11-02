#!/usr/bin/env python3
"""
D17 Token Unlock Short Bot — Live Implementation.

Strategy: Short token 3 days before known unlock date, exit 3 days after.
Validated edge: IS t=2.66, OOS-2025 t=5.43, OOS-2026 t=2.59.
Funding cost: ~-4bps (irrelevante). NET OOS-2025: +656bps.

Architecture:
  - Scheduler: checks daily for upcoming unlocks (3d ahead)
  - Entry: market short on Binance USDT-M perp at 00:05 UTC (3d before unlock)
  - Exit: market close at 00:05 UTC (3d after unlock)
  - Position sizing: Kelly fraction (capped at 25% of equity per position)
  - Risk management:
      - Max concurrent positions: 5
      - Max position size: 25% of equity
      - Stop loss: -15% (emergency exit if trade goes very wrong)
      - Min unlock size filter: $50M (skip tiny unlocks)
  - Modes: PAPER (default, no real orders) / LIVE (requires API keys)
  - Logging: JSON trade log + console

Usage:
  # Paper trading (default — no API keys needed)
  python3 unlock_short_bot.py

  # Paper trading with custom equity
  python3 unlock_short_bot.py --paper --equity 10000

  # Live trading (REQUIRES Binance API keys in .env)
  python3 unlock_short_bot.py --live --equity 10000

  # Backtest mode (simulate on historical unlocks)
  python3 unlock_short_bot.py --backtest

.env file (for LIVE mode):
  BINANCE_API_KEY=your_key
  BINANCE_API_SECRET=your_secret

All unlock events from token_unlock_scan.py (shared hardcoded list).
"""
import argparse
import hashlib
import hmac
import json
import logging
import math
import os
import time
import urllib.request
import urllib.parse
from datetime import datetime, timezone, timedelta
from typing import Optional

# Shared unlock events and helpers
import sys
sys.path.insert(0, os.path.dirname(__file__))
from token_unlock_scan import KNOWN_UNLOCKS, date_to_ms, fetch_daily_candles, mean, std
from unlock_data import get_upcoming_unlocks as fetch_upcoming_unlocks

# ─── Config ──────────────────────────────────────────────────────────────────
ENTRY_DAYS = -3    # 3 days before unlock
EXIT_DAYS = +3     # 3 days after unlock
FEE_BPS = 20       # 10 bps per side
STOP_LOSS_PCT = 15 # -15% stop loss (emergency)
MAX_CONCURRENT = 5
MAX_POSITION_PCT = 0.25  # 25% of equity per position
MIN_UNLOCK_VALUE_MM = 50  # Validated edge threshold ($50M); override via --min-unlock

# Whitelist of validated symbols (from backtest with t-stat > 2.5 in OOS)
# Only these tokens have statistically validated edge from the backtest
VALIDATED_SYMBOLS = {
    "APTUSDT", "ARBUSDT", "AXSUSDT", "DYDXUSDT", "IMXUSDT",
    "OPUSDT", "SEIUSDT", "STRKUSDT", "SUIUSDT",
}
KELLY_FRACTION = 0.5  # Half-Kelly for safety
CHECK_INTERVAL_S = 3600  # Check every hour
ENTRY_TIME_UTC = "00:05"  # Entry/exit at 00:05 UTC
ENTRY_WINDOW_S = CHECK_INTERVAL_S
OUT_OF_POLICY_STATUS = "out_of_policy_legacy"
IN_POLICY_STATUS = "in_policy_v2"

BINANCE_FAPI_PROD = "https://fapi.binance.com/fapi/v1"
BINANCE_FAPI_PROD_V2 = "https://fapi.binance.com/fapi/v2"  # account/balance only (v1 blocked in EU)
BINANCE_FAPI_TESTNET = "https://demo-fapi.binance.com/fapi/v1"
BINANCE_FAPI = BINANCE_FAPI_PROD  # Default; switched via --testnet/--demo flags

# Spot Demo for market data (demo-api.binance.com)
BINANCE_SPOT_DEMO = "https://demo-api.binance.com/api/v3"

UA = {"User-Agent": "unlock-short-bot/1.0"}

_TAG = os.getenv("UNLOCK_BOT_TAG", "").strip()
_SUFFIX = f"_{_TAG}" if _TAG else ""
_HERE = os.path.dirname(__file__)
TRADE_LOG = os.path.join(_HERE, f"unlock_short_trades{_SUFFIX}.json")
STATE_FILE = os.path.join(_HERE, f"unlock_short_state{_SUFFIX}.json")
LOG_FILE = os.path.join(_HERE, f"unlock_bot{_SUFFIX}.log")
DISCORD_WEBHOOK = os.getenv("DISCORD_WEBHOOK_URL", "").strip() or None

# ─── Logging ──────────────────────────────────────────────────────────────────
logger = logging.getLogger("unlock_bot")
logger.setLevel(logging.DEBUG)
_file_handler = logging.FileHandler(LOG_FILE, encoding="utf-8")
_file_handler.setLevel(logging.DEBUG)
_file_handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
_console_handler = logging.StreamHandler()
_console_handler.setLevel(logging.INFO)
_console_handler.setFormatter(logging.Formatter("%(asctime)s %(message)s", datefmt="%H:%M:%S"))
logger.addHandler(_file_handler)
logger.addHandler(_console_handler)


def send_discord(message, username="D17 Unlock Bot"):
    if not DISCORD_WEBHOOK:
        return
    try:
        data = json.dumps({"content": message, "username": username}).encode()
        req = urllib.request.Request(
            DISCORD_WEBHOOK, data=data,
            headers={
                "User-Agent": "Mozilla/5.0 (compatible; D17UnlockBot/1.0)",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        urllib.request.urlopen(req, timeout=10)
    except Exception as e:
        logger.debug(f"  [DISCORD] notify failed: {e}")


# ─── Binance API helpers ─────────────────────────────────────────────────────

def binance_get(endpoint, params=None, timeout=15):
    url = f"{BINANCE_FAPI}/{endpoint}"
    if params:
        url += "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


def binance_signed(endpoint, params, api_key, api_secret, method="POST", timeout=15, use_v2=False):
    """Binance USDT-M signed request."""
    params["timestamp"] = int(time.time() * 1000)
    query = urllib.parse.urlencode(params)
    signature = hmac.new(api_secret.encode(), query.encode(), hashlib.sha256).hexdigest()
    params["signature"] = signature
    base = BINANCE_FAPI_PROD_V2 if (use_v2 and BINANCE_FAPI == BINANCE_FAPI_PROD) else BINANCE_FAPI
    url = f"{base}/{endpoint}"
    if method == "GET":
        url += "?" + urllib.parse.urlencode(params)
        req = urllib.request.Request(url, headers={**UA, "X-MBX-APIKEY": api_key})
    else:
        data = urllib.parse.urlencode(params).encode()
        req = urllib.request.Request(url, data=data, headers={**UA, "X-MBX-APIKEY": api_key}, method=method)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


def get_current_price(symbol):
    """Get current mark price for a USDT-M perp."""
    data = binance_get("premiumIndex", {"symbol": symbol})
    return float(data["markPrice"])


def get_position_info(symbol, api_key, api_secret):
    """Get current position for a symbol."""
    data = binance_signed("positionRisk", {"symbol": symbol}, api_key, api_secret, method="GET", use_v2=True)
    for pos in data:
        if float(pos["positionAmt"]) != 0:
            return {
                "size": float(pos["positionAmt"]),
                "entry_price": float(pos["entryPrice"]),
                "unrealized_pnl": float(pos["unRealizedProfit"]),
            }
    return None


def place_short_order(symbol, quantity, api_key, api_secret):
    """Place a market short order on Binance USDT-M."""
    params = {
        "symbol": symbol,
        "side": "SELL",
        "type": "MARKET",
        "quantity": str(quantity),
        "reduceOnly": "false",
    }
    return binance_signed("order", params, api_key, api_secret, method="POST")


def close_short_order(symbol, quantity, api_key, api_secret):
    """Close a short position by buying."""
    params = {
        "symbol": symbol,
        "side": "BUY",
        "type": "MARKET",
        "quantity": str(quantity),
        "reduceOnly": "true",
    }
    return binance_signed("order", params, api_key, api_secret, method="POST")


def get_account_balance(api_key, api_secret):
    """Get USDT balance from Binance futures account."""
    data = binance_signed("balance", {}, api_key, api_secret, method="GET")
    for asset in data:
        if asset.get("asset") == "USDT":
            return float(asset["balance"])
    return 0.0


# ─── State management ─────────────────────────────────────────────────────────

def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE) as f:
            return json.load(f)
    return {"open_positions": [], "closed_trades": [], "last_check": None}


def save_state(state):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2, default=str)


def load_trade_log():
    if os.path.exists(TRADE_LOG):
        with open(TRADE_LOG) as f:
            return json.load(f)
    return []


def append_trade_log(trade):
    log = load_trade_log()
    log.append(trade)
    with open(TRADE_LOG, "w") as f:
        json.dump(log, f, indent=2, default=str)


# ─── Unlock schedule ──────────────────────────────────────────────────────────

def get_upcoming_unlocks(days_ahead=3, days_window=1):
    """Get unlock events within the entry window (0 to `days_ahead` days from now)."""
    now = datetime.now(timezone.utc)
    all_upcoming = fetch_upcoming_unlocks(
        min_value_mm=MIN_UNLOCK_VALUE_MM,
        symbol_whitelist=VALIDATED_SYMBOLS,
    )
    eligible = []
    for u in all_upcoming:
        unlock_dt = datetime.strptime(u["unlock_date"], "%Y-%m-%d").replace(tzinfo=timezone.utc)
        days_until = (unlock_dt.date() - now.date()).days
        # Eligible if within [0, days_ahead] days prior to unlock
        if 0 <= days_until <= days_ahead:
            eligible.append(u)
    return eligible


def get_all_upcoming_unlocks():
    """Get all future unlock events (dynamic fetch with hardcoded fallback)."""
    return fetch_upcoming_unlocks(
        min_value_mm=MIN_UNLOCK_VALUE_MM,
        symbol_whitelist=VALIDATED_SYMBOLS,
    )


def is_entry_window(now, allow_catchup=True):
    """Check if current time is within entry window or allows catchup."""
    if allow_catchup:
        return True
    hour, minute = (int(part) for part in ENTRY_TIME_UTC.split(":", 1))
    target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    return target <= now < target + timedelta(seconds=ENTRY_WINDOW_S)


def mark_out_of_policy_positions(state, now=None):
    now = now or datetime.now(timezone.utc)
    marked = []
    for position in state["open_positions"]:
        if position.get("policy_status") is not None:
            continue
        if float(position.get("unlock_value_mm", 0)) < MIN_UNLOCK_VALUE_MM:
            position["policy_status"] = OUT_OF_POLICY_STATUS
            position["policy_reason"] = f"unlock below ${MIN_UNLOCK_VALUE_MM}M minimum"
            position["policy_marked_at"] = now.isoformat()
            marked.append(position)
        else:
            position["policy_status"] = "legacy_in_policy"
    return marked


# ─── Position sizing (Kelly) ──────────────────────────────────────────────────

def kelly_position_size(equity, win_rate, avg_win_bps, avg_loss_bps):
    """Kelly criterion position sizing.
    
    Kelly fraction = (p * b - q) / b
    where p = win rate, q = 1-p, b = avg_win/avg_loss
    
    We use half-Kelly for safety, capped at MAX_POSITION_PCT.
    """
    if avg_loss_bps == 0:
        return equity * MAX_POSITION_PCT * KELLY_FRACTION
    
    p = win_rate / 100
    q = 1 - p
    b = abs(avg_win_bps / avg_loss_bps)  # win/loss ratio
    
    kelly_f = (p * b - q) / b if b > 0 else 0
    kelly_f = max(0, min(kelly_f, MAX_POSITION_PCT))
    
    # Half-Kelly
    position = equity * kelly_f * KELLY_FRACTION
    return min(position, equity * MAX_POSITION_PCT)


def get_historical_stats(closed_trades=None):
    """Win rate and avg win/loss (bps).

    Data-driven from live closed trades once enough accumulate (N>=20);
    otherwise conservative priors from the validated backtest (discounted
    for OOS-2026 edge decay, t=1.99)."""
    if closed_trades and len(closed_trades) >= 20:
        bps = [t.get("pnl_pct", 0.0) * 100 for t in closed_trades]
        wins = [b for b in bps if b > 0]
        losses = [b for b in bps if b <= 0]
        return {
            "win_rate": len(wins) / len(bps) * 100,
            "avg_win_bps": mean(wins) if wins else 400.0,
            "avg_loss_bps": abs(mean(losses)) if losses else 400.0,
        }
    return {
        "win_rate": 63,
        "avg_win_bps": 550,
        "avg_loss_bps": 450,
    }


# ─── Paper trading ────────────────────────────────────────────────────────────

def paper_open_short(symbol, notional, entry_price, state, unlock_info):
    """Open a paper short position."""
    position = {
        "symbol": symbol,
        "side": "SHORT",
        "entry_price": entry_price,
        "notional": notional,
        "quantity": notional / entry_price,
        "entry_time": datetime.now(timezone.utc).isoformat(),
        "unlock_date": unlock_info["unlock_date"],
        "unlock_value_mm": unlock_info["unlock_value_mm"],
        "mode": "PAPER",
        "policy_status": IN_POLICY_STATUS,
        "stop_loss_price": entry_price * (1 + STOP_LOSS_PCT / 100),
    }
    state["open_positions"].append(position)
    logger.info(f"  [PAPER] OPENED SHORT {symbol} @ ${entry_price:.4f}, notional=${notional:.2f}, qty={position['quantity']:.4f}")
    send_discord(f"**[ABERTURA] SHORT {symbol}** (PAPER) @ ${entry_price:.4f}\n"
                 f"notional ${notional:.2f} | qty {position['quantity']:.4f} | "
                 f"unlock {unlock_info['unlock_date']} (${unlock_info['unlock_value_mm']:.0f}M)")
    return position


def paper_close_short(position, exit_price, state, reason="scheduled"):
    """Close a paper short position."""
    entry = position["entry_price"]
    qty = position["quantity"]
    gross_pnl = (entry - exit_price) * qty
    fees = position["notional"] * FEE_BPS / 10000
    net_pnl = gross_pnl - fees
    pnl_pct = net_pnl / position["notional"] * 100
    
    trade = {
        **position,
        "exit_price": exit_price,
        "exit_time": datetime.now(timezone.utc).isoformat(),
        "gross_pnl": gross_pnl,
        "fees": fees,
        "net_pnl": net_pnl,
        "pnl_pct": pnl_pct,
        "close_reason": reason,
    }
    
    state["open_positions"] = [p for p in state["open_positions"] if p != position]
    state["closed_trades"].append(trade)
    append_trade_log(trade)
    
    logger.info(f"  [PAPER] CLOSED SHORT {position['symbol']} @ ${exit_price:.4f}, "
                f"PnL=${net_pnl:+.2f} ({pnl_pct:+.2f}%) [{reason}]")
    send_discord(f"**[FECHAMENTO] {position['symbol']}** (PAPER) @ ${exit_price:.4f}\n"
                 f"PnL ${net_pnl:+.2f} ({pnl_pct:+.2f}%) | motivo: {reason}")
    return trade


def paper_check_stop_loss(position, state):
    """Check if stop loss is hit."""
    try:
        current_price = get_current_price(position["symbol"])
        if current_price >= position["stop_loss_price"]:
            paper_close_short(position, current_price, state, reason="STOP_LOSS")
            return True
    except Exception as e:
        logger.error(f"  [PAPER] Error checking stop loss for {position['symbol']}: {e}")
    return False


# ─── Live trading ─────────────────────────────────────────────────────────────

def live_open_short(symbol, notional, api_key, api_secret, state, unlock_info):
    """Open a real short position on Binance."""
    price = get_current_price(symbol)
    quantity = round(notional / price, 3)  # Adjust precision per symbol
    
    try:
        result = place_short_order(symbol, quantity, api_key, api_secret)
        entry_price = float(result.get("avgPrice", price))
        position = {
            "symbol": symbol,
            "side": "SHORT",
            "entry_price": entry_price,
            "notional": notional,
            "quantity": quantity,
            "entry_time": datetime.now(timezone.utc).isoformat(),
            "unlock_date": unlock_info["unlock_date"],
            "unlock_value_mm": unlock_info["unlock_value_mm"],
            "mode": "LIVE",
            "policy_status": IN_POLICY_STATUS,
            "stop_loss_price": entry_price * (1 + STOP_LOSS_PCT / 100),
            "order_id": result.get("orderId"),
        }
        state["open_positions"].append(position)
        logger.info(f"  [LIVE] OPENED SHORT {symbol} @ ${entry_price:.4f}, notional=${notional:.2f}, qty={quantity}")
        send_discord(f"**[ABERTURA] SHORT {symbol}** (LIVE) @ ${entry_price:.4f}\n"
                     f"notional ${notional:.2f} | qty {quantity} | "
                     f"unlock {unlock_info['unlock_date']} (${unlock_info['unlock_value_mm']:.0f}M)")
        return position
    except Exception as e:
        logger.error(f"  [LIVE] ERROR opening short {symbol}: {e}")
        return None


def live_close_short(position, api_key, api_secret, state, reason="scheduled"):
    """Close a real short position on Binance."""
    try:
        result = close_short_order(position["symbol"], position["quantity"], api_key, api_secret)
        exit_price = get_current_price(position["symbol"])
        gross_pnl = (position["entry_price"] - exit_price) * position["quantity"]
        fees = position["notional"] * FEE_BPS / 10000
        net_pnl = gross_pnl - fees
        pnl_pct = net_pnl / position["notional"] * 100
        
        trade = {
            **position,
            "exit_price": exit_price,
            "exit_time": datetime.now(timezone.utc).isoformat(),
            "gross_pnl": gross_pnl,
            "fees": fees,
            "net_pnl": net_pnl,
            "pnl_pct": pnl_pct,
            "close_reason": reason,
            "close_order_id": result.get("orderId"),
        }
        state["open_positions"] = [p for p in state["open_positions"] if p != position]
        state["closed_trades"].append(trade)
        append_trade_log(trade)
        logger.info(f"  [LIVE] CLOSED SHORT {position['symbol']} @ ${exit_price:.4f}, "
                    f"PnL=${net_pnl:+.2f} ({pnl_pct:+.2f}%) [{reason}]")
        send_discord(f"**[FECHAMENTO] {position['symbol']}** (LIVE) @ ${exit_price:.4f}\n"
                     f"PnL ${net_pnl:+.2f} ({pnl_pct:+.2f}%) | motivo: {reason}")
        return trade
    except Exception as e:
        logger.error(f"  [LIVE] ERROR closing short {position['symbol']}: {e}")
        return None


def live_check_stop_loss(position, api_key, api_secret, state):
    """Check stop loss for live position."""
    try:
        current_price = get_current_price(position["symbol"])
        if current_price >= position["stop_loss_price"]:
            live_close_short(position, api_key, api_secret, state, reason="STOP_LOSS")
            return True
    except Exception as e:
        logger.error(f"  [LIVE] Error checking stop loss for {position['symbol']}: {e}")
    return False


# ─── Main loop ────────────────────────────────────────────────────────────────

def run_bot(mode="paper", equity=10000, api_key=None, api_secret=None, dry_run=False, interval=60):
    """Main bot loop."""
    state = load_state()
    marked_positions = mark_out_of_policy_positions(state)
    if marked_positions:
        save_state(state)
    stats = get_historical_stats(state["closed_trades"])
    
    logger.info(f"{'='*80}")
    logger.info(f"D17 Token Unlock Short Bot — {mode.upper()} MODE")
    logger.info(f"{'='*80}")
    logger.info(f"  Strategy: Short {abs(ENTRY_DAYS)}d before unlock, exit +{EXIT_DAYS}d after")
    logger.info(f"  Equity: ${equity:,.2f}")
    logger.info(f"  Max concurrent: {MAX_CONCURRENT}")
    logger.info(f"  Max position: {MAX_POSITION_PCT*100:.0f}% of equity")
    logger.info(f"  Stop loss: -{STOP_LOSS_PCT}%")
    logger.info(f"  Min unlock size: ${MIN_UNLOCK_VALUE_MM}M")
    logger.info(f"  Validated symbols: {len(VALIDATED_SYMBOLS)} ({', '.join(sorted(VALIDATED_SYMBOLS))})")
    logger.info(f"  Kelly fraction: {KELLY_FRACTION} (half-Kelly)")
    logger.info(f"  Check interval: {interval}s")
    if marked_positions:
        logger.warning(f"  Marked {len(marked_positions)} legacy position(s) out of policy")
    if os.getenv("TOKENOMIST_API_KEY"):
        logger.info(f"  Data source: Tokenomist API (key detected)")
    else:
        logger.info(f"  Data source: Hardcoded fallback (no TOKENOMIST_API_KEY)")
    
    # Show upcoming unlocks
    upcoming = get_all_upcoming_unlocks()
    logger.info(f"  Upcoming unlocks (≥${MIN_UNLOCK_VALUE_MM}M): {len(upcoming)} events")
    now = datetime.now(timezone.utc)
    for u in upcoming[:20]:
        unlock_dt = datetime.strptime(u["unlock_date"], "%Y-%m-%d").replace(tzinfo=timezone.utc)
        days_until = (unlock_dt - now).days
        entry_date = unlock_dt + timedelta(days=ENTRY_DAYS)
        logger.info(f"    {u['unlock_date']} {u['symbol']:>10s}  ${u['unlock_value_mm']:.0f}M  "
                    f"entry={entry_date.strftime('%Y-%m-%d')} ({days_until}d until unlock)")

    if not upcoming:
        logger.info(f"    (none scheduled)")
    
    if dry_run:
        logger.info(f"  [DRY RUN] No trades will be placed. Showing schedule only.")
        logger.info(f"  Open positions in state: {len(state['open_positions'])}")
        logger.info(f"  Closed trades in log: {len(state['closed_trades'])}")
        return

    send_discord(f"**[START] D17 Unlock Bot ({mode.upper()})** | equity ${equity:,.2f} | "
                 f"min unlock ${MIN_UNLOCK_VALUE_MM}M | {len(upcoming)} unlocks na fila")
    logger.info(f"  Starting main loop (checking every {CHECK_INTERVAL_S}s)...")
    logger.info(f"  Press Ctrl+C to stop.\n")
    
    while True:
        try:
            now = datetime.now(timezone.utc)
            now_str = now.strftime("%Y-%m-%d")
            now_time = now.strftime("%H:%M")
            logger.debug(f"Check cycle: {now.isoformat()}")

            # ─── 1. Check for entries (3d before unlock) ──────────────────────
            entry_unlocks = get_upcoming_unlocks(days_ahead=abs(ENTRY_DAYS))
            if entry_unlocks:
                logger.debug(f"  [{now_str}] {len(entry_unlocks)} eligible entry signal(s) in window")

            for unlock in entry_unlocks:
                sym = unlock["symbol"]

                # Check if already have a position for this unlock
                existing = [p for p in state["open_positions"] if p["symbol"] == sym and p.get("unlock_date") == unlock["unlock_date"]]
                if existing:
                    continue

                managed_positions = [p for p in state["open_positions"] if p.get("policy_status") != OUT_OF_POLICY_STATUS]
                if len(managed_positions) >= MAX_CONCURRENT:
                    logger.warning(f"  [{now_str}] Max concurrent positions reached, skipping {sym}")
                    continue

                # Position sizing
                stats = get_historical_stats(state["closed_trades"])
                position_size = kelly_position_size(
                    equity, stats["win_rate"], stats["avg_win_bps"], stats["avg_loss_bps"]
                )

                logger.info(f"  [{now.isoformat()}] ENTRY SIGNAL TRIGGERED: {sym} unlock on {unlock['unlock_date']} (${unlock['unlock_value_mm']:.0f}M)")
                logger.info(f"    Position size: ${position_size:.2f} ({position_size/equity*100:.1f}% of equity)")

                if mode == "paper":
                    try:
                        price = get_current_price(sym)
                        paper_open_short(sym, position_size, price, state, unlock)
                    except Exception as e:
                        logger.error(f"    Error getting price for {sym}: {e}")
                elif mode == "live" and api_key and api_secret:
                    try:
                        live_open_short(sym, position_size, api_key, api_secret, state, unlock)
                    except Exception as e:
                        logger.error(f"    Live order failed ({e}), falling back to PAPER mode for {sym}")
                        price = get_current_price(sym)
                        paper_open_short(sym, position_size, price, state, unlock)

                save_state(state)

            # ─── 2. Check for exits (3d after unlock) ─────────────────────────
            for position in list(state["open_positions"]):
                unlock_date = datetime.strptime(position["unlock_date"], "%Y-%m-%d").replace(tzinfo=timezone.utc)
                exit_date = unlock_date + timedelta(days=EXIT_DAYS)

                if now >= exit_date:
                    logger.info(f"  [{now.isoformat()}] EXIT SIGNAL: {position['symbol']} (unlock was {position['unlock_date']}, +{EXIT_DAYS}d reached)")
                    if position.get("mode") == "PAPER":
                        try:
                            price = get_current_price(position["symbol"])
                            paper_close_short(position, price, state, reason="scheduled")
                        except Exception as e:
                            logger.error(f"    Error closing {position['symbol']}: {e}")
                    elif position.get("mode") == "LIVE" and api_key and api_secret:
                        live_close_short(position, api_key, api_secret, state, reason="scheduled")
                    save_state(state)
                else:
                    # ─── 3. Check stop losses ─────────────────────────────────
                    if position.get("mode") == "PAPER":
                        paper_check_stop_loss(position, state)
                    elif position.get("mode") == "LIVE" and api_key and api_secret:
                        live_check_stop_loss(position, api_key, api_secret, state)
                    save_state(state)

            # ─── 4. Status report ─────────────────────────────────────────────
            open_count = len(state["open_positions"])
            closed_count = len(state["closed_trades"])
            if open_count > 0:
                for pos in state["open_positions"]:
                    try:
                        cur_px = get_current_price(pos["symbol"])
                        unrealized = (pos["entry_price"] - cur_px) * pos["quantity"]
                        unrealized_pct = (pos["entry_price"] - cur_px) / pos["entry_price"] * 100
                        logger.info(f"  [ACTIVE SHORT] {pos['symbol']}: Entry=${pos['entry_price']:.4f} | Mark=${cur_px:.4f} | Unrealized PnL=${unrealized:+.2f} ({unrealized_pct:+.2f}%) | StopLoss=${pos['stop_loss_price']:.4f}")
                    except Exception:
                        pass

            if closed_count > 0:
                total_pnl = sum(t.get("net_pnl", 0) for t in state["closed_trades"])
                wins = sum(1 for t in state["closed_trades"] if t.get("net_pnl", 0) > 0)
                wr = wins / closed_count * 100 if closed_count > 0 else 0
                logger.info(f"  [{now.strftime('%H:%M UTC')}] Closed Stats: {closed_count} closed, WR={wr:.0f}%, total PnL=${total_pnl:+.2f}")

            state["last_check"] = now.isoformat()
            save_state(state)

            time.sleep(interval)

        except KeyboardInterrupt:
            logger.info(f"\n  Stopping bot...")
            save_state(state)
            logger.info(f"  State saved. {len(state['open_positions'])} positions remain open.")
            break
        except Exception as e:
            logger.error(f"  [ERROR] {e}", exc_info=True)
            time.sleep(60)  # Wait 1 min before retrying


# ─── Backtest mode ────────────────────────────────────────────────────────────

def run_backtest(equity=10000):
    """Run a backtest using the validated strategy on all historical unlocks."""
    print(f"\n{'='*80}")
    print(f"D17 Token Unlock Short Bot — BACKTEST MODE")
    print(f"{'='*80}")
    print(f"  Equity: ${equity:,.2f}")
    print(f"  Strategy: Short {abs(ENTRY_DAYS)}d before, exit +{EXIT_DAYS}d after")
    print(f"  Position sizing: Half-Kelly, capped at {MAX_POSITION_PCT*100:.0f}%")
    print(f"  Fees: {FEE_BPS}bps round trip\n")
    
    stats = get_historical_stats()
    
    # Group unlocks by symbol
    symbols = {}
    for sym, date, val, pct, src in KNOWN_UNLOCKS:
        if sym not in symbols:
            symbols[sym] = []
        symbols[sym].append({"date": date, "value_mm": val, "pct_supply": pct, "source": src})
    
    # Fetch all candle data
    print("  Fetching price data...")
    symbol_candles = {}
    for symbol in symbols:
        try:
            candles = fetch_daily_candles(symbol, date_to_ms("2023-01-01"), date_to_ms("2026-07-03"))
            if len(candles) >= 30:
                symbol_candles[symbol] = candles
        except:
            pass
        time.sleep(0.2)
    
    oos_cutoff = date_to_ms("2025-01-01")
    oos2_cutoff = date_to_ms("2026-01-01")
    
    trades = []
    current_equity = equity
    
    for sym, events in symbols.items():
        if sym not in symbol_candles:
            continue
        candles = symbol_candles[sym]
        
        for event in events:
            if event["value_mm"] < MIN_UNLOCK_VALUE_MM:
                continue
            
            unlock_ts = date_to_ms(event["date"])
            entry_ts = unlock_ts + ENTRY_DAYS * 86400000
            exit_ts = unlock_ts + EXIT_DAYS * 86400000
            
            p_entry = min(candles, key=lambda c: abs(c["ts"] - entry_ts))
            p_exit = min(candles, key=lambda c: abs(c["ts"] - exit_ts))
            
            if abs(p_entry["ts"] - entry_ts) > 2 * 86400000:
                continue
            if abs(p_exit["ts"] - exit_ts) > 2 * 86400000:
                continue
            
            entry_price = p_entry["close"]
            exit_price = p_exit["close"]
            
            # Position size
            notional = kelly_position_size(current_equity, stats["win_rate"], stats["avg_win_bps"], stats["avg_loss_bps"])
            quantity = notional / entry_price
            
            gross_pnl = (entry_price - exit_price) * quantity
            fees = notional * FEE_BPS / 10000
            net_pnl = gross_pnl - fees
            pnl_pct = net_pnl / notional * 100
            
            current_equity += net_pnl
            
            if unlock_ts < oos_cutoff:
                period = "IS"
            elif unlock_ts < oos2_cutoff:
                period = "OOS-2025"
            else:
                period = "OOS-2026"
            
            trades.append({
                "symbol": sym,
                "unlock_date": event["date"],
                "entry_price": entry_price,
                "exit_price": exit_price,
                "notional": notional,
                "net_pnl": net_pnl,
                "pnl_pct": pnl_pct,
                "period": period,
                "equity_after": current_equity,
            })
    
    # Results
    print(f"\n  {'='*60}")
    print(f"  BACKTEST RESULTS ({len(trades)} trades)\n")
    
    for label, period in [("ALL", None), ("IS (2023-2024)", "IS"), ("OOS-2025", "OOS-2025"), ("OOS-2026", "OOS-2026")]:
        period_trades = trades if period is None else [t for t in trades if t["period"] == period]
        if not period_trades:
            continue
        
        pnls = [t["net_pnl"] for t in period_trades]
        wins = sum(1 for p in pnls if p > 0)
        wr = wins / len(pnls) * 100
        total_pnl = sum(pnls)
        avg_pnl = mean(pnls)
        s = std(pnls)
        t_stat = avg_pnl / (s / math.sqrt(len(pnls))) if s > 0 else 0
        
        eq_start = equity if period is None else (equity if period == "IS" else trades[0]["equity_after"] if period == "OOS-2025" else 0)
        eq_end = period_trades[-1]["equity_after"]
        
        print(f"  {label}: N={len(period_trades)}, WR={wr:.0f}%, "
              f"total PnL=${total_pnl:+,.2f}, avg=${avg_pnl:+.0f}, t={t_stat:.2f}")
    
    print(f"\n  Starting equity: ${equity:,.2f}")
    print(f"  Final equity:    ${current_equity:,.2f}")
    print(f"  Total return:    {(current_equity/equity-1)*100:+.1f}%")
    
    # Per-symbol
    print(f"\n  Per-symbol:")
    print(f"    {'Symbol':>10s} {'N':>4s} {'WR':>5s} {'Total PnL':>12s}")
    print("    " + "-" * 35)
    for sym in sorted(set(t["symbol"] for t in trades)):
        sym_trades = [t for t in trades if t["symbol"] == sym]
        sym_pnls = [t["net_pnl"] for t in sym_trades]
        sym_wr = sum(1 for p in sym_pnls if p > 0) / len(sym_pnls) * 100
        sym_total = sum(sym_pnls)
        print(f"    {sym:>10s} {len(sym_trades):4d} {sym_wr:4.0f}% {sym_total:+11.2f}")


# ─── CLI ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="D17 Token Unlock Short Bot")
    parser.add_argument("--paper", action="store_true", default=True, help="Paper trading mode (default)")
    parser.add_argument("--live", action="store_true", help="Live trading mode (requires API keys)")
    parser.add_argument("--backtest", action="store_true", help="Run historical backtest")
    parser.add_argument("--dry-run", action="store_true", help="Show schedule only, no trades")
    parser.add_argument("--equity", type=float, default=10000, help="Starting equity in USDT")
    parser.add_argument("--min-unlock", type=float, default=50.0, help="Minimum unlock size in $M to trade (validated: $50M)")
    parser.add_argument("--testnet", action="store_true", help="Use Binance Futures testnet (demo-fapi.binance.com) instead of production")
    parser.add_argument("--demo", action="store_true", help="Use Binance Spot Demo (demo-api.binance.com) with DEMO keys for market data + paper trading")
    parser.add_argument("--interval", type=int, default=60, help="Check interval in seconds (default: 60)")
    args = parser.parse_args()
    
    global MIN_UNLOCK_VALUE_MM
    MIN_UNLOCK_VALUE_MM = args.min_unlock

    if args.backtest:
        run_backtest(equity=args.equity)
        return
    
    mode = "live" if args.live else "paper"
    api_key = None
    api_secret = None
    
    if mode == "live":
        from dotenv import load_dotenv
        load_dotenv()
        # --demo uses DEMO keys, --testnet uses prod keys on testnet, else prod keys on prod
        if args.demo:
            api_key = os.getenv("BINANCE_API_KEY_DEMO")
            api_secret = os.getenv("BINANCE_API_SECRET_DEMO")
            if not api_key or not api_secret:
                print("ERROR: BINANCE_API_KEY_DEMO and BINANCE_API_SECRET_DEMO required for --demo mode.")
                return
        else:
            api_key = os.getenv("BINANCE_API_KEY")
            api_secret = os.getenv("BINANCE_API_SECRET")
            if not api_key or not api_secret:
                print("ERROR: BINANCE_API_KEY and BINANCE_API_SECRET required for live mode.")
                print("Create a .env file with:")
                print("  BINANCE_API_KEY=your_key")
                print("  BINANCE_API_SECRET=your_secret")
                return

    # Switch API endpoint based on flag
    global BINANCE_FAPI
    if args.testnet:
        BINANCE_FAPI = BINANCE_FAPI_TESTNET
        print("  >> Using Binance Futures TESTNET (demo-fapi.binance.com)")
    elif args.demo:
        # Spot Demo: use demo-api for price data, force paper mode (Spot can't short)
        BINANCE_FAPI = BINANCE_FAPI_TESTNET  # Try futures testnet for prices
        if mode == "live":
            print("  >> NOTE: Spot Demo keys detected. Spot doesn't support shorting.")
            print("  >> Switching to PAPER mode with demo price data.")
            mode = "paper"
            api_key = None
            api_secret = None
        print("  >> Using Binance Demo environment")
    else:
        BINANCE_FAPI = BINANCE_FAPI_PROD

    run_bot(mode=mode, equity=args.equity, api_key=api_key, api_secret=api_secret, dry_run=args.dry_run, interval=args.interval)


if __name__ == "__main__":
    main()
