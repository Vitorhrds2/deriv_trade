import asyncio
import logging
from deriv_client import DerivClient

logging.basicConfig(level=logging.INFO)

async def main():
    client = DerivClient()
    await client.connect()
    try:
        res = await client.get_active_symbols()
        symbols = res.get("active_symbols", [])
        print(f"Total symbols: {len(symbols)}")
        for s in symbols[:10]:
            print(f"Symbol: {s['symbol']} - {s['display_name']} - Market: {s['market']}")
            
        # Puxar contratos de um symbol específico para ver o que existe
        res_contracts = await client.send_request({
            "contracts_for": "1HZ10V"
        })
        
        contracts = res_contracts.get("contracts_for", {}).get("available", [])
        categories = set(c["contract_category"] for c in contracts)
        print(f"\nAvailable categories for 1HZ10V: {categories}")
        
    finally:
        await client.disconnect()

asyncio.run(main())
