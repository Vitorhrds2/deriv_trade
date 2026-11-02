import os, json, asyncio
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv
from deriv_client import DerivClient

load_dotenv()

async def main():
    c = DerivClient(app_id=os.getenv("DERIV_APP_ID"), api_token=os.getenv("DERIV_API_TOKEN"), use_demo=True)
    await c.connect()
    now = datetime.now(timezone.utc)
    df, dt = int((now - timedelta(hours=24)).timestamp()), int(now.timestamp())

    bal = await c.send_request({"balance": 1})
    print(f"SALDO: ${bal.get('balance',{}).get('balance',0):.2f}")

    # Closed
    closed, off = [], 0
    while True:
        r = await c.send_request({"profit_table":1,"description":1,"date_from":df,"date_to":dt,"limit":100,"offset":off})
        if "error" in r: break
        t = r.get("profit_table",{}).get("transactions",[])
        if not t: break
        closed.extend(t)
        if len(t) < 100: break
        off += 100
        await asyncio.sleep(0.5)

    print(f"\nFECHADAS: {len(closed)}")
    tp = 0.0
    stats = {}
    for t in closed:
        p = float(t.get("sell_price",0)) - float(t.get("buy_price",0))
        tp += p
        r2 = await c.send_request({"proposal_open_contract":1,"contract_id":t["contract_id"]})
        ct = r2.get("proposal_open_contract",{})
        h = "OUTRO"
        sym, typ, mul, dur, du, can = ct.get("underlying",""), ct.get("contract_type",""), ct.get("multiplier",0), ct.get("duration",0), ct.get("duration_unit",""), ct.get("cancellation")
        if can and sym=="1HZ10V" and typ in("MULTUP","MULTDOWN"): h="D52"
        elif can and sym in("1HZ100V","R_100","1HZ50V") and typ in("MULTUP","MULTDOWN"): h="D95"
        elif typ in("CALL","PUT") and sym=="1HZ10V" and du=="m" and dur in(15,60): h="D90"
        elif typ in("DIGITOVER","DIGITUNDER"): h="D101"
        elif typ in("MULTUP","MULTDOWN") and sym=="1HZ10V": h="D52?"
        elif typ in("MULTUP","MULTDOWN") and sym in("1HZ100V","R_100","1HZ50V"): h="D95?"
        elif typ in("MULTUP","MULTDOWN"): h=f"MULT({sym})"
        s = stats.setdefault(h, {"n":0,"pnl":0.0,"w":0,"l":0})
        s["n"]+=1; s["pnl"]+=p; s["w"]+=p>0; s["l"]+=p<0
        await asyncio.sleep(0.1)

    print(f"PnL fechado: ${tp:.2f}")
    for h,s in sorted(stats.items(), key=lambda x:-x[1]["pnl"]):
        print(f"  {h}: N={s['n']} PnL=${s['pnl']:.2f} W={s['w']} L={s['l']}")

    # Open
    po = await c.send_request({"portfolio":1})
    oc = po.get("portfolio",{}).get("contracts",[])
    print(f"\nABERTAS: {len(oc)}")
    op = 0.0
    for x in oc:
        bp = float(x.get("buy_price",0))
        op -= bp
        print(f"  cid={x['contract_id']} {x.get('contract_type','')} {x.get('underlying','')} buy=${bp}")
    print(f"Custo abertas: ${-op:.2f}")

    await c.disconnect()

asyncio.run(main())
