import asyncio
import logging
import os
import pandas as pd
from collections import defaultdict
from dotenv import load_dotenv
from deriv_client import DerivClient

logging.basicConfig(level=logging.INFO, format='%(asctime)s - RNG_ANALYZER:%(levelname)s:%(message)s')
logger = logging.getLogger("RNG_ANALYZER")

load_dotenv()
API_TOKEN = os.getenv("DERIV_API_TOKEN")
APP_ID = os.getenv("DERIV_APP_ID")
SYMBOL = "1HZ10V" # Volatility 10 (1s) Index

class RNGAnalyzer:
    def __init__(self):
        self.client = DerivClient(app_id=APP_ID, api_token=API_TOKEN, use_demo=True)
        
    async def get_raw_ticks(self, count=5000):
        """Puxa os ticks crus (não candles) para pegarmos os dígitos exatos"""
        return await self.client.send_request({
            "ticks_history": SYMBOL,
            "adjust_start_time": 1,
            "count": count,
            "end": "latest",
            "start": 1,
            "style": "ticks"
        })

    def extract_last_digit(self, price):
        # Volatility Indices geralmente operam com 2 ou 3 casas decimais (1HZ10V costuma ser 2).
        # Multiplicar por 100 e pegar o módulo nos dá o último dígito com segurança.
        return int(round(price * 100)) % 10

    async def start(self):
        if not API_TOKEN or not APP_ID:
            logger.error("Credenciais ausentes.")
            return
            
        await self.client.connect()
        try:
            logger.info("📡 Baixando os últimos 5.000 Ticks para análise profunda do RNG...")
            res = await self.get_raw_ticks(count=5000)
            
            if "error" in res:
                logger.error(f"Erro ao puxar ticks: {res['error']['message']}")
                return
                
            history = res.get("history", {})
            prices = history.get("prices", [])
            
            if not prices:
                logger.error("Nenhum preço retornado.")
                return
                
            logger.info(f"✅ {len(prices)} ticks extraídos com sucesso. Processando dígitos...")
            
            digits = [self.extract_last_digit(p) for p in prices]
            
            # Análise 1: Distribuição Simples
            freq = pd.Series(digits).value_counts(normalize=True).sort_index() * 100
            logger.info("\n=== DISTRIBUIÇÃO SIMPLES DOS DÍGITOS ===")
            for d, pct in freq.items():
                logger.info(f"Dígito {d}: {pct:.2f}% (Ideal: 10.00%)")
                
            # Análise 2: Cadeia de Markov (Probabilidade de Transição 1 Passo)
            # P(Dígito B sair, dado que o último foi A)
            transitions = defaultdict(lambda: defaultdict(int))
            for i in range(len(digits) - 1):
                current_d = digits[i]
                next_d = digits[i+1]
                transitions[current_d][next_d] += 1
                
            logger.info("\n=== CADEIA DE MARKOV (PROBABILIDADE CONDICIONAL) ===")
            logger.info("Qual é a chance de sair o dígito X logo após o dígito Y?")
            
            anomalies = []
            
            for current_d in range(10):
                total_transitions = sum(transitions[current_d].values())
                if total_transitions == 0: continue
                
                # Para cada dígito seguinte, calcula a porcentagem
                for next_d in range(10):
                    count = transitions[current_d][next_d]
                    pct = (count / total_transitions) * 100
                    
                    # Se for anormalmente baixo (menos que 7.5% em vez de 10%)
                    if pct < 7.5:
                        anomalies.append({
                            "condicao": f"Se sair {current_d}, apostar que NÃO sai {next_d}",
                            "chance_erro": pct,
                            "win_rate": 100 - pct
                        })
                        
            if anomalies:
                logger.info("\n🚨🚨 ANOMALIAS DE RNG DETECTADAS! (BRECHAS MATEMÁTICAS) 🚨🚨")
                # Ordena pela maior taxa de vitória
                anomalies.sort(key=lambda x: x["win_rate"], reverse=True)
                for a in anomalies:
                    logger.info(f"[WIN RATE ESPERADO: {a['win_rate']:.2f}%] -> {a['condicao']}")
            else:
                logger.info("\nNenhuma anomalia grave detectada na transição de 1 passo. O RNG parece perfeitamente distribuído.")

            # Análise 3: Repetições Seguidas (Streaks)
            streaks = []
            current_streak = 1
            for i in range(1, len(digits)):
                if digits[i] == digits[i-1]:
                    current_streak += 1
                else:
                    if current_streak > 1:
                        streaks.append(current_streak)
                    current_streak = 1
                    
            if streaks:
                max_streak = max(streaks)
                logger.info(f"\n📈 A maior sequência do mesmo dígito consecutivo foi: {max_streak} vezes seguidas.")
            
        except Exception as e:
            logger.error(f"Erro crítico na análise: {e}")
        finally:
            await self.client.disconnect()

if __name__ == "__main__":
    analyzer = RNGAnalyzer()
    asyncio.run(analyzer.start())
