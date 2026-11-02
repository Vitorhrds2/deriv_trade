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

    # Get ALL closed positions
    closed, off = [], 0
    while True:
        r = await c.send_request({"profit_table":1,"description":1,"date_from":df,"date_to":dt2,"limit":100,"offset":off})
        if "error" in r: break
        t = r.get("profit_table",{}).get("transactions",[])
        if not t: break
        closed.extend(t)
        if len(t) < 100: break
        off += 100
        await asyncio.sleep(0.5)

    # Classify by getting contract details
    stats = {}
    total_pnl = 0.0
    for i, t in enumerate(closed):
        cid = t["contract_id"]
        p = float(t.get("sell_price",0)) - float(t.get("buy_price",0))
        total_pnl += p
        bp = float(t.get("buy_price",0))

        # Get contract details for classification
        r = await c.send_request({"proposal_open_contract":1,"contract_id":cid})
        ct = r.get("proposal_open_contract",{})
        typ = ct.get("contract_type","")
        sc = ct.get("shortcode","")

        # Classify
        if "MULTUP" in sc or "MULTDOWN" in sc:
            if "1HZ10V" in sc: h = "D52"
            elif "1HZ100V" in sc or "R_100" in sc or "1HZ50V" in sc: h = "D95"
            else: h = f"MULT({sc.split('_')[1]})"
        elif typ in ("DIGITOVER","DIGITUNDER","DIGITODD","DIGITEVEN","DIGITMATCH","DIGITDIFF"):
            h = "d106/d101(digits)"
        elif typ in ("CALL","PUT"):
            if "1HZ10V" in sc and ("15m" in sc or "60m" in sc): h = "D90"
            else: h = "d106(CALL/PUT)"
        else:
            h = f"OTHER({typ})"

        s = stats.setdefault(h, {"n":0,"pnl":0.0,"w":0,"l":0,"cost":0.0})
        s["n"] += 1; s["pnl"] += p; s["cost"] += bp
        if p > 0: s["w"] += 1
        elif p < 0: s["l"] += 1

        if i % 200 == 0:
            print(f"  Processados {i}/{len(closed)}...", flush=True)
        await asyncio.sleep(0.05)

    print(f"\nTotal fechadas: {len(closed)}")
    print(f"PnL total fechado: ${total_pnl:.2f}\n")
    print("=== POR ORIGEM ===")
    for h, s in sorted(stats.items(), key=lambda x: x[1]["n"]):
        print(f"  {h}: N={s['n']} PnL=${s['pnl']:.2f} W={s['w']} L={s['l']} Cost=${s['cost']:.2f}")

    # Open positions
    po = await c.send_request({"portfolio":1})
    oc = po.get("portfolio",{}).get("contracts",[])
    open_stats = {}
    open_profit = 0.0
    open_cost = 0.0
    for x in oc:
        cid = x.get("contract_id")
        bp = float(x.get("buy_price",0))
        sc = x.get("shortcode","")
        r = await c.send_request({"proposal_open_contract":1,"contract_id":cid})
        ct = r.get("proposal_open_contract",{})
        profit = float(ct.get("profit",0))
        open_profit += profit
        open_cost += bp

        if "MULTUP" in sc or "MULTDOWN" in sc:
            if "1HZ10V" in sc: h = "D52"
            elif "1HZ100V" in sc or "R_100" in sc or "1HZ50V" in sc: h = "D95"
            else: h = f"MULT({sc.split('_')[1]})"
        elif "CALL" in sc or "PUT" in sc:
            if "1HZ10V" in sc: h = "D90"
            else: h = "d106(CALL/PUT)"
        else:
            h = f"OTHER"

        s2 = open_stats.setdefault(h, {"n":0,"profit":0.0,"cost":0.0})
        s2["n"] += 1; s2["profit"] += profit; s2["cost"] += bp
        await asyncio.sleep(0.05)

    print(f"\n=== {len(oc)} ABERTAS ===")
    for h, s in sorted(open_stats.items(), key=lambda x: -x[1]["profit"]):
        print(f"  {h}: N={s['n']} unrealized=${s['profit']:.2f} cost=${s['cost']:.2f}")

    print(f"\n=== RESUMO FINAL ===")
    print(f"Realized (fechadas):   ${total_pnl:.2f}")
    print(f"Unrealized (abertas):  ${open_profit:.2f}")
    print(f"NET:                   ${total_pnl + open_profit:.2f}")

    await c.disconnect()

asyncio.run(main())
