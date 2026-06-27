import asyncio
import logging
import os
import time
import numpy as np
from dotenv import load_dotenv
from deriv_client import DerivClient

logging.basicConfig(level=logging.INFO, format='%(asctime)s - REVERSE_ENGINEERING:%(levelname)s:%(message)s')
logger = logging.getLogger("REVERSE_ENGINEERING")

load_dotenv()
API_TOKEN = os.getenv("DERIV_API_TOKEN")
APP_ID = os.getenv("DERIV_APP_ID")
SYMBOL = "BOOM500"

async def fetch_historical_ticks(client, num_chunks=100):
    logger.info(f"📥 Baixando {num_chunks * 5000} ticks históricos para {SYMBOL}...")
    current_end = "latest"
    all_prices = []
    
    for i in range(num_chunks):
        res = await client.send_request({
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
            
        all_prices = prices + all_prices
        current_end = times[0] - 1
        await asyncio.sleep(1) # Respeita o rate limit
        logger.info(f" -> Chunk {i+1}/{num_chunks} OK.")
        
    return all_prices

def analyze_spikes(prices):
    logger.info("🔬 Analisando distâncias entre Spikes (Booms)...")
    spike_distances = []
    ticks_since_last_spike = 0
    
    for i in range(1, len(prices)):
        delta = prices[i] - prices[i-1]
        
        # Em BOOM, o tick normal é negativo. O Spike é positivo e enorme.
        if delta > 0:
            # É um Spike!
            spike_distances.append(ticks_since_last_spike)
            ticks_since_last_spike = 0
        else:
            ticks_since_last_spike += 1
            
    # Remove a primeira distância porque o começo é arbitrário
    if spike_distances:
        spike_distances.pop(0)
        
    if not spike_distances:
        logger.error("Nenhum spike encontrado!")
        return

    logger.info("📊 === RESULTADOS ESTATÍSTICOS DOS SPIKES ===")
    logger.info(f"Total de Spikes analisados: {len(spike_distances)}")
    logger.info(f"Média de ticks entre Spikes: {np.mean(spike_distances):.2f} ticks")
    logger.info(f"Mediana: {np.median(spike_distances):.2f} ticks")
    logger.info(f"Desvio Padrão: {np.std(spike_distances):.2f}")
    logger.info(f"Máximo tempo sem Spike (Dry Run): {np.max(spike_distances)} ticks")
    logger.info(f"Mínimo tempo entre Spikes: {np.min(spike_distances)} ticks")
    
    # Vamos calcular as fatias de probabilidade (CDF)
    dist = np.array(spike_distances)
    percentiles = [50, 75, 90, 95, 99]
    for p in percentiles:
        logger.info(f"{p}% dos Booms acontecem em até {np.percentile(dist, p):.0f} ticks.")

    # Analisar o "Sweet Spot" ou a tese de "Memória"
    # Se fosse puramente aleatório (Poisson / Geométrica), a chance de sair um Spike
    # não mudaria se passassem muitos ticks. Vamos testar.
    
    # Salvar para plotagem / uso posterior
    with open("boom_distances.txt", "w") as f:
        for d in spike_distances:
            f.write(f"{d}\n")

async def analyze():
    client = DerivClient(app_id=APP_ID, api_token=API_TOKEN, use_demo=True)
    await client.connect()
    
    try:
        prices = await fetch_historical_ticks(client, num_chunks=100) # 500.000 ticks
        analyze_spikes(prices)
    finally:
        await client.disconnect()

if __name__ == "__main__":
    asyncio.run(analyze())
