import asyncio
import os
import sys
import time
from datetime import datetime, timezone
from dotenv import load_dotenv

load_dotenv(dotenv_path="trading-engine/.env")
sys.path.insert(0, "trading-engine")

from deriv_client import DerivClient

APP_ID = os.getenv("DERIV_APP_ID", "33iJWIKcLfzGYo9IE1Y6f")
TOKEN = os.getenv("DERIV_API_TOKEN", "")

async def test_lead_lag():
    client = DerivClient(app_id=APP_ID, api_token=TOKEN, use_demo=True)
    await client.connect()
    
    ticks_frx = []
    ticks_basket = []
    
    async def on_frx(data):
        t = data.get("tick")
        if t:
            arrival = time.time()
            ticks_frx.append((arrival, int(t.get("epoch", 0)), float(t.get("quote", 0))))
            print(f"  [FRX] {datetime.now().strftime('%H:%M:%S.%f')[:-3]} quote={t.get('quote')} epoch={t.get('epoch')}")

    async def on_basket(data):
        t = data.get("tick")
        if t:
            arrival = time.time()
            ticks_basket.append((arrival, int(t.get("epoch", 0)), float(t.get("quote", 0))))
            print(f"  [BASKET] {datetime.now().strftime('%H:%M:%S.%f')[:-3]} quote={t.get('quote')} epoch={t.get('epoch')}")

    print("Subscribing to frxEURUSD and WLDEUR...")
    sub1 = await client.subscribe_ticks("frxEURUSD", on_frx)
    sub2 = await client.subscribe_ticks("WLDEUR", on_basket)
    print("Subscription responses:", sub1, sub2)
    
    print("Recording ticks for 15 seconds...")
    await asyncio.sleep(15.0)
    
    print(f"\nCaptured: {len(ticks_frx)} frxEURUSD ticks, {len(ticks_basket)} WLDEUR ticks")
    await client.disconnect()

if __name__ == "__main__":
    asyncio.run(test_lead_lag())
