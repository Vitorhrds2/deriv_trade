import asyncio
import logging
import os
import pandas as pd
from collections import deque
from dotenv import load_dotenv
from deriv_client import DerivClient

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s:%(levelname)s:%(message)s')
logger = logging.getLogger("HEDGE_BOT")

# Configs - Hedge Fund (Sniper Assertivo)
SYMBOL = "1HZ10V"
VIRTUAL_BANKROLL = 5.00 # Saldo isolado para simular a conta real de $5
MULTIPLIER = 4000       # Fôlego para o trade não ser stopado por ruído

# Thresholds da Estratégia
RSI_PERIOD = 14          # RSI mais reativo (rápido) para M1
RSI_PULLBACK_UPTREND = 25 # Captura pullbacks saudáveis
RSI_PULLBACK_DNTREND = 75
SMA_FAST_PERIOD = 20
SMA_SLOW_PERIOD = 50
CANDLE_GRANULARITY = 60 # 1 minute

# Mecanismo de Defesa
MAX_CANDLE_JUMP = 3.0    # Salto máximo em 1 vela (em pontos). Evita Faca Caindo e Trem-bala.

load_dotenv()
API_TOKEN = os.getenv("DERIV_API_TOKEN")
APP_ID = os.getenv("DERIV_APP_ID")

class HedgeBot:
    def __init__(self):
        # Voltando para Conta Demo / Conta Real
        self.client = DerivClient(app_id=APP_ID, api_token=API_TOKEN, use_demo=False)
        self.closes = deque(maxlen=SMA_SLOW_PERIOD + 1)
        self.last_candle_start = None
        self.virtual_balance = VIRTUAL_BANKROLL
        self.is_trading = False # Trava para evitar abrir múltiplos trades simultâneos

    def calculate_indicators(self):
        if len(self.closes) < SMA_SLOW_PERIOD:
            return None, None, None
        
        series = pd.Series(list(self.closes))
        sma_fast = series.rolling(window=SMA_FAST_PERIOD).mean().iloc[-1]
        sma_slow = series.rolling(window=SMA_SLOW_PERIOD).mean().iloc[-1]
        
        delta = series.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=RSI_PERIOD).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=RSI_PERIOD).mean()
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))
        current_rsi = rsi.iloc[-1]
        
        return sma_fast, sma_slow, current_rsi

    async def monitor_contract(self, contract_id):
        """Monitora o contrato até ele fechar e atualiza a banca virtual."""
        is_sold = False
        while not is_sold:
            await asyncio.sleep(2)
            try:
                res = await self.client.send_request({"proposal_open_contract": 1, "contract_id": contract_id})
                if "proposal_open_contract" in res:
                    contract = res["proposal_open_contract"]
                    if contract.get("is_sold"):
                        profit = float(contract["profit"])
                        self.virtual_balance += profit
                        status = "✅ WIN" if profit > 0 else "❌ LOSS"
                        tipo_banca = "Banca Virtual" if self.client.use_demo else "Saldo Real"
                        logger.info(f"{status}! Contrato Fechado. PnL: ${profit:.2f} | 💰 {tipo_banca}: ${self.virtual_balance:.2f}")
                        is_sold = True
                        self.is_trading = False # Libera o bot para novos tiros
                        
                        if self.virtual_balance < 1.00:
                            logger.error(f"💀 {tipo_banca.upper()} QUEBRADA! Saldo abaixo de $1.00. O robô será encerrado.")
                            os._exit(0)
            except Exception as e:
                logger.error(f"Erro ao monitorar contrato: {e}")

    async def execute_trade(self, contract_type, current_price, current_rsi):
        if self.is_trading:
            return
            
        # ========================================================
        # TIER SYSTEM DINÂMICO (SCALE UP e SCALE DOWN AUTOMÁTICOS)
        # ========================================================
        # Calcula o stake baseado na dezena da banca (ex: $5 -> $1, $15 -> $2, $25 -> $3)
        calculated_stake = int(self.virtual_balance // 10) + 1
        
        # Limita o stake máximo a $10.00 para não estourar o gerenciamento
        current_stake = float(min(calculated_stake, 10))
        
        # Garante que o stake nunca seja menor que $1.00 por segurança
        current_stake = float(max(current_stake, 1.00))
        
        # Mantém a relação Risco/Retorno de 1:1
        current_tp = current_stake
        current_sl = current_stake
            
        if self.virtual_balance < current_stake:
            tipo_banca = "Banca virtual" if self.client.use_demo else "Saldo real"
            logger.error(f"{tipo_banca} insuficiente (${self.virtual_balance:.2f}) para Stake de ${current_stake:.2f}.")
            return

        self.is_trading = True
        logger.info(f"🎯 SINAL SNIPER {contract_type} M1 | RSI: {current_rsi:.2f} | Preço: {current_price}")
        logger.info(f"🔫 Atirando! Multiplicador x{MULTIPLIER} | Stake: ${current_stake:.2f} | TP: ${current_tp} / SL: ${current_sl}")
        
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
                logger.error(f"Erro na proposta: {proposal_res['error']['message']}")
                self.is_trading = False
                return

            proposal_id = proposal_res["proposal"]["id"]
            buy_res = await self.client.buy_contract(proposal_id, price=current_stake)
            
            if "error" in buy_res:
                logger.error(f"Erro ao comprar: {buy_res['error']['message']}")
                self.is_trading = False
                return
                
            contract_id = buy_res["buy"]["contract_id"]
            logger.info(f"🛒 Contrato Aberto (ID: {contract_id}). Monitorando fechamento...")
            
            # Inicia o monitoramento do contrato em background
            asyncio.create_task(self.monitor_contract(contract_id))

        except Exception as e:
            logger.error(f"Erro ao executar trade: {e}")
            self.is_trading = False

    async def on_candle(self, data):
        if "ohlc" not in data:
            return
            
        ohlc = data["ohlc"]
        epoch = int(ohlc["epoch"])
        close = float(ohlc["close"])
        
        current_candle_start = (epoch // CANDLE_GRANULARITY) * CANDLE_GRANULARITY
        
        # Avalia apenas na virada de minuto e se não houver trade em andamento
        if self.last_candle_start is not None and current_candle_start > self.last_candle_start:
            if len(self.closes) >= SMA_SLOW_PERIOD:
                sma_fast, sma_slow, rsi = self.calculate_indicators()
                if rsi is not None and sma_fast is not None and sma_slow is not None:
                    trend = "ALTA 🟢" if sma_fast > sma_slow else "BAIXA 🔴"
                    closed_price = self.closes[-1]
                    tipo_banca = "Banca Virtual" if self.client.use_demo else "Saldo Real"
                    logger.info(f"Vela M1 Concluída | Fechamento: {closed_price} | RSI: {rsi:05.2f} | {trend} | {tipo_banca}: ${self.virtual_balance:.2f}")
                    
                    if not self.is_trading:
                        # ========================================================
                        # LÓGICA DE DETECÇÃO DE FACA CAINDO E TREM-BALA (MOMENTUM)
                        # ========================================================
                        prev_close = self.closes[-2]
                        candle_jump = closed_price - prev_close # Positivo = Alta | Negativo = Queda
                        
                        if sma_fast > sma_slow:
                            if rsi < RSI_PULLBACK_UPTREND:
                                if candle_jump < -MAX_CANDLE_JUMP:
                                    logger.warning(f"⚠️ FACA CAINDO DETECTADA (Queda de {candle_jump:.2f} pts). Sinal MULTUP abortado!")
                                else:
                                    asyncio.create_task(self.execute_trade("MULTUP", closed_price, rsi))
                        elif sma_fast < sma_slow:
                            if rsi > RSI_PULLBACK_DNTREND:
                                if candle_jump > MAX_CANDLE_JUMP:
                                    logger.warning(f"⚠️ TREM-BALA DETECTADO (Alta de +{candle_jump:.2f} pts). Sinal MULTDOWN abortado!")
                                else:
                                    asyncio.create_task(self.execute_trade("MULTDOWN", closed_price, rsi))
                    else:
                        logger.info("⏳ Aguardando contrato atual fechar...")
        
        if self.last_candle_start is None or current_candle_start > self.last_candle_start:
            self.closes.append(close)
            self.last_candle_start = current_candle_start
        else:
            self.closes[-1] = close

    async def start(self):
        if not API_TOKEN or not APP_ID:
            logger.error("Faltando DERIV_API_TOKEN ou DERIV_APP_ID no .env")
            return

        try:
            await self.client.connect()
            conta_tipo = "CONTA DEMO" if self.client.use_demo else "CONTA REAL"
            logger.info(f"🚀 Hedge Fund Bot (Sniper Assertivo) Iniciado na {conta_tipo}!")
            
            if self.client.use_demo:
                logger.info(f"🛡️  Banca Virtual isolada definida em: ${self.virtual_balance:.2f} (Ignorando saldo real)")
            else:
                bal_res = await self.client.get_balance()
                if "balance" in bal_res:
                    self.virtual_balance = float(bal_res["balance"]["balance"])
                logger.info(f"🏦 Saldo Real Sincronizado: ${self.virtual_balance:.2f}")
            logger.info(f"Baixando histórico para buffer inicial...")
            
            hist = await self.client.get_candles(SYMBOL, count=SMA_SLOW_PERIOD, granularity=CANDLE_GRANULARITY)
            if "candles" in hist:
                for c in hist["candles"]:
                    self.closes.append(float(c["close"]))
                    self.last_candle_start = int(c["epoch"])
            
            logger.info(f"Histórico carregado. Assinando WebSockets para M1.")
            await self.client.subscribe_candles(SYMBOL, granularity=CANDLE_GRANULARITY, callback=self.on_candle)
            
            while True:
                await asyncio.sleep(1)
                
        except Exception as e:
            logger.error(f"Erro fatal: {e}")
        finally:
            await self.client.disconnect()

if __name__ == "__main__":
    bot = HedgeBot()
    asyncio.run(bot.start())