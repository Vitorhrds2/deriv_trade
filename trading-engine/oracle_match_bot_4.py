import asyncio
import logging
import os
import time
from collections import defaultdict
from dotenv import load_dotenv
from deriv_client import DerivClient

os.makedirs('logs/oracle_match_bot_4', exist_ok=True)
logging.basicConfig(level=logging.INFO, format='%(asctime)s - MATCH_BOT_4:%(levelname)s:%(message)s', handlers=[logging.FileHandler(f'logs/oracle_match_bot_4/{time.strftime("%Y-%m-%d_%H-%M-%S")}.log'), logging.StreamHandler()])
logger = logging.getLogger("MATCH_BOT_4")

load_dotenv()
API_TOKEN = os.getenv("DERIV_API_TOKEN")
APP_ID = os.getenv("DERIV_APP_ID")
SYMBOL = "1HZ10V"

BASE_STAKE = 10.00
TRAIN_TICK_COUNT = 5000

class OracleMatchBot4:
    def __init__(self):
        self.client = DerivClient(app_id=APP_ID, api_token=API_TOKEN, use_demo=True)
        self.anomalies = {}
        self.is_trading = False
        self.current_stake = BASE_STAKE
        self.pnl_acumulado = 0.0
        self.total_trades = 0
        self.total_wins = 0
        self.armed_target = None

    def extract_last_digit(self, price):
        return int(round(price * 100)) % 10

    async def train_oracle(self):
        logger.info(f"🧠 [ORÁCULO] Extraindo {TRAIN_TICK_COUNT} ticks para mapear os Clusters de Anomalia...")
        res = await self.client.send_request({
            "ticks_history": SYMBOL,
            "adjust_start_time": 1,
            "count": TRAIN_TICK_COUNT,
            "end": "latest",
            "start": 1,
            "style": "ticks"
        })
        
        prices = res.get("history", {}).get("prices", [])
        if not prices: raise ValueError("Falha ao baixar ticks.")
            
        digits = [self.extract_last_digit(p) for p in prices]
        
        transitions = defaultdict(lambda: defaultdict(int))
        for i in range(len(digits) - 1):
            transitions[digits[i]][digits[i+1]] += 1
            
        logger.info("🧠 [ORÁCULO] Mapeando anomalias no Pseudo-RNG...")
        for current_d in range(10):
            total_transitions = sum(transitions[current_d].values())
            if total_transitions == 0: continue
            
            worst_next_d = min(transitions[current_d], key=transitions[current_d].get)
            pct = (transitions[current_d][worst_next_d] / total_transitions) * 100
            
            if pct <= 6.0:
                self.anomalies[current_d] = worst_next_d
                logger.info(f"   -> Anomalia: {current_d} seguido de {worst_next_d} ({pct:.2f}%). Apostaremos no Cluster!")

        if not self.anomalies:
            logger.info("Pegando a anomalia mais severa possível...")
            best_diff = 100.0
            best_curr, best_next = None, None
            for c in range(10):
                t = sum(transitions[c].values())
                if t == 0: continue
                n = min(transitions[c], key=transitions[c].get)
                pct = (transitions[c][n] / t) * 100
                if pct < best_diff:
                    best_diff = pct
                    best_curr, best_next = c, n
            self.anomalies[best_curr] = best_next
            logger.info(f"   -> Forçado: {best_curr} seguido de {best_next} ({best_diff:.2f}%).")

    async def get_match_proposal(self, barrier_digit):
        return await self.client.send_request({
            "proposal": 1,
            "amount": self.current_stake,
            "basis": "stake",
            "contract_type": "DIGITMATCH",
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

    async def execute_trade(self, target_digit):
        try:
            logger.info(f"🔥 [SWAN HUNTER] O Cluster se iniciou (Anomalia validada). Entrando em DIGITMATCH para o dígito {target_digit}!")
            
            res_prop = await self.get_match_proposal(target_digit)
            if "error" in res_prop:
                logger.error(f"Erro na proposta: {res_prop['error']['message']}")
                return
                
            proposal_id = res_prop["proposal"]["id"]
            
            res_buy = await self.client.buy_contract(proposal_id, price=self.current_stake)
            if "error" in res_buy:
                logger.error(f"Erro na compra: {res_buy['error']['message']}")
                return
                
            contract_id = res_buy["buy"]["contract_id"]
            logger.info(f"🔫 [SWAN HUNTER] Disparo Efetuado! Stake: ${self.current_stake:.2f} | ID: {contract_id}")
            
            profit = await self.monitor_contract(contract_id)
            self.pnl_acumulado += profit
            self.total_trades += 1
            
            if profit > 0:
                self.total_wins += 1
                wr = (self.total_wins / self.total_trades) * 100
                logger.info(f"🚀✅ WIN GIGANTE | Lucro: +${profit:.2f} | PnL Total: ${self.pnl_acumulado:.2f} | WR: {wr:.2f}%")
            else:
                wr = (self.total_wins / self.total_trades) * 100
                logger.error(f"❌ LOSS Normal | Prejuízo: ${profit:.2f} | PnL Total: ${self.pnl_acumulado:.2f} | WR: {wr:.2f}%")
                    
        except Exception as e:
            logger.error(f"Erro na execução: {e}")
        finally:
            logger.info("⏳ Caçador desarmado. Aguardando a próxima anomalia...")
            self.is_trading = False

    async def on_tick(self, data):
        if self.is_trading: return
            
        tick = data.get("tick")
        if not tick: return
        
        price = tick["quote"]
        last_digit = self.extract_last_digit(price)
        
        # Se estamos armados (a anomalia estava sendo monitorada)
        if self.armed_target is not None:
            # Verifica se o evento anômalo aconteceu
            if last_digit == self.armed_target:
                # O CLUSTER ESTÁ FORMADO! O evento improvável aconteceu.
                # A Antítese diz que ele vai se repetir AGORA.
                self.is_trading = True
                asyncio.create_task(self.execute_trade(last_digit))
            
            # Independente do que saiu, o tiro de armar se perdeu.
            self.armed_target = None
            return

        # Armar o Sniper para a anomalia (Virtual Loss)
        if last_digit in self.anomalies:
            self.armed_target = self.anomalies[last_digit]

    async def start(self):
        if not API_TOKEN or not APP_ID: return
        await self.client.connect()
        try:
            await self.train_oracle()
            logger.info("📡 Tese B (O Caçador de Cisnes) online. Buscando aglomerações matemáticas (DIGITMATCH)...")
            await self.client.subscribe_ticks(SYMBOL, self.on_tick)
            while True: await asyncio.sleep(1)
        except Exception as e:
            logger.error(f"Erro fatal: {e}")
        finally:
            await self.client.disconnect()

if __name__ == "__main__":
    bot = OracleMatchBot4()
    asyncio.run(bot.start())
