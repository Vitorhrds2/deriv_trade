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
        for s in symbols[:1]:
            print(f"Symbol data: {s}")
            
        res_contracts = await client.send_request({
            "contracts_for": "1HZ10V"
        })
        
        contracts = res_contracts.get("contracts_for", {}).get("available", [])
        categories = set(c["contract_category"] for c in contracts)
        print(f"\nAvailable categories for 1HZ10V: {categories}")
        for c in contracts:
            if c["contract_category"] == "digits":
                print(f"Digit contract: {c['contract_type']} - Payout: {c.get('payout_dict', {})}")
                
    finally:
        await client.disconnect()

if __name__ == "__main__":
    asyncio.run(main())
