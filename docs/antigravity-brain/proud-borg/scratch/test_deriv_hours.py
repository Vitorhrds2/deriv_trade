import asyncio
import websockets
import json
from datetime import datetime, timezone, timedelta

async def find_oldest_tick():
    uri = "wss://api.derivws.com/trading/v1/options/ws/public"
    
    async with websockets.connect(uri) as ws:
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
        
        for hours in range(1, 25):
            dt = now - timedelta(hours=hours)
            success, result = await check_date(dt)
            if success:
                tick_time = datetime.fromtimestamp(result, tz=timezone.utc)
                if tick_time < now - timedelta(minutes=1):
                    print(f"Data {hours} hours ago: OK -> Returned tick at {tick_time}")
                else:
                    print(f"Data {hours} hours ago: FAILED -> API returned {tick_time}")
            else:
                print(f"Data {hours} hours ago: FAILED -> {result}")

if __name__ == "__main__":
    asyncio.run(find_oldest_tick())
