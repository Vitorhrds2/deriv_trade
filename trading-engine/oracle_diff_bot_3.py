import asyncio
import logging
import os
import math
from collections import defaultdict
import time
from dotenv import load_dotenv
from deriv_client import DerivClient

# Configuração do logger
os.makedirs('logs/oracle_diff_bot_3', exist_ok=True)
# show logs on terminal and save on log file
logging.basicConfig(level=logging.INFO, format='%(asctime)s - ORACLE_DIFF:%(levelname)s:%(message)s', handlers=[logging.FileHandler(f'logs/oracle_diff_bot_3/{time.strftime("%Y-%m-%d_%H-%M-%S")}.log'), logging.StreamHandler()])
logger = logging.getLogger("ORACLE_DIFF")

load_dotenv()
API_TOKEN = os.getenv("DERIV_API_TOKEN")
APP_ID = os.getenv("DERIV_APP_ID")
SYMBOL = "1HZ10V" # Volatility 10 (1s) Index

# ======================================================================
# CONFIGURAÇÕES DA ESTRATÉGIA 3 (O PURO ORÁCULO)
# ======================================================================
BASE_STAKE = 10.00
# Sem Martingale. Sem Virtual Loss.
TRAIN_TICK_COUNT = 5000

class OracleDiffBot3:
    def __init__(self):
        self.client = DerivClient(app_id=APP_ID, api_token=API_TOKEN, use_demo=True)
        self.anomalies = {}
        self.is_trading = False
        self.current_stake = BASE_STAKE
        self.pnl_acumulado = 0.0
        self.total_trades = 0
        self.total_wins = 0

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
        
        transitions = defaultdict(lambda: defaultdict(int))
        for i in range(len(digits) - 1):
            transitions[digits[i]][digits[i+1]] += 1
            
        logger.info("🧠 [ORÁCULO] Mapeando anomalias no Pseudo-RNG...")
        
        for current_d in range(10):
            total_transitions = sum(transitions[current_d].values())
            if total_transitions == 0: continue
            
            worst_next_d = min(transitions[current_d], key=transitions[current_d].get)
            count = transitions[current_d][worst_next_d]
            pct = (count / total_transitions) * 100
            
            if pct <= 6.0:
                self.anomalies[current_d] = worst_next_d
                logger.info(f"   -> Encontrado Ponto Cego: Se sair {current_d}, a chance de sair {worst_next_d} é de apenas {pct:.2f}%! (WinRate Esperado: {100-pct:.2f}%)")

        if not self.anomalies:
            logger.warning("Nenhuma anomalia grave encontrada agora. Pegando a melhor disponível...")
            best_diff = 100.0
            best_curr, best_next = None, None
            for current_d in range(10):
                total = sum(transitions[current_d].values())
                if total == 0: continue
                worst_next_d = min(transitions[current_d], key=transitions[current_d].get)
                pct = (transitions[current_d][worst_next_d] / total) * 100
                if pct < best_diff:
                    best_diff = pct
                    best_curr, best_next = current_d, worst_next_d
            
            self.anomalies[best_curr] = best_next
            logger.info(f"   -> Anomalia Forçada: Se sair {best_curr}, apostar que não sai {best_next} ({100-best_diff:.2f}% WinRate)")

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
                    profit = float(contract["profit"])
                    return profit
            except Exception as e:
                logger.error(f"Erro no monitoramento: {e}")
                return 0.0

    async def execute_trade(self, current_digit, target_diff_digit):
        try:
            logger.info(f"🎯 [SNIPER] O Dígito {current_digit} apareceu! Solicitando Diferença em {target_diff_digit}...")
            
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
            self.total_trades += 1
            
            if profit > 0:
                self.total_wins += 1
                wr = (self.total_wins / self.total_trades) * 100
                logger.info(f"✅ WIN | Lucro: +${profit:.2f} | PnL Total: ${self.pnl_acumulado:.2f} | WR: {wr:.2f}% ({self.total_wins}/{self.total_trades})")
            else:
                wr = (self.total_wins / self.total_trades) * 100
                logger.error(f"❌ LOSS | Prejuízo: ${profit:.2f} | PnL Total: ${self.pnl_acumulado:.2f} | WR: {wr:.2f}% ({self.total_wins}/{self.total_trades})")
                logger.warning(f"⚠️ Aceitando o Loss do Cluster. Mantendo stake fixa matemática de ${self.current_stake:.2f}.")
                    
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

    async def start(self):
        if not API_TOKEN or not APP_ID:
            logger.error("Credenciais ausentes no .env")
            return
            
        await self.client.connect()
        try:
            await self.train_oracle()
            logger.info("📡 Conectando antena de Ticks e ativando Modo Tiro Cego (Sem Martingale)...")
            await self.client.subscribe_ticks(SYMBOL, self.on_tick)
            
            while True:
                await asyncio.sleep(1)
                
        except Exception as e:
            logger.error(f"Erro fatal: {e}")
        finally:
            await self.client.disconnect()

if __name__ == "__main__":
    bot = OracleDiffBot3()
    asyncio.run(bot.start())
