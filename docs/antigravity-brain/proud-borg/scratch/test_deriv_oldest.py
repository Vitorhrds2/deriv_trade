import asyncio
import websockets
import json
from datetime import datetime, timezone, timedelta
import time

async def find_oldest_tick():
    uri = "wss://api.derivws.com/trading/v1/options/ws/public"
    
    async with websockets.connect(uri) as ws:
        # Tentar pegar 1 tick exatamente 1 dia atrás
        async def check_date(dt):
            req = {
                "ticks_history": "cryBTCUSD",
                "end": int(dt.timestamp()),
                "style": "ticks",
                "count": 1
            }
            await ws.send(json.dumps(req))
            res = json.loads(await ws.recv())
            if "error" in res:
                return False, res["error"]["message"]
            history = res.get("history", {})
            times = history.get("times", [])
            return len(times) > 0, times[0] if times else None

        now = datetime.now(timezone.utc)
        
        # Binary search or just test offsets
        # Let's test 1 day, 7 days, 30 days, 90 days, 180 days, 1 year
        offsets = [1, 7, 30, 90, 180, 365, 730]
        
        print("Testing how far back we can fetch cryBTCUSD ticks...")
        for days in offsets:
            dt = now - timedelta(days=days)
            success, result = await check_date(dt)
            if success:
                tick_time = datetime.fromtimestamp(result, tz=timezone.utc)
                print(f"Data {days} days ago ({dt.date()}): OK -> Returned tick at {tick_time}")
            else:
                print(f"Data {days} days ago ({dt.date()}): FAILED -> {result}")
                
if __name__ == "__main__":
    asyncio.run(find_oldest_tick())
