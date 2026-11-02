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
    
    for sym in ['RDBULL', 'RDBEAR']:
        print(f"\n======================================================")
        print(f"  EXACT TIME-ALIGNED EV MATRIX: {sym}")
        print(f"======================================================")
        
        # Fetch 6000 ticks (~3.3 hours)
        prices = []
        times = []
        end = 'latest'
        for _ in range(3):
            r = await client.send_request({'ticks_history': sym, 'end': end, 'count': 5000, 'style': 'ticks'})
            h = r.get('history', {})
            p = h.get('prices', [])
            t = h.get('times', [])
            if not p:
                break
            if prices:
                prices = p[:-1] + prices
                times = t[:-1] + times
            else:
                prices = p
                times = t
            end = str(t[0])
            await asyncio.sleep(0.05)
            
        prices = np.array(prices, dtype=np.float64)
        times = np.array(times, dtype=np.int64)
        print(f"Loaded {len(prices):,} ticks (~{(times[-1]-times[0])/3600:.1f}h)")
        
        # Test durations: 2m (120s), 3m (180s), 5m (300s)
        for dur_m in [2, 3, 5]:
            dur_s = dur_m * 60
            ticks_n = dur_s // 2  # exactly 2 seconds per tick!
            
            print(f"\n--- Duration: {dur_m}m ({dur_s}s = {ticks_n} ticks) ---")
            print(f"{'Barrier':<8} | {'Payout':<8} | {'BE WR':<8} | {'Real WR':<8} | {'Edge':<8} | {'EV / $1':<8}")
            print("-" * 60)
            
            for b in [0.5, 0.8, 1.0, 1.2, 1.5, 2.0]:
                b_str = f"-{b:.1f}" if sym == 'RDBULL' else f"+{b:.1f}"
                prop = await client.send_request({
                    'proposal': 1, 'amount': 10.0, 'basis': 'stake', 'contract_type': 'ONETOUCH',
                    'currency': 'USD', 'underlying_symbol': sym, 'duration': dur_m, 'duration_unit': 'm', 'barrier': b_str
                })
                payout = prop.get('proposal', {}).get('payout', 0)
                if payout <= 0:
                    continue
                be_wr = (10.0 / payout) * 100
                
                hits = 0
                total = 0
                for i in range(0, len(prices) - ticks_n, 10):
                    p0 = prices[i]
                    path = prices[i:i + ticks_n + 1]
                    if sym == 'RDBULL' and np.min(path) - p0 <= -b:
                        hits += 1
                    elif sym == 'RDBEAR' and np.max(path) - p0 >= +b:
                        hits += 1
                    total += 1
                    
                real_wr = (hits / total) * 100
                edge = real_wr - be_wr
                ev = (real_wr / 100.0) * (payout / 10.0) - 1.0
                print(f"{b_str:<8} | ${payout:<7.2f} | {be_wr:5.1f}%  | {real_wr:5.1f}%   | {edge:+5.1f}% | ${ev:+6.3f}")
                await asyncio.sleep(0.04)

    if client.ws:
        await client.ws.close()

if __name__ == '__main__':
    asyncio.run(main())
