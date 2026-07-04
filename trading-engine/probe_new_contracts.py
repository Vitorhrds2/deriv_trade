"""Probe cru de contracts_for para descobrir os contract_type reais e seus parametros
(High/Low Ticks, Only Ups/Downs, Turbos, Reset Call/Put, Lookback, Asians) -- antes de
implementar qualquer scan de edge. So leitura, nenhuma ordem enviada."""
import asyncio
import json
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

DETAIL = {"TICKHIGH", "TICKLOW", "RUNHIGH", "RUNLOW", "TURBOSLONG", "TURBOSSHORT",
          "RESETCALL", "RESETPUT", "ASIAND", "ASIANU"}


async def main():
    symbols = sys.argv[1:] or ["1HZ100V", "R_100"]
    client = DerivClient(app_id=APP_ID, api_token=API_TOKEN, use_demo=True)
    await client.connect()
    try:
        for sym in symbols:
            res = await client.send_request({"contracts_for": sym})
            if "error" in res:
                print(f"{sym}: erro {res['error'].get('message')}")
                continue
            avail = res.get("contracts_for", {}).get("available", [])
            by_type = {}
            for c in avail:
                ct = c.get("contract_type")
                by_type.setdefault(ct, c)
            print(f"\n{'='*90}\n>>> {sym}: {len(avail)} contratos, {len(by_type)} contract_types unicos\n{'='*90}")
            print(", ".join(sorted(by_type)))
            for ct in sorted(by_type):
                if ct not in DETAIL:
                    continue
                print(f"\n--- {sym} / {ct} ---")
                print(json.dumps(by_type[ct], indent=2, ensure_ascii=False))
    finally:
        await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
