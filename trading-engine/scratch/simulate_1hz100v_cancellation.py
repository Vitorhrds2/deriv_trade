import asyncio, json, os, sys
import numpy as np

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from deriv_client import DerivClient

async def run():
    client = DerivClient()
    await client.connect()
    res = await client.send_request({
        'ticks_history': '1HZ100V',
        'adjust_start_time': 1,
        'count': 5000,
        'end': 'latest',
        'style': 'candles',
        'granularity': 60
    })
    await client.disconnect()

    candles = res.get('candles', [])
    print(f"Fetched {len(candles)} 1m candles for 1HZ100V")
    if not candles:
        return

    closes = np.array([float(c['close']) for c in candles])
    highs = np.array([float(c['high']) for c in candles])
    lows = np.array([float(c['low']) for c in candles])

    n = len(closes) - 5
    mfe_up = np.zeros(n)
    mfe_down = np.zeros(n)

    for i in range(n):
        entry = closes[i]
        mfe_up[i] = (np.max(highs[i+1:i+6]) - entry) / entry * 100.0
        mfe_down[i] = (entry - np.min(lows[i+1:i+6])) / entry * 100.0

    print(f"Analysis of {n} 5-minute trading windows in 1HZ100V (Mult 100x):")
    print(f"  P(Peak MFE >= +0.25% / +25% profit on stake): {np.mean(mfe_up >= 0.25)*100:.2f}%")
    print(f"  P(Peak MFE >= +0.35% / +35% profit on stake): {np.mean(mfe_up >= 0.35)*100:.2f}%")
    print(f"  P(Peak MFE >= +0.50% / +50% profit on stake): {np.mean(mfe_up >= 0.50)*100:.2f}%")
    print(f"  P(Peak MFE >= +0.75% / +75% profit on stake): {np.mean(mfe_up >= 0.75)*100:.2f}%")
    print(f"  P(Peak MFE >= +1.00% / +100% profit on stake): {np.mean(mfe_up >= 1.00)*100:.2f}%")

    print("\nDeal Cancellation Strategy Results (Mult 100x, Fee = -$0.11):")
    for tp in [0.20, 0.25, 0.30, 0.35, 0.40, 0.50, 0.60, 0.75]:
        p_hit = np.mean(mfe_up >= tp)
        ev = p_hit * tp - (1.0 - p_hit) * 0.11
        print(f"  TP Target = +{tp*100:4.1f}% (+${tp:4.2f}): Hit Rate = {p_hit*100:5.2f}% | EV = ${ev:+6.4f} ({ev*100:+5.2f}%)")

    # What if we select direction using 1m momentum (if close > open, buy MULTUP; else buy MULTDOWN)?
    opens = np.array([float(c['open']) for c in candles])
    mfe_dir = np.zeros(n)
    for i in range(n):
        if closes[i] >= opens[i]:
            mfe_dir[i] = mfe_up[i]
        else:
            mfe_dir[i] = mfe_down[i]

    print("\nWith Directional Momentum (Follow previous 1m bar):")
    for tp in [0.20, 0.25, 0.30, 0.35, 0.40, 0.50, 0.60, 0.75]:
        p_hit = np.mean(mfe_dir >= tp)
        ev = p_hit * tp - (1.0 - p_hit) * 0.11
        print(f"  TP Target = +{tp*100:4.1f}% (+${tp:4.2f}): Hit Rate = {p_hit*100:5.2f}% | EV = ${ev:+6.4f} ({ev*100:+5.2f}%)")

if __name__ == "__main__":
    asyncio.run(run())
