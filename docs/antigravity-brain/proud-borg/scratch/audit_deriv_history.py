import asyncio
import websockets
import json
import time
from datetime import datetime, timezone

# 2026-06-28 12:34:00 GMT-3 = 2026-06-28 15:34:00 UTC
start_epoch = int(datetime(2026, 6, 28, 15, 34, 0, tzinfo=timezone.utc).timestamp())
end_epoch = int(datetime(2026, 6, 28, 18, 5, 0, tzinfo=timezone.utc).timestamp())

async def fetch_history():
    uri = "wss://api.derivws.com/trading/v1/options/ws/public"
    async with websockets.connect(uri) as ws:
        req = {
            "ticks_history": "cryBTCUSD",
            "end": "latest",
            "start": start_epoch,
            "style": "ticks",
            "count": 50000
        }
        await ws.send(json.dumps(req))
        res = await ws.recv()
        data = json.loads(res)
        
        if "error" in data:
            print("Error:", data["error"])
            return
            
        history = data.get("history", {})
        prices = history.get("prices", [])
        times = history.get("times", [])
        
        print(f"Coletados {len(prices)} ticks da Deriv.")
        
        jumps = 0
        for i in range(1, len(prices)):
            diff = prices[i] - prices[i-1]
            time_diff = times[i] - times[i-1]
            
            if abs(diff) >= 50.0:
                dt = datetime.fromtimestamp(times[i])
                print(f"SALTO ENCONTRADO na Deriv! {dt} - Diff: {diff:.2f} (Time diff: {time_diff}s)")
                jumps += 1
                
        print(f"Total de saltos >= 50 encontrados na Deriv puramente (Tick a Tick): {jumps}")

if __name__ == "__main__":
    asyncio.run(fetch_history())
