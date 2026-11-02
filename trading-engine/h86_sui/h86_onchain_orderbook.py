#!/usr/bin/env python3
"""H86 DeepBook V3 on-chain orderbook reader.

Queries Sui RPC directly to extract real-time orderbook prices
from DeepBook V3 pools. No indexer needed.
"""
import requests
import json
import time
import statistics
from datetime import datetime, timezone

RPC = "https://fullnode.mainnet.sui.io"
PKG = "0x000000000000000000000000000000000000000000000000000000000000dee9"

# Discovered pool IDs from PoolCreated events
POOLS = {
    "SUI_USDC_2bps": {
        "id": "0x4405b50d791fd3346754e8171aaab6bc2ed26c2c46efdd033c14b30ae507ac33",
        "base": "SUI", "quote": "USDC",
        "base_decimals": 9, "quote_decimals": 6,
        "taker_fee": 200000, "maker_rebate": 200000,
    },
    "SUI_USDC_25bps": {
        "id": "0x18d871e3c3da99046dfc0d3de612c5d88859bc03b8f0568bd127d0e70dbc58be",
        "base": "SUI", "quote": "USDC",
        "base_decimals": 9, "quote_decimals": 6,
        "taker_fee": 2500000, "maker_rebate": 1500000,
    },
}

DURATION = 1800  # 30 minutes per pool
POLL_INTERVAL = 15  # seconds (RPC is slow with many calls)

# DeepBook price formula:
# FLOAT_SCALING = 1e9
# price_factor = 10^(9 - base_decimals + quote_decimals)
# For SUI/WUSDC: base_decimals=9, quote_decimals=6 → price_factor = 10^6
# real_price = raw_key / price_factor
PRICE_FACTOR = 1_000_000  # 10^6 for SUI(9 decimals) / WUSDC(6 decimals)


def rpc_call(method, params):
    r = requests.post(RPC, json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params}, timeout=15)
    return r.json()


def get_pool_orderbook(pool_id):
    """Extract orderbook from a DeepBook V3 pool object."""
    r = rpc_call("sui_getObject", [pool_id, {"showContent": True}])
    obj = r.get("result", {}).get("data", {})
    content = obj.get("content", {})
    fields = content.get("fields", {})
    if not fields:
        print(f"    [DEBUG] No fields in pool object. Content keys: {list(content.keys()) if content else 'empty'}")
        return None

    bids_tree = fields.get("bids", {}).get("fields", {})
    asks_tree = fields.get("asks", {}).get("fields", {})

    bids_leaves_id = bids_tree.get("leaves", {}).get("fields", {}).get("id", {}).get("id", "")
    asks_leaves_id = asks_tree.get("leaves", {}).get("fields", {}).get("id", {}).get("id", "")

    tick_size = int(fields.get("tick_size", 100))
    lot_size = int(fields.get("lot_size", 100000000))

    bid_prices = get_leaf_prices(bids_leaves_id)
    ask_prices = get_leaf_prices(asks_leaves_id)

    return {
        "bid_prices": bid_prices,
        "ask_prices": ask_prices,
        "tick_size": tick_size,
        "lot_size": lot_size,
    }


def get_leaf_prices(leaves_table_id, max_levels=5):
    """Get price levels from a CritbitTree leaves table.
    Only fetches first few + last few to minimize RPC calls."""
    if not leaves_table_id:
        return []

    r = rpc_call("suix_getDynamicFields", [leaves_table_id])
    fields = r.get("result", {}).get("data", [])
    if not fields:
        return []

    # Only fetch a subset of leaves to avoid too many RPC calls
    # Get first 3 and last 3 (best prices are at extremes)
    n = len(fields)
    if n <= max_levels * 2:
        subset = fields
    else:
        subset = fields[:max_levels] + fields[-max_levels:]

    prices = []
    for df in subset:
        obj_id = df.get("objectId", "")
        r2 = rpc_call("sui_getObject", [obj_id, {"showContent": True}])
        obj = r2.get("result", {}).get("data", {})
        content = obj.get("content", {})
        cfields = content.get("fields", {})
        value = cfields.get("value", {})
        if isinstance(value, dict):
            vfields = value.get("fields", {})
            leaf_key = vfields.get("key", "0")
            if leaf_key:
                prices.append(int(leaf_key))

    prices.sort()
    return prices


def get_coinbase_price(symbol):
    try:
        r = requests.get(f"https://api.coinbase.com/v2/prices/{symbol}-USD/spot", timeout=5)
        if r.ok:
            return float(r.json()["data"]["amount"])
    except:
        pass
    return None


def get_recent_fills(pool_id, n=20):
    """Get recent OrderFilled events for a specific pool."""
    r = rpc_call("suix_queryEvents", [
        {"MoveModule": {"package": PKG, "module": "clob_v2"}}, None, 50, True
    ])
    events = r.get("result", {}).get("data", [])
    fills = []
    for evt in events:
        if "OrderFilled" not in evt.get("type", ""):
            continue
        parsed = evt.get("parsedJson", {})
        if pool_id in parsed.get("pool_id", ""):
            fills.append({
                "qty": int(parsed.get("base_asset_quantity_filled", 0)),
                "is_bid": parsed.get("is_bid", False),
                "maker_rebates": int(parsed.get("maker_rebates", 0)),
                "ts": evt.get("timestampMs", ""),
            })
    return fills[:n]


def main():
    print("=" * 80)
    print("H86 DeepBook V3 On-Chain Orderbook Scan")
    print("=" * 80)
    print(f"  RPC: {RPC}")
    print(f"  Duration: {DURATION}s, Poll: {POLL_INTERVAL}s")
    print()

    # First, discover all pools
    print("[Discovery] Querying PoolCreated events...")
    r = rpc_call("suix_queryEvents", [
        {"MoveEventType": f"{PKG}::clob_v2::PoolCreated"}, None, 50, False
    ])
    events = r.get("result", {}).get("data", [])
    print(f"  Found {len(events)} PoolCreated events")

    all_pools = {}
    for evt in events:
        parsed = evt.get("parsedJson", {})
        pool_id = parsed.get("pool_id", "")
        base = parsed.get("base_asset", {}).get("name", "")
        quote = parsed.get("quote_asset", {}).get("name", "")
        taker_fee = int(parsed.get("taker_fee_rate", 0))
        maker_rebate = int(parsed.get("maker_rebate_rate", 0))

        # Identify token by type string (addresses may not have 0x prefix)
        base_lower = base.lower()
        quote_lower = quote.lower()

        base_name = "UNKNOWN"
        quote_name = "UNKNOWN"
        if "::sui::sui" in base_lower:
            base_name = "SUI"
        elif "5d4b302506645c37ff133b98c4b50a5ae14841659738d6d733d59d0d217a93bf" in base_lower:
            base_name = "WUSDC"  # Wormhole USDC
        elif "dba34672e30cb065b1f93e3ab55318768fd6fef66c15942c9f7cb846e2f900e7" in base_lower:
            base_name = "USDC"  # Native USDC
        elif "c060006111016b8a020ad5b33834984a437aaa7d3c74c18e09a95d48aceab08c" in base_lower:
            base_name = "USDT"
        elif "af8cd5edc19c4512f4259f0bee101a40d41ebed738ade5874359610ef8eeced5" in base_lower:
            base_name = "WAL"
        elif "bc3a676894871284b3ccfb2eec66f428612000e2a6e6d23f592ce8833c27c973" in base_lower:
            base_name = "DEEP"
        elif "960b531667636f39e85867775f52f6b1f220a058c4de786905bdf761e06a56bb" in base_lower:
            base_name = "USDY"

        if "::sui::sui" in quote_lower:
            quote_name = "SUI"
        elif "5d4b302506645c37ff133b98c4b50a5ae14841659738d6d733d59d0d217a93bf" in quote_lower:
            quote_name = "WUSDC"
        elif "dba34672e30cb065b1f93e3ab55318768fd6fef66c15942c9f7cb846e2f900e7" in quote_lower:
            quote_name = "USDC"

        pair = f"{base_name}/{quote_name}"
        fee_bps = taker_fee / 10000
        # Use pool_id as key to avoid duplicates overwriting each other
        all_pools[pool_id] = {
            "pair": pair,
            "id": pool_id,
            "base_name": base_name,
            "quote_name": quote_name,
            "taker_fee_bps": fee_bps,
            "maker_rebate_bps": maker_rebate / 10000,
        }
        print(f"  {pair}: fee={fee_bps:.1f}bps  rebate={maker_rebate/10000:.1f}bps  id={pool_id[:20]}...")

    # Focus on SUI pools — only scan the 2 with lowest fees (most liquid)
    sui_pools = {pid: v for pid, v in all_pools.items() if "SUI" in v.get("pair", "")}
    # Sort by fee and take 2 lowest
    sorted_pools = sorted(sui_pools.items(), key=lambda x: x[1]["taker_fee_bps"])
    scan_pools = dict(sorted_pools[:2])
    print(f"\n  Scanning {len(scan_pools)} SUI pools (lowest fee tier)")

    # Get Coinbase reference
    sui_ref = get_coinbase_price("SUI")
    print(f"  Coinbase SUI-USD: ${sui_ref:.4f}" if sui_ref else "  Coinbase: unavailable")

    results = {}

    for pool_key, pool_info in scan_pools.items():
        pool_id = pool_info["id"]
        pair_name = pool_info.get("pair", pool_key[:20])
        print(f"\n{'='*60}")
        print(f"  Pool: {pair_name} (fee={pool_info['taker_fee_bps']:.1f}bps)")
        print(f"{'='*60}")

        samples = []
        start = time.time()

        while time.time() - start < DURATION:
            book = get_pool_orderbook(pool_id)
            ref = get_coinbase_price("SUI")

            if book and book["bid_prices"] and book["ask_prices"]:
                tick_size = book["tick_size"]

                best_bid_key = max(book["bid_prices"])
                best_ask_key = min(book["ask_prices"])

                # DeepBook price formula: real_price = key / price_factor
                # price_factor = 10^(9 - base_decimals + quote_decimals) = 10^6 for SUI/WUSDC
                bid_price = best_bid_key / PRICE_FACTOR
                ask_price = best_ask_key / PRICE_FACTOR
                mid = (bid_price + ask_price) / 2
                spread_bps = ((ask_price - bid_price) / mid) * 10000 if mid > 0 else 0
                cross_venue = ((mid - ref) / ref) * 10000 if ref and ref > 0 else None

                # Also get all bid/ask levels for depth analysis
                all_bids = [k / PRICE_FACTOR for k in book["bid_prices"]]
                all_asks = [k / PRICE_FACTOR for k in book["ask_prices"]]

                sample = {
                    "ts": time.time(),
                    "best_bid_key": best_bid_key,
                    "best_ask_key": best_ask_key,
                    "bid_price": bid_price,
                    "ask_price": ask_price,
                    "mid_price": mid,
                    "spread_bps": spread_bps,
                    "cross_venue_bps": cross_venue,
                    "n_bid_levels": len(book["bid_prices"]),
                    "n_ask_levels": len(book["ask_prices"]),
                    "tick_size": tick_size,
                    "coinbase_price": ref,
                    "all_bids": all_bids,
                    "all_asks": all_asks,
                }

                print(f"  [{time.strftime('%H:%M:%S')}] bid=${bid_price:.6f} ask=${ask_price:.6f} "
                      f"mid=${mid:.6f} spread={spread_bps:.2f}bps "
                      f"vs_coinbase={cross_venue:+.2f}bps" if cross_venue else
                      f"  [{time.strftime('%H:%M:%S')}] bid=${bid_price:.6f} ask=${ask_price:.6f} "
                      f"mid=${mid:.6f} spread={spread_bps:.2f}bps")

                if cross_venue and abs(cross_venue) > 10:
                    print(f"  *** ARB OPPORTUNITY: {cross_venue:+.2f}bps vs Coinbase ***")
                    print(f"      DeepBook mid=${mid:.6f} vs Coinbase=${ref:.6f}")
                    print(f"      After taker fee {pool_info['taker_fee_bps']:.1f}bps: "
                          f"net={(cross_venue - pool_info['taker_fee_bps']):+.2f}bps")

                samples.append(sample)

            # Get recent fills
            fills = get_recent_fills(pool_id, 5)
            if fills:
                print(f"  Recent fills: {len(fills)} (last: qty={fills[0]['qty']/1e9:.4f} SUI, "
                      f"{'buy' if fills[0]['is_bid'] else 'sell'}, "
                      f"rebate={fills[0]['maker_rebates']})")

            time.sleep(POLL_INTERVAL)

        # Summary
        print(f"\n  {pair_name} Summary:")
        print(f"    Samples: {len(samples)}")

        matched = [s for s in samples if s.get("matching_scale")]
        if matched:
            spreads = [s["spread_bps"] for s in matched if "spread_bps" in s]
            cross = [s["cross_venue_bps"] for s in matched if "cross_venue_bps" in s]
            if spreads:
                print(f"    DeepBook spread: mean={statistics.mean(spreads):.2f}bps median={statistics.median(spreads):.2f}bps")
            if cross:
                print(f"    Cross-venue (vs Coinbase): mean={statistics.mean(cross):+.2f}bps median={statistics.median(cross):+.2f}bps")
                opps = [c for c in cross if abs(c) > 10]
                print(f"    Opportunities >10bps: {len(opps)}/{len(cross)}")
        else:
            print(f"    Could not determine price scale (no Coinbase match)")

        results[pair_name] = {
            "pool_id": pool_id,
            "taker_fee_bps": pool_info["taker_fee_bps"],
            "maker_rebate_bps": pool_info["maker_rebate_bps"],
            "n_samples": len(samples),
            "samples": samples[-20:],
        }
    # Final verdict
    print(f"\n{'='*80}")
    print("VEREDITO FINAL — H86 DeepBook On-Chain Scan")
    print(f"{'='*80}")

    print(f"\n  Pools discovered: {len(all_pools)}")
    for pid, info in all_pools.items():
        print(f"    {info['pair']}: fee={info['taker_fee_bps']:.1f}bps rebate={info['maker_rebate_bps']:.1f}bps")

    print(f"\n  Fee structure:")
    print(f"    Lowest taker fee: {min(p['taker_fee_bps'] for p in all_pools.values()):.1f}bps")
    print(f"    Highest maker rebate: {max(p['maker_rebate_bps'] for p in all_pools.values()):.1f}bps")

    # Save results
    output = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "hypothesis": "H86",
        "platform": "Sui DeepBookV3 (on-chain RPC)",
        "pools_discovered": all_pools,
        "coinbase_sui_price": sui_ref,
        "results": {k: {kk: vv for kk, vv in v.items() if kk != "samples"} | 
                     {"last_sample": v["samples"][-1] if v["samples"] else None}
                     for k, v in results.items()},
    }
    fname = "h86_deepbook_onchain_results.json"
    with open(fname, "w") as f:
        json.dump(output, f, indent=2, default=str)
    print(f"\n  Results saved to {fname}")


if __name__ == "__main__":
    main()
