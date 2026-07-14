import asyncio
import os
from dotenv import load_dotenv
from deriv_client import DerivClient

load_dotenv()

async def main():
    app_id = os.getenv('DERIV_APP_ID')
    token = os.getenv('DERIV_API_TOKEN')
    c = DerivClient(app_id, token)
    await c.connect()
    for sym in ['cryBTCUSD', 'frxEURUSD']:
        res = await c.send_request({'contracts_for': sym})
        print('===', sym)
        if 'error' in res:
            print('ERROR', res['error'].get('message'))
            continue
        avail = res.get('contracts_for', {}).get('available', [])
        print('total', len(avail))
        types = {}
        for a in avail:
            ct = a.get('contract_type')
            cat = a.get('contract_category')
            types.setdefault(ct, []).append(cat)
        for ct, cats in sorted(types.items()):
            print(ct, '| categories:', set(cats))
    await c.disconnect()

asyncio.run(main())
