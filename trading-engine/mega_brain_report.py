import asyncio
import os
import logging
from dotenv import load_dotenv
from deriv_client import DerivClient

logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger("REPORT")

load_dotenv()
DERIV_API_TOKEN = os.getenv("DERIV_API_TOKEN")
DERIV_APP_ID = os.getenv("DERIV_APP_ID")

async def generate_report():
    logger.info("📊 Inicializando Gerador de Relatórios do Mega Brain...")
    
    if not DERIV_API_TOKEN or not DERIV_APP_ID:
        logger.error("Credenciais da Deriv ausentes no .env")
        return
        
    client = DerivClient(app_id=DERIV_APP_ID, api_token=DERIV_API_TOKEN, use_demo=True)
    
    try:
        await client.connect()
        logger.info("✅ Conectado à conta Demo.")
        
        # Puxar a tabela de lucros
        # Limitamos a 50 para pegar os testes mais recentes
        res = await client.send_request({
            "profit_table": 1,
            "description": 1,
            "limit": 50,
            "sort": "DESC"
        })
        
        if "error" in res:
            logger.error(f"❌ Erro ao buscar Profit Table: {res['error']['message']}")
            return
            
        transactions = res.get("profit_table", {}).get("transactions", [])
        
        if not transactions:
            logger.info("Nenhuma transação encontrada no histórico recente.")
            return
            
        logger.info("\n=======================================================")
        logger.info("              MEGA BRAIN - ÚLTIMOS 50 TRADES            ")
        logger.info("=======================================================\n")
        
        total_pnl = 0.0
        straddle_pnl = 0.0
        straddle_trades = 0
        latency_pnl = 0.0
        latency_trades = 0
        oracle_pnl = 0.0
        oracle_trades = 0
        rng_pnl = 0.0
        rng_trades = 0
        forex_ob_pnl = 0.0
        forex_ob_trades = 0
        other_pnl = 0.0
        
        logger.info(f"{'ID Contrato':<15} | {'Tipo':<15} | {'Compra ($)':<10} | {'Venda ($)':<10} | {'Lucro/Perda ($)':<15}")
        logger.info("-" * 75)
        
        for t in transactions:
            c_id = str(t.get("contract_id"))
            c_type = t.get("shortcode", "").split('_')[0]
            shortcode = t.get("shortcode", "")
            buy_price = float(t.get("buy_price", 0))
            sell_price = float(t.get("sell_price", 0))
            pnl = sell_price - buy_price
            
            total_pnl += pnl
            
            # Classificação por ativo no shortcode
            if "cryBTCUSD" in shortcode:
                latency_pnl += pnl
                latency_trades += 1
                c_type = f"{c_type} (LAT)"
            elif "1HZ10V" in shortcode and ("MULTUP" in c_type or "MULTDOWN" in c_type):
                straddle_pnl += pnl
                straddle_trades += 1
                c_type = f"{c_type} (STR)"
            elif "1HZ10V" in shortcode and c_type in ["DIGITMATCH", "DIGITEVEN", "DIGITODD", "DIGITOVER", "DIGITUNDER"]:
                oracle_pnl += pnl
                oracle_trades += 1
                c_type = f"{c_type} (ORC)"
            elif "1HZ10V" in shortcode and c_type in ["CALL", "PUT"]:
                rng_pnl += pnl
                rng_trades += 1
                c_type = f"{c_type} (RNG)"
            elif "frxEURUSD" in shortcode:
                forex_ob_pnl += pnl
                forex_ob_trades += 1
                c_type = f"{c_type} (FX_OB)"
            else:
                other_pnl += pnl
                
            pnl_str = f"+{pnl:.2f}" if pnl > 0 else f"{pnl:.2f}"
            logger.info(f"{c_id:<15} | {c_type:<15} | {buy_price:<10.2f} | {sell_price:<10.2f} | {pnl_str:<15}")
            
        logger.info("\n=======================================================")
        logger.info("                    RESUMO DE PERFORMANCE               ")
        logger.info("=======================================================\n")
        logger.info(f"Total de Trades Analisados: {len(transactions)}")
        logger.info(f"Total PnL Líquido: ${total_pnl:.2f}\n")
        
        logger.info(f"🧠 ORACLE DEEP LEARNING (V1)")
        logger.info(f"   Trades Fechados: {oracle_trades}")
        logger.info(f"   PnL Líquido: ${oracle_pnl:.2f}\n")

        logger.info(f"🎯 RNG MOMENTUM SNIPER (V1)")
        logger.info(f"   Trades Fechados: {rng_trades}")
        logger.info(f"   PnL Líquido: ${rng_pnl:.2f}\n")

        logger.info(f"📈 FOREX ORDER BLOCK (V1)")
        logger.info(f"   Trades Fechados: {forex_ob_trades}")
        logger.info(f"   PnL Líquido: ${forex_ob_pnl:.2f}\n")
        
        logger.info(f"💥 STRADDLE MULTIPLIERS (Exploit 2)")
        logger.info(f"   Trades Fechados: {straddle_trades}")
        logger.info(f"   PnL Líquido: ${straddle_pnl:.2f}\n")
        
        logger.info(f"⚡ LATENCY ARBITRAGE (Exploit 1)")
        logger.info(f"   Trades Fechados: {latency_trades}")
        logger.info(f"   PnL Líquido: ${latency_pnl:.2f}\n")
        
        logger.info(f"🔮 OUTROS BOTS")
        logger.info(f"   PnL Líquido: ${other_pnl:.2f}")
        logger.info("=======================================================\n")
        
    except Exception as e:
        logger.error(f"Erro ao gerar relatório: {e}")
    finally:
        await client.disconnect()

if __name__ == "__main__":
    asyncio.run(generate_report())
