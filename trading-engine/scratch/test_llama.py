import urllib.request
import json

urls = [
    "https://api.llama.fi/emissions",
    "https://api.llama.fi/protocols",
    "https://cryptorank.io/_next/data",
]

for url in urls:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
            print(f"URL: {url} -> OK, type={type(data)}, len={len(data) if hasattr(data, '__len__') else 'N/A'}")
    except Exception as e:
        print(f"URL: {url} -> {e}")
