import os
import json
import asyncio
import time
from dotenv import load_dotenv
from deriv_client import DerivClient

load_dotenv()
API_TOKEN = os.getenv("DERIV_API_TOKEN")
APP_ID = os.getenv("DERIV_APP_ID")

async def monitor_ticks():
    client = DerivClient(app_id=APP_ID, api_token=API_TOKEN, use_demo=True)
    await client.connect()
    
    req = {
        "ticks": "cryBTCUSD"
    }
    await client.ws.send(json.dumps(req))
    
    print("Monitorando a frequência de ticks de cryBTCUSD na Deriv...")
    last_time = time.time()
    
    for _ in range(10):
        res = json.loads(await client.ws.recv())
        if 'tick' in res:
            tick = res['tick']
            now = time.time()
            elapsed = now - last_time
            print(f"Tick recebido! Preço: {tick['quote']} | Tempo desde último: {elapsed:.2f}s | Timestamp: {tick['epoch']}")
            last_time = now

if __name__ == "__main__":
    asyncio.run(monitor_ticks())
