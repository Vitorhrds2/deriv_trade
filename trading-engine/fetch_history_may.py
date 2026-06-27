import asyncio
import logging
import os
import pandas as pd
from datetime import datetime, timezone
from dotenv import load_dotenv
from deriv_client import DerivClient

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s:%(message)s')
logger = logging.getLogger("HISTORY_FETCHER")

load_dotenv()
API_TOKEN = os.getenv("DERIV_API_TOKEN")
APP_ID = os.getenv("DERIV_APP_ID")

async def fetch_full_history():
    if not API_TOKEN or not APP_ID:
        logger.error("Faltando DERIV_API_TOKEN ou DERIV_APP_ID no arquivo .env")
        return

    # Certifique-se de alterar 'use_demo' para True ou False dependendo de qual conta você quer analisar
    client = DerivClient(app_id=APP_ID, api_token=API_TOKEN, use_demo=False)
    
    try:
        await client.connect()
        logger.info("✅ Conectado à Deriv. Iniciando extração do histórico...")

        # Definindo o período (01 de Maio de 2026 a 31 de Maio de 2026)
        # Convertendo para timestamp Epoch (UTC)
        date_from = int(datetime(2026, 5, 1, 0, 0, 0, tzinfo=timezone.utc).timestamp())
        date_to = int(datetime(2026, 5, 31, 23, 59, 59, tzinfo=timezone.utc).timestamp())
        
        limit = 100  # Limite máximo seguro por requisição na Deriv
        offset = 0
        all_trades = []
        
        logger.info("📅 Buscando trades de Maio de 2026...")

        while True:
            logger.info(f"Fazendo requisição com offset {offset}...")
            
            res = await client.send_request({
                "profit_table": 1,
                "description": 1,
                "date_from": date_from,
                "date_to": date_to,
                "limit": limit,
                "offset": offset
            })

            if "error" in res:
                logger.error(f"Erro na API da Deriv: {res['error']['message']}")
                break

            transactions = res.get("profit_table", {}).get("transactions", [])
            
            if not transactions:
                logger.info("Nenhuma transação a mais encontrada. Busca finalizada.")
                break
                
            all_trades.extend(transactions)
            logger.info(f"Baixados {len(transactions)} trades. Total acumulado: {len(all_trades)}")
            
            if len(transactions) < limit:
                # Se vieram menos trades que o limite, chegamos ao fim
                break
                
            # Prepara o offset para a próxima página
            offset += limit
            
            # Pausa para evitar Rate Limit
            await asyncio.sleep(1)

        if all_trades:
            # Converte a lista de dicionários para um DataFrame do Pandas
            df = pd.DataFrame(all_trades)
            
            # Formata as datas de Epoch para datetime legível
            df['purchase_time'] = pd.to_datetime(df['purchase_time'], unit='s')
            df['sell_time'] = pd.to_datetime(df['sell_time'], unit='s')
            
            # Salva num arquivo CSV de forma bem completa
            filename = "historico_trades_maio.csv"
            df.to_csv(filename, index=False)
            logger.info(f"💾 Sucesso! Histórico com {len(all_trades)} trades salvo em '{filename}'.")
            
            # Mostra um resumo do que foi baixado
            total_profit = df['sell_price'].astype(float).sum() - df['buy_price'].astype(float).sum()
            logger.info(f"📊 Resumo do Mês: Total de Trades = {len(all_trades)} | PnL Bruto Estimado = ${total_profit:.2f}")
        else:
            logger.warning("Nenhum trade encontrado neste período na conta informada.")

    except Exception as e:
        logger.error(f"Erro inesperado: {e}")
    finally:
        await client.disconnect()

if __name__ == "__main__":
    asyncio.run(fetch_full_history())
