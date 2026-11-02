import os, json, asyncio
from dotenv import load_dotenv
from deriv_client import DerivClient

load_dotenv()

async def main():
    c = DerivClient(app_id=os.getenv("DERIV_APP_ID"), api_token=os.getenv("DERIV_API_TOKEN"), use_demo=True)
    await c.connect()

    # Get portfolio
    po = await c.send_request({"portfolio": 1})
    oc = po.get("portfolio", {}).get("contracts", [])
    print(f"Posições abertas: {len(oc)}")

    # Get current ticks
    r10v = await c.send_request({"ticks": "1HZ10V"})
    curr_10v = float(r10v["tick"]["quote"])
    await asyncio.sleep(0.3)
    r100v = await c.send_request({"ticks": "1HZ100V"})
    curr_100v = float(r100v["tick"]["quote"])
    print(f"1HZ10V atual: {curr_10v}")
    print(f"1HZ100V atual: {curr_100v}\n")

    # For each contract, extract entry time from shortcode and get historical tick
    total_profit = 0.0
    total_cost = 0.0
    by_group = {}

    for x in oc:
        cid = x.get("contract_id")
        bp = float(x.get("buy_price", 0))
        total_cost += bp
        sc = x.get("shortcode", "")
        typ = x.get("contract_type", "")
        sym = x.get("underlying_symbol", "")

        # Parse shortcode: MULTDOWN_1HZ10V_10.00_400_1784050355_4937673599_5m_0.00_N1_0
        parts = sc.split("_")
        stake = float(parts[2]) if len(parts) > 2 else 0
        mult = int(parts[3]) if len(parts) > 3 else 0
        purchase_ts = int(parts[4]) if len(parts) > 4 else 0

        # Get entry spot from ticks_history at purchase time
        entry_spot = 0.0
        if purchase_ts > 0 and sym:
            try:
                # Get 1 tick right before purchase time (entry spot)
                hist = await c.send_request({
                    "ticks_history": sym,
                    "start": purchase_ts - 5,
                    "end": purchase_ts + 5,
                    "count": 1,
                    "style": "ticks"
                })
                if "history" in hist:
                    prices = hist["history"]["prices"]
                    if prices:
                        entry_spot = float(prices[-1])
                elif "candles" in hist:
                    if hist["candles"]:
                        entry_spot = float(hist["candles"][0]["close"])
            except Exception as e:
                pass
            await asyncio.sleep(0.1)

        # Current spot
        curr_spot = curr_10v if "1HZ10V" in sym else (curr_100v if "1HZ100V" in sym else 0)

        # Calculate profit
        # Multiplier: profit = (% move in favor) * stake * multiplier
        # MULTDOWN: profit = (entry - curr) / entry * stake * mult
        # MULTUP: profit = (curr - entry) / entry * stake * mult
        profit = 0.0
        if entry_spot > 0 and curr_spot > 0 and stake > 0 and mult > 0:
            if typ == "MULTDOWN":
                profit = ((entry_spot - curr_spot) / entry_spot) * stake * mult
            elif typ == "MULTUP":
                profit = ((curr_spot - entry_spot) / entry_spot) * stake * mult

        total_profit += profit

        # Group
        key = f"{typ}_{sym}_{stake}_{mult}"
        g = by_group.setdefault(key, {"n":0, "profit":0.0, "cost":0.0, "entries":[]})
        g["n"] += 1
        g["profit"] += profit
        g["cost"] += bp
        g["entries"].append(entry_spot)

        print(f"cid={cid} {typ} {sym} {mult}x stake=${stake} entry={entry_spot:.2f} curr={curr_spot:.2f} profit=${profit:.2f} buy=${bp:.2f}")

    print(f"\n{'='*80}")
    print(f"=== RESUMO FINAL ===")
    print(f"{'='*80}")
    print(f"Posições abertas: {len(oc)}")
    print(f"Custo total (buy prices): ${total_cost:.2f}")
    print(f"Profit não-realizado total: ${total_profit:.2f}")
    print(f"NET (profit - cost): ${total_profit - total_cost:.2f}")

    print(f"\n=== POR GRUPO ===")
    for k, g in sorted(by_group.items(), key=lambda x: -x[1]["profit"]):
        avg_entry = sum(g["entries"]) / len(g["entries"]) if g["entries"] else 0
        print(f"  {k}: N={g['n']} profit=${g['profit']:.2f} cost=${g['cost']:.2f} avg_entry={avg_entry:.2f}")

    # Balance
    bal = await c.send_request({"balance": 1})
    saldo = bal.get("balance",{}).get("balance",0)
    print(f"\nSaldo: ${saldo:.2f}")
    print(f"Saldo + Unrealized: ${saldo + total_profit:.2f}")

    # Key analysis
    multdown_count = sum(g["n"] for k, g in by_group.items() if "MULTDOWN" in k)
    multup_count = sum(g["n"] for k, g in by_group.items() if "MULTUP" in k)
    print(f"\n=== ANÁLISE DE DIRECIONAL ===")
    print(f"MULTDOWN: {multdown_count} posições")
    print(f"MULTUP: {multup_count} posições")
    print(f"Net short: {multdown_count - multup_count} posições")
    print(f"\nO profit é DIRECIONAL (net short em 1HZ10V que caiu).")
    print(f"Se 1HZ10V reverter, o profit desaparece.")

    await c.disconnect()

asyncio.run(main())
