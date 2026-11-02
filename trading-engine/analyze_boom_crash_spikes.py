import asyncio
import os
import sys
import json
import numpy as np
import scipy.stats as stats

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from dotenv import load_dotenv
from deriv_client import DerivClient

load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env'))
token = os.getenv('DERIV_API_TOKEN')
app_id = os.getenv('DERIV_APP_ID')

async def fetch_historical_ticks(client, symbol, total_count=10000):
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
    
    symbols = ['BOOM50', 'CRASH50', 'BOOM150N', 'CRASH150N', 'BOOM500', 'CRASH500']
    
    results = {}
    
    for sym in symbols:
        print(f"\n=======================================================")
        print(f"  ANALYZING {sym}")
        print(f"=======================================================")
        prices, times = await fetch_historical_ticks(client, sym, total_count=15000)
        n = len(prices)
        print(f"Fetched {n:,} ticks. Timespan: {times[0]} to {times[-1]} ({(times[-1]-times[0])/3600:.2f} hours)")
        
        diffs = np.diff(prices)
        is_boom = 'BOOM' in sym
        
        # Identify spikes:
        # For BOOM: spikes are large positive diffs
        # For CRASH: spikes are large negative diffs
        if is_boom:
            # Normal drift is negative. A spike is a large positive jump.
            # Let's determine threshold via IQR / robust statistics
            median_diff = np.median(diffs)
            mad = np.median(np.abs(diffs - median_diff))
            threshold = median_diff + 10 * (mad * 1.4826)
            spike_mask = diffs > max(threshold, 1.0)
            normal_diffs = diffs[~spike_mask]
            spike_diffs = diffs[spike_mask]
        else:
            median_diff = np.median(diffs)
            mad = np.median(np.abs(diffs - median_diff))
            threshold = median_diff - 10 * (mad * 1.4826)
            spike_mask = diffs < min(threshold, -1.0)
            normal_diffs = diffs[~spike_mask]
            spike_diffs = diffs[spike_mask]
            
        spike_indices = np.where(spike_mask)[0]
        n_spikes = len(spike_indices)
        
        if n_spikes < 5:
            print(f"Too few spikes ({n_spikes}) found for {sym}")
            continue
            
        gaps = np.diff(spike_indices) # inter-spike interval in ticks
        
        # Theoretical parameter for geometric distribution: p = 1 / mean_gap
        mean_gap = np.mean(gaps)
        median_gap = np.median(gaps)
        min_gap = np.min(gaps)
        max_gap = np.max(gaps)
        std_gap = np.std(gaps)
        
        print(f"Total Spikes: {n_spikes:,}")
        print(f"Normal ticks: mean move = {np.mean(normal_diffs):.6f}, std = {np.std(normal_diffs):.6f}, range = [{np.min(normal_diffs):.4f}, {np.max(normal_diffs):.4f}]")
        print(f"Spike size: mean = {np.mean(spike_diffs):.2f}, std = {np.std(spike_diffs):.2f}, range = [{np.min(spike_diffs):.2f}, {np.max(spike_diffs):.2f}]")
        print(f"\n--- INTER-SPIKE INTERVAL (GAPS) ---")
        print(f"Mean Gap:   {mean_gap:.2f} ticks (Deriv nominal: {sym.replace('BOOM','').replace('CRASH','').replace('N','')})")
        print(f"Median Gap: {median_gap:.1f} ticks")
        print(f"Min Gap:    {min_gap} ticks")
        print(f"Max Gap:    {max_gap} ticks")
        print(f"Std Gap:    {std_gap:.2f} ticks")
        
        # Test 1: Is there a refractory / lockout period?
        # Check gaps <= 5 ticks
        immediate_followups = sum(1 for g in gaps if g <= 2)
        gaps_le_5 = sum(1 for g in gaps if g <= 5)
        print(f"\n--- LOCKOUT / REFRACTORY TEST ---")
        print(f"Gaps == 1 (Back-to-back spikes): {sum(1 for g in gaps if g == 1)} ({sum(1 for g in gaps if g == 1)/len(gaps)*100:.2f}%)")
        print(f"Gaps <= 2: {immediate_followups} ({immediate_followups/len(gaps)*100:.2f}%)")
        print(f"Gaps <= 5: {gaps_le_5} ({gaps_le_5/len(gaps)*100:.2f}%)")
        
        # Test 2: Goodness of Fit to Geometric Distribution (Memoryless)
        # In a memoryless process, gaps follow Geometric(p), where p = 1 / mean_gap.
        # For Geometric(p), std = sqrt((1-p)/p^2) approx mean_gap.
        p_est = 1.0 / mean_gap
        geom_std = np.sqrt((1 - p_est) / (p_est**2))
        dispersion_ratio = std_gap / geom_std
        print(f"\n--- MEMORYLESSNESS (POISSON) TEST ---")
        print(f"Observed Std / Geometric Std: {dispersion_ratio:.4f} (1.0 = perfect Poisson/memoryless)")
        
        # Kolmogorov-Smirnov test against geometric distribution
        # Continuous exponential approximation or discrete KS
        geom_cdf = stats.geom(p_est).cdf
        ks_stat, ks_pval = stats.kstest(gaps, geom_cdf)
        print(f"KS-Test vs Geometric: stat = {ks_stat:.4f}, p-value = {ks_pval:.4f}")
        if ks_pval < 0.01:
            print("  -> REJECT MEMORYLESS: Distribution deviates significantly from memoryless!")
        else:
            print("  -> CANNOT REJECT MEMORYLESS: Gaps are consistent with a memoryless Poisson process.")
            
        # Test 3: Hazard Rate Analysis
        # h(k) = P(Spike at tick k | Survived to tick k)
        # Compute empirical hazard rate for bins: 1-10, 11-20, 21-30, 31-50, 51-100, >100
        print(f"\n--- EMPIRICAL HAZARD RATE h(k) ---")
        bins = [(1, 5), (6, 15), (16, 30), (31, 50), (51, 80), (81, 120), (121, 200)]
        for low, high in bins:
            # Number of gaps that survived to 'low'
            at_risk = sum(1 for g in gaps if g >= low)
            # Number of gaps that failed in [low, high]
            failed = sum(1 for g in gaps if low <= g <= high)
            hazard = failed / at_risk if at_risk > 0 else 0
            # Expected under geometric
            p_geom_fail = 1.0 - (1.0 - p_est)**(high - low + 1)
            print(f"  Ticks [{low:3d}, {high:3d}]: At Risk = {at_risk:4d} | Spikes = {failed:3d} | Empirical P = {hazard*100:5.2f}% | Expected Geometric = {p_geom_fail*100:5.2f}%")
            
        results[sym] = {
            'n_spikes': int(n_spikes),
            'mean_gap': float(mean_gap),
            'min_gap': int(min_gap),
            'dispersion': float(dispersion_ratio),
            'ks_pval': float(ks_pval)
        }
        
    # Check Multiplier specifications on BOOM50 / CRASH50
    print("\n=======================================================")
    print("  MULTIPLIER PROPOSALS ON BOOM50 / CRASH50")
    print("=======================================================")
    for sym in ['BOOM50', 'CRASH50']:
        for ct in ['MULTUP', 'MULTDOWN']:
            prop = await client.send_request({
                'proposal': 1,
                'amount': 10.0,
                'basis': 'stake',
                'contract_type': ct,
                'currency': 'USD',
                'underlying_symbol': sym,
                'multiplier': 100
            })
            p = prop.get('proposal', {})
            print(f"{sym} {ct} 100x:")
            print(f"  Ask Price: {p.get('ask_price')} | Commission: {p.get('commission')}")
            print(f"  Stop Out: {p.get('limit_order', {}).get('stop_out', {}).get('value')}")
            print(f"  Error if any: {prop.get('error')}")

    if client.ws:
        await client.ws.close()

if __name__ == '__main__':
    asyncio.run(main())
