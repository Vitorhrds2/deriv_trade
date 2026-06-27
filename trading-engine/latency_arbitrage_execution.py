import asyncio
import logging
import json
import time
import os
import websockets
from dotenv import load_dotenv
from deriv_client import DerivClient

logging.basicConfig(level=logging.INFO, format='%(asctime)s - EXECUTION_LAB:%(levelname)s:%(message)s')
logger = logging.getLogger("EXECUTION_LAB")

load_dotenv()
DERIV_API_TOKEN = os.getenv("DERIV_API_TOKEN")
DERIV_APP_ID = os.getenv("DERIV_APP_ID")
DERIV_SYMBOL = "cryBTCUSD"
BINANCE_SYMBOL = "btcusdt"

state = {
    "deriv_client": None,
    "proposal_id": None,
    "has_fired": False,
    "price_history": [] # list of {"t": time, "p": price}
}

async def execute_trade():
    state["has_fired"] = True
    logger.info("⚡ GATILHO ACIONADO! Enviando ordem de compra para a Deriv...")
    
    start_time = time.time()
    
    try:
        # Tenta comprar o contrato usando o proposal_id
        # Note que se o preço mudou a proposal pode estar inválida,
        # mas só queremos medir o tempo de resposta do servidor da Deriv.
        res = await state["deriv_client"].buy_contract(state["proposal_id"], 10.0)
        
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
        
    # Encerra o script logo depois
    asyncio.get_event_loop().stop()

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
                
                # Mantém apenas os últimos 5 segundos
                state["price_history"] = [x for x in state["price_history"] if local_time - x["t"] <= 5.0]
                
                if len(state["price_history"]) > 10:
                    oldest = state["price_history"][0]
                    diff = ask_price - oldest["p"]
                    
                    if diff >= 1.0: # Salto de $1 pra cima
                        logger.warning(f"🚨 PRICE SHOCK DETECTADO! Salto de +${diff:.2f} em {(local_time - oldest['t'])*1000:.0f}ms")
                        await execute_trade()
                        break
                        
    except Exception as e:
        logger.error(f"Erro Binance: {e}")

async def setup_deriv():
    logger.info("Inicializando cliente Deriv...")
    client = DerivClient(app_id=DERIV_APP_ID, api_token=DERIV_API_TOKEN, use_demo=True)
    await client.connect()
    state["deriv_client"] = client
    
    logger.info("Obtendo Proposal para Contrato Multiplier Up (MULTUP)...")
    res = await client.get_proposal(
        contract_type="MULTUP",
        stake=10.0,
        symbol=DERIV_SYMBOL,
        multiplier=100 # Sem duration para Multipliers
    )
    
    if "error" in res:
        logger.error(f"Erro ao obter proposal: {res['error']['message']}")
        return False
        
    state["proposal_id"] = res["proposal"]["id"]
    logger.info(f"Proposal obtida! ID: {state['proposal_id']}")
    return True

async def main():
    logger.info("🧪 INICIANDO TESTE DE EXECUTION DELAY")
    
    success = await setup_deriv()
    if not success:
        return
        
    await binance_ws()

if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.run_until_complete(main())
