import asyncio
import logging
import os
import pandas as pd
from dotenv import load_dotenv
from deriv_client import DerivClient
from backtester import calculate_bollinger_bands

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s', datefmt='%H:%M:%S')
logger = logging.getLogger("BOT")

class LiveTradingBot:
    def __init__(self, symbol="1HZ100V"):
        self.symbol = symbol
        self.capital = 0.0
        self.position = 0 # 1=Long, -1=Short, 0=Flat
        self.entry_price = 0.0
        self.contract_id = None
        self.risk_per_trade = 0.02
        self.multiplier = 100
        self.candles_buffer = pd.DataFrame()
        self.client = None

    async def start(self):
        load_dotenv()
        app_id = os.getenv("DERIV_APP_ID")
        api_token = os.getenv("DERIV_API_TOKEN")
        
        if not app_id or not api_token:
            logger.error("DERIV_APP_ID or DERIV_API_TOKEN is missing in .env")
            return
            
        self.client = DerivClient(app_id=app_id, api_token=api_token)
        await self.client.connect()
        
        # Obter Saldo Real
        balance_res = await self.client.get_balance()
        if "balance" in balance_res:
            self.capital = balance_res["balance"]["balance"]
        
        logger.info(f"🚀 Bot Live Iniciado. Conta Demo Conectada! Saldo Atual: ${self.capital:.2f}")
        logger.info(f"Carregando buffer inicial de 20 velas para {self.symbol}...")
        
        history = await self.client.get_candles(self.symbol, count=20, granularity=60)
        self.candles_buffer = pd.DataFrame(history.get("candles", []))
        
        logger.info("Assinando WebSocket para receber velas em tempo real...")
        await self.client.subscribe_candles(self.symbol, granularity=60, callback=self.on_candle)
        
        while True:
            await asyncio.sleep(1)
            
    async def get_dynamic_stake(self):
        balance_res = await self.client.get_balance()
        if "balance" in balance_res:
            self.capital = balance_res["balance"]["balance"]
        return max(1.0, round(self.capital * self.risk_per_trade, 2))
            
    async def on_candle(self, data):
        ohlc = data.get("ohlc")
        if not ohlc:
            return
            
        current_price = float(ohlc["close"])
        candle_epoch = int(ohlc["open_time"])
        
        if len(self.candles_buffer) > 0 and self.candles_buffer.iloc[-1]['epoch'] == candle_epoch:
            self.candles_buffer.loc[self.candles_buffer.index[-1], 'close'] = current_price
        else:
            new_row = {'epoch': candle_epoch, 'open': float(ohlc["open"]), 'high': float(ohlc["high"]), 'low': float(ohlc["low"]), 'close': current_price}
            self.candles_buffer = pd.concat([self.candles_buffer, pd.DataFrame([new_row])], ignore_index=True)
            if len(self.candles_buffer) > 20:
                self.candles_buffer = self.candles_buffer.iloc[1:].reset_index(drop=True)
                
        if len(self.candles_buffer) >= 20:
            df = calculate_bollinger_bands(self.candles_buffer.copy(), window=20, num_sd=2.5)
            current_row = df.iloc[-1]
            await self.check_signals(current_price, current_row)
            
    async def execute_trade(self, signal, current_price):
        stake = await self.get_dynamic_stake()
        contract_type = "MULTUP" if signal == 1 else "MULTDOWN"
        
        logger.info(f"🔄 Solicitando Proposal para {contract_type} com stake de ${stake:.2f}...")
        proposal_res = await self.client.get_proposal(
            contract_type=contract_type, 
            stake=stake, 
            symbol=self.symbol, 
            multiplier=self.multiplier
        )
        
        if "error" in proposal_res:
            logger.error(f"Erro no proposal: {proposal_res['error']['message']}")
            return
            
        proposal_id = proposal_res["proposal"]["id"]
        
        logger.info(f"🛒 Enviando ordem de COMPRA (Buy) para proposal {proposal_id}...")
        buy_res = await self.client.buy_contract(proposal_id=proposal_id, price=stake)
        
        if "error" in buy_res:
            logger.error(f"Erro na compra: {buy_res['error']['message']}")
            return
            
        self.contract_id = buy_res["buy"]["contract_id"]
        self.position = signal
        self.entry_price = current_price
        self.capital = buy_res["buy"]["balance_after"]
        
        logger.info(f"✅ Trade Aberto! Contract ID: {self.contract_id} | Tipo: {contract_type} | Preço Entrada: {current_price}")
        
    async def check_signals(self, current_price, row):
        sma = row['sma']
        std = row['std']
        upper = row['upper_band']
        lower = row['lower_band']
        
        if pd.isna(sma):
            return
            
        # Saídas
        if self.position != 0 and self.contract_id:
            sl_distance = 2.0 * std
            close_trade = False
            reason = ""
            
            if self.position == 1:
                sl_price = self.entry_price - sl_distance
                if current_price >= sma:
                    close_trade, reason = True, "Take Profit (Cruzou SMA)"
                elif current_price <= sl_price:
                    close_trade, reason = True, "Stop Loss (Violou 2.0 SD)"
            
            elif self.position == -1:
                sl_price = self.entry_price + sl_distance
                if current_price <= sma:
                    close_trade, reason = True, "Take Profit (Cruzou SMA)"
                elif current_price >= sl_price:
                    close_trade, reason = True, "Stop Loss (Violou 2.0 SD)"
            
            if close_trade:
                logger.info(f"⚠️ Condição de Saída atingida: {reason}. Fechando Contrato {self.contract_id}...")
                sell_res = await self.client.sell_contract(self.contract_id)
                if "error" in sell_res:
                    logger.error(f"Erro ao fechar contrato: {sell_res['error']['message']}")
                    # If already closed/expired
                    if sell_res['error']['code'] == 'InvalidSellContractProposal':
                        self.position = 0
                        self.contract_id = None
                else:
                    profit = sell_res["sell"]["sold_for"]
                    self.capital = sell_res["sell"]["balance_after"]
                    logger.info(f"💵 Contrato Vendido! Recebido: ${profit} | Novo Saldo: ${self.capital:.2f}")
                    self.position = 0
                    self.contract_id = None
                    
        # Entradas
        if self.position == 0:
            if current_price < lower:
                logger.info("🟢 SINAL DE COMPRA (Cruzou Banda Inferior)!")
                await self.execute_trade(1, current_price)
            elif current_price > upper:
                logger.info("🔴 SINAL DE VENDA (Cruzou Banda Superior)!")
                await self.execute_trade(-1, current_price)
                
        status = "FLAT" if self.position == 0 else ("LONG" if self.position == 1 else "SHORT")
        print(f"\rStatus: {status} | Preço: {current_price:.2f} | SMA: {sma:.2f} | Saldo: ${self.capital:.2f}", end="")

if __name__ == "__main__":
    bot = LiveTradingBot()
    try:
        asyncio.run(bot.start())
    except KeyboardInterrupt:
        logger.info("Bot finalizado pelo usuário.")
