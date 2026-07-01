import asyncio
import json
import os
from dotenv import load_dotenv
from deriv_client import DerivClient

load_dotenv()
async def check():
    client = DerivClient(os.getenv("DERIV_APP_ID"), os.getenv("DERIV_API_TOKEN"))
    await client.connect()
    
    res = await client.buy_direct(
        contract_type="DIGITMATCH",
        stake=1.0,
        symbol="1HZ10V",
        duration=1,
        duration_unit="t",
        barrier=5
    )
    print("DIGITMATCH Response:", json.dumps(res, indent=2))
    
    res2 = await client.buy_direct(
        contract_type="DIGITODD",
        stake=1.0,
        symbol="1HZ10V",
        duration=1,
        duration_unit="t"
    )
    print("DIGITODD Response:", json.dumps(res2, indent=2))
    
    await client.disconnect()

asyncio.run(check())
