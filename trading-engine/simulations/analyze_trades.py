import urllib.request
import json
import numpy as np

url = "https://api.geckoterminal.com/api/v2/networks/sui-network/pools/0x51e883ba7c0b566a26cbc8a94cd33eb0abd418a77cc1e60ad22fd9b1f29cd2ab/trades"
req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
with urllib.request.urlopen(req) as resp:
    data = json.loads(resp.read().decode())

trades = data.get("data", [])
volumes = []
for t in trades:
    v = float(t["attributes"].get("volume_in_usd", 0))
    if v > 0:
        volumes.append(v)

v_arr = np.array(volumes)
print(f"Total trades analyzed: {len(v_arr)}")
print(f"Median trade size: ${np.median(v_arr):.2f}")
print(f"Mean trade size: ${np.mean(v_arr):.2f}")
print(f"Max trade size: ${np.max(v_arr):.2f}")
print(f"Trades >= $500: {np.sum(v_arr >= 500)} ({np.mean(v_arr >= 500)*100:.1f}%)")
print(f"Trades >= $1,000: {np.sum(v_arr >= 1000)} ({np.mean(v_arr >= 1000)*100:.1f}%)")
print(f"Trades >= $2,500: {np.sum(v_arr >= 2500)} ({np.mean(v_arr >= 2500)*100:.1f}%)")
print(f"Trades >= $5,000: {np.sum(v_arr >= 5000)} ({np.mean(v_arr >= 5000)*100:.1f}%)")
print(f"Trades >= $10,000: {np.sum(v_arr >= 10000)} ({np.mean(v_arr >= 10000)*100:.1f}%)")

# Let us check the time span of these 300 trades
ts_first = trades[-1]["attributes"]["block_timestamp"]
ts_last = trades[0]["attributes"]["block_timestamp"]
print(f"\nTime span of sample: from {ts_first} to {ts_last}")
