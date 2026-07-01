import asyncio
import json
import os
from dotenv import load_dotenv
from deriv_client import DerivClient

load_dotenv()
async def check():
    client = DerivClient(os.getenv("DERIV_APP_ID"), os.getenv("DERIV_API_TOKEN"))
    await client.connect()
    
    res = await client.send_request({"active_symbols": "brief", "product_type": "basic"})
    symbols = res.get("active_symbols", [])
    
    fast_real_markets = []
    
    for s in symbols:
        sym = s["symbol"]
        market = s["market"]
        if market == "synthetic_index": continue # ignore synthetic
        
        # print(f"Checking {sym} ({market})...")
        c_res = await client.send_request({"contracts_for": sym})
        contracts = c_res.get("contracts_for", {}).get("available", [])
        
        has_tick = False
        for c in contracts:
            if "t" in str(c.get("min_contract_duration", "")):
                has_tick = True
                break
        
        if has_tick:
            fast_real_markets.append(sym)
            print(f"Found tick market: {sym}")
            
    print(f"Real markets with tick options: {fast_real_markets}")
    await client.disconnect()

asyncio.run(check())
