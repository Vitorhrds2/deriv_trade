"""
D39 — Max Pain Tracker (continuous hourly logging until 10JUL26 expiry)

Logs BTC/ETH spot price vs max pain every hour to track convergence.
Appends to d39_max_pain_tracker.log for later analysis.

Usage:
  python3 max_pain_tracker.py              # one-shot snapshot
  python3 max_pain_tracker.py --continuous # hourly loop until expiry
"""
import json
import time
import urllib.request
from datetime import datetime, timezone

LOG_FILE = "d39_max_pain_tracker.log"
TRACK_INTERVAL_S = 3600  # 1 hour
DERIBIT_BASE = "https://www.deribit.com/api/v2/public/get_book_summary"
BINANCE_PRICE = "https://api.binance.com/api/v3/ticker/price"


def fetch_json(url, timeout=15):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode())


def fetch_price(symbol="BTCUSDT"):
    try:
        data = fetch_json(f"{BINANCE_PRICE}?symbol={symbol}", timeout=5)
        return float(data["price"])
    except:
        return None


def parse_instrument_name(name):
    """Parse Deribit instrument name: BTC-10JUL26-61000-C -> (expiry_str, strike, opt_type)"""
    parts = name.split("-")
    if len(parts) < 4:
        return None, None, None
    expiry_str = parts[1]
    strike = float(parts[2])
    opt_type = parts[3]  # C or P
    return expiry_str, strike, opt_type


def expiry_str_to_ts(expiry_str):
    """Convert '10JUL26' to timestamp ms."""
    try:
        from datetime import datetime
        dt = datetime.strptime(expiry_str, "%d%b%y")
        return int(dt.timestamp() * 1000)
    except:
        return None


def fetch_max_pain(currency="BTC"):
    """Fetch Deribit options book summary and compute max pain for nearest expiry."""
    try:
        url = f"https://www.deribit.com/api/v2/public/get_book_summary_by_currency?currency={currency}&kind=option"
        data = fetch_json(url, timeout=15)
        summaries = data.get("result", [])

        if not summaries:
            return None, None, None

        # Parse instrument names to get expiry info
        now_ms = int(time.time() * 1000)
        expiry_map = {}
        for s in summaries:
            name = s.get("instrument_name", "")
            expiry_str, strike, opt_type = parse_instrument_name(name)
            if not expiry_str:
                continue
            expiry_ts = expiry_str_to_ts(expiry_str)
            if not expiry_ts or expiry_ts <= now_ms:
                continue
            if expiry_str not in expiry_map:
                expiry_map[expiry_str] = {"ts": expiry_ts, "instruments": []}
            oi = s.get("open_interest", 0)
            expiry_map[expiry_str]["instruments"].append({
                "strike": strike,
                "opt_type": opt_type,
                "oi": oi,
            })

        if not expiry_map:
            return None, None, None

        # Find nearest expiry
        nearest = min(expiry_map.values(), key=lambda v: v["ts"])
        nearest_expiry_str = [k for k, v in expiry_map.items() if v is nearest][0]

        # Compute max pain
        instruments = nearest["instruments"]
        strikes = sorted(set(i["strike"] for i in instruments))
        if not strikes:
            return None, None, None

        # Build OI map
        oi_map = {}
        for i in instruments:
            if i["strike"] not in oi_map:
                oi_map[i["strike"]] = {"C": 0, "P": 0}
            oi_map[i["strike"]][i["opt_type"]] += i["oi"]

        # Compute pain for each settlement price
        pain_by_strike = {}
        for settle_price in strikes:
            total_pain = 0
            for strike in strikes:
                call_oi = oi_map[strike]["C"]
                put_oi = oi_map[strike]["P"]
                if settle_price > strike:
                    total_pain += call_oi * (settle_price - strike)
                if settle_price < strike:
                    total_pain += put_oi * (strike - settle_price)
            pain_by_strike[settle_price] = total_pain

        max_pain = min(pain_by_strike, key=pain_by_strike.get)
        total_oi = sum(sum(oi.values()) for oi in oi_map.values())

        return max_pain, nearest_expiry_str, total_oi

    except Exception as e:
        print(f"  Max pain fetch error: {e}")
        return None, None, None


def track_once():
    """Take one snapshot of price vs max pain."""
    ts = datetime.now(timezone.utc)
    btc_price = fetch_price("BTCUSDT")
    eth_price = fetch_price("ETHUSDT")

    btc_mp, btc_expiry, btc_oi = fetch_max_pain("BTC")
    eth_mp, eth_expiry, eth_oi = fetch_max_pain("ETH")

    line = f"[{ts.isoformat()[:19]}]"
    if btc_price and btc_mp:
        diff_pct = (btc_price - btc_mp) / btc_mp * 100
        line += f" BTC: spot=${btc_price:,.0f} max_pain=${btc_mp:,.0f} diff={diff_pct:+.2f}% expiry={btc_expiry} OI={btc_oi}"
    else:
        line += " BTC: fetch failed"

    if eth_price and eth_mp:
        diff_pct = (eth_price - eth_mp) / eth_mp * 100
        line += f" | ETH: spot=${eth_price:,.0f} max_pain=${eth_mp:,.0f} diff={diff_pct:+.2f}% expiry={eth_expiry} OI={eth_oi}"
    else:
        line += " | ETH: fetch failed"

    print(line)
    with open(LOG_FILE, "a") as f:
        f.write(line + "\n")

    return {
        "timestamp": ts.isoformat(),
        "btc": {"spot": btc_price, "max_pain": btc_mp, "expiry": btc_expiry, "oi": btc_oi},
        "eth": {"spot": eth_price, "max_pain": eth_mp, "expiry": eth_expiry, "oi": eth_oi},
    }


if __name__ == "__main__":
    import sys
    print("=" * 80)
    print("D39 — Max Pain Tracker (hourly logging until 10JUL26 expiry)")
    print("=" * 80)

    if "--continuous" in sys.argv:
        print(f"CONTINUOUS MODE — logging every {TRACK_INTERVAL_S}s to {LOG_FILE}")
        while True:
            try:
                track_once()
            except Exception as e:
                print(f"  Error: {e}")
            time.sleep(TRACK_INTERVAL_S)
    else:
        track_once()
