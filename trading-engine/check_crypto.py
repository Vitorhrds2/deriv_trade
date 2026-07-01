import asyncio
import json
import os
from dotenv import load_dotenv
from deriv_client import DerivClient

load_dotenv()
async def check():
    client = DerivClient(os.getenv("DERIV_APP_ID"), os.getenv("DERIV_API_TOKEN"))
    await client.connect()
    
    res = await client.send_request({"contracts_for": "cryBTCUSD"})
    contracts = res.get("contracts_for", {}).get("available", [])
    
    for c in contracts:
        if c["contract_category"] in ["callput", "risefall"]:
            print(f"Type: {c['contract_type']}, Min: {c.get('min_contract_duration')}, Max: {c.get('max_contract_duration')}")
            
    await client.disconnect()

asyncio.run(check())
