#!/usr/bin/env python3
"""Quick test to check if Deriv API rate limit is still active."""
import asyncio, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from deriv_client import DerivClient

async def test():
    token = os.getenv("DERIV_API_TOKEN", "")
    if not token:
        with open(".env") as f:
            for line in f:
                if "DERIV_API_TOKEN" in line and "=" in line:
                    token = line.split("=", 1)[1].strip().strip('"')
                    break
    print(f"Token: {token[:8]}...")
    client = DerivClient(app_id="1089", api_token=token, use_demo=True)
    await client.connect()
    await asyncio.sleep(2)
    res = await client.send_request({
        "proposal": 1,
        "amount": 1.0,
        "basis": "stake",
        "contract_type": "CALL",
        "currency": "USD",
        "underlying_symbol": "1HZ10V",
        "duration": 5,
        "duration_unit": "t",
    })
    if "error" in res:
        print(f"ERROR: {res['error']['message']}")
    else:
        print(f"Proposal OK: ask={res['proposal']['ask_price']} payout={res['proposal']['payout']}")
    await client.disconnect()

asyncio.run(test())
