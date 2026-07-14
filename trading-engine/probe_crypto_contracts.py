import asyncio, os, sys
sys.path.insert(0, ".")
from deriv_client import DerivClient

async def main():
    client = DerivClient(app_id=os.getenv("DERIV_APP_ID"), api_token=os.getenv("DERIV_API_TOKEN"), use_demo=True)
    await client.connect()
    for ct in ["CALL", "PUT", "MULTUP", "MULTDOWN", "ASIANU", "ASIAND", "DIGITOVER", "DIGITUNDER", "DIGITMATCH", "DIGITEVEN", "DIGITODD", "ONETOUCH", "NOTOUCH", "RANGE", "UPORDOWN", "EXPIRYRANGE", "EXPIRYMISS", "HIGHER", "LOWER", "STAYIN", "GOOUT"]:
        for dur, unit in [(1, "d"), (1, "h"), (10, "t"), (5, "m")]:
            payload = {"proposal": 1, "amount": 1.0, "basis": "stake", "contract_type": ct, "currency": "USD", "underlying_symbol": "cryBTCUSD", "duration": dur, "duration_unit": unit}
            try:
                res = await asyncio.wait_for(client.send_request(payload), timeout=10)
                if "error" not in res:
                    p = res.get("proposal", {})
                    print(f"  {ct:12s} {dur}{unit}: ask={p.get('ask_price')} payout={p.get('payout')} longcode={p.get('longcode','')[:80]}")
                    break
            except:
                pass
    await client.disconnect()

asyncio.run(main())
