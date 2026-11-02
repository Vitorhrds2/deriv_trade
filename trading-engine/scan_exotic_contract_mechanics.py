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
    print("Connected to Deriv! Auditing exotic contract categories across all active symbols...")
    
    # 1. Fetch all active symbols
    r_sym = await client.get_active_symbols()
    symbols = r_sym.get('active_symbols', [])
    print(f"Total symbols: {len(symbols)}")
    
    # Group by submarket
    submarkets = {}
    for s in symbols:
        sm = s.get('submarket', 'unknown')
        submarkets.setdefault(sm, []).append(s)
        
    print(f"Submarkets found: {list(submarkets.keys())}")
    for sm, slist in submarkets.items():
        print(f"  [{sm}] ({len(slist)} symbols): {[x['underlying_symbol'] for x in slist[:6]]}")

    # Inspect exotic contracts on representative symbols from each submarket
    target_symbols = [
        '1HZ10V', 'R_100', 'STPINDEX', 'BOOM50', 'CRASH50', 
        'JD10', 'JD100', 'RB100', 'RDBULL', 'RDBEAR',
        'frxEURUSD', 'cryBTCUSD'
    ]
    
    # Add any DEX symbols if they exist
    dex_syms = [s['underlying_symbol'] for s in symbols if 'DEX' in s['underlying_symbol']]
    print(f"DEX symbols found: {dex_syms}")
    target_symbols.extend(dex_syms)

    print("\n=======================================================")
    print("  EXOTIC CONTRACT AUDIT MATRIX")
    print("=======================================================")
    
    contract_types_catalog = {}
    
    for sym in target_symbols:
        cf = await client.send_request({'contracts_for': sym})
        avail = cf.get('contracts_for', {}).get('available', [])
        c_types = set(c.get('contract_type') for c in avail)
        contract_types_catalog[sym] = c_types
        print(f"Symbol {sym:<12}: {len(c_types)} contract types -> {sorted(list(c_types))[:8]}")
        
    # Check for interesting exotic contracts:
    # RESETCALL, RESETPUT, ASIANU, ASIAND, RUNHIGH, RUNLOW, TICKHIGH, TICKLOW, EXPIRYRANGE, EXPIRYMISS
    exotics = ['RESETCALL', 'RESETPUT', 'ASIANU', 'ASIAND', 'RUNHIGH', 'RUNLOW', 'TICKHIGH', 'TICKLOW', 'EXPIRYRANGE', 'EXPIRYMISS', 'ACCU']
    print("\n--- Support for Exotic Types ---")
    for ex in exotics:
        supporting = [s for s, types in contract_types_catalog.items() if ex in types]
        print(f"  {ex:<12}: Supported on {len(supporting)} symbols -> {supporting}")

    if client.ws:
        await client.ws.close()

if __name__ == '__main__':
    asyncio.run(main())
