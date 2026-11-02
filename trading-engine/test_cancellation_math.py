import gzip
import json
import numpy as np

with gzip.open('trading-engine/d107_exact_7d_manual_scenarios.ticks.json.gz', 'rt') as f:
    data = json.load(f)

prices = np.array(data['demo']['prices'], dtype=np.float64)
times = np.array(data['demo']['times'], dtype=np.int64)
n_ticks = len(prices)
print(f"Loaded {n_ticks:,} ticks.")

# Parameters
stake = 10.0
multiplier = 400
fee = 0.42
commission = 0.20
duration_s = 300 # 5 minutes
step_s = 60 # enter a trade every 60 seconds

def evaluate_strategy(direction_mode='alternate'):
    pnls = []
    wins = 0
    losses = 0
    cancels = 0
    sells = 0
    
    i = 0
    trade_idx = 0
    while i < n_ticks:
        t_entry = times[i]
        p_entry = prices[i]
        t_exit = t_entry + duration_s
        
        idx_exit = np.searchsorted(times, t_exit)
        if idx_exit >= n_ticks:
            break
            
        directions = []
        if direction_mode == 'up':
            directions = ['MULTUP']
        elif direction_mode == 'down':
            directions = ['MULTDOWN']
        elif direction_mode == 'alternate':
            directions = ['MULTUP' if trade_idx % 2 == 0 else 'MULTDOWN']
        elif direction_mode == 'straddle':
            directions = ['MULTUP', 'MULTDOWN']
            
        for d in directions:
            path = prices[i:idx_exit+1]
            if d == 'MULTUP':
                path_gross = multiplier * stake * (path - p_entry) / p_entry
            else:
                path_gross = multiplier * stake * (p_entry - path) / p_entry
                
            final_gross = path_gross[-1]
            min_gross = np.min(path_gross)
            
            if min_gross <= -stake:
                pnl = -fee
                cancels += 1
                losses += 1
            else:
                net_at_exit = final_gross - commission
                if net_at_exit <= 0:
                    pnl = -fee
                    cancels += 1
                    losses += 1
                else:
                    pnl = net_at_exit - fee
                    sells += 1
                    if pnl > 0:
                        wins += 1
                    else:
                        losses += 1
            pnls.append(pnl)
            
        trade_idx += 1
        next_t = t_entry + step_s
        i = np.searchsorted(times, next_t)
        
    pnls = np.array(pnls)
    n = len(pnls)
    mean_pnl = float(np.mean(pnls))
    se = float(np.std(pnls, ddof=1) / np.sqrt(n))
    ci_lo = mean_pnl - 1.96 * se
    ci_hi = mean_pnl + 1.96 * se
    wr = (wins / n) * 100
    
    print(f"=== Direction: {direction_mode} ===")
    print(f"Trades: {n:,} | Wins: {wins} ({wr:.2f}%) | Cancels: {cancels} | Sells: {sells}")
    print(f"Total PnL: ${float(np.sum(pnls)):+.2f}")
    print(f"EV/trade: ${mean_pnl:+.4f} | CI95%: [${ci_lo:+.4f}, ${ci_hi:+.4f}]")
    print()

evaluate_strategy('up')
evaluate_strategy('down')
evaluate_strategy('alternate')
evaluate_strategy('straddle')
