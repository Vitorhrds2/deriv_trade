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
        
        for days in range(1, 10):
            dt = now - timedelta(days=days)
            success, result = await check_date(dt)
            if success:
                tick_time = datetime.fromtimestamp(result, tz=timezone.utc)
                # Verify if the returned tick is actually from the requested day
                # Deriv sometimes falls back to current day if data is unavailable
                if abs((dt - tick_time).total_seconds()) < 86400:
                    print(f"Data {days} days ago ({dt.date()}): OK -> Returned tick at {tick_time}")
                else:
                    print(f"Data {days} days ago ({dt.date()}): FAILED -> API ignored the date and returned {tick_time}")
            else:
                print(f"Data {days} days ago ({dt.date()}): FAILED -> {result}")

if __name__ == "__main__":
    asyncio.run(find_oldest_tick())
