import asyncio
import logging
import os
from dotenv import load_dotenv
from deriv_client import DerivClient

logging.basicConfig(level=logging.INFO, format='%(asctime)s - LAB:%(levelname)s:%(message)s')
logger = logging.getLogger("HYPOTHESIS_LAB")

load_dotenv()
API_TOKEN = os.getenv("DERIV_API_TOKEN")
APP_ID = os.getenv("DERIV_APP_ID")
SYMBOL = "1HZ10V"

class HypothesisLab:
    def __init__(self):
        self.client = DerivClient(app_id=APP_ID, api_token=API_TOKEN, use_demo=True)
        
    async def get_proposal_custom(self, payload):
        return await self.client.send_request(payload)

    async def test_hypothesis_1_digitmatch(self):
        logger.info("🧪 [HIPÓTESE 1] Testando Cobertura de DIGITMATCH (0 a 9)")
        stake = 10.00
        duration = 1
        duration_unit = "t"
        
        payloads = []
        for digit in range(10):
            payload = {
                "proposal": 1,
                "amount": stake,
                "basis": "stake",
                "contract_type": "DIGITMATCH",
                "currency": "USD",
                "underlying_symbol": SYMBOL,
                "duration": duration,
                "duration_unit": duration_unit,
                "barrier": str(digit)
            }
            payloads.append(self.get_proposal_custom(payload))
            
        results = await asyncio.gather(*payloads)
        
        payouts = {}
        for i, res in enumerate(results):
            if "error" in res:
                logger.error(f"Erro no dígito {i}: {res['error']['message']}")
                continue
            
            payout = float(res['proposal']['payout'])
            payouts[i] = payout
            
        if not payouts: return
            
        logger.info("📊 Payouts Brutos para os 10 dígitos (Aposta base: $10):")
        for digit, payout in payouts.items():
            logger.info(f"   Dígito {digit}: Recebe ${payout:.2f} (Lucro: +${payout - stake:.2f})")
            
        if len(payouts) == 10:
            avg_payout = sum(payouts.values()) / 10
            total_cost_9 = stake * 9
            
            logger.info("\n=== ANÁLISE DE ARBITRAGEM (Cobertura de 9 Dígitos) ===")
            logger.info(f"Custo total para comprar 9 contratos: ${total_cost_9:.2f}")
            logger.info(f"Retorno médio SE ACERTAR um deles (90% chance): ${avg_payout:.2f}")
            
            lucro_liquido_acerto = avg_payout - total_cost_9
            logger.info(f"LUCRO LÍQUIDO SE ACERTAR: ${lucro_liquido_acerto:.2f}")
            logger.info(f"LUCRO LÍQUIDO SE ERRAR (10% chance): -${total_cost_9:.2f}")
            
            ev = (0.90 * lucro_liquido_acerto) + (0.10 * -total_cost_9)
            logger.info(f"EXPECTATIVA MATEMÁTICA LÍQUIDA (EV): ${ev:.2f} por rodada")

    async def test_hypothesis_3_barriers(self):
        logger.info("\n🧪 [HIPÓTESE 3] Testando HIGHER/LOWER com Barreiras Opostas (Strangle Volátil)")
        stake = 10.00
        duration = 5 # Barreiras altas geralmente precisam de mais ticks para estourar
        duration_unit = "t"
        
        # Testaremos algumas barreiras para ver como a corretora precifica
        barriers_to_test = ["+0.10", "+0.20", "+0.40", "+0.80"]
        
        for b_up in barriers_to_test:
            b_down = "-" + b_up[1:]
            
            payload_call = {
                "proposal": 1, "amount": stake, "basis": "stake", "contract_type": "CALL",
                "currency": "USD", "underlying_symbol": SYMBOL, "duration": duration, "duration_unit": duration_unit,
                "barrier": b_up
            }
            payload_put = {
                "proposal": 1, "amount": stake, "basis": "stake", "contract_type": "PUT",
                "currency": "USD", "underlying_symbol": SYMBOL, "duration": duration, "duration_unit": duration_unit,
                "barrier": b_down
            }
            
            res_call, res_put = await asyncio.gather(
                self.get_proposal_custom(payload_call),
                self.get_proposal_custom(payload_put)
            )
            
            if "error" in res_call or "error" in res_put:
                err = res_call.get("error", res_put.get("error"))["message"]
                logger.error(f"Barreira {b_up}/{b_down} recusada: {err}")
                continue
                
            payout_call = float(res_call['proposal']['payout'])
            payout_put = float(res_put['proposal']['payout'])
            
            cost = stake * 2
            profit_if_up = payout_call - cost
            profit_if_down = payout_put - cost
            
            logger.info(f"Barreiras: Superior {b_up} / Inferior {b_down}")
            logger.info(f"   Payout Bruto -> Higher: ${payout_call:.2f} | Lower: ${payout_put:.2f}")
            logger.info(f"   Custo: ${cost:.2f} | PnL Líquido (UP): ${profit_if_up:+.2f} | PnL Líquido (DOWN): ${profit_if_down:+.2f}")
            
            if profit_if_up > 0 and profit_if_down > 0:
                logger.info("   🚨🚨 ARBITRAGEM GARANTIDA ENCONTRADA!!!")
                
    async def start(self):
        if not API_TOKEN or not APP_ID:
            logger.error("Credenciais ausentes no .env")
            return
            
        await self.client.connect()
        try:
            await self.test_hypothesis_1_digitmatch()
            await asyncio.sleep(2)
            await self.test_hypothesis_3_barriers()
        except Exception as e:
            logger.error(f"Erro crítico no lab: {e}")
        finally:
            await self.client.disconnect()

if __name__ == "__main__":
    lab = HypothesisLab()
    asyncio.run(lab.start())
