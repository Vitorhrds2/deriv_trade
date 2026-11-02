import urllib.request, json
from datetime import datetime, timezone

url = "https://fapi.binance.com/fapi/v1/fundingRate?symbol=BLURUSDT&limit=100"
req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
with urllib.request.urlopen(req, timeout=5) as resp:
    data = json.loads(resp.read().decode())

print(f"Fetched {len(data)} funding records for BLURUSDT:")
for d in data[-15:]:
    t = datetime.fromtimestamp(int(d["fundingTime"])/1000, tz=timezone.utc).strftime("%Y-%m-%d %H:%M")
    rate = float(d["fundingRate"]) * 100
    print(f"  {t} | Funding: {rate:+.4f}%/8h | Mark: {d.get('markPrice')}")
