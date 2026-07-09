#!/usr/bin/env python3
"""Quick test: Binance Futures testnet connectivity + order execution."""
import hmac, hashlib, time, urllib.request, urllib.parse, json, os, sys

def signed_request(base, endpoint, params, api_key, api_secret, method="GET"):
    ts = int(time.time() * 1000)
    params["timestamp"] = ts
    query = urllib.parse.urlencode(params)
    sig = hmac.new(api_secret.encode(), query.encode(), hashlib.sha256).hexdigest()
    url = f"{base}/{endpoint}?{query}&signature={sig}"
    req = urllib.request.Request(url, headers={"X-MBX-APIKEY": api_key}, method=method)
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read().decode())

def main():
    # Load .env manually
    env_path = os.path.join(os.path.dirname(__file__), ".env")
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ[k] = v

    api_key = os.environ.get("BINANCE_API_KEY_DEMO", "")
    api_secret = os.environ.get("BINANCE_API_SECRET_DEMO", "")
    base = "https://demo-fapi.binance.com/fapi/v1"

    print(f"Demo key: {api_key[:10]}... len={len(api_key)}")
    print(f"Demo secret: {api_secret[:10]}... len={len(api_secret)}")

    # 1. Check balance
    print("\n=== BALANCE ===")
    try:
        data = signed_request(base, "balance", {}, api_key, api_secret)
        if isinstance(data, list):
            for b in data:
                if float(b.get("balance", 0)) != 0:
                    print(f"  {b['asset']}: {b['balance']} (avail: {b.get('availableBalance', '?')})")
            if not any(float(b.get("balance", 0)) != 0 for b in data):
                print("  All balances zero — need to fund testnet at https://testnet.binancefuture.com")
        else:
            print(f"  Response: {json.dumps(data, indent=2)[:500]}")
    except Exception as e:
        print(f"  Error: {e}")

    # 2. Get APTUSDT price
    print("\n=== APTUSDT PRICE ===")
    try:
        url = f"{base}/ticker/price?symbol=APTUSDT"
        with urllib.request.urlopen(url, timeout=10) as r:
            data = json.loads(r.read().decode())
        print(f"  Price: ${data['price']}")
    except Exception as e:
        print(f"  Error: {e}")

    # 3. Test market short order (tiny size)
    print("\n=== TEST SHORT ORDER (APTUSDT, minimal) ===")
    try:
        price_data = signed_request(base, "ticker/price", {"symbol": "APTUSDT"}, api_key, api_secret)
        price = float(price_data["price"])
        qty = round(5.0 / price, 1)  # ~$5 notional
        if qty < 1:
            qty = 1  # minimum
        print(f"  Attempting SHORT APTUSDT qty={qty} (~${qty*price:.2f})")
        result = signed_request(base, "order", {
            "symbol": "APTUSDT",
            "side": "SELL",
            "type": "MARKET",
            "quantity": str(qty),
        }, api_key, api_secret, method="POST")
        print(f"  Order OK! ID={result.get('orderId')}, status={result.get('status')}")
        print(f"  Avg price: {result.get('avgPrice', 'N/A')}")

        # Close position immediately
        print("\n=== CLOSING POSITION ===")
        result2 = signed_request(base, "order", {
            "symbol": "APTUSDT",
            "side": "BUY",
            "type": "MARKET",
            "quantity": str(qty),
            "reduceOnly": "true",
        }, api_key, api_secret, method="POST")
        print(f"  Close OK! ID={result2.get('orderId')}, status={result2.get('status')}")
        print("\n  TESTNET EXECUTION: SUCCESS")
    except Exception as e:
        print(f"  Error: {e}")
        print("\n  TESTNET EXECUTION: FAILED (may need to fund testnet account)")

if __name__ == "__main__":
    main()
