import os, json, asyncio, time
from dotenv import load_dotenv
from deriv_client import DerivClient

load_dotenv()

async def main():
    c = DerivClient(app_id=os.getenv("DERIV_APP_ID"), api_token=os.getenv("DERIV_API_TOKEN"), use_demo=True)
    await c.connect()

    bal = await c.send_request({"balance": 1})
    saldo = bal.get("balance",{}).get("balance",0)
    print(f"Saldo: ${saldo:.2f}\n")

    # Get open positions
    po = await c.send_request({"portfolio": 1})
    oc = po.get("portfolio", {}).get("contracts", [])
    print(f"Posições abertas: {len(oc)}\n")

    # Query each contract WITHOUT subscribe, WITHOUT forget_all
    total_profit = 0.0
    total_cost = 0.0
    profitable_count = 0
    losing_count = 0
    zero_count = 0
    details = []

    for i, x in enumerate(oc):
        cid = x.get("contract_id")
        bp = float(x.get("buy_price", 0))
        total_cost += bp

        r = await c.send_request({"proposal_open_contract": 1, "contract_id": cid})
        ct = r.get("proposal_open_contract", {})

        profit = float(ct.get("profit", 0))
        entry = float(ct.get("entry_spot", 0))
        curr = float(ct.get("current_spot", 0))
        typ = ct.get("contract_type", "")
        sc = ct.get("shortcode", "")
        mult = int(ct.get("multiplier", 0))
        status = ct.get("status", "")
        canc = ct.get("cancellation", {})
        canc_exp = canc.get("date_expiry", 0) if canc else 0
        date_exp = ct.get("date_expiry", 0)
        date_start = ct.get("date_start", 0)
        amount = float(ct.get("amount", 0))
        is_expired = ct.get("is_expired", 0)
        is_sold = ct.get("is_sold", 0)
        sell_price = float(ct.get("sell_price", 0))

        # Manual profit calc for multipliers
        # MULTDOWN: profit = (entry - curr) / entry * stake * multiplier
        # MULTUP: profit = (curr - entry) / entry * stake * multiplier
        manual_profit = 0.0
        if entry > 0 and curr > 0 and mult > 0 and amount > 0:
            if typ == "MULTDOWN":
                manual_profit = ((entry - curr) / entry) * amount * mult
            elif typ == "MULTUP":
                manual_profit = ((curr - entry) / entry) * amount * mult

        total_profit += profit
        if profit > 0: profitable_count += 1
        elif profit < 0: losing_count += 1
        else: zero_count += 1

        d = {
            "cid": cid, "type": typ, "sc": sc, "mult": mult,
            "entry": entry, "curr": curr, "profit": profit,
            "manual": manual_profit, "status": status,
            "canc_exp": canc_exp, "buy": bp, "amount": amount,
            "date_exp": date_exp, "date_start": date_start,
            "is_expired": is_expired, "is_sold": is_sold,
        }
        details.append(d)

        # Print first 10 and any with profit
        if i < 10 or profit != 0:
            now_ts = int(time.time())
            canc_active = "ACTIVE" if canc_exp > now_ts else ("EXPIRED" if canc_exp > 0 else "NONE")
            print(f"cid={cid} {typ} {mult}x entry={entry} curr={curr} "
                  f"profit=${profit:.2f} manual=${manual_profit:.2f} "
                  f"canc={canc_active} status={status} buy=${bp:.2f} "
                  f"amt={amount} exp={is_expired} sold={is_sold}")

        await asyncio.sleep(0.1)

    print(f"\n=== RESUMO ===")
    print(f"Saldo: ${saldo:.2f}")
    print(f"Custo abertas: ${total_cost:.2f}")
    print(f"Profit API total: ${total_profit:.2f}")
    print(f"Profitáveis: {profitable_count}")
    print(f"Em loss: {losing_count}")
    print(f"Zero: {zero_count}")

    # Manual profit calc
    total_manual = sum(d["manual"] for d in details if d["entry"] > 0 and d["curr"] > 0)
    no_data = sum(1 for d in details if d["entry"] == 0 or d["curr"] == 0)
    print(f"\nManual profit (com entry/curr): ${total_manual:.2f}")
    print(f"Contratos sem entry/curr data: {no_data}")

    # Check contracts with no data - maybe they need subscribe to get first update
    print(f"\n=== CONTRATOS SEM DATA (entry=0) ===")
    no_data_cids = [d["cid"] for d in details if d["entry"] == 0]
    print(f"Total: {len(no_data_cids)}")

    # Try subscribe on first 3 no-data contracts
    if no_data_cids:
        print(f"\nTentando subscribe nos primeiros 3...")
        for cid in no_data_cids[:3]:
            try:
                r = await c.send_request({"proposal_open_contract": 1, "contract_id": cid, "subscribe": 1})
                ct = r.get("proposal_open_contract", {})
                print(f"  cid={cid} profit={ct.get('profit',0)} entry={ct.get('entry_spot',0)} "
                      f"curr={ct.get('current_spot',0)} status={ct.get('status','')} "
                      f"amount={ct.get('amount',0)} mult={ct.get('multiplier',0)}")
                # DON'T forget_all - let it stream
            except Exception as e:
                print(f"  cid={cid} erro: {e}")
            await asyncio.sleep(1)

    # Wait 5 seconds for subscribe updates to arrive
    print(f"\nAguardando 5s para updates...")
    await asyncio.sleep(5)

    # Re-check those 3 contracts without subscribe
    for cid in no_data_cids[:3]:
        r = await c.send_request({"proposal_open_contract": 1, "contract_id": cid})
        ct = r.get("proposal_open_contract", {})
        print(f"  RECHECK cid={cid} profit={ct.get('profit',0)} entry={ct.get('entry_spot',0)} "
              f"curr={ct.get('current_spot',0)} status={ct.get('status','')}")

    # Try selling one contract to see actual value
    print(f"\n=== TENTATIVA DE VENDA ===")
    # Find any contract with profit > 0
    for d in details:
        if d["profit"] > 0:
            print(f"Tentando vender cid={d['cid']} profit=${d['profit']:.2f}")
            try:
                sell_res = await c.send_request({"sell": 1, "contract_id": d["cid"], "price": 0})
                if "error" in sell_res:
                    print(f"  ERRO: {sell_res['error']['message']}")
                else:
                    sold_for = float(sell_res.get("sell", {}).get("sold_for", 0))
                    print(f"  VENDIDO! sold_for=${sold_for:.2f} profit=${sold_for - d['buy']:.2f}")
            except Exception as e:
                print(f"  Exceção: {e}")
            break

    await c.disconnect()

asyncio.run(main())
