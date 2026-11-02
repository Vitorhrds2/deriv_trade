import asyncio
import os
import sys
import json
import time

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
    
    # 1. Get proposal for ONETOUCH on RDBULL (barrier -2.0, 2m, stake $1.00)
    sym = 'RDBULL'
    barrier = '-2.0'
    stake = 1.00
    
    print(f"\n1. Requesting proposal for {sym} ONETOUCH {barrier} (2m)...")
    prop = await client.send_request({
        'proposal': 1,
        'amount': stake,
        'basis': 'stake',
        'contract_type': 'ONETOUCH',
        'currency': 'USD',
        'underlying_symbol': sym,
        'duration': 2,
        'duration_unit': 'm',
        'barrier': barrier
    })
    
    if 'error' in prop:
        print("Proposal error:", prop['error'])
        if client.ws:
            await client.ws.close()
        return
        
    p = prop['proposal']
    prop_id = p['id']
    ask_price = float(p['ask_price'])
    payout = float(p['payout'])
    print(f"Proposal ID: {prop_id} | Ask Price: ${ask_price} | Payout: ${payout} | Spot: {p.get('spot')}")
    
    # 2. Buy contract on Demo
    print("\n2. Executing buy contract on Demo...")
    buy_resp = await client.buy_contract(prop_id, ask_price)
    if 'error' in buy_resp:
        print("Buy error:", buy_resp['error'])
        if client.ws:
            await client.ws.close()
        return
        
    b = buy_resp['buy']
    contract_id = b['contract_id']
    buy_price = b['buy_price']
    print(f"Contract bought! ID: {contract_id} | Buy Price: ${buy_price}")
    
    # 3. Track contract via proposal_open_contract until expiry / win
    print("\n3. Monitoring contract lifecycle tick by tick...")
    start_t = time.time()
    while time.time() - start_t < 140:
        poc = await client.send_request({
            'proposal_open_contract': 1,
            'contract_id': contract_id
        })
        c = poc.get('proposal_open_contract', {})
        status = c.get('status')
        is_sold = c.get('is_sold')
        profit = c.get('profit')
        current_spot = c.get('current_spot')
        entry_spot = c.get('entry_spot')
        barrier_val = c.get('barrier')
        date_expiry = c.get('date_expiry')
        
        remaining = (date_expiry - time.time()) if date_expiry else 0
        dist_to_barrier = (float(current_spot) - float(barrier_val)) if (current_spot and barrier_val) else None
        
        print(f"  [{time.time()-start_t:5.1f}s] Spot: {current_spot} | Entry: {entry_spot} | Barrier: {barrier_val} | Dist: {dist_to_barrier:+.4f} | Status: {status} | Profit: {profit}")
        
        if is_sold:
            print(f"\nContract closed! Final Status: {status} | Profit: ${profit}")
            break
            
        await asyncio.sleep(2.0)

    if client.ws:
        await client.ws.close()

if __name__ == '__main__':
    asyncio.run(main())
