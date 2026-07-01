import asyncio
import logging
import json
import time
import os
import websockets
from dotenv import load_dotenv
from deriv_client import DerivClient
import sys

logging.basicConfig(level=logging.INFO, format='%(asctime)s - EXECUTION_LAB:%(levelname)s:%(message)s')
logger = logging.getLogger("EXECUTION_LAB")

load_dotenv()
DERIV_API_TOKEN = os.getenv("DERIV_API_TOKEN")
DERIV_APP_ID = os.getenv("DERIV_APP_ID")

# Mega Brain Params
params_str = os.getenv("LATENCY_ARB_V1_PARAMS", "{}")
params = json.loads(params_str)
DERIV_SYMBOL = params.get("deriv_symbol", "cryBTCUSD")
BINANCE_SYMBOL = params.get("binance_symbol", "btcusdt")
STAKE = float(params.get("stake", 1.0))
USE_DEMO = os.getenv("MEGA_BRAIN_DEMO", "1") == "1"

state = {
    "deriv_client": None,
    "proposal_id_long": None,
    "proposal_id_short": None,
    "has_fired": False,
    "price_history": []
}

async def execute_trade(direction):
    state["has_fired"] = True
    proposal_id = state["proposal_id_long"] if direction == "LONG" else state["proposal_id_short"]
    
    logger.info(f"⚡ GATILHO ACIONADO! Enviando ordem de {direction} (Multiplier) para a Deriv...")
    
    start_time = time.time()
    try:
        res = await state["deriv_client"].buy_contract(proposal_id, STAKE)
        end_time = time.time()
        execution_time = (end_time - start_time) * 1000
        
        if "error" in res:
            logger.warning(f"❌ Ordem rejeitada pela Deriv: {res['error']['message']}")
            logger.info(f"⏱️ Tempo de processamento da recusa: {execution_time:.0f}ms")
        else:
            logger.info("✅ Ordem ACEITA pela Deriv!")
            logger.info(f"⏱️ Tempo de execução da ordem: {execution_time:.0f}ms")
    except Exception as e:
        end_time = time.time()
        logger.error(f"Erro na execução: {e} (levou {(end_time - start_time)*1000:.0f}ms)")
        
    sys.exit(0)

async def binance_ws():
    uri = f"wss://stream.binance.com:9443/ws/{BINANCE_SYMBOL}@bookTicker"
    logger.info(f"Conectando à Binance: {uri}")
    try:
        async with websockets.connect(uri) as websocket:
            logger.info("Binance Conectado! Vigiando Price Shocks...")
            async for message in websocket:
                if state["has_fired"]:
                    break
                    
                data = json.loads(message)
                ask_price = float(data['a'])
                local_time = time.time()
                
                state["price_history"].append({"t": local_time, "p": ask_price})
                state["price_history"] = [x for x in state["price_history"] if local_time - x["t"] <= 5.0]
                
                if len(state["price_history"]) > 10:
                    oldest = state["price_history"][0]
                    diff = ask_price - oldest["p"]
                    
                    if diff >= 1.0:
                        logger.warning(f"🚨 PRICE SHOCK DETECTADO (BULLISH)! Salto de +${diff:.2f}")
                        await execute_trade("LONG")
                        break
                    elif diff <= -1.0:
                        logger.warning(f"🚨 PRICE SHOCK DETECTADO (BEARISH)! Queda de ${diff:.2f}")
                        await execute_trade("SHORT")
                        break
    except Exception as e:
        logger.error(f"Erro Binance: {e}")

async def setup_deriv():
    logger.info("Inicializando cliente Deriv...")
    client = DerivClient(app_id=DERIV_APP_ID, api_token=DERIV_API_TOKEN, use_demo=USE_DEMO)
    await client.connect()
    state["deriv_client"] = client
    
    logger.info("Obtendo Proposals para Contratos MULTUP e MULTDOWN (Multipliers x100)...")
    
    res_up = await client.get_proposal(
        contract_type="MULTUP",
        stake=STAKE,
        symbol=DERIV_SYMBOL,
        multiplier=100
    )
    if "error" in res_up:
        logger.error(f"Erro ao obter proposal MULTUP: {res_up['error']['message']}")
        return False
    state["proposal_id_long"] = res_up["proposal"]["id"]
    
    res_down = await client.get_proposal(
        contract_type="MULTDOWN",
        stake=STAKE,
        symbol=DERIV_SYMBOL,
        multiplier=100
    )
    if "error" in res_down:
        logger.error(f"Erro ao obter proposal MULTDOWN: {res_down['error']['message']}")
        return False
    state["proposal_id_short"] = res_down["proposal"]["id"]
    
    logger.info("Proposals obtidas! Latency Bot Armado.")
    return True

async def main():
    logger.info("🧪 INICIANDO TESTE DE EXECUTION DELAY (MULTIPLIERS)")
    success = await setup_deriv()
    if not success:
        return
    await binance_ws()

if __name__ == "__main__":
    asyncio.run(main())
