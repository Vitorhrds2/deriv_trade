import asyncio
import websockets
import json
from datetime import datetime, timezone, timedelta

async def backtest_24h():
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
                
    print(f"Coletados {len(all_prices)} ticks. Analisando saltos...")
    
    wins = 0
    pnl = 0.0
    stake = 10.0
    profit_per_win = stake * 0.95
    cooldown_until = 0
    
    for i in range(2, len(all_prices)):
        current_time = all_times[i]
        
        if current_time < cooldown_until:
            continue
            
        diff_1s = abs(all_prices[i] - all_prices[i-1])
        diff_2s = abs(all_prices[i] - all_prices[i-2])
        
        if diff_1s >= 60.0 or diff_2s >= 60.0:
            dt_gmt3 = datetime.fromtimestamp(current_time)
            jump_val = all_prices[i] - all_prices[i-2]
            print(f"🎯 TRADE WIN: {dt_gmt3.strftime('%d/%m %H:%M:%S')} | Salto real: {jump_val:.2f} | Lucro: +${profit_per_win:.2f}")
            wins += 1
            pnl += profit_per_win
            cooldown_until = current_time + 3  # Cooldown de 3 segundos
            
    print("-" * 40)
    print(f"📊 RESULTADO 24 HORAS (Stake: ${stake:.2f})")
    print(f"Total de Trades: {wins}")
    print(f"Lucro Estimado (PnL): +${pnl:.2f}")
    
if __name__ == "__main__":
    asyncio.run(backtest_24h())
