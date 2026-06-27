import os
import json
import asyncio
from dotenv import load_dotenv
from deriv_client import DerivClient

load_dotenv()
API_TOKEN = os.getenv("DERIV_API_TOKEN")
APP_ID = os.getenv("DERIV_APP_ID")

async def main():
    client = DerivClient(app_id=APP_ID, api_token=API_TOKEN, use_demo=True)
    await client.connect()
    
    req = {
        "profit_table": 1,
        "description": 1,
        "limit": 10
    }
    res = await client.send_request(req)
    
    if "error" in res:
        print(f"Erro ao buscar profit_table: {res['error']['message']}")
        return
        
    transactions = res['profit_table']['transactions']
    
    print("Últimos Trades na Deriv (Profit Table):")
    print("="*60)
    seen = set()
    for t in transactions:
        contract_id = t['contract_id']
        
        if contract_id in seen:
            continue
        seen.add(contract_id)
        
        c_req = {
            "proposal_open_contract": 1,
            "contract_id": contract_id
        }
        c_res = await client.send_request(c_req)
        if "error" not in c_res:
            contract = c_res['proposal_open_contract']
            entry_spot = contract.get('entry_spot')
            sell_spot = contract.get('sell_spot')
            profit = contract.get('profit')
            status = contract.get('status')
            
            if entry_spot and sell_spot:
                diff = float(sell_spot) - float(entry_spot)
                print(f"Contrato: {contract_id} | Status: {status}")
                print(f"Entry Spot: {entry_spot}")
                print(f"Sell Spot : {sell_spot}")
                print(f"Diferença Real (Deriv): ${diff:.2f}")
                print(f"Lucro: ${profit}")
                print("-" * 30)

if __name__ == "__main__":
    asyncio.run(main())
