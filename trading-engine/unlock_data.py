#!/usr/bin/env python3
"""
Unlock data fetcher — busca calendário de token unlocks de fontes públicas.

Primary: Tokenomist API (https://api.unlocks.app) se TOKENOMIST_API_KEY estiver setada.
Fallback: lista hardcoded atualizada (KNOWN_UNLOCKS do token_unlock_scan.py + extras).

Interface unificada: get_upcoming_unlocks() retorna lista de dicts:
  {symbol, unlock_date, unlock_value_mm, pct_supply, source}
"""
import json
import os
import sys
import urllib.request
import urllib.parse
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(__file__))
from token_unlock_scan import KNOWN_UNLOCKS

TOKENOMIST_API = "https://api.unlocks.app"
UA = {"User-Agent": "unlock-data-fetcher/1.0"}


def fetch_tokenomist_upcoming(min_value_usd=20_000_000, days_ahead=90):
    """Fetch upcoming unlocks from Tokenomist API.

    Requires TOKENOMIST_API_KEY env var.
    Returns list of dicts: {symbol, unlock_date, unlock_value_mm, pct_supply, source}
    """
    api_key = os.getenv("TOKENOMIST_API_KEY")
    if not api_key:
        return None

    now = datetime.now(timezone.utc)
    start = now.strftime("%Y-%m-%d")
    end = (now + _timedelta_days(days_ahead)).strftime("%Y-%m-%d")

    params = {
        "minTotalUnlockAmount": str(min_value_usd),
        "minUnlockDate": start,
        "maxUnlockDate": end,
    }
    url = f"{TOKENOMIST_API}/v1/unlock/events/upcoming?" + urllib.parse.urlencode(params)

    req = urllib.request.Request(url, headers={**UA, "x-api-key": api_key})
    with urllib.request.urlopen(req, timeout=15) as r:
        data = json.loads(r.read().decode())

    events = []
    for item in data.get("data", []):
        symbol = item.get("tokenSymbol", "") + "USDT"
        unlock_date_raw = item.get("unlockDate", "")
        if not unlock_date_raw:
            continue
        unlock_date = unlock_date_raw[:10]  # YYYY-MM-DD

        total_value = 0
        pct_supply = 0
        for cliff in item.get("cliffUnlocks", []):
            total_value += float(cliff.get("cliffValue", 0))
            pct_supply += float(cliff.get("cliffAmount", 0))

        if total_value / 1e6 < 1:  # skip < $1M
            continue

        events.append({
            "symbol": symbol,
            "unlock_date": unlock_date,
            "unlock_value_mm": round(total_value / 1e6, 1),
            "pct_supply": round(pct_supply, 2),
            "source": "TokenomistAPI",
        })

    return sorted(events, key=lambda x: x["unlock_date"])


def get_hardcoded_upcoming(min_value_mm=20):
    """Get upcoming unlocks from hardcoded list (fallback)."""
    now = datetime.now(timezone.utc)
    now_str = now.strftime("%Y-%m-%d")
    upcoming = []
    for sym, date, val, pct, src in KNOWN_UNLOCKS:
        if date >= now_str and val >= min_value_mm:
            upcoming.append({
                "symbol": sym,
                "unlock_date": date,
                "unlock_value_mm": val,
                "pct_supply": pct,
                "source": src,
            })
    return sorted(upcoming, key=lambda x: x["unlock_date"])


def get_upcoming_unlocks(min_value_mm=20, days_ahead=90):
    """Get upcoming unlocks — tries API first, falls back to hardcoded.

    Returns list of dicts: {symbol, unlock_date, unlock_value_mm, pct_supply, source}
    """
    # Try API first
    try:
        api_data = fetch_tokenomist_upcoming(
            min_value_usd=int(min_value_mm * 1e6),
            days_ahead=days_ahead,
        )
        if api_data is not None:
            return api_data
    except Exception as e:
        print(f"[unlock_data] API fetch failed: {e}, using hardcoded fallback")

    # Fallback to hardcoded
    return get_hardcoded_upcoming(min_value_mm=min_value_mm)


def _timedelta_days(n):
    from datetime import timedelta
    return timedelta(days=n)
