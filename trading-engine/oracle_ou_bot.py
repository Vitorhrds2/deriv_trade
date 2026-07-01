import asyncio
import logging
import os
import math
from collections import defaultdict
from dotenv import load_dotenv
from deriv_client import DerivClient

logging.basicConfig(level=logging.INFO, format='%(asctime)s - ORACLE_OU:%(levelname)s:%(message)s')
logger = logging.getLogger("ORACLE_OU")

load_dotenv()
API_TOKEN = os.getenv("DERIV_API_TOKEN")
APP_ID = os.getenv("DERIV_APP_ID")
SYMBOL = "1HZ10V" # Volatility 10 (1s) Index

# ======================================================================
# CONFIGURAÇÕES DE RISCO E MARTINGALE (SOBREVIVÊNCIA PARA BANCA DE $2.69)
# ======================================================================
BASE_STAKE = 0.35
MARTINGALE_MULTIPLIER = 2.1  
MAX_MARTINGALE_LEVELS = 2    # Lvl0($0.35) -> Lvl1($0.73) -> Lvl2($1.53) = Custo: $2.61 (ideal para simular banca de $5)
TRAIN_TICK_COUNT = 5000      
RETRAIN_INTERVAL_MINUTES = 10
ANOMALY_THRESHOLD = 58.0     # MODO SNIPER DE ELITE: Só entra se a chance for > 58%

class OracleOverUnderBot:
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
        logger.info(f"🧠 [ORÁCULO] Extraindo os últimos {TRAIN_TICK_COUNT} ticks para Machine Learning...")
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
            raise ValueError("Não foi possível baixar os ticks para treinamento.")
            
        digits = [self.extract_last_digit(p) for p in prices]
        
        # Mapeando probabilidade de Over/Under baseada no dígito atual
        transitions = {d: {"OVER_4": 0, "UNDER_5": 0} for d in range(10)}
        for i in range(len(digits) - 1):
            curr = digits[i]
            nxt = digits[i+1]
            if nxt < 5:
                transitions[curr]["UNDER_5"] += 1
            else:
                transitions[curr]["OVER_4"] += 1
            
        logger.info("🧠 [ORÁCULO] Mapeando anomalias 50/50 no Pseudo-RNG...")
        
        for d in range(10):
            total = transitions[d]["UNDER_5"] + transitions[d]["OVER_4"]
            if total == 0: continue
            
            pct_under = (transitions[d]["UNDER_5"] / total) * 100
            pct_over = (transitions[d]["OVER_4"] / total) * 100
            
            if pct_under >= ANOMALY_THRESHOLD:
                self.anomalies[d] = {"type": "DIGITUNDER", "barrier": "5", "winrate": pct_under}
                logger.info(f"   -> 💎 ANOMALIA DE ELITE: Após sair {d}, chance de ser UNDER 5 é de absurdas {pct_under:.2f}%!")
            elif pct_over >= ANOMALY_THRESHOLD:
                self.anomalies[d] = {"type": "DIGITOVER", "barrier": "4", "winrate": pct_over}
                logger.info(f"   -> 💎 ANOMALIA DE ELITE: Após sair {d}, chance de ser OVER 4 é de absurdas {pct_over:.2f}%!")

        if not self.anomalies:
            logger.warning(f"Nenhuma anomalia > {ANOMALY_THRESHOLD}% encontrada agora. O mercado está imprevisível.")
            logger.info("⏳ O Oráculo vai dormir por 60 segundos e coletar novos dados...")
            await asyncio.sleep(60)
            return await self.train_oracle()

    async def get_ou_proposal(self, contract_type, barrier):
        return await self.client.send_request({
            "proposal": 1,
            "amount": round(self.current_stake, 2),
            "basis": "stake",
            "contract_type": contract_type,
            "currency": "USD",
            "underlying_symbol": SYMBOL,
            "duration": 1,
            "duration_unit": "t",
            "barrier": barrier
        })

    async def monitor_contract(self, contract_id):
        while True:
            await asyncio.sleep(1)
            try:
                res = await self.client.send_request({"proposal_open_contract": 1, "contract_id": contract_id})
                contract = res.get("proposal_open_contract", {})
                if contract.get("is_sold"):
                    profit = float(contract["profit"])
                    return profit
            except Exception as e:
                logger.error(f"Erro no monitoramento: {e}")
                return 0.0

    async def execute_trade(self, current_digit, anomaly_data):
        try:
            c_type = anomaly_data["type"]
            barrier = anomaly_data["barrier"]
            
            logger.info(f"🎯 [SNIPER] O Dígito {current_digit} apareceu! Solicitando {c_type}...")
            
            res_prop = await self.get_ou_proposal(c_type, barrier)
            if "error" in res_prop:
                logger.error(f"Erro na proposta: {res_prop['error']['message']}")
                return
                
            proposal_id = res_prop["proposal"]["id"]
            
            res_buy = await self.client.buy_contract(proposal_id, price=round(self.current_stake, 2))
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
                    logger.error("🛑 Limite de Martingale Atingido. Resetando ciclo de apostas.")
                    self.current_stake = BASE_STAKE
                    self.martingale_level = 0
                else:
                    self.current_stake = self.current_stake * MARTINGALE_MULTIPLIER
                    logger.warning(f"⚠️ Aplicando Martingale {self.martingale_level} (Fator {MARTINGALE_MULTIPLIER}x). Próxima Stake: ${self.current_stake:.2f}")
                    
        except Exception as e:
            logger.error(f"Erro na execução: {e}")
        finally:
            logger.info("⏳ Aguardando próximo gatilho...")
            self.is_trading = False

    async def on_tick(self, data):
        if self.is_trading:
            return
            
        tick = data.get("tick")
        if not tick: return
        
        price = tick["quote"]
        last_digit = self.extract_last_digit(price)
        
        if last_digit in self.anomalies:
            self.is_trading = True
            asyncio.create_task(self.execute_trade(last_digit, self.anomalies[last_digit]))

    async def retrain_loop(self):
        while True:
            await asyncio.sleep(RETRAIN_INTERVAL_MINUTES * 60)
            logger.warning(f"🔄 [CRON] Pausando operações para Retreinamento Agendado ({RETRAIN_INTERVAL_MINUTES}m)...")
            self.is_trading = True
            try:
                self.anomalies.clear()
                await self.train_oracle()
            except Exception as e:
                logger.error(f"Erro no retreinamento: {e}")
            finally:
                self.is_trading = False
                logger.info("📡 Retreinamento concluído. Sniper destravado.")

    async def start(self):
        if not API_TOKEN or not APP_ID:
            logger.error("Credenciais ausentes.")
            return
            
        await self.client.connect()
        try:
            await self.train_oracle()
            logger.info("📡 Conectando antena de Ticks e ativando Modo Sniper...")
            await self.client.subscribe_ticks(SYMBOL, self.on_tick)
            
            asyncio.create_task(self.retrain_loop())
            
            while True:
                await asyncio.sleep(1)
                
        except Exception as e:
            logger.error(f"Erro fatal: {e}")
        finally:
            await self.client.disconnect()

if __name__ == "__main__":
    bot = OracleOverUnderBot()
    asyncio.run(bot.start())
