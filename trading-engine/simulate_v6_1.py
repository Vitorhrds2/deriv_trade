import asyncio
import os
import json
import time
from datetime import datetime, timezone
import websockets
from dotenv import load_dotenv

load_dotenv()
APP_ID = os.getenv("DERIV_APP_ID")
if not APP_ID:
    APP_ID = "1089" # Fallback app id

async def fetch_history():
    uri = "wss://ws.binaryws.com/websockets/v3?app_id=1089"
    all_prices = []
    all_times = []
    async with websockets.connect(uri) as ws:
        end = int(time.time())
        start = end - (48 * 3600) # Past 48 hours
        
        current_end = end
        while current_end > start:
            req = {
                "ticks_history": "cryBTCUSD",
                "adjust_start_time": 1,
                "count": 5000,
                "end": current_end,
                "start": start,
                "style": "ticks"
            }
            await ws.send(json.dumps(req))
            res = json.loads(await ws.recv())
            hist = res.get("history", {})
            prices = hist.get("prices", [])
            times = hist.get("times", [])
            
            if not prices:
                break
                
            # Prepend because we are iterating backwards
            all_prices = prices + all_prices
            all_times = times + all_times
            
            current_end = times[0] - 1
            time.sleep(0.1) # Avoid rate limit
            
        return {"prices": all_prices, "times": all_times}

def simulate():
    history = asyncio.run(fetch_history())
    prices = history.get("prices", [])
    times = history.get("times", [])
    
    if not prices:
        print("No prices fetched!")
        print(history)
        return
        
    print(f"Fetched {len(prices)} prices.")
        
    STAKE = 10.0
    MULTIPLIER = 800
    THRESHOLD = 55.0
    TP = STAKE * 0.60
    SL = -(STAKE * 0.35)
    TIMEOUT = 120
    SPREAD_PENALTY = 0.50 # Estimate $0.50 spread loss on entry
    
    trades = []
    
    for i in range(1, len(prices) - TIMEOUT):
        diff = prices[i] - prices[i-1]
        
        if abs(diff) >= THRESHOLD:
            direction = "UP" if diff > 0 else "DOWN"
            entry_price = prices[i]
            entry_time = times[i]
            
            # Simulate the trade over the next TIMEOUT ticks
            trade_profit = 0.0
            closed = False
            close_time = None
            
            for j in range(1, TIMEOUT + 1):
                current_price = prices[i+j]
                
                if direction == "UP":
                    raw_profit = ((current_price - entry_price) / entry_price) * STAKE * MULTIPLIER
                else:
                    raw_profit = ((entry_price - current_price) / entry_price) * STAKE * MULTIPLIER
                    
                profit = raw_profit - SPREAD_PENALTY
                
                if profit >= TP:
                    trade_profit = TP
                    closed = True
                    close_time = times[i+j]
                    break
                elif profit <= SL:
                    trade_profit = SL
                    closed = True
                    close_time = times[i+j]
                    break
                    
            if not closed:
                trade_profit = profit
                close_time = times[i+TIMEOUT]
                
            trades.append({
                "entry_time": entry_time,
                "direction": direction,
                "diff": diff,
                "profit": trade_profit,
                "duration": close_time - entry_time
            })
            
    # Aggregate by Hour (UTC)
    hourly_pnl = {}
    
    for t in trades:
        dt = datetime.fromtimestamp(t["entry_time"], tz=timezone.utc)
        hour_key = dt.strftime("%Y-%m-%d %H:00")
        if hour_key not in hourly_pnl:
            hourly_pnl[hour_key] = {"pnl": 0.0, "wins": 0, "losses": 0, "count": 0}
            
        hourly_pnl[hour_key]["pnl"] += t["profit"]
        hourly_pnl[hour_key]["count"] += 1
        if t["profit"] > 0:
            hourly_pnl[hour_key]["wins"] += 1
        else:
            hourly_pnl[hour_key]["losses"] += 1
            
    print("--- TRADES SIMULADAS ---")
    for t in trades[-10:]: # Print last 10 for sanity check
        dt = datetime.fromtimestamp(t["entry_time"], tz=timezone.utc)
        print(f"{dt.strftime('%Y-%m-%d %H:%M:%S')} | {t['direction']} | Jump: {t['diff']:.2f} | PnL: ${t['profit']:.2f} | Dur: {t['duration']}s")
        
    print("\n--- LUCRATIVIDADE POR HORA (UTC) ---")
    total_pnl = 0
    for h in sorted(hourly_pnl.keys()):
        data = hourly_pnl[h]
        total_pnl += data["pnl"]
        print(f"{h} | Trades: {data['count']:02d} | W: {data['wins']} L: {data['losses']} | PnL: ${data['pnl']:>6.2f}")
        
    print(f"\nTotal PnL 48h: ${total_pnl:.2f}")

if __name__ == "__main__":
    simulate()
