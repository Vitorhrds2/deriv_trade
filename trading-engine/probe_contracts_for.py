"""Mostra, por tipo de contrato, as duracoes e barreiras VALIDAS de um simbolo
(via API contracts_for). Usado para calibrar o exotic_value_scan."""
import asyncio
import os
import sys

from dotenv import load_dotenv
from deriv_client import DerivClient

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

load_dotenv()
API_TOKEN = os.getenv("DERIV_API_TOKEN")
APP_ID = os.getenv("DERIV_APP_ID")

WANT = {"ONETOUCH", "NOTOUCH", "EXPIRYRANGE", "EXPIRYMISS", "RANGE", "UPORDOWN",
        "CALL", "PUT", "CALLE", "PUTE"}


async def main():
    symbols = sys.argv[1:] or ["R_100"]
    client = DerivClient(app_id=APP_ID, api_token=API_TOKEN, use_demo=True)
    await client.connect()
    try:
        for sym in symbols:
            res = await client.send_request({"contracts_for": sym})
            if "error" in res:
                print(f"{sym}: erro {res['error'].get('message')}")
                continue
            avail = res.get("contracts_for", {}).get("available", [])
            print(f"\n>>> {sym}: {len(avail)} contratos")
            seen = {}
            for c in avail:
                ct = c.get("contract_type")
                if ct not in WANT:
                    continue
                key = (ct, c.get("expiry_type"), c.get("start_type"))
                if key in seen:
                    continue
                seen[key] = True
                g = lambda k: str(c.get(k))
                print(f"  {ct:12} cat={g('contract_category'):10} "
                      f"expiry={g('expiry_type'):8} start={g('start_type'):6} "
                      f"dur=[{g('min_contract_duration')}..{g('max_contract_duration')}] "
                      f"barrier_cat={g('barrier_category')} "
                      f"barriers={g('barriers')} "
                      f"low={g('low_barrier')} high={g('high_barrier')} "
                      f"barrier={g('barrier')}")
    finally:
        await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
