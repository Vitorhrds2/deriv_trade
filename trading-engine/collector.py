import asyncio
import os
import sqlite3
import logging
from datetime import datetime
from dotenv import load_dotenv
from deriv_client import DerivClient

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

DB_PATH = "ticks.db"

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS ticks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT,
            quote REAL,
            epoch INTEGER,
            timestamp DATETIME
        )
    ''')
    conn.commit()
    conn.close()
    logger.info("Database inicializada.")

def save_tick(symbol, quote, epoch):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO ticks (symbol, quote, epoch, timestamp)
        VALUES (?, ?, ?, ?)
    ''', (symbol, quote, epoch, datetime.fromtimestamp(epoch)))
    conn.commit()
    conn.close()

async def main():
    init_db()
    
    # We use the generic app_id for public data if the user's is invalid
    app_id = "1089"
    client = DerivClient(app_id=app_id)
    
    await client.connect()
    
    symbol = "1HZ100V" # Volatility 100 Index
    logger.info(f"Coletando ticks para {symbol}...")
    
    def on_tick(data):
        tick = data.get("tick")
        if tick:
            sym = tick.get("symbol")
            quote = tick.get("quote")
            epoch = tick.get("epoch")
            logger.info(f"Salvo -> {sym}: {quote}")
            save_tick(sym, quote, epoch)
            
    await client.subscribe_ticks(symbol, on_tick)
    
    try:
        # Run indefinitely (or for a short time for testing)
        logger.info("Executando coletor por 10 segundos para teste...")
        await asyncio.sleep(10)
    finally:
        await client.disconnect()

if __name__ == "__main__":
    asyncio.run(main())
