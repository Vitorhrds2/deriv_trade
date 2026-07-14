import asyncio, os, json
from dotenv import load_dotenv
load_dotenv('.env')
from deriv_client import DerivClient

async def main():
    c = DerivClient(app_id=os.getenv('DERIV_APP_ID'), api_token=os.getenv('DERIV_API_TOKEN'), use_demo=True)
    await c.connect()
    for mult in [100, 200]:
        res = await c.send_request({
            'proposal': 1, 'amount': 1.0, 'basis': 'stake', 'currency': 'USD',
            'contract_type': 'MULTDOWN', 'underlying_symbol': '1HZ100V',
            'multiplier': mult, 'cancellation': '5m'
        })
        print(json.dumps(res, indent=2, default=str))
    await c.disconnect()

if __name__ == '__main__':
    asyncio.run(main())
