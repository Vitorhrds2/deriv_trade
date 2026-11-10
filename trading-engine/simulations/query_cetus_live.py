import urllib.request
import json

url = "https://api.geckoterminal.com/api/v2/networks/sui-network/dexes/cetus/pools?page=1"
req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
with urllib.request.urlopen(req) as resp:
    data = json.loads(resp.read().decode())

for p in data["data"][:8]:
    attr = p["attributes"]
    name = attr.get("name", "Unknown")
    addr = attr.get("address", "")
    tx24 = attr.get("transactions", {}).get("h24", {})
    buys = tx24.get("buys", 0)
    sells = tx24.get("sells", 0)
    total_tx = buys + sells
    vol = float(attr.get("volume_usd", {}).get("h24", 0))
    reserve = float(attr.get("reserve_in_usd", 0))
    print(f"Pool: {name}")
    print(f"  Address: {addr}")
    print(f"  TVL Reserve: ${reserve:,.2f}")
    print(f"  24h Volume: ${vol:,.2f}")
    print(f"  24h Swaps: {total_tx:,} ({buys:,} buys, {sells:,} sells)")
    print("-" * 50)
