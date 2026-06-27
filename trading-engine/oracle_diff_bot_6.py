import asyncio
import logging
import os
import time
import argparse
from collections import defaultdict, deque
from dotenv import load_dotenv
from deriv_client import DerivClient

# Configuração de Argparse
parser = argparse.ArgumentParser(description="Oráculo Dinâmico HFT")
parser.add_argument("--window", type=int, default=1000, help="Tamanho da Rolling Window (ticks)")
parser.add_argument("--vl", type=int, default=1, help="Número de Virtual Losses antes de atirar")
parser.add_argument("--contract", type=str, default="DIGITDIFF", choices=["DIGITDIFF", "DIGITMATCH"], help="Tipo de Contrato")
parser.add_argument("--soros", type=int, default=0, help="Níveis de Soros (Reinvestimento)")
parser.add_argument("--symbol", type=str, default="1HZ100V", help="Símbolo do Mercado (ex: 1HZ10V, R_100)")
parser.add_argument("--stake", type=float, default=10.0, help="Aposta base em USD")
parser.add_argument("--mode", type=str, default="DEMO", help="Prefixo para logs (DEMO ou REAL)")
parser.add_argument("--envfile", type=str, default=".env", help="Arquivo de variáveis de ambiente")
parser.add_argument("--freeroll", action="store_true", help="Ativa o modo de Risco Zero (House Money)")
args = parser.parse_args()

bot_id = f"BOT_{args.mode}_{args.symbol}_W{args.window}_VL{args.vl}_S{args.soros}_{args.contract}"
os.makedirs(f'logs/{bot_id}', exist_ok=True)
logging.basicConfig(level=logging.INFO, format=f'%(asctime)s - {bot_id}:%(levelname)s:%(message)s', handlers=[logging.FileHandler(f'logs/{bot_id}/{time.strftime("%Y-%m-%d_%H-%M-%S")}.log'), logging.StreamHandler()])
logger = logging.getLogger(bot_id)

load_dotenv(args.envfile)
API_TOKEN = os.getenv("DERIV_API_TOKEN")
APP_ID = os.getenv("DERIV_APP_ID")
SYMBOL = args.symbol

BASE_STAKE = args.stake
ROLLING_WINDOW_SIZE = args.window
TARGET_VL = args.vl
CONTRACT_TYPE = args.contract
SOROS_LEVELS = args.soros

class DynamicOracleBot:
    def __init__(self):
        is_demo = (args.mode != "REAL")
        self.client = DerivClient(app_id=APP_ID, api_token=API_TOKEN, use_demo=is_demo)
        self.tick_buffer = deque(maxlen=ROLLING_WINDOW_SIZE)
        self.anomalies = {}
        self.is_trading = False
        self.current_stake = BASE_STAKE
        self.pnl_acumulado = 0.0
        self.total_trades = 0
        self.total_wins = 0
        
        self.armed_target = None
        self.current_vl_count = 0
        self.last_anomaly_log = 0
        self.current_soros = 0
        self.freeroll_active = False

    def extract_last_digit(self, price):
        return int(round(price * 100)) % 10

    def recalculate_anomalies(self):
        if len(self.tick_buffer) < ROLLING_WINDOW_SIZE: return
            
        digits = list(self.tick_buffer)
        transitions = defaultdict(lambda: defaultdict(int))
        for i in range(len(digits) - 1):
            transitions[digits[i]][digits[i+1]] += 1
            
        new_anomalies = {}
        for current_d in range(10):
            total_transitions = sum(transitions[current_d].values())
            if total_transitions == 0: continue
            
            worst_next_d = min(transitions[current_d], key=transitions[current_d].get)
            pct = (transitions[current_d][worst_next_d] / total_transitions) * 100
            if pct <= 6.0: new_anomalies[current_d] = worst_next_d
                
        if not new_anomalies:
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
            new_anomalies[best_curr] = best_next
            
        self.anomalies = new_anomalies
        
        now = time.time()
        if now - self.last_anomaly_log > 10:
            logger.info(f"🔄 Oráculo Atualizado [Últimos {ROLLING_WINDOW_SIZE} Ticks]: Anomalias -> {self.anomalies}")
            self.last_anomaly_log = now

    async def prefill_buffer(self):
        logger.info(f"🧠 Baixando buffer inicial de {ROLLING_WINDOW_SIZE} ticks...")
        res = await self.client.send_request({
            "ticks_history": SYMBOL,
            "adjust_start_time": 1,
            "count": ROLLING_WINDOW_SIZE,
            "end": "latest",
            "start": 1,
            "style": "ticks"
        })
        
        prices = res.get("history", {}).get("prices", [])
        if not prices: raise ValueError("Falha ao baixar ticks.")
            
        for p in prices:
            self.tick_buffer.append(self.extract_last_digit(p))
            
        self.recalculate_anomalies()
        logger.info("✅ Buffer carregado.")

    async def get_proposal(self, barrier_digit):
        return await self.client.send_request({
            "proposal": 1,
            "amount": self.current_stake,
            "basis": "stake",
            "contract_type": CONTRACT_TYPE,
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
            logger.info(f"💥 [GATILHO ALCANÇADO] {TARGET_VL} VLs atingidos! Atirando {CONTRACT_TYPE} contra {target_digit}!")
            
            res_prop = await self.get_proposal(target_digit)
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
                logger.info(f"✅ WIN | Lucro: +${profit:.2f} | PnL Total: ${self.pnl_acumulado:.2f} | WR: {wr:.2f}%")
                
                # Lógica Soros
                if SOROS_LEVELS > 0:
                    if self.current_soros < SOROS_LEVELS:
                        self.current_soros += 1
                        self.current_stake += profit
                        
                        # VERIFICAÇÃO FREE ROLL
                        if getattr(args, "freeroll", False) and not self.freeroll_active:
                            lucro_nesta_corrida = self.current_stake - BASE_STAKE
                            if lucro_nesta_corrida >= BASE_STAKE:
                                logger.info(f"🛡️ FREE ROLL ATINGIDO! Retirando risco inicial (${BASE_STAKE:.2f}) da mesa.")
                                self.freeroll_active = True
                                self.current_stake -= BASE_STAKE
                                
                        logger.info(f"📈 SOROS ATIVADO (Nível {self.current_soros}/{SOROS_LEVELS}). Nova Stake para próximo tiro: ${self.current_stake:.2f}")
                    else:
                        logger.info(f"🎯 CICLO SOROS CONCLUÍDO! Lucro retido. Resetando stake para ${BASE_STAKE:.2f}")
                        self.current_soros = 0
                        self.current_stake = BASE_STAKE
                        self.freeroll_active = False
            else:
                wr = (self.total_wins / self.total_trades) * 100
                logger.error(f"❌ LOSS | Prejuízo: ${profit:.2f} | PnL Total: ${self.pnl_acumulado:.2f} | WR: {wr:.2f}%")
                if getattr(args, "freeroll", False) and self.freeroll_active:
                    logger.warning(f"⚠️ FREE ROLL PERDIDO. Caixa inicial preservado. Reiniciando ciclo de risco.")
                elif SOROS_LEVELS > 0:
                    logger.warning(f"⚠️ SOROS QUEBRADO. Resetando stake para ${BASE_STAKE:.2f}")
                self.current_soros = 0
                self.current_stake = BASE_STAKE
                self.freeroll_active = False
                    
        except Exception as e:
            logger.error(f"Erro na execução: {e}")
        finally:
            logger.info("⏳ Retornando à fase de espreita...")
            self.is_trading = False

    async def on_tick(self, data):
        tick = data.get("tick")
        if not tick: return
        
        price = tick["quote"]
        last_digit = self.extract_last_digit(price)
        
        self.tick_buffer.append(last_digit)
        
        if self.is_trading: return
        self.recalculate_anomalies()
        
        # Modo Rajada: Desarmar apenas se a anomalia sumir da janela
        if self.armed_target is not None and self.armed_target not in self.anomalies.values():
            self.armed_target = None
            self.current_vl_count = 0
            
        if self.armed_target is not None:
            if last_digit == self.armed_target:
                self.current_vl_count += 1
                if self.current_vl_count >= TARGET_VL:
                    self.is_trading = True
                    asyncio.create_task(self.execute_trade(self.armed_target))
            else:
                # Se ainda não bateu a meta do VL, reseta a contagem
                if self.current_vl_count < TARGET_VL:
                    self.armed_target = None
                    self.current_vl_count = 0
            return

        if last_digit in self.anomalies:
            self.armed_target = self.anomalies[last_digit]
            self.current_vl_count = 0
            
            if TARGET_VL == 0:
                self.is_trading = True
                asyncio.create_task(self.execute_trade(self.armed_target))
                self.armed_target = None

    async def start(self):
        if not API_TOKEN or not APP_ID: return
        await self.client.connect()
        try:
            await self.prefill_buffer()
            logger.info(f"📡 Oráculo Dinâmico ({bot_id}) Online.")
            await self.client.subscribe_ticks(SYMBOL, self.on_tick)
            while True: await asyncio.sleep(1)
        except Exception as e:
            logger.error(f"Erro fatal: {e}")
        finally:
            await self.client.disconnect()

if __name__ == "__main__":
    bot = DynamicOracleBot()
    asyncio.run(bot.start())
