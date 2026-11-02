import asyncio
import os
import sys
import json

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from dotenv import load_dotenv
from deriv_client import DerivClient

load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env'))
token = os.getenv('DERIV_API_TOKEN')
app_id = os.getenv('DERIV_APP_ID')

async def main():
    client = DerivClient(app_id=app_id, api_token=token, use_demo=True)
    await client.connect()
    
    pt = await client.send_request({
        'profit_table': 1,
        'description': 1,
        'limit': 5
    })
    transactions = pt.get('profit_table', {}).get('transactions', [])
    print(f"Recent profit table transactions ({len(transactions)}):")
    for t in transactions:
        print(f"  ID: {t.get('contract_id')} | Shortcode: {t.get('shortcode')} | Profit: ${t.get('profit_loss')} | Sold for: ${t.get('sell_price')}")

    if client.ws:
        await client.ws.close()

if __name__ == '__main__':
    asyncio.run(main())
