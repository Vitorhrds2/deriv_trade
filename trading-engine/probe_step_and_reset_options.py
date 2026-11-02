import asyncio
import os
import sys
import numpy as np

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from dotenv import load_dotenv
from deriv_client import DerivClient

load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env'))
token = os.getenv('DERIV_API_TOKEN')
app_id = os.getenv('DERIV_APP_ID')

async def main():
    client = DerivClient(app_id=app_id, api_token=token, use_demo=True)
    await client.connect()
    print("Connected to Deriv! Probing Step Indices (stpRNG) and Reset Options...")

    # 1. Step Indices Analysis (stpRNG to stpRNG5)
    print("\n=======================================================")
    print("  STEP INDICES TICK AUDIT (stpRNG to stpRNG5)")
    print("=======================================================")
    for s in ['stpRNG', 'stpRNG2', 'stpRNG3', 'stpRNG4', 'stpRNG5']:
        r = await client.send_request({'ticks_history': s, 'end': 'latest', 'count': 500, 'style': 'ticks'})
        prices = np.array(r.get('history', {}).get('prices', []), dtype=np.float64)
        if len(prices) < 2:
            continue
        diffs = np.diff(prices)
        up_steps = np.sum(diffs > 0)
        down_steps = np.sum(diffs < 0)
        zero_steps = np.sum(diffs == 0)
        total = len(diffs)
        
        # Unique step values
        unique_steps = np.unique(np.round(diffs, 4))
        print(f"[{s}] N={total} ticks: UP={up_steps} ({up_steps/total*100:.1f}%) | DOWN={down_steps} ({down_steps/total*100:.1f}%) | FLAT={zero_steps} | Steps={unique_steps}")
        
        # Check 1-tick and 5-tick Call/Put proposals
        prop_c1 = await client.send_request({
            'proposal': 1, 'amount': 10.0, 'basis': 'stake', 'contract_type': 'CALL',
            'currency': 'USD', 'underlying_symbol': s, 'duration': 1, 'duration_unit': 't'
        })
        prop_c5 = await client.send_request({
            'proposal': 1, 'amount': 10.0, 'basis': 'stake', 'contract_type': 'CALL',
            'currency': 'USD', 'underlying_symbol': s, 'duration': 5, 'duration_unit': 't'
        })
        p1 = prop_c1.get('proposal', {})
        p5 = prop_c5.get('proposal', {})
        print(f"  [{s}] 1-tick CALL Payout: ${p1.get('payout', 0)} (BE: {10.0/float(p1.get('payout', 1))*100:.1f}%) | 5-tick CALL: ${p5.get('payout', 0)} (BE: {10.0/float(p5.get('payout', 1))*100:.1f}%)")

    # 2. Reset Options Analysis (RESETCALL / RESETPUT)
    print("\n=======================================================")
    print("  RESET OPTIONS AUDIT (1HZ10V, R_100)")
    print("=======================================================")
    for s in ['1HZ10V', 'R_100']:
        for dur in [5, 15]:
            prop_rc = await client.send_request({
                'proposal': 1, 'amount': 10.0, 'basis': 'stake', 'contract_type': 'RESETCALL',
                'currency': 'USD', 'underlying_symbol': s, 'duration': dur, 'duration_unit': 't'
            })
            prop_call = await client.send_request({
                'proposal': 1, 'amount': 10.0, 'basis': 'stake', 'contract_type': 'CALL',
                'currency': 'USD', 'underlying_symbol': s, 'duration': dur, 'duration_unit': 't'
            })
            p_rc = prop_rc.get('proposal', {})
            p_c = prop_call.get('proposal', {})
            print(f"[{s}] {dur} ticks -> Standard CALL: Payout=${p_c.get('payout')} | RESETCALL: Payout=${p_rc.get('payout')}")

    if client.ws:
        await client.ws.close()

if __name__ == '__main__':
    asyncio.run(main())
