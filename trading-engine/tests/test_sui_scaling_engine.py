"""Comprehensive Automated Unit Test Suite for Dynamic Capital Scaling Engine & Sui Balance Tracker.

Milestone M2 Verification Suite covering:
1. Initial tier parameterization (1,000 USDC = 1_000_000_000 micro-units).
2. Tier 1 -> Tier 2 state promotion (>= $100 profit + >= 10 successful trades).
3. Tier 2 -> Tier 3 state promotion (>= $750 cumulative profit + >= 20 successful trades).
4. Non-transition boundary conditions (profit met but trade count insufficient, and vice versa).
5. 3-abort tier downgrade and 60-second cooldown (COOLING_DOWN).
6. 5-abort emergency lock circuit breaker (EMERGENCY_LOCKED).
7. Gas safety floor handling (1.5 SUI warning flag, 0.5 SUI critical hard stop).
8. SUI-quote equivalent conversion for DEEP/SUI and CETUS/SUI across spot prices.
9. SuiBalanceTracker GraphQL balance parsing, decimal conversions, and gas floor integration.
10. Automatic recovery on cooldown expiration and wallet reconciliation.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Ensure trading-engine directory is on sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from venues.sui_scaling_engine import (
    DEFAULT_CRITICAL_GAS_FLOOR,
    DEFAULT_WARNING_GAS_FLOOR,
    OPERATOR_WALLET_ADDRESS,
    STATUS_ACTIVE,
    STATUS_COOLING_DOWN,
    STATUS_EMERGENCY_LOCKED,
    DynamicCapitalScalingEngine,
    ScalingState,
    ScalingTier,
    SuiBalanceTracker,
    WalletBalanceSnapshot,
)


# ==============================================================================
# 1. INITIAL TIER & PARAMETERIZATION TESTS
# ==============================================================================

def test_initial_tier_and_parameters():
    """Validates that initial flash_borrow_amount is 1,000 USDC (1_000_000_000) and status is ACTIVE."""
    engine = DynamicCapitalScalingEngine()

    assert engine.current_tier == ScalingTier.TIER_1
    assert engine.current_tier.value == 1_000_000_000
    assert engine.current_tier.usd_value == 1000.0
    assert engine.flash_borrow_amount == 1_000_000_000
    assert engine.status == STATUS_ACTIVE
    assert engine.can_trade() is True

    # State dataclass fields
    assert engine.state.accumulated_net_profit_usdc == 0.0
    assert engine.state.successful_trades == 0
    assert engine.state.consecutive_aborts == 0
    assert engine.state.gas_warning is False
    assert engine.state.cooldown_until == 0.0


def test_scaling_tier_enum_properties():
    """Validates ScalingTier values and nominal USD conversions."""
    assert ScalingTier.TIER_1 == 1_000_000_000
    assert ScalingTier.TIER_2 == 5_000_000_000
    assert ScalingTier.TIER_3 == 10_000_000_000

    assert ScalingTier.TIER_1.usd_value == 1000.0
    assert ScalingTier.TIER_2.usd_value == 5000.0
    assert ScalingTier.TIER_3.usd_value == 10000.0


# ==============================================================================
# 2. TIER 1 -> TIER 2 TRANSITION TESTS
# ==============================================================================

def test_tier_1_to_tier_2_transition_on_100_profit_and_10_trades():
    """Validates promotion from Tier 1 to Tier 2 when reaching >= $100 net profit and >= 10 trades."""
    engine = DynamicCapitalScalingEngine()
    assert engine.current_tier == ScalingTier.TIER_1

    # Record 9 trades of $11 each ($99 profit) -> Should NOT promote yet
    for i in range(9):
        engine.record_trade_success(profit_usdc=11.0)
        assert engine.current_tier == ScalingTier.TIER_1
        assert engine.flash_borrow_amount == 1_000_000_000

    assert engine.state.successful_trades == 9
    assert engine.state.accumulated_net_profit_usdc == 99.0
    assert engine.current_tier == ScalingTier.TIER_1

    # Record 10th trade of $1.00 ($100.00 total) -> Should promote to Tier 2
    engine.record_trade_success(profit_usdc=1.0)

    assert engine.state.successful_trades == 10
    assert engine.state.accumulated_net_profit_usdc == 100.0
    assert engine.current_tier == ScalingTier.TIER_2
    assert engine.flash_borrow_amount == 5_000_000_000
    assert engine.status == STATUS_ACTIVE


# ==============================================================================
# 3. TIER 2 -> TIER 3 TRANSITION TESTS
# ==============================================================================

def test_tier_2_to_tier_3_transition_on_750_cumulative_profit_and_20_trades():
    """Validates promotion from Tier 2 to Tier 3 when reaching >= $750 cumulative profit and >= 20 trades."""
    engine = DynamicCapitalScalingEngine()

    # Reach Tier 2 first ($100 profit and 10 trades)
    for _ in range(10):
        engine.record_trade_success(profit_usdc=10.0)
    assert engine.current_tier == ScalingTier.TIER_2

    # Add 9 more trades of $70 each ($630 additional profit, total $730, 19 trades)
    for _ in range(9):
        engine.record_trade_success(profit_usdc=70.0)
        assert engine.current_tier == ScalingTier.TIER_2

    assert engine.state.successful_trades == 19
    assert engine.state.accumulated_net_profit_usdc == 730.0
    assert engine.current_tier == ScalingTier.TIER_2

    # 20th trade of $20 ($750 total profit, 20 trades) -> Promotes to Tier 3
    engine.record_trade_success(profit_usdc=20.0)

    assert engine.state.successful_trades == 20
    assert engine.state.accumulated_net_profit_usdc == 750.0
    assert engine.current_tier == ScalingTier.TIER_3
    assert engine.flash_borrow_amount == 10_000_000_000
    assert engine.status == STATUS_ACTIVE


def test_direct_tier_1_to_tier_3_promotion():
    """Validates direct promotion to Tier 3 if both profit >= 750 and trades >= 20 are satisfied."""
    engine = DynamicCapitalScalingEngine()

    # Execute 20 trades of $40 each ($800 profit, 20 trades)
    for _ in range(20):
        engine.record_trade_success(profit_usdc=40.0)

    assert engine.state.successful_trades == 20
    assert engine.state.accumulated_net_profit_usdc == 800.0
    assert engine.current_tier == ScalingTier.TIER_3
    assert engine.flash_borrow_amount == 10_000_000_000


# ==============================================================================
# 4. NON-TRANSITION BOUNDARY TESTS
# ==============================================================================

def test_non_transition_when_profit_met_but_trades_insufficient():
    """Validates that reaching profit threshold without enough trades does NOT promote."""
    engine = DynamicCapitalScalingEngine()

    # Subcase A: $150 profit in just 5 trades (needs 10 trades)
    for _ in range(5):
        engine.record_trade_success(profit_usdc=30.0)

    assert engine.state.accumulated_net_profit_usdc == 150.0
    assert engine.state.successful_trades == 5
    assert engine.current_tier == ScalingTier.TIER_1  # Insufficient trades
    assert engine.flash_borrow_amount == 1_000_000_000


def test_non_transition_when_trades_met_but_profit_insufficient():
    """Validates that reaching trade count without enough profit does NOT promote."""
    engine = DynamicCapitalScalingEngine()

    # Subcase B: 15 trades of $3 each ($45 profit, needs $100)
    for _ in range(15):
        engine.record_trade_success(profit_usdc=3.0)

    assert engine.state.successful_trades == 15
    assert engine.state.accumulated_net_profit_usdc == 45.0
    assert engine.current_tier == ScalingTier.TIER_1  # Insufficient profit
    assert engine.flash_borrow_amount == 1_000_000_000


def test_tier_2_non_transition_boundary_cases():
    """Validates Tier 2 boundary cases where only one of (profit, trades) is satisfied."""
    # Setup Tier 2
    engine = DynamicCapitalScalingEngine(initial_tier=ScalingTier.TIER_2)
    engine.state.accumulated_net_profit_usdc = 100.0
    engine.state.successful_trades = 10

    # Subcase C: $800 profit but only 18 trades
    engine.record_trade_success(profit_usdc=700.0)  # total $800 profit, 11 trades
    for _ in range(7):
        engine.record_trade_success(profit_usdc=0.0)  # 18 trades total

    assert engine.state.successful_trades == 18
    assert engine.state.accumulated_net_profit_usdc == 800.0
    assert engine.current_tier == ScalingTier.TIER_2  # Needs 20 trades

    # Subcase D: 25 trades but only $600 profit
    engine2 = DynamicCapitalScalingEngine(initial_tier=ScalingTier.TIER_2)
    engine2.state.accumulated_net_profit_usdc = 100.0
    engine2.state.successful_trades = 10

    for _ in range(15):
        engine2.record_trade_success(profit_usdc=33.33)  # ~$600 total, 25 trades

    assert engine2.state.successful_trades == 25
    assert engine2.state.accumulated_net_profit_usdc < 750.0
    assert engine2.current_tier == ScalingTier.TIER_2  # Needs $750


# ==============================================================================
# 5. DRAWDOWN & CIRCUIT BREAKER TESTS (3-ABORT & 5-ABORT)
# ==============================================================================

def test_three_abort_downgrade_and_cooldown_from_tier_2():
    """Validates 3 consecutive aborts demote Tier 2 -> Tier 1 and trigger 60-second cooldown."""
    engine = DynamicCapitalScalingEngine(initial_tier=ScalingTier.TIER_2)
    assert engine.current_tier == ScalingTier.TIER_2

    # 1st abort
    engine.record_trade_abort()
    assert engine.state.consecutive_aborts == 1
    assert engine.state.status == STATUS_ACTIVE
    assert engine.current_tier == ScalingTier.TIER_2
    assert engine.can_trade() is True

    # 2nd abort
    engine.record_trade_abort()
    assert engine.state.consecutive_aborts == 2
    assert engine.state.status == STATUS_ACTIVE
    assert engine.current_tier == ScalingTier.TIER_2
    assert engine.can_trade() is True

    # 3rd abort -> Demotes to Tier 1, enters COOLING_DOWN
    start_time = time.time()
    engine.record_trade_abort()
    assert engine.state.consecutive_aborts == 3
    assert engine.current_tier == ScalingTier.TIER_1
    assert engine.flash_borrow_amount == 1_000_000_000
    assert engine.state.status == STATUS_COOLING_DOWN
    assert engine.state.cooldown_until >= start_time + 59.0
    assert engine.can_trade() is False


def test_three_abort_downgrade_from_tier_3():
    """Validates 3 consecutive aborts demote Tier 3 -> Tier 2."""
    engine = DynamicCapitalScalingEngine(initial_tier=ScalingTier.TIER_3)
    assert engine.current_tier == ScalingTier.TIER_3

    engine.record_trade_abort()
    engine.record_trade_abort()
    engine.record_trade_abort()

    assert engine.current_tier == ScalingTier.TIER_2
    assert engine.flash_borrow_amount == 5_000_000_000
    assert engine.state.status == STATUS_COOLING_DOWN


def test_three_abort_at_tier_1_stays_at_tier_1_with_cooldown():
    """Validates 3 consecutive aborts at Tier 1 remains at Tier 1 and enters cooldown."""
    engine = DynamicCapitalScalingEngine(initial_tier=ScalingTier.TIER_1)

    engine.record_trade_abort()
    engine.record_trade_abort()
    engine.record_trade_abort()

    assert engine.current_tier == ScalingTier.TIER_1
    assert engine.state.status == STATUS_COOLING_DOWN
    assert engine.can_trade() is False


def test_five_abort_emergency_lock():
    """Validates 5 consecutive aborts trigger EMERGENCY_LOCKED status."""
    engine = DynamicCapitalScalingEngine(initial_tier=ScalingTier.TIER_2)

    for _ in range(4):
        engine.record_trade_abort()

    assert engine.state.consecutive_aborts == 4
    assert engine.state.status == STATUS_COOLING_DOWN

    # 5th abort -> EMERGENCY_LOCKED
    engine.record_trade_abort()
    assert engine.state.consecutive_aborts == 5
    assert engine.state.status == STATUS_EMERGENCY_LOCKED
    assert engine.can_trade() is False

    # Emergency locked persists even after cooldown expires
    with patch("time.time", return_value=time.time() + 3600):
        assert engine.status == STATUS_EMERGENCY_LOCKED
        assert engine.can_trade() is False


def test_trade_success_resets_abort_count_and_clears_cooldown():
    """Validates that a successful trade resets consecutive aborts to 0 and clears cooldown."""
    engine = DynamicCapitalScalingEngine()

    engine.record_trade_abort()
    engine.record_trade_abort()
    assert engine.state.consecutive_aborts == 2

    engine.record_trade_success(profit_usdc=5.0)
    assert engine.state.consecutive_aborts == 0
    assert engine.state.status == STATUS_ACTIVE


def test_cooldown_auto_recovery_after_expiry():
    """Validates that status automatically transitions from COOLING_DOWN to ACTIVE after 60 seconds."""
    engine = DynamicCapitalScalingEngine()
    engine.state.sui_gas_balance = 3.0  # healthy gas

    engine.record_trade_abort()
    engine.record_trade_abort()
    engine.record_trade_abort()
    assert engine.state.status == STATUS_COOLING_DOWN
    assert engine.can_trade() is False

    # Mock time advancement by 61 seconds
    future_time = time.time() + 61.0
    with patch("time.time", return_value=future_time):
        assert engine.status == STATUS_ACTIVE
        assert engine.can_trade() is True


def test_emergency_unlock():
    """Validates manual operator reset of emergency lock."""
    engine = DynamicCapitalScalingEngine()
    engine.state.sui_gas_balance = 2.0  # Above critical floor

    for _ in range(5):
        engine.record_trade_abort()
    assert engine.state.status == STATUS_EMERGENCY_LOCKED

    success = engine.unlock_emergency()
    assert success is True
    assert engine.state.status == STATUS_ACTIVE
    assert engine.state.consecutive_aborts == 0
    assert engine.can_trade() is True


# ==============================================================================
# 6. GAS SAFETY FLOORS (1.5 SUI WARNING & 0.5 SUI CRITICAL STOP)
# ==============================================================================

def test_gas_safety_warning_at_1_5_sui():
    """Validates warning floor at 1.5 SUI triggers gas_warning flag without emergency lock."""
    engine = DynamicCapitalScalingEngine()

    # Normal gas
    engine.update_from_wallet_balances(usdc_balance=0.0, sui_balance=3.0)
    assert engine.state.gas_warning is False
    assert engine.state.status == STATUS_ACTIVE
    assert engine.can_trade() is True

    # Gas drops to 1.45 SUI (< 1.5 SUI warning floor)
    engine.update_from_wallet_balances(usdc_balance=0.0, sui_balance=1.45)
    assert engine.state.gas_warning is True
    assert engine.state.status == STATUS_ACTIVE  # Throttled, but still active
    assert engine.can_trade() is True

    # Gas restored to 2.5 SUI
    engine.update_from_wallet_balances(usdc_balance=0.0, sui_balance=2.5)
    assert engine.state.gas_warning is False
    assert engine.state.status == STATUS_ACTIVE


def test_gas_safety_critical_hard_stop_at_0_5_sui():
    """Validates critical hard stop at 0.5 SUI triggers EMERGENCY_LOCKED and halts trading."""
    engine = DynamicCapitalScalingEngine()

    engine.update_from_wallet_balances(usdc_balance=0.0, sui_balance=2.0)
    assert engine.can_trade() is True

    # Gas drops to 0.49 SUI (< 0.5 SUI critical floor)
    engine.update_from_wallet_balances(usdc_balance=0.0, sui_balance=0.49)
    assert engine.state.status == STATUS_EMERGENCY_LOCKED
    assert engine.state.gas_warning is True
    assert engine.can_trade() is False

    # Gas replenished above 0.5 SUI -> Recovers to ACTIVE
    engine.update_from_wallet_balances(usdc_balance=0.0, sui_balance=3.5)
    assert engine.state.status == STATUS_ACTIVE
    assert engine.state.gas_warning is False
    assert engine.can_trade() is True


def test_gas_critical_does_not_unlock_if_5_aborts_present():
    """Validates gas replenishment does not bypass 5-abort emergency lock."""
    engine = DynamicCapitalScalingEngine()

    for _ in range(5):
        engine.record_trade_abort()
    assert engine.state.status == STATUS_EMERGENCY_LOCKED

    # Refuel gas
    engine.update_from_wallet_balances(usdc_balance=0.0, sui_balance=5.0)
    assert engine.state.status == STATUS_EMERGENCY_LOCKED  # Still locked due to aborts


# ==============================================================================
# 7. SUI-QUOTE EQUIVALENT CONVERSION TESTS (DEEP/SUI & CETUS/SUI)
# ==============================================================================

def test_sui_quote_conversion_deep_sui_and_cetus_sui():
    """Validates dynamic SUI quote resolution for DEEP/SUI and CETUS/SUI based on SUI spot price."""
    engine = DynamicCapitalScalingEngine()  # Tier 1 = $1,000 USD

    # 1. Spot price = $2.00 / SUI
    # $1,000 / 2.0 = 500 SUI = 500_000_000_000 MIST
    assert engine.get_current_borrow_amount("DEEP/SUI", sui_spot_price=2.0) == 500_000_000_000
    assert engine.get_current_borrow_amount("CETUS/SUI", sui_spot_price=2.0) == 500_000_000_000

    # 2. Spot price = $2.50 / SUI
    # $1,000 / 2.5 = 400 SUI = 400_000_000_000 MIST
    assert engine.get_current_borrow_amount("DEEP/SUI", sui_spot_price=2.5) == 400_000_000_000
    assert engine.get_current_borrow_amount("CETUS/SUI", sui_spot_price=2.5) == 400_000_000_000

    # 3. Default spot price (2.0) if None is provided
    assert engine.get_current_borrow_amount("DEEP/SUI") == 500_000_000_000
    assert engine.get_current_borrow_amount("CETUS/SUI") == 500_000_000_000

    # 4. Promote to Tier 2 ($5,000 USD)
    engine.state.current_tier = ScalingTier.TIER_2
    # $5,000 / 2.0 = 2,500 SUI = 2_500_000_000_000 MIST
    assert engine.get_current_borrow_amount("DEEP/SUI", sui_spot_price=2.0) == 2_500_000_000_000
    assert engine.get_current_borrow_amount("CETUS/SUI", sui_spot_price=2.0) == 2_500_000_000_000

    # 5. Promote to Tier 3 ($10,000 USD)
    engine.state.current_tier = ScalingTier.TIER_3
    # $10,000 / 2.0 = 5,000 SUI = 5_000_000_000_000 MIST
    assert engine.get_current_borrow_amount("DEEP/SUI", sui_spot_price=2.0) == 5_000_000_000_000
    assert engine.get_current_borrow_amount("CETUS/SUI", sui_spot_price=2.0) == 5_000_000_000_000


def test_usdc_quote_pairs_return_tier_value_directly():
    """Validates that SUI/USDC and DEEP/USDC return tier value directly regardless of spot price."""
    engine = DynamicCapitalScalingEngine()

    for tier, expected_units in [
        (ScalingTier.TIER_1, 1_000_000_000),
        (ScalingTier.TIER_2, 5_000_000_000),
        (ScalingTier.TIER_3, 10_000_000_000),
    ]:
        engine.state.current_tier = tier
        assert engine.get_current_borrow_amount("SUI/USDC", sui_spot_price=2.0) == expected_units
        assert engine.get_current_borrow_amount("DEEP/USDC", sui_spot_price=2.0) == expected_units
        assert engine.get_current_borrow_amount("sui_usdc", sui_spot_price=3.5) == expected_units


def test_invalid_sui_spot_price_raises_error():
    """Validates that non-positive spot price raises ValueError."""
    engine = DynamicCapitalScalingEngine()
    with pytest.raises(ValueError):
        engine.get_current_borrow_amount("DEEP/SUI", sui_spot_price=-1.0)
    with pytest.raises(ValueError):
        engine.get_current_borrow_amount("DEEP/SUI", sui_spot_price=0.0)


# ==============================================================================
# 8. WALLET RECONCILIATION & AUTOMATED PROMOTION
# ==============================================================================

def test_wallet_balance_reconciliation_triggers_promotions():
    """Validates that periodic balance updates track net profit and promote tiers."""
    engine = DynamicCapitalScalingEngine()

    # Step 1: Initial baseline establish (0 USDC, 5.419 SUI)
    engine.update_from_wallet_balances(usdc_balance=0.0, sui_balance=5.419245048)
    assert engine.baseline_usdc_balance == 0.0
    assert engine.current_tier == ScalingTier.TIER_1

    # Step 2: Simulate 10 successful executions recorded
    engine.state.successful_trades = 10

    # Step 3: Wallet balance sweep detects $120.00 USDC in wallet
    engine.update_from_wallet_balances(usdc_balance=120.0, sui_balance=5.38)
    assert engine.state.accumulated_net_profit_usdc == 120.0
    assert engine.current_tier == ScalingTier.TIER_2
    assert engine.flash_borrow_amount == 5_000_000_000

    # Step 4: Add 10 more trades (total 20) and sweep detects $800.00 USDC
    engine.state.successful_trades = 20
    engine.update_from_wallet_balances(usdc_balance=800.0, sui_balance=5.32)
    assert engine.state.accumulated_net_profit_usdc == 800.0
    assert engine.current_tier == ScalingTier.TIER_3
    assert engine.flash_borrow_amount == 10_000_000_000


# ==============================================================================
# 9. SUI BALANCE TRACKER INTEGRATION TESTS
# ==============================================================================

@pytest.mark.asyncio
async def test_sui_balance_tracker_parsing_and_gas_floors():
    """Validates SuiBalanceTracker parses GraphQL response and checks safety floors."""
    mock_client = MagicMock()
    # Mocking live Mainnet response: 5.419245048 SUI and 0 USDC
    mock_client.get_wallet_balances = AsyncMock(return_value={
        "sui_mist": 5419245048,
        "sui": 5.419245048,
        "usdc_raw": 0,
        "usdc": 0.0,
    })

    tracker = SuiBalanceTracker(
        client=mock_client,
        wallet_address=OPERATOR_WALLET_ADDRESS,
    )

    snapshot = await tracker.fetch_balances()

    assert snapshot.sui_mist == 5419245048
    assert snapshot.sui_balance == 5.419245048
    assert snapshot.sui_float == 5.419245048
    assert snapshot.usdc_raw == 0
    assert snapshot.usdc_balance == 0.0
    assert snapshot.usdc_float == 0.0
    assert snapshot.is_gas_warning is False
    assert snapshot.is_gas_critical is False
    assert snapshot.status == "HEALTHY"

    # Test gas validation helper
    can_trade, alert = tracker.validate_gas_safety(5.419)
    assert can_trade is True and alert == "HEALTHY"

    can_trade, alert = tracker.validate_gas_safety(1.2)
    assert can_trade is True and alert == "WARNING"

    can_trade, alert = tracker.validate_gas_safety(0.4)
    assert can_trade is False and alert == "CRITICAL"


@pytest.mark.asyncio
async def test_sui_balance_tracker_updates_scaling_engine():
    """Validates that SuiBalanceTracker synchronizes state into DynamicCapitalScalingEngine."""
    mock_client = MagicMock()
    mock_client.get_wallet_balances = AsyncMock(return_value={
        "sui_mist": 1400000000,  # 1.4 SUI (warning floor)
        "sui": 1.4,
        "usdc_raw": 150000000,   # 150 USDC
        "usdc": 150.0,
    })

    engine = DynamicCapitalScalingEngine(initial_baseline_usdc=0.0)
    engine.state.successful_trades = 10

    tracker = SuiBalanceTracker(client=mock_client)
    snapshot = await tracker.update_scaling_engine(engine)

    assert snapshot.sui_balance == 1.4
    assert snapshot.is_gas_warning is True
    assert engine.state.gas_warning is True
    assert engine.state.sui_gas_balance == 1.4
    assert engine.state.accumulated_net_profit_usdc == 150.0
    # Promoted to Tier 2 because $150 >= $100 and 10 trades >= 10
    assert engine.current_tier == ScalingTier.TIER_2


def test_depth_aware_borrow_sizing():
    """Validates that borrow amounts are dynamically capped by top-of-book depth."""
    engine = DynamicCapitalScalingEngine()

    # Tier 1 defaults to 1,000 USDC
    assert engine.get_current_borrow_amount("DEEP/USDC") == 1_000_000_000

    # When orderbook depth is $500, borrow is capped to 85% of depth ($425 USDC)
    capped_amount = engine.get_current_borrow_amount("DEEP/USDC", max_depth_quote=500.0)
    assert capped_amount == 425_000_000  # $425 USDC

    # When orderbook depth is large ($2,500), borrow remains at Tier 1 ceiling ($1,000 USDC)
    large_depth_amount = engine.get_current_borrow_amount("SUI/USDC", max_depth_quote=2500.0)
    assert large_depth_amount == 1_000_000_000

    # When depth is shallow, minimum $25 floor applies
    shallow_depth = engine.get_current_borrow_amount("DEEP/USDC", max_depth_quote=20.0)
    assert shallow_depth == 25_000_000  # $25 USDC

    # For SUI quote pairs:
    # 50 SUI depth -> 85% is 42.5 SUI (42_500_000_000 MIST)
    sui_quote_amount = engine.get_current_borrow_amount("DEEP/SUI", sui_spot_price=1.0, max_depth_quote=50.0)
    assert sui_quote_amount == 42_500_000_000


def test_depth_aggregation_and_usd_normalization():
    """Validates depth aggregation across multi-level bids and USD profit normalization."""
    import asyncio
    from unittest.mock import AsyncMock, patch
    from venues.sui_deepbook_venue import SuiGraphQLClient, SUI_GRAPHQL_MAINNET

    async def _run():
        client = SuiGraphQLClient(endpoint=SUI_GRAPHQL_MAINNET)
        mock_indexer = {
            "SUI_USDC": {},
            "DEEP_SUI": {},
            "DEEP_USDC": {
                "bids": [
                    ["0.01392", "720"],
                    ["0.01391", "35500"],
                ],
                "asks": [["0.01395", "1000"]],
            },
        }

        async def mock_fetch_orderbook(symbol):
            return mock_indexer.get(symbol, {})

        mock_data = {
            "cetus_bids": {},  # activates is_live_graphql
            "p_sui_usdc": {"asMoveObject": {"contents": {"json": {"current_sqrt_price": str(int(((0.83) ** 0.5) * (2**64)))}}}},
            "p_deep_sui": {"asMoveObject": {"contents": {"json": {"current_sqrt_price": str(int(((0.016) ** 0.5) * (2**64)))}}}},
            "p_cetus_sui": {"asMoveObject": {"contents": {"json": {"current_sqrt_price": str(int(((0.023) ** 0.5) * (2**64)))}}}},
            "p_deep_usdc": {
                "asMoveObject": {
                    "contents": {
                        "json": {
                            # 0.01380 in sqrt_price Q64 format
                            "current_sqrt_price": str(int(((0.01380) ** 0.5) * (2**64)))
                        }
                    }
                }
            },
        }

        with patch.object(client, "execute", new_callable=AsyncMock) as mock_exec, \
             patch.object(client, "_fetch_deepbook_indexer_orderbook", side_effect=mock_fetch_orderbook):
            mock_exec.return_value = {"data": mock_data}
            res = await client.query_live_market_spreads()

            assert "DEEP/USDC" in res
            deep_usdc = res["DEEP/USDC"]
            # Total quote depth should aggregate 720 * 0.01392 + 35500 * 0.01391 = 10.0224 + 493.805 = 503.8274
            assert deep_usdc["bid_depth_quote"] > 500.0
            assert deep_usdc["bid_size"] == 36220.0
            # VWAP should be ~0.0139102
            assert 0.01391 <= deep_usdc["deepbook_price"] <= 0.01392

        await client.close()

    asyncio.run(_run())


def test_optimized_tier3_per_pair_scaling():
    """Validates Tier 3 pair-differentiated borrow ceilings protecting thin pools while scaling SUI/USDC."""
    from venues.sui_scaling_engine import DEFAULT_PAIR_MAX_BORROW_USD

    engine = DynamicCapitalScalingEngine(
        initial_tier=ScalingTier.TIER_3,
        pair_max_borrow_usd=DEFAULT_PAIR_MAX_BORROW_USD,
    )
    assert engine.current_tier == ScalingTier.TIER_3

    # 1. SUI/USDC allows full Tier 3 ($10,000 USDC)
    sui_usdc_amt = engine.get_current_borrow_amount("SUI/USDC")
    assert sui_usdc_amt == 10_000_000_000  # $10k USDC

    # 2. DEEP/USDC is capped at $1,000 USD to protect Cetus $241k pool
    deep_usdc_amt = engine.get_current_borrow_amount("DEEP/USDC")
    assert deep_usdc_amt == 1_000_000_000  # $1k USDC (not $10k)

    # 3. DEEP/SUI is capped at $4,000 USD equivalent (at $2.00 / SUI => 2,000 SUI)
    deep_sui_amt = engine.get_current_borrow_amount("DEEP/SUI", sui_spot_price=2.0)
    assert deep_sui_amt == 2_000_000_000_000  # 2,000 SUI

    # 4. CETUS/SUI is capped at $2,500 USD equivalent (at $2.00 / SUI => 1,250 SUI)
    cetus_sui_amt = engine.get_current_borrow_amount("CETUS/SUI", sui_spot_price=2.0)
    assert cetus_sui_amt == 1_250_000_000_000  # 1,250 SUI


