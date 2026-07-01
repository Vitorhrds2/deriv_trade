import asyncio
import websockets
import json
from datetime import datetime, timezone, timedelta

async def analyze_reversion():
    uri = "wss://api.derivws.com/trading/v1/options/ws/public"
    
    now = datetime.now(timezone.utc)
    start_epoch = int((now - timedelta(hours=23, minutes=58)).timestamp())
    current_end = int(now.timestamp())
    
    all_prices = []
    all_times = []
    
    async with websockets.connect(uri) as ws:
        print("Coletando histórico das últimas 24h...")
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
            
            if len(prices) < 1000:
                break
                
    print(f"Coletados {len(all_prices)} ticks. Analisando Mean Reversion...")
    
    jumps = 0
    reversion_profits = []
    
    for i in range(1, len(all_prices) - 5):
        jump = all_prices[i] - all_prices[i-1]
        
        if abs(jump) >= 50.0:
            jumps += 1
            # If jump is negative (drop), we buy UP. If jump is positive (spike), we buy DOWN.
            entry_price = all_prices[i]
            direction = "UP" if jump < 0 else "DOWN"
            
            # Check price 2 seconds later
            exit_price = all_prices[i+2]
            
            if direction == "UP":
                price_diff = exit_price - entry_price
            else:
                price_diff = entry_price - exit_price
                
            # Simulate Multiplier profit
            profit = (price_diff / entry_price) * 800 * 10
            
            print(f"Shock: {jump:.2f} | Entry: {entry_price:.2f} | Exit (2s): {exit_price:.2f} | Reversion Diff: {price_diff:.2f} | Profit: ${profit:.2f}")
            reversion_profits.append(profit)
            
    if jumps > 0:
        win_rate = len([p for p in reversion_profits if p > 0]) / jumps * 100
        print("-" * 40)
        print(f"Total Shocks >= 50: {jumps}")
        print(f"Total Profit (2s hold): ${sum(reversion_profits):.2f}")
        print(f"Win Rate: {win_rate:.1f}%")

if __name__ == "__main__":
    asyncio.run(analyze_reversion())
