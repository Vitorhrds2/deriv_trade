import asyncio
import json
import websockets
import os
from dotenv import load_dotenv
from deriv_client import DerivClient

load_dotenv()
DERIV_API_TOKEN = os.getenv("DERIV_API_TOKEN")
DERIV_APP_ID = os.getenv("DERIV_APP_ID")

async def main():
    client = DerivClient(app_id=DERIV_APP_ID, api_token=DERIV_API_TOKEN, use_demo=True)
    await client.connect()
    
    print("Getting UP proposal...")
    res_up = await client.get_proposal(contract_type="MULTUP", stake=10, symbol="cryBTCUSD", multiplier=800)
    proposal_id = res_up["proposal"]["id"]
    
    print("Buying contract...")
    buy_res = await client.buy_contract(proposal_id, 10)
    contract_id = buy_res["buy"]["contract_id"]
    print(f"Bought: {contract_id}")
    
    for _ in range(5):
        poll = await client.send_request({"proposal_open_contract": 1, "contract_id": contract_id})
        contract = poll.get("proposal_open_contract", {})
        print(f"Poll: entry_tick={contract.get('entry_tick')}, current_tick={contract.get('current_spot_time')}, profit={contract.get('profit')}, bid={contract.get('bid_price')}")
        await asyncio.sleep(0.5)
        
    print("Selling contract...")
    sell_res = await client.sell_contract(contract_id)
    print("Sell res:", sell_res.get("sell"))
    
    await client.disconnect()

asyncio.run(main())
