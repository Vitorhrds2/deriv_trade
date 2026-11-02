import urllib.request
import json

url = "https://api.cryptorank.io/v3/currencies/upcoming-token-unlocks?daysAhead=30&sortBy=unlockValue&sortOrder=desc"
try:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=10) as resp:
        data = json.loads(resp.read().decode())
        print("CryptoRank v3 response:", data)
except Exception as e:
    print("CryptoRank v3 error:", e)
