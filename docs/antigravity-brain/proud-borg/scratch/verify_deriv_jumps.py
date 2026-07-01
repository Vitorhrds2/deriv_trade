import asyncio
import websockets
import json
import time

BINANCE_SYMBOL = "btcusdt"
DERIV_SYMBOL = "cryBTCUSD"
DERIV_APP_ID = "1089" # Generic app id

binance_history = []
deriv_history = []

async def deriv_ws():
    uri = f"wss://api.derivws.com/trading/v1/options/ws/public"
    async with websockets.connect(uri) as ws:
        await ws.send(json.dumps({"ticks": DERIV_SYMBOL}))
        async for msg in ws:
            data = json.loads(msg)
            if 'tick' in data:
                tick = data['tick']
                deriv_history.append({
                    "time": time.time(),
                    "quote": float(tick['quote']),
                    "epoch": tick['epoch']
                })
                # Keep last 10 seconds
                while deriv_history and deriv_history[-1]["time"] - deriv_history[0]["time"] > 10:
                    deriv_history.pop(0)

async def binance_ws():
    uri = f"wss://stream.binance.com:9443/ws/{BINANCE_SYMBOL}@bookTicker"
    async with websockets.connect(uri) as ws:
        print("Aguardando um price shock na Binance para auditar o comportamento da Deriv...")
        async for msg in ws:
            data = json.loads(msg)
            price = float(data['a'])
            now = time.time()
            binance_history.append({"time": now, "price": price})
            
            # Keep last 1 second
            while binance_history and now - binance_history[0]["time"] > 1.0:
                binance_history.pop(0)
                
            if len(binance_history) >= 2:
                oldest = binance_history[0]
                diff = price - oldest["price"]
                
                # Se pular mais de 30 dólares num segundo
                if abs(diff) >= 30.0:
                    print(f"\n🚨 PULO DETECTADO NA BINANCE: {diff:.2f}")
                    print(f"Preço Base (Binance): {oldest['price']:.2f} -> Pico: {price:.2f}")
                    
                    # Espera 3 segundos para a Deriv processar
                    print("Aguardando 3 segundos para coletar os ticks futuros da Deriv...")
                    await asyncio.sleep(3.0)
                    
                    print("\n--- TICKS DA DERIV NO MESMO PERÍODO ---")
                    for d in deriv_history:
                        # Marcar o momento do pulo (t=0)
                        rel_time = d["time"] - now
                        print(f"T {rel_time:+.3f}s | Tick: {d['quote']:.2f}")
                        
                    print("\nAuditoria concluída. Analise os valores acima para ver se a Deriv realmente replicou o salto da Binance.")
                    import sys
                    sys.exit(0)

async def main():
    await asyncio.gather(
        deriv_ws(),
        binance_ws()
    )

if __name__ == "__main__":
    asyncio.run(main())
