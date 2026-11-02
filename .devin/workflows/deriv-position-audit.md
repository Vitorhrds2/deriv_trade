---
description: How to audit and monitor Deriv positions via API for any hypothesis
---

# Deriv Position Audit

## Prerequisites

- `.env` file in `trading-engine/` with `DERIV_APP_ID` and `DERIV_API_TOKEN`
- `deriv_client.py` and `python-dotenv` installed

## Quick Audit Script Template

```python
import os, asyncio
from dotenv import load_dotenv
from deriv_client import DerivClient

load_dotenv()

async def main():
    c = DerivClient(app_id=os.getenv("DERIV_APP_ID"), api_token=os.getenv("DERIV_API_TOKEN"), use_demo=True)
    await c.connect()

    # Balance
    bal = await c.send_request({"balance": 1})
    print(f"Saldo: ${bal.get('balance',{}).get('balance',0):.2f}")

    # Open positions
    po = await c.send_request({"portfolio": 1})
    oc = po.get("portfolio", {}).get("contracts", [])
    print(f"Posições abertas: {len(oc)}")

    # For each open position, calculate profit manually
    for x in oc:
        cid = x.get("contract_id")
        sc = x.get("shortcode", "")
        parts = sc.split("_")
        stake = float(parts[2]) if len(parts) > 2 else 0
        mult = int(parts[3]) if len(parts) > 3 else 0
        purchase_ts = int(parts[4]) if len(parts) > 4 else 0
        sym = x.get("underlying_symbol", "")
        typ = x.get("contract_type", "")

        # Get entry spot from ticks_history
        hist = await c.send_request({"ticks_history": sym, "start": purchase_ts - 5, "end": purchase_ts + 5, "count": 1, "style": "ticks"})
        entry = float(hist["history"]["prices"][-1]) if "history" in hist else 0

        # Get current spot
        tick = await c.send_request({"ticks": sym})
        curr = float(tick["tick"]["quote"]) if "tick" in tick else 0

        # Calculate profit
        if entry > 0 and curr > 0 and stake > 0 and mult > 0:
            if typ == "MULTDOWN":
                profit = ((entry - curr) / entry) * stake * mult
            elif typ == "MULTUP":
                profit = ((curr - entry) / entry) * stake * mult
            else:
                profit = 0
        else:
            profit = 0

        print(f"cid={cid} {typ} {sym} {mult}x entry={entry:.2f} curr={curr:.2f} profit=${profit:.2f}")
        await asyncio.sleep(0.1)

    # Closed positions (last 24h)
    from datetime import datetime, timezone, timedelta
    now = datetime.now(timezone.utc)
    df, dt2 = int((now - timedelta(hours=24)).timestamp()), int(now.timestamp())
    closed, off = [], 0
    while True:
        r = await c.send_request({"profit_table": 1, "description": 1, "date_from": df, "date_to": dt2, "limit": 100, "offset": off})
        t = r.get("profit_table", {}).get("transactions", [])
        if not t: break
        closed.extend(t)
        if len(t) < 100: break
        off += 100
        await asyncio.sleep(0.3)

    total_pnl = sum(float(t.get("sell_price", 0)) - float(t.get("buy_price", 0)) for t in closed)
    print(f"\nFechadas 24h: {len(closed)} | PnL: ${total_pnl:.2f}")

    await c.disconnect()

asyncio.run(main())
```

## Key API Notes

- `proposal_open_contract` may return empty fields for multiplier contracts — calculate profit manually
- Shortcode format: `MULTDOWN_1HZ10V_10.00_400_<purchase_ts>_<expiry_ts>_5m_0.00_N1_0`
- Multiplier contracts with expired cancellation become perpetual (expiry 2126)
- Rate limiting affects SELL more than CANCEL
- Use `ticks_history` to get entry spot at purchase timestamp
- Use `ticks` to get current spot
