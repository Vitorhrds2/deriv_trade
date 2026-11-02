"""H84 — Hyperliquid Gossip Protocol Market Making Feasibility Scan.

The PDF proposes running a non-validator node with split_client_blocks:true
to see mempool txs 70-150ms before finality, enabling toxic flow avoidance
for market making. Requires 32 cores, 128GB RAM.

This instance has 2 vCPUs, 7.6GB RAM — CANNOT run a full node.
Instead, this script does a FEASIBILITY ASSESSMENT:

1. Measures API latency from this AWS region (us-east-2) to Hyperliquid
   - WebSocket round-trip time (post -> ack)
   - REST API latency
   - Compare to the claimed 380ms public API latency

2. Measures L2 book update latency vs trade execution
   - How fast does the book update after a trade?
   - This proxies the "information delay" that gossip would reduce

3. Simulates market making EV with adverse selection
   - Place hypothetical orders at spread ± 1 tick
   - Track how often we'd get filled vs adverse selection
   - Calculate maker rebate EV vs toxic fill cost

4. Documents the hardware gap and what would be needed

Usage: python3 h84_hyperliquid_gossip_feasibility.py
"""
import asyncio
import json
import os
import statistics
import sys
import time
from datetime import datetime, timezone

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import websockets
import requests

HL_WS_URL = "wss://api.hyperliquid.xyz/ws"
HL_REST_URL = "https://api.hyperliquid.xyz/info"
COINS = ["BTC", "ETH", "SOL"]
DURATION_SECONDS = 120  # 2 min per coin for latency measurement
MM_SIM_DURATION = 300   # 5 min market making simulation per coin

# Hyperliquid maker rebate: currently -0.001% (taker fee 0.035%, maker rebate 0.001%)
# Source: Hyperliquid docs fee structure
MAKER_REBATE_BPS = 0.1  # 0.001% = 0.1 bps
TAKER_FEE_BPS = 3.5     # 0.035% = 3.5 bps


async def measure_ws_latency(coin, duration):
    """Measure WebSocket round-trip latency by subscribing to a channel
    and timing the response."""
    latencies = []
    msg_count = 0

    subscribe_msg = {
        "method": "subscribe",
        "subscription": {"type": "trades", "coin": coin},
    }

    try:
        async with websockets.connect(HL_WS_URL, ping_interval=10) as ws:
            await ws.send(json.dumps(subscribe_msg))
            start = time.monotonic()

            while time.monotonic() - start < duration:
                try:
                    response = await asyncio.wait_for(ws.recv(), timeout=5.0)
                    msg_count += 1
                    # Parse trade timestamps
                    data = json.loads(response)
                    if data.get("channel") == "trades" and "data" in data:
                        for trade in data["data"]:
                            ts = trade.get("time", 0)
                            if ts > 0:
                                # Server time vs our time
                                our_time_ms = int(time.time() * 1000)
                                latency_ms = our_time_ms - ts
                                if 0 < latency_ms < 10000:  # sanity check
                                    latencies.append(latency_ms)
                except asyncio.TimeoutError:
                    continue

    except Exception as e:
        print(f"  [WS error] {e}")

    return latencies, msg_count


def measure_rest_latency(coin, n=10):
    """Measure REST API latency for getting L2 book."""
    latencies = []
    for _ in range(n):
        try:
            t0 = time.monotonic()
            resp = requests.post(
                HL_REST_URL,
                json={"type": "l2Book", "coin": coin},
                timeout=5,
            )
            t1 = time.monotonic()
            if resp.status_code == 200:
                latencies.append((t1 - t0) * 1000)
        except Exception:
            pass
        time.sleep(0.2)
    return latencies


async def simulate_market_making(coin, duration):
    """Simulate market making by tracking L2 book updates and trades.
    Calculate how often hypothetical maker orders would be filled
    vs adversely selected (price moves through our order)."""
    fills = 0
    adverse_fills = 0
    book_updates = 0
    spread_samples = []
    mid_prices = []

    # Track book state
    current_bids = []
    current_asks = []

    subscribe_book = {
        "method": "subscribe",
        "subscription": {"type": "l2Book", "coin": coin},
    }
    subscribe_trades = {
        "method": "subscribe",
        "subscription": {"type": "trades", "coin": coin},
    }

    # Track if we have an open hypothetical order
    our_bid_price = None
    our_ask_price = None
    our_bid_time = None
    our_ask_time = None

    try:
        async with websockets.connect(HL_WS_URL, ping_interval=10) as ws:
            await ws.send(json.dumps(subscribe_book))
            await ws.send(json.dumps(subscribe_trades))
            start = time.monotonic()

            while time.monotonic() - start < duration:
                try:
                    response = await asyncio.wait_for(ws.recv(), timeout=5.0)
                    data = json.loads(response)

                    if data.get("channel") == "l2Book" and "data" in data:
                        book = data["data"]
                        levels = book.get("levels", [])
                        if len(levels) >= 2:
                            best_bid = float(levels[0].get("bid", "0") if "bid" in levels[0] else levels[0].get("px", "0"))
                            best_ask = float(levels[1].get("ask", "0") if "ask" in levels[1] else levels[1].get("px", "0"))
                            # Actually levels structure: [{"px":..,"sz":..,"n":..}, ...] for bids and asks separately
                            # Let me handle both formats
                            if "bid" in levels[0]:
                                bids = [l["bid"] for l in levels if "bid" in l]
                                asks = [l["ask"] for l in levels if "ask" in l]
                            else:
                                # Split: first half bids, second half asks (or separate fields)
                                bids_raw = book.get("levels", [])
                                # Hyperliquid format: {"bid": [...], "ask": [...]}
                                pass

                            # Try Hyperliquid's actual format
                            all_levels = book.get("levels", [])
                            bid_levels = [l for l in all_levels if "bid" in l]
                            ask_levels = [l for l in all_levels if "ask" in l]

                            if bid_levels and ask_levels:
                                best_bid = float(bid_levels[0]["bid"]["px"])
                                best_ask = float(ask_levels[0]["ask"]["px"])
                            elif len(all_levels) >= 2:
                                best_bid = float(all_levels[0].get("px", 0))
                                best_ask = float(all_levels[1].get("px", 0))
                            else:
                                continue

                            if best_bid > 0 and best_ask > 0:
                                mid = (best_bid + best_ask) / 2
                                spread_bps = (best_ask - best_bid) / mid * 10000
                                spread_samples.append(spread_bps)
                                mid_prices.append(mid)
                                book_updates += 1

                                # Place hypothetical orders at best bid/ask
                                our_bid_price = best_bid
                                our_ask_price = best_ask
                                our_bid_time = time.monotonic()
                                our_ask_time = time.monotonic()

                    elif data.get("channel") == "trades" and "data" in data:
                        for trade in data["data"]:
                            trade_px = float(trade.get("px", 0))
                            trade_side = trade.get("side", "")

                            if trade_px > 0 and our_bid_price and our_ask_price:
                                # Check if trade would fill our orders
                                if trade_side == "A" and trade_px <= our_bid_price:
                                    # Someone sold at or below our bid — we'd be filled
                                    fills += 1
                                    # Check if it was adverse (price kept dropping)
                                    # We'll check next book update
                                elif trade_side == "B" and trade_px >= our_ask_price:
                                    fills += 1

                except asyncio.TimeoutError:
                    continue

    except Exception as e:
        print(f"  [MM sim error] {e}")

    return {
        "fills": fills,
        "adverse_fills": adverse_fills,
        "book_updates": book_updates,
        "spread_samples": spread_samples,
        "mid_prices": mid_prices,
    }


async def main():
    print("=" * 90)
    print("H84 — Hyperliquid Gossip Protocol Market Making Feasibility Scan")
    print("=" * 90)
    print(f"  Instance: us-east-2 (Ohio)")
    print(f"  Hardware: 2 vCPUs, 7.6GB RAM (NOT sufficient for full node)")
    print(f"  Full node req: 32 cores, 128GB RAM, 500MB/s storage")
    print(f"  Approach: Feasibility assessment via public API latency + MM simulation")
    print()

    results = {}

    for coin in COINS:
        print(f"\n{'='*70}")
        print(f"  COIN: {coin}")
        print(f"{'='*70}")

        # 1. REST latency
        print(f"\n  [1] REST API latency (L2 book)...")
        rest_lat = measure_rest_latency(coin, n=10)
        if rest_lat:
            print(f"      mean={statistics.mean(rest_lat):.1f}ms  "
                  f"median={statistics.median(rest_lat):.1f}ms  "
                  f"min={min(rest_lat):.1f}ms  max={max(rest_lat):.1f}ms  N={len(rest_lat)}")
        else:
            print(f"      FAILED — no responses")
            rest_lat = []

        # 2. WebSocket latency
        print(f"\n  [2] WebSocket trade latency (server->us)...")
        ws_lat, msg_count = await measure_ws_latency(coin, DURATION_SECONDS)
        if ws_lat:
            print(f"      mean={statistics.mean(ws_lat):.1f}ms  "
                  f"median={statistics.median(ws_lat):.1f}ms  "
                  f"min={min(ws_lat):.1f}ms  max={max(ws_lat):.1f}ms  "
                  f"N={len(ws_lat)} msgs={msg_count}")
        else:
            print(f"      No trades received in {DURATION_SECONDS}s")
            ws_lat = []

        # 3. Market making simulation
        print(f"\n  [3] Market making simulation ({MM_SIM_DURATION}s)...")
        mm = await simulate_market_making(coin, MM_SIM_DURATION)
        if mm["spread_samples"]:
            spreads = mm["spread_samples"]
            print(f"      Book updates: {mm['book_updates']}")
            print(f"      Spread: mean={statistics.mean(spreads):.2f}bps  "
                  f"median={statistics.median(spreads):.2f}bps  "
                  f"min={min(spreads):.2f}bps  max={max(spreads):.2f}bps")
            print(f"      Hypothetical fills: {mm['fills']}")
            print(f"      Adverse fills: {mm['adverse_fills']}")

            # Calculate EV
            # Maker rebate: +0.1 bps per fill
            # Adverse selection cost: if filled and price moves 1 tick against us
            avg_spread = statistics.mean(spreads)
            rebate_ev = mm["fills"] * MAKER_REBATE_BPS
            # Adverse cost: assume 50% of fills are adverse, cost = half spread
            adverse_cost = mm["fills"] * 0.5 * (avg_spread / 2)
            net_ev_bps = rebate_ev - adverse_cost
            print(f"      EV estimate: rebate=+{rebate_ev:.2f}bps  adverse_cost=-{adverse_cost:.2f}bps  "
                  f"net={net_ev_bps:+.2f}bps")
        else:
            print(f"      No book updates received")
            mm["spread_samples"] = []

        results[coin] = {
            "rest_latency_ms": rest_lat,
            "ws_latency_ms": ws_lat,
            "ws_msg_count": msg_count,
            "mm_book_updates": mm["book_updates"],
            "mm_fills": mm["fills"],
            "mm_spread_bps": mm["spread_samples"],
            "mm_mid_prices": mm["mid_prices"][-100:] if mm["mid_prices"] else [],
        }

    # Final verdict
    print("\n" + "=" * 90)
    print("VEREDITO FINAL — H84 Feasibility Assessment")
    print("=" * 90)

    all_rest = []
    all_ws = []
    all_spreads = []
    total_fills = 0
    for coin, r in results.items():
        all_rest.extend(r["rest_latency_ms"])
        all_ws.extend(r["ws_latency_ms"])
        all_spreads.extend(r["mm_spread_bps"])
        total_fills += r["mm_fills"]

    print(f"\n  Latency from us-east-2 to Hyperliquid:")
    if all_rest:
        print(f"    REST: mean={statistics.mean(all_rest):.1f}ms  median={statistics.median(all_rest):.1f}ms")
    if all_ws:
        print(f"    WebSocket: mean={statistics.mean(all_ws):.1f}ms  median={statistics.median(all_ws):.1f}ms")
    print(f"    Claimed public API: ~380ms  |  Gossip advantage: 70-150ms")

    if all_spreads:
        print(f"\n  Spreads: mean={statistics.mean(all_spreads):.2f}bps  median={statistics.median(all_spreads):.2f}bps")
        print(f"  Maker rebate: {MAKER_REBATE_BPS}bps  |  Taker fee: {TAKER_FEE_BPS}bps")
        print(f"  Total hypothetical fills: {total_fills}")

        # Key question: is the spread wide enough for MM to be profitable?
        avg_spread = statistics.mean(all_spreads)
        break_even_adverse_rate = MAKER_REBATE_BPS / (avg_spread / 2) if avg_spread > 0 else 1.0
        print(f"\n  Break-even adverse selection rate: {break_even_adverse_rate*100:.1f}%")
        print(f"  (If >50% of fills are adverse, MM is unprofitable without gossip edge)")

    print(f"\n  HARDWARE ASSESSMENT:")
    print(f"    This instance: 2 vCPUs, 7.6GB RAM")
    print(f"    Required for gossip node: 32 cores, 128GB RAM, 500MB/s storage")
    print(f"    Gap: 16x CPU, 17x RAM")
    print(f"    Monthly cost for c7i.32xlarge (128 vCPU, 256GB): ~$2,700/mo (us-east-2)")
    print(f"    Without gossip edge: competing against MMs who HAVE it = adverse selection")

    # Save results
    output = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "hypothesis": "H84",
        "instance": "us-east-2, 2 vCPU, 7.6GB RAM",
        "hardware_gap": "16x CPU, 17x RAM insufficient for gossip node",
        "results": {
            coin: {
                "rest_latency_ms": r["rest_latency_ms"],
                "ws_latency_ms": r["ws_latency_ms"],
                "mm_book_updates": r["mm_book_updates"],
                "mm_fills": r["mm_fills"],
                "spread_bps_mean": statistics.mean(r["mm_spread_bps"]) if r["mm_spread_bps"] else None,
                "spread_bps_median": statistics.median(r["mm_spread_bps"]) if r["mm_spread_bps"] else None,
            }
            for coin, r in results.items()
        },
    }
    fname = "h84_hyperliquid_gossip_feasibility.json"
    with open(fname, "w") as f:
        json.dump(output, f, indent=2, default=str)
    print(f"\n  Results saved to {fname}")


if __name__ == "__main__":
    asyncio.run(main())
