"""Probe: descobrir quais contract types tem is_valid_to_sell=true na Deriv.
Testa CALL com diferentes durations para encontrar contratos sellable."""
import asyncio, os, sys, json, time
from dotenv import load_dotenv
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from deriv_client import DerivClient

load_dotenv()

state = {"last_tick": None}

def on_tick(data):
    t = data.get("tick")
    if t and "quote" in t:
        state["last_tick"] = float(t["quote"])

async def main():
    client = DerivClient(app_id=os.getenv("DERIV_APP_ID"), api_token=os.getenv("DERIV_API_TOKEN"), use_demo=True)
    await client.connect()
    await client.subscribe_ticks("1HZ10V", on_tick)
    await asyncio.sleep(2)

    # Testar diferentes durations
    configs = [
        ("CALL", 5, "t"), ("CALL", 10, "t"),
        ("CALL", 15, "s"), ("CALL", 60, "s"),
        ("CALL", 5, "m"), ("CALL", 15, "m"),
        ("HIGHER", 5, "t"), ("HIGHER", 10, "t"),
        ("CALLE", 5, "m"), ("CALLE", 15, "m"),
        ("PUT", 5, "m"), ("PUT", 15, "m"),
    ]

    for ct, dur, unit in configs:
        params = {
            "buy": 1, "price": 10,
            "parameters": {
                "amount": 10, "basis": "stake", "contract_type": ct,
                "currency": "USD", "underlying_symbol": "1HZ10V",
                "duration": dur, "duration_unit": unit,
            }
        }
        if ct in ("HIGHER", "LOWER"):
            params["parameters"]["barrier"] = "+0.33"

        res = await client.send_request(params)
        if "error" in res:
            print(f"{ct} dur={dur}{unit}: BUY erro: {res['error'].get('message','')[:80]}")
            continue

        b = res["buy"]
        cid = b["contract_id"]
        await asyncio.sleep(0.5)

        poc = await client.send_request({"proposal_open_contract": 1, "contract_id": cid})
        c = poc.get("proposal_open_contract", {})
        sellable = c.get("is_valid_to_sell", False)
        bid = c.get("bid_price", 0)
        print(f"{ct} dur={dur}{unit}: sellable={sellable} bid=${bid} "
              f"payout={c.get('payout','?')} buy_price={b.get('buy_price','?')}")

        # Se sellable, tentar vender imediatamente
        if sellable:
            sell_res = await client.send_request({"sell": cid, "price": 0})
            if "error" in sell_res:
                print(f"  -> SELL erro: {sell_res['error'].get('message','')}")
            else:
                print(f"  -> SOLD for ${sell_res['sell'].get('sell_price','?')}")
        else:
            # Esperar expiry
            for _ in range(100):
                poc = await client.send_request({"proposal_open_contract": 1, "contract_id": cid})
                c = poc.get("proposal_open_contract", {})
                if c.get("is_sold"):
                    break
                await asyncio.sleep(0.3)

        await asyncio.sleep(0.5)

    await client.disconnect()

asyncio.run(main())
