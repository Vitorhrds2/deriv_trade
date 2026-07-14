import asyncio
import logging
import time
import os
from dotenv import load_dotenv
from deriv_client import DerivClient
from datetime import datetime, timezone, timedelta

# Define GMT-3 timezone
GMT_MINUS_3 = timezone(timedelta(hours=-3))

class GMTMinus3Formatter(logging.Formatter):
    def formatTime(self, record, datefmt=None):
        dt = datetime.fromtimestamp(record.created, tz=GMT_MINUS_3)
        if datefmt:
            return dt.strftime(datefmt)
        return dt.isoformat()

formatter = GMTMinus3Formatter('%(asctime)s - FLAT_TICK_BOT:%(levelname)s:%(message)s', datefmt='%Y-%m-%d %H:%M:%S.%f')
file_handler = logging.FileHandler("flat_tick.log")
file_handler.setFormatter(formatter)
stream_handler = logging.StreamHandler()
stream_handler.setFormatter(formatter)

logging.basicConfig(level=logging.INFO, handlers=[file_handler, stream_handler])
logger = logging.getLogger("FLAT_TICK_BOT")

load_dotenv()
DERIV_API_TOKEN = os.getenv("DERIV_API_TOKEN")
DERIV_APP_ID = os.getenv("DERIV_APP_ID")
SYMBOL = "JD100"

STAKE = 1.00
GLOBAL_STOP_LOSS = -100.00

state = {
    "total_profit": 0.0,
    "trades_won": 0,
    "trades_lost": 0,  # Means one won, one lost (normal scenario)
    "jackpots": 0,     # Means both won (flat tick)
    "total_trades": 0
}

async def fetch_profit(client, contract_id):
    """Wait for the contract to close and return its profit/loss."""
    await asyncio.sleep(2.0) # Wait for the 1-tick contract to resolve
    
    timeout = 10
    start_time = time.time()
    while time.time() - start_time < timeout:
        poll_res = await client.send_request({"proposal_open_contract": 1, "contract_id": contract_id})
        if "proposal_open_contract" in poll_res and poll_res["proposal_open_contract"]:
            contract = poll_res["proposal_open_contract"]
            if contract.get("is_sold") or contract.get("is_settled"):
                profit = float(contract.get("profit", 0))
                status = contract.get("status")
                return profit, status
        await asyncio.sleep(0.5)
    return 0.0, "timeout"

async def run_bot():
    client = DerivClient(app_id=DERIV_APP_ID, api_token=DERIV_API_TOKEN, use_demo=True)
    
    logger.info("🚀 INICIANDO FLAT TICK BOT (Arbitragem de Empate)")
    logger.info(f"Target Symbol: {SYMBOL}")
    logger.info(f"Stake por Perna: ${STAKE:.2f} (Total ${STAKE*2:.2f} por rodada)")
    logger.info(f"Stop Loss Global: ${GLOBAL_STOP_LOSS:.2f}")
    
    try:
        await client.connect()
    except Exception as e:
        logger.error(f"Erro ao conectar: {e}")
        return

    await asyncio.sleep(2)
    
    # Loop de execução
    while True:
        if state["total_profit"] <= GLOBAL_STOP_LOSS:
            logger.error(f"⛔ STOP LOSS GLOBAL ATINGIDO! Prejuízo acumulado: ${state['total_profit']:.2f}")
            break
            
        logger.info("⚔️ Disparando cerco (CALLE + PUTE) simultâneo...")
        start_exec = time.time()
        
        # Dispara as duas ordens no exato mesmo momento
        buy_tasks = [
            client.buy_direct(contract_type="CALLE", stake=STAKE, symbol=SYMBOL, duration=1, duration_unit="t"),
            client.buy_direct(contract_type="PUTE", stake=STAKE, symbol=SYMBOL, duration=1, duration_unit="t")
        ]
        
        results = await asyncio.gather(*buy_tasks, return_exceptions=True)
        end_exec = time.time()
        
        contract_ids = []
        for i, res in enumerate(results):
            if isinstance(res, Exception):
                logger.error(f"❌ Erro na perna {i}: {res}")
            elif "error" in res:
                logger.error(f"❌ Ordem rejeitada: {res['error']['message']}")
            else:
                contract_ids.append(res["buy"]["contract_id"])
                
        if len(contract_ids) == 2:
            exec_time = (end_exec - start_exec) * 1000
            logger.info(f"✅ Cerco armado com sucesso em {exec_time:.0f}ms! IDs: {contract_ids[0]}, {contract_ids[1]}")
            
            # Aguarda a resolução dos 2 contratos
            profit_tasks = [
                fetch_profit(client, contract_ids[0]),
                fetch_profit(client, contract_ids[1])
            ]
            
            profit_results = await asyncio.gather(*profit_tasks)
            
            p1, s1 = profit_results[0]
            p2, s2 = profit_results[1]
            
            round_profit = p1 + p2
            state["total_profit"] += round_profit
            state["total_trades"] += 1
            
            if p1 > 0 and p2 > 0:
                state["jackpots"] += 1
                logger.info(f"🔥 JACKPOT! FLAT TICK DETECTADO! Lucro da rodada: +${round_profit:.2f}")
            else:
                state["trades_lost"] += 1
                logger.info(f"💧 O preço andou. Pedágio pago. Lucro da rodada: ${round_profit:.2f}")
                
            logger.info(f"📊 Stats | Total Trades: {state['total_trades']} | Jackpots: {state['jackpots']} | Lucro Acumulado: ${state['total_profit']:.2f}\n")
        else:
            logger.warning("Falha ao armar o cerco completo. Pausando 5s...")
            await asyncio.sleep(5)
            
        # Pequena pausa antes do próximo tiro para evitar rate limits
        await asyncio.sleep(3)

    await client.disconnect()

if __name__ == "__main__":
    asyncio.run(run_bot())
