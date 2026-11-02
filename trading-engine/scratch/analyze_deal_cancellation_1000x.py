import asyncio, json, os, sys
import numpy as np

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from deriv_client import DerivClient

async def run():
    client = DerivClient()
    await client.connect()
    # Fetch 5000 1-minute candles for 1HZ10V
    res = await client.send_request({
        'ticks_history': '1HZ10V',
        'adjust_start_time': 1,
        'count': 5000,
        'end': 'latest',
        'style': 'candles',
        'granularity': 60
    })
    await client.disconnect()

    candles = res.get('candles', [])
    print(f"Fetched {len(candles)} 1m candles for 1HZ10V")
    if not candles:
        return

    closes = np.array([float(c['close']) for c in candles])
    opens = np.array([float(c['open']) for c in candles])
    highs = np.array([float(c['high']) for c in candles])
    lows = np.array([float(c['low']) for c in candles])

    # 5-minute return: close[t+5] vs close[t]
    ret_5m = (closes[5:] - closes[:-5]) / closes[:-5]

    frac_up_10bps = np.mean(ret_5m >= 0.0010)
    frac_up_15bps = np.mean(ret_5m >= 0.0015)
    frac_up_20bps = np.mean(ret_5m >= 0.0020)
    frac_down_10bps = np.mean(ret_5m <= -0.0010)

    print("Distribution of 5-minute terminal returns on 1HZ10V:")
    print(f"  P(Ret >= +0.10% / +100% on 1000x): {frac_up_10bps*100:.2f}%")
    print(f"  P(Ret >= +0.15% / +150% on 1000x): {frac_up_15bps*100:.2f}%")
    print(f"  P(Ret >= +0.20% / +200% on 1000x): {frac_up_20bps*100:.2f}%")
    print(f"  P(Ret <= -0.10% / -100% on 1000x): {frac_down_10bps*100:.2f}%")

    # MAX return within the 5m window: (max(high[t+1..t+5]) - close[t]) / close[t]
    max_ret_5m = np.zeros(len(closes) - 5)
    min_ret_5m = np.zeros(len(closes) - 5)
    for i in range(len(closes) - 5):
        max_ret_5m[i] = (np.max(highs[i+1:i+6]) - closes[i]) / closes[i]
        min_ret_5m[i] = (np.min(lows[i+1:i+6]) - closes[i]) / closes[i]

    print("\nMaximum favorable excursion (MFE) within the 5-minute window:")
    print(f"  P(Peak MFE >= +0.10% / +100%): {np.mean(max_ret_5m >= 0.0010)*100:.2f}%")
    print(f"  P(Peak MFE >= +0.15% / +150%): {np.mean(max_ret_5m >= 0.0015)*100:.2f}%")
    print(f"  P(Peak MFE >= +0.20% / +200%): {np.mean(max_ret_5m >= 0.0020)*100:.2f}%")
    print(f"  P(Peak MFE >= +0.30% / +300%): {np.mean(max_ret_5m >= 0.0030)*100:.2f}%")

    # In 1000x leverage:
    # If MFE >= +0.15%, an auto-sell at 1.5x triggers profit of +$0.50!
    # If not triggered and trade is losing at 4m45s, Deal Cancellation refunds stake with fee of -$0.10!
    # Let us compute the EV of this Take-Profit + Cancellation strategy:
    p_take_profit_15 = np.mean(max_ret_5m >= 0.0015)
    p_loss_15 = 1.0 - p_take_profit_15
    ev_15 = p_take_profit_15 * 0.50 - p_loss_15 * 0.10
    print("\nStrategy 1: 1000x Multiplier, TP = 1.5x (+0.15% move), Deal Cancellation 5m (Fee = -$0.10):")
    print(f"  Win Rate (hits +150% in 5m): {p_take_profit_15*100:.2f}%")
    print(f"  EV per $1 stake: ${ev_15:+.4f} ({ev_15*100:+.2f}%)")

    p_take_profit_10 = np.mean(max_ret_5m >= 0.0010)
    p_loss_10 = 1.0 - p_take_profit_10
    ev_10 = p_take_profit_10 * 0.25 - p_loss_10 * 0.10 # e.g. close at 1.25x (+0.10% move, fee amortized)
    print("\nStrategy 2: 1000x Multiplier, TP = 1.25x (+0.10% move), Deal Cancellation 5m:")
    print(f"  Win Rate (hits +100% in 5m): {p_take_profit_10*100:.2f}%")
    print(f"  EV per $1 stake: ${ev_10:+.4f} ({ev_10*100:+.2f}%)")

if __name__ == "__main__":
    asyncio.run(run())
