"""Probe de proposal (cotacao real) para os 5 produtos novos, so leitura."""
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
        print(json.dumps(res.get("proposal", res), indent=2, ensure_ascii=False)[:2500])
    await asyncio.sleep(0.3)


async def main():
    client = DerivClient(app_id=APP_ID, api_token=API_TOKEN, use_demo=True)
    await client.connect()
    try:
        # TICKHIGH sem selected_tick
        await show(client, "TICKHIGH sem selected_tick", {
            "proposal": 1, "amount": 10, "basis": "stake", "contract_type": "TICKHIGH",
            "currency": "USD", "underlying_symbol": SYMBOL, "duration": 5, "duration_unit": "t",
        })
        # TICKHIGH com selected_tick=3
        await show(client, "TICKHIGH selected_tick=3", {
            "proposal": 1, "amount": 10, "basis": "stake", "contract_type": "TICKHIGH",
            "currency": "USD", "underlying_symbol": SYMBOL, "duration": 5, "duration_unit": "t",
            "selected_tick": 3,
        })
        # RUNHIGH duration=2t (minimo)
        await show(client, "RUNHIGH duration=2t", {
            "proposal": 1, "amount": 10, "basis": "stake", "contract_type": "RUNHIGH",
            "currency": "USD", "underlying_symbol": SYMBOL, "duration": 2, "duration_unit": "t",
        })
        # RUNHIGH duration=5t (max)
        await show(client, "RUNHIGH duration=5t", {
            "proposal": 1, "amount": 10, "basis": "stake", "contract_type": "RUNHIGH",
            "currency": "USD", "underlying_symbol": SYMBOL, "duration": 5, "duration_unit": "t",
        })
        # ASIANU duration=5t
        await show(client, "ASIANU duration=5t", {
            "proposal": 1, "amount": 10, "basis": "stake", "contract_type": "ASIANU",
            "currency": "USD", "underlying_symbol": SYMBOL, "duration": 5, "duration_unit": "t",
        })
        # TICKHIGH/TICKLOW em todas as posicoes
        for pos in [1, 2, 4, 5]:
            await show(client, f"TICKHIGH selected_tick={pos}", {
                "proposal": 1, "amount": 10, "basis": "stake", "contract_type": "TICKHIGH",
                "currency": "USD", "underlying_symbol": SYMBOL, "duration": 5, "duration_unit": "t",
                "selected_tick": pos,
            })
        for pos in [1, 2, 3, 4, 5]:
            await show(client, f"TICKLOW selected_tick={pos}", {
                "proposal": 1, "amount": 10, "basis": "stake", "contract_type": "TICKLOW",
                "currency": "USD", "underlying_symbol": SYMBOL, "duration": 5, "duration_unit": "t",
                "selected_tick": pos,
            })
        # RESETCALL sem barrier (deve ser sempre ATM)
        await show(client, "RESETCALL duration=5m sem barrier", {
            "proposal": 1, "amount": 10, "basis": "stake", "contract_type": "RESETCALL",
            "currency": "USD", "underlying_symbol": SYMBOL, "duration": 5, "duration_unit": "m",
        })
        await show(client, "RESETPUT duration=5m sem barrier", {
            "proposal": 1, "amount": 10, "basis": "stake", "contract_type": "RESETPUT",
            "currency": "USD", "underlying_symbol": SYMBOL, "duration": 5, "duration_unit": "m",
        })
        # TURBOSLONG com stake maior
        await show(client, "TURBOSLONG barrier=42.27 stake=25", {
            "proposal": 1, "amount": 25, "basis": "stake", "contract_type": "TURBOSLONG",
            "currency": "USD", "underlying_symbol": SYMBOL, "duration": 1, "duration_unit": "d",
            "barrier": "42.27",
        })
        await show(client, "TURBOSLONG barrier=2.51 stake=25", {
            "proposal": 1, "amount": 25, "basis": "stake", "contract_type": "TURBOSLONG",
            "currency": "USD", "underlying_symbol": SYMBOL, "duration": 1, "duration_unit": "d",
            "barrier": "2.51",
        })
    finally:
        await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
