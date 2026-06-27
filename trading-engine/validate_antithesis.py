import asyncio
import logging
import os
import pandas as pd
from collections import defaultdict
from dotenv import load_dotenv
from deriv_client import DerivClient

logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger("VALIDATOR")

load_dotenv()
API_TOKEN = os.getenv("DERIV_API_TOKEN")
APP_ID = os.getenv("DERIV_APP_ID")
SYMBOL = "1HZ10V"

class AntithesisValidator:
    def __init__(self):
        self.client = DerivClient(app_id=APP_ID, api_token=API_TOKEN, use_demo=True)
        
    def extract_last_digit(self, price):
        return int(round(price * 100)) % 10

    async def get_raw_ticks(self, count=5000):
        return await self.client.send_request({
            "ticks_history": SYMBOL,
            "adjust_start_time": 1,
            "count": count,
            "end": "latest",
            "start": 1,
            "style": "ticks"
        })

    async def run_validation(self):
        if not API_TOKEN or not APP_ID:
            logger.error("Credenciais ausentes no .env")
            return
            
        await self.client.connect()
        try:
            logger.info(f"=== INICIANDO EXPERIMENTO DE VALIDAÇÃO (TESE vs ANTÍTESE) ===")
            logger.info("Baixando 5000 ticks históricos para análise...")
            res = await self.get_raw_ticks(count=5000)
            prices = res.get("history", {}).get("prices", [])
            
            if not prices:
                logger.error("Falha ao puxar ticks.")
                return
                
            digits = [self.extract_last_digit(p) for p in prices]
            
            logger.info("Mapeando transições de dígitos e encontrando anomalias (< 6%)...")
            transitions = defaultdict(lambda: defaultdict(int))
            for i in range(len(digits) - 1):
                transitions[digits[i]][digits[i+1]] += 1
                
            anomalies = {}
            for current_d in range(10):
                total = sum(transitions[current_d].values())
                if total == 0: continue
                
                for next_d in range(10):
                    pct = (transitions[current_d][next_d] / total) * 100
                    if pct <= 6.0:
                        anomalies[current_d] = next_d
                        
            if not anomalies:
                logger.info("Nenhuma anomalia grave (<6%) encontrada nesta amostragem. Usando as mais raras.")
                for current_d in range(10):
                    total = sum(transitions[current_d].values())
                    if total == 0: continue
                    rarest_next = min(transitions[current_d], key=transitions[current_d].get)
                    anomalies[current_d] = rarest_next
                    logger.info(f"Anomalia mapeada: Após {current_d}, apostamos contra {rarest_next}.")
            else:
                for c, n in anomalies.items():
                    t = sum(transitions[c].values())
                    logger.info(f"Anomalia real mapeada: Após {c}, {n} sai apenas {(transitions[c][n]/t)*100:.2f}% das vezes.")
                    
            logger.info("\n=== RODANDO A SIMULAÇÃO RETROATIVA (5000 TICKS) ===")
            
            bot1_trades = 0
            bot1_losses = 0
            
            for i in range(len(digits) - 1):
                d1 = digits[i]
                d2 = digits[i+1]
                
                if d1 in anomalies:
                    target_diff = anomalies[d1]
                    bot1_trades += 1
                    if d2 == target_diff:
                        bot1_losses += 1
                        
            bot2_ready_for_trigger = {} # Mantém estado por dígito gatilho
            for d in range(10):
                bot2_ready_for_trigger[d] = False
                
            bot2_trades_real = 0
            bot2_losses_real = 0
            
            for i in range(1, len(digits) - 1):
                prev_d = digits[i-1]
                curr_d = digits[i]
                
                # Bot 2 atira (dinheiro real) se já estava armado para ESSE gatilho (prev_d)
                if prev_d in anomalies and bot2_ready_for_trigger[prev_d]:
                    target_diff = anomalies[prev_d]
                    bot2_trades_real += 1
                    if curr_d == target_diff:
                        bot2_losses_real += 1 # Cluster ocorreu! A Antítese ataca.
                    
                    # Desarma após o tiro (win ou loss)
                    bot2_ready_for_trigger[prev_d] = False
                    continue 

                # Armar sniper se ocorrer o Virtual Loss para esse gatilho
                if prev_d in anomalies and not bot2_ready_for_trigger[prev_d]:
                    target_diff = anomalies[prev_d]
                    if curr_d == target_diff:
                        # Ocorreu o erro. Armar!
                        bot2_ready_for_trigger[prev_d] = True
                    
            logger.info("\n=== RESULTADOS FINAIS ===")
            logger.info(f"[BOT 1 - Operação Contínua (Tiro Cego)]")
            logger.info(f"Total de Trades Simulados: {bot1_trades}")
            logger.info(f"Total de Losses Sofridos: {bot1_losses}")
            wr1 = ((bot1_trades - bot1_losses) / bot1_trades * 100) if bot1_trades > 0 else 0
            logger.info(f"Win Rate Prático (Sem Martingale): {wr1:.2f}%\n")
            
            logger.info(f"[BOT 2 - Espera Virtual Exata (Sniper)]")
            logger.info(f"Total de Tiros de Sniper Dados: {bot2_trades_real}")
            logger.info(f"Total de Losses (Clusters Fatais): {bot2_losses_real}")
            wr2 = ((bot2_trades_real - bot2_losses_real) / bot2_trades_real * 100) if bot2_trades_real > 0 else 0
            logger.info(f"Win Rate Prático (Após o Filtro): {wr2:.2f}%")
            
            logger.info("\n=== VEREDITO CIENTÍFICO DA ANTÍTESE ===")
            if wr2 < wr1:
                logger.info("❌ A Antítese estava CORRETA! O RNG agrupa os erros, e entrar após eles é perigoso.")
            elif wr2 == 100.0:
                logger.info("✅ A Tese é ABSOLUTA! O Bot 2 desviou de todas as falhas e obteve 100% nas operações que resolveu fazer.")
            elif wr2 > wr1:
                logger.info(f"✅ A Tese se COMPROVA PARCIALMENTE. O Virtual Loss evitou {bot1_losses - bot2_losses_real} perdas em relação ao Bot 1, subindo o WR de {wr1:.2f}% para {wr2:.2f}%.")
            else:
                logger.info("O filtro Virtual Loss não impactou estatisticamente as chances (WR iguais).")
                
        except Exception as e:
            logger.error(f"Erro fatal: {e}")
        finally:
            await self.client.disconnect()

if __name__ == "__main__":
    validator = AntithesisValidator()
    asyncio.run(validator.run_validation())
