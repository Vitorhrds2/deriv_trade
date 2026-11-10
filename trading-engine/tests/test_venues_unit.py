"""Comprehensive Unit Test Suite for Venue Execution Connectors.

Validates all 6 quantitative market microstructure vectors per Milestone M3:
1. Base & Registry contracts (`MarketUpdate`, `OrderExecutionResult`, `UnifiedVenue`, registry auto-registration).
2. Hyperliquid (H84): l2Book levels parsing bug fix, EIP-712 signing, Post-Only ALO, mempool toxic flow defense.
3. Velocity SWIFT (H85): Ed25519 challenge auth, live Dutch auction curve P(t) bug fix, 0.25 bps maker rebate, LRU deduplication, toxic flow gating.
4. Sui DeepBookV3 (H86): Move 8-step PTB builder, Hot Potato 0-fee flash loan, Cetus AMM leg fix, zero leg risk dry-run simulation, Circle USDC pool.
5. Kalshi FIX (H87): Tag 96 Ed25519 auth, strict CFTC Tag 50 omission on Logon, binary contract execution and cancellation via mock server.
6. dYdX v4: L2/L3 orderbook maintainer, zero-gas short-term order placement, maker rebate tiers.
7. GMX v2 & CEXs: MEXC/Gate.io WS ticker parsing, dynamic price impact fee, lead-lag signal detection, acceptablePrice pull oracle barrier check, synthetic delta-neutral hedging.
"""

from __future__ import annotations

import asyncio
import os
import sys
import time
import pytest
from pathlib import Path

# Ensure trading-engine directory is on sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from eth_account import Account
from cryptography.hazmat.primitives.asymmetric import ed25519

from venues.base import MarketUpdate, OrderExecutionResult, UnifiedVenue
from venues.registry import get_venue, list_venues, register
from venues.hyperliquid_venue import HyperliquidVenue, HYPERLIQUID_FEE_TIERS
from venues.velocity_swift_venue import VelocitySwiftVenue, compute_swift_auction_price
from venues.sui_deepbook_venue import (
    SuiDeepBookVenue,
    SuiDeepBookPTBBuilder,
    HotPotatoPTBParams,
    SUI_USDC_POOL_ID,
    CIRCLE_USDC_TYPE,
)
from venues.kalshi_fix_venue import (
    KalshiFixVenue,
    KalshiFixMessage,
    create_kalshi_logon,
    TAG_RAW_DATA,
    TAG_SENDER_SUB_ID,
)
from mocks.kalshi_fix_mock import KalshiFixMockServer, SIDE_BUY, SIDE_SELL
from venues.dydx_v4_venue import DydxV4Venue, DYDX_FEE_TIERS
from venues.gmx_cex_venue import GmxCexVenue, compute_gmx_price_impact_fee


# ==============================================================================
# 1. BASE ABSTRACTIONS & REGISTRY TESTS
# ==============================================================================

def test_registry_and_contracts():
    """Validates unified venue interface and registry lookups."""
    registered = list_venues()
    expected_venues = [
        "hyperliquid",
        "velocity_swift",
        "sui_deepbook",
        "kalshi_fix",
        "dydx_v4",
        "gmx_cex",
    ]
    for v in expected_venues:
        assert v in registered
        cls = get_venue(v)
        assert issubclass(cls, UnifiedVenue)

    # Validate MarketUpdate dataclass
    mu = MarketUpdate(
        venue="test",
        symbol="SOL",
        bid_px=100.0,
        bid_sz=10.0,
        ask_px=100.5,
        ask_sz=8.0,
        timestamp_ns=1_000_000_000,
    )
    assert mu.bid_px == 100.0
    assert mu.ask_sz == 8.0

    # Validate OrderExecutionResult dataclass
    res = OrderExecutionResult(
        venue="test",
        order_id="ORD-1",
        symbol="SOL",
        side="BUY",
        price=100.0,
        size=5.0,
        fee_bps=1.5,
        rebate_bps=0.0,
        is_maker=True,
        status="FILLED",
        latency_ms=1.2,
        timestamp_ns=1_000_000_000,
    )
    assert res.status == "FILLED"
    assert res.is_maker is True


# ==============================================================================
# 2. HYPERLIQUID CONNECTOR (H84) TESTS
# ==============================================================================

@pytest.mark.asyncio
async def test_hyperliquid_l2_book_parsing_bug_fix():
    """Validates rectification of Post-Mortem 5.1: levels[0]=bids, levels[1]=asks."""
    venue = HyperliquidVenue(env="testnet")
    await venue.connect()

    # Raw message format directly from Hyperliquid public WebSocket
    raw_l2_book = {
        "channel": "l2Book",
        "data": {
            "coin": "SOL",
            "time": 1720000000000,
            "levels": [
                [{"px": "145.50", "sz": "10.0", "n": 3}, {"px": "145.40", "sz": "25.0", "n": 5}],
                [{"px": "145.55", "sz": "8.5", "n": 2}, {"px": "145.65", "sz": "15.0", "n": 4}],
            ],
        },
    }

    update = venue.parse_l2_book(raw_l2_book)
    assert update is not None
    assert update.symbol == "SOL"
    assert update.bid_px == 145.50
    assert update.bid_sz == 10.0
    assert update.ask_px == 145.55
    assert update.ask_sz == 8.5
    assert update.timestamp_ns == 1720000000000 * 1_000_000

    await venue.disconnect()


@pytest.mark.asyncio
async def test_hyperliquid_eip712_signing_and_alo_flag():
    """Validates cryptographic EIP-712 signing and Post-Only / ALO order rules."""
    account = Account.create()
    venue = HyperliquidVenue(
        env="testnet",
        wallet_address=account.address,
        private_key=account.key.hex(),
        fee_tier=0,
    )
    await venue.connect()

    # Verify ALO payload construction
    spec = venue.build_eip712_order_payload(
        coin="SOL",
        is_buy=True,
        sz=2.0,
        limit_px=140.0,
        post_only=True,
    )
    assert spec["coin"] == "SOL"
    assert spec["order_type"]["limit"]["tif"] == "Alo"

    # Verify EIP-712 action signing
    action = {"type": "order", "orders": [spec], "grouping": "na"}
    sig = venue.sign_action(action, nonce=123456789)
    assert "r" in sig and "s" in sig and "v" in sig
    assert sig["signature"].startswith("0x") or len(sig["signature"]) == 130

    # Test order submission resting as maker
    res_maker = await venue.submit_order({
        "coin": "SOL",
        "side": "BUY",
        "price": 140.0,
        "size": 2.0,
        "post_only": True,
    })
    assert res_maker.status == "OPEN"
    assert res_maker.is_maker is True
    assert res_maker.fee_bps == HYPERLIQUID_FEE_TIERS[0]["maker_bps"]

    # Seed orderbook with best ask = 145.0
    venue.parse_l2_book({
        "channel": "l2Book",
        "data": {
            "coin": "SOL",
            "time": 1720000000000,
            "levels": [
                [{"px": "144.50", "sz": "10.0", "n": 1}],
                [{"px": "145.00", "sz": "5.0", "n": 1}],
            ],
        },
    })

    # Order crossing the spread with post_only=True must be automatically CANCELLED/REJECTED
    res_crossing = await venue.submit_order({
        "coin": "SOL",
        "side": "BUY",
        "price": 146.0,  # Crossing best ask of 145.0
        "size": 1.0,
        "post_only": True,
    })
    assert res_crossing.status == "CANCELLED"
    assert res_crossing.fee_bps == 0.0

    await venue.disconnect()


@pytest.mark.asyncio
async def test_hyperliquid_mempool_toxic_flow_defense():
    """Validates pre-consensus mempool gossip stream toxic flow detection and order cancellation."""
    venue = HyperliquidVenue(env="testnet")
    await venue.connect()

    # Place resting maker buy order
    order_res = await venue.submit_order({
        "coin": "SOL",
        "side": "BUY",
        "price": 140.0,
        "size": 5.0,
        "post_only": True,
    })
    cloid = order_res.order_id
    assert cloid in venue._active_orders
    assert venue._active_orders[cloid]["status"] == "OPEN"

    # Simulate an incoming toxic market sell transaction from mempool
    class MockTx:
        def __init__(self, coin, is_buy, is_market, sz):
            self.coin = coin
            self.is_buy = is_buy
            self.is_market = is_market
            self.sz = sz

    # Small tx -> below threshold -> no cancellation
    small_tx = MockTx(coin="SOL", is_buy=False, is_market=True, sz=2.0)
    cancelled = venue.evaluate_toxic_flow(small_tx, toxicity_threshold_sz=10.0)
    assert len(cancelled) == 0
    assert venue._active_orders[cloid]["status"] == "OPEN"

    # Toxic market sell sweeping bids (sz=50.0 > 10.0)
    toxic_tx = MockTx(coin="SOL", is_buy=False, is_market=True, sz=50.0)
    cancelled = venue.evaluate_toxic_flow(toxic_tx, toxicity_threshold_sz=10.0)
    assert cloid in cancelled
    assert venue._active_orders[cloid]["status"] == "CANCELLED"
    assert venue._active_orders[cloid]["cancel_reason"] == "TOXIC_FLOW_AVOIDANCE"

    await venue.disconnect()


# ==============================================================================
# 3. VELOCITY SWIFT CONNECTOR (H85) TESTS
# ==============================================================================

def test_velocity_swift_dutch_auction_curve_math():
    """Validates rectification of Post-Mortem 5.2: live Dutch auction curve calculation."""
    # Test descending auction (taker sell): starts at 75.0, ends at 60.0 over 4000ms
    start_px = 75.0
    end_px = 60.0
    t0 = 1000
    duration = 4000

    # At start (t = 0)
    p_start = compute_swift_auction_price(start_px, end_px, start_time=t0, duration_ms=duration, current_time=1000)
    assert p_start == 75.0

    # At half duration (t = 2000ms)
    p_mid = compute_swift_auction_price(start_px, end_px, start_time=t0, duration_ms=duration, current_time=3000)
    assert p_mid == 67.5

    # At end (t = 4000ms)
    p_end = compute_swift_auction_price(start_px, end_px, start_time=t0, duration_ms=duration, current_time=5000)
    assert p_end == 60.0

    # Past duration (t > 4000ms) clamps to end_px
    p_past = compute_swift_auction_price(start_px, end_px, start_time=t0, duration_ms=duration, current_time=7000)
    assert p_past == 60.0


@pytest.mark.asyncio
async def test_velocity_swift_auth_rebate_and_deduplication():
    """Validates Ed25519 challenge auth, 0.25 bps maker rebate, and message deduplication."""
    priv = ed25519.Ed25519PrivateKey.generate()
    venue = VelocitySwiftVenue(env="devnet", private_key_bytes=priv.private_bytes_raw())
    await venue.connect()

    # Test challenge authentication
    auth_resp = venue.authenticate_challenge("CHALLENGE_NONCE_ABC_123")
    assert auth_resp["action"] == "authenticate"
    assert len(auth_resp["signature_hex"]) == 128  # 64-byte Ed25519 signature in hex

    # Test SWIFT taker order intent parsing
    swift_msg = {
        "params": {
            "orderId": "SWIFT-TAKER-999",
            "market": "SOL-PERP",
            "direction": "sell",
            "auctionStartPrice": 75_000_000,  # 75.0
            "auctionEndPrice": 60_000_000,    # 60.0
            "auctionDuration": 10,            # 10 slots * 400ms = 4000ms
            "auctionStartTime": 1000,
            "baseAssetAmount": 10_000_000_000 # 10 SOL
        }
    }
    parsed = venue.parse_swift_order_intent(swift_msg, current_time_ms=3000)
    assert parsed["order_id"] == "SWIFT-TAKER-999"
    assert parsed["current_auction_price"] == 67.5  # Mid-point of auction
    assert parsed["size"] == 10.0

    # Test maker order submission capturing 0.25 bps rebate
    venue.update_reference_oracle("SOL-PERP", 67.5)  # Oracle matches price (non-toxic)
    res = await venue.submit_order({
        "taker_order_id": "SWIFT-TAKER-999",
        "symbol": "SOL-PERP",
        "side": "BUY",
        "price": 67.5,
        "size": 10.0,
        "preceding_ixs": ["compute_budget_ix_1"],
    })
    assert res.status == "FILLED"
    assert res.is_maker is True
    assert res.rebate_bps == 0.25
    assert res.fee_bps == -0.25  # Negative fee = rebate earned

    # Test deduplication: submitting duplicate order must be rejected
    res_dup = await venue.submit_order({
        "taker_order_id": "SWIFT-TAKER-999",
        "symbol": "SOL-PERP",
        "side": "BUY",
        "price": 67.5,
        "size": 10.0,
    })
    assert res_dup.status == "REJECTED"

    # Test toxic flow gating: order deviating significantly from oracle must be rejected
    venue.update_reference_oracle("SOL-PERP", 75.0)  # Oracle is 75.0, auction is 60.0 (2000 bps)
    res_toxic = await venue.submit_order({
        "taker_order_id": "SWIFT-TAKER-1000",
        "symbol": "SOL-PERP",
        "side": "BUY",
        "price": 60.0,
        "size": 5.0,
    })
    assert res_toxic.status == "REJECTED"

    await venue.disconnect()


# ==============================================================================
# 4. SUI DEEPBOOKV3 (H86) TESTS
# ==============================================================================

def test_sui_ptb_builder_8_steps_and_hot_potato():
    """Validates Sui Move PTB builder with 8 atomic steps, Cetus AMM swap, and Hot Potato."""
    builder = SuiDeepBookPTBBuilder()
    params = HotPotatoPTBParams(
        pool_id=SUI_USDC_POOL_ID,
        quote_coin_type=CIRCLE_USDC_TYPE,
        flash_borrow_amount=500_000_000,  # 500 USDC
        amm_target="cetus",
    )
    ptb = builder.build_atomic_arb_ptb(params)

    assert ptb["is_atomic"] is True
    assert ptb["hot_potato_guarantee"] is True
    commands = ptb["commands"]
    assert len(commands) == 8

    # Verify Command 0: Flash Loan borrow (0% fee)
    cmd0 = commands[0]
    assert cmd0["function"] == "borrow_flashloan_quote"
    assert "flash_loan_receipt" in cmd0["outputs"]

    # Verify Command 1: AMM swap leg (Cetus CLMM) - Post-Mortem 5.3 fix
    cmd1 = commands[1]
    assert cmd1["module"] == "pool"
    assert cmd1["function"] == "swap"

    # Verify Command 6: Return Flash Loan satisfying Hot Potato
    cmd6 = commands[6]
    assert cmd6["function"] == "return_flashloan_quote"

    # Verify Command 7: Transfer net profit to sender
    cmd7 = commands[7]
    assert cmd7["type"] == "TransferObjects"


@pytest.mark.asyncio
async def test_sui_deepbook_zero_leg_risk_dry_run_simulation():
    """Validates that unprofitable spread cleanly aborts inside Sui Move VM without leg risk."""
    venue = SuiDeepBookVenue(env="mainnet")
    await venue.connect()

    ptb = venue.build_arbitrage_ptb()

    # Case A: Profitable Spread (DeepBook Bid $2.05 > Cetus Swap In $2.00)
    sim_profit = venue.simulate_dry_run(
        ptb=ptb,
        deepbook_bid_px=2.05,
        amm_swap_out_px=2.00,
        borrow_amount=100_000_000,
    )
    assert sim_profit["status"] == "SUCCESS"
    assert sim_profit["hot_potato_satisfied"] is True
    assert sim_profit["zero_leg_risk_preserved"] is True
    assert sim_profit["net_profit_quote"] > 0
    assert sim_profit["gas_cost_sui"] == 0.002

    # Case B: Unprofitable Spread (DeepBook Bid $1.95 <= Cetus Swap In $2.00)
    sim_loss = venue.simulate_dry_run(
        ptb=ptb,
        deepbook_bid_px=1.95,
        amm_swap_out_px=2.00,
        borrow_amount=100_000_000,
    )
    # Must ABORT cleanly: SplitCoins fails, Hot Potato is never repaid -> VM reverts 100%
    assert sim_loss["status"] == "ABORTED"
    assert sim_loss["hot_potato_aborted"] is True
    assert sim_loss["zero_leg_risk_preserved"] is True
    assert sim_loss["state_mutations"] == 0
    assert sim_loss["gas_cost_sui"] == 0.002  # Only execution gas burned

    # Test order execution reflecting VM abort
    res_abort = await venue.submit_order({
        "symbol": "SUI/USDC",
        "price": 1.95,
        "amm_price": 2.00,
        "size": 100.0,
        "is_arb_ptb": True,
    })
    assert res_abort.status == "REJECTED"

    await venue.disconnect()


# ==============================================================================
# 5. KALSHI FIX PROTOCOL (H87) TESTS
# ==============================================================================

def test_kalshi_fix_logon_tag96_and_strict_tag50_omission():
    """Validates Ed25519 Tag 96 authentication and strict CFTC Tag 50 omission on Logon."""
    priv = ed25519.Ed25519PrivateKey.generate()
    api_key_id = "test-api-key-uuid-1234"

    logon_msg = create_kalshi_logon(
        api_key_id=api_key_id,
        private_key=priv,
        target_comp_id="KalshiNR",
    )

    assert logon_msg.msg_type == "A"
    assert logon_msg.sender_comp_id == api_key_id
    assert logon_msg.target_comp_id == "KalshiNR"
    assert TAG_RAW_DATA in logon_msg.fields
    assert len(logon_msg.fields[TAG_RAW_DATA]) > 0

    # MANDATORY REGULATORY RULE: Tag 50 must NOT be present on Logon (35=A)
    assert TAG_SENDER_SUB_ID not in logon_msg.fields


@pytest.mark.asyncio
async def test_kalshi_fix_live_socket_order_lifecycle():
    """Validates end-to-end socket connectivity, binary contract limit orders, and cancellation."""
    # Spin up mock FIX server on a dynamic port
    mock_server = KalshiFixMockServer(host="127.0.0.1", port=0)
    await mock_server.start()
    actual_port = mock_server.server.sockets[0].getsockname()[1]

    venue = KalshiFixVenue(
        env="mock",
        host="127.0.0.1",
        port=actual_port,
        api_key_id="test-client-uuid",
        target_comp_id="KalshiNR",
        sender_sub_id="TRADER_DESK_1",
    )

    # 1. Connect and verify Logon
    connected = await venue.connect()
    assert connected is True
    assert venue.is_connected is True

    # 2. Submit binary contract order within [0.01, 0.99]
    res_order = await venue.submit_order({
        "symbol": "KXFEDDEC26-YES",
        "side": "BUY",
        "price": 0.45,
        "size": 10.0,
        "order_id": "CLORD-TEST-100",
    })
    assert res_order.status == "OPEN"
    assert res_order.price == 0.45
    assert res_order.size == 10.0

    # 3. Test price boundary validation: $1.20 must be rejected
    res_invalid = await venue.submit_order({
        "symbol": "KXFEDDEC26-YES",
        "side": "BUY",
        "price": 1.20,  # Invalid binary contract price (> 0.99)
        "size": 5.0,
    })
    assert res_invalid.status == "REJECTED"

    # 4. Cancel resting order
    canceled = await venue.cancel_order("CLORD-TEST-100", "KXFEDDEC26-YES")
    assert canceled is True

    # 5. Clean disconnect
    await venue.disconnect()
    await mock_server.stop()


# ==============================================================================
# 6. DYDX V4 CONNECTOR TESTS
# ==============================================================================

@pytest.mark.asyncio
async def test_dydx_v4_l2_l3_maintenance_and_zero_gas_orders():
    """Validates dYdX v4 L2/L3 orderbook maintenance and zero-gas short-term order placement."""
    venue = DydxV4Venue(env="testnet", fee_tier=6)
    await venue.connect()

    # Handle L2 snapshot
    msg_l2 = {
        "contents": {
            "id": "BTC-USD",
            "bids": [{"price": "65000.0", "size": "1.5"}],
            "asks": [{"price": "65010.0", "size": "2.0"}],
        }
    }
    update = venue.handle_l2_orderbook_message(msg_l2)
    assert update.symbol == "BTC-USD"
    assert update.bid_px == 65000.0
    assert update.ask_px == 65010.0

    # Maintain L3 orderbook
    venue.update_l3_order("BTC-USD", "L3-ORD-1", "BUY", 65000.0, 1.5, is_active=True)
    venue.update_l3_order("BTC-USD", "L3-ORD-2", "SELL", 65010.0, 2.0, is_active=True)
    depth = venue.get_l3_depth("BTC-USD")
    assert depth["total_orders"] == 2
    assert depth["bid_orders_count"] == 1
    assert depth["ask_orders_count"] == 1

    # Place zero-gas short-term order
    res_sto = await venue.submit_order({
        "symbol": "BTC-USD",
        "side": "BUY",
        "price": 64990.0,
        "size": 0.5,
        "post_only": True,
    })
    assert res_sto.status == "OPEN"
    assert res_sto.is_maker is True
    # In Tier 6, maker earns 0.7 bps rebate
    assert res_sto.fee_bps == DYDX_FEE_TIERS[6]["maker_bps"]
    assert res_sto.rebate_bps == 0.7

    # Cancel zero-gas order
    cancelled = await venue.cancel_order(res_sto.order_id, "BTC-USD")
    assert cancelled is True

    await venue.disconnect()


# ==============================================================================
# 7. GMX V2 & CEXS CONNECTOR TESTS
# ==============================================================================

@pytest.mark.asyncio
async def test_gmx_cex_feeds_lead_lag_and_acceptable_price_barrier():
    """Validates MEXC/Gate.io feed parsing, lead-lag detection, dynamic fee, and slippage barrier."""
    venue = GmxCexVenue(env="mainnet", gmx_pool_depth_usd=10_000_000.0, base_fee_bps=5.0)
    await venue.connect()

    # Dynamic price impact fee formula test
    fee_small = compute_gmx_price_impact_fee(order_size_usd=100_000.0, pool_depth_usd=10_000_000.0)
    assert fee_small == 5.0 + 50.0 * (100_000 / 10_000_000)  # 5.5 bps

    # Parse MEXC ticker
    mexc_msg = {
        "s": "ETHUSDT",
        "t": 1720000000000,
        "d": {"b": "3500.00", "B": "15.0", "a": "3500.50", "A": "12.0"}
    }
    mexc_update = venue.parse_mexc_ticker(mexc_msg)
    assert mexc_update.symbol == "ETHUSDT"
    assert mexc_update.bid_px == 3500.0

    # Parse Gate.io ticker
    gate_msg = {
        "result": {"s": "ETH_USDT", "b": "3500.20", "B": "10.0", "a": "3500.60", "A": "8.0", "t": 1720000000000}
    }
    gate_update = venue.parse_gateio_ticker(gate_msg)
    assert gate_update.symbol == "ETH_USDT"

    # Lead-lag detection: GMX at 3490.0, CEX at 3500.0 (leads by ~28 bps)
    venue.update_gmx_oracle_price("ETHUSDT", price=3490.0, ts_ns=1720000000000 * 1_000_000)
    lead_lag = venue.detect_lead_lag("ETHUSDT")
    assert lead_lag["has_signal"] is True
    assert lead_lag["direction"] == "LONG"
    assert lead_lag["divergence_bps"] > 20.0

    # Chainlink Data Streams 2-step acceptablePrice slippage barrier test:
    # BUY order with acceptable_price = 3495.0.
    # Current oracle is 3490.0 <= 3495.0 -> fills!
    res_filled = await venue.submit_order({
        "symbol": "ETHUSDT",
        "side": "BUY",
        "price": 3490.0,
        "acceptable_price": 3495.0,
        "size": 2.0,
        "is_synthetic_hedge": True,
    })
    assert res_filled.status == "FILLED"
    assert res_filled.price == 3490.0

    # BUY order with acceptable_price = 3485.0.
    # Current oracle is 3490.0 > 3485.0 (market jumped adverse) -> must CANCEL/ABORT!
    res_aborted = await venue.submit_order({
        "symbol": "ETHUSDT",
        "side": "BUY",
        "price": 3490.0,
        "acceptable_price": 3485.0,
        "size": 2.0,
    })
    assert res_aborted.status == "CANCELLED"

    await venue.disconnect()
