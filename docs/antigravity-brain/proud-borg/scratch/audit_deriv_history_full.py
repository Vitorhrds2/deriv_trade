import asyncio
import websockets
import json
from datetime import datetime, timezone

start_epoch = int(datetime(2026, 6, 28, 15, 34, 0, tzinfo=timezone.utc).timestamp())
end_epoch = int(datetime(2026, 6, 28, 18, 5, 0, tzinfo=timezone.utc).timestamp())

async def fetch_all_history():
    uri = "wss://api.derivws.com/trading/v1/options/ws/public"
    
    current_end = end_epoch
    all_prices = []
    all_times = []
    
    async with websockets.connect(uri) as ws:
        while current_end > start_epoch:
            req = {
                "ticks_history": "cryBTCUSD",
                "end": current_end,
                "start": start_epoch,
                "style": "ticks",
                "count": 5000
            }
            await ws.send(json.dumps(req))
            res = await ws.recv()
            data = json.loads(res)
            
            if "error" in data:
                print("Error:", data["error"])
                break
                
            history = data.get("history", {})
            prices = history.get("prices", [])
            times = history.get("times", [])
            
            if not prices:
                break
                
            all_prices = prices + all_prices
            all_times = times + all_times
            
            current_end = times[0] - 1
            
            # API returns max 1000 ticks per request
            if len(prices) < 1000:
                break

    print(f"Total de {len(all_prices)} ticks coletados da Deriv desde as 12:34 (GMT-3)")
    
    jumps = 0
    for i in range(1, len(all_prices)):
        diff = all_prices[i] - all_prices[i-1]
        
        if abs(diff) >= 50.0:
            dt_gmt3 = datetime.fromtimestamp(all_times[i])
            print(f"SALTO DERIV: {dt_gmt3.strftime('%H:%M:%S')} | Diff: {diff:.2f}")
            jumps += 1
            
    print(f"Total de saltos (Deriv puramente) >= $50: {jumps}")

if __name__ == "__main__":
    asyncio.run(fetch_all_history())
