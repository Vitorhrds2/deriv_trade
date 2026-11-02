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

async def fetch_ticks(client, symbol, total_count=15000):
    prices = []
    end = 'latest'
    while len(prices) < total_count:
        batch_size = min(5000, total_count - len(prices))
        req = {'ticks_history': symbol, 'end': end, 'count': batch_size, 'style': 'ticks'}
        resp = await client.send_request(req)
        if 'error' in resp:
            break
        h = resp.get('history', {})
        p = h.get('prices', [])
        t = h.get('times', [])
        if not p:
            break
        if prices:
            prices = p[:-1] + prices
        else:
            prices = p
        end = str(t[0])
        if len(p) < 2:
            break
        await asyncio.sleep(0.08)
    return np.array(prices, dtype=np.float64)

async def main():
    client = DerivClient(app_id=app_id, api_token=token, use_demo=True)
    await client.connect()
    print("Connected to Deriv! Analyzing serial correlation on Step Indices (stpRNG to stpRNG5)...")
    
    for s in ['stpRNG', 'stpRNG2', 'stpRNG3', 'stpRNG4', 'stpRNG5']:
        prices = await fetch_ticks(client, s, total_count=15000)
        n = len(prices)
        if n < 500:
            continue
            
        diffs = np.diff(prices)
        steps = np.sign(diffs) # +1 for UP, -1 for DOWN
        
        up_count = np.sum(steps > 0)
        down_count = np.sum(steps < 0)
        p_up = up_count / len(steps)
        
        # 1. First-order Markov Transition Matrix:
        # P(Up | Up), P(Down | Up), P(Up | Down), P(Down | Down)
        up_given_up = 0
        total_prev_up = 0
        up_given_down = 0
        total_prev_down = 0
        
        for i in range(len(steps) - 1):
            if steps[i] > 0:
                total_prev_up += 1
                if steps[i+1] > 0:
                    up_given_up += 1
            elif steps[i] < 0:
                total_prev_down += 1
                if steps[i+1] > 0:
                    up_given_down += 1
                    
        prob_up_up = up_given_up / total_prev_up if total_prev_up > 0 else 0
        prob_down_up = 1.0 - prob_up_up
        prob_up_down = up_given_down / total_prev_down if total_prev_down > 0 else 0
        prob_down_down = 1.0 - prob_up_down
        
        # 2. Runs of length 2, 3, 4
        # What is P(Reversal) after 3 consecutive UP ticks?
        rev_after_3_up = 0
        total_3_up = 0
        for i in range(len(steps) - 3):
            if steps[i] > 0 and steps[i+1] > 0 and steps[i+2] > 0:
                total_3_up += 1
                if steps[i+3] < 0:
                    rev_after_3_up += 1
        p_rev_3up = rev_after_3_up / total_3_up if total_3_up > 0 else 0
        
        rev_after_3_down = 0
        total_3_down = 0
        for i in range(len(steps) - 3):
            if steps[i] < 0 and steps[i+1] < 0 and steps[i+2] < 0:
                total_3_down += 1
                if steps[i+3] > 0:
                    rev_after_3_down += 1
        p_rev_3down = rev_after_3_down / total_3_down if total_3_down > 0 else 0

        # Autocorrelation lag 1
        autocorr_1 = np.corrcoef(steps[:-1], steps[1:])[0, 1]

        print(f"\n=======================================================")
        print(f"  {s} ANALYSIS (N={n:,} ticks)")
        print(f"=======================================================")
        print(f"  Unconditional: UP={p_up*100:.2f}% | DOWN={(1-p_up)*100:.2f}%")
        print(f"  Lag-1 Autocorrelation: {autocorr_1:+.4f}")
        print(f"  Markov Transitions:")
        print(f"    P(UP   | UP)   = {prob_up_up*100:5.2f}% | P(DOWN | UP)   = {prob_down_up*100:5.2f}%")
        print(f"    P(DOWN | DOWN) = {prob_down_down*100:5.2f}% | P(UP   | DOWN) = {prob_up_down*100:5.2f}%")
        print(f"  Streak Reversals:")
        print(f"    After 3 consecutive UP ticks   -> P(DOWN) = {p_rev_3up*100:5.2f}% (N={total_3_up})")
        print(f"    After 3 consecutive DOWN ticks -> P(UP)   = {p_rev_3down*100:5.2f}% (N={total_3_down})")

    if client.ws:
        await client.ws.close()

if __name__ == '__main__':
    asyncio.run(main())
