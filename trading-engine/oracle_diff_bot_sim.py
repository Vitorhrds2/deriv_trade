import asyncio
import logging
import os
import math
import sys
from collections import defaultdict
from dotenv import load_dotenv
from deriv_client import DerivClient

logging.basicConfig(level=logging.INFO, format='%(asctime)s - ORACLE_SIM:%(levelname)s:%(message)s')
logger = logging.getLogger("ORACLE_SIM")

load_dotenv()
API_TOKEN = os.getenv("DERIV_API_TOKEN")
APP_ID = os.getenv("DERIV_APP_ID")
SYMBOL = "1HZ10V" # Volatility 10 (1s) Index

# ======================================================================
# CONFIGURAÇÕES DE RISCO E MARTINGALE (CONTA REAL SIMULADA)
# ======================================================================
BASE_STAKE = 1.00             # Aposta mínima inicial
VIRTUAL_BANKROLL = 12.00      # Saldo total da sua "Conta Real Futura"
MARTINGALE_MULTIPLIER = 11.0  # 11x para recuperar o loss num payout de 9.9%
MAX_MARTINGALE_LEVELS = 3     
TRAIN_TICK_COUNT = 5000       
RETRAIN_INTERVAL_MINUTES = 20

class OracleDiffBotSim:
    def __init__(self):
        self.client = DerivClient(app_id=APP_ID, api_token=API_TOKEN, use_demo=True)
        self.anomalies = {} 
        self.is_trading = False
        self.local_base_stake = BASE_STAKE
        self.current_stake = self.local_base_stake
        self.martingale_level = 0
        self.virtual_bankroll = VIRTUAL_BANKROLL

    def extract_last_digit(self, price):
        return int(round(price * 100)) % 10

    async def train_oracle(self):
        logger.info(f"🧠 [ORÁCULO] Extraindo os últimos {TRAIN_TICK_COUNT} ticks...")
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
            
        for current_d in range(10):
            total_transitions = sum(transitions[current_d].values())
            if total_transitions == 0: continue
            
            worst_next_d = min(transitions[current_d], key=transitions[current_d].get)
            count = transitions[current_d][worst_next_d]
            pct = (count / total_transitions) * 100
            
            if pct <= 6.0:
                self.anomalies[current_d] = worst_next_d
                logger.info(f"   -> Ponto Cego: Se sair {current_d}, a chance de sair {worst_next_d} é {pct:.2f}% (WinRate: {100-pct:.2f}%)")

        if not self.anomalies:
            logger.warning("Nenhuma anomalia grave encontrada. Pegando a melhor...")
            best_diff = 100.0
            best_curr, best_next = None, None
            for current_d in range(10):
                total = sum(transitions[current_d].values())
                if total == 0: continue
                worst_next_d = min(transitions[current_d], key=transitions[current_d].get)
                pct = (transitions[current_d][worst_next_d] / total) * 100
                if pct < best_diff:
                    best_diff, best_curr, best_next = pct, current_d, worst_next_d
            
            self.anomalies[best_curr] = best_next
            logger.info(f"   -> Anomalia Forçada: Se {best_curr}, não sai {best_next} ({100-best_diff:.2f}%)")

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
            # Proteção da Banca Virtual
            if self.current_stake > self.virtual_bankroll:
                logger.error(f"🛑 BANKRUPT! QUEBRA DE BANCA. Saldo Restante: ${self.virtual_bankroll:.2f} | Stake Exigida: ${self.current_stake:.2f}")
                logger.error("O Martingale ultrapassou a banca simulada. Desligando robô para segurança.")
                sys.exit(0)

            logger.info(f"🎯 [SNIPER] Dígito {current_digit} -> Disparo contra {target_diff_digit}...")
            
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
            logger.info(f"🔫 Disparo! Stake: ${self.current_stake:.2f} | ID: {contract_id}")
            
            profit = await self.monitor_contract(contract_id)
            self.virtual_bankroll += profit
            
            if profit > 0:
                logger.info(f"✅ WIN | Lucro: +${profit:.2f} | Banca Atual: ${self.virtual_bankroll:.2f}")
                
                # Juros Compostos: Recalcula a Stake Base conforme a banca
                nova_base_stake = math.floor(self.virtual_bankroll / 11.0)
                nova_base_stake = float(max(1.0, min(10.0, nova_base_stake)))
                
                if nova_base_stake != self.local_base_stake:
                    logger.info(f"📈 [COMPOSIÇÃO] Banca cresceu! A Stake Base foi ajustada para: ${nova_base_stake:.2f}")
                
                self.local_base_stake = nova_base_stake
                self.current_stake = self.local_base_stake
                self.martingale_level = 0
            else:
                logger.error(f"❌ LOSS | Prejuízo: ${profit:.2f} | Banca Atual: ${self.virtual_bankroll:.2f}")
                self.martingale_level += 1
                self.current_stake = self.local_base_stake * MARTINGALE_MULTIPLIER
                logger.warning(f"⚠️ Martingale Nível {self.martingale_level}. Próxima Stake Exigida: ${self.current_stake:.2f}")
                    
        except SystemExit:
            os._exit(0)
        except Exception as e:
            logger.error(f"Erro na execução: {e}")
        finally:
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
            logger.warning(f"🔄 [CRON] Pausando operações para Retreinamento Agendado ({RETRAIN_INTERVAL_MINUTES}m)...")
            self.is_trading = True
            try:
                self.anomalies.clear()
                await self.train_oracle()
            except Exception as e:
                logger.error(f"Erro no retreinamento automático: {e}")
            finally:
                self.is_trading = False
                logger.info("📡 Retreinamento concluído. Sniper pronto.")

    async def start(self):
        if not API_TOKEN or not APP_ID:
            return
            
        await self.client.connect()
        try:
            logger.info(f"🏦 INICIANDO SIMULADOR: Banca = ${self.virtual_bankroll:.2f} | Juros Compostos Ativados (Max Stake: $10)")
            await self.train_oracle()
            await self.client.subscribe_ticks(SYMBOL, self.on_tick)
            asyncio.create_task(self.retrain_loop())
            while True:
                await asyncio.sleep(1)
        finally:
            await self.client.disconnect()

if __name__ == "__main__":
    bot = OracleDiffBotSim()
    asyncio.run(bot.start())
