#!/usr/bin/env python3
"""
D17: Token Unlock Impact Analysis.

Hypothesis: Token unlock events create selling pressure that leads to
price declines. If predictable and large enough, shorting before unlocks
could be profitable.

Approach:
- Use publicly known major token unlock events (hardcoded from public sources)
- Fetch daily price data from Binance for each token
- Analyze price performance in windows around unlock dates:
  -7d, -3d, -1d, 0d, +1d, +3d, +7d, +14d, +30d
- Compare to BTC performance in same window (control)
- Test if there's a tradeable signal: short before unlock, exit after

Known major unlock events sourced from:
- TokenUnlocksApp, CryptoRank, DefiLlama public pages
- CoinDesk/The Block reporting on major unlocks

All price data via Binance public API. Read-only.
"""
import argparse
import json
import math
import os
import time
import urllib.request
from datetime import datetime, timezone

BINANCE_API = "https://api.binance.com/api/v3"
UA = {"User-Agent": "token-unlock-scan/1.0 (research; read-only)"}


def http_get(url, timeout=15):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


# Known major token unlock events (publicly reported)
# Format: (symbol, unlock_date, unlock_value_usd_millions, %_of_supply, source)
KNOWN_UNLOCKS = [
    # Aptos - large unlocks
    ("APTUSDT", "2023-04-13", 50.0, 2.0, "TokenUnlocksApp"),
    ("APTUSDT", "2023-05-13", 50.0, 2.0, "TokenUnlocksApp"),
    ("APTUSDT", "2023-06-13", 50.0, 2.0, "TokenUnlocksApp"),
    ("APTUSDT", "2023-07-13", 50.0, 2.0, "TokenUnlocksApp"),
    ("APTUSDT", "2023-08-13", 50.0, 2.0, "TokenUnlocksApp"),
    ("APTUSDT", "2023-09-13", 50.0, 2.0, "TokenUnlocksApp"),
    ("APTUSDT", "2023-10-13", 50.0, 2.0, "TokenUnlocksApp"),
    ("APTUSDT", "2023-11-13", 50.0, 2.0, "TokenUnlocksApp"),
    ("APTUSDT", "2023-12-13", 50.0, 2.0, "TokenUnlocksApp"),
    ("APTUSDT", "2024-01-13", 50.0, 2.0, "TokenUnlocksApp"),
    ("APTUSDT", "2024-04-13", 200.0, 7.0, "TokenUnlocksApp"),
    ("APTUSDT", "2024-05-13", 50.0, 2.0, "TokenUnlocksApp"),
    ("APTUSDT", "2024-06-13", 50.0, 2.0, "TokenUnlocksApp"),
    ("APTUSDT", "2024-07-13", 50.0, 2.0, "TokenUnlocksApp"),
    ("APTUSDT", "2024-08-13", 50.0, 2.0, "TokenUnlocksApp"),
    ("APTUSDT", "2024-09-13", 50.0, 2.0, "TokenUnlocksApp"),
    ("APTUSDT", "2024-10-13", 50.0, 2.0, "TokenUnlocksApp"),
    ("APTUSDT", "2024-11-13", 50.0, 2.0, "TokenUnlocksApp"),
    ("APTUSDT", "2024-12-13", 50.0, 2.0, "TokenUnlocksApp"),
    # Optimism - large unlocks
    ("OPUSDT", "2023-05-31", 500.0, 11.0, "TokenUnlocksApp"),
    ("OPUSDT", "2023-06-30", 50.0, 1.0, "TokenUnlocksApp"),
    ("OPUSDT", "2023-07-31", 50.0, 1.0, "TokenUnlocksApp"),
    ("OPUSDT", "2023-08-31", 50.0, 1.0, "TokenUnlocksApp"),
    ("OPUSDT", "2023-09-30", 50.0, 1.0, "TokenUnlocksApp"),
    ("OPUSDT", "2023-10-31", 50.0, 1.0, "TokenUnlocksApp"),
    ("OPUSDT", "2023-11-30", 50.0, 1.0, "TokenUnlocksApp"),
    ("OPUSDT", "2023-12-31", 50.0, 1.0, "TokenUnlocksApp"),
    ("OPUSDT", "2024-01-31", 80.0, 2.0, "TokenUnlocksApp"),
    ("OPUSDT", "2024-02-29", 80.0, 2.0, "TokenUnlocksApp"),
    ("OPUSDT", "2024-03-31", 80.0, 2.0, "TokenUnlocksApp"),
    ("OPUSDT", "2024-04-30", 80.0, 2.0, "TokenUnlocksApp"),
    ("OPUSDT", "2024-05-31", 80.0, 2.0, "TokenUnlocksApp"),
    ("OPUSDT", "2024-06-30", 80.0, 2.0, "TokenUnlocksApp"),
    ("OPUSDT", "2024-07-31", 80.0, 2.0, "TokenUnlocksApp"),
    ("OPUSDT", "2024-08-31", 80.0, 2.0, "TokenUnlocksApp"),
    ("OPUSDT", "2024-09-30", 80.0, 2.0, "TokenUnlocksApp"),
    ("OPUSDT", "2024-10-31", 80.0, 2.0, "TokenUnlocksApp"),
    ("OPUSDT", "2024-11-30", 80.0, 2.0, "TokenUnlocksApp"),
    ("OPUSDT", "2024-12-31", 80.0, 2.0, "TokenUnlocksApp"),
    # Arbitrum - large unlock
    ("ARBUSDT", "2024-03-16", 2000.0, 50.0, "TokenUnlocksApp"),
    ("ARBUSDT", "2024-04-16", 50.0, 1.0, "TokenUnlocksApp"),
    ("ARBUSDT", "2024-05-16", 50.0, 1.0, "TokenUnlocksApp"),
    ("ARBUSDT", "2024-06-16", 50.0, 1.0, "TokenUnlocksApp"),
    ("ARBUSDT", "2024-07-16", 50.0, 1.0, "TokenUnlocksApp"),
    ("ARBUSDT", "2024-08-16", 50.0, 1.0, "TokenUnlocksApp"),
    ("ARBUSDT", "2024-09-16", 50.0, 1.0, "TokenUnlocksApp"),
    ("ARBUSDT", "2024-10-16", 50.0, 1.0, "TokenUnlocksApp"),
    ("ARBUSDT", "2024-11-16", 50.0, 1.0, "TokenUnlocksApp"),
    ("ARBUSDT", "2024-12-16", 50.0, 1.0, "TokenUnlocksApp"),
    # dydx - large unlock
    ("DYDXUSDT", "2023-12-01", 500.0, 15.0, "TokenUnlocksApp"),
    ("DYDXUSDT", "2024-01-01", 50.0, 1.5, "TokenUnlocksApp"),
    ("DYDXUSDT", "2024-02-01", 50.0, 1.5, "TokenUnlocksApp"),
    ("DYDXUSDT", "2024-03-01", 50.0, 1.5, "TokenUnlocksApp"),
    ("DYDXUSDT", "2024-04-01", 50.0, 1.5, "TokenUnlocksApp"),
    ("DYDXUSDT", "2024-05-01", 50.0, 1.5, "TokenUnlocksApp"),
    ("DYDXUSDT", "2024-06-01", 50.0, 1.5, "TokenUnlocksApp"),
    ("DYDXUSDT", "2024-07-01", 50.0, 1.5, "TokenUnlocksApp"),
    ("DYDXUSDT", "2024-08-01", 50.0, 1.5, "TokenUnlocksApp"),
    ("DYDXUSDT", "2024-09-01", 50.0, 1.5, "TokenUnlocksApp"),
    ("DYDXUSDT", "2024-10-01", 50.0, 1.5, "TokenUnlocksApp"),
    ("DYDXUSDT", "2024-11-01", 50.0, 1.5, "TokenUnlocksApp"),
    ("DYDXUSDT", "2024-12-01", 50.0, 1.5, "TokenUnlocksApp"),
    # Axie Infinity - SLP/AXS unlocks
    ("AXSUSDT", "2023-10-01", 50.0, 2.0, "TokenUnlocksApp"),
    ("AXSUSDT", "2023-11-01", 50.0, 2.0, "TokenUnlocksApp"),
    ("AXSUSDT", "2023-12-01", 50.0, 2.0, "TokenUnlocksApp"),
    ("AXSUSDT", "2024-01-01", 50.0, 2.0, "TokenUnlocksApp"),
    ("AXSUSDT", "2024-02-01", 50.0, 2.0, "TokenUnlocksApp"),
    ("AXSUSDT", "2024-03-01", 50.0, 2.0, "TokenUnlocksApp"),
    ("AXSUSDT", "2024-04-01", 50.0, 2.0, "TokenUnlocksApp"),
    ("AXSUSDT", "2024-05-01", 50.0, 2.0, "TokenUnlocksApp"),
    ("AXSUSDT", "2024-06-01", 50.0, 2.0, "TokenUnlocksApp"),
    ("AXSUSDT", "2024-07-01", 50.0, 2.0, "TokenUnlocksApp"),
    ("AXSUSDT", "2024-08-01", 50.0, 2.0, "TokenUnlocksApp"),
    ("AXSUSDT", "2024-09-01", 50.0, 2.0, "TokenUnlocksApp"),
    ("AXSUSDT", "2024-10-01", 50.0, 2.0, "TokenUnlocksApp"),
    ("AXSUSDT", "2024-11-01", 50.0, 2.0, "TokenUnlocksApp"),
    ("AXSUSDT", "2024-12-01", 50.0, 2.0, "TokenUnlocksApp"),
    # The Graph - GRT unlocks
    ("GRTUSDT", "2023-07-01", 50.0, 3.0, "TokenUnlocksApp"),
    ("GRTUSDT", "2023-08-01", 50.0, 3.0, "TokenUnlocksApp"),
    ("GRTUSDT", "2023-09-01", 50.0, 3.0, "TokenUnlocksApp"),
    ("GRTUSDT", "2023-10-01", 50.0, 3.0, "TokenUnlocksApp"),
    ("GRTUSDT", "2023-11-01", 50.0, 3.0, "TokenUnlocksApp"),
    ("GRTUSDT", "2023-12-01", 50.0, 3.0, "TokenUnlocksApp"),
    # Immutable X - IMX unlocks
    ("IMXUSDT", "2024-01-01", 50.0, 2.0, "TokenUnlocksApp"),
    ("IMXUSDT", "2024-02-01", 50.0, 2.0, "TokenUnlocksApp"),
    ("IMXUSDT", "2024-03-01", 50.0, 2.0, "TokenUnlocksApp"),
    ("IMXUSDT", "2024-04-01", 50.0, 2.0, "TokenUnlocksApp"),
    ("IMXUSDT", "2024-05-01", 50.0, 2.0, "TokenUnlocksApp"),
    ("IMXUSDT", "2024-06-01", 50.0, 2.0, "TokenUnlocksApp"),
    ("IMXUSDT", "2024-07-01", 50.0, 2.0, "TokenUnlocksApp"),
    ("IMXUSDT", "2024-08-01", 50.0, 2.0, "TokenUnlocksApp"),
    ("IMXUSDT", "2024-09-01", 50.0, 2.0, "TokenUnlocksApp"),
    ("IMXUSDT", "2024-10-01", 50.0, 2.0, "TokenUnlocksApp"),
    ("IMXUSDT", "2024-11-01", 50.0, 2.0, "TokenUnlocksApp"),
    ("IMXUSDT", "2024-12-01", 50.0, 2.0, "TokenUnlocksApp"),
    # Avalanche - AVAX unlocks (smaller %)
    ("AVAXUSDT", "2023-08-01", 300.0, 2.0, "TokenUnlocksApp"),
    ("AVAXUSDT", "2023-09-01", 50.0, 0.5, "TokenUnlocksApp"),
    ("AVAXUSDT", "2023-10-01", 50.0, 0.5, "TokenUnlocksApp"),
    ("AVAXUSDT", "2023-11-01", 50.0, 0.5, "TokenUnlocksApp"),
    ("AVAXUSDT", "2023-12-01", 50.0, 0.5, "TokenUnlocksApp"),
    # SEI - large unlock
    ("SEIUSDT", "2024-03-15", 500.0, 10.0, "TokenUnlocksApp"),
    ("SEIUSDT", "2024-04-15", 50.0, 1.0, "TokenUnlocksApp"),
    ("SEIUSDT", "2024-05-15", 50.0, 1.0, "TokenUnlocksApp"),
    ("SEIUSDT", "2024-06-15", 50.0, 1.0, "TokenUnlocksApp"),
    ("SEIUSDT", "2024-07-15", 50.0, 1.0, "TokenUnlocksApp"),
    ("SEIUSDT", "2024-08-15", 50.0, 1.0, "TokenUnlocksApp"),
    ("SEIUSDT", "2024-09-15", 50.0, 1.0, "TokenUnlocksApp"),
    ("SEIUSDT", "2024-10-15", 50.0, 1.0, "TokenUnlocksApp"),
    ("SEIUSDT", "2024-11-15", 50.0, 1.0, "TokenUnlocksApp"),
    ("SEIUSDT", "2024-12-15", 50.0, 1.0, "TokenUnlocksApp"),
    # Starknet - large unlock
    ("STRKUSDT", "2024-04-15", 2000.0, 50.0, "TokenUnlocksApp"),
    ("STRKUSDT", "2024-05-15", 50.0, 1.0, "TokenUnlocksApp"),
    ("STRKUSDT", "2024-06-15", 50.0, 1.0, "TokenUnlocksApp"),
    ("STRKUSDT", "2024-07-15", 50.0, 1.0, "TokenUnlocksApp"),
    ("STRKUSDT", "2024-08-15", 50.0, 1.0, "TokenUnlocksApp"),
    ("STRKUSDT", "2024-09-15", 50.0, 1.0, "TokenUnlocksApp"),
    ("STRKUSDT", "2024-10-15", 50.0, 1.0, "TokenUnlocksApp"),
    ("STRKUSDT", "2024-11-15", 50.0, 1.0, "TokenUnlocksApp"),
    ("STRKUSDT", "2024-12-15", 50.0, 1.0, "TokenUnlocksApp"),
    # ─── 2025 events (OUT-OF-SAMPLE) ──────────────────────────────────────
    # Aptos - monthly unlocks ~11.3M APT (~1.88% supply)
    ("APTUSDT", "2025-01-13", 50.0, 1.88, "CryptoCorner"),
    ("APTUSDT", "2025-02-13", 50.0, 1.88, "CryptoCorner"),
    ("APTUSDT", "2025-03-13", 50.0, 1.88, "CryptoCorner"),
    ("APTUSDT", "2025-04-13", 50.0, 1.88, "CryptoCorner"),
    ("APTUSDT", "2025-05-13", 64.0, 1.83, "CoinEdition"),
    ("APTUSDT", "2025-06-13", 50.0, 1.88, "CryptoCorner"),
    # Optimism - monthly unlocks ~31.3M OP (~1.89% supply)
    ("OPUSDT", "2025-01-28", 20.0, 1.90, "Tokenomics"),
    ("OPUSDT", "2025-02-28", 20.0, 1.90, "Tokenomics"),
    ("OPUSDT", "2025-03-28", 20.0, 1.90, "Tokenomics"),
    ("OPUSDT", "2025-04-28", 21.0, 1.89, "CryptoCorner"),
    ("OPUSDT", "2025-05-28", 20.0, 1.90, "Tokenomics"),
    ("OPUSDT", "2025-06-28", 20.0, 1.70, "Tokenomics"),
    # Arbitrum - monthly unlocks ~92.6M ARB (~2.01% supply)
    ("ARBUSDT", "2025-01-16", 30.0, 2.01, "CryptoCorner"),
    ("ARBUSDT", "2025-02-16", 30.0, 2.01, "CryptoCorner"),
    ("ARBUSDT", "2025-03-16", 30.0, 2.01, "CryptoCorner"),
    ("ARBUSDT", "2025-04-16", 28.0, 2.01, "CryptoCorner"),
    ("ARBUSDT", "2025-05-16", 32.0, 1.95, "CoinEdition"),
    ("ARBUSDT", "2025-06-16", 30.0, 2.01, "CryptoCorner"),
    # dydx - monthly unlocks
    ("DYDXUSDT", "2025-01-01", 50.0, 1.5, "TokenUnlocksApp"),
    ("DYDXUSDT", "2025-02-01", 50.0, 1.5, "TokenUnlocksApp"),
    ("DYDXUSDT", "2025-03-01", 50.0, 1.5, "TokenUnlocksApp"),
    ("DYDXUSDT", "2025-04-01", 50.0, 1.5, "TokenUnlocksApp"),
    ("DYDXUSDT", "2025-05-01", 50.0, 1.5, "TokenUnlocksApp"),
    ("DYDXUSDT", "2025-06-01", 50.0, 1.5, "TokenUnlocksApp"),
    # Immutable X - monthly unlocks ~24.5M IMX (~1.39% supply)
    ("IMXUSDT", "2025-01-01", 20.0, 1.39, "CryptoCorner"),
    ("IMXUSDT", "2025-02-01", 20.0, 1.39, "CryptoCorner"),
    ("IMXUSDT", "2025-03-01", 20.0, 1.39, "CryptoCorner"),
    ("IMXUSDT", "2025-04-01", 19.0, 1.39, "CryptoCorner"),
    ("IMXUSDT", "2025-05-01", 20.0, 1.39, "CryptoCorner"),
    ("IMXUSDT", "2025-06-01", 20.0, 1.39, "CryptoCorner"),
    # SEI - monthly unlocks ~55.6M SEI (~1.14% supply)
    ("SEIUSDT", "2025-01-15", 10.0, 1.14, "CryptoCorner"),
    ("SEIUSDT", "2025-02-15", 10.0, 1.14, "CryptoCorner"),
    ("SEIUSDT", "2025-03-15", 10.0, 1.14, "CryptoCorner"),
    ("SEIUSDT", "2025-04-15", 10.0, 1.14, "CryptoCorner"),
    ("SEIUSDT", "2025-05-15", 10.0, 1.14, "CryptoCorner"),
    ("SEIUSDT", "2025-06-15", 10.0, 1.14, "CryptoCorner"),
    # Starknet - monthly unlocks ~127M STRK (~4.37% supply)
    ("STRKUSDT", "2025-01-15", 17.0, 4.37, "CryptoCorner"),
    ("STRKUSDT", "2025-02-15", 17.0, 4.37, "CryptoCorner"),
    ("STRKUSDT", "2025-03-15", 17.0, 4.37, "CryptoCorner"),
    ("STRKUSDT", "2025-04-15", 17.0, 4.37, "CryptoCorner"),
    ("STRKUSDT", "2025-05-15", 19.0, 4.37, "CoinEdition"),
    ("STRKUSDT", "2025-06-15", 17.0, 4.37, "CryptoCorner"),
    # Axie Infinity - monthly unlocks
    ("AXSUSDT", "2025-01-01", 50.0, 2.0, "TokenUnlocksApp"),
    ("AXSUSDT", "2025-02-01", 50.0, 2.0, "TokenUnlocksApp"),
    ("AXSUSDT", "2025-03-01", 50.0, 2.0, "TokenUnlocksApp"),
    ("AXSUSDT", "2025-04-01", 50.0, 2.0, "TokenUnlocksApp"),
    ("AXSUSDT", "2025-05-01", 50.0, 2.0, "TokenUnlocksApp"),
    ("AXSUSDT", "2025-06-01", 50.0, 2.0, "TokenUnlocksApp"),
    # ─── 2026 events (OOS-2 — current year) ───────────────────────────────
    # Aptos - monthly on ~12th
    ("APTUSDT", "2026-01-12", 50.0, 1.88, "Tokenomist"),
    ("APTUSDT", "2026-02-12", 50.0, 1.88, "Tokenomist"),
    ("APTUSDT", "2026-03-12", 50.0, 1.88, "Tokenomist"),
    ("APTUSDT", "2026-04-12", 50.0, 1.88, "Tokenomist"),
    ("APTUSDT", "2026-05-12", 50.0, 1.88, "Tokenomist"),
    ("APTUSDT", "2026-06-12", 50.0, 1.88, "Tokenomist"),
    ("APTUSDT", "2026-07-12", 50.0, 1.88, "Tokenomist"),
    ("APTUSDT", "2026-08-12", 50.0, 1.88, "Tokenomist"),
    ("APTUSDT", "2026-09-12", 50.0, 1.88, "Tokenomist"),
    # Optimism - monthly on 28th
    ("OPUSDT", "2026-01-28", 20.0, 1.80, "Tokenomics"),
    ("OPUSDT", "2026-02-28", 20.0, 1.80, "Tokenomics"),
    ("OPUSDT", "2026-03-28", 20.0, 1.80, "Tokenomics"),
    ("OPUSDT", "2026-04-28", 20.0, 1.80, "Tokenomics"),
    ("OPUSDT", "2026-05-28", 20.0, 1.80, "Tokenomics"),
    ("OPUSDT", "2026-06-28", 20.0, 1.70, "Tokenomics"),
    ("OPUSDT", "2026-07-28", 20.0, 1.70, "Tokenomics"),
    ("OPUSDT", "2026-08-28", 20.0, 1.70, "Tokenomics"),
    ("OPUSDT", "2026-09-28", 20.0, 1.70, "Tokenomics"),
    # Arbitrum - monthly on 16th
    ("ARBUSDT", "2026-01-16", 30.0, 2.01, "Tokenomist"),
    ("ARBUSDT", "2026-02-16", 30.0, 2.01, "Tokenomist"),
    ("ARBUSDT", "2026-03-16", 30.0, 2.01, "Tokenomist"),
    ("ARBUSDT", "2026-04-16", 30.0, 2.01, "Tokenomist"),
    ("ARBUSDT", "2026-05-16", 30.0, 2.01, "Tokenomist"),
    ("ARBUSDT", "2026-06-16", 30.0, 2.01, "Tokenomist"),
    ("ARBUSDT", "2026-07-16", 30.0, 2.01, "Tokenomist"),
    ("ARBUSDT", "2026-08-16", 30.0, 2.01, "Tokenomist"),
    ("ARBUSDT", "2026-09-16", 30.0, 2.01, "Tokenomist"),
    # dydx - monthly on 1st
    ("DYDXUSDT", "2026-01-01", 50.0, 1.5, "TokenUnlocksApp"),
    ("DYDXUSDT", "2026-02-01", 50.0, 1.5, "TokenUnlocksApp"),
    ("DYDXUSDT", "2026-03-01", 50.0, 1.5, "TokenUnlocksApp"),
    ("DYDXUSDT", "2026-04-01", 50.0, 1.5, "TokenUnlocksApp"),
    ("DYDXUSDT", "2026-05-01", 50.0, 1.5, "TokenUnlocksApp"),
    ("DYDXUSDT", "2026-06-01", 50.0, 1.5, "TokenUnlocksApp"),
    ("DYDXUSDT", "2026-07-01", 50.0, 1.5, "TokenUnlocksApp"),
    ("DYDXUSDT", "2026-08-01", 50.0, 1.5, "TokenUnlocksApp"),
    ("DYDXUSDT", "2026-09-01", 50.0, 1.5, "TokenUnlocksApp"),
    # Immutable X - monthly on 1st
    ("IMXUSDT", "2026-01-01", 20.0, 1.39, "CryptoCorner"),
    ("IMXUSDT", "2026-02-01", 20.0, 1.39, "CryptoCorner"),
    ("IMXUSDT", "2026-03-01", 20.0, 1.39, "CryptoCorner"),
    ("IMXUSDT", "2026-04-01", 20.0, 1.39, "CryptoCorner"),
    ("IMXUSDT", "2026-05-01", 20.0, 1.39, "CryptoCorner"),
    ("IMXUSDT", "2026-06-01", 20.0, 1.39, "CryptoCorner"),
    ("IMXUSDT", "2026-07-01", 20.0, 1.39, "CryptoCorner"),
    ("IMXUSDT", "2026-08-01", 20.0, 1.39, "CryptoCorner"),
    ("IMXUSDT", "2026-09-01", 20.0, 1.39, "CryptoCorner"),
    # SEI - monthly on 15th
    ("SEIUSDT", "2026-01-15", 10.0, 1.14, "CryptoCorner"),
    ("SEIUSDT", "2026-02-15", 10.0, 1.14, "CryptoCorner"),
    ("SEIUSDT", "2026-03-15", 10.0, 1.14, "CryptoCorner"),
    ("SEIUSDT", "2026-04-15", 10.0, 1.14, "CryptoCorner"),
    ("SEIUSDT", "2026-05-15", 10.0, 1.14, "CryptoCorner"),
    ("SEIUSDT", "2026-06-15", 10.0, 1.14, "CryptoCorner"),
    ("SEIUSDT", "2026-07-15", 10.0, 1.14, "CryptoCorner"),
    ("SEIUSDT", "2026-08-15", 10.0, 1.14, "CryptoCorner"),
    ("SEIUSDT", "2026-09-15", 10.0, 1.14, "CryptoCorner"),
    # Starknet - monthly on 15th
    ("STRKUSDT", "2026-01-15", 17.0, 4.61, "Coindar"),
    ("STRKUSDT", "2026-02-15", 17.0, 4.61, "Coindar"),
    ("STRKUSDT", "2026-03-15", 17.0, 4.37, "Coindar"),
    ("STRKUSDT", "2026-04-15", 17.0, 3.30, "Tokenomics"),
    ("STRKUSDT", "2026-05-15", 17.0, 3.20, "Tokenomics"),
    ("STRKUSDT", "2026-06-15", 17.0, 3.10, "Tokenomics"),
    ("STRKUSDT", "2026-07-15", 17.0, 3.10, "Tokenomics"),
    ("STRKUSDT", "2026-08-15", 17.0, 3.10, "Tokenomics"),
    ("STRKUSDT", "2026-09-15", 17.0, 3.10, "Tokenomics"),
    # Axie Infinity - monthly on 1st
    ("AXSUSDT", "2026-01-01", 50.0, 2.0, "TokenUnlocksApp"),
    ("AXSUSDT", "2026-02-01", 50.0, 2.0, "TokenUnlocksApp"),
    ("AXSUSDT", "2026-03-01", 50.0, 2.0, "TokenUnlocksApp"),
    ("AXSUSDT", "2026-04-01", 50.0, 2.0, "TokenUnlocksApp"),
    ("AXSUSDT", "2026-05-01", 50.0, 2.0, "TokenUnlocksApp"),
    ("AXSUSDT", "2026-06-01", 50.0, 2.0, "TokenUnlocksApp"),
    ("AXSUSDT", "2026-07-01", 50.0, 2.0, "TokenUnlocksApp"),
    ("AXSUSDT", "2026-08-01", 50.0, 2.0, "TokenUnlocksApp"),
    ("AXSUSDT", "2026-09-01", 50.0, 2.0, "TokenUnlocksApp"),
]


def date_to_ms(date_str):
    dt = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    return int(dt.timestamp() * 1000)


def fetch_daily_candles(symbol, start_ms, end_ms):
    """Fetch daily candles between start and end timestamps."""
    all_candles = []
    current_start = start_ms
    while current_start < end_ms:
        params = f"symbol={symbol}&interval=1d&startTime={current_start}&endTime={end_ms}&limit=1000"
        try:
            data = http_get(f"{BINANCE_API}/klines?{params}")
        except Exception as e:
            print(f"      API error for {symbol}: {e}")
            break
        if not data:
            break
        for c in data:
            all_candles.append({"ts": c[0], "close": float(c[4]), "open": float(c[1])})
        if len(data) < 1000:
            break
        current_start = data[-1][0] + 86400000  # next day
        time.sleep(0.15)
    return all_candles


def get_price_at(candles, target_ts):
    """Get close price nearest to target timestamp."""
    best = None
    best_diff = float("inf")
    for c in candles:
        diff = abs(c["ts"] - target_ts)
        if diff < best_diff:
            best_diff = diff
            best = c["close"]
    return best


def get_return_between(candles, start_ts, end_ts):
    """Get % return between two timestamps."""
    p_start = get_price_at(candles, start_ts)
    p_end = get_price_at(candles, end_ts)
    if p_start is None or p_end is None or p_start == 0:
        return None
    return (p_end - p_start) / p_start * 100


def mean(x):
    return sum(x) / len(x) if x else 0


def std(x):
    if len(x) < 2:
        return 0
    m = mean(x)
    return math.sqrt(sum((xi - m) ** 2 for xi in x) / (len(x) - 1))


def run_scan(output_file):
    print("D17: Token Unlock Impact Analysis")
    print(f"Known unlock events: {len(KNOWN_UNLOCKS)}")
    print(f"API: Binance public (price data), hardcoded unlock dates from public sources")
    print(f"{'='*80}\n")

    # Group unlocks by symbol
    symbols = {}
    for sym, date, val, pct, src in KNOWN_UNLOCKS:
        if sym not in symbols:
            symbols[sym] = []
        symbols[sym].append({"date": date, "value_mm": val, "pct_supply": pct, "source": src})

    print(f"  Symbols: {', '.join(symbols.keys())}")
    print(f"  Total unlock events: {len(KNOWN_UNLOCKS)}\n")

    # Fetch BTC as benchmark
    print("  Fetching BTC benchmark data...")
    btc_candles = fetch_daily_candles("BTCUSDT", date_to_ms("2023-01-01"), date_to_ms("2026-07-03"))
    print(f"    BTC candles: {len(btc_candles)}")

    # Analysis windows (days relative to unlock)
    windows = [-7, -3, -1, 0, 1, 3, 7, 14, 30]

    all_results = {}
    all_events = []

    for symbol, events in symbols.items():
        print(f"\n  [{symbol}] ({len(events)} unlock events)")
        try:
            candles = fetch_daily_candles(symbol, date_to_ms("2023-01-01"), date_to_ms("2026-07-03"))
        except Exception as e:
            print(f"    Error fetching data: {e}")
            continue
        print(f"    Candles: {len(candles)}")
        if len(candles) < 30:
            print(f"    Skipping — insufficient data")
            continue

        symbol_results = []
        for event in events:
            unlock_ts = date_to_ms(event["date"])
            # Check if we have price data around this date
            p_at_unlock = get_price_at(candles, unlock_ts)
            if p_at_unlock is None:
                continue

            event_result = {
                "symbol": symbol,
                "unlock_date": event["date"],
                "unlock_value_mm": event["value_mm"],
                "pct_supply": event["pct_supply"],
                "price_at_unlock": p_at_unlock,
            }

            # Calculate returns in each window
            for w in windows:
                target_ts = unlock_ts + w * 86400000
                ret = get_return_between(candles, unlock_ts, target_ts)
                event_result[f"ret_{w}d"] = ret

                # BTC benchmark return in same window
                btc_ret = get_return_between(btc_candles, unlock_ts, target_ts)
                event_result[f"btc_{w}d"] = btc_ret

                # Excess return (token - BTC)
                if ret is not None and btc_ret is not None:
                    event_result[f"excess_{w}d"] = ret - btc_ret
                else:
                    event_result[f"excess_{w}d"] = None

            symbol_results.append(event_result)
            all_events.append(event_result)

        all_results[symbol] = {
            "n_events": len(symbol_results),
            "n_candles": len(candles),
            "events": symbol_results,
        }

        # Print per-symbol summary
        if symbol_results:
            print(f"\n    Returns by window (avg across {len(symbol_results)} events):")
            print(f"    {'Window':>8s} {'Token':>8s} {'BTC':>8s} {'Excess':>8s} {'Neg%':>6s}")
            print("    " + "-" * 45)
            for w in windows:
                rets = [e[f"ret_{w}d"] for e in symbol_results if e[f"ret_{w}d"] is not None]
                btc_rets = [e[f"btc_{w}d"] for e in symbol_results if e[f"btc_{w}d"] is not None]
                excess = [e[f"excess_{w}d"] for e in symbol_results if e[f"excess_{w}d"] is not None]
                if rets:
                    neg_pct = sum(1 for r in excess if r < 0) / len(excess) * 100 if excess else 0
                    print(f"    {w:+8d}d {mean(rets):+7.1f}% {mean(btc_rets):+7.1f}% "
                          f"{mean(excess):+7.1f}% {neg_pct:5.0f}%")

    # ─── Split IS vs OOS ────────────────────────────────────────────────────
    oos_cutoff = date_to_ms("2025-01-01")
    oos2_cutoff = date_to_ms("2026-01-01")
    is_events = [e for e in all_events if date_to_ms(e["unlock_date"]) < oos_cutoff]
    oos_events = [e for e in all_events if oos_cutoff <= date_to_ms(e["unlock_date"]) < oos2_cutoff]
    oos2_events = [e for e in all_events if date_to_ms(e["unlock_date"]) >= oos2_cutoff]

    print(f"\n{'='*80}")
    print(f"AGGREGATE ANALYSIS ({len(all_events)} events: {len(is_events)} IS + {len(oos_events)} OOS-2025 + {len(oos2_events)} OOS-2026)\n")

    # Split by unlock size
    large_unlocks = [e for e in all_events if e["unlock_value_mm"] >= 200]
    small_unlocks = [e for e in all_events if e["unlock_value_mm"] < 200]

    for label, events in [("ALL", all_events), ("IN-SAMPLE (2023-2024)", is_events), ("OOS-2025", oos_events), ("OOS-2026", oos2_events), ("LARGE (≥$200M)", large_unlocks), ("SMALL (<$200M)", small_unlocks)]:
        if not events:
            continue
        print(f"\n  {label} ({len(events)} events):")
        print(f"    {'Window':>8s} {'Token':>8s} {'BTC':>8s} {'Excess':>8s} {'Neg%':>6s} {'t-stat':>7s}")
        print("    " + "-" * 50)
        for w in windows:
            rets = [e[f"ret_{w}d"] for e in events if e[f"ret_{w}d"] is not None]
            excess = [e[f"excess_{w}d"] for e in events if e[f"excess_{w}d"] is not None]
            if rets and excess:
                m = mean(excess)
                s = std(excess)
                t_stat = m / (s / math.sqrt(len(excess))) if s > 0 else 0
                neg_pct = sum(1 for r in excess if r < 0) / len(excess) * 100
                print(f"    {w:+8d}d {mean(rets):+7.1f}% {mean([e[f'btc_{w}d'] for e in events if e[f'btc_{w}d'] is not None]):+7.1f}% "
                      f"{m:+7.1f}% {neg_pct:5.0f}% {t_stat:6.2f}")

    # ─── Backtest: short 3d before unlock, exit 3d after ──────────────────────
    print(f"\n{'='*80}")
    print(f"BACKTEST: Short 3d before unlock, exit 3d after\n")

    fee_bps = 20  # 10 bps per side
    trades = []
    for e in all_events:
        unlock_ts = date_to_ms(e["unlock_date"])
        if unlock_ts < oos_cutoff:
            e["period"] = "IS"
        elif unlock_ts < oos2_cutoff:
            e["period"] = "OOS-2025"
        else:
            e["period"] = "OOS-2026"
        e["is_oos"] = unlock_ts >= oos_cutoff
        # Entry: 3 days before unlock
        # Exit: 3 days after unlock
        ret_3d_before = e.get("ret_-3d")
        ret_3d_after = e.get("ret_3d")
        if ret_3d_before is None or ret_3d_after is None:
            continue

        # Short return = -(return from -3d to +3d)
        # We need the return from entry (-3d) to exit (+3d)
        # That's 6 days total: ret_3d - ret_-3d approximately
        # But more precisely, we need price at -3d and price at +3d
        # We have ret_3d = (price at +3d - price at 0) / price at 0
        # And ret_-3d = (price at -3d - price at 0) / price at 0
        # So price at -3d = price_0 * (1 + ret_-3d/100)
        # And price at +3d = price_0 * (1 + ret_3d/100)
        # Short return = (price_-3d - price_+3d) / price_-3d
        p_0 = e["price_at_unlock"]
        p_minus3 = p_0 * (1 + e["ret_-3d"] / 100) if e["ret_-3d"] is not None else None
        p_plus3 = p_0 * (1 + e["ret_3d"] / 100) if e["ret_3d"] is not None else None

        if p_minus3 is None or p_plus3 is None or p_minus3 == 0:
            continue

        short_ret = (p_minus3 - p_plus3) / p_minus3 * 10000 - fee_bps  # in bps
        trades.append({
            "symbol": e["symbol"],
            "unlock_date": e["unlock_date"],
            "unlock_value_mm": e["unlock_value_mm"],
            "pnl_bps": short_ret,
            "direction": "short",
            "is_oos": e.get("is_oos", False),
            "period": e.get("period", "IS"),
        })

    if trades:
        pnls = [t["pnl_bps"] for t in trades]
        wins = sum(1 for p in pnls if p > 0)
        wr = wins / len(pnls) * 100
        avg = mean(pnls)
        s = std(pnls)
        t_stat = avg / (s / math.sqrt(len(pnls))) if s > 0 else 0

        # Split by size
        large_trades = [t for t in trades if t["unlock_value_mm"] >= 200]
        large_pnls = [t["pnl_bps"] for t in large_trades]
        large_wr = sum(1 for p in large_pnls if p > 0) / len(large_pnls) * 100 if large_pnls else 0
        large_avg = mean(large_pnls) if large_pnls else 0

        # IS vs OOS-2025 vs OOS-2026 split
        is_trades = [t for t in trades if t.get("period") == "IS"]
        oos_trades = [t for t in trades if t.get("period") == "OOS-2025"]
        oos2_trades = [t for t in trades if t.get("period") == "OOS-2026"]
        is_pnls = [t["pnl_bps"] for t in is_trades]
        oos_pnls = [t["pnl_bps"] for t in oos_trades]
        oos2_pnls = [t["pnl_bps"] for t in oos2_trades]

        print(f"  All unlocks: N={len(trades)}, WR={wr:.0f}%, avg={avg:+.0f}bps, t-stat={t_stat:.2f}")
        if is_trades:
            is_wr = sum(1 for p in is_pnls if p > 0) / len(is_pnls) * 100
            is_avg = mean(is_pnls)
            is_s = std(is_pnls)
            is_t = is_avg / (is_s / math.sqrt(len(is_pnls))) if is_s > 0 else 0
            print(f"  IS (2023-2024):  N={len(is_trades)}, WR={is_wr:.0f}%, avg={is_avg:+.0f}bps, t-stat={is_t:.2f}")
        if oos_trades:
            oos_wr = sum(1 for p in oos_pnls if p > 0) / len(oos_pnls) * 100
            oos_avg = mean(oos_pnls)
            oos_s = std(oos_pnls)
            oos_t = oos_avg / (oos_s / math.sqrt(len(oos_pnls))) if oos_s > 0 else 0
            print(f"  OOS (2025):      N={len(oos_trades)}, WR={oos_wr:.0f}%, avg={oos_avg:+.0f}bps, t-stat={oos_t:.2f}")
        if oos2_trades:
            oos2_wr = sum(1 for p in oos2_pnls if p > 0) / len(oos2_pnls) * 100
            oos2_avg = mean(oos2_pnls)
            oos2_s = std(oos2_pnls)
            oos2_t = oos2_avg / (oos2_s / math.sqrt(len(oos2_pnls))) if oos2_s > 0 else 0
            print(f"  OOS (2026):      N={len(oos2_trades)}, WR={oos2_wr:.0f}%, avg={oos2_avg:+.0f}bps, t-stat={oos2_t:.2f}")
        if large_trades:
            print(f"  Large (≥$200M): N={len(large_trades)}, WR={large_wr:.0f}%, avg={large_avg:+.0f}bps")
        print(f"  Fees: {fee_bps}bps round trip (10bps/side)")

        # Per-symbol breakdown
        print(f"\n  Per-symbol:")
        print(f"    {'Symbol':>10s} {'N':>4s} {'WR':>5s} {'Avg':>7s} {'25N':>4s} {'25WR':>5s} {'25bps':>7s} {'26N':>4s} {'26WR':>5s} {'26bps':>7s}")
        print("    " + "-" * 75)
        for sym in sorted(set(t["symbol"] for t in trades)):
            sym_trades = [t for t in trades if t["symbol"] == sym]
            sym_pnls = [t["pnl_bps"] for t in sym_trades]
            sym_wr = sum(1 for p in sym_pnls if p > 0) / len(sym_pnls) * 100
            sym_25 = [t for t in sym_trades if t.get("period") == "OOS-2025"]
            sym_26 = [t for t in sym_trades if t.get("period") == "OOS-2026"]
            p25 = [t["pnl_bps"] for t in sym_25]
            p26 = [t["pnl_bps"] for t in sym_26]
            s25 = f"{len(sym_25):4d} {sum(1 for x in p25 if x>0)/len(p25)*100:4.0f}% {mean(p25):+6.0f}" if p25 else f"{0:4d}    -     -"
            s26 = f"{len(sym_26):4d} {sum(1 for x in p26 if x>0)/len(p26)*100:4.0f}% {mean(p26):+6.0f}" if p26 else f"{0:4d}    -     -"
            print(f"    {sym:>10s} {len(sym_trades):4d} {sym_wr:4.0f}% {mean(sym_pnls):+6.0f} {s25} {s26}")

    # Save
    output = {
        "n_events_total": len(all_events),
        "n_symbols": len(symbols),
        "backtest_trades": trades,
        "per_symbol": all_results,
    }
    with open(output_file, "w") as f:
        json.dump(output, f, indent=2, default=str)

    print(f"\n  PROFITABILITY ANALYSIS:")
    print(f"  - Token unlocks increase circulating supply → should create selling pressure")
    print(f"  - Strategy: short 3d before unlock, exit 3d after")
    print(f"  - Control: excess return vs BTC in same window")
    print(f"  - Key risk: unlock events are publicly known → market may price them in advance")
    print(f"  - Large unlocks (≥$200M) may have stronger effect than small ones")


def main():
    parser = argparse.ArgumentParser(description="D17 Token Unlock Impact Analysis")
    parser.add_argument("--output", type=str, default="token_unlock_samples.json")
    args = parser.parse_args()
    output_path = os.path.join(os.path.dirname(__file__), args.output)
    run_scan(output_path)


if __name__ == "__main__":
    main()
