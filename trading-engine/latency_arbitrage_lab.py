import asyncio
import logging
import json
import time
import os
import websockets
from dotenv import load_dotenv
from deriv_client import DerivClient

logging.basicConfig(level=logging.INFO, format='%(asctime)s - LATENCY_LAB:%(levelname)s:%(message)s')
logger = logging.getLogger("LATENCY_LAB")

load_dotenv()
DERIV_API_TOKEN = os.getenv("DERIV_API_TOKEN")
DERIV_APP_ID = os.getenv("DERIV_APP_ID")
DERIV_SYMBOL = "cryBTCUSD"
BINANCE_SYMBOL = "btcusdt"

# Variáveis Globais de Estado
state = {
    "binance_price": None,
    "binance_ticks": [],
    "deriv_ticks": []
}

async def binance_ws():
    uri = f"wss://stream.binance.com:9443/ws/{BINANCE_SYMBOL}@bookTicker"
    logger.info(f"Conectando à Binance: {uri}")
    try:
        async with websockets.connect(uri) as websocket:
            logger.info("Binance Conectado!")
            async for message in websocket:
                data = json.loads(message)
                ask_price = float(data['a'])
                local_time = time.time()
                
                if state["binance_price"] != ask_price:
                    state["binance_price"] = ask_price
                    state["binance_ticks"].append({"t": local_time, "p": ask_price})
    except Exception as e:
        logger.error(f"Erro Binance: {e}")

async def deriv_tick_callback(data):
    if 'tick' in data:
        tick_price = float(data['tick']['ask'])
        local_time = time.time()
        state["deriv_ticks"].append({"t": local_time, "p": tick_price})
        logger.info(f"Deriv Tick: {tick_price:.2f} | Ticks coletados -> Binance: {len(state['binance_ticks'])}, Deriv: {len(state['deriv_ticks'])}")

async def deriv_ws():
    logger.info("Conectando à Deriv...")
    client = DerivClient(app_id=DERIV_APP_ID, api_token=DERIV_API_TOKEN, use_demo=True)
    await client.connect()
    
    await client.subscribe_ticks(DERIV_SYMBOL, deriv_tick_callback)
    logger.info(f"Deriv Conectado! Inscrito em {DERIV_SYMBOL}")
    
    while True:
        await asyncio.sleep(1)

async def main():
    logger.info("🧪 INICIANDO LABORATÓRIO DE ARBITRAGEM DE LATÊNCIA")
    
    task1 = asyncio.create_task(binance_ws())
    task2 = asyncio.create_task(deriv_ws())
    
    await asyncio.sleep(60)
    
    task1.cancel()
    task2.cancel()
    
    # Save to file
    with open("latency_data.json", "w") as f:
        json.dump({
            "binance": state["binance_ticks"],
            "deriv": state["deriv_ticks"]
        }, f)
        
    logger.info("Laboratório finalizado. Dados salvos em latency_data.json")

if __name__ == "__main__":
    asyncio.run(main())
