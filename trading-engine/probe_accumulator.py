"""
Probe read-only (nenhuma ordem enviada) para descobrir a estrutura real da resposta
`proposal` de um contrato ACCU (Accumulator) na Deriv: barreira efetiva por growth_rate,
payout, e campos disponiveis. Necessario porque Accumulators nunca foram testados neste
ecossistema -- precisamos dos numeros REAIS da API antes de desenhar o teste de edge.
"""
import asyncio
import os
import json
from dotenv import load_dotenv
from deriv_client import DerivClient

load_dotenv()
APP_ID = os.getenv("DERIV_APP_ID")
TOKEN = os.getenv("DERIV_API_TOKEN")

SYMBOLS = ["R_100", "R_50", "R_10", "1HZ100V"]
GROWTH_RATES = [0.01, 0.02, 0.03, 0.04, 0.05]


async def main():
    client = DerivClient(app_id=APP_ID, api_token=TOKEN, use_demo=True)
    await client.connect()

    for symbol in SYMBOLS:
        print(f"\n{'='*60}\n{symbol} — contracts_for\n{'='*60}")
        cf = await client.get_contracts_for(symbol)
        if "error" in cf:
            print(f"ERRO: {cf['error']['message']}")
            continue
        accu_specs = [c for c in cf.get("contracts_for", {}).get("available", []) if c.get("contract_type") == "ACCU"]
        if accu_specs:
            print(json.dumps(accu_specs[0], indent=2, ensure_ascii=False))
        else:
            print("Nenhum contrato ACCU disponivel para este simbolo.")
            continue

        for gr in GROWTH_RATES:
            res = await client.get_proposal("ACCU", stake=10.0, symbol=symbol, growth_rate=gr)
            if "error" in res:
                print(f"  growth_rate={gr}: ERRO {res['error']['message']}")
                continue
            p = res.get("proposal", {})
            print(f"  growth_rate={gr}: payout={p.get('payout')} ask_price={p.get('ask_price')} "
                  f"barrier={p.get('barrier')} high_barrier={p.get('high_barrier')} low_barrier={p.get('low_barrier')} "
                  f"contract_details={p.get('contract_details')}")
            # imprime a resposta bruta completa da 1a vez para inspecionar TODOS os campos
            if gr == GROWTH_RATES[0]:
                print("  RESPOSTA BRUTA COMPLETA:")
                print(" ", json.dumps(p, indent=2, ensure_ascii=False)[:2000])

    await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
