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
    print("Connected to Deriv! Checking active symbols and contracts...")

    # Fetch active symbols
    sym_resp = await client.get_active_symbols()
    
    symbols = sym_resp.get('active_symbols', [])
    print(f"Total active symbols returned: {len(symbols)}")
    
    # Filter synthetic indices
    synthetic_syms = [s for s in symbols if s.get('market') == 'synthetic_index']
    print(f"Synthetic index symbols: {len(synthetic_syms)}")
    
    touch_capable = []
    
    for s in synthetic_syms:
        sym = s['underlying_symbol']
        disp = s.get('underlying_symbol_name', sym)
        cf_resp = await client.send_request({
            'contracts_for': sym
        })
        if 'error' in cf_resp:
            continue
        c_list = cf_resp.get('contracts_for', {}).get('available', [])
        
        onetouch_contracts = [c for c in c_list if c.get('contract_type') == 'ONETOUCH']
        notouch_contracts = [c for c in c_list if c.get('contract_type') == 'NOTOUCH']
        
        if onetouch_contracts:
            c = onetouch_contracts[0]
            min_dur = c.get('min_contract_duration')
            max_dur = c.get('max_contract_duration')
            touch_capable.append({
                'symbol': sym,
                'name': disp,
                'min_duration': min_dur,
                'max_duration': max_dur,
                'barriers': c.get('barriers')
            })
            print(f"[{sym}] ({disp}): Min Duration = {min_dur} | Max = {max_dur} | Barriers = {c.get('barriers')}")
            
    print("\n--- Summary of Touch Capable Assets ---")
    for tc in touch_capable:
        print(f"Symbol: {tc['symbol']} ({tc['name']}) -> Min: {tc['min_duration']}, Max: {tc['max_duration']}")
        
    if client.ws:
        await client.ws.close()

if __name__ == '__main__':
    asyncio.run(main())
