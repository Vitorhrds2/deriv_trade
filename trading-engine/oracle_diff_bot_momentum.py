import asyncio
import logging
import os
import sys
from collections import defaultdict
from dotenv import load_dotenv
from deriv_client import DerivClient

logging.basicConfig(level=logging.INFO, format='%(asctime)s - ORACLE_MOMENTUM:%(levelname)s:%(message)s')
logger = logging.getLogger("ORACLE_MOMENTUM")

load_dotenv()
API_TOKEN = os.getenv("DERIV_API_TOKEN")
APP_ID = os.getenv("DERIV_APP_ID")
SYMBOL = "1HZ10V" # Volatility 10 (1s) Index

# ======================================================================
# CONFIGURAÇÕES DE RISCO E MARTINGALE
# ======================================================================
BASE_STAKE = 1.00 # Reduzido para teste seguro. Pode alterar se quiser.
MARTINGALE_MULTIPLIER = 11.0 
MAX_MARTINGALE_LEVELS = 1    
TRAIN_TICK_COUNT = 5000      
RETRAIN_INTERVAL_MINUTES = 20 

class OracleDiffBotMomentum:
    def __init__(self):
        self.client = DerivClient(app_id=APP_ID, api_token=API_TOKEN, use_demo=True)
        self.anomalies = {} 
        self.is_trading = False
        self.current_stake = BASE_STAKE
        self.martingale_level = 0
        self.pnl_acumulado = 0.0

    def extract_last_digit(self, price):
        return int(round(price * 100)) % 10

    async def train_oracle(self):
        """Mapeia os ticks e escolhe APENAS O MELHOR PONTO CEGO SUPREMO"""
        logger.info(f"🧠 [ORÁCULO] Analisando {TRAIN_TICK_COUNT} ticks para encontrar o Momentum Supremo...")
        res = await self.client.send_request({
            "ticks_history": SYMBOL,
            "adjust_start_time": 1,
            "count": TRAIN_TICK_COUNT,
            "end": "latest",
            "start": 1,
            "style": "ticks"
        })
        
        prices = res.get("history", {}).get("prices", [])
        if not prices:
            raise ValueError("Não foi possível baixar os ticks.")
            
        digits = [self.extract_last_digit(p) for p in prices]
        
        transitions = defaultdict(lambda: defaultdict(int))
        for i in range(len(digits) - 1):
            transitions[digits[i]][digits[i+1]] += 1
            
        best_diff = 100.0
        best_curr, best_next = None, None
        
        # Encontra a anomalia mais severa de todas
        for current_d in range(10):
            total = sum(transitions[current_d].values())
            if total == 0: continue
            
            worst_next_d = min(transitions[current_d], key=transitions[current_d].get)
            pct = (transitions[current_d][worst_next_d] / total) * 100
            
            if pct < best_diff:
                best_diff = pct
                best_curr = current_d
                best_next = worst_next_d
                
        self.anomalies.clear()
        self.anomalies[best_curr] = best_next
        logger.info(f"   -> 🎯 PONTO CEGO SUPREMO: Se sair {best_curr}, NÃO sai {best_next} (WinRate Recalculado: {100-best_diff:.2f}%)")

    async def get_diff_proposal(self, barrier_digit):
        return await self.client.send_request({
            "proposal": 1,
            "amount": self.current_stake,
            "basis": "stake",
            "contract_type": "DIGITDIFF",
            "currency": "USD",
            "underlying_symbol": SYMBOL,
            "duration": 1,
            "duration_unit": "t",
            "barrier": str(barrier_digit)
        })

    async def monitor_contract(self, contract_id):
        while True:
            await asyncio.sleep(1)
            try:
                res = await self.client.send_request({"proposal_open_contract": 1, "contract_id": contract_id})
                contract = res.get("proposal_open_contract", {})
                if contract.get("is_sold"):
                    return float(contract["profit"])
            except Exception as e:
                logger.error(f"Erro no monitoramento: {e}")
                return 0.0

    async def execute_trade(self, current_digit, target_diff_digit):
        try:
            logger.info(f"🎯 [SNIPER] O Dígito {current_digit} apareceu! Disparando contra {target_diff_digit}...")
            
            res_prop = await self.get_diff_proposal(target_diff_digit)
            if "error" in res_prop:
                logger.error(f"Erro na proposta: {res_prop['error']['message']}")
                return
                
            proposal_id = res_prop["proposal"]["id"]
            
            res_buy = await self.client.buy_contract(proposal_id, price=self.current_stake)
            if "error" in res_buy:
                logger.error(f"Erro na compra: {res_buy['error']['message']}")
                return
                
            contract_id = res_buy["buy"]["contract_id"]
            logger.info(f"🔫 [SNIPER] Disparo Efetuado! Stake: ${self.current_stake:.2f} | ID: {contract_id}")
            
            profit = await self.monitor_contract(contract_id)
            self.pnl_acumulado += profit
            
            if profit > 0:
                logger.info(f"✅ WIN | Lucro: +${profit:.2f} | PnL Total: ${self.pnl_acumulado:.2f}")
                self.current_stake = BASE_STAKE
                self.martingale_level = 0
            else:
                logger.error(f"❌ LOSS | Prejuízo: ${profit:.2f} | PnL Total: ${self.pnl_acumulado:.2f}")
                self.martingale_level += 1
                
                if self.martingale_level > MAX_MARTINGALE_LEVELS:
                    logger.error("🛑 Limite de Martingale Atingido. Resetando Stake Base.")
                    self.current_stake = BASE_STAKE
                    self.martingale_level = 0
                else:
                    self.current_stake = self.current_stake * MARTINGALE_MULTIPLIER
                    logger.warning(f"⚠️ Martingale Nível {self.martingale_level} Armado. Próxima Stake: ${self.current_stake:.2f}")
                    
                    # === O PULO DO GATO: Retreinar antes de atirar ===
                    logger.warning("🔄 [MOMENTUM] Pausando operações para recalibrar o Oráculo antes do tiro de Martingale...")
                    await self.train_oracle()
                    
        except Exception as e:
            logger.error(f"Erro na execução: {e}")
        finally:
            logger.info("⏳ Aguardando próximo gatilho supremo...")
            self.is_trading = False

    async def on_tick(self, data):
        if self.is_trading: return
            
        tick = data.get("tick")
        if not tick: return
        
        last_digit = self.extract_last_digit(tick["quote"])
        if last_digit in self.anomalies:
            self.is_trading = True
            asyncio.create_task(self.execute_trade(last_digit, self.anomalies[last_digit]))

    async def retrain_loop(self):
        while True:
            await asyncio.sleep(RETRAIN_INTERVAL_MINUTES * 60)
            logger.warning(f"🔄 [CRON] Retreinamento Agendado ({RETRAIN_INTERVAL_MINUTES}m)...")
            self.is_trading = True
            try:
                await self.train_oracle()
            except Exception as e:
                logger.error(f"Erro no retreinamento automático: {e}")
            finally:
                self.is_trading = False

    async def start(self):
        if not API_TOKEN or not APP_ID:
            logger.error("Credenciais ausentes.")
            return
            
        await self.client.connect()
        try:
            logger.info("🚀 INICIANDO ORACLE MOMENTUM (1 Ponto Cego Supremo + Retrain no Loss)")
            await self.train_oracle()
            await self.client.subscribe_ticks(SYMBOL, self.on_tick)
            asyncio.create_task(self.retrain_loop())
            while True:
                await asyncio.sleep(1)
        finally:
            await self.client.disconnect()

if __name__ == "__main__":
    bot = OracleDiffBotMomentum()
    asyncio.run(bot.start())
