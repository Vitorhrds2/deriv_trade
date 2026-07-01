import asyncio
import websockets
import json
from datetime import datetime, timezone

start_epoch = int(datetime(2026, 6, 28, 15, 34, 0, tzinfo=timezone.utc).timestamp())
end_epoch = int(datetime(2026, 6, 28, 18, 5, 0, tzinfo=timezone.utc).timestamp())

async def fetch_all_history():
    uri = "wss://api.derivws.com/trading/v1/options/ws/public"
    async with websockets.connect(uri) as ws:
        req = {
            "ticks_history": "cryBTCUSD",
            "end": end_epoch,
            "start": start_epoch,
            "style": "ticks",
            "count": 5000
        }
        await ws.send(json.dumps(req))
        res = await ws.recv()
        data = json.loads(res)
        history = data.get("history", {})
        times = history.get("times", [])
        if times:
            t_first = datetime.fromtimestamp(times[0], tz=timezone.utc)
            t_last = datetime.fromtimestamp(times[-1], tz=timezone.utc)
            print(f"Retornados {len(times)} ticks.")
            print(f"Primeiro: {t_first}")
            print(f"Ultimo: {t_last}")

if __name__ == "__main__":
    asyncio.run(fetch_all_history())
