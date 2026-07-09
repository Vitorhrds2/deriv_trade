#!/usr/bin/env python3
"""Test Binance Futures PROD API: hybrid v1 (order/ticker) + v2 (account/positionRisk)."""
import hmac, hashlib, time, urllib.request, urllib.parse, urllib.error, json, os

def signed_req(base, endpoint, params, api_key, api_secret, method="GET"):
    ts = int(time.time() * 1000)
    params["timestamp"] = ts
    query = urllib.parse.urlencode(params)
    sig = hmac.new(api_secret.encode(), query.encode(), hashlib.sha256).hexdigest()
    params["signature"] = sig
    url = f"{base}/{endpoint}"
    if method == "GET":
        url += "?" + urllib.parse.urlencode(params)
        req = urllib.request.Request(url, headers={"X-MBX-APIKEY": api_key})
    else:
        data = urllib.parse.urlencode(params).encode()
        req = urllib.request.Request(url, data=data, headers={"X-MBX-APIKEY": api_key}, method=method)
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read().decode())

def main():
    with open(os.path.join(os.path.dirname(__file__), ".env")) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ[k] = v

    api_key = os.environ.get("BINANCE_API_KEY", "")
    api_secret = os.environ.get("BINANCE_API_SECRET", "")
    v1 = "https://fapi.binance.com/fapi/v1"
    v2 = "https://fapi.binance.com/fapi/v2"

    # 1. Account info (v2)
    print("=== PROD FUTURES ACCOUNT (v2) ===")
    try:
        data = signed_req(v2, "account", {}, api_key, api_secret)
        print(f"  Can trade: {data.get('canTrade')}")
        assets = [a for a in data.get("assets", []) if float(a.get("walletBalance", 0)) != 0]
        for a in assets:
            print(f"  {a['asset']}: balance={a['walletBalance']}, avail={a.get('availableBalance', '?')}")
        if not assets:
            print("  No balances -- account not funded yet")
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        print(f"  HTTP {e.code}: {body}")
        print()
        print("  PROD API v1 ORDER: FAILED")
    except Exception as e:
        print(f"  Account error: {e}")

    # 2. APTUSDT price (v1 public)
    print()
    try:
        url = f"{v1}/ticker/price?symbol=APTUSDT"
        with urllib.request.urlopen(url, timeout=10) as r:
            pdata = json.loads(r.read().decode())
        price = float(pdata["price"])
        print(f"APTUSDT price: ${price}")
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        print(f"  HTTP {e.code}: {body}")
        print()
        print("  PROD API v1 ORDER: FAILED")
    except Exception as e:
        print(f"Price error: {e}")
        return

    # 3. Place far LIMIT BUY on v1 (signed)
    print()
    print("=== TEST: PLACE + CANCEL LIMIT ORDER (v1) ===")
    test_price = round(price * 0.5, 5)
    try:
        result = signed_req(v1, "order", {
            "symbol": "APTUSDT",
            "side": "BUY",
            "type": "LIMIT",
            "timeInForce": "GTC",
            "quantity": "20",
            "price": str(test_price),
        }, api_key, api_secret, method="POST")
        print(f"  Order placed! ID={result.get('orderId')}, status={result.get('status')}")

        cancel = signed_req(v1, "order", {
            "symbol": "APTUSDT",
            "orderId": result["orderId"],
        }, api_key, api_secret, method="DELETE")
        print(f"  Cancelled! status={cancel.get('status')}")
        print()
        print("  PROD API v1 ORDER: SUCCESS")
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        print(f"  HTTP {e.code}: {body}")
        print()
        print("  PROD API v1 ORDER: FAILED")
    except Exception as e:
        print(f"  Error: {e}")
        print()
        print("  PROD API v1 ORDER: FAILED")

    # 4. Test positionRisk (v2 signed)
    print()
    print("=== TEST: POSITION RISK (v2) ===")
    try:
        pos = signed_req(v2, "positionRisk", {"symbol": "APTUSDT"}, api_key, api_secret)
        print(f"  OK: {len(pos)} positions returned")
        print("  PROD API v2 POSITION: SUCCESS")
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        print(f"  HTTP {e.code}: {body}")
        print()
        print("  PROD API v1 ORDER: FAILED")
    except Exception as e:
        print(f"  Error: {e}")

if __name__ == "__main__":
    main()
