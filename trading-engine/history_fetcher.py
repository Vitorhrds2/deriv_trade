import asyncio
import sqlite3
import logging
import pandas as pd
from datetime import datetime
from deriv_client import DerivClient

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

DB_PATH = "ticks.db"

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS candles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT,
            epoch INTEGER,
            open REAL,
            high REAL,
            low REAL,
            close REAL,
            timestamp DATETIME,
            UNIQUE(symbol, epoch)
        )
    ''')
    conn.commit()
    conn.close()

def save_candles(symbol, candles):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    records = []
    for c in candles:
        epoch = c.get("epoch")
        open_p = c.get("open")
        high_p = c.get("high")
        low_p = c.get("low")
        close_p = c.get("close")
        ts = datetime.fromtimestamp(epoch).isoformat()
        records.append((symbol, epoch, open_p, high_p, low_p, close_p, ts))
        
    cursor.executemany('''
        INSERT OR IGNORE INTO candles (symbol, epoch, open, high, low, close, timestamp)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', records)
    
    conn.commit()
    conn.close()
    logger.info(f"{len(records)} velas salvas/ignoradas no banco para {symbol}.")

async def main():
    init_db()
    app_id = "1089"
    client = DerivClient(app_id=app_id)
    await client.connect()
    
    symbol = "1HZ100V" # Volatility 100 Index
    logger.info(f"Baixando 50000 velas de 1 minuto para {symbol} (Out-of-Sample)...")
    
    end_time = "latest"
    total_fetched = 0
    
    for i in range(10): # 10 páginas de 5000 = 50.000 velas
        logger.info(f"Buscando lote {i+1}/10 (end={end_time})...")
        response = await client.get_candles(symbol, count=5000, granularity=60, end=end_time)
        
        candles = response.get("candles", [])
        if not candles:
            logger.error(f"Sem dados na resposta: {response}")
            break
            
        logger.info(f"Lote {i+1} obteve {len(candles)} velas.")
        save_candles(symbol, candles)
        total_fetched += len(candles)
        
        # A API retorna em ordem crescente, então a primeira vela é a mais antiga
        earliest_epoch = candles[0].get("epoch")
        # O próximo batch deve terminar logo antes da vela mais antiga deste batch
        end_time = earliest_epoch - 60 
        
        await asyncio.sleep(2) # Respeitar limites da API
        
    logger.info(f"Finalizado. Total de velas processadas: {total_fetched}")
        
    await client.disconnect()

if __name__ == "__main__":
    asyncio.run(main())
