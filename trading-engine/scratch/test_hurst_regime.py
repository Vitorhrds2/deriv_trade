import asyncio, json, os, sys
import numpy as np

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from deriv_client import DerivClient

def calc_hurst(ts):
    """Calculate Hurst exponent using Rescaled Range (R/S) analysis."""
    ts = np.asarray(ts)
    if len(ts) < 20:
        return 0.5
    
    # Calculate log returns
    returns = np.diff(np.log(ts))
    n = len(returns)
    if n < 20:
        return 0.5
        
    # Sizes to divide into
    sizes = [10, 20, 50, n // 2]
    sizes = [s for s in sizes if s < n and s >= 5]
    if len(sizes) < 2:
        return 0.5
        
    rs_values = []
    for s in sizes:
        chunks = n // s
        rs_chunk = []
        for i in range(chunks):
            chunk = returns[i*s : (i+1)*s]
            m = np.mean(chunk)
            y = np.cumsum(chunk - m)
            r = np.max(y) - np.min(y)
            s_std = np.std(chunk, ddof=1)
            if s_std > 1e-9:
                rs_chunk.append(r / s_std)
        if rs_chunk:
            rs_values.append(np.mean(rs_chunk))
        else:
            rs_values.append(1.0)
            
    # Regression log(R/S) vs log(s)
    poly = np.polyfit(np.log(sizes), np.log(rs_values), 1)
    return float(poly[0])

async def run():
    client = DerivClient()
    await client.connect()
    
    for sym in ["1HZ100V", "R_100"]:
        res = await client.send_request({
            'ticks_history': sym,
            'count': 1000,
            'end': 'latest',
            'style': 'candles',
            'granularity': 60
        })
        candles = res.get('candles', [])
        closes = [float(c['close']) for c in candles]
        
        # Calculate full series Hurst
        h_full = calc_hurst(closes)
        
        # Calculate rolling 100-candle Hurst
        recent_hurst = [calc_hurst(closes[i-100:i]) for i in range(100, len(closes), 50)]
        
        print(f"==================================================")
        print(f"SYMBOL: {sym}")
        print(f"Full 1000m Hurst Exponent: {h_full:.4f}")
        print(f"Recent rolling Hurst: {[round(h, 3) for h in recent_hurst[-5:]]}")
        
        if h_full < 0.45:
            regime = "STRONG MEAN REVERSION (RSI EXTREMES OPTIMAL)"
        elif h_full > 0.55:
            regime = "STRONG MOMENTUM / TRENDING (BREAKOUT OPTIMAL)"
        else:
            regime = "BALANCED / RANDOM DRIFT (CANCELLATION CONVEXITY)"
        print(f"Dominant Structural Regime: {regime}")

    await client.disconnect()

if __name__ == "__main__":
    asyncio.run(run())
