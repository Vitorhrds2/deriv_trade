import asyncio
import logging
import json
import time
import os
import websockets
from dotenv import load_dotenv
from deriv_client import DerivClient

logging.basicConfig(level=logging.INFO, format='%(asctime)s - HFT_SNIPER:%(levelname)s:%(message)s', handlers=[
    logging.FileHandler("hft_trades.log"),
    logging.StreamHandler()
])
logger = logging.getLogger("HFT_SNIPER")

load_dotenv()
DERIV_API_TOKEN = os.getenv("DERIV_API_TOKEN")
DERIV_APP_ID = os.getenv("DERIV_APP_ID")
DERIV_SYMBOL = "cryBTCUSD"
BINANCE_SYMBOL = "btcusdt"

STAKE = 10.0
MULTIPLIER = 800
PRICE_SHOCK_THRESHOLD = 50.00 # $50.00 para ruptura estrutural > 2s
#PRICE_SHOCK_CEILING = 65.00 # Evitar "Fat Fingers" e flash crashes
#SUSTAIN_DELAY_MS = 350 # Removido da lógica, mas mantido para histórico
LIQUIDATION_DELAY = 0.2

state = {
    "is_trading": False,
    "proposal_up": None,
    "proposal_down": None,
    "deriv_client": None,
    "price_history": [],
    "pending_trigger": None,
    "last_deriv_tick_time": 0.0
}

async def refresh_proposals():
    client = state["deriv_client"]
    while True:
        try:
            # Request UP proposal
            res_up = await client.get_proposal(
                contract_type="MULTUP",
                stake=STAKE,
                symbol=DERIV_SYMBOL,
                multiplier=MULTIPLIER
            )
            if "proposal" in res_up:
                state["proposal_up"] = res_up["proposal"]["id"]
                
            # Request DOWN proposal
            res_down = await client.get_proposal(
                contract_type="MULTDOWN",
                stake=STAKE,
                symbol=DERIV_SYMBOL,
                multiplier=MULTIPLIER
            )
            if "proposal" in res_down:
                state["proposal_down"] = res_down["proposal"]["id"]
                
            await asyncio.sleep(15) # Refresh every 15 seconds
        except Exception as e:
            logger.error(f"Erro ao reciclar proposals: {e}")
            try:
                if client.ws.closed:
                    logger.warning("DerivClient WS fechado! Reconectando...")
                    await client.connect()
            except Exception as ex:
                logger.error(f"Erro ao tentar reconectar DerivClient: {ex}")
            await asyncio.sleep(5)

async def close_trade(contract_id, direction):
    logger.info(f"⏳ Aguardando a ruptura estrutural de 2 segundos...")
    await asyncio.sleep(2.0)
    
    logger.info(f"⏳ Liquidando agressivamente o contrato... (Polling por entry_tick)")
    try:
        logger.info(f"💥 ENVIANDO ORDEM DE FECHAMENTO (SELL) - {contract_id}")
        while True:
            sell_res = await state["deriv_client"].sell_contract(contract_id)
            if "error" in sell_res:
                if "Waiting for entry tick" in sell_res["error"]["message"] or "InvalidContractProposal" in sell_res["error"]["code"]:
                    await asyncio.sleep(0.05)
                    continue
                else:
                    logger.warning(f"❌ Erro ao fechar contrato: {sell_res['error']['message']}")
                    break
            else:
                profit = float(sell_res["sell"]["sold_for"]) - STAKE
                sold_for = float(sell_res["sell"]["sold_for"])
                logger.info(f"✅ TRADE ENCERRADO! Retorno: ${sold_for:.2f} | Lucro: ${profit:.2f} | Direção: {direction}")
                break
    except Exception as e:
        logger.error(f"Erro no fechamento agressivo: {e}")
        
    state["is_trading"] = False
    logger.info("🤖 Sniper recarregado e pronto para o próximo tiro.")

async def execute_trade(direction, price_shock_amount, elapsed_ms):
    if state["is_trading"]:
        return
        
    state["is_trading"] = True
    proposal_id = state["proposal_up"] if direction == "UP" else state["proposal_down"]
    
    if not proposal_id:
        logger.error("Sem proposal ID válido! Cancelando tiro.")
        state["is_trading"] = False
        return
        
    logger.info(f"⚡ GATILHO ACIONADO! Direção: {direction} | Salto: {price_shock_amount:.2f} em {elapsed_ms:.0f}ms")
    start_time = time.time()
    
    try:
        res = await state["deriv_client"].buy_contract(proposal_id, STAKE)
        end_time = time.time()
        exec_time = (end_time - start_time) * 1000
        
        if "error" in res:
            logger.warning(f"❌ Ordem rejeitada: {res['error']['message']}")
            state["is_trading"] = False
        else:
            contract_id = res["buy"]["contract_id"]
            buy_price = float(res["buy"]["buy_price"])
            logger.info(f"✅ ORDEM EXECUTADA! ID: {contract_id} | Execution Time: {exec_time:.0f}ms | Stake: ${buy_price:.2f}")
            
            # Chama a liquidação em background sem travar
            asyncio.create_task(close_trade(contract_id, direction))
            
    except Exception as e:
        logger.error(f"Erro no envio da ordem: {e}")
        state["is_trading"] = False

async def deriv_tick_sync():
    """Worker dedicado para sincronizar o relógio local com os Ticks de 1s da Deriv."""
    uri = f"wss://api.derivws.com/trading/v1/options/ws/public"
    
    while True:
        try:
            async with websockets.connect(uri) as ws:
                req = {"ticks": DERIV_SYMBOL}
                await ws.send(json.dumps(req))
                logger.info("⏱️ Deriv Tick Sync conectado (Raw WS)...")
                
                async for message in ws:
                    res = json.loads(message)
                    if 'tick' in res:
                        state["last_deriv_tick_time"] = time.time()
        except Exception as e:
            logger.error(f"Erro no Tick Sync WS: {e}")
            await asyncio.sleep(2)

async def binance_ws():
    uri = f"wss://stream.binance.com:9443/ws/{BINANCE_SYMBOL}@bookTicker"
    logger.info(f"Conectando à Binance: {uri}")
    
    # Margem de segurança brutal: Exigimos que o tick esteja pelo menos 350ms no futuro.
    # Se a internet variar e a ordem demorar 300ms, ainda entramos antes do tick nascer!
    L_DERIV = 0.350
    # Atraso fixo da Deriv para refletir a Binance
    DERIV_LAG = 0.690
    
    while True:
        try:
            async with websockets.connect(uri) as websocket:
                logger.info("Binance Conectado! Vigiando Price Shocks na Janela de Ouro...")
                async for message in websocket:
                    if state["is_trading"]:
                        continue
                        
                    data = json.loads(message)
                    ask_price = float(data['a'])
                    local_time = time.time()
                    
                    state["price_history"].append({"t": local_time, "p": ask_price})
                    
                    # Mantém os últimos 500ms
                    state["price_history"] = [x for x in state["price_history"] if local_time - x["t"] <= 0.5]
                    
                    if len(state["price_history"]) >= 2:
                        oldest = state["price_history"][0]
                        diff = ask_price - oldest["p"]
                        
                        # Com a lógica de janela de fase, não precisamos mais do teto, apenas do limiar mínimo
                        # if PRICE_SHOCK_THRESHOLD <= abs(diff) <= PRICE_SHOCK_CEILING:
                        if abs(diff) >= PRICE_SHOCK_THRESHOLD:
                            t_0 = local_time
                            t_next_tick = state["last_deriv_tick_time"] + 1.000
                            
                            # Avalia a Janela de Fase
                            # 1. A nossa ordem precisa chegar ANTES do tick
                            cond_arrive_early = (t_0 + L_DERIV) < t_next_tick
                            # 2. O tick precisa nascer ANTES do pulo da Binance chegar na corretora
                            cond_tick_before_jump = t_next_tick < (t_0 + DERIV_LAG)
                            
                            if cond_arrive_early and cond_tick_before_jump:
                                direction = "UP" if diff > 0 else "DOWN"
                                logger.info(f"🎯 FASE ALINHADA! Pulo de {diff:.2f}. Disparando imediatamente!")
                                await execute_trade(direction, diff, 0)
                                state["price_history"].clear()
                            else:
                                pass # Fora de fase, descarta o pulo silenciosamente para não floodar o log
                                
        except Exception as e:
            logger.error(f"Erro Binance WS: {e}. Reconectando em 2s...")
            await asyncio.sleep(2)

async def main():
    logger.info("🚀 INICIANDO BOT HFT - ARBITRAGEM DE LATÊNCIA")
    
    client = DerivClient(app_id=DERIV_APP_ID, api_token=DERIV_API_TOKEN, use_demo=True)
    await client.connect()
    state["deriv_client"] = client
    
    # Inicia as tasks em background
    asyncio.create_task(refresh_proposals())
    asyncio.create_task(deriv_tick_sync())
    await asyncio.sleep(2) # Espera as proposals chegarem
    
    # Roda o websocket da Binance infinitamente
    await binance_ws()

if __name__ == "__main__":
    asyncio.run(main())
