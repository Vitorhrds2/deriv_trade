import asyncio
import logging
import json
import random
import time
import os
import websockets
from dotenv import load_dotenv
from deriv_client import DerivClient

import time
from datetime import datetime, timezone, timedelta

# Define GMT-3 timezone
GMT_MINUS_3 = timezone(timedelta(hours=-3))

class GMTMinus3Formatter(logging.Formatter):
    def formatTime(self, record, datefmt=None):
        dt = datetime.fromtimestamp(record.created, tz=GMT_MINUS_3)
        if datefmt:
            return dt.strftime(datefmt)
        return dt.isoformat()

formatter = GMTMinus3Formatter('%(asctime)s - HFT_SNIPER:%(levelname)s:%(message)s', datefmt='%Y-%m-%d %H:%M:%S.%f')
file_handler = logging.FileHandler("hft_trades.log")
file_handler.setFormatter(formatter)
stream_handler = logging.StreamHandler()
stream_handler.setFormatter(formatter)

logging.basicConfig(level=logging.INFO, handlers=[file_handler, stream_handler])
logger = logging.getLogger("HFT_SNIPER")

load_dotenv()
DERIV_API_TOKEN = os.getenv("DERIV_API_TOKEN")
DERIV_APP_ID = os.getenv("DERIV_APP_ID")
DERIV_SYMBOL = "cryBTCUSD"
BINANCE_SYMBOL = "btcusdt"

MAX_DEMO_LOSS_USD = float(os.getenv("HFT_MAX_DEMO_LOSS_USD", "50"))
MAX_SESSION_TRADES = int(os.getenv("HFT_MAX_SESSION_TRADES", "30"))

STAKE = 10.0
MULTIPLIER = 800
PRICE_SHOCK_THRESHOLD = 45.00 # V6.2 Ultra-Momentum: threshold reduzido de 50 para 45 (mais frequência de entradas)
TAKE_PROFIT_PCT = 0.80 # V6.2: alvo ampliado de 60% para 80%
STOP_LOSS_PCT = 0.25 # V6.2: stop encurtado de 35% para 25%
# Decisão (analysis_results.md): teto de preço fixo removido em favor de um filtro de velocidade.
# Saltos que se formam lentamente (>JUMP_FORMATION_WINDOW) já foram parcialmente absorvidos
# pelo índice sintético da Deriv antes do robô disparar, e tendem a não pagar a comissão.
JUMP_FORMATION_WINDOW = 0.050 # 50ms: só aceita saltos que se formaram dentro desta janela
# Investigação 2026-07-01 (docs/antigravity-brain/README.md): todas as trades reais fechavam
# via venda manual (não pelo SL/TP nativo), a preços de mercado arbitrários, sempre piores que
# a SL configurada. Causa: timeout de força-fechamento (antigo 120s) curto demais. Fix: confiar
# no limit_order nativo e só usar o fechamento manual como rede de segurança de última instância.
SAFETY_TIMEOUT = 1800.0 # 30min — não deve disparar em operação normal
LIQUIDATION_DELAY = 0.2

# Horário de ouro (proud-borg/hft_period_analysis.md): ~85% do lucro histórico se concentra
# entre 12:00-17:59 UTC. Fora dessa janela o robô só monitora, não dispara ordens.
GOLDEN_HOUR_START_UTC = 12
GOLDEN_HOUR_END_UTC = 18 # exclusivo (ou seja, até 17:59:59)

# Shadow A/B (docs/hft_v62_audit_report.md): a auditoria da Fase 1 nao teve controle nulo
# explicito -- o bot so testou "aligned" (segue o choque), nunca "anti" (contra), diferente
# do H3 (que rodou os dois grupos). Com isso ativo, cada gatilho sorteia 50/50 entre os dois
# grupos e loga qual foi usado, para que audit_hft_trades.py possa comparar EV(aligned) vs
# EV(anti) com bootstrap_diff_ci -- se nao houver diferenca estatistica, o problema e
# estrutural (latencia de execucao, ja confirmado por H3), nao de direcao do sinal.
SHADOW_AB_TESTING = True
SHADOW_AB_ANTI_PROB = 0.5

global_prices = {
    "binance": None,
    "coinbase": None,
    "kraken": None
}

state = {
    "is_trading": False,
    "proposal_up": None,
    "proposal_down": None,
    "deriv_client": None,
    "price_history": [],
    "pending_trigger": None,
    "last_deriv_tick_time": 0.0,
    "session_pnl": 0.0,
    "closed_trades": 0,
    "halted": False
}

def is_golden_hour():
    hour_utc = datetime.now(timezone.utc).hour
    return GOLDEN_HOUR_START_UTC <= hour_utc < GOLDEN_HOUR_END_UTC

def record_closed_trade(profit):
    state["session_pnl"] += profit
    state["closed_trades"] += 1
    logger.info(
        f"SESSION LEDGER | Trades: {state['closed_trades']} | "
        f"PnL: ${state['session_pnl']:.2f} | MaxLoss: ${MAX_DEMO_LOSS_USD:.2f}"
    )

    if MAX_DEMO_LOSS_USD > 0 and state["session_pnl"] <= -abs(MAX_DEMO_LOSS_USD):
        state["halted"] = True
        logger.critical(
            f"KILL SWITCH: perda demo de sessao atingiu ${state['session_pnl']:.2f}. "
            "Novas ordens bloqueadas ate reinicio/configuracao humana."
        )

    if MAX_SESSION_TRADES > 0 and state["closed_trades"] >= MAX_SESSION_TRADES:
        state["halted"] = True
        logger.critical(
            f"KILL SWITCH: limite de {MAX_SESSION_TRADES} trades demo atingido. "
            "Novas ordens bloqueadas ate revisao humana."
        )

async def close_trade(contract_id, direction, group):
    start_time = time.time()
    
    # V6.0: Aguarda 0.8s para que o entry_spot seja fixado e evitar lucros fantasmas
    await asyncio.sleep(0.8)
    
    try:
        while True:
            # Polling do contrato para ler o lucro atual
            poll_res = await state["deriv_client"].send_request({"proposal_open_contract": 1, "contract_id": contract_id})
            
            if "proposal_open_contract" in poll_res and poll_res["proposal_open_contract"]:
                contract = poll_res["proposal_open_contract"]
                
                # Se o contrato já foi vendido (pela Deriv Stop Loss/Take Profit nativo)
                if contract.get("is_sold"):
                    profit = float(contract.get("profit", 0))
                    logger.info(f"✅ TRADE ENCERRADO AUTOMATICAMENTE! Lucro: ${profit:.2f} | Direção: {direction} | Grupo: {group}")
                    record_closed_trade(profit)
                    state["is_trading"] = False
                    return

                profit = float(contract.get("profit", 0))
                elapsed = time.time() - start_time
                
                # Rede de segurança apenas para recuperação de falhas (ex.: contrato nunca
                # settla por erro de API). NÃO deve disparar em operação normal — o SL/TP
                # nativo (limit_order enviado no buy_direct) sempre encerra o contrato antes
                # disso. Um timeout curto aqui força vendas a mercado num preço arbitrário,
                # que é justamente o que causava perdas maiores que a SL configurada.
                if elapsed > SAFETY_TIMEOUT:
                    logger.warning(f"⚠️ Rede de segurança acionada ({SAFETY_TIMEOUT:.0f}s sem is_sold). Forçando fechamento. Profit Atual: ${profit:.2f}")
                    break
            
            await asyncio.sleep(0.5)
            
    except Exception as e:
        logger.error(f"Erro ao monitorar contrato: {e}")

    logger.info(f"💥 ENVIANDO ORDEM DE FECHAMENTO (SELL) - {contract_id}")
    try:
        while True:
            sell_res = await state["deriv_client"].sell_contract(contract_id)
            if "error" in sell_res:
                if "Waiting for entry tick" in sell_res["error"]["message"] or "InvalidContractProposal" in sell_res["error"]["code"]:
                    await asyncio.sleep(0.05)
                    continue
                else:
                    logger.warning(f"❌ Erro ao fechar contrato: {sell_res['error']['message']}")
                    break
            else:
                profit = float(sell_res["sell"]["sold_for"]) - STAKE
                sold_for = float(sell_res["sell"]["sold_for"])
                logger.info(f"✅ TRADE ENCERRADO! Retorno: ${sold_for:.2f} | Lucro: ${profit:.2f} | Direção: {direction} | Grupo: {group}")
                record_closed_trade(profit)
                break
    except Exception as e:
        logger.error(f"Erro no fechamento agressivo: {e}")
        
    state["is_trading"] = False
    logger.info("🤖 Sniper recarregado e pronto para o próximo tiro.")

async def execute_trade(direction, price_shock_amount, elapsed_ms):
    if state["halted"]:
        logger.warning("Bot em estado halted; ordem ignorada.")
        return

    if state["is_trading"]:
        return
        
    state["is_trading"] = True

    # direction (UP/DOWN) e o sentido do choque observado -- preservado intacto para log/auditoria.
    aligned_contract = "MULTUP" if direction == "UP" else "MULTDOWN"
    if SHADOW_AB_TESTING and random.random() < SHADOW_AB_ANTI_PROB:
        group = "ANTI"
        contract_type = "MULTDOWN" if aligned_contract == "MULTUP" else "MULTUP"
    else:
        group = "ALIGNED"
        contract_type = aligned_contract

    logger.info(f"⚡ GATILHO ACIONADO! Direção: {direction} | Grupo: {group} | Ordem: {contract_type} | Salto: {price_shock_amount:.2f} em {elapsed_ms:.0f}ms")
    start_time = time.time()
    
    try:
        res = await state["deriv_client"].buy_direct(
            contract_type=contract_type,
            stake=STAKE,
            symbol=DERIV_SYMBOL,
            multiplier=MULTIPLIER,
            take_profit=round(STAKE * TAKE_PROFIT_PCT, 2),
            stop_loss=round(STAKE * STOP_LOSS_PCT, 2)
        )
        end_time = time.time()
        exec_time = (end_time - start_time) * 1000
        
        if "error" in res:
            logger.warning(f"❌ Ordem rejeitada: {res['error']['message']}")
            state["is_trading"] = False
        else:
            contract_id = res["buy"]["contract_id"]
            buy_price = float(res["buy"]["buy_price"])
            logger.info(f"✅ ORDEM EXECUTADA! ID: {contract_id} | Execution Time: {exec_time:.0f}ms | Stake: ${buy_price:.2f}")
            
            # Chama a liquidação em background sem travar
            asyncio.create_task(close_trade(contract_id, direction, group))
            
    except Exception as e:
        logger.error(f"Erro no envio da ordem: {e}")
        state["is_trading"] = False

async def deriv_tick_sync():
    """Worker dedicado para sincronizar o relógio local com os Ticks de 1s da Deriv."""
    uri = f"wss://api.derivws.com/trading/v1/options/ws/public"
    
    while True:
        try:
            async with websockets.connect(uri) as ws:
                req = {"ticks": DERIV_SYMBOL}
                await ws.send(json.dumps(req))
                logger.info("⏱️ Deriv Tick Sync conectado (Raw WS)...")
                
                async for message in ws:
                    res = json.loads(message)
                    if 'tick' in res:
                        state["last_deriv_tick_time"] = time.time()
        except Exception as e:
            logger.error(f"Erro no Tick Sync WS: {e}")
            await asyncio.sleep(2)

async def update_synthetic_price():
    if not all(global_prices.values()):
        return

    if state["halted"]:
        return
    
    # Calcula o índice sintético com a fórmula da regressão (R2=0.928)
    synthetic_price = (0.3874 * global_prices["binance"]) + \
                      (0.5338 * global_prices["coinbase"]) + \
                      (0.0266 * global_prices["kraken"]) + \
                      3152.82
                      
    if state["is_trading"]:
        return
        
    local_time = time.time()
    state["price_history"].append({"t": local_time, "p": synthetic_price})
    
    # Mantém apenas a janela de formação do salto (filtro de velocidade)
    state["price_history"] = [x for x in state["price_history"] if local_time - x["t"] <= JUMP_FORMATION_WINDOW]
    
    if len(state["price_history"]) >= 2:
        oldest = state["price_history"][0]
        diff = synthetic_price - oldest["p"]
        formation_time = local_time - oldest["t"]
        
        if abs(diff) >= PRICE_SHOCK_THRESHOLD:
            t_0 = local_time
            t_next_tick = state["last_deriv_tick_time"] + 1.000
            
            L_DERIV = 0.350
            DERIV_LAG = 0.690
            
            cond_arrive_early = (t_0 + L_DERIV) < t_next_tick
            cond_tick_before_jump = t_next_tick < (t_0 + DERIV_LAG)
            
            if cond_arrive_early and cond_tick_before_jump:
                if not is_golden_hour():
                    logger.info(f"⏱️ Salto de {diff:.2f} detectado fora do horário de ouro (UTC {datetime.now(timezone.utc).strftime('%H:%M')}) — ignorado.")
                    state["price_history"].clear()
                    return
                # TREND FOLLOWER (Momentum) com filtro de velocidade
                direction = "UP" if diff > 0 else "DOWN"
                logger.info(f"🎯 FASE ALINHADA! Pulo Sintético Global de {diff:.2f} formado em {formation_time*1000:.0f}ms. Disparando {direction} (Momentum)!")
                await execute_trade(direction, diff, formation_time * 1000)
                state["price_history"].clear()
            else:
                # Diagnostico (2026-07-02): choque passou do threshold mas falhou no gate de
                # timing (arrival vs proximo tick da Deriv) -- antes disso era ignorado em
                # silencio, impossivel distinguir "mercado quieto" de "gate rejeitando tudo".
                # So log, nao muda nenhuma logica/estado de trade.
                logger.info(f"👀 Salto de {diff:.2f} passou do threshold mas falhou no gate de timing (arrive_early={cond_arrive_early}, tick_before_jump={cond_tick_before_jump}) — ignorado, sem disparo.")

async def binance_ws():
    uri = f"wss://stream.binance.com:9443/ws/{BINANCE_SYMBOL}@bookTicker"
    logger.info("Conectando à Binance...")
    while True:
        try:
            async with websockets.connect(uri) as ws:
                logger.info("✅ Binance Conectado!")
                async for msg in ws:
                    data = json.loads(msg)
                    global_prices["binance"] = float(data['a'])
                    await update_synthetic_price()
        except Exception as e:
            logger.error(f"Erro Binance WS: {e}. Reconectando...")
            await asyncio.sleep(2)

async def coinbase_ws():
    uri = "wss://ws-feed.exchange.coinbase.com"
    logger.info("Conectando à Coinbase...")
    while True:
        try:
            async with websockets.connect(uri) as ws:
                await ws.send(json.dumps({
                    "type": "subscribe",
                    "product_ids": ["BTC-USD"],
                    "channels": ["ticker"]
                }))
                logger.info("✅ Coinbase Conectado!")
                async for msg in ws:
                    data = json.loads(msg)
                    if data.get("type") == "ticker" and "best_ask" in data:
                        global_prices["coinbase"] = float(data["best_ask"])
                        await update_synthetic_price()
        except Exception as e:
            logger.error(f"Erro Coinbase WS: {e}. Reconectando...")
            await asyncio.sleep(2)

async def kraken_ws():
    uri = "wss://ws.kraken.com"
    logger.info("Conectando à Kraken...")
    while True:
        try:
            async with websockets.connect(uri) as ws:
                await ws.send(json.dumps({
                    "event": "subscribe",
                    "pair": ["XBT/USD"],
                    "subscription": {"name": "ticker"}
                }))
                logger.info("✅ Kraken Conectado!")
                async for msg in ws:
                    data = json.loads(msg)
                    if isinstance(data, list) and len(data) > 1:
                        ticker_data = data[1]
                        if "a" in ticker_data:
                            global_prices["kraken"] = float(ticker_data["a"][0])
                            await update_synthetic_price()
        except Exception as e:
            logger.error(f"Erro Kraken WS: {e}. Reconectando...")
            await asyncio.sleep(2)

async def main():
    logger.info("🚀 INICIANDO BOT HFT - ARBITRAGEM SINTÉTICA (V6.2 Ultra-Momentum + Filtro de Velocidade + Horário de Ouro)")
    logger.info(
        f"Guardrails demo: max_loss=${MAX_DEMO_LOSS_USD:.2f}, "
        f"max_trades={MAX_SESSION_TRADES}, use_demo=True"
    )

    client = DerivClient(app_id=DERIV_APP_ID, api_token=DERIV_API_TOKEN, use_demo=True)
    await client.connect()
    if not str(client.account_id or "").startswith("DOT"):
        logger.critical(f"ABORTANDO: conta autenticada nao parece DEMO/DOT: {client.account_id}")
        await client.disconnect()
        return
    state["deriv_client"] = client
    
    # Inicia as tasks em background

    asyncio.create_task(deriv_tick_sync())
    await asyncio.sleep(2) # Espera as proposals chegarem
    
    logger.info("Vigiando Price Shocks no Índice Sintético da Deriv...")
    # Inicia os WebSockets do Índice Sintético
    await asyncio.gather(
        binance_ws(),
        coinbase_ws(),
        kraken_ws()
    )

if __name__ == "__main__":
    asyncio.run(main())
