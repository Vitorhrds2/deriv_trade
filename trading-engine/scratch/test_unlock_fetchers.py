import asyncio
import os
import sys
import json
import urllib.request
from dotenv import load_dotenv

load_dotenv(dotenv_path="trading-engine/.env")
sys.path.insert(0, "trading-engine")

import unlock_data

print("1. Testing Tokenomist via unlock_data.get_upcoming_unlocks()...")
unlocks = unlock_data.get_upcoming_unlocks(min_value_mm=5, days_ahead=60)
print(f"Tokenomist returned {len(unlocks) if unlocks else 0} unlock events:")
if unlocks:
    for u in unlocks[:10]:
        print(f"  {u['symbol']}: {u['unlock_date']} | Value: ${u['unlock_value_mm']}M | Supply: {u['pct_supply']}%")

print("\n2. Testing CryptoRank API probe...")
cryptorank_urls = [
    "https://api.cryptorank.io/v0/vestings/upcoming",
    "https://api.cryptorank.io/v1/vesting",
    "https://api.cryptorank.io/v1/currencies?limit=10",
]
headers = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json"
}

for url in cryptorank_urls:
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
            print(f"CryptoRank OK on {url}! Keys: {list(data.keys()) if isinstance(data, dict) else type(data)}")
    except Exception as e:
        print(f"CryptoRank error on {url}: {e}")
