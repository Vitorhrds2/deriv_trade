import asyncio
import logging
import os
from dotenv import load_dotenv
from deriv_client import DerivClient

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s:%(levelname)s:%(message)s')
logger = logging.getLogger("DUAL_HEDGE")

# ======================================================================
# CONFIGURAÇÕES DO DUAL HEDGE BOT (METRALHADORA)
# ======================================================================
SYMBOL = "1HZ10V" # Jump 100 Index
STAKE = 20.00
DURATION = 1
DURATION_UNIT = "t" # 1 Tick

load_dotenv()
API_TOKEN = os.getenv("DERIV_API_TOKEN")
APP_ID = os.getenv("DERIV_APP_ID")

class DualHedgeBot:
    def __init__(self):
        self.client = DerivClient(app_id=APP_ID, api_token=API_TOKEN, use_demo=True)
        
    async def get_dual_proposals(self):
        """Pede as duas propostas (CALLE e PUTE) simultaneamente"""
        res_call, res_put = await asyncio.gather(
            self.client.get_proposal(contract_type="CALLE", stake=STAKE, symbol=SYMBOL, duration=DURATION, duration_unit=DURATION_UNIT),
            self.client.get_proposal(contract_type="PUTE", stake=STAKE, symbol=SYMBOL, duration=DURATION, duration_unit=DURATION_UNIT)
        )
        return res_call, res_put

    async def execute_dual_trade(self, call_proposal_id, put_proposal_id):
        """Dispara as duas ordens simultaneamente usando gather para colar os milissegundos"""
        res_call_buy, res_put_buy = await asyncio.gather(
            self.client.buy_contract(call_proposal_id, price=STAKE),
            self.client.buy_contract(put_proposal_id, price=STAKE)
        )
        return res_call_buy, res_put_buy

    async def monitor_contract(self, contract_id, contract_type):
        """Fica checando se o contrato fechou e retorna o lucro"""
        is_sold = False
        while not is_sold:
            await asyncio.sleep(1) # 1 segundo, já que é 1 tick
            try:
                res = await self.client.send_request({"proposal_open_contract": 1, "contract_id": contract_id})
                if "proposal_open_contract" in res:
                    contract = res["proposal_open_contract"]
                    if contract.get("is_sold"):
                        profit = float(contract["profit"])
                        status = "✅ WIN" if profit > 0 else "❌ LOSS"
                        logger.info(f"   -> {contract_type} FECHADO | {status} | ${profit:+.2f}")
                        is_sold = True
                        return profit
            except Exception as e:
                logger.error(f"Erro ao monitorar {contract_type}: {e}")
                return 0.0
        return 0.0

    async def start(self):
        if not API_TOKEN or not APP_ID:
            logger.error("Faltando DERIV_API_TOKEN ou DERIV_APP_ID no .env")
            return
            
        try:
            await self.client.connect()
            logger.info("🚀 Dual Hedge Bot (METRALHADORA) Iniciado! Caçando Flat Ticks...")
            
            pares_lancados = 0
            duplos_vencedores = 0
            pnl_acumulado = 0.0
            
            while True:
                pares_lancados += 1
                logger.info(f"")
                logger.info(f"=== RODADA {pares_lancados} ===")
                
                res_call, res_put = await self.get_dual_proposals()
                
                if "error" in res_call or "error" in res_put:
                    logger.error("Erro ao obter proposta. Tentando novamente na próxima rodada.")
                    await asyncio.sleep(4)
                    continue
                    
                call_id = res_call["proposal"]["id"]
                put_id = res_put["proposal"]["id"]
                
                buy_call, buy_put = await self.execute_dual_trade(call_id, put_id)
                
                call_success = "error" not in buy_call
                put_success = "error" not in buy_put
                
                if not call_success or not put_success:
                    logger.error("Falha ao comprar. Uma perna falhou. Verifique logs/rate limits.")
                    await asyncio.sleep(4)
                    continue
                
                call_contract_id = buy_call['buy']['contract_id']
                put_contract_id = buy_put['buy']['contract_id']
                
                profits = await asyncio.gather(
                    self.monitor_contract(call_contract_id, "CALLE"),
                    self.monitor_contract(put_contract_id, "PUTE")
                )
                
                net_pnl = sum(profits)
                pnl_acumulado += net_pnl
                
                # Se ambas as pernas deram lucro (Flat Tick)
                if profits[0] > 0 and profits[1] > 0:
                    duplos_vencedores += 1
                    logger.info(f"🚨 JACKPOT! FLAT TICK ENCONTRADO! 🚨")
                
                logger.info(f"💰 PNL LÍQUIDO DO PAR: ${net_pnl:+.2f}")
                logger.info(f"📊 ESTATÍSTICAS: Pares: {pares_lancados} | Flat Ticks: {duplos_vencedores} | PnL Global: ${pnl_acumulado:+.2f}")
                
                logger.info("Recarregando... Aguardando 4 segundos.")
                await asyncio.sleep(4)
                
        except Exception as e:
            logger.error(f"Erro fatal: {e}")
        finally:
            await self.client.disconnect()

if __name__ == "__main__":
    bot = DualHedgeBot()
    asyncio.run(bot.start())
