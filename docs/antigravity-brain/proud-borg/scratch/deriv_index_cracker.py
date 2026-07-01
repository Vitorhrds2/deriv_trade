import asyncio
import websockets
import json
import time
import csv

# Símbolos
BINANCE_SYMBOL = "btcusdt"
COINBASE_PRODUCT = "BTC-USD"
KRAKEN_PAIR = "XBT/USD"
DERIV_SYMBOL = "cryBTCUSD"

DURATION_SECONDS = 300 # 5 minutos

# Históricos (time, price)
history = {
    "binance": [],
    "coinbase": [],
    "kraken": [],
    "deriv": []
}

async def binance_ws():
    uri = f"wss://stream.binance.com:9443/ws/{BINANCE_SYMBOL}@bookTicker"
    while True:
        try:
            async with websockets.connect(uri) as ws:
                print("Conectado na Binance")
                async for msg in ws:
                    data = json.loads(msg)
                    price = float(data['a']) # ask price
                    history["binance"].append((time.time(), price))
        except Exception as e:
            print(f"Erro Binance: {e}")
            await asyncio.sleep(2)

async def coinbase_ws():
    uri = "wss://ws-feed.exchange.coinbase.com"
    while True:
        try:
            async with websockets.connect(uri) as ws:
                await ws.send(json.dumps({
                    "type": "subscribe",
                    "product_ids": [COINBASE_PRODUCT],
                    "channels": ["ticker"]
                }))
                print("Conectado na Coinbase")
                async for msg in ws:
                    data = json.loads(msg)
                    if data.get("type") == "ticker" and "best_ask" in data:
                        price = float(data["best_ask"])
                        history["coinbase"].append((time.time(), price))
        except Exception as e:
            print(f"Erro Coinbase: {e}")
            await asyncio.sleep(2)

async def kraken_ws():
    uri = "wss://ws.kraken.com"
    while True:
        try:
            async with websockets.connect(uri) as ws:
                await ws.send(json.dumps({
                    "event": "subscribe",
                    "pair": [KRAKEN_PAIR],
                    "subscription": {"name": "ticker"}
                }))
                print("Conectado na Kraken")
                async for msg in ws:
                    data = json.loads(msg)
                    if isinstance(data, list) and len(data) > 1:
                        ticker_data = data[1]
                        if "a" in ticker_data: # ask array
                            price = float(ticker_data["a"][0])
                            history["kraken"].append((time.time(), price))
        except Exception as e:
            print(f"Erro Kraken: {e}")
            await asyncio.sleep(2)

async def deriv_ws():
    uri = "wss://api.derivws.com/trading/v1/options/ws/public"
    while True:
        try:
            async with websockets.connect(uri) as ws:
                await ws.send(json.dumps({"ticks": DERIV_SYMBOL}))
                print("Conectado na Deriv")
                async for msg in ws:
                    data = json.loads(msg)
                    if "tick" in data:
                        price = float(data["tick"]["quote"])
                        history["deriv"].append((time.time(), price))
        except Exception as e:
            print(f"Erro Deriv: {e}")
            await asyncio.sleep(2)

async def timer():
    print(f"Iniciando gravação de {DURATION_SECONDS} segundos...")
    await asyncio.sleep(DURATION_SECONDS)
    print("Tempo esgotado. Consolidando CSV...")
    
    # Criar amostras a cada 50ms
    if not history["deriv"]:
        print("Nenhum dado da Deriv coletado!")
        import sys
        sys.exit(0)
        
    start_time = history["deriv"][0][0]
    end_time = start_time + DURATION_SECONDS
    
    with open("multi_exchange_ticks.csv", "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["timestamp", "binance", "coinbase", "kraken", "deriv"])
        
        current_t = start_time
        
        idx_binance = 0
        idx_coinbase = 0
        idx_kraken = 0
        idx_deriv = 0
        
        last_binance = None
        last_coinbase = None
        last_kraken = None
        last_deriv = None
        
        while current_t <= end_time:
            while idx_binance < len(history["binance"]) and history["binance"][idx_binance][0] <= current_t:
                last_binance = history["binance"][idx_binance][1]
                idx_binance += 1
                
            while idx_coinbase < len(history["coinbase"]) and history["coinbase"][idx_coinbase][0] <= current_t:
                last_coinbase = history["coinbase"][idx_coinbase][1]
                idx_coinbase += 1
                
            while idx_kraken < len(history["kraken"]) and history["kraken"][idx_kraken][0] <= current_t:
                last_kraken = history["kraken"][idx_kraken][1]
                idx_kraken += 1
                
            while idx_deriv < len(history["deriv"]) and history["deriv"][idx_deriv][0] <= current_t:
                last_deriv = history["deriv"][idx_deriv][1]
                idx_deriv += 1
                
            if all([last_binance, last_coinbase, last_kraken, last_deriv]):
                writer.writerow([f"{current_t:.3f}", last_binance, last_coinbase, last_kraken, last_deriv])
                
            current_t += 0.050 # amostras a cada 50ms

    print("✅ CSV salvo com sucesso!")
    import sys
    sys.exit(0)

async def main():
    await asyncio.gather(
        binance_ws(),
        coinbase_ws(),
        kraken_ws(),
        deriv_ws(),
        timer()
    )

if __name__ == "__main__":
    asyncio.run(main())
