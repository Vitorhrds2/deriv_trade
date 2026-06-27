import asyncio
import logging
import os
from collections import defaultdict
from dotenv import load_dotenv
from deriv_client import DerivClient
import time

logging.basicConfig(level=logging.INFO, format='%(asctime)s - BACKTEST:%(levelname)s:%(message)s')
logger = logging.getLogger("BACKTEST")

load_dotenv()
API_TOKEN = os.getenv("DERIV_API_TOKEN")
APP_ID = os.getenv("DERIV_APP_ID")
SYMBOL = "1HZ10V"

class RNGBacktester:
    def __init__(self):
        self.client = DerivClient(app_id=APP_ID, api_token=API_TOKEN, use_demo=True)
        self.all_digits = []

    def extract_last_digit(self, price):
        return int(round(price * 100)) % 10

    async def fetch_historical_chunks(self, num_chunks=5):
        """Baixa blocos de 5000 ticks para formar uma grande base de dados"""
        logger.info(f"📥 Baixando {num_chunks * 5000} ticks históricos para análise...")
        
        current_end = "latest"
        all_prices = []
        
        for i in range(num_chunks):
            res = await self.client.send_request({
                "ticks_history": SYMBOL,
                "adjust_start_time": 1,
                "count": 5000,
                "end": current_end,
                "style": "ticks"
            })
            
            times = res.get("history", {}).get("times", [])
            prices = res.get("history", {}).get("prices", [])
            
            if not prices or not times:
                logger.error("Falha ao baixar bloco de ticks.")
                break
                
            # Adiciona no início da lista (pois estamos indo de trás pra frente)
            all_prices = prices + all_prices
            
            # O próximo request deve terminar no tempo do primeiro tick deste bloco
            current_end = times[0] - 1
            await asyncio.sleep(1) # Rate limit
            
        self.all_digits = [self.extract_last_digit(p) for p in all_prices]
        logger.info(f"✅ {len(self.all_digits)} dígitos extraídos com sucesso.")

    def find_anomalies(self, digits_sample):
        """Acha pontos cegos numa amostra de treinamento"""
        transitions = defaultdict(lambda: defaultdict(int))
        for i in range(len(digits_sample) - 1):
            transitions[digits_sample[i]][digits_sample[i+1]] += 1
            
        anomalies = {}
        for current_d in range(10):
            total = sum(transitions[current_d].values())
            if total == 0: continue
            
            worst_next_d = min(transitions[current_d], key=transitions[current_d].get)
            pct = (transitions[current_d][worst_next_d] / total) * 100
            
            if pct <= 6.0:
                anomalies[current_d] = worst_next_d
                
        return anomalies

    def run_backtest(self):
        """Simula a passagem do tempo: treina em 5000, testa nos próximos 1000, repete."""
        if len(self.all_digits) < 6000:
            logger.error("Dígitos insuficientes para backtest.")
            return

        logger.info("🔬 INICIANDO BACKTEST (Caminhada no Tempo)...")
        
        train_size = 5000
        test_size = 2000 # O tempo que o bot fica rodando antes de recalibrar
        
        total_wins = 0
        total_losses = 0
        max_consecutive_losses = 0
        current_consecutive_losses = 0
        
        # Desliza a janela pela história
        for i in range(0, len(self.all_digits) - train_size - test_size, test_size):
            # 1. Treinamento
            train_window = self.all_digits[i : i + train_size]
            anomalies = self.find_anomalies(train_window)
            
            # Se não achou anomalia <= 6%, pega a melhor disponível
            if not anomalies:
                transitions = defaultdict(lambda: defaultdict(int))
                for j in range(len(train_window) - 1):
                    transitions[train_window[j]][train_window[j+1]] += 1
                best_diff = 100.0
                best_curr, best_next = None, None
                for current_d in range(10):
                    total = sum(transitions[current_d].values())
                    if total == 0: continue
                    worst_next_d = min(transitions[current_d], key=transitions[current_d].get)
                    pct = (transitions[current_d][worst_next_d] / total) * 100
                    if pct < best_diff:
                        best_diff, best_curr, best_next = pct, current_d, worst_next_d
                anomalies[best_curr] = best_next
                
            # 2. Teste Cego no Futuro (Os ticks que vieram DEPOIS do treino)
            test_window = self.all_digits[i + train_size : i + train_size + test_size]
            
            for j in range(len(test_window) - 1):
                curr_digit = test_window[j]
                actual_next_digit = test_window[j+1]
                
                # Se o dígito for um gatilho do nosso oráculo treinado
                if curr_digit in anomalies:
                    target_not_to_be = anomalies[curr_digit]
                    
                    if actual_next_digit != target_not_to_be:
                        total_wins += 1
                        current_consecutive_losses = 0
                    else:
                        total_losses += 1
                        current_consecutive_losses += 1
                        if current_consecutive_losses > max_consecutive_losses:
                            max_consecutive_losses = current_consecutive_losses

        total_trades = total_wins + total_losses
        if total_trades > 0:
            win_rate = (total_wins / total_trades) * 100
            logger.info("==================================================")
            logger.info(f"📊 RESULTADOS DO BACKTEST ESTÁTICO (Sem Retrain a cada tiro)")
            logger.info("==================================================")
            logger.info(f"Total de Trades Simulados: {total_trades}")
            logger.info(f"Wins: {total_wins}")
            logger.info(f"Losses: {total_losses}")
            logger.info(f"WIN RATE REAL NO FUTURO DESCONHECIDO: {win_rate:.2f}%")
            logger.info(f"Máximo de Derrotas Consecutivas: {max_consecutive_losses}")
            logger.info("==================================================")
            
            if max_consecutive_losses > 3:
                logger.warning(f"🚨 Com {max_consecutive_losses} derrotas seguidas, qualquer banca quebraria no Martingale.")

    async def start(self):
        await self.client.connect()
        try:
            # Baixa 50.000 ticks (10 chunks de 5000)
            await self.fetch_historical_chunks(10)
            self.run_backtest()
        finally:
            await self.client.disconnect()

if __name__ == "__main__":
    bot = RNGBacktester()
    asyncio.run(bot.start())
