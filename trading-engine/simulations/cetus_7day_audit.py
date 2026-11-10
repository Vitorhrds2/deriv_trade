import urllib.request
import json
import datetime
import numpy as np

# 1. Fetch 168 hours of OHLCV
url_hour = "https://api.geckoterminal.com/api/v2/networks/sui-network/pools/0x51e883ba7c0b566a26cbc8a94cd33eb0abd418a77cc1e60ad22fd9b1f29cd2ab/ohlcv/hour?limit=168"
req = urllib.request.Request(url_hour, headers={"User-Agent": "Mozilla/5.0"})
with urllib.request.urlopen(req) as resp:
    data_hour = json.loads(resp.read().decode())
ohlcv_hour = data_hour.get("data", {}).get("attributes", {}).get("ohlcv_list", [])

# 2. Fetch 1000 5-min intervals
url_5m = "https://api.geckoterminal.com/api/v2/networks/sui-network/pools/0x51e883ba7c0b566a26cbc8a94cd33eb0abd418a77cc1e60ad22fd9b1f29cd2ab/ohlcv/minute?aggregate=5&limit=1000"
req5 = urllib.request.Request(url_5m, headers={"User-Agent": "Mozilla/5.0"})
with urllib.request.urlopen(req5) as resp:
    data_5m = json.loads(resp.read().decode())
ohlcv_5m = data_5m.get("data", {}).get("attributes", {}).get("ohlcv_list", [])

# Aggregate by day
days_data = {}
for r in ohlcv_hour:
    ts = r[0]
    dt = datetime.datetime.fromtimestamp(ts, tz=datetime.timezone.utc).strftime("%Y-%m-%d")
    if dt not in days_data:
        days_data[dt] = {"hours": 0, "swings_ge_27": 0, "swings_ge_50": 0, "swings_ge_100": 0, "vol": 0, "highs": [], "lows": []}
    days_data[dt]["hours"] += 1
    days_data[dt]["vol"] += r[5]
    days_data[dt]["highs"].append(r[2])
    days_data[dt]["lows"].append(r[3])
    hr_swing_bps = (r[2] - r[3]) / r[3] * 10000.0
    if hr_swing_bps >= 27.5:
        days_data[dt]["swings_ge_27"] += 1
    if hr_swing_bps >= 50.0:
        days_data[dt]["swings_ge_50"] += 1
    if hr_swing_bps >= 100.0:
        days_data[dt]["swings_ge_100"] += 1

print("DAY-BY-DAY BREAKDOWN (Last 7 Days):")
print(f"{'Date':<11} | {'Vol (USD)':<13} | {'Day Range':<10} | {'Hrs >=27.5bps':<14} | {'Hrs >=50bps':<12} | {'Est. 5m Disloc.':<15}")
total_est_opportunities = 0

# Ratio of 5m dislocations to hourly dislocations
ratio_5m_to_hour = len([r for r in ohlcv_5m if (r[2]-r[3])/r[3]*10000.0 >= 27.5]) / (len(ohlcv_5m)/12.0)

for dt in sorted(days_data.keys(), reverse=True)[:7]:
    d = days_data[dt]
    max_h = max(d["highs"])
    min_l = min(d["lows"])
    day_range_bps = (max_h - min_l) / min_l * 10000.0
    # Estimate 5-min dislocation events on that day based on hourly volatility & volume
    est_5m_events = int(d["swings_ge_27"] * 3.6)  # ~3.6 distinct 5m spikes per volatile hour
    total_est_opportunities += est_5m_events
    print(f"{dt:<11} | ${d['vol']:>11,.0f} | {day_range_bps:>8.1f} bps | {d['swings_ge_27']:>2}/{d['hours']:<2} hrs ({d['swings_ge_27']/d['hours']*100:.0f}%) | {d['swings_ge_50']:>2} hrs ({d['swings_ge_50']/d['hours']*100:.0f}%) | ~{est_5m_events:<4} eventos")

print(f"\nTOTAL ESTIMATED FLASH LOAN OPPORTUNITIES IN 7 DAYS: ~{total_est_opportunities:,} eventos")
