import asyncio
import json
import websockets
import numpy as np

async def main():
    uri = "wss://ws.derivws.com/websockets/v3?app_id=1089"
    async with websockets.connect(uri) as ws:
        # Fetch 500 1-minute candles of 1HZ75V
        await ws.send(json.dumps({
            "ticks_history": "1HZ75V",
            "count": 500,
            "end": "latest",
            "style": "candles",
            "granularity": 60
        }))
        res = json.loads(await ws.recv())
        candles = res.get("candles", [])
        if not candles:
            print("No candles returned")
            return
        
        closes = [float(c["close"]) for c in candles]
        highs = [float(c["high"]) for c in candles]
        lows = [float(c["low"]) for c in candles]
        
        first_close = closes[0]
        last_close = closes[-1]
        overall_change = (last_close - first_close) / first_close * 100
        
        print(f"500 minutes (~8.3 hours) of 1HZ75V:")
        print(f"  First close: {first_close:.2f} | Last close: {last_close:.2f} | Change: {overall_change:+.2f}%")
        print(f"  Highest high: {max(highs):.2f} | Lowest low: {min(lows):.2f} | Range: {(max(highs)-min(lows))/first_close*100:.2f}%")
        
        # Check autocorrelation and Hurst of 1HZ75V vs R_100
        diffs = np.diff(closes)
        ac1 = np.corrcoef(diffs[:-1], diffs[1:])[0, 1]
        print(f"  1-minute return autocorrelation: {ac1:.4f}")

asyncio.run(main())
