import asyncio, json, os, sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from deriv_client import DerivClient

TEST_SPECS = [
    # symbol, list of multipliers to test
    ("R_10", [400, 1000, 2000, 4000]),
    ("1HZ10V", [400, 1000, 2000, 4000]),
    ("R_25", [160, 400, 800, 1600]),
    ("1HZ25V", [160, 400, 800, 1600]),
    ("R_50", [80, 200, 400, 800]),
    ("1HZ50V", [80, 200, 400, 800]),
    ("R_75", [60, 100, 200, 400]),
    ("1HZ75V", [60, 100, 200, 400]),
    ("R_100", [40, 100, 200, 400]),
    ("1HZ100V", [40, 100, 200, 400]),
    ("stpRNG", [750, 2000, 3500, 7500]),
]

async def probe():
    client = DerivClient()
    await client.connect()
    
    print(f"{'SYMBOL':10} | {'MULT':5} | {'FEE ($)':8} | {'FEE (%)':8} | {'COMMISSION':10} | {'STATUS'}")
    print("-" * 65)
    
    results = []
    for sym, mults in TEST_SPECS:
        for mult in mults:
            res = await client.send_request({
                "proposal": 1,
                "amount": 1.0,
                "basis": "stake",
                "contract_type": "MULTUP",
                "currency": "USD",
                "underlying_symbol": sym,
                "multiplier": mult,
                "cancellation": "5m"
            })
            if "error" in res:
                err = res["error"].get("message", "")
                if "cancellation is not available" in err.lower():
                    print(f"{sym:10} | {mult:5}x | {'N/A':8} | {'N/A':8} | {'N/A':10} | No Deal Cancellation")
                    break
                else:
                    print(f"{sym:10} | {mult:5}x | {'ERR':8} | {'ERR':8} | {'ERR':10} | {err[:30]}")
            else:
                p = res["proposal"]
                canc = p.get("cancellation", {})
                fee = float(canc.get("ask_price", 0))
                comm = float(p.get("commission", 0))
                print(f"{sym:10} | {mult:5}x | ${fee:6.2f} | {fee*100:6.1f}% | ${comm:8.4f} | OK")
                results.append({
                    "symbol": sym,
                    "multiplier": mult,
                    "fee": fee,
                    "fee_pct": fee * 100,
                    "commission": comm
                })
    await client.disconnect()
    
    # Sort results by fee percentage ascending
    results.sort(key=lambda x: x["fee_pct"])
    print("\n" + "=" * 65)
    print("TOP ASSETS BY LOWEST DEAL CANCELLATION FEE:")
    print("=" * 65)
    for r in results:
        print(f"  {r['symbol']:10} | Mult: {r['multiplier']:5}x | Fee: ${r['fee']:.2f} ({r['fee_pct']:5.1f}%) | Comm: ${r['commission']:.4f}")

if __name__ == "__main__":
    asyncio.run(probe())
