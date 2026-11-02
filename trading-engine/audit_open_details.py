import os, json, asyncio
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv
from deriv_client import DerivClient

load_dotenv()

async def main():
    c = DerivClient(app_id=os.getenv("DERIV_APP_ID"), api_token=os.getenv("DERIV_API_TOKEN"), use_demo=True)
    await c.connect()

    # Get full details of ALL open positions
    po = await c.send_request({"portfolio": 1})
    oc = po.get("portfolio", {}).get("contracts", [])
    print(f"=== DETALHES DAS {len(oc)} POSIÇÕES ABERTAS ===\n")

    open_details = []
    for x in oc:
        cid = x.get("contract_id")
        bp = float(x.get("buy_price", 0))
        r = await c.send_request({"proposal_open_contract": 1, "contract_id": cid})
        ct = r.get("proposal_open_contract", {})
        sym = ct.get("underlying", "")
        typ = ct.get("contract_type", "")
        mul = ct.get("multiplier", 0)
        dur = ct.get("duration", 0)
        du = ct.get("duration_unit", "")
        can = ct.get("cancellation")
        can_dur = ct.get("cancellation", {}).get("duration", 0) if can else 0
        barrier = ct.get("barrier", "")
        entry_spot = ct.get("entry_spot", 0)
        current_spot = ct.get("current_spot", 0)
        profit = float(ct.get("profit", 0))
        status = ct.get("status", "")
        stake = ct.get("amount", 0)
        payout = float(ct.get("payout", 0))
        d = {
            "cid": cid, "type": typ, "sym": sym, "mul": mul,
            "dur": f"{dur}{du}", "stake": stake, "buy": bp,
            "canc": bool(can), "can_dur": can_dur,
            "entry": entry_spot, "current": current_spot,
            "profit": profit, "payout": payout, "status": status,
            "barrier": barrier,
        }
        open_details.append(d)
        print(f"cid={cid} {typ} {sym} {mul}x {d['dur']} stake=${stake} buy=${bp} canc={d['canc']}(can_dur={can_dur}) profit=${profit:.2f} entry={entry_spot} curr={current_spot}")
        await asyncio.sleep(0.1)

    total_unrealized = sum(d["profit"] for d in open_details)
    total_cost = sum(d["buy"] for d in open_details)
    print(f"\nTotal unrealized profit (abertas): ${total_unrealized:.2f}")
    print(f"Total cost (abertas): ${total_cost:.2f}")

    # Classify open positions
    print("\n=== CLASSIFICAÇÃO DAS ABERTAS ===")
    by_h = {}
    for d in open_details:
        h = "OUTRO"
        if d["canc"] and d["sym"] == "1HZ10V" and d["type"] in ("MULTUP", "MULTDOWN"): h = "D52"
        elif d["canc"] and d["sym"] in ("1HZ100V", "R_100", "1HZ50V") and d["type"] in ("MULTUP", "MULTDOWN"): h = "D95"
        elif d["type"] in ("CALL", "PUT") and d["sym"] == "1HZ10V": h = "D90"
        elif d["type"] in ("DIGITOVER", "DIGITUNDER"): h = "D101"
        elif d["type"] in ("MULTUP", "MULTDOWN") and d["sym"] == "1HZ10V": h = "D52(no_canc)"
        elif d["type"] in ("MULTUP", "MULTDOWN") and d["sym"] in ("1HZ100V", "R_100", "1HZ50V"): h = "D95(no_canc)"
        elif d["type"] in ("MULTUP", "MULTDOWN"): h = f"MULT({d['sym']})"
        s = by_h.setdefault(h, {"n": 0, "profit": 0.0, "cost": 0.0})
        s["n"] += 1; s["profit"] += d["profit"]; s["cost"] += d["buy"]
    for h, s in sorted(by_h.items(), key=lambda x: -x[1]["profit"]):
        print(f"  {h}: N={s['n']} unrealized=${s['profit']:.2f} cost=${s['cost']:.2f}")

    # Now get a sample of closed positions with full details
    now = datetime.now(timezone.utc)
    df, dt2 = int((now - timedelta(hours=24)).timestamp()), int(now.timestamp())
    closed, off = [], 0
    while len(closed) < 200:
        r = await c.send_request({"profit_table": 1, "description": 1, "date_from": df, "date_to": dt2, "limit": 100, "offset": off})
        if "error" in r: break
        t = r.get("profit_table", {}).get("transactions", [])
        if not t: break
        closed.extend(t)
        off += 100
        await asyncio.sleep(0.5)

    print(f"\n=== AMOSTRA DE {min(50, len(closed))} POSIÇÕES FECHADAS (com detalhes) ===\n")
    sample = closed[:50]
    for t in sample:
        cid = t["contract_id"]
        p = float(t.get("sell_price", 0)) - float(t.get("buy_price", 0))
        r = await c.send_request({"proposal_open_contract": 1, "contract_id": cid})
        ct = r.get("proposal_open_contract", {})
        sym = ct.get("underlying", "")
        typ = ct.get("contract_type", "")
        mul = ct.get("multiplier", 0)
        dur = ct.get("duration", 0)
        du = ct.get("duration_unit", "")
        can = ct.get("cancellation")
        print(f"cid={cid} {typ} {sym} {mul}x {dur}{du} canc={bool(can)} profit=${p:.2f} buy=${float(t.get('buy_price',0)):.2f} sell=${float(t.get('sell_price',0)):.2f}")
        await asyncio.sleep(0.1)

    await c.disconnect()

asyncio.run(main())
