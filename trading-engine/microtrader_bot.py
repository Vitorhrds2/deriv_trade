import asyncio
import logging
import os
import random
import pandas as pd
from collections import deque
from dotenv import load_dotenv
from deriv_client import DerivClient

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s:%(levelname)s:%(message)s')
logger = logging.getLogger("MICROTRADER")

# ======================================================================
# CONFIGURAÇÕES DO MICROTRADER
# ======================================================================
SYMBOL = "1HZ10V"

MULTIPLIER = 4000        # Menor multiplicador para dar espaço ao SL largo
MAX_CONCURRENT_TRADES = 15 # Limite de requisições paralelas para evitar ban da Deriv
TRADE_INTERVAL_SEC = 2.0   # Tenta abrir um novo trade a cada X segundos
BASE_STAKE = 1.00          # Stake inicial. O Oráculo calculará o TP/SL em cima disso.

load_dotenv()
API_TOKEN = os.getenv("DERIV_API_TOKEN")
APP_ID = os.getenv("DERIV_APP_ID")

class MicrotraderBot:
    def __init__(self):
        self.client = DerivClient(app_id=APP_ID, api_token=API_TOKEN, use_demo=True)
        self.virtual_balance = 0.0
        
        self.trade_semaphore = asyncio.Semaphore(MAX_CONCURRENT_TRADES)
        
        self.active_trades = 0
        self.total_wins = 0
        self.total_losses = 0
        
        # Valores que serão preenchidos automaticamente pelo Oráculo
        self.base_tp_usd = 0.0
        self.base_sl_usd = 0.0

    async def run_oracle(self):
        logger.info("🔮 Executando Oráculo Histórico automaticamente (Extraindo 5000 ticks)...")
        res = await self.client.send_request({
            "ticks_history": SYMBOL,
            "adjust_start_time": 1,
            "count": 5000,
            "end": "latest",
            "style": "ticks"
        })
        
        if "error" in res:
            logger.error(f"Erro no oráculo: {res['error']['message']}")
            return False
            
        prices = res["history"]["prices"]
        df = pd.DataFrame({"price": prices})
        
        results = []
        window_size = 30 # Analisa o que acontece nos 30 segundos após cada tick
        
        for i in range(len(df) - window_size):
            entry_price = df.iloc[i]["price"]
            window = df.iloc[i+1 : i+1+window_size]
            
            # Para uma ordem de Compra (MULTUP)
            max_favorable = window["price"].max() - entry_price
            max_adverse = entry_price - window["price"].min()
            
            results.append({
                "mfe": max_favorable,
                "mae": max_adverse
            })
            
        res_df = pd.DataFrame(results)
        
        # TP que tem 80% de chance de bater (20º percentil do MFE)
        tp_points = res_df["mfe"].quantile(0.20)
        # SL que tem apenas 1% de chance de bater (99º percentil do MAE)
        sl_points = res_df["mae"].quantile(0.99)
        
        latest_price = prices[-1]
        
        # Fórmula de Lucro: (Pontos / Preço de Entrada) * Stake * Multiplicador
        self.base_tp_usd = (tp_points / latest_price) * BASE_STAKE * MULTIPLIER
        self.base_sl_usd = (sl_points / latest_price) * BASE_STAKE * MULTIPLIER
        
        # Proteções Risco/Retorno
        # Garante que o TP seja no mínimo $0.75 para pagar a comissão com folga
        self.base_tp_usd = max(self.base_tp_usd, 0.75)
        # Garante que o SL seja largo o suficiente (no mínimo $5.00)
        self.base_sl_usd = max(self.base_sl_usd, 5.00)
        
        logger.info(f"🧠 Oráculo Finalizado! TP Base Otimizado: ${self.base_tp_usd:.2f} | SL Base Seguro: ${self.base_sl_usd:.2f}")
        return True

    def calculate_scale(self):
        """Scale Up inteligente: O TP, SL e o Stake sobem lentamente com a banca"""
        tier = max(1, int(self.virtual_balance // 50) + 1)
        tier = min(tier, 10)
        
        current_stake = BASE_STAKE * tier
        current_tp = self.base_tp_usd * tier
        
        # O Stop Loss não pode ser maior que o próprio Stake nos Multiplicadores da Deriv
        current_sl = min(self.base_sl_usd * tier, current_stake)
        
        return current_stake, current_tp, current_sl

    async def monitor_contract(self, contract_id):
        """Fica checando de tempos em tempos se o contrato já fechou"""
        is_sold = False
        while not is_sold:
            await asyncio.sleep(3)
            try:
                res = await self.client.send_request({"proposal_open_contract": 1, "contract_id": contract_id})
                if "proposal_open_contract" in res:
                    contract = res["proposal_open_contract"]
                    if contract.get("is_sold"):
                        profit = float(contract["profit"])
                        self.virtual_balance += profit
                        
                        if profit > 0:
                            self.total_wins += 1
                            status = "✅ WIN"
                        else:
                            self.total_losses += 1
                            status = "❌ LOSS"
                            
                        win_rate = (self.total_wins / (self.total_wins + self.total_losses)) * 100
                            
                        logger.info(f"{status}! PnL: ${profit:+.2f} | Banca: ${self.virtual_balance:.2f} | WR: {win_rate:.1f}%")
                        is_sold = True
            except Exception as e:
                pass
                
        self.active_trades -= 1

    async def open_micro_trade(self):
        """Abre um único trade usando o semáforo para limitar a concorrência"""
        async with self.trade_semaphore:
            current_stake, current_tp, current_sl = self.calculate_scale()
            
            # Escolhe uma direção aleatória (O TP é tão curto que o ruído deve atingir de qualquer forma)
            contract_type = random.choice(["MULTUP", "MULTDOWN"])
            
            try:
                proposal_res = await self.client.get_proposal(
                    contract_type=contract_type,
                    stake=current_stake,
                    symbol=SYMBOL,
                    multiplier=MULTIPLIER,
                    stop_loss=current_sl,
                    take_profit=current_tp
                )
                
                if "error" in proposal_res:
                    logger.error(f"Erro na proposta (Pode ser limites): {proposal_res['error']['message']}")
                    return
                    
                proposal_id = proposal_res["proposal"]["id"]
                buy_res = await self.client.buy_contract(proposal_id, price=current_stake)
                
                if "error" in buy_res:
                    logger.error(f"Erro na compra: {buy_res['error']['message']}")
                    return
                    
                contract_id = buy_res["buy"]["contract_id"]
                self.active_trades += 1
                logger.info(f"🛒 Contrato {contract_type} Aberto. Ativos: {self.active_trades}/{MAX_CONCURRENT_TRADES}")
                
                # Monitora no background sem travar a thread
                asyncio.create_task(self.monitor_contract(contract_id))
                
            except Exception as e:
                logger.error(f"Exceção no open_micro_trade: {e}")

    async def start_trading_loop(self):
        logger.info("🔥 Iniciando o Motor de Microtrading (Metralhadora)...")
        while True:
            if self.active_trades < MAX_CONCURRENT_TRADES:
                asyncio.create_task(self.open_micro_trade())
            
            await asyncio.sleep(TRADE_INTERVAL_SEC)

    async def start(self):
        if not API_TOKEN or not APP_ID:
            logger.error("Faltando DERIV_API_TOKEN ou DERIV_APP_ID no .env")
            return
            
        try:
            await self.client.connect()
            logger.info("🚀 Microtrader Bot Inicializado!")
            
            # Oráculo embutido: Roda antes de começar os trades!
            oracle_success = await self.run_oracle()
            if not oracle_success:
                logger.error("Falha ao rodar o Oráculo. Abortando.")
                return
            
            bal_res = await self.client.get_balance()
            if "balance" in bal_res:
                self.virtual_balance = float(bal_res["balance"]["balance"])
                
            logger.info(f"🏦 Banca Inicial Sincronizada: ${self.virtual_balance:.2f}")
            
            # Inicia o loop infinito de trading
            await self.start_trading_loop()
                
        except Exception as e:
            logger.error(f"Erro fatal: {e}")
        finally:
            await self.client.disconnect()

if __name__ == "__main__":
    bot = MicrotraderBot()
    asyncio.run(bot.start())
