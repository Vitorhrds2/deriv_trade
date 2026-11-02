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
    
    print("=== BOOM50 / CRASH50 MULTIPLIER PROPOSAL SCAN ===")
    for sym in ['BOOM50', 'CRASH50']:
        for ct in ['MULTUP', 'MULTDOWN']:
            for mult in [500, 1000, 2000, 4000]:
                # Test with cancellation
                prop_cancel = await client.send_request({
                    'proposal': 1,
                    'amount': 10.0,
                    'basis': 'stake',
                    'contract_type': ct,
                    'currency': 'USD',
                    'underlying_symbol': sym,
                    'multiplier': mult,
                    'cancellation': '5m'
                })
                # Test without cancellation
                prop_nocancel = await client.send_request({
                    'proposal': 1,
                    'amount': 10.0,
                    'basis': 'stake',
                    'contract_type': ct,
                    'currency': 'USD',
                    'underlying_symbol': sym,
                    'multiplier': mult
                })
                
                print(f"--- {sym} {ct} {mult}x ---")
                if 'error' not in prop_cancel:
                    p = prop_cancel['proposal']
                    print(f"  WITH 5m CANCEL: Ask=${p.get('ask_price')} | CancelFee=${p.get('cancellation', {}).get('ask_price')} | Comm=${p.get('commission')}")
                else:
                    print(f"  WITH 5m CANCEL: Error = {prop_cancel['error'].get('message')}")
                    
                if 'error' not in prop_nocancel:
                    p = prop_nocancel['proposal']
                    stopout = p.get('limit_order', {}).get('stop_out', {}).get('value')
                    spot = p.get('spot')
                    move_to_stop = (float(stopout) - float(spot)) if (stopout and spot) else None
                    pct_to_stop = (move_to_stop / float(spot) * 100) if (move_to_stop and spot) else None
                    print(f"  NO CANCEL: Ask=${p.get('ask_price')} | Comm=${p.get('commission')} | Spot={spot} | StopOut={stopout} (Dist: {move_to_stop:+.2f}, {pct_to_stop:+.4f}%)")
                else:
                    print(f"  NO CANCEL: Error = {prop_nocancel['error'].get('message')}")
                print()

    if client.ws:
        await client.ws.close()

if __name__ == '__main__':
    asyncio.run(main())
