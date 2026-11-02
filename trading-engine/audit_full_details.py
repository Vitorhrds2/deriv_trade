import os, json, asyncio
from dotenv import load_dotenv
from deriv_client import DerivClient

load_dotenv()

async def main():
    c = DerivClient(app_id=os.getenv("DERIV_APP_ID"), api_token=os.getenv("DERIV_API_TOKEN"), use_demo=True)
    await c.connect()

    # Get portfolio with full contract details
    po = await c.send_request({"portfolio": 1})
    oc = po.get("portfolio", {}).get("contracts", [])

    print(f"=== {len(oc)} POSIÇÕES ABERTAS — DETALHES COMPLETOS ===\n")

    for x in oc:
        cid = x.get("contract_id")
        # Portfolio already has some info
        print(f"PORTFOLIO: cid={cid} type={x.get('contract_type','')} sym={x.get('underlying','')} "
              f"buy=${float(x.get('buy_price',0)):.2f} payout={x.get('payout',0)} "
              f"longcode={x.get('longcode','')[:80]}")
        await asyncio.sleep(0.05)

    # Get detailed contract info for first 5 of each buy_price type
    print("\n=== DETALHES PROPOSAL_OPEN_CONTRACT (amostra) ===\n")
    seen_prices = set()
    for x in oc:
        bp = float(x.get("buy_price", 0))
        bp_key = round(bp, 2)
        if bp_key in seen_prices:
            continue
        seen_prices.add(bp_key)
        if len(seen_prices) > 5:
            break

        cid = x.get("contract_id")
        r = await c.send_request({"proposal_open_contract": 1, "contract_id": cid})
        ct = r.get("proposal_open_contract", {})
        print(f"\ncid={cid} buy=${bp:.2f}")
        print(f"  contract_type: {ct.get('contract_type','')}")
        print(f"  underlying: {ct.get('underlying','')}")
        print(f"  multiplier: {ct.get('multiplier',0)}")
        print(f"  duration: {ct.get('duration',0)}{ct.get('duration_unit','')}")
        print(f"  amount(stake): {ct.get('amount',0)}")
        print(f"  barrier: {ct.get('barrier','')}")
        print(f"  cancellation: {ct.get('cancellation','')}")
        print(f"  entry_spot: {ct.get('entry_spot',0)}")
        print(f"  current_spot: {ct.get('current_spot',0)}")
        print(f"  profit: {ct.get('profit',0)}")
        print(f"  status: {ct.get('status','')}")
        print(f"  shortcode: {ct.get('shortcode','')}")
        print(f"  longcode: {ct.get('longcode','')[:120]}")
        await asyncio.sleep(0.2)

    # Also check: what does the app likely show? Get balance + portfolio value
    bal = await c.send_request({"balance": 1})
    print(f"\n=== RESUMO FINAL ===")
    print(f"Saldo: ${bal.get('balance',{}).get('balance',0):.2f}")

    # Calculate total unrealized
    total_unreal = 0.0
    for x in oc:
        cid = x.get("contract_id")
        r = await c.send_request({"proposal_open_contract": 1, "contract_id": cid})
        ct = r.get("proposal_open_contract", {})
        total_unreal += float(ct.get("profit", 0))
        await asyncio.sleep(0.05)
    print(f"Unrealized (abertas): ${total_unreal:.2f}")
    print(f"Saldo + Unrealized: ${bal.get('balance',{}).get('balance',0) + total_unreal:.2f}")

    await c.disconnect()

asyncio.run(main())
