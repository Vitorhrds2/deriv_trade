import numpy as np
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
    
    # Fetch 15,000 ticks of BOOM50 and CRASH50
    for sym in ['BOOM50', 'CRASH50']:
        resp = await client.send_request({
            'ticks_history': sym,
            'end': 'latest',
            'count': 5000,
            'style': 'ticks'
        })
        history = resp.get('history', {})
        prices = np.array(history.get('prices', []), dtype=np.float64)
        times = np.array(history.get('times', []), dtype=np.int64)
        n = len(prices)
        
        diffs = np.diff(prices)
        is_boom = 'BOOM' in sym
        
        if is_boom:
            spike_mask = diffs > 1.0
        else:
            spike_mask = diffs < -1.0
            
        spike_indices = np.where(spike_mask)[0]
        print(f"\n=======================================================")
        print(f"  SIMULATING STRATEGIES ON {sym} (N={n:,} ticks, {len(spike_indices)} spikes)")
        print(f"=======================================================")
        
        stake = 10.0
        multiplier = 500
        commission = 0.07 # actual Deriv commission for 500x
        
        # Strategy A: Drift Scalping
        # On BOOM50: Enter MULTDOWN right after a spike (at index + 1)
        # Hold for M ticks (e.g. M = 5, 10, 15, 20, 30 ticks)
        # If another spike hits during the M ticks, take the loss (or stopout if adverse >= stake)
        print("\n--- Strategy A: Drift Scalper (Enter right after spike, hold M ticks) ---")
        for m_hold in [3, 5, 10, 15, 20, 30]:
            trades_pnl = []
            stopped_out = 0
            
            for s_idx in spike_indices:
                entry_idx = s_idx + 1
                exit_idx = entry_idx + m_hold
                if exit_idx >= n:
                    continue
                    
                p_entry = prices[entry_idx]
                p_path = prices[entry_idx:exit_idx+1]
                
                if is_boom:
                    # MULTDOWN gains when price drops
                    path_gross = multiplier * stake * (p_entry - p_path) / p_entry
                else:
                    # MULTUP gains when price rises
                    path_gross = multiplier * stake * (p_path - p_entry) / p_entry
                    
                min_adverse = np.min(path_gross)
                if min_adverse <= -stake:
                    pnl = -stake
                    stopped_out += 1
                else:
                    final_gross = path_gross[-1]
                    pnl = final_gross - commission
                    
                trades_pnl.append(pnl)
                
            trades_pnl = np.array(trades_pnl)
            total_trades = len(trades_pnl)
            wins = np.sum(trades_pnl > 0)
            wr = (wins / total_trades) * 100 if total_trades > 0 else 0
            mean_pnl = np.mean(trades_pnl) if total_trades > 0 else 0
            se = np.std(trades_pnl, ddof=1) / np.sqrt(total_trades) if total_trades > 1 else 0
            
            print(f"  Hold {m_hold:2d} ticks: N={total_trades:3d} | WR={wr:5.1f}% | Stopouts={stopped_out:2d} | Mean EV/trade=${mean_pnl:+.4f} | Total PnL=${np.sum(trades_pnl):+.2f} | CI95%=[${mean_pnl-1.96*se:+.4f}, ${mean_pnl+1.96*se:+.4f}]")

        # Strategy B: Spike Hunter
        # On BOOM50: Enter MULTUP when quiet for K ticks (e.g. K = 20, 30, 50, 70 ticks without spike)
        # Hold until 1 spike occurs (or max 50 ticks)
        print("\n--- Strategy B: Spike Hunter (Enter after K ticks without spike, exit on spike) ---")
        for k_quiet in [20, 30, 50, 70]:
            trades_pnl = []
            # Find all points where no spike occurred for k_quiet ticks
            # Walk through ticks
            curr_quiet = 0
            i = 0
            while i < n - 60:
                is_spike = spike_mask[i]
                if is_spike:
                    curr_quiet = 0
                    i += 1
                    continue
                curr_quiet += 1
                if curr_quiet >= k_quiet:
                    # Enter trade
                    entry_idx = i
                    p_entry = prices[entry_idx]
                    # Hold until next spike or max 40 ticks
                    # find next spike
                    sub_spikes = np.where(spike_mask[entry_idx:entry_idx+50])[0]
                    if len(sub_spikes) > 0:
                        exit_idx = entry_idx + sub_spikes[0] + 1
                    else:
                        exit_idx = entry_idx + 40
                        
                    p_exit = prices[exit_idx]
                    if is_boom:
                        gross = multiplier * stake * (p_exit - p_entry) / p_entry
                    else:
                        gross = multiplier * stake * (p_entry - p_exit) / p_entry
                        
                    pnl = gross - commission
                    trades_pnl.append(pnl)
                    # skip to after exit
                    i = exit_idx + 1
                    curr_quiet = 0
                else:
                    i += 1
                    
            trades_pnl = np.array(trades_pnl)
            total_trades = len(trades_pnl)
            if total_trades > 0:
                wins = np.sum(trades_pnl > 0)
                wr = (wins / total_trades) * 100
                mean_pnl = np.mean(trades_pnl)
                se = np.std(trades_pnl, ddof=1) / np.sqrt(total_trades) if total_trades > 1 else 0
                print(f"  Wait {k_quiet:2d} ticks: N={total_trades:3d} | WR={wr:5.1f}% | Mean EV/trade=${mean_pnl:+.4f} | Total PnL=${np.sum(trades_pnl):+.2f} | CI95%=[${mean_pnl-1.96*se:+.4f}, ${mean_pnl+1.96*se:+.4f}]")

    if client.ws:
        await client.ws.close()

if __name__ == '__main__':
    asyncio.run(main())
