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

async def fetch_ticks(client, symbol, total_count=30000):
    prices = []
    times = []
    end = 'latest'
    while len(prices) < total_count:
        batch_size = min(5000, total_count - len(prices))
        req = {
            'ticks_history': symbol,
            'end': end,
            'count': batch_size,
            'style': 'ticks'
        }
        resp = await client.send_request(req)
        if 'error' in resp:
            break
        history = resp.get('history', {})
        batch_prices = history.get('prices', [])
        batch_times = history.get('times', [])
        if not batch_prices:
            break
        if prices:
            prices = batch_prices[:-1] + prices
            times = batch_times[:-1] + times
        else:
            prices = batch_prices
            times = batch_times
        end = str(batch_times[0])
        if len(batch_prices) < 2:
            break
        await asyncio.sleep(0.08)
    return np.array(prices, dtype=np.float64), np.array(times, dtype=np.int64)

async def main():
    client = DerivClient(app_id=app_id, api_token=token, use_demo=True)
    await client.connect()
    print("Connected to Deriv! Analyzing barrier surface on RDBULL and RDBEAR...")

    for sym in ['RDBULL', 'RDBEAR']:
        print(f"\n=======================================================")
        print(f"  BARRIER OPTIMIZATION MATRIX: {sym}")
        print(f"=======================================================")
        prices, times = await fetch_ticks(client, sym, total_count=30000)
        n = len(prices)
        print(f"Loaded {n:,} ticks (~{(times[-1]-times[0])/3600:.1f} hours of live data)")
        
        # Test durations: 2m (120s), 3m (180s), 5m (300s)
        for dur_m in [2, 3, 5]:
            dur_s = dur_m * 60
            step = 30
            sample_idxs = range(0, n - dur_s, step)
            total_samples = len(sample_idxs)
            
            print(f"\n--- Duration: {dur_m} minutes ({dur_s}s) | N={total_samples} windows ---")
            print(f"{'Barrier':<10} | {'Type':<8} | {'Payout ($)':<10} | {'BE WR':<8} | {'Emp WR':<8} | {'Edge':<8} | {'EV ($/1$)':<10} | {'Z-Score':<8}")
            print("-" * 80)
            
            # Counter-trend barriers
            # For RDBULL, counter-trend is negative barrier (-b)
            # For RDBEAR, counter-trend is positive barrier (+b)
            barriers_to_test = [1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0]
            
            for b in barriers_to_test:
                barrier_str = f"-{b:.1f}" if sym == 'RDBULL' else f"+{b:.1f}"
                sign = -1 if sym == 'RDBULL' else +1
                
                # Query proposal
                prop = await client.send_request({
                    'proposal': 1,
                    'amount': 10.0,
                    'basis': 'stake',
                    'contract_type': 'ONETOUCH',
                    'currency': 'USD',
                    'underlying_symbol': sym,
                    'duration': dur_m,
                    'duration_unit': 'm',
                    'barrier': barrier_str
                })
                
                if 'error' in prop:
                    continue
                    
                payout = prop.get('proposal', {}).get('payout', 0)
                if payout <= 0:
                    continue
                    
                be_wr = (10.0 / payout) * 100
                
                # Compute empirical hit rate
                hits = 0
                for idx in sample_idxs:
                    p0 = prices[idx]
                    path = prices[idx:idx + dur_s + 1]
                    if sign == -1:
                        if np.min(path) - p0 <= -b:
                            hits += 1
                    else:
                        if np.max(path) - p0 >= b:
                            hits += 1
                            
                emp_wr = (hits / total_samples) * 100
                edge = emp_wr - be_wr
                
                # EV per $1 stake
                payout_ratio = payout / 10.0
                ev_per_dollar = (emp_wr / 100.0) * payout_ratio - 1.0
                
                # Z-score
                se = np.sqrt((be_wr / 100.0 * (1.0 - be_wr / 100.0)) / total_samples)
                z = ((emp_wr - be_wr) / 100.0) / se if se > 0 else 0.0
                
                print(f"{barrier_str:<10} | {'TOUCH':<8} | ${payout:<9.2f} | {be_wr:6.1f}% | {emp_wr:6.1f}% | {edge:+6.1f}% | ${ev_per_dollar:+8.3f} | {z:+6.2f}")
                await asyncio.sleep(0.05)

    if client.ws:
        await client.ws.close()

if __name__ == '__main__':
    asyncio.run(main())
