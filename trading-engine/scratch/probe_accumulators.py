import asyncio
import os
import sys
import json

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from dotenv import load_dotenv
from deriv_client import DerivClient

load_dotenv()

async def probe_accumulators():
    client = DerivClient(app_id=os.getenv('DERIV_APP_ID'), api_token=os.getenv('DERIV_API_TOKEN'), use_demo=True)
    await client.connect()
    
    symbols = ['1HZ10V', '1HZ25V', '1HZ50V', '1HZ100V', 'R_10', 'R_100']
    growth_rates = [0.01, 0.02, 0.03, 0.04, 0.05]
    
    print(f"{'Symbol':<10} | {'GrowthRate':<10} | {'Stake':<6} | {'AskPrice':<8} | {'Barrier':<10} | {'HighBarrier':<12} | {'LowBarrier':<12}")
    print('-'*80)
    for s in symbols:
        for gr in growth_rates:
            req = {
                'proposal': 1,
                'amount': 1.0,
                'basis': 'stake',
                'contract_type': 'ACCU',
                'currency': 'USD',
                'underlying_symbol': s,
                'growth_rate': gr,
            }
            res = await client.send_request(req)
            if 'error' in res:
                # print(s, gr, res['error']['message'])
                continue
            p = res.get('proposal', {})
            ask = p.get('ask_price')
            b = p.get('barrier')
            hb = p.get('high_barrier')
            lb = p.get('low_barrier')
            print(f"{s:<10} | {gr*100:>8.1f}% | $1.00  | ${ask:<7} | {str(b):<10} | {str(hb):<12} | {str(lb):<12}")
            
    await client.disconnect()

if __name__ == '__main__':
    asyncio.run(probe_accumulators())
