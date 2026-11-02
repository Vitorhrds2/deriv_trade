import os
import sys
from dotenv import load_dotenv

load_dotenv(dotenv_path="trading-engine/.env")
sys.path.insert(0, "trading-engine")

import unlock_short_bot

api_key = os.getenv("BINANCE_API_KEY_DEMO")
api_secret = os.getenv("BINANCE_API_SECRET_DEMO")

unlock_short_bot.BINANCE_FAPI = "https://testnet.binancefuture.com/fapi/v1"
print(f"Testing Binance Futures Testnet at https://testnet.binancefuture.com/fapi/v1...")
try:
    bal = unlock_short_bot.get_account_balance(api_key, api_secret)
    print(f"Futures Testnet Balance: ${bal:.2f}")
except Exception as e:
    print(f"Futures Testnet error: {e}")
