import asyncio
import os
import sys
import numpy as np
import scipy.stats as stats

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from dotenv import load_dotenv
from deriv_client import DerivClient

load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env'))
token = os.getenv('DERIV_API_TOKEN')
app_id = os.getenv('DERIV_APP_ID')

async def fetch_ticks(client, symbol, total_count=20000):
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
            print(f"Error fetching {symbol}: {resp['error']}")
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
        await asyncio.sleep(0.1)
    return np.array(prices, dtype=np.float64), np.array(times, dtype=np.int64)

async def main():
    client = DerivClient(app_id=app_id, api_token=token, use_demo=True)
    await client.connect()
    print("Connected! Account:", client.account_id)
    
    for sym in ['RDBULL', 'RDBEAR']:
        print(f"\n=======================================================")
        print(f"  RIGOROUS TOUCH AUDIT ON {sym}")
        print(f"=======================================================")
        prices, times = await fetch_ticks(client, sym, total_count=25000)
        n = len(prices)
        print(f"Fetched {n:,} ticks. Timespan: {(times[-1]-times[0])/3600:.2f} hours")
        
        # Calculate realized volatility
        log_rets = np.diff(np.log(prices))
        sigma_sec = np.std(log_rets)
        annualized_vol = sigma_sec * np.sqrt(365.25 * 86400)
        print(f"Realized sigma per second: {sigma_sec:.6f} | Annualized vol: {annualized_vol*100:.2f}%")
        
        # Test 2-minute (120 ticks) and 5-minute (300 ticks) Touch rates
        for duration_s in [120, 300]:
            print(f"\n--- Duration: {duration_s}s ({duration_s//60} minutes) ---")
            
            # Step every 30 seconds to avoid overly correlated overlapping windows
            step = 30
            sample_idxs = range(0, n - duration_s, step)
            
            for b in [0.5, 1.0, 1.5, 2.0, 3.0]:
                # Query Deriv live proposal for this exact barrier and duration
                prop_up = await client.send_request({
                    'proposal': 1,
                    'amount': 10.0,
                    'basis': 'stake',
                    'contract_type': 'ONETOUCH',
                    'currency': 'USD',
                    'underlying_symbol': sym,
                    'duration': duration_s // 60,
                    'duration_unit': 'm',
                    'barrier': f"+{b}"
                })
                prop_down = await client.send_request({
                    'proposal': 1,
                    'amount': 10.0,
                    'basis': 'stake',
                    'contract_type': 'ONETOUCH',
                    'currency': 'USD',
                    'underlying_symbol': sym,
                    'duration': duration_s // 60,
                    'duration_unit': 'm',
                    'barrier': f"-{b}"
                })
                
                payout_up = prop_up.get('proposal', {}).get('payout', 0)
                payout_down = prop_down.get('proposal', {}).get('payout', 0)
                
                breakeven_up = (10.0 / payout_up * 100) if payout_up > 0 else 0
                breakeven_down = (10.0 / payout_down * 100) if payout_down > 0 else 0
                
                # Empirical count
                up_touches = 0
                down_touches = 0
                total = 0
                for idx in sample_idxs:
                    p0 = prices[idx]
                    path = prices[idx:idx + duration_s + 1]
                    if np.max(path) - p0 >= b:
                        up_touches += 1
                    if np.min(path) - p0 <= -b:
                        down_touches += 1
                    total += 1
                    
                real_wr_up = (up_touches / total) * 100
                real_wr_down = (down_touches / total) * 100
                
                # Edge: Real WR - Breakeven WR
                edge_up = real_wr_up - breakeven_up
                edge_down = real_wr_down - breakeven_down
                
                # Statistical test: Z-score of real WR vs breakeven
                se_up = np.sqrt((breakeven_up/100 * (1 - breakeven_up/100)) / total)
                z_up = ((real_wr_up - breakeven_up)/100) / se_up if se_up > 0 else 0
                
                se_down = np.sqrt((breakeven_down/100 * (1 - breakeven_down/100)) / total)
                z_down = ((real_wr_down - breakeven_down)/100) / se_down if se_down > 0 else 0
                
                print(f"  Barrier ±{b:3.1f} | N={total:4d}:")
                print(f"    UP (+{b:.1f}): Real WR={real_wr_up:5.1f}% vs BE={breakeven_up:5.1f}% | Edge={edge_up:+5.1f}% | Z={z_up:+.2f} | Payout={payout_up}")
                print(f"    DN (-{b:.1f}): Real WR={real_wr_down:5.1f}% vs BE={breakeven_down:5.1f}% | Edge={edge_down:+5.1f}% | Z={z_down:+.2f} | Payout={payout_down}")

    if client.ws:
        await client.ws.close()

if __name__ == '__main__':
    asyncio.run(main())
