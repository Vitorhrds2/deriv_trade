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
    
    # 1. Analyze RB100 and RB200 ticks
    print("\n=======================================================")
    print("  ANALYZING RANGE BREAK INDICES (RB100, RB200)")
    print("=======================================================")
    for sym in ['RB100', 'RB200']:
        prices, times = await fetch_ticks(client, sym, total_count=10000)
        n = len(prices)
        print(f"\n--- {sym} (N={n:,} ticks) ---")
        print(f"Sample prices: {prices[:10]}")
        print(f"Price range: min={np.min(prices):.2f}, max={np.max(prices):.2f}, start={prices[0]:.2f}, end={prices[-1]:.2f}")
        
        diffs = np.diff(prices)
        abs_diffs = np.abs(diffs)
        
        # Breakouts are large jumps
        # Normal ticks vs breakout ticks
        median_move = np.median(abs_diffs)
        mean_move = np.mean(abs_diffs)
        std_move = np.std(abs_diffs)
        print(f"Tick absolute moves: median={median_move:.4f}, mean={mean_move:.4f}, std={std_move:.4f}")
        
        # Identify breakout jumps (e.g. moves > 5x median)
        breakout_threshold = max(5.0 * median_move, 10.0)
        breakouts = np.where(abs_diffs > breakout_threshold)[0]
        n_breakouts = len(breakouts)
        print(f"Breakouts (moves > {breakout_threshold:.1f}): count={n_breakouts}")
        if n_breakouts > 5:
            breakout_sizes = diffs[breakouts]
            up_breakouts = np.sum(breakout_sizes > 0)
            down_breakouts = np.sum(breakout_sizes < 0)
            print(f"  Upward breakouts: {up_breakouts} ({up_breakouts/n_breakouts*100:.1f}%) | Mean size = {np.mean(breakout_sizes[breakout_sizes > 0]):+.2f}")
            print(f"  Downward breakouts: {down_breakouts} ({down_breakouts/n_breakouts*100:.1f}%) | Mean size = {np.mean(breakout_sizes[breakout_sizes < 0]):+.2f}")
            
            # Gaps between breakouts
            bo_gaps = np.diff(breakouts)
            print(f"  Breakout interval (ticks): mean={np.mean(bo_gaps):.1f}, median={np.median(bo_gaps):.1f}, min={np.min(bo_gaps)}, max={np.max(bo_gaps)}")
            
            # What happens AFTER a breakout?
            # Examine next 5 ticks and 10 ticks after a breakout
            post_moves_1t = [diffs[b + 1] for b in breakouts if b + 1 < len(diffs)]
            post_moves_5t = [prices[b + 5] - prices[b + 1] for b in breakouts if b + 5 < len(prices)]
            
            # Does the price continue (momentum) or revert (reversal)?
            # Align with breakout direction
            bo_signs = np.sign(diffs[breakouts[:len(post_moves_1t)]])
            aligned_1t = [bo_signs[i] * post_moves_1t[i] for i in range(len(post_moves_1t))]
            aligned_5t = [bo_signs[i] * post_moves_5t[i] for i in range(len(post_moves_5t))]
            
            p_cont_1t = np.mean(np.array(aligned_1t) > 0) * 100
            p_rev_1t = np.mean(np.array(aligned_1t) < 0) * 100
            p_flat_1t = np.mean(np.array(aligned_1t) == 0) * 100
            
            print(f"\n  Post-Breakout 1-tick Reaction (N={len(aligned_1t)}):")
            print(f"    Continuation (same direction): {p_cont_1t:.1f}%")
            print(f"    Reversal (opposite direction): {p_rev_1t:.1f}%")
            print(f"    Flat:                          {p_flat_1t:.1f}%")
            print(f"    Mean aligned move:             {np.mean(aligned_1t):+.4f} points")

    # 2. Touch Options Backtest on RDBEAR / RDBULL
    print("\n=======================================================")
    print("  EMPIRICAL TOUCH / NO-TOUCH BACKTEST (RDBEAR / RDBULL)")
    print("=======================================================")
    for sym in ['RDBEAR', 'RDBULL']:
        prices, times = await fetch_ticks(client, sym, total_count=10000)
        n = len(prices)
        print(f"\n--- {sym} (N={n:,} ticks) ---")
        
        # Duration: 2 minutes = 120 seconds (approx 120 ticks, since 1 tick/sec)
        window = 120
        
        # Test barriers: +0.5, -0.5, +1.0, -1.0, +2.0, -2.0
        # For each tick t:
        # Check if max(prices[t:t+120]) - prices[t] >= barrier (for positive)
        # Check if min(prices[t:t+120]) - prices[t] <= barrier (for negative)
        
        # Step through every 30 ticks to get semi-independent samples
        sample_indices = range(0, n - window, 15)
        
        for b in [0.5, 1.0, 1.5, 2.0]:
            # Upper barrier (+b)
            touches_up = 0
            # Lower barrier (-b)
            touches_down = 0
            total_trials = 0
            
            for idx in sample_indices:
                p0 = prices[idx]
                future_path = prices[idx:idx + window + 1]
                max_dev = np.max(future_path) - p0
                min_dev = np.min(future_path) - p0
                
                if max_dev >= b:
                    touches_up += 1
                if min_dev <= -b:
                    touches_down += 1
                total_trials += 1
                
            p_touch_up = (touches_up / total_trials) * 100
            p_notouch_up = 100 - p_touch_up
            p_touch_down = (touches_down / total_trials) * 100
            p_notouch_down = 100 - p_touch_down
            
            print(f"  Barrier ±{b:3.1f} (N={total_trials}):")
            print(f"    Upper (+{b:.1f}): P(Touch)={p_touch_up:5.1f}% | P(NoTouch)={p_notouch_up:5.1f}%")
            print(f"    Lower (-{b:.1f}): P(Touch)={p_touch_down:5.1f}% | P(NoTouch)={p_notouch_down:5.1f}%")

    if client.ws:
        await client.ws.close()

if __name__ == '__main__':
    asyncio.run(main())
