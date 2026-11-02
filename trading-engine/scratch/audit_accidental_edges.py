import asyncio, os, sys
import numpy as np

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from deriv_client import DerivClient
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

async def main():
    token = os.environ.get('DERIV_DEMO_API_KEY')
    client = DerivClient(api_token=token, app_id=1089)
    await client.connect()
    
    test_specs = [
        ('1HZ10V', 400, 0.04),
        ('1HZ50V', 80, 0.04),
        ('1HZ75V', 100, 0.08),
        ('R_75', 100, 0.08),
        ('R_100', 100, 0.11),
        ('1HZ100V', 100, 0.11),
    ]
    
    for sym, mult, fee in test_specs:
        res = await client.send_request({
            'ticks_history': sym,
            'adjust_start_time': 1,
            'count': 1000,
            'end': 'latest',
            'style': 'candles',
            'granularity': 60
        })
        candles = res.get('candles', [])
        if not candles:
            print(f"No candles for {sym}")
            continue
        closes = np.array([float(c['close']) for c in candles])
        highs = np.array([float(c['high']) for c in candles])
        lows = np.array([float(c['low']) for c in candles])
        
        n = len(candles) - 5
        mfes = []
        for i in range(n):
            entry = closes[i]
            h5 = np.max(highs[i+1:i+6])
            l5 = np.min(lows[i+1:i+6])
            up_mfe = (h5 - entry) / entry * mult
            down_mfe = (entry - l5) / entry * mult
            mfes.append((up_mfe, down_mfe))
            
        up_mfes = np.array([m[0] for m in mfes])
        down_mfes = np.array([m[1] for m in mfes])
        
        print(f"\n================ {sym} ({mult}x, Fee = ${fee:.2f}) ================")
        for target in [0.10, 0.15, 0.20, 0.30, 0.50]:
            up_wins = float(np.mean(up_mfes >= target))
            down_wins = float(np.mean(down_mfes >= target))
            avg_wr = (up_wins + down_wins) / 2.0
            ev = avg_wr * target - (1.0 - avg_wr) * fee
            print(f"  Target +{int(target*100)}%: WR = {avg_wr*100:.1f}% (UP: {up_wins*100:.1f}%, DOWN: {down_wins*100:.1f}%) | EV = ${ev:+.4f} ({ev*100:+.2f}%)")
            
    await client.disconnect()

if __name__ == '__main__':
    asyncio.run(main())
