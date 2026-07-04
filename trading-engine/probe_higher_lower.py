"""Probe HIGHER/LOWER contracts: descobrir barreiras validas, payouts e estrutura de pricing."""
import asyncio, os, sys, json
from dotenv import load_dotenv
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from deriv_client import DerivClient

load_dotenv()

async def main():
    client = DerivClient(app_id=os.getenv("DERIV_APP_ID"), api_token=os.getenv("DERIV_API_TOKEN"), use_demo=True)
    await client.connect()
    try:
        for ct in ["HIGHER", "LOWER"]:
            for dur in [1, 5, 10]:
                for barrier in ["0.10", "0.50", "1.00", "5.00"]:
                    res = await client.send_request({
                        "proposal": 1, "amount": 10, "basis": "stake",
                        "contract_type": ct, "currency": "USD", "underlying_symbol": "1HZ10V",
                        "duration": dur, "duration_unit": "t", "barrier": barrier,
                    })
                    if "error" in res:
                        msg = res["error"].get("message", "")[:100]
                        print(f"{ct} dur={dur}t barrier={barrier}: ERRO {msg}")
                    else:
                        p = res["proposal"]
                        print(f"{ct} dur={dur}t barrier={barrier}: ask=${p['ask_price']:.4f} "
                              f"payout=${p['payout']:.2f} spot={p.get('spot','?')} "
                              f"id={p['id'][:8]}")
                    await asyncio.sleep(0.2)
        # Also try without barrier (ATM)
        for ct in ["HIGHER", "LOWER"]:
            for dur in [1, 5, 10]:
                res = await client.send_request({
                    "proposal": 1, "amount": 10, "basis": "stake",
                    "contract_type": ct, "currency": "USD", "underlying_symbol": "1HZ10V",
                    "duration": dur, "duration_unit": "t",
                })
                if "error" in res:
                    msg = res["error"].get("message", "")[:100]
                    print(f"{ct} dur={dur}t NO barrier: ERRO {msg}")
                else:
                    p = res["proposal"]
                    print(f"{ct} dur={dur}t NO barrier: ask=${p['ask_price']:.4f} "
                          f"payout=${p['payout']:.2f} spot={p.get('spot','?')} "
                          f"barrier={p.get('barrier','?')} id={p['id'][:8]}")
                await asyncio.sleep(0.2)
    finally:
        await client.disconnect()

asyncio.run(main())
