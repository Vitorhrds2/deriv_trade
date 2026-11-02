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

    # Get ALL closed positions in 24h
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

    print(f"Total fechadas 24h: {len(closed)}")

    # Get shortcode for each closed position to classify precisely
    # shortcode format: TYPE_SYMBOL_STake_multiplier_purchase_expiry_...
    stats = {}
    total_pnl = 0.0
    for t in closed:
        cid = t["contract_id"]
        p = float(t.get("sell_price",0)) - float(t.get("buy_price",0))
        total_pnl += p

        # Use shortcode from profit_table description
        shortcode = t.get("short_code", "")
        desc = t.get("description", "")

        # Classify from shortcode
        hypo = "OUTRO"
        if "MULTUP" in shortcode or "MULTDOWN" in shortcode:
            if "1HZ10V" in shortcode:
                hypo = "D52"
            elif "1HZ100V" in shortcode or "R_100" in shortcode or "1HZ50V" in shortcode:
                hypo = "D95"
            else:
                hypo = f"MULT({shortcode.split('_')[1] if '_' in shortcode else '?'})"
        elif "CALL" in shortcode or "PUT" in shortcode:
            if "1HZ10V" in shortcode:
                hypo = "D90"
            else:
                hypo = "CALLPUT_other"
        elif "DIGITOVER" in shortcode or "DIGITUNDER" in shortcode:
            hypo = "D101"
        elif "DIGITODD" in shortcode or "DIGITEVEN" in shortcode:
            hypo = "D101(digit_odd_even)"
        elif "DIGITMATCH" in shortcode or "DIGITDIFF" in shortcode:
            hypo = "D101(digit_match_diff)"

        s = stats.setdefault(hypo, {"n":0,"pnl":0.0,"w":0,"l":0,"examples":[]})
        s["n"] += 1; s["pnl"] += p
        if p > 0: s["w"] += 1
        elif p < 0: s["l"] += 1
        if len(s["examples"]) < 3:
            s["examples"].append({"cid":cid,"p":round(p,2),"sc":shortcode[:60]})

    print(f"PnL total fechado: ${total_pnl:.2f}\n")
    print("=== POR HIPÓTESE (classificado por shortcode) ===")
    for h, s in sorted(stats.items(), key=lambda x: -x[1]["n"]):
        print(f"\n{h}: N={s['n']} PnL=${s['pnl']:.2f} W={s['w']} L={s['l']}")
        for e in s["examples"]:
            print(f"  cid={e['cid']} p=${e['p']} sc={e['sc']}")

    # Open positions - classify by shortcode
    po = await c.send_request({"portfolio":1})
    oc = po.get("portfolio",{}).get("contracts",[])
    print(f"\n=== {len(oc)} POSIÇÕES ABERTAS ===")

    open_stats = {}
    open_total_profit = 0.0
    open_total_cost = 0.0
    for x in oc:
        cid = x.get("contract_id")
        bp = float(x.get("buy_price",0))
        sc = x.get("shortcode","")
        r = await c.send_request({"proposal_open_contract":1,"contract_id":cid})
        ct = r.get("proposal_open_contract",{})
        profit = float(ct.get("profit",0))
        open_total_profit += profit
        open_total_cost += bp

        hypo = "OUTRO"
        if "MULTUP" in sc or "MULTDOWN" in sc:
            if "1HZ10V" in sc: hypo = "D52"
            elif "1HZ100V" in sc or "R_100" in sc or "1HZ50V" in sc: hypo = "D95"
            else: hypo = f"MULT({sc.split('_')[1]})"
        elif "CALL" in sc or "PUT" in sc:
            if "1HZ10V" in sc: hypo = "D90"
            else: hypo = "CALLPUT_other"
        elif "DIGITOVER" in sc or "DIGITUNDER" in sc: hypo = "D101"
        elif "DIGITODD" in sc or "DIGITEVEN" in sc: hypo = "D101(odd_even)"

        s2 = open_stats.setdefault(hypo, {"n":0,"profit":0.0,"cost":0.0})
        s2["n"] += 1; s2["profit"] += profit; s2["cost"] += bp
        await asyncio.sleep(0.05)

    print(f"Unrealized total: ${open_total_profit:.2f}")
    print(f"Cost total: ${open_total_cost:.2f}")
    for h, s in sorted(open_stats.items(), key=lambda x: -x[1]["profit"]):
        print(f"  {h}: N={s['n']} unrealized=${s['profit']:.2f} cost=${s['cost']:.2f}")

    # NET
    print(f"\n=== RESUMO FINAL ===")
    print(f"Realized (fechadas): ${total_pnl:.2f}")
    print(f"Unrealized (abertas): ${open_total_profit:.2f}")
    print(f"NET: ${total_pnl + open_total_profit:.2f}")

    # Count cancellation fees in open positions
    fee_total = 0.0
    for x in oc:
        cid = x.get("contract_id")
        r = await c.send_request({"proposal_open_contract":1,"contract_id":cid})
        ct = r.get("proposal_open_contract",{})
        canc = ct.get("cancellation")
        if canc:
            fee_total += float(canc.get("ask_price",0))
        await asyncio.sleep(0.05)
    print(f"Cancellation fees pendentes (abertas): ${fee_total:.2f}")
    print(f"NET após fees: ${total_pnl + open_total_profit - fee_total:.2f}")

    await c.disconnect()

asyncio.run(main())
