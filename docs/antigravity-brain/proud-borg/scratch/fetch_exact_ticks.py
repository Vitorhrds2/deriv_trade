import asyncio
import json
import websockets
import time

async def main():
    start_time = 1782685250
    end_time = 1782685270

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
            
            print("Ticks around jump time:")
            for t, p in zip(times, prices):
                print(f"{t} -> {p}")
        else:
            print("Error or no history:", res)

asyncio.run(main())
