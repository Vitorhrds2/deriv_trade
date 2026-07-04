"""Probe HIGHER/LOWER com barriers relativos descobertos via contracts_for."""
import asyncio, os, sys, json
from dotenv import load_dotenv
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from deriv_client import DerivClient

load_dotenv()

async def main():
    client = DerivClient(app_id=os.getenv("DERIV_APP_ID"), api_token=os.getenv("DERIV_API_TOKEN"), use_demo=True)
    await client.connect()
    try:
        # Usar barriers relativos (+0.33 e variacoes) para tick contracts
        barriers_to_try = ["+0.33", "+0.10", "+0.20", "+0.50", "+1.00", "-0.33", "-0.10", "+0.01"]
        for ct in ["HIGHER", "LOWER"]:
            for dur in [5, 10]:
                for barrier in barriers_to_try:
                    res = await client.send_request({
                        "proposal": 1, "amount": 10, "basis": "stake",
                        "contract_type": ct, "currency": "USD", "underlying_symbol": "1HZ10V",
                        "duration": dur, "duration_unit": "t", "barrier": barrier,
                    })
                    if "error" in res:
                        msg = res["error"].get("message", "")[:80]
                        details = res.get("error", {}).get("details", {})
                        bc = details.get("barrier_choices", [])
                        extra = f" choices={bc}" if bc else ""
                        print(f"{ct} dur={dur}t barrier={barrier}: ERRO {msg}{extra}")
                    else:
                        p = res["proposal"]
                        print(f"{ct} dur={dur}t barrier={barrier}: ask=${p['ask_price']:.4f} "
                              f"payout=${p['payout']:.2f} spot={p.get('spot','?')} "
                              f"barrier={p.get('barrier','?')}")
                        if "barrier_choices" in p:
                            print(f"  barrier_choices: {p['barrier_choices']}")
                    await asyncio.sleep(0.2)
    finally:
        await client.disconnect()

asyncio.run(main())
