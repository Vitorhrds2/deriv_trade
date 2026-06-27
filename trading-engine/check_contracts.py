import asyncio
import os
import json
from dotenv import load_dotenv
from deriv_client import DerivClient

load_dotenv()
DERIV_API_TOKEN = os.getenv("DERIV_API_TOKEN")
DERIV_APP_ID = os.getenv("DERIV_APP_ID")

async def test():
    client = DerivClient(app_id=DERIV_APP_ID, api_token=DERIV_API_TOKEN, use_demo=True)
    await client.connect()
    
    res = await client.send_request({
        "contracts_for": "cryBTCUSD"
    })
    
    with open("cryBTCUSD_contracts.json", "w") as f:
        json.dump(res, f, indent=4)
        
    await client.disconnect()

if __name__ == "__main__":
    asyncio.run(test())
