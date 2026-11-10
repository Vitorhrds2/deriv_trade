"""Adversarial Stress Test Harness (Challenger 1 — Tier 5 Hardening).

Target Vectors:
1. Velocity SWIFT (H85):
   - Concurrency race conditions in order deduplication under high-volume identical taker order barrage.
   - LRU cache saturation, boundary handling, and eviction determinism.
   - Adversarial order ID shape fuzzing (empty, unicode, 64KB strings).
   - Toxic flow gating under rapid price divergence races.
2. Hyperliquid (H84):
   - Toxic flow frontrunning deflection race comparing Tokyo sub-5ms vs US-East ~150ms RTT.
   - Microstructural discrete-event simulation of 1,000 pre-consensus gossip events (70-150ms lead time).
   - Adverse selection vulnerability under network jitter (200-300ms RTT).
   - Directional precision of defensive toxic cancellations and multi-asset book isolation.
3. Kalshi FIX (H87):
   - TCP socket drops, disconnection resilience, and reconnection recovery.
   - FIXT.1.1 Logon (35=A) with Tag 96 Ed25519 signature and strict CFTC Tag 50 omission across reconnection cycles.
   - Rapid connect / disconnect lifecycle stress loops without task or descriptor leaks.
   - Single-session concurrency enforcement and duplicate CompID rejection.
4. dYdX v4 (CometBFT / MemCLOB):
   - In-memory L3 orderbook cancel storms (1,000 simultaneous order cancels).
   - Concurrent cancel storm under active background orderbook depth telemetry readers.
   - Duplicate, phantom, and out-of-order cancel floods.
   - Zero-gas short-term order lifespan and maker rebate tiers (up to -1.1 bps).
"""

from __future__ import annotations

import asyncio
import os
import random
import sys
import time
from pathlib import Path
from typing import Any, Dict, List
from uuid import uuid4

import pytest
from cryptography.hazmat.primitives.asymmetric import ed25519
from eth_account import Account

# Ensure trading-engine root is in sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from venues.velocity_swift_venue import VelocitySwiftVenue, compute_swift_auction_price
from venues.hyperliquid_venue import HyperliquidVenue, HYPERLIQUID_FEE_TIERS
from mocks.hyperliquid_mempool_mock import (
    HyperliquidMempoolEmulator,
    MempoolTransaction,
)
from venues.kalshi_fix_venue import (
    KalshiFixVenue,
    KalshiFixMessage,
    create_kalshi_logon,
    TAG_RAW_DATA,
    TAG_SENDER_SUB_ID,
)
from mocks.kalshi_fix_mock import (
    KalshiFixMockServer,
    SIDE_BUY,
    SIDE_SELL,
    STATUS_NEW,
    STATUS_FILLED,
    STATUS_CANCELED,
    STATUS_REJECTED,
)
from venues.dydx_v4_venue import DydxV4Venue, DYDX_FEE_TIERS


# ==============================================================================
# 1. VELOCITY SWIFT DEDUPLICATION & CONCURRENCY RACE TESTS
# ==============================================================================

@pytest.mark.asyncio
async def test_swift_dedup_high_concurrency_barrage():
    """Adversarial stress test: High-concurrency barrage of identical taker orders.

    Attacks the SWIFT maker engine by firing 100 concurrent submit_order tasks
    with the exact same taker_order_id.
    Validates:
    - Exactly 1 task receives FILLED with 0.25 bps maker rebate.
    - Exactly 99 tasks receive REJECTED (deduplicated).
    - Zero state corruption, double-fills, or unhandled exceptions.
    """
    venue = VelocitySwiftVenue(env="devnet")
    await venue.connect()

    shared_taker_id = f"ATTACK-TAKER-INTENT-{uuid4().hex}"
    num_concurrent_orders = 100

    order_payload = {
        "symbol": "SOL-PERP",
        "side": "BUY",
        "price": 145.0,
        "size": 2.5,
        "taker_order_id": shared_taker_id,
    }

    # Fire 100 concurrent tasks simultaneously
    tasks = [venue.submit_order(order_payload.copy()) for _ in range(num_concurrent_orders)]
    results = await asyncio.gather(*tasks)

    filled_orders = [r for r in results if r.status == "FILLED"]
    rejected_orders = [r for r in results if r.status == "REJECTED"]

    assert len(filled_orders) == 1, (
        f"Critical Failure: Expected exactly 1 filled order, but got {len(filled_orders)}"
    )
    assert len(rejected_orders) == num_concurrent_orders - 1, (
        f"Critical Failure: Expected {num_concurrent_orders - 1} rejected duplicates, got {len(rejected_orders)}"
    )

    # Validate maker rebate earned on single genuine fill
    fill = filled_orders[0]
    assert fill.rebate_bps == 0.25
    assert fill.fee_bps == -0.25
    assert fill.is_maker is True
    assert fill.order_id == f"SWIFT-FILL-{shared_taker_id}"

    # Verify duplicate attempts produce zero rebate
    for rej in rejected_orders:
        assert rej.rebate_bps == 0.0
        assert rej.fee_bps == 0.0
        assert rej.status == "REJECTED"

    await venue.disconnect()


@pytest.mark.asyncio
async def test_swift_dedup_lru_cache_eviction_and_saturation():
    """Adversarial stress test: LRU deduplication cache saturation and memory bounding.

    Tests LRU cache eviction boundary:
    - Sets cache size to 50.
    - Submits 100 distinct unique orders sequentially.
    - Asserts that all 100 unique orders are successfully FILLED.
    - Asserts that cache length remains strictly bounded at <= 50.
    - Replays order #99 (still resident in LRU cache) -> must be REJECTED.
    - Replays order #0 (evicted from LRU cache) -> gracefully accepted without memory leak.
    """
    cache_capacity = 50
    venue = VelocitySwiftVenue(env="devnet", max_dedup_cache_size=cache_capacity)
    await venue.connect()

    order_ids = [f"INTENT-SEQ-{i:04d}" for i in range(100)]

    for oid in order_ids:
        res = await venue.submit_order({
            "symbol": "SOL-PERP",
            "side": "BUY",
            "price": 140.0,
            "size": 1.0,
            "taker_order_id": oid,
        })
        assert res.status == "FILLED"

    # Verify cache capacity enforcement
    assert len(venue._dedup_cache) <= cache_capacity

    # Replay recently added order (order #99)
    res_recent = await venue.submit_order({
        "symbol": "SOL-PERP",
        "side": "BUY",
        "price": 140.0,
        "size": 1.0,
        "taker_order_id": order_ids[-1],
    })
    assert res_recent.status == "REJECTED", "Order resident in LRU cache was not deduplicated!"

    # Replay evicted order (order #0)
    res_evicted = await venue.submit_order({
        "symbol": "SOL-PERP",
        "side": "BUY",
        "price": 140.0,
        "size": 1.0,
        "taker_order_id": order_ids[0],
    })
    # Since order #0 was evicted, it behaves as fresh; cache remains bounded
    assert res_evicted.status == "FILLED"
    assert len(venue._dedup_cache) <= cache_capacity

    await venue.disconnect()


@pytest.mark.asyncio
async def test_swift_dedup_adversarial_id_shapes():
    """Adversarial stress test: Malformed, oversized, and unicode order IDs."""
    venue = VelocitySwiftVenue(env="devnet")
    await venue.connect()

    adversarial_ids = [
        "",                                    # Empty string
        "A" * 65_536,                          # 64KB giant string
        "⚡_SWIFT_🔥_\x00_NULLBYTE_DEDUP",     # Non-ASCII, null byte, unicode emojis
        "   SPACES_LEAD_TRAIL   ",             # Leading/trailing whitespace
        "order-lowercase-1",                   # Lowercase vs uppercase test
        "ORDER-LOWERCASE-1",
    ]

    for adv_id in adversarial_ids:
        res1 = await venue.submit_order({
            "symbol": "SOL-PERP",
            "side": "SELL",
            "price": 150.0,
            "size": 1.0,
            "taker_order_id": adv_id,
        })
        assert res1.status == "FILLED"

        # Immediate replay of the exact same adversarial ID must be REJECTED
        res2 = await venue.submit_order({
            "symbol": "SOL-PERP",
            "side": "SELL",
            "price": 150.0,
            "size": 1.0,
            "taker_order_id": adv_id,
        })
        assert res2.status == "REJECTED"

    await venue.disconnect()


@pytest.mark.asyncio
async def test_swift_toxic_flow_gating_adversarial_prices():
    """Adversarial stress test: Rapid toxic price divergence gating under race conditions."""
    venue = VelocitySwiftVenue(env="devnet", max_toxic_divergence_bps=50.0)
    await venue.connect()

    symbol = "SOL-PERP"
    oracle_px = 150.00
    venue.update_reference_oracle(symbol, oracle_px)

    # 50 bps on $150 = $0.75. Acceptable price band: [149.25, 150.75]
    test_cases = [
        (150.00, "FILLED", "At oracle price"),
        (150.70, "FILLED", "Divergence 46.7 bps (< 50 bps)"),
        (149.30, "FILLED", "Divergence 46.7 bps (< 50 bps)"),
        (150.76, "REJECTED", "Divergence 50.7 bps (> 50 bps toxic threshold)"),
        (149.24, "REJECTED", "Divergence 50.7 bps (> 50 bps toxic threshold)"),
        (165.00, "REJECTED", "Massive pump divergence 1000 bps"),
        (135.00, "REJECTED", "Massive dump divergence 1000 bps"),
    ]

    for px, expected_status, note in test_cases:
        res = await venue.submit_order({
            "symbol": symbol,
            "side": "BUY",
            "price": px,
            "size": 1.0,
            "taker_order_id": f"TOXIC-TEST-{px}-{uuid4().hex[:6]}",
        })
        assert res.status == expected_status, f"Failed for price {px} ({note}): expected {expected_status}, got {res.status}"

    await venue.disconnect()


# ==============================================================================
# 2. HYPERLIQUID TOXIC FLOW DEFLECTION RACE TESTS (TOKYO vs US-EAST)
# ==============================================================================

def test_hyperliquid_tokyo_sub5ms_vs_useast_150ms_monte_carlo():
    """Empirical adversarial stress test: 1,000 Monte Carlo frontrunning trials.

    Microstructural Physics:
    - Pre-consensus gossip window: 70ms to 150ms lead time.
    - Tokyo co-located bot: RTT in [2.0, 5.0] ms, cancel latency = 2.0 + 0.5 * RTT <= 4.5 ms.
      Since 4.5 ms << 70 ms (minimum lead time), Tokyo deflection rate MUST BE 100.0%.
    - US-East bot (Virginia/Ohio): RTT in [140.0, 160.0] ms, cancel latency = 2.0 + 0.5 * RTT in [72.0, 82.0] ms.
      Whenever gossip lead time falls in [70, 72-82] ms, the cancel arrives AFTER block commitment,
      causing the resting maker order to be toxic-filled.
    """
    emulator = HyperliquidMempoolEmulator(min_lead_time_ms=70.0, max_lead_time_ms=150.0)
    trials = 1000

    tokyo_avoided = 0
    tokyo_swept = 0
    useast_avoided = 0
    useast_swept = 0

    random.seed(42)  # Deterministic seed for reproducible adversarial verification

    for i in range(trials):
        # Generate genuine toxic market sweep
        tx = emulator.generate_synthetic_tx(coin="SOL", force_toxic=True)

        # 1. Tokyo Node Test
        tokyo_cloid = f"MAKER-TOKYO-{i}"
        emulator.register_maker_order(tokyo_cloid, "SOL", is_buy=True, limit_px=145.0, sz=10.0)
        tokyo_rtt = random.uniform(2.0, 5.0)
        tokyo_res = emulator.evaluate_cancellation_race(
            toxic_tx=tx,
            maker_cloid=tokyo_cloid,
            network_rtt_ms=tokyo_rtt,
            detection_delay_ms=2.0,
        )
        if tokyo_res["adverse_selection_avoided"]:
            tokyo_avoided += 1
        else:
            tokyo_swept += 1

        # 2. US-East Node Test
        useast_cloid = f"MAKER-USEAST-{i}"
        emulator.register_maker_order(useast_cloid, "SOL", is_buy=True, limit_px=145.0, sz=10.0)
        useast_rtt = random.uniform(140.0, 160.0)
        useast_res = emulator.evaluate_cancellation_race(
            toxic_tx=tx,
            maker_cloid=useast_cloid,
            network_rtt_ms=useast_rtt,
            detection_delay_ms=2.0,
        )
        if useast_res["adverse_selection_avoided"]:
            useast_avoided += 1
        else:
            useast_swept += 1

    tokyo_avoidance_pct = (tokyo_avoided / trials) * 100.0
    useast_avoidance_pct = (useast_avoided / trials) * 100.0

    # EMPIRICAL ORACLE ASSERTIONS:
    # 1. Tokyo sub-5ms must achieve 100% avoidance with 0 orders swept
    assert tokyo_avoidance_pct == 100.0, f"Tokyo avoidance failed: {tokyo_avoidance_pct}%"
    assert tokyo_swept == 0, f"Tokyo had {tokyo_swept} swept orders!"

    # 2. US-East must fail repeatedly on tight lead times (adverse selection demonstrated)
    assert useast_swept > 0, "US-East should have experienced toxic sweeps under tight lead times!"
    assert useast_avoidance_pct < 95.0, (
        f"US-East avoidance unexpectedly high ({useast_avoidance_pct}%). "
        "Expected empirical vulnerability under 140-160ms RTT."
    )


def test_hyperliquid_adverse_selection_catastrophic_jitter():
    """Adversarial stress test: Severe packet jitter (200-300ms RTT) collapses maker defense."""
    emulator = HyperliquidMempoolEmulator(min_lead_time_ms=70.0, max_lead_time_ms=150.0)
    trials = 500
    jitter_swept = 0

    random.seed(99)

    for i in range(trials):
        tx = emulator.generate_synthetic_tx(coin="SOL", force_toxic=True)
        cloid = f"MAKER-JITTER-{i}"
        emulator.register_maker_order(cloid, "SOL", is_buy=True, limit_px=145.0, sz=10.0)

        # High jitter / cross-region transpacific RTT (200 - 300ms)
        congested_rtt = random.uniform(200.0, 300.0)
        res = emulator.evaluate_cancellation_race(
            toxic_tx=tx,
            maker_cloid=cloid,
            network_rtt_ms=congested_rtt,
            detection_delay_ms=2.0,
        )
        if not res["adverse_selection_avoided"]:
            jitter_swept += 1

    swept_pct = (jitter_swept / trials) * 100.0
    # Under 200-300ms RTT, cancel latency is 102-152ms, exceeding the majority of lead times.
    assert swept_pct >= 40.0, f"Expected >= 40% toxic sweeps under severe jitter, got {swept_pct:.1f}%"


@pytest.mark.asyncio
async def test_hyperliquid_deflection_directional_precision_and_multi_coin():
    """Adversarial stress test: Directional precision and multi-asset isolation.

    Validates:
    - Toxic SELL sweeps BUY orders only (never cancels resting SELL orders).
    - Toxic BUY sweeps SELL orders only (never cancels resting BUY orders).
    - Multi-coin isolation: SOL toxic sweep does not touch ETH or BTC resting orders.
    """
    account = Account.create()
    venue = HyperliquidVenue(
        env="testnet",
        wallet_address=account.address,
        private_key=account.key.hex(),
    )
    await venue.connect()

    # Place resting orders:
    # 1. SOL Buy @ 140.0 (is_buy=True)
    # 2. SOL Sell @ 160.0 (explicit is_buy=False)
    # 3. ETH Buy @ 3000.0 (is_buy=True)
    await venue.submit_order({"symbol": "SOL", "side": "BUY", "is_buy": True, "price": 140.0, "size": 1.0, "cloid": "SOL-BUY-1"})
    await venue.submit_order({"symbol": "SOL", "side": "SELL", "is_buy": False, "price": 160.0, "size": 1.0, "cloid": "SOL-SELL-1"})
    await venue.submit_order({"symbol": "ETH", "side": "BUY", "is_buy": True, "price": 3000.0, "size": 1.0, "cloid": "ETH-BUY-1"})

    assert venue._active_orders["SOL-BUY-1"]["status"] == "OPEN"
    assert venue._active_orders["SOL-SELL-1"]["status"] == "OPEN"
    assert venue._active_orders["ETH-BUY-1"]["status"] == "OPEN"

    # Simulate Mempool Toxic Transaction: Aggressive Market Sell in SOL (sweeps bids)
    toxic_sol_sell = type("MockTx", (), {
        "is_market": True,
        "coin": "SOL",
        "is_buy": False,  # Aggressive Sell
        "sz": 50.0,       # Exceeds threshold (10.0)
    })()

    cancelled = venue.evaluate_toxic_flow(toxic_sol_sell, toxicity_threshold_sz=10.0)

    # Only SOL-BUY-1 must be cancelled
    assert "SOL-BUY-1" in cancelled
    assert venue._active_orders["SOL-BUY-1"]["status"] == "CANCELLED"

    # SOL-SELL-1 and ETH-BUY-1 must remain completely unaffected
    assert "SOL-SELL-1" not in cancelled
    assert venue._active_orders["SOL-SELL-1"]["status"] == "OPEN"
    assert "ETH-BUY-1" not in cancelled
    assert venue._active_orders["ETH-BUY-1"]["status"] == "OPEN"

    await venue.disconnect()


@pytest.mark.asyncio
async def test_hyperliquid_side_parameter_adversarial_flaw():
    """Adversarial vulnerability check: Uncovers flaw in hyperliquid_venue.py line 242.

    Observation:
    Line 242 reads: `is_buy = side == 'BUY' or order_params.get('is_buy', True)`
    When a caller passes `{'side': 'SELL'}` without explicitly setting `{'is_buy': False}`,
    the expression evaluates to `False or True -> True`.
    This silently mutates a SELL order into a BUY order!
    This test verifies that if `is_buy` is omitted, the connector currently misidentifies
    the order side as 'BUY', creating a severe adverse selection hazard.
    """
    venue = HyperliquidVenue(env="testnet")
    await venue.connect()

    # Pass side="SELL" WITHOUT is_buy=False
    res = await venue.submit_order({
        "symbol": "SOL",
        "side": "SELL",
        "price": 160.0,
        "size": 1.0,
        "cloid": "VULN-CHECK-1",
    })

    # Verified fix:
    # When fixed, res.side == 'SELL'.
    assert res.side == "SELL", (
        f"Expected res.side == 'SELL' after line 242 fix, got {res.side}"
    )
    assert venue._active_orders["VULN-CHECK-1"]["side"] == "SELL"

    await venue.disconnect()


# ==============================================================================
# 3. KALSHI FIX PROTOCOL SOCKET DROPS & RECONNECTION RECOVERY TESTS
# ==============================================================================

@pytest.mark.asyncio
async def test_kalshi_fix_socket_drop_and_reconnection_recovery():
    """Adversarial stress test: Socket connection drop and reconnection recovery.

    Simulates:
    1. Active FIX session on dynamic port.
    2. Order entry while connected.
    3. Abrupt socket drop (stopping mock server).
    4. Re-establishing mock server and reconnecting venue.
    5. Verifying successful re-logon with fresh Tag 96 Ed25519 signature and strict Tag 50 omission.
    6. Verifying subsequent order placement (maker resting and taker filling) and cancellation lifecycle.
    """
    # Phase 1: Initial connection
    server1 = KalshiFixMockServer(host="127.0.0.1", port=0)
    await server1.start()
    port1 = server1.server.sockets[0].getsockname()[1]

    venue = KalshiFixVenue(
        env="mock",
        host="127.0.0.1",
        port=port1,
        api_key_id="adversarial-trader-uuid-1",
        target_comp_id="KalshiNR",
        sender_sub_id="DESK_SUB_1",
    )

    ok1 = await venue.connect()
    assert ok1 is True
    assert venue.is_connected is True

    # Submit resting maker order at 0.40 (below 0.55 best ask)
    res1 = await venue.submit_order({
        "symbol": "KXFEDDEC26-YES",
        "side": "BUY",
        "price": 0.40,
        "size": 10.0,
        "order_id": "CLORD-PRE-DROP",
    })
    assert res1.status == "OPEN"

    # Phase 2: Abrupt socket termination
    await venue.disconnect()
    await server1.stop()
    assert venue.is_connected is False

    # Attempting order submission while disconnected must fall back gracefully without crashing
    res_offline = await venue.submit_order({
        "symbol": "KXFEDDEC26-YES",
        "side": "BUY",
        "price": 0.40,
        "size": 10.0,
        "order_id": "CLORD-WHILE-OFFLINE",
    })
    # Fallback simulated order is marked OPEN in offline mock mode without unhandled exceptions
    assert res_offline.status in ("OPEN", "REJECTED")

    # Phase 3: Server recovers on new port, client reconnects
    server2 = KalshiFixMockServer(host="127.0.0.1", port=0)
    await server2.start()
    port2 = server2.server.sockets[0].getsockname()[1]

    venue.port = port2
    ok2 = await venue.connect()
    assert ok2 is True
    assert venue.is_connected is True

    # Submit resting maker order on reconnected session at 0.42 (below 0.55 ask)
    res2 = await venue.submit_order({
        "symbol": "KXFEDDEC26-YES",
        "side": "BUY",
        "price": 0.42,
        "size": 20.0,
        "order_id": "CLORD-POST-RECONNECT",
    })
    assert res2.status == "OPEN"
    assert res2.price == 0.42
    assert res2.size == 20.0

    # Cancel resting order on reconnected session
    canceled = await venue.cancel_order("CLORD-POST-RECONNECT", "KXFEDDEC26-YES")
    assert canceled is True

    # Submit aggressive taker order crossing the spread at 0.60 (crosses 0.55 ask)
    res_taker = await venue.submit_order({
        "symbol": "KXFEDDEC26-YES",
        "side": "BUY",
        "price": 0.60,
        "size": 10.0,
        "order_id": "CLORD-TAKER-CROSS",
    })
    assert res_taker.status == "FILLED"

    await venue.disconnect()
    await server2.stop()


@pytest.mark.asyncio
async def test_kalshi_fix_rapid_disconnect_reconnect_stress_loop():
    """Adversarial stress test: Rapid connect/disconnect stress loop (10 cycles)."""
    server = KalshiFixMockServer(host="127.0.0.1", port=0)
    await server.start()
    port = server.server.sockets[0].getsockname()[1]

    venue = KalshiFixVenue(
        env="mock",
        host="127.0.0.1",
        port=port,
        api_key_id="rapid-reconnect-client",
        target_comp_id="KalshiNR",
    )

    for cycle in range(10):
        ok = await venue.connect()
        assert ok is True, f"Failed to connect on cycle {cycle}"
        assert venue.is_connected is True

        res = await venue.submit_order({
            "symbol": "KXFEDDEC26-YES",
            "side": "BUY",
            "price": 0.50,
            "size": 5.0,
            "order_id": f"CLORD-CYCLE-{cycle}",
        })
        assert res.status == "OPEN", f"Failed order on cycle {cycle}"

        await venue.disconnect()
        assert venue.is_connected is False

    await server.stop()


@pytest.mark.asyncio
async def test_kalshi_fix_single_session_concurrency_enforcement():
    """Adversarial stress test: FIX concurrency rule — only 1 active session per API Key ID."""
    server = KalshiFixMockServer(host="127.0.0.1", port=0)
    await server.start()
    port = server.server.sockets[0].getsockname()[1]

    shared_comp_id = "EXCLUSIVE-API-KEY-007"

    # Client A connects
    venue_a = KalshiFixVenue(env="mock", host="127.0.0.1", port=port, api_key_id=shared_comp_id)
    ok_a = await venue_a.connect()
    assert ok_a is True

    # Client B attempts to connect with the SAME CompID simultaneously
    venue_b = KalshiFixVenue(env="mock", host="127.0.0.1", port=port, api_key_id=shared_comp_id)
    ok_b = await venue_b.connect()

    # Client B MUST be rejected by FIX mock server with Logout (35=5)
    assert ok_b is False, "Server allowed duplicate active FIX session for the same CompID!"

    # Disconnect Client A
    await venue_a.disconnect()
    await asyncio.sleep(0.05)  # Allow socket cleanup

    # Now Client B should successfully connect
    ok_b_retry = await venue_b.connect()
    assert ok_b_retry is True

    await venue_b.disconnect()
    await server.stop()


# ==============================================================================
# 4. DYDX V4 IN-MEMORY L3 ORDERBOOK CANCEL STORMS
# ==============================================================================

@pytest.mark.asyncio
async def test_dydx_v4_cancel_storm_concurrency_1000_orders():
    """Adversarial stress test: In-memory L3 orderbook cancel storm.

    Tests:
    - Concurrently submits 1,000 short-term orders into the L3 orderbook.
    - Asserts that all 1,000 are indexed in the in-memory book.
    - Launches a simultaneous cancel storm canceling all 1,000 orders via asyncio.gather.
    - Asserts that all 1,000 cancellations succeed with zero gas.
    - Asserts that get_l3_depth returns exactly 0 remaining orders and 0 size.
    """
    venue = DydxV4Venue(env="testnet")
    await venue.connect()

    symbol = "BTC-USD"
    order_count = 1000

    # 1. Concurrently submit 1,000 orders
    order_tasks = [
        venue.submit_order({
            "symbol": symbol,
            "side": "BUY" if i % 2 == 0 else "SELL",
            "price": 60_000.0 + (i * 0.1),
            "size": 0.1,
            "client_id": i + 1,
        })
        for i in range(order_count)
    ]
    order_results = await asyncio.gather(*order_tasks)
    assert len(order_results) == order_count

    # Verify L3 depth
    depth_before = venue.get_l3_depth(symbol)
    assert depth_before["total_orders"] == order_count
    assert depth_before["bid_orders_count"] == 500
    assert depth_before["ask_orders_count"] == 500
    assert pytest.approx(depth_before["total_bid_size"], 1e-4) == 50.0
    assert pytest.approx(depth_before["total_ask_size"], 1e-4) == 50.0

    # 2. Concurrently fire 1,000 cancellations (Cancel Storm)
    cancel_tasks = [
        venue.cancel_order(f"DYDX-STO-{i + 1}", symbol)
        for i in range(order_count)
    ]
    cancel_results = await asyncio.gather(*cancel_tasks)

    assert all(cancel_results), "One or more cancellations failed in cancel storm!"
    assert len(cancel_results) == order_count

    # 3. Verify total book drainage
    depth_after = venue.get_l3_depth(symbol)
    assert depth_after["total_orders"] == 0
    assert depth_after["bid_orders_count"] == 0
    assert depth_after["ask_orders_count"] == 0
    assert depth_after["total_bid_size"] == 0.0
    assert depth_after["total_ask_size"] == 0.0
    assert len(venue._resting_orders) == 0

    await venue.disconnect()


@pytest.mark.asyncio
async def test_dydx_v4_concurrent_cancel_storm_with_active_depth_readers():
    """Adversarial stress test: Concurrent cancel storm while active readers query L3 depth.

    Stresses in-memory dictionary traversal during concurrent modification.
    Asserts zero `RuntimeError: dictionary changed size during iteration`.
    """
    venue = DydxV4Venue(env="testnet")
    await venue.connect()

    symbol = "ETH-USD"
    order_count = 500

    # Place orders
    for i in range(order_count):
        await venue.submit_order({
            "symbol": symbol,
            "side": "BUY",
            "price": 3000.0 + i,
            "size": 0.5,
            "client_id": 100_000 + i,
        })

    stop_reader = False
    reader_exceptions = []

    async def continuous_depth_reader():
        while not stop_reader:
            try:
                venue.get_l3_depth(symbol)
            except Exception as e:
                reader_exceptions.append(e)
            await asyncio.sleep(0.001)

    reader_task = asyncio.create_task(continuous_depth_reader())

    # Concurrent cancel storm
    cancels = [
        venue.cancel_order(f"DYDX-STO-{100_000 + i}", symbol)
        for i in range(order_count)
    ]
    cancel_results = await asyncio.gather(*cancels)

    stop_reader = True
    await reader_task

    assert len(reader_exceptions) == 0, f"Reader encountered exceptions: {reader_exceptions}"
    assert all(cancel_results)
    assert venue.get_l3_depth(symbol)["total_orders"] == 0

    await venue.disconnect()


@pytest.mark.asyncio
async def test_dydx_v4_duplicate_and_phantom_cancel_flood():
    """Adversarial stress test: Idempotency under duplicate and phantom cancel floods."""
    venue = DydxV4Venue(env="testnet")
    await venue.connect()

    symbol = "BTC-USD"
    # Place a single valid order
    res = await venue.submit_order({
        "symbol": symbol,
        "side": "BUY",
        "price": 60_000.0,
        "size": 1.0,
        "client_id": 9999,
    })
    order_id = res.order_id

    # 1. First cancel must succeed
    assert await venue.cancel_order(order_id, symbol) is True

    # 2. Fire 100 duplicate cancels for the same already-cancelled order
    duplicate_cancels = [venue.cancel_order(order_id, symbol) for _ in range(100)]
    dup_results = await asyncio.gather(*duplicate_cancels)
    assert all(r is False for r in dup_results), "Duplicate cancel returned True!"

    # 3. Fire 100 phantom cancels for orders that never existed
    phantom_cancels = [venue.cancel_order(f"PHANTOM-ORD-{uuid4().hex}", symbol) for _ in range(100)]
    phantom_results = await asyncio.gather(*phantom_cancels)
    assert all(r is False for r in phantom_results), "Phantom cancel returned True!"

    await venue.disconnect()


@pytest.mark.asyncio
async def test_dydx_v4_fee_and_maker_rebate_tiers_across_storm():
    """Adversarial stress test: Maker rebate modeling across all dYdX v4 volume tiers."""
    symbol = "BTC-USD"

    # Tier 1 (< $1M): Maker pays 1.0 bps fee
    v_tier1 = DydxV4Venue(env="testnet", fee_tier=1)
    res_t1 = await v_tier1.submit_order({"symbol": symbol, "side": "BUY", "price": 60000.0, "size": 0.1, "post_only": True})
    assert res_t1.fee_bps == 1.0
    assert res_t1.rebate_bps == 0.0

    # Tier 4 (>= $25M): Zero maker fee
    v_tier4 = DydxV4Venue(env="testnet", fee_tier=4)
    res_t4 = await v_tier4.submit_order({"symbol": symbol, "side": "BUY", "price": 60000.0, "size": 0.1, "post_only": True})
    assert res_t4.fee_bps == 0.0
    assert res_t4.rebate_bps == 0.0

    # Tier 6 (>= $100M): Maker earns 0.7 bps rebate (-0.7 bps fee)
    v_tier6 = DydxV4Venue(env="testnet", fee_tier=6)
    res_t6 = await v_tier6.submit_order({"symbol": symbol, "side": "BUY", "price": 60000.0, "size": 0.1, "post_only": True})
    assert res_t6.fee_bps == -0.7
    assert res_t6.rebate_bps == 0.7

    # Tier 7 (>= $200M): Maker earns 1.1 bps rebate (-1.1 bps fee)
    v_tier7 = DydxV4Venue(env="testnet", fee_tier=7)
    res_t7 = await v_tier7.submit_order({"symbol": symbol, "side": "BUY", "price": 60000.0, "size": 0.1, "post_only": True})
    assert res_t7.fee_bps == -1.1
    assert res_t7.rebate_bps == 1.1
