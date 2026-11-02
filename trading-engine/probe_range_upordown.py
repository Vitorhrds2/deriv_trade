import asyncio
import os
import sys

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from dotenv import load_dotenv
from deriv_client import DerivClient

load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env'))
token = os.getenv('DERIV_API_TOKEN')
app_id = os.getenv('DERIV_APP_ID')

async def main():
    client = DerivClient(app_id=app_id, api_token=token, use_demo=True)
    await client.connect()
    print("Connected to Deriv! Probing UPORDOWN and RANGE contracts on RDBULL and RDBEAR...")
    
    for sym in ['RDBULL', 'RDBEAR']:
        print(f"\n=======================================================")
        print(f"  PROBING UPORDOWN / RANGE ON {sym}")
        print(f"=======================================================")
        
        for ctype in ['UPORDOWN', 'RANGE', 'EXPIRYRANGE', 'EXPIRYMISS']:
            for b in [1.0, 1.5, 2.0]:
                prop = await client.send_request({
                    'proposal': 1,
                    'amount': 10.0,
                    'basis': 'stake',
                    'contract_type': ctype,
                    'currency': 'USD',
                    'underlying_symbol': sym,
                    'duration': 2,
                    'duration_unit': 'm',
                    'barrier': f"+{b:.1f}",
                    'barrier2': f"-{b:.1f}"
                })
                if 'error' in prop:
                    print(f"  [{sym}] {ctype} (±{b:.1f}): Error -> {prop['error'].get('message')}")
                else:
                    p = prop.get('proposal', {})
                    ask = float(p.get('ask_price', 0))
                    payout = float(p.get('payout', 0))
                    ratio = payout / ask if ask > 0 else 0
                    be_wr = (100.0 / ratio) if ratio > 0 else 0
                    print(f"  [{sym}] {ctype:<11} (±{b:.1f}): Ask=${ask} | Payout=${payout} (Ratio: {ratio:.3f}x, BE: {be_wr:.1f}%)")
                await asyncio.sleep(0.05)

    if client.ws:
        await client.ws.close()

if __name__ == '__main__':
    asyncio.run(main())
