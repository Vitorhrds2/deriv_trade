import os, asyncio
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv
from deriv_client import DerivClient

load_dotenv()

async def main():
    c = DerivClient(app_id=os.getenv("DERIV_APP_ID"), api_token=os.getenv("DERIV_API_TOKEN"), use_demo=True)
    await c.connect()

    now = datetime.now(timezone.utc)
    # Get 1HZ10V price over last 24h (candles 1h)
    for sym, gran in [("1HZ10V", 3600), ("1HZ100V", 3600)]:
        r = await c.send_request({
            "ticks_history": sym,
            "start": int((now - timedelta(hours=24)).timestamp()),
            "end": int(now.timestamp()),
            "granularity": gran,
            "style": "candles",
            "count": 24
        })
        if "candles" in r:
            candles = r["candles"]
            print(f"\n=== {sym} (1h candles, últimas 24h) ===")
            high = max(float(c["high"]) for c in candles)
            low = min(float(c["low"]) for c in candles)
            open_p = float(candles[0]["open"])
            close_p = float(candles[-1]["close"])
            change = (close_p - open_p) / open_p * 100
            print(f"  Open(24h ago): {open_p:.2f}")
            print(f"  High: {high:.2f}")
            print(f"  Low: {low:.2f}")
            print(f"  Close(now): {close_p:.2f}")
            print(f"  Change: {change:+.2f}%")
            print(f"  Range: {(high-low)/open_p*100:.2f}%")
            for c in candles:
                t = datetime.fromtimestamp(c["epoch"], tz=timezone.utc).strftime("%H:%M")
                print(f"    {t}: O={float(c['open']):.2f} H={float(c['high']):.2f} L={float(c['low']):.2f} C={float(c['close']):.2f}")
        await asyncio.sleep(0.5)

    await c.disconnect()

asyncio.run(main())
