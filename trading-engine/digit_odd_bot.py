import asyncio
import logging
import time
import os
from dotenv import load_dotenv
from deriv_client import DerivClient
from datetime import datetime, timezone, timedelta

# Define GMT-3 timezone
GMT_MINUS_3 = timezone(timedelta(hours=-3))

class GMTMinus3Formatter(logging.Formatter):
    def formatTime(self, record, datefmt=None):
        dt = datetime.fromtimestamp(record.created, tz=GMT_MINUS_3)
        if datefmt:
            return dt.strftime(datefmt)
        return dt.isoformat()

formatter = GMTMinus3Formatter('%(asctime)s - DIGITODD:%(levelname)s:%(message)s', datefmt='%Y-%m-%d %H:%M:%S.%f')
file_handler = logging.FileHandler("digitodd.log")
file_handler.setFormatter(formatter)
stream_handler = logging.StreamHandler()
stream_handler.setFormatter(formatter)

logging.basicConfig(level=logging.INFO, handlers=[file_handler, stream_handler])
logger = logging.getLogger("DIGITODD")

load_dotenv()
DERIV_API_TOKEN = os.getenv("DERIV_API_TOKEN")
DERIV_APP_ID = os.getenv("DERIV_APP_ID")

# ===== CONFIGURAÇÃO =====
SYMBOL = "JD75"          # Maior viés ímpar (55.86%) e payout alto (195.31%)
STAKE = 1.00             # Stake por trade (conservador para validação)
GLOBAL_STOP_LOSS = -100  # Parar se perder $100 acumulado
TARGET_TRADES = 200      # Meta de trades para validação
PAUSE_BETWEEN = 1.5      # Segundos entre trades (evitar rate limit)
# =========================

state = {
    "total_profit": 0.0,
    "wins": 0,
    "losses": 0,
    "total_trades": 0,
    "start_time": 0,
    "current_payout_ratio": 0.0,
}

async def check_payout(client):
    """Verifica o payout atual antes de iniciar. Aborta se caiu abaixo de 190%."""
    res = await client.get_proposal(
        contract_type="DIGITODD",
        stake=STAKE,
        symbol=SYMBOL,
        duration=1,
        duration_unit="t"
    )
    if 'proposal' in res:
        payout = float(res['proposal']['payout'])
        ratio = payout / STAKE * 100
        state["current_payout_ratio"] = ratio
        logger.info(f"📋 Payout atual DIGITODD {SYMBOL}: ${payout:.2f} ({ratio:.2f}%)")
        if ratio < 190:
            logger.error(f"⛔ PAYOUT ABAIXO DE 190% ({ratio:.2f}%)! A Deriv pode ter ajustado. ABORTANDO.")
            return False
        return True
    else:
        logger.error(f"Erro ao consultar payout: {res.get('error', {}).get('message', '?')}")
        return False

async def run_bot():
    client = DerivClient(app_id=DERIV_APP_ID, api_token=DERIV_API_TOKEN, use_demo=True)

    logger.info("🚀 INICIANDO DIGIT ODD BOT (Exploit de Viés Ímpar)")
    logger.info(f"  Símbolo: {SYMBOL}")
    logger.info(f"  Stake: ${STAKE:.2f}")
    logger.info(f"  Stop Loss Global: ${GLOBAL_STOP_LOSS:.2f}")
    logger.info(f"  Meta de trades: {TARGET_TRADES}")

    try:
        await client.connect()
    except Exception as e:
        logger.error(f"Erro ao conectar: {e}")
        return

    await asyncio.sleep(1)

    # Verificação de segurança do payout
    if not await check_payout(client):
        await client.disconnect()
        return

    state["start_time"] = time.time()

    while state["total_trades"] < TARGET_TRADES:
        # Check stop loss
        if state["total_profit"] <= GLOBAL_STOP_LOSS:
            logger.error(f"⛔ STOP LOSS GLOBAL ATINGIDO! Prejuízo: ${state['total_profit']:.2f}")
            break

        # Compra DIGITODD
        try:
            res = await client.buy_direct(
                contract_type="DIGITODD",
                stake=STAKE,
                symbol=SYMBOL,
                duration=1,
                duration_unit="t"
            )

            if "error" in res:
                logger.warning(f"❌ Ordem rejeitada: {res['error']['message']}")
                await asyncio.sleep(3)
                continue

            contract_id = res["buy"]["contract_id"]
            buy_price = float(res["buy"]["buy_price"])

            # Espera resolução do contrato (1 tick ~2s)
            await asyncio.sleep(2)

            # Poll até o contrato fechar
            timeout = 10
            start_poll = time.time()
            profit = 0.0
            while time.time() - start_poll < timeout:
                poll_res = await client.send_request({
                    "proposal_open_contract": 1,
                    "contract_id": contract_id
                })
                if "proposal_open_contract" in poll_res:
                    contract = poll_res["proposal_open_contract"]
                    if contract.get("is_sold") or contract.get("is_settled"):
                        profit = float(contract.get("profit", 0))
                        break
                await asyncio.sleep(0.5)

            state["total_trades"] += 1
            state["total_profit"] += profit

            if profit > 0:
                state["wins"] += 1
                logger.info(f"✅ WIN  #{state['total_trades']:>4} | +${profit:.2f} | Acum: ${state['total_profit']:.2f} | WR: {state['wins']/state['total_trades']*100:.1f}%")
            else:
                state["losses"] += 1
                logger.info(f"❌ LOSS #{state['total_trades']:>4} | ${profit:.2f} | Acum: ${state['total_profit']:.2f} | WR: {state['wins']/state['total_trades']*100:.1f}%")

            # Stats a cada 25 trades
            if state["total_trades"] % 25 == 0:
                elapsed = time.time() - state["start_time"]
                trades_per_min = state["total_trades"] / (elapsed / 60) if elapsed > 0 else 0
                logger.info(f"📊 === CHECKPOINT {state['total_trades']}/{TARGET_TRADES} ===")
                logger.info(f"   Wins: {state['wins']} | Losses: {state['losses']} | Win Rate: {state['wins']/state['total_trades']*100:.2f}%")
                logger.info(f"   Lucro Acumulado: ${state['total_profit']:.2f}")
                logger.info(f"   Trades/min: {trades_per_min:.1f}")
                logger.info(f"   Tempo decorrido: {elapsed/60:.1f} min")

        except Exception as e:
            logger.error(f"Erro no trade: {e}")
            await asyncio.sleep(3)

        await asyncio.sleep(PAUSE_BETWEEN)

    # Relatório final
    elapsed = time.time() - state["start_time"]
    logger.info("=" * 60)
    logger.info("📊 RELATÓRIO FINAL")
    logger.info("=" * 60)
    logger.info(f"  Total de trades: {state['total_trades']}")
    logger.info(f"  Wins: {state['wins']}")
    logger.info(f"  Losses: {state['losses']}")
    logger.info(f"  Win Rate: {state['wins']/max(state['total_trades'],1)*100:.2f}%")
    logger.info(f"  Lucro Acumulado: ${state['total_profit']:.2f}")
    logger.info(f"  EV observado/trade: ${state['total_profit']/max(state['total_trades'],1):.4f}")
    logger.info(f"  Tempo total: {elapsed/60:.1f} min")
    logger.info(f"  Trades/min: {state['total_trades']/(elapsed/60) if elapsed > 0 else 0:.1f}")

    await client.disconnect()

if __name__ == "__main__":
    asyncio.run(run_bot())
