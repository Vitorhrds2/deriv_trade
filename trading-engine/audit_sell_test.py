import os, json, asyncio
from dotenv import load_dotenv
from deriv_client import DerivClient

load_dotenv()

async def main():
    c = DerivClient(app_id=os.getenv("DERIV_APP_ID"), api_token=os.getenv("DERIV_API_TOKEN"), use_demo=True)
    await c.connect()

    # 1. Get raw portfolio response
    po = await c.send_request({"portfolio": 1})
    oc = po.get("portfolio", {}).get("contracts", [])

    # Print ALL fields from first few portfolio contracts
    print("=== CAMPOS DO PORTFOLIO ===")
    for x in oc[:3]:
        print(json.dumps(x, indent=2, default=str))
        print("---")

    # 2. Get current tick for 1HZ10V and 1HZ100V
    print("\n=== TICK ATUAL ===")
    for sym in ["1HZ10V", "1HZ100V"]:
        r = await c.send_request({"ticks": sym})
        if "tick" in r:
            print(f"  {sym}: {r['tick']['quote']}")
        await asyncio.sleep(0.5)

    # 3. For each open contract, try to get contract_details via proposal_open_contract
    # and also try the "contract_history" endpoint
    print(f"\n=== {len(oc)} CONTRATOS ABERTOS ===\n")

    # Group by shortcode pattern to understand what they are
    patterns = {}
    for x in oc:
        sc = x.get("shortcode", "")
        bp = float(x.get("buy_price", 0))
        # Extract symbol from shortcode
        parts = sc.split("_")
        sym = parts[1] if len(parts) > 1 else "?"
        key = f"{x.get('contract_type','')}_{sym}_{bp}"
        patterns.setdefault(key, []).append(x)

    print("=== AGRUPADOS ===")
    for k, v in sorted(patterns.items(), key=lambda x: -len(x[1])):
        print(f"  {k}: N={len(v)}")
        if v:
            print(f"    shortcode: {v[0].get('shortcode','')}")
            print(f"    longcode: {v[0].get('longcode','')[:100]}")

    # 4. Try to sell at market price - check what sell price would be
    # Use "price": 0 means sell at market
    print(f"\n=== TENTATIVA DE VENDA (um de cada grupo) ===")
    sold_any = False
    for k, v in patterns.items():
        if not v:
            continue
        cid = v[0]["contract_id"]
        bp = float(v[0].get("buy_price", 0))
        print(f"\n  Tentando vender cid={cid} ({k}) buy=${bp:.2f}")
        try:
            sell_res = await c.send_request({"sell": 1, "contract_id": cid, "price": 0})
            if "error" in sell_res:
                print(f"    ERRO: {sell_res['error']['message']}")
            else:
                sold_for = float(sell_res.get("sell", {}).get("sold_for", 0))
                profit = sold_for - bp
                print(f"    VENDIDO! sold_for=${sold_for:.2f} profit=${profit:.2f}")
                sold_any = True
        except Exception as e:
            print(f"    Exceção: {e}")
        await asyncio.sleep(1)

    # 5. Check balance after potential sell
    bal = await c.send_request({"balance": 1})
    print(f"\nSaldo após: ${bal.get('balance',{}).get('balance',0):.2f}")

    # 6. Get updated portfolio
    po2 = await c.send_request({"portfolio": 1})
    oc2 = po2.get("portfolio", {}).get("contracts", [])
    print(f"Posições abertas após: {len(oc2)}")

    await c.disconnect()

asyncio.run(main())
