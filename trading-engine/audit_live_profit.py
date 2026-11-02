import os, json, asyncio
from dotenv import load_dotenv
from deriv_client import DerivClient

load_dotenv()

async def main():
    c = DerivClient(app_id=os.getenv("DERIV_APP_ID"), api_token=os.getenv("DERIV_API_TOKEN"), use_demo=True)
    await c.connect()

    # Balance
    bal = await c.send_request({"balance": 1})
    saldo = bal.get("balance",{}).get("balance",0)
    print(f"Saldo: ${saldo:.2f}\n")

    # Get ALL open positions with subscribe for live profit
    po = await c.send_request({"portfolio": 1})
    oc = po.get("portfolio", {}).get("contracts", [])
    print(f"=== {len(oc)} POSIÇÕES ABERTAS ===\n")

    total_unreal = 0.0
    total_cost = 0.0
    details = []

    for x in oc:
        cid = x.get("contract_id")
        bp = float(x.get("buy_price", 0))
        total_cost += bp

        # Use proposal_open_contract WITH subscribe to get live profit
        r = await c.send_request({"proposal_open_contract": 1, "contract_id": cid, "subscribe": 1})
        ct = r.get("proposal_open_contract", {})

        typ = ct.get("contract_type", "")
        sc = ct.get("shortcode", "")
        mult = ct.get("multiplier", 0)
        entry = ct.get("entry_spot", 0)
        curr = ct.get("current_spot", 0)
        profit = float(ct.get("profit", 0))
        status = ct.get("status", "")
        canc = ct.get("cancellation", {})
        canc_expiry = canc.get("date_expiry", 0) if canc else 0
        canc_price = canc.get("ask_price", 0) if canc else 0
        amount = ct.get("amount", 0)
        payout = float(ct.get("payout", 0))
        date_expiry = ct.get("date_expiry", 0)
        date_start = ct.get("date_start", 0)
        is_sold = ct.get("is_sold", 0)
        is_expired = ct.get("is_expired", 0)
        sell_price = float(ct.get("sell_price", 0))

        total_unreal += profit

        d = {
            "cid": cid, "type": typ, "sc": sc, "mult": mult,
            "entry": entry, "curr": curr, "profit": profit,
            "status": status, "canc_exp": canc_expiry,
            "canc_price": canc_price, "amount": amount,
            "payout": payout, "buy": bp,
            "date_exp": date_expiry, "date_start": date_start,
            "is_sold": is_sold, "is_expired": is_expired,
            "sell_price": sell_price,
        }
        details.append(d)

        # Unsubscribe to avoid flooding
        try:
            await c.send_request({"forget_all": "proposal_open_contract"})
        except:
            pass

        print(f"cid={cid} {typ} {sc[:40]} entry={entry} curr={curr} "
              f"profit=${profit:.2f} status={status} canc_exp={canc_expiry} "
              f"buy=${bp:.2f} amt={amount} payout={payout} "
              f"expired={is_expired} sold={is_sold}")
        await asyncio.sleep(0.15)

    print(f"\n=== RESUMO ===")
    print(f"Saldo: ${saldo:.2f}")
    print(f"Custo total abertas: ${total_cost:.2f}")
    print(f"Unrealized total: ${total_unreal:.2f}")
    print(f"Saldo + Unrealized: ${saldo + total_unreal:.2f}")

    # Classify by type
    by_type = {}
    for d in details:
        key = d["type"]
        s = by_type.setdefault(key, {"n":0,"profit":0.0,"cost":0.0})
        s["n"] += 1; s["profit"] += d["profit"]; s["cost"] += d["buy"]

    print(f"\n=== POR TIPO ===")
    for k, s in sorted(by_type.items(), key=lambda x: -x[1]["profit"]):
        print(f"  {k}: N={s['n']} profit=${s['profit']:.2f} cost=${s['cost']:.2f}")

    # Check: how many have cancellation still active vs expired
    import time
    now_ts = int(time.time())
    canc_active = sum(1 for d in details if d["canc_exp"] > now_ts)
    canc_expired = sum(1 for d in details if d["canc_exp"] > 0 and d["canc_exp"] <= now_ts)
    no_canc = sum(1 for d in details if d["canc_exp"] == 0)
    print(f"\n=== CANCELLATION STATUS ===")
    print(f"  Cancellation ativa: {canc_active}")
    print(f"  Cancellation expirada: {canc_expired}")
    print(f"  Sem cancellation: {no_canc}")

    # Check date_expiry - are these long-duration contracts?
    print(f"\n=== EXPIRY ANALYSIS ===")
    for d in details[:5]:
        exp = d["date_exp"]
        start = d["date_start"]
        if exp and start:
            dur_min = (exp - start) / 60
            print(f"  cid={d['cid']} dur={dur_min:.0f}min exp={exp} start={start}")
        else:
            print(f"  cid={d['cid']} no expiry data (exp={exp} start={start})")

    # Key question: can we sell these for profit?
    print(f"\n=== SELL ANALYSIS ===")
    profitable = [d for d in details if d["profit"] > 0]
    losing = [d for d in details if d["profit"] < 0]
    print(f"  Profitáveis: {len(profitable)} (total ${sum(d['profit'] for d in profitable):.2f})")
    print(f"  Em loss: {len(losing)} (total ${sum(d['profit'] for d in losing):.2f})")
    print(f"  Net: ${total_unreal:.2f}")

    # Try to sell one profitable contract to verify
    if profitable:
        best = max(profitable, key=lambda x: x["profit"])
        print(f"\n=== TESTE: TENTAR VENDER O MAIS LUCRATIVO ===")
        print(f"  cid={best['cid']} profit=${best['profit']:.2f}")
        try:
            sell_res = await c.send_request({"sell": 1, "contract_id": best["cid"], "price": 0})
            if "error" in sell_res:
                print(f"  ERRO ao vender: {sell_res['error']['message']}")
            else:
                sold_for = sell_res.get("sell", {}).get("sold_for", 0)
                print(f"  VENDIDO por ${sold_for:.2f}! Profit realizado: ${float(sold_for) - best['buy']:.2f}")
        except Exception as e:
            print(f"  Exceção: {e}")

    await c.disconnect()

asyncio.run(main())
