import asyncio
import os
import sys
from dotenv import load_dotenv

load_dotenv(dotenv_path="trading-engine/.env")
sys.path.insert(0, "trading-engine")

from deriv_client import DerivClient

APP_ID = os.getenv("DERIV_APP_ID", "33iJWIKcLfzGYo9IE1Y6f")
TOKEN = os.getenv("DERIV_API_TOKEN", "")

async def test_turbos_stake():
    client = DerivClient(app_id=APP_ID, api_token=TOKEN, use_demo=True)
    await client.connect()
    
    prop_payload = {
        "proposal": 1,
        "amount": 200.0,
        "basis": "stake",
        "contract_type": "TURBOSLONG",
        "currency": "USD",
        "underlying_symbol": "1HZ10V",
        "duration": 5,
        "duration_unit": "m",
        "barrier": "178.93"
    }
    prop_res = await client.send_request(prop_payload)
    print("Turbo proposal 200:", prop_res)
    await client.disconnect()

if __name__ == "__main__":
    asyncio.run(test_turbos_stake())
