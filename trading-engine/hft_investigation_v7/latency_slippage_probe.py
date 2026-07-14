import asyncio
import json
import logging
import os
import sys
import time
import statistics
import websockets
from datetime import datetime, timezone

sys.path.insert(0, '/Users/vitorhrds/Documents/Github/hypothesis/trading-engine')
from dotenv import load_dotenv
from deriv_client import DerivClient

load_dotenv(dotenv_path='/Users/vitorhrds/Documents/Github/hypothesis/trading-engine/.env')
DERIV_API_TOKEN = os.getenv("DERIV_API_TOKEN")
DERIV_APP_ID = os.getenv("DERIV_APP_ID")

RESULTS_FILE = "probe_results.jsonl"

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("FrankensteinProbe")

# Variáveis Globais de Preço
global_prices = {
    "binance": None,
    "coinbase": None,
    "kraken": None,
    "bitfinex": None
}

# Configurações do Modeler
WINDOW_MS = 5000
MIN_SAMPLES = 50
Z_SCORE_THRESHOLD = 1.5

state = {
    "deriv_client": None,
    "last_deriv_tick": None,
    "synthetic_history": [],  # lista de (timestamp, price)
    "is_probing": False,
    "probe_count": 0,
    "max_probes": 10
}

def calculate_synthetic():
    if not all(global_prices.values()):
        return None
    # Pesos adaptados com Bitfinex (5%)
    # Como não temos o intercepto perfeito para a regressão de 4 variáveis, 
    # usamos a proporção para rastrear o DELTA (a variação real), que é o que importa.
    return (
        (0.38 * global_prices["binance"]) +
        (0.50 * global_prices["coinbase"]) +
        (0.07 * global_prices["kraken"]) +
        (0.05 * global_prices["bitfinex"])
    )

async def monitor_volatility():
    while True:
        await asyncio.sleep(0.01) # Avalia a cada 10ms
        
        if state["is_probing"] or state["probe_count"] >= state["max_probes"]:
            continue
            
        syn_price = calculate_synthetic()
        if not syn_price:
            continue
            
        now = time.time()
        state["synthetic_history"].append((now, syn_price))
        
        # Limpa histórico velho
        state["synthetic_history"] = [
            x for x in state["synthetic_history"] 
            if (now - x[0]) * 1000 <= WINDOW_MS
        ]
        
        if len(state["synthetic_history"]) < MIN_SAMPLES:
            continue
            
        prices = [x[1] for x in state["synthetic_history"]]
        mean = statistics.mean(prices)
        stdev = statistics.stdev(prices) if len(prices) > 1 else 0
        
        if stdev == 0:
            continue
            
        # Pega a variação nos últimos 50ms para ver se foi um "choque" abrupto
        recent_prices = [x for x in state["synthetic_history"] if (now - x[0]) * 1000 <= 50]
        if not recent_prices:
            continue
            
        oldest_recent = recent_prices[0]
        jump = syn_price - oldest_recent[1]
        
        z_score = abs(jump) / stdev
        
        if z_score >= Z_SCORE_THRESHOLD and abs(jump) > 2.0:  # Z-score alto E movimento real mínimo
            direction = "UP" if jump > 0 else "DOWN"
            logger.warning(f"⚡ CHOQUE DETECTADO! Z-Score: {z_score:.2f} | Salto: {jump:.2f} | Média: {mean:.2f} | Volatilidade(std): {stdev:.2f}")
            asyncio.create_task(fire_probe(direction, syn_price, jump, z_score))


async def fire_probe(direction, trigger_synthetic, jump_amount, z_score):
    if state["is_probing"]: return
    state["is_probing"] = True
    
    logger.info("🚀 INICIANDO AUDITORIA DE SLIPPAGE...")
    client = state["deriv_client"]
    
    # 1. Pegar o tick exato da Deriv ANTES de mandar a ordem
    pre_tick = state["last_deriv_tick"]
    if not pre_tick:
        logger.error("Sem tick da Deriv, abortando.")
        state["is_probing"] = False
        return
        
    logger.info(f"Deriv Pre-Tick: {pre_tick['quote']} (Epoch: {pre_tick['epoch']})")
    
    # 2. Enviar a Ordem
    contract_type = "MULTUP" if direction == "UP" else "MULTDOWN"
    stake = 10.0
    
    ts_start = time.time()
    res = await client.buy_direct(
        contract_type=contract_type,
        stake=stake,
        symbol="cryBTCUSD",
        multiplier=100,  # Multiplicador baixo pois é só probe
        take_profit=1.0,
        stop_loss=1.0
    )
    ts_end = time.time()
    exec_latency_ms = (ts_end - ts_start) * 1000
    
    if "error" in res:
        logger.error(f"Erro na compra: {res['error']['message']}")
        state["is_probing"] = False
        return
        
    contract_id = res["buy"]["contract_id"]
    logger.info(f"✅ Compra Efetuada. ID: {contract_id} | Latência API: {exec_latency_ms:.1f}ms")
    
    # 3. Esperar 1.5s para o contrato estabilizar e ler o entry_spot
    await asyncio.sleep(1.5)
    
    poc = await client.send_request({
        "proposal_open_contract": 1,
        "contract_id": contract_id
    })
    
    entry_spot = None
    if "proposal_open_contract" in poc:
        entry_spot = float(poc["proposal_open_contract"].get("entry_spot", 0) or 0)
        
    logger.info(f"Entry Spot Capturado: {entry_spot}")
    
    # 4. Fechar o contrato manualmente para evitar exposição
    await client.sell_contract(contract_id)
    
    # 5. Salvar Log da Auditoria
    log_data = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "direction": direction,
        "z_score": round(z_score, 2),
        "synthetic_jump": round(jump_amount, 2),
        "synthetic_price_at_trigger": round(trigger_synthetic, 2),
        "deriv_pre_tick_quote": pre_tick["quote"],
        "deriv_pre_tick_epoch": pre_tick["epoch"],
        "deriv_entry_spot": entry_spot,
        "api_latency_ms": round(exec_latency_ms, 1),
        "slippage": round((entry_spot - float(pre_tick["quote"])), 2) if entry_spot else None,
        "is_locked": False
    }
    
    if log_data["slippage"] and abs(log_data["slippage"]) > 0:
        log_data["is_locked"] = True
        logger.critical(f"🚨 TRAVA DETECTADA! Entry Spot ({entry_spot}) diferiu do Pre-Tick ({pre_tick['quote']}). Slippage: {log_data['slippage']}")
    else:
        logger.info(f"🟢 LIVRE DE TRAVA! Entry Spot cravado no Pre-Tick.")
        
    with open(RESULTS_FILE, "a") as f:
        f.write(json.dumps(log_data) + "\n")
        
    state["probe_count"] += 1
    logger.info(f"Audit {state['probe_count']}/{state['max_probes']} concluída. Pausando 10s...")
    
    await asyncio.sleep(10)
    # Limpa buffer para evitar re-disparos pelo mesmo choque
    state["synthetic_history"].clear()
    state["is_probing"] = False
    
    if state["probe_count"] >= state["max_probes"]:
        logger.info("Bateria de testes concluída. Encerrando.")
        os._exit(0)


async def deriv_tick_sync():
    while True:
        try:
            uri = f"wss://api.derivws.com/trading/v1/options/ws/public"
            async with websockets.connect(uri) as ws:
                req = {"ticks": "cryBTCUSD"}
                await ws.send(json.dumps(req))
                logger.info("Deriv Tick Sync conectado...")
                async for message in ws:
                    res = json.loads(message)
                    if 'tick' in res:
                        state["last_deriv_tick"] = {
                            "quote": float(res["tick"]["quote"]),
                            "epoch": res["tick"]["epoch"]
                        }
        except Exception as e:
            logger.error(f"Erro Deriv WS: {e}")
            await asyncio.sleep(2)

async def binance_ws():
    while True:
        try:
            async with websockets.connect("wss://stream.binance.com:9443/ws/btcusdt@bookTicker") as ws:
                logger.info("Binance WS Conectado.")
                async for msg in ws:
                    global_prices["binance"] = float(json.loads(msg)['a'])
        except Exception:
            await asyncio.sleep(2)

async def coinbase_ws():
    while True:
        try:
            async with websockets.connect("wss://ws-feed.exchange.coinbase.com") as ws:
                await ws.send(json.dumps({"type": "subscribe", "product_ids": ["BTC-USD"], "channels": ["ticker"]}))
                logger.info("Coinbase WS Conectado.")
                async for msg in ws:
                    data = json.loads(msg)
                    if "best_ask" in data:
                        global_prices["coinbase"] = float(data["best_ask"])
        except Exception:
            await asyncio.sleep(2)

async def kraken_ws():
    while True:
        try:
            async with websockets.connect("wss://ws.kraken.com") as ws:
                await ws.send(json.dumps({"event": "subscribe", "pair": ["XBT/USD"], "subscription": {"name": "ticker"}}))
                logger.info("Kraken WS Conectado.")
                async for msg in ws:
                    data = json.loads(msg)
                    if isinstance(data, list) and len(data) > 1 and "a" in data[1]:
                        global_prices["kraken"] = float(data[1]["a"][0])
        except Exception:
            await asyncio.sleep(2)

async def bitfinex_ws():
    while True:
        try:
            async with websockets.connect("wss://api-pub.bitfinex.com/ws/2") as ws:
                await ws.send(json.dumps({"event": "subscribe", "channel": "ticker", "symbol": "tBTCUSD"}))
                logger.info("Bitfinex WS Conectado.")
                async for msg in ws:
                    data = json.loads(msg)
                    if isinstance(data, list) and len(data) > 1 and data[1] != "hb":
                        # Bitfinex ticker: [CHANNEL_ID, [BID, BID_SIZE, ASK, ASK_SIZE, ...]]
                        global_prices["bitfinex"] = float(data[1][2]) # ASK price
        except Exception:
            await asyncio.sleep(2)

async def main():
    logger.info("INICIANDO FRANKENSTEIN PROBE (HFT V7)")
    
    client = DerivClient(app_id=DERIV_APP_ID, api_token=DERIV_API_TOKEN, use_demo=True)
    await client.connect()
    
    if not str(client.account_id or "").startswith("DOT"):
        logger.critical("Bot deve rodar em conta DEMO. Abortando.")
        return
        
    state["deriv_client"] = client
    
    await asyncio.gather(
        deriv_tick_sync(),
        binance_ws(),
        coinbase_ws(),
        kraken_ws(),
        bitfinex_ws(),
        monitor_volatility()
    )

if __name__ == "__main__":
    asyncio.run(main())
