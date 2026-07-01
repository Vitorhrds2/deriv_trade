import asyncio
import json
import websockets
import time
from datetime import datetime

async def main():
    # 28/06/2026 19:20:57 GMT-3 is 22:20:57 GMT
    # timestamp = 1782685257 (approx)
    
    # Actually, we can just use time.strptime or datetime to be precise:
    dt = datetime.strptime("2026-06-28 22:20:57", "%Y-%m-%d %H:%M:%S")
    target_time_gmt = int(dt.timestamp())
    start_time = target_time_gmt - 10
    end_time = target_time_gmt + 10

    uri = "wss://api.derivws.com/trading/v1/options/ws/public"
    async with websockets.connect(uri) as ws:
        req = {
            "ticks_history": "cryBTCUSD",
            "end": str(end_time),
            "start": str(start_time),
            "style": "ticks",
            "count": 100
        }
        await ws.send(json.dumps(req))
        res = json.loads(await ws.recv())
        
        if "history" in res:
            prices = res["history"]["prices"]
            times = res["history"]["times"]
            
            print(f"Ticks for cryBTCUSD between {datetime.fromtimestamp(start_time)} and {datetime.fromtimestamp(end_time)}:")
            for t, p in zip(times, prices):
                dt = datetime.fromtimestamp(t)
                print(f"[{dt.strftime('%H:%M:%S')}] {t} -> {p}")
        else:
            print("Error or no history:", res)

asyncio.run(main())
