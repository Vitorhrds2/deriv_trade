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

async def fetch_ticks(client, symbol, total_count=10000):
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
    
    pairs = [
        ('WLDEUR', 'WLDUSD', 'frxEURUSD'),
        ('WLDGBP', 'WLDUSD', 'frxGBPUSD'),
        ('WLDAUD', 'WLDUSD', 'frxAUDUSD')
    ]
    
    for basket_base, basket_quote, real_sym in pairs:
        print(f"\n=======================================================")
        print(f"  LEAD-LAG AUDIT: {basket_base}/{basket_quote} vs {real_sym}")
        print(f"=======================================================")
        
        p_base, t_base = await fetch_ticks(client, basket_base, total_count=10000)
        p_quote, t_quote = await fetch_ticks(client, basket_quote, total_count=10000)
        p_real, t_real = await fetch_ticks(client, real_sym, total_count=10000)
        
        map_base = dict(zip(t_base, p_base))
        map_quote = dict(zip(t_quote, p_quote))
        map_real = dict(zip(t_real, p_real))
        
        common_t = sorted(list(set(map_base.keys()) & set(map_quote.keys()) & set(map_real.keys())))
        print(f"Common aligned timestamps: {len(common_t):,} ticks")
        
        if len(common_t) < 500:
            print("Insufficient aligned timestamps.")
            continue
            
        b_base = np.array([map_base[t] for t in common_t])
        b_quote = np.array([map_quote[t] for t in common_t])
        real_p = np.array([map_real[t] for t in common_t])
        
        # Log returns
        ret_basket = np.diff(np.log(b_base / b_quote))
        ret_real = np.diff(np.log(real_p))
        
        # Cross correlation at lag k:
        # lag k > 0: real_t leads basket_(t+k)
        # lag k < 0: basket_t leads real_(t-k)
        print("\n--- CROSS-CORRELATION BY LAG k (seconds) ---")
        print("  Positive lag k > 0 means REAL FOREX LEADS THE BASKET by k seconds")
        print("  Negative lag k < 0 means BASKET LEADS REAL FOREX by |k| seconds")
        print("---------------------------------------------------------------")
        
        best_lag = 0
        best_corr = -1
        
        lags = list(range(-10, 11))
        corr_by_lag = {}
        for k in lags:
            if k > 0:
                # ret_real[:-k] vs ret_basket[k:]
                c = np.corrcoef(ret_real[:-k], ret_basket[k:])[0, 1]
            elif k < 0:
                # ret_real[-k:] vs ret_basket[:k]
                c = np.corrcoef(ret_real[-k:], ret_basket[:k])[0, 1]
            else:
                c = np.corrcoef(ret_real, ret_basket)[0, 1]
                
            corr_by_lag[k] = c
            if c > best_corr:
                best_corr = c
                best_lag = k
            bar = '#' * int(max(0, c * 50))
            print(f"  Lag {k:+3d}s: corr = {c:+.4f} | {bar}")
            
        print(f"\n  ==> PEAK CORRELATION: {best_corr:+.4f} at LAG {best_lag:+d}s")
        if best_lag > 0:
            print(f"  *** DISCOVERY: Real Forex LEADS the synthetic Basket by {best_lag} second(s)! ***")
        elif best_lag < 0:
            print(f"  *** DISCOVERY: Synthetic Basket LEADS real Forex by {abs(best_lag)} second(s)! ***")
        else:
            print(f"  Synchronous (Lag 0s is peak).")
            
        # Also check lead-lag of single base basket vs real
        ret_base_single = np.diff(np.log(b_base))
        c0_base = np.corrcoef(ret_real, ret_base_single)[0, 1]
        print(f"\n  Baseline synchronous corr of {basket_base} alone vs {real_sym}: {c0_base:+.4f}")

    if client.ws:
        await client.ws.close()

if __name__ == '__main__':
    asyncio.run(main())
