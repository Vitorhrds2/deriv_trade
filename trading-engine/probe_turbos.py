"""Probe focado em Turbos -- confirmar sinal de barreira (LONG/SHORT) e estrutura de payout."""
import asyncio
import json
import os
import sys

from dotenv import load_dotenv
from deriv_client import DerivClient

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

load_dotenv()
API_TOKEN = os.getenv("DERIV_API_TOKEN")
APP_ID = os.getenv("DERIV_APP_ID")
SYMBOL = "1HZ100V"


async def show(client, label, payload):
    res = await client.send_request(payload)
    print(f"\n--- {label} ---")
    print(json.dumps(payload, ensure_ascii=False))
    if "error" in res:
        print(f"ERRO: {res['error'].get('message')} (code={res['error'].get('code')})")
    else:
        print(json.dumps(res.get("proposal", res), indent=2, ensure_ascii=False))
    await asyncio.sleep(0.3)


async def get_fresh_barrier(client, contract_type, duration_val, duration_unit, placeholder):
    res = await client.send_request({
        "proposal": 1, "amount": 25, "basis": "stake", "contract_type": contract_type,
        "currency": "USD", "underlying_symbol": SYMBOL, "duration": duration_val,
        "duration_unit": duration_unit, "barrier": placeholder,
    })
    msg = res.get("error", {}).get("message", "")
    first = msg.split("are ")[-1].split(",")[0].strip().rstrip(".")
    return first


async def main():
    client = DerivClient(app_id=APP_ID, api_token=API_TOKEN, use_demo=True)
    await client.connect()
    try:
        b = await get_fresh_barrier(client, "TURBOSLONG", 1, "d", "-2.51")
        await show(client, f"TURBOSLONG barrier={b} stake=25 dur=1d (barreira fresca)", {
            "proposal": 1, "amount": 25, "basis": "stake", "contract_type": "TURBOSLONG",
            "currency": "USD", "underlying_symbol": SYMBOL, "duration": 1, "duration_unit": "d",
            "barrier": b,
        })
        b = await get_fresh_barrier(client, "TURBOSSHORT", 1, "d", "2.51")
        await show(client, f"TURBOSSHORT barrier={b} stake=25 dur=1d (barreira fresca)", {
            "proposal": 1, "amount": 25, "basis": "stake", "contract_type": "TURBOSSHORT",
            "currency": "USD", "underlying_symbol": SYMBOL, "duration": 1, "duration_unit": "d",
            "barrier": b,
        })
        b = await get_fresh_barrier(client, "TURBOSLONG", 5, "m", "-2.51")
        await show(client, f"TURBOSLONG barrier={b} stake=25 dur=5m (testar duracao curta)", {
            "proposal": 1, "amount": 25, "basis": "stake", "contract_type": "TURBOSLONG",
            "currency": "USD", "underlying_symbol": SYMBOL, "duration": 5, "duration_unit": "m",
            "barrier": b,
        })
    finally:
        await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
