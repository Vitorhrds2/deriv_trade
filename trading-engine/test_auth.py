import asyncio
import os
from pathlib import Path

from dotenv import load_dotenv

from deriv_client import DerivClient


async def check_auth():
    load_dotenv(Path(__file__).with_name(".env"))
    app_id = os.getenv("DERIV_APP_ID")
    token = os.getenv("DERIV_API_TOKEN")
    if not app_id or not token:
        raise RuntimeError("DERIV_APP_ID and DERIV_API_TOKEN are required")
    client = DerivClient(app_id=app_id, api_token=token, use_demo=True)
    await client.connect()
    try:
        response = await client.send_request({"authorize": token})
        loginid = response.get("authorize", {}).get("loginid", "")
        account_id = str(client.account_id or "")
        if not account_id.startswith("DOT") or not loginid.startswith("DOT"):
            raise RuntimeError("authenticated account is not DEMO")
        print(f"Demo authentication OK: {loginid[:3]}***")
    finally:
        await client.disconnect()


if __name__ == "__main__":
    asyncio.run(check_auth())
