import os
import sys
from dotenv import load_dotenv

load_dotenv(dotenv_path="trading-engine/.env")
sys.path.insert(0, "trading-engine")

import unlock_short_bot

api_key = os.getenv("BINANCE_API_KEY_DEMO")
api_secret = os.getenv("BINANCE_API_SECRET_DEMO")

print(f"Testing Binance Demo connection...")
print(f"API Key: {api_key[:8]}...{api_key[-4:] if api_key else 'None'}")

# 1. Test public price endpoint (does not require auth)
try:
    sui_price = unlock_short_bot.get_current_price("SUIUSDT")
    print(f"Public mark price SUIUSDT: ${sui_price}")
except Exception as e:
    print(f"Public price failed: {e}")

# 2. Test testnet futures endpoint
unlock_short_bot.BINANCE_FAPI = unlock_short_bot.BINANCE_FAPI_TESTNET
print(f"\nTesting Binance Futures Testnet ({unlock_short_bot.BINANCE_FAPI})...")
try:
    bal = unlock_short_bot.get_account_balance(api_key, api_secret)
    print(f"Futures Testnet Balance: ${bal:.2f}")
except Exception as e:
    print(f"Futures Testnet failed: {e}")

# 3. Test Spot Demo
print(f"\nTesting Binance Spot Demo endpoint...")
try:
    import urllib.request
    import json
    req = urllib.request.Request("https://demo-api.binance.com/api/v3/ping")
    with urllib.request.urlopen(req, timeout=5) as r:
        print(f"Spot demo ping: {r.status}")
except Exception as e:
    print(f"Spot demo ping failed: {e}")
