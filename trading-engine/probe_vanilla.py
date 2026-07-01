"""
Probe read-only para Vanilla Options (VANILLALONGCALL/PUT) -- produto nunca testado neste
ecossistema. Opcionalidade real (payoff convexo), diferente de tudo ja testado (binario/barreira
fixa). Precisamos ver os campos reais da API antes de desenhar o teste de mispricing.
"""
import asyncio
import os
import json
from dotenv import load_dotenv
from deriv_client import DerivClient

load_dotenv()
APP_ID = os.getenv("DERIV_APP_ID")
TOKEN = os.getenv("DERIV_API_TOKEN")

SYMBOL = "1HZ100V"
DURATIONS = [("15", "m"), ("1", "h")]


async def main():
    client = DerivClient(app_id=APP_ID, api_token=TOKEN, use_demo=True)
    await client.connect()

    cf = await client.get_contracts_for(SYMBOL)
    vanilla_specs = [c for c in cf.get("contracts_for", {}).get("available", [])
                      if "VANILLA" in c.get("contract_type", "")]
    print(f"Especificacoes VANILLA disponiveis para {SYMBOL}:")
    for spec in vanilla_specs[:4]:
        print(json.dumps(spec, indent=2, ensure_ascii=False))

    for duration, unit in DURATIONS:
        print(f"\n{'='*60}\nDuration={duration}{unit}\n{'='*60}")
        payload_base = {
            "proposal": 1, "amount": 10.0, "basis": "stake",
            "contract_type": "VANILLALONGCALL", "currency": "USD",
            "underlying_symbol": SYMBOL, "duration": duration, "duration_unit": unit,
        }
        # tenta barrier "+0.00" (ATM) primeiro pra ver os campos
        res = await client.send_request({**payload_base, "barrier": "+0.00"})
        if "error" in res:
            print(f"ERRO barrier +0.00: {res['error']['message']}")
        else:
            print("RESPOSTA BRUTA (ATM, barrier=+0.00):")
            print(json.dumps(res.get("proposal", {}), indent=2, ensure_ascii=False)[:1800])

    await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
