import os, json, asyncio
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv
from deriv_client import DerivClient

load_dotenv()

async def main():
    c = DerivClient(app_id=os.getenv("DERIV_APP_ID"), api_token=os.getenv("DERIV_API_TOKEN"), use_demo=True)
    await c.connect()
    now = datetime.now(timezone.utc)
    df, dt2 = int((now - timedelta(hours=24)).timestamp()), int(now.timestamp())

    # Get closed positions - just first 100 to check OTHER category
    r = await c.send_request({"profit_table":1,"description":1,"date_from":df,"date_to":dt2,"limit":100,"offset":0})
    txns = r.get("profit_table",{}).get("transactions",[])

    # Check what fields are available in profit_table directly
    print("=== CAMPOS DISPONÍVEIS NO PROFIT_TABLE ===")
    if txns:
        print(json.dumps(txns[0], indent=2))
        print(f"\nTotal campos: {list(txns[0].keys())}")

    # Check a few "OTHER" contracts
    print("\n=== AMOSTRA DE CONTRATOS 'OTHER' ===")
    for t in txns[:10]:
        cid = t["contract_id"]
        r2 = await c.send_request({"proposal_open_contract":1,"contract_id":cid})
        ct = r2.get("proposal_open_contract",{})
        print(f"cid={cid} type='{ct.get('contract_type','')}' sc='{ct.get('shortcode','')}' "
              f"longcode='{ct.get('longcode','')[:80]}' "
              f"buy=${float(t.get('buy_price',0)):.2f} sell=${float(t.get('sell_price',0)):.2f}")
        await asyncio.sleep(0.1)

    # Also check: what does the app show? Get balance
    bal = await c.send_request({"balance": 1})
    print(f"\nSaldo atual: ${bal.get('balance',{}).get('balance',0):.2f}")

    # Get open positions with current profit
    po = await c.send_request({"portfolio":1})
    oc = po.get("portfolio",{}).get("contracts",[])
    print(f"\nPosições abertas: {len(oc)}")

    # Check if profit shows up with subscribe
    total_unreal = 0.0
    for x in oc[:5]:
        cid = x.get("contract_id")
        r3 = await c.send_request({"proposal_open_contract":1,"contract_id":cid,"subscribe":1})
        ct = r3.get("proposal_open_contract",{})
        print(f"  cid={cid} profit={ct.get('profit',0)} status={ct.get('status','')} "
              f"entry={ct.get('entry_spot',0)} curr={ct.get('current_spot',0)}")
        total_unreal += float(ct.get("profit",0))
        await asyncio.sleep(0.2)

    await c.disconnect()

asyncio.run(main())
