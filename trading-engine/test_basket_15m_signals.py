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

async def main():
    client = DerivClient(app_id=app_id, api_token=token, use_demo=True)
    await client.connect()
    print("Connected! Account:", client.account_id)
    
    # Fetch 5,000 1-minute candles for WLDEUR and WLDUSD
    for sym in ['WLDEUR', 'WLDUSD', 'WLDGBP']:
        resp = await client.send_request({
            'ticks_history': sym,
            'end': 'latest',
            'count': 5000,
            'style': 'candles',
            'granularity': 60 # 1 minute candles (span: 5000 mins ~ 3.5 days)
        })
        candles = resp.get('candles', [])
        print(f"\n=======================================================")
        print(f"  ANALYZING 15-MINUTE PREDICTABILITY ON {sym} (N={len(candles)} 1m candles)")
        print(f"=======================================================")
        
        if len(candles) < 100:
            print("Insufficient candles.")
            continue
            
        closes = np.array([float(c['close']) for c in candles])
        times = np.array([int(c['epoch']) for c in candles])
        
        # We want to test predicting the direction over the next 15 minutes (15 candles ahead)
        # Target: y = sign(closes[t + 15] - closes[t])
        horizon = 15
        
        valid_indices = range(50, len(closes) - horizon)
        
        # Test Signal 1: Momentum (Trend Following)
        # Lookback = 15, 30, 60 mins
        print("\n--- Signal 1: Momentum / Trend Following (Past return predicts next 15m) ---")
        for lookback in [5, 15, 30, 60]:
            aligned = []
            for t in valid_indices:
                past_ret = closes[t] - closes[t - lookback]
                future_ret = closes[t + horizon] - closes[t]
                if past_ret != 0 and future_ret != 0:
                    aligned.append(np.sign(past_ret) == np.sign(future_ret))
                    
            aligned = np.array(aligned)
            wr = np.mean(aligned) * 100
            n_t = len(aligned)
            se = np.sqrt(0.25 / n_t)
            z = (np.mean(aligned) - 0.5) / se
            p_val = 2 * (1 - stats.norm.cdf(abs(z)))
            print(f"  Lookback {lookback:2d}m: N={n_t} | Win Rate={wr:5.2f}% | Z={z:+.2f} | p={p_val:.4f} (Breakeven ~60.4%)")

        # Test Signal 2: Mean Reversion (RSI / Bollinger Reversion)
        print("\n--- Signal 2: Mean Reversion (Fade extreme moves over next 15m) ---")
        for lookback in [15, 30, 60]:
            aligned = []
            for t in valid_indices:
                # Rolling mean and std
                window = closes[t - lookback:t + 1]
                m = np.mean(window)
                s = np.std(window)
                if s > 0:
                    z_score = (closes[t] - m) / s
                    if abs(z_score) > 2.0: # Extreme deviation: fade it!
                        # Bet direction opposite to z_score
                        bet_dir = -np.sign(z_score)
                        future_ret = closes[t + horizon] - closes[t]
                        if future_ret != 0:
                            aligned.append(bet_dir == np.sign(future_ret))
                            
            aligned = np.array(aligned)
            n_t = len(aligned)
            if n_t > 0:
                wr = np.mean(aligned) * 100
                se = np.sqrt(0.25 / n_t)
                z = (np.mean(aligned) - 0.5) / se
                p_val = 2 * (1 - stats.norm.cdf(abs(z)))
                print(f"  Bollinger (|z|>2.0) Lookback {lookback:2d}m: N={n_t} | Win Rate={wr:5.2f}% | Z={z:+.2f} | p={p_val:.4f}")

    if client.ws:
        await client.ws.close()

if __name__ == '__main__':
    asyncio.run(main())
