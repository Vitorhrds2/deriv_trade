import asyncio
import json
import os
from dotenv import load_dotenv
from deriv_client import DerivClient

load_dotenv()
async def check():
    client = DerivClient(os.getenv("DERIV_APP_ID"), os.getenv("DERIV_API_TOKEN"))
    await client.connect()
    res = await client.send_request({"contracts_for": "1HZ10V"})
    contracts = res.get("contracts_for", {}).get("available", [])
    
    for c in contracts:
        if c["contract_category"] == "digits":
            print(f"Type: {c['contract_type']}, Min duration: {c['min_contract_duration']}, Max: {c['max_contract_duration']}")
    await client.disconnect()

asyncio.run(check())
