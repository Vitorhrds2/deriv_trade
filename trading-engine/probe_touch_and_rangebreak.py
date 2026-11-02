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
    print("Connected! Account:", client.account_id)
    
    # 1. Inspect RDBEAR / RDBULL Touch options
    print("\n=== TOUCH OPTIONS ON RDBEAR / RDBULL ===")
    for sym in ['RDBEAR', 'RDBULL']:
        t_resp = await client.send_request({'ticks_history': sym, 'end': 'latest', 'count': 1, 'style': 'ticks'})
        spot = t_resp.get('history', {}).get('prices', [0])[0]
        print(f"\n{sym} current spot: {spot}")
        
        for b_offset in ['+0.5', '-0.5', '+1.0', '-1.0', '+2.0', '-2.0']:
            for ct in ['NOTOUCH', 'ONETOUCH']:
                prop = await client.send_request({
                    'proposal': 1,
                    'amount': 10.0,
                    'basis': 'stake',
                    'contract_type': ct,
                    'currency': 'USD',
                    'underlying_symbol': sym,
                    'duration': 2,
                    'duration_unit': 'm',
                    'barrier': b_offset
                })
                if 'error' not in prop:
                    p = prop['proposal']
                    payout = p.get('payout')
                    ask = p.get('ask_price')
                    ratio = payout / ask if (payout and ask) else 0
                    print(f"  {sym} {ct:8s} 2m offset {b_offset:5s}: Payout=${payout} Ask=${ask} Ratio={ratio:.4f}")
                else:
                    err_msg = prop['error'].get('message')
                    print(f"  {sym} {ct:8s} 2m offset {b_offset:5s}: Error = {err_msg}")

    # 2. Inspect Multiplier proposals on RB100 / RB200
    print("\n=== MULTIPLIER PROPOSALS ON RB100 / RB200 ===")
    for sym in ['RB100', 'RB200']:
        for ct in ['MULTUP', 'MULTDOWN']:
            for mult in [50, 100, 200, 400, 500, 1000]:
                prop = await client.send_request({
                    'proposal': 1,
                    'amount': 10.0,
                    'basis': 'stake',
                    'contract_type': ct,
                    'currency': 'USD',
                    'underlying_symbol': sym,
                    'multiplier': mult,
                    'cancellation': '5m'
                })
                if 'error' not in prop:
                    p = prop['proposal']
                    fee = p.get('cancellation', {}).get('ask_price')
                    comm = p.get('commission')
                    print(f"  {sym} {ct} {mult}x (5m cancel): fee=${fee} comm=${comm} ask=${p.get('ask_price')}")
                else:
                    # try without cancel
                    prop2 = await client.send_request({
                        'proposal': 1,
                        'amount': 10.0,
                        'basis': 'stake',
                        'contract_type': ct,
                        'currency': 'USD',
                        'underlying_symbol': sym,
                        'multiplier': mult
                    })
                    if 'error' not in prop2:
                        p2 = prop2['proposal']
                        comm = p2.get('commission')
                        stopout = p2.get('limit_order', {}).get('stop_out', {}).get('value')
                        print(f"  {sym} {ct} {mult}x (no cancel): comm=${comm} spot={p2.get('spot')} stopout={stopout}")
                    else:
                        print(f"  {sym} {ct} {mult}x: Error = {prop2['error'].get('message')}")

    if client.ws:
        await client.ws.close()

if __name__ == '__main__':
    asyncio.run(main())
