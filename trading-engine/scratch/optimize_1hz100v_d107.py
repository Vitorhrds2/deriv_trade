import asyncio, json, os, sys
import numpy as np

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from deriv_client import DerivClient

def calc_rsi(prices, period=14):
    deltas = np.diff(prices)
    seed = deltas[:period+1]
    up = seed[seed >= 0].sum() / period
    down = -seed[seed < 0].sum() / period
    rs = up / (down + 1e-9)
    rsi = np.zeros_like(prices)
    rsi[:period] = 100. - 100. / (1. + rs)

    upval = np.maximum(deltas, 0)
    downval = -np.minimum(deltas, 0)
    
    # Simple rolling
    for i in range(period, len(prices)):
        up = (up * (period - 1) + upval[i-1]) / period
        down = (down * (period - 1) + downval[i-1]) / period
        rs = up / (down + 1e-9)
        rsi[i] = 100. - 100. / (1. + rs)
    return rsi

def calc_ema(prices, span):
    alpha = 2.0 / (span + 1.0)
    ema = np.zeros_like(prices)
    ema[0] = prices[0]
    for i in range(1, len(prices)):
        ema[i] = alpha * prices[i] + (1 - alpha) * ema[i-1]
    return ema

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
    opens = np.array([float(c['open']) for c in candles])

    ema_fast = calc_ema(closes, 5)
    ema_slow = calc_ema(closes, 20)
    rsi = calc_rsi(closes, 14)

    # Simulation setup
    stake = 1.0
    fee = 0.11
    n = len(closes) - 5

    # Strategy tests:
    # We test different TP targets (+15%, +20%, +25%, +30%)
    # And different entry rules:
    # Rule 0: Unconditional MULTUP
    # Rule 1: Trend Following: If EMA5 > EMA20 and RSI > 50 -> MULTUP. If EMA5 < EMA20 and RSI < 50 -> MULTDOWN.
    # Rule 2: Mean Reversion: If RSI < 35 -> MULTUP. If RSI > 65 -> MULTDOWN.

    for rule_name, rule_id in [("Unconditional MULTUP", 0), ("Trend (EMA5/20 + RSI)", 1), ("Mean Reversion (RSI 35/65)", 2)]:
        print(f"\n========================================================")
        print(f"Testing Rule: {rule_name}")
        print(f"========================================================")
        
        for tp in [0.15, 0.20, 0.25, 0.30]:
            trades = 0
            wins = 0
            total_pnl = 0.0

            for i in range(25, n):
                direction = None
                if rule_id == 0:
                    direction = "MULTUP"
                elif rule_id == 1:
                    if ema_fast[i] > ema_slow[i] and rsi[i] > 50:
                        direction = "MULTUP"
                    elif ema_fast[i] < ema_slow[i] and rsi[i] < 50:
                        direction = "MULTDOWN"
                elif rule_id == 2:
                    if rsi[i] < 35:
                        direction = "MULTUP"
                    elif rsi[i] > 65:
                        direction = "MULTDOWN"

                if direction is None:
                    continue

                trades += 1
                entry = closes[i]
                
                # Check 5-minute trajectory
                hit_tp = False
                for step in range(1, 6):
                    cur_h = highs[i + step]
                    cur_l = lows[i + step]
                    if direction == "MULTUP":
                        mfe = (cur_h - entry) / entry * 100.0 # on 100x multiplier, % move in spot is % profit on stake
                    else:
                        mfe = (entry - cur_l) / entry * 100.0

                    if mfe >= tp:
                        hit_tp = True
                        break

                if hit_tp:
                    wins += 1
                    total_pnl += tp
                else:
                    # Cancelled at 4m45s
                    total_pnl -= fee

            if trades > 0:
                wr = wins / trades * 100.0
                ev = total_pnl / trades
                print(f"TP = +{tp*100:.0f}%: Trades = {trades:4d} | Win Rate = {wr:5.2f}% | EV = ${ev:+6.4f} ({ev*100:+5.2f}%) | Net PnL = ${total_pnl:+7.2f}")

if __name__ == "__main__":
    asyncio.run(run())
