import asyncio
import os
import logging
from dotenv import load_dotenv
from deriv_client import DerivClient

logging.basicConfig(level=logging.INFO, format='%(message)s')

load_dotenv()
DERIV_API_TOKEN = os.getenv("DERIV_API_TOKEN")
DERIV_APP_ID = os.getenv("DERIV_APP_ID")

async def verify_deriv_api():
    client = DerivClient(app_id=DERIV_APP_ID, api_token=DERIV_API_TOKEN, use_demo=True)
    await client.connect()
    print("Conectado à Deriv. Puxando as últimas 200 transações...")
    
    res = await client.send_request({
        "profit_table": 1,
        "description": 1,
        "limit": 200,
        "sort": "DESC"
    })
    
    transactions = res.get("profit_table", {}).get("transactions", [])
    
    rng_wins = 0
    rng_losses = 0
    rng_pnl = 0.0
    
    for t in transactions:
        shortcode = t.get("shortcode", "")
        if "1HZ10V" in shortcode and ("CALL" in shortcode or "PUT" in shortcode) and "MULT" not in shortcode:
            pnl = float(t.get("sell_price", 0)) - float(t.get("buy_price", 0))
            rng_pnl += pnl
            if pnl > 0:
                rng_wins += 1
            else:
                rng_losses += 1

    total = rng_wins + rng_losses
    win_rate = (rng_wins / total * 100) if total > 0 else 0
    print(f"Total RNG Trades: {total}")
    print(f"Wins: {rng_wins} | Losses: {rng_losses}")
    print(f"Win Rate: {win_rate:.2f}%")
    print(f"Total PnL: ${rng_pnl:.2f}")

    await client.disconnect()

if __name__ == "__main__":
    asyncio.run(verify_deriv_api())
