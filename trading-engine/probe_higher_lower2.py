"""Probe HIGHER/LOWER: descobrir barreiras validas via error.details.barrier_choices."""
import asyncio, os, sys, json
from dotenv import load_dotenv
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from deriv_client import DerivClient

load_dotenv()

async def main():
    client = DerivClient(app_id=os.getenv("DERIV_APP_ID"), api_token=os.getenv("DERIV_API_TOKEN"), use_demo=True)
    await client.connect()
    try:
        # Tentar com barrier absurdo pra forcar a API a devolver barrier_choices
        for ct in ["HIGHER", "LOWER"]:
            for dur in [5, 10]:
                res = await client.send_request({
                    "proposal": 1, "amount": 10, "basis": "stake",
                    "contract_type": ct, "currency": "USD", "underlying_symbol": "1HZ10V",
                    "duration": dur, "duration_unit": "t", "barrier": "999.99",
                })
                if "error" in res:
                    err = res["error"]
                    print(f"\n{ct} dur={dur}t barrier=999.99:")
                    print(f"  message: {err.get('message','')}")
                    details = err.get("details", {})
                    if details:
                        print(f"  details: {json.dumps(details, indent=2, ensure_ascii=False)}")
                    # Tentar barrier_choices da message
                    msg = err.get("message", "")
                    if "barrier" in msg.lower():
                        print(f"  (message menciona barrier)")
                else:
                    p = res["proposal"]
                    print(f"\n{ct} dur={dur}t barrier=999.99: SUCCESS?!")
                    print(f"  ask=${p['ask_price']:.4f} payout=${p['payout']:.2f} "
                          f"spot={p.get('spot','?')} barrier={p.get('barrier','?')}")
                    if "barrier_choices" in p:
                        print(f"  barrier_choices: {p['barrier_choices']}")
                await asyncio.sleep(0.3)

        # Tambem tentar sem barrier mas com contracts_for pra ver a estrutura
        res = await client.send_request({"contracts_for": "1HZ10V"})
        avail = res.get("contracts_for", {}).get("available", [])
        for c in avail:
            if c.get("contract_type") in ("HIGHER", "LOWER"):
                print(f"\ncontracts_for {c['contract_type']}:")
                print(json.dumps(c, indent=2, ensure_ascii=False)[:1500])
    finally:
        await client.disconnect()

asyncio.run(main())
