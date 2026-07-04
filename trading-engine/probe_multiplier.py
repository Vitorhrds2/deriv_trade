"""Probe de Multipliers (MULTUP/MULTDOWN) -- unico produto Deriv ativo nunca testado para mispricing.
Descobrir: estrutura de proposal, barrier, payout, duration limits, contract_details."""
import asyncio, json, os, sys
from dotenv import load_dotenv
from deriv_client import DerivClient

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

load_dotenv()
API_TOKEN = os.getenv("DERIV_API_TOKEN")
APP_ID = os.getenv("DERIV_APP_ID")

SYMBOL = "1HZ10V"

async def main():
    client = DerivClient(app_id=APP_ID, api_token=API_TOKEN, use_demo=True)
    await client.connect()

    # 1. contracts_for -- ver estrutura
    res = await client.send_request({"contracts_for": SYMBOL})
    avail = res.get("contracts_for", {}).get("available", [])
    mults = [c for c in avail if c.get("contract_type") in ("MULTUP", "MULTDOWN")]
    print(f"\n{'='*90}\n>>> {SYMBOL}: {len(mults)} contratos MULTUP/MULTDOWN\n{'='*90}")
    for c in mults:
        print(json.dumps(c, indent=2, ensure_ascii=False))

    # 2. Proposals com diferentes durations e multipliers
    configs = [
        ("MULTUP", 5, "t", None),
        ("MULTUP", 10, "t", None),
        ("MULTUP", 15, "t", None),
        ("MULTUP", 5, "m", None),
        ("MULTUP", 15, "m", None),
        ("MULTDOWN", 5, "t", None),
        ("MULTDOWN", 10, "t", None),
        ("MULTDOWN", 5, "m", None),
        ("MULTDOWN", 15, "m", None),
    ]

    for ct, dur, unit, barrier in configs:
        payload = {
            "proposal": 1, "amount": 10, "basis": "stake",
            "contract_type": ct, "currency": "USD",
            "underlying_symbol": SYMBOL, "duration": dur, "duration_unit": unit,
        }
        if barrier:
            payload["barrier"] = barrier
        res = await client.send_request(payload)
        if "error" in res:
            print(f"\n--- {ct} dur={dur}{unit}: ERRO: {res['error'].get('message','')[:100]} ---")
        else:
            p = res["proposal"]
            print(f"\n--- {ct} dur={dur}{unit} ---")
            print(f"  ask_price={p.get('ask_price')} | payout={p.get('payout')} | spot={p.get('spot')}")
            print(f"  barrier={p.get('barrier')} | barrier_choices={p.get('barrier_choices')}")
            cd = p.get("contract_details", {})
            print(f"  contract_details: {json.dumps(cd, indent=2, ensure_ascii=False)[:500]}")
            # Campos relevantes
            for k in ["display_number_of_contracts", "multiplier", "stop_loss", "stop_out",
                       "take_profit", "commission", "payout_per_point"]:
                if k in p or k in cd:
                    print(f"  {k} = {p.get(k, cd.get(k))}")
        await asyncio.sleep(0.3)

    # 3. Tentar com barrier (multiplier)
    for mult in ["5", "10", "20", "50", "100"]:
        for ct in ["MULTUP", "MULTDOWN"]:
            payload = {
                "proposal": 1, "amount": 10, "basis": "stake",
                "contract_type": ct, "currency": "USD",
                "underlying_symbol": SYMBOL, "duration": 5, "duration_unit": "t",
                "barrier": mult,
            }
            res = await client.send_request(payload)
            if "error" in res:
                print(f"\n--- {ct} barrier={mult} dur=5t: ERRO: {res['error'].get('message','')[:80]} ---")
            else:
                p = res["proposal"]
                print(f"\n--- {ct} barrier={mult} dur=5t ---")
                print(f"  ask_price={p.get('ask_price')} | payout={p.get('payout')} | spot={p.get('spot')}")
                print(f"  barrier={p.get('barrier')} | barrier_choices={p.get('barrier_choices')}")
                cd = p.get("contract_details", {})
                if cd:
                    print(f"  contract_details: {json.dumps(cd, indent=2, ensure_ascii=False)[:500]}")
            await asyncio.sleep(0.3)

    await client.disconnect()

asyncio.run(main())
