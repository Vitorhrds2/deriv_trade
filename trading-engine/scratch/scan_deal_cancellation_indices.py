import asyncio
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from dotenv import load_dotenv
from deriv_client import DerivClient

load_dotenv()

async def scan():
    client = DerivClient(app_id=os.getenv('DERIV_APP_ID'), api_token=os.getenv('DERIV_API_TOKEN'), use_demo=True)
    await client.connect()
    symbols = ['1HZ10V', '1HZ25V', '1HZ50V', '1HZ75V', '1HZ100V', 'R_10', 'R_25', 'R_50', 'R_75', 'R_100']
    print(f"{'Symbol':<10} | {'Mult':<5} | {'Stake':<6} | {'Ask':<6} | {'CancelFee':<10} | {'Fee%':<6}")
    print('-'*60)
    for s in symbols:
        for mult in [100, 200, 400, 500, 1000]:
            req = {
                'proposal': 1,
                'amount': 1.0,
                'basis': 'stake',
                'contract_type': 'MULTUP',
                'currency': 'USD',
                'underlying_symbol': s,
                'multiplier': mult,
                'cancellation': '5m',
            }
            res = await client.send_request(req)
            if 'error' in res:
                continue
            p = res.get('proposal', {})
            cancel = p.get('cancellation', {})
            c_fee = cancel.get('ask_price')
            ask = p.get('ask_price')
            fee_pct = (c_fee / 1.0 * 100) if c_fee else 0
            print(f"{s:<10} | {mult:<5} | $1.00  | ${ask:<5} | ${c_fee:<9} | {fee_pct:>5.1f}%")
    await client.disconnect()

if __name__ == '__main__':
    asyncio.run(scan())
