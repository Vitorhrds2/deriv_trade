import asyncio
import logging
import sqlite3
import json
import os
import time
import sys
from dotenv import load_dotenv
from deriv_client import DerivClient

logging.basicConfig(level=logging.INFO, format='%(asctime)s - [DEEP_ORACLE] %(message)s')
logger = logging.getLogger("DEEP_ORACLE")

load_dotenv()
DERIV_API_TOKEN = os.getenv("DERIV_API_TOKEN")
DERIV_APP_ID = os.getenv("DERIV_APP_ID")

params_str = os.getenv("ORACLE_DEEP_V1_PARAMS", "{}")
params = json.loads(params_str)
SYMBOL = params.get("symbol", "1HZ10V")
STAKE = float(params.get("stake", 0.35))
USE_DEMO = os.getenv("MEGA_BRAIN_DEMO", "1") == "1"
TARGET_TICKS = 100000

DB_FILE = "deep_ticks_memory.db"
PATTERN_DEPTH = 3

class DeepLearningOracle:
    def __init__(self):
        self.client = DerivClient(app_id=DERIV_APP_ID, api_token=DERIV_API_TOKEN, use_demo=USE_DEMO)
        self.conn = sqlite3.connect(DB_FILE)
        self._init_db()
        self.recent_digits = []
        self.anomalies = {} # dict mapping pattern(tuple) -> best_trade_info
        self.is_trading = False
        
    def _init_db(self):
        cursor = self.conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS ticks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                epoch INTEGER UNIQUE,
                price REAL,
                digit INTEGER
            )
        ''')
        # Tabela auxiliar para metadados
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS meta (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        ''')
        self.conn.commit()

    def extract_last_digit(self, price):
        return int(round(price * 100)) % 10

    def get_all_digits_from_db(self):
        cursor = self.conn.cursor()
        cursor.execute('SELECT digit FROM ticks ORDER BY epoch ASC')
        return [row[0] for row in cursor.fetchall()]
        
    def get_db_count(self):
        cursor = self.conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM ticks")
        return cursor.fetchone()[0]

    async def backfill_history(self):
        current_count = self.get_db_count()
        if current_count >= TARGET_TICKS:
            logger.info(f"✅ DB já possui {current_count} ticks. Pulando download.")
            return

        logger.info(f"📥 Iniciando Big Data Backfill ({TARGET_TICKS} ticks)... Isso pode levar alguns segundos.")
        
        # Obter o último epoch que temos (se tivermos)
        cursor = self.conn.cursor()
        cursor.execute("SELECT MIN(epoch) FROM ticks")
        oldest = cursor.fetchone()[0]
        
        end_time = oldest if oldest else "latest"
        
        while current_count < TARGET_TICKS:
            res = await self.client.send_request({
                "ticks_history": SYMBOL,
                "adjust_start_time": 1,
                "count": 5000,
                "end": end_time,
                "start": 1,
                "style": "ticks"
            })
            
            history = res.get("history", {})
            prices = history.get("prices", [])
            times = history.get("times", [])
            
            if not prices:
                logger.error("Falha ao baixar ticks da API.")
                break
                
            inserted = 0
            for t, p in zip(times, prices):
                try:
                    cursor.execute("INSERT INTO ticks (epoch, price, digit) VALUES (?, ?, ?)", 
                                   (t, p, self.extract_last_digit(p)))
                    inserted += 1
                except sqlite3.IntegrityError:
                    pass # Evita duplicatas
                    
            self.conn.commit()
            
            if inserted == 0:
                break
                
            end_time = times[0] # Move a janela para o passado
            current_count = self.get_db_count()
            logger.info(f"📊 Downloaded: {current_count}/{TARGET_TICKS} ticks...")
            await asyncio.sleep(0.5) # Anti-rate limit
            
        logger.info("✅ Backfill Concluído.")

    async def mine_anomalies(self):
        digits = self.get_all_digits_from_db()
        logger.info(f"🔍 Minerando anomalias na amostra de {len(digits)} ticks...")
        
        patterns = {}
        for i in range(len(digits) - PATTERN_DEPTH):
            seq = tuple(digits[i : i + PATTERN_DEPTH])
            nxt = digits[i + PATTERN_DEPTH]
            
            if seq not in patterns:
                patterns[seq] = [0] * 10 # Contador para dígitos 0-9
                
            patterns[seq][nxt] += 1
            
        self.anomalies.clear()
        found = 0
        
        for seq, counts in patterns.items():
            total = sum(counts)
            if total < 50: # Precisamos de amostragem robusta
                continue
                
            # Calcula EVs
            over_4 = sum(counts[5:])
            under_5 = sum(counts[:5])
            even = sum(counts[i] for i in [0, 2, 4, 6, 8])
            odd = sum(counts[i] for i in [1, 3, 5, 7, 9])
            
            over_winrate = over_4 / total
            under_winrate = under_5 / total
            even_winrate = even / total
            odd_winrate = odd / total
            
            best_trade = None
            highest_ev = 0.0
            
            # Limiares calculados para EV Positivo com base no Payout
            # Payout normal: ~95%
            # Payout Matches: ~900%
            
            # Verifica OVER/UNDER/EVEN/ODD (requer > 53% winrate para EV positivo, mas buscamos anomalias > 60%)
            if over_winrate > 0.60:
                ev = over_winrate * 0.95 - (1 - over_winrate)
                if ev > highest_ev:
                    highest_ev = ev
                    best_trade = {"type": "DIGITOVER", "barrier": 4, "winrate": over_winrate}
            
            if under_winrate > 0.60:
                ev = under_winrate * 0.95 - (1 - under_winrate)
                if ev > highest_ev:
                    highest_ev = ev
                    best_trade = {"type": "DIGITUNDER", "barrier": 5, "winrate": under_winrate}
                    
            if even_winrate > 0.60:
                ev = even_winrate * 0.95 - (1 - even_winrate)
                if ev > highest_ev:
                    highest_ev = ev
                    best_trade = {"type": "DIGITEVEN", "barrier": None, "winrate": even_winrate}
                    
            if odd_winrate > 0.60:
                ev = odd_winrate * 0.95 - (1 - odd_winrate)
                if ev > highest_ev:
                    highest_ev = ev
                    best_trade = {"type": "DIGITODD", "barrier": None, "winrate": odd_winrate}
                    
            # Verifica MATCHES (Payout incrível, winrate normal 10%, buscamos > 16%)
            for digit_val, freq in enumerate(counts):
                match_winrate = freq / total
                if match_winrate > 0.16:
                    ev = match_winrate * 9.0 - (1 - match_winrate)
                    if ev > highest_ev:
                        highest_ev = ev
                        best_trade = {"type": "DIGITMATCH", "barrier": digit_val, "winrate": match_winrate}
            
            if best_trade:
                self.anomalies[seq] = best_trade
                found += 1
                bar_str = f"(Barrier: {best_trade['barrier']})" if best_trade['barrier'] is not None else ""
                logger.info(f"🌟 ANOMALIA {seq} -> {best_trade['type']} {bar_str} | WinRate: {best_trade['winrate']*100:.1f}% | EV: +${highest_ev:.2f}/$1")
                
        logger.info(f"✅ Treinamento concluído. {found} oportunidades matemáticas mapeadas!")

    async def on_tick(self, data):
        tick = data.get("tick")
        if not tick: return
        
        price = tick["quote"]
        digit = self.extract_last_digit(price)
        
        self.recent_digits.append(digit)
        if len(self.recent_digits) > PATTERN_DEPTH:
            self.recent_digits.pop(0)
            
        if len(self.recent_digits) == PATTERN_DEPTH:
            current_seq = tuple(self.recent_digits)
            if current_seq in self.anomalies and not self.is_trading:
                self.is_trading = True
                trade = self.anomalies[current_seq]
                
                logger.warning(f"💥 GATILHO ATIVADO! Sequência {current_seq} detectada. Disparando {trade['type']} ao vivo!")
                
                try:
                    res = await self.client.buy_direct(
                        contract_type=trade['type'],
                        stake=STAKE,
                        symbol=SYMBOL,
                        duration=1,
                        duration_unit="t",
                        barrier=trade['barrier']
                    )
                    
                    if "error" in res:
                        logger.error(f"❌ Erro ao abrir contrato: {res['error']['message']}")
                    else:
                        c_id = res['buy']['contract_id']
                        logger.info(f"✅ Contrato COMPRADO! ID: {c_id}")
                except Exception as e:
                    logger.error(f"Falha no trade: {e}")
                
                await asyncio.sleep(2) # Evita multi-disparos rápidos
                self.is_trading = False

    async def start(self):
        await self.client.connect()
        try:
            await self.backfill_history()
            await self.mine_anomalies()
            
            logger.info("📡 Conectando antena de Ticks e ativando robô V2...")
            await self.client.subscribe_ticks(SYMBOL, self.on_tick)
            
            while True:
                await asyncio.sleep(1)
                
        except Exception as e:
            logger.error(f"Erro fatal: {e}")
        finally:
            await self.client.disconnect()
            self.conn.close()

if __name__ == "__main__":
    bot = DeepLearningOracle()
    asyncio.run(bot.start())
