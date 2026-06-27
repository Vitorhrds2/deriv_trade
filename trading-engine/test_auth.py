import asyncio
import json
import websockets

async def test():
    uri = "wss://api.derivws.com/trading/v1/options/ws/demo?otp=gy2krhKg&app_id=33iJWIKcLfzGYo9IE1Y6f"
    async with websockets.connect(uri) as ws:
        await ws.send(json.dumps({
            "proposal": 1,
            "amount": 10,
            "contract_type": "MULTUP",
            "currency": "USD",
            "multiplier": 100,
            "underlying_symbol": "1HZ100V",
            "req_id": 1
        }))
        
        while True:
            res = await ws.recv()
            print("Response:", res)
            if "proposal" in res or "error" in res:
                break

asyncio.run(test())
