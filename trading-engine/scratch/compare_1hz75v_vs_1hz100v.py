import asyncio, json, os, sys
import numpy as np

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from deriv_client import DerivClient

async def test_symbol(client, symbol, mult, fee):
    res = await client.send_request({
        'ticks_history': symbol,
        'adjust_start_time': 1,
        'count': 5000,
        'end': 'latest',
        'style': 'candles',
        'granularity': 60
    })
    candles = res.get('candles', [])
    if not candles:
        print(f"Error fetching candles for {symbol}")
        return

    closes = np.array([float(c['close']) for c in candles])
    highs = np.array([float(c['high']) for c in candles])
    lows = np.array([float(c['low']) for c in candles])
    opens = np.array([float(c['open']) for c in candles])
    n = len(closes) - 5

    mfe_up = np.zeros(n)
    mfe_down = np.zeros(n)
    for i in range(n):
        entry = closes[i]
        mfe_up[i] = (np.max(highs[i+1:i+6]) - entry) / entry * 100.0 * (mult / 100.0) # scaled to $1 stake
        mfe_down[i] = (entry - np.min(lows[i+1:i+6])) / entry * 100.0 * (mult / 100.0)

    # 1. Unconditional MULTUP
    print(f"\n========================================================")
    print(f"Analysis for {symbol} (Mult {mult}x, Fee = ${fee:.2f})")
    print(f"========================================================")
    for tp in [0.15, 0.20, 0.25, 0.30]:
        p_hit = np.mean(mfe_up >= tp)
        ev = p_hit * tp - (1.0 - p_hit) * fee
        print(f"  Unconditional MULTUP | TP +{tp*100:4.1f}%: Win Rate = {p_hit*100:5.2f}% | EV = ${ev:+6.4f} ({ev*100:+5.2f}%)")

    # 2. Directional Momentum (Green candle -> MULTUP, Red candle -> MULTDOWN)
    mfe_mom = np.zeros(n)
    for i in range(n):
        if closes[i] >= opens[i]:
            mfe_mom[i] = mfe_up[i]
        else:
            mfe_mom[i] = mfe_down[i]

    print(f"--- With 1m Momentum Filter (Trend following) ---")
    for tp in [0.15, 0.20, 0.25, 0.30]:
        p_hit = np.mean(mfe_mom >= tp)
        ev = p_hit * tp - (1.0 - p_hit) * fee
        print(f"  Momentum Filter      | TP +{tp*100:4.1f}%: Win Rate = {p_hit*100:5.2f}% | EV = ${ev:+6.4f} ({ev*100:+5.2f}%)")

async def run():
    client = DerivClient()
    await client.connect()
    # Test 1HZ75V (mult 100, fee 0.08)
    await test_symbol(client, "1HZ75V", 100, 0.08)
    # Test 1HZ100V (mult 100, fee 0.11)
    await test_symbol(client, "1HZ100V", 100, 0.11)
    # Test R_100 (mult 100, fee 0.11) - 2s tick comparison
    await test_symbol(client, "R_100", 100, 0.11)
    await client.disconnect()

if __name__ == "__main__":
    asyncio.run(run())
