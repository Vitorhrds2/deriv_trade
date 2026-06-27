import asyncio
import logging
import os
from dotenv import load_dotenv
from deriv_client import DerivClient

# Configurar logging básico
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def main():
    load_dotenv()
    
    app_id = os.getenv("DERIV_APP_ID")
    if not app_id:
        logger.warning("DERIV_APP_ID não definido no .env. Algumas chamadas da API podem falhar ou ser rejeitadas.")
        # Se desejar usar o ID de demonstração para testes rápidos, descomente a linha abaixo
        # app_id = "1089" # ID genérico público
        
    client = DerivClient(app_id=app_id)
    
    try:
        await client.connect()
        
        # Testar conexão com um ping
        logger.info("Enviando ping...")
        response = await client.ping()
        logger.info(f"Resposta do ping: {response}")
        
        # Consultar símbolos ativos
        logger.info("Buscando símbolos ativos (brief)...")
        symbols = await client.get_active_symbols()
        
        if "active_symbols" in symbols:
            first_symbol = symbols["active_symbols"][0]
            logger.info(f"Primeiro símbolo encontrado: {first_symbol['underlying_symbol']} - {first_symbol['underlying_symbol_name']}")
            
            # Inscrever-se para os ticks desse símbolo
            target_symbol = first_symbol['underlying_symbol']
            logger.info(f"Inscrevendo para os ticks de {target_symbol}...")
            
            def on_tick(data):
                tick = data.get("tick", {})
                logger.info(f"TICK -> Símbolo: {tick.get('symbol')}, Preço: {tick.get('quote')}")
                
            await client.subscribe_ticks(target_symbol, on_tick)
            
            # Aguardar alguns segundos recebendo dados
            logger.info("Aguardando 10 segundos para coletar alguns ticks...")
            await asyncio.sleep(10)
            
        else:
            logger.error(f"Erro ao buscar símbolos: {symbols}")

    except Exception as e:
        logger.error(f"Ocorreu um erro: {e}")
    finally:
        await client.disconnect()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Execução interrompida pelo usuário.")
