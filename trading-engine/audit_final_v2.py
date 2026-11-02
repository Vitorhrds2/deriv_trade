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

    # Get ALL closed - use profit_table fields directly
    closed, off = [], 0
    while True:
        r = await c.send_request({"profit_table":1,"description":1,"date_from":df,"date_to":dt2,"limit":100,"offset":off})
        if "error" in r: break
        t = r.get("profit_table",{}).get("transactions",[])
        if not t: break
        closed.extend(t)
        if len(t) < 100: break
        off += 100
        await asyncio.sleep(0.3)

    print(f"Total fechadas 24h: {len(closed)}")

    # Classify using profit_table fields directly
    stats = {}
    total_pnl = 0.0
    for t in closed:
        p = float(t.get("sell_price",0)) - float(t.get("buy_price",0))
        total_pnl += p
        ct = t.get("contract_type","")
        sc = t.get("shortcode","")
        sym = t.get("underlying_symbol","")
        bp = float(t.get("buy_price",0))

        if "MULTUP" in sc or "MULTDOWN" in sc or ct in ("MULTUP","MULTDOWN"):
            if "1HZ10V" in sc or sym == "1HZ10V": h = "D52"
            elif "1HZ100V" in sc or "R_100" in sc or "1HZ50V" in sc or sym in ("1HZ100V","R_100","1HZ50V"): h = "D95"
            else: h = f"MULT({sym})"
        elif ct in ("DIGITOVER","DIGITUNDER","DIGITODD","DIGITEVEN","DIGITMATCH","DIGITDIFF"):
            h = "d106/d101(digits)"
        elif ct in ("CALL","PUT"):
            if "1HZ10V" in sc and ("15m" in sc or "60m" in sc): h = "D90"
            else: h = "d106(CALL/PUT)"
        elif not ct and not sc:
            h = "expired(no_data)"
        else:
            h = f"OTHER({ct})"

        s = stats.setdefault(h, {"n":0,"pnl":0.0,"w":0,"l":0,"cost":0.0})
        s["n"] += 1; s["pnl"] += p; s["cost"] += bp
        if p > 0: s["w"] += 1
        elif p < 0: s["l"] += 1

    print(f"PnL total fechado: ${total_pnl:.2f}\n")
    print("=== POR ORIGEM (profit_table direto) ===")
    for h, s in sorted(stats.items(), key=lambda x: x[1]["n"]):
        wr = s["w"]/(s["w"]+s["l"])*100 if (s["w"]+s["l"]) > 0 else 0
        print(f"  {h}: N={s['n']} PnL=${s['pnl']:.2f} W={s['w']} L={s['l']} WR={wr:.0f}% Cost=${s['cost']:.2f}")

    # Open positions
    po = await c.send_request({"portfolio":1})
    oc = po.get("portfolio",{}).get("contracts",[])
    print(f"\n=== {len(oc)} ABERTAS ===")
    open_stats = {}
    for x in oc:
        bp = float(x.get("buy_price",0))
        ct = x.get("contract_type","")
        sc = x.get("shortcode","")
        sym = x.get("underlying","")

        if "MULTUP" in sc or "MULTDOWN" in sc or ct in ("MULTUP","MULTDOWN"):
            if "1HZ10V" in sc or sym == "1HZ10V": h = "D52"
            elif "1HZ100V" in sc or "R_100" in sc or "1HZ50V" in sc or sym in ("1HZ100V","R_100","1HZ50V"): h = "D95"
            else: h = f"MULT({sym})"
        elif ct in ("CALL","PUT"):
            if "1HZ10V" in sc: h = "D90"
            else: h = "d106(CALL/PUT)"
        else:
            h = f"OTHER({ct})"

        s2 = open_stats.setdefault(h, {"n":0,"cost":0.0})
        s2["n"] += 1; s2["cost"] += bp

    for h, s in sorted(open_stats.items(), key=lambda x: -x[1]["n"]):
        print(f"  {h}: N={s['n']} cost=${s['cost']:.2f}")

    # Balance
    bal = await c.send_request({"balance": 1})
    saldo = bal.get("balance",{}).get("balance",0)
    print(f"\n=== RESUMO FINAL ===")
    print(f"Saldo atual:           ${saldo:.2f}")
    print(f"Realized (fechadas):   ${total_pnl:.2f}")
    print(f"NET:                   ${total_pnl:.2f}")
    print(f"\nO '+830' era lucro UNREALIZED das posições D52/D95 abertas.")
    print(f"Já evaporou (profit=0 nas abertas agora).")
    print(f"P&L real = ${total_pnl:.2f}")

    await c.disconnect()

asyncio.run(main())
