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

async def run_touch_trial(client, trial_num, symbol, barrier_offset, stake=1.00, duration_m=2):
    print(f"\n=======================================================")
    print(f"  TRIAL #{trial_num}: {symbol} ONETOUCH {barrier_offset} (Duration: {duration_m}m, Stake: ${stake})")
    print(f"=======================================================")
    
    # 1. Get proposal
    prop = await client.send_request({
        'proposal': 1,
        'amount': stake,
        'basis': 'stake',
        'contract_type': 'ONETOUCH',
        'currency': 'USD',
        'underlying_symbol': symbol,
        'duration': duration_m,
        'duration_unit': 'm',
        'barrier': barrier_offset
    })
    
    if 'error' in prop:
        print(f"  [#{trial_num}] Proposal error: {prop['error'].get('message')}")
        return None
        
    p = prop['proposal']
    prop_id = p['id']
    ask_price = float(p['ask_price'])
    payout = float(p['payout'])
    ratio = payout / ask_price
    print(f"  [#{trial_num}] Quote: Ask=${ask_price} | Payout=${payout} (Ratio: {ratio:.4f}, BE: {100/ratio:.1f}%)")
    
    # 2. Buy contract
    buy = await client.buy_contract(prop_id, ask_price)
    if 'error' in buy:
        print(f"  [#{trial_num}] Buy error: {buy['error'].get('message')}")
        return None
        
    contract_id = buy['buy']['contract_id']
    t_start = time.time()
    print(f"  [#{trial_num}] Bought contract ID: {contract_id}")
    
    # 3. Monitor until close
    while time.time() - t_start < (duration_m * 60 + 15):
        poc = await client.send_request({
            'proposal_open_contract': 1,
            'contract_id': contract_id
        })
        c = poc.get('proposal_open_contract', {})
        status = c.get('status')
        is_sold = bool(c.get('is_sold'))
        profit = float(c.get('profit', 0) or 0)
        spot = c.get('current_spot')
        entry = c.get('entry_spot')
        barrier = c.get('barrier')
        elapsed = time.time() - t_start
        
        if is_sold:
            result = "WIN" if status == "won" else "LOSS"
            print(f"  [#{trial_num}] RESULT: {result} | Status={status} | PnL=${profit:+.2f} | Time={elapsed:.1f}s | Entry={entry} | Barrier={barrier} | Exit={spot}")
            return {
                'trial': trial_num,
                'symbol': symbol,
                'barrier': barrier_offset,
                'result': result,
                'profit': profit,
                'elapsed': elapsed,
                'ratio': ratio,
                'payout': payout
            }
            
        await asyncio.sleep(2.0)
        
    print(f"  [#{trial_num}] TIMEOUT")
    return None

async def main():
    client = DerivClient(app_id=app_id, api_token=token, use_demo=True)
    await client.connect()
    print(f"Connected to Deriv! Account: {client.account_id}")
    
    # We test 6 trials:
    # 3 on RDBULL (barrier -2.0)
    # 3 on RDBEAR (barrier +2.0)
    configs = [
        ('RDBULL', '-2.0'),
        ('RDBEAR', '+2.0'),
        ('RDBULL', '-2.0'),
        ('RDBEAR', '+2.0'),
        ('RDBULL', '-2.0'),
        ('RDBEAR', '+2.0'),
    ]
    
    results = []
    for i, (sym, b_off) in enumerate(configs, 1):
        res = await run_touch_trial(client, i, sym, b_off, stake=1.00, duration_m=2)
        if res:
            results.append(res)
        await asyncio.sleep(3.0)
        
    print("\n=======================================================")
    print("  BATTERY SUMMARY (LIVE DEMO EXECUTION)")
    print("=======================================================")
    wins = sum(1 for r in results if r['result'] == 'WIN')
    total = len(results)
    total_pnl = sum(r['profit'] for r in results)
    wr = (wins / total * 100) if total > 0 else 0
    print(f"Total Trades: {total} | Wins: {wins} ({wr:.1f}%) | Losses: {total - wins}")
    print(f"Total Realized PnL: ${total_pnl:+.2f}")
    for r in results:
        print(f"  Trial #{r['trial']} ({r['symbol']} {r['barrier']}): {r['result']} | PnL=${r['profit']:+.2f} in {r['elapsed']:.1f}s")

    if client.ws:
        await client.ws.close()

if __name__ == '__main__':
    asyncio.run(main())
