import asyncio, json, os, sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from deriv_client import DerivClient

# Symbols to test
CANDIDATE_SYMBOLS = [
    # Synthetic Volatility Indices
    "R_10", "R_25", "R_50", "R_75", "R_100",
    "1HZ10V", "1HZ25V", "1HZ50V", "1HZ75V", "1HZ100V", "1HZ150V", "1HZ250V", "1HZ300V",
    # Crash / Boom
    "BOOM300N", "BOOM500", "BOOM1000",
    "CRASH300N", "CRASH500", "CRASH1000",
    # Jump Indices
    "JD10", "JD25", "JD50", "JD75", "JD100",
    # Step Indices
    "stpRNG", "step_index",
    # Range Break
    "RANGEBREAK100", "RANGEBREAK200",
    # Crypto
    "cryBTCUSD", "cryETHUSD", "BTCUSD", "ETHUSD",
    # Forex
    "frxEURUSD", "frxGBPUSD", "frxUSDJPY"
]

async def probe_symbols():
    client = DerivClient()
    await client.connect()
    
    print("================================================================================")
    print("PROBING DERIV ASSETS FOR MULTIPLIERS & DEAL CANCELLATION SUPPORT")
    print("================================================================================")
    
    supported = []
    
    for sym in CANDIDATE_SYMBOLS:
        # 1. First probe Multipliers
        res = await client.send_request({
            "proposal": 1,
            "amount": 1.0,
            "basis": "stake",
            "contract_type": "MULTUP",
            "currency": "USD",
            "underlying_symbol": sym,
            "multiplier": 100,
            "cancellation": "5m"
        })
        
        if "error" in res:
            err_code = res["error"].get("code", "")
            err_msg = res["error"].get("message", "")
            
            # If error is multiplier out of range, let's see acceptable multipliers
            if "Accepts" in err_msg or "Multiplier is not in acceptable range" in err_msg:
                # Extract acceptable multipliers
                print(f"  {sym:14} | Multiplier 100 invalid: {err_msg}")
            elif "cancellation" in err_msg.lower() or "cancellation" in err_code.lower():
                print(f"  {sym:14} | Multipliers OK, but NO Deal Cancellation: {err_msg}")
            elif "ContractBuyValidationError" in err_code:
                print(f"  {sym:14} | Contract validation error: {err_msg}")
            else:
                pass # not supported or invalid symbol
        else:
            p = res["proposal"]
            canc = p.get("cancellation", {})
            fee = canc.get("ask_price", 0)
            mult = p.get("multiplier", 100)
            print(f"  {sym:14} | [SUPPORTED] Multiplier: {mult}x | Cancellation Fee: ${fee:.2f} ({fee*100:.1f}%) | Spot: {p.get('spot')}")
            supported.append({
                "symbol": sym,
                "multiplier": mult,
                "cancellation_fee": fee,
                "fee_pct": fee * 100,
                "spot": p.get("spot")
            })
            
    await client.disconnect()
    
    print("\n================================================================================")
    print(f"TOTAL SUPPORTED ASSETS WITH DEAL CANCELLATION: {len(supported)}")
    print("================================================================================")
    for s in supported:
        print(f"  {s['symbol']:14} | Mult: {s['multiplier']}x | Fee: ${s['cancellation_fee']:.2f} ({s['fee_pct']:.1f}%) | Spot: {s['spot']}")

if __name__ == "__main__":
    asyncio.run(probe_symbols())
