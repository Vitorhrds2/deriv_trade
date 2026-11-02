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
    print("Connected to Deriv! Auditing 3 new frontier hypotheses...")
    
    # -------------------------------------------------------------
    # Hypothesis 1: EXPIRYRANGE / EXPIRYMISS on RDBULL & RDBEAR
    # -------------------------------------------------------------
    print("\n=======================================================")
    print("  HYPOTHESIS 1: EXPIRYRANGE / EXPIRYMISS on RDBULL / RDBEAR")
    print("=======================================================")
    for sym in ['RDBULL', 'RDBEAR']:
        cf = await client.send_request({'contracts_for': sym})
        avail = cf.get('contracts_for', {}).get('available', [])
        range_contracts = [c for c in avail if c.get('contract_type') in ['EXPIRYRANGE', 'EXPIRYMISS', 'RANGE', 'UPORDOWN']]
        print(f"[{sym}] Range contract types available: {[c['contract_type'] for c in range_contracts]}")
        for c in range_contracts:
            print(f"  Type: {c['contract_type']} | Min Dur: {c.get('min_contract_duration')} | Max Dur: {c.get('max_contract_duration')} | Barriers: {c.get('barriers')}")
            
    # -------------------------------------------------------------
    # Hypothesis 2: Step Indices (stpRNG, stpRNG2, stpRNG3, stpRNG4, stpRNG5)
    # -------------------------------------------------------------
    print("\n=======================================================")
    print("  HYPOTHESIS 2: STEP INDICES CONTRACTS (stpRNG 1 to 5)")
    print("=======================================================")
    for sym in ['stpRNG', 'stpRNG2', 'stpRNG3', 'stpRNG4', 'stpRNG5']:
        cf = await client.send_request({'contracts_for': sym})
        avail = cf.get('contracts_for', {}).get('available', [])
        c_types = sorted(list(set(c.get('contract_type') for c in avail)))
        print(f"[{sym}] ({len(c_types)} types): {c_types}")
        for c in avail:
            if c.get('contract_type') in ['CALL', 'PUT', 'MULTUP', 'MULTDOWN', 'ONETOUCH', 'ACCU']:
                print(f"    {c.get('contract_type')}: Min={c.get('min_contract_duration')} Max={c.get('max_contract_duration')}")

    # -------------------------------------------------------------
    # Hypothesis 3: Accumulators on BOOM50 & CRASH50
    # -------------------------------------------------------------
    print("\n=======================================================")
    print("  HYPOTHESIS 3: ACCUMULATORS ON BOOM50 & CRASH50")
    print("=======================================================")
    for sym in ['BOOM50', 'CRASH50']:
        prop = await client.send_request({
            'proposal': 1,
            'amount': 10.0,
            'basis': 'stake',
            'contract_type': 'ACCU',
            'currency': 'USD',
            'underlying_symbol': sym,
            'growth_rate': 0.01
        })
        print(f"[{sym}] ACCU Proposal (1% growth): {prop.get('proposal', prop.get('error'))}")

    if client.ws:
        await client.ws.close()

if __name__ == '__main__':
    asyncio.run(main())
