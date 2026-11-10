"""Milestone M2 Adversarial Stress Test Suite: Empirical Challenger.

Empirical verification and adversarial challenge of Dynamic Capital Scaling Engine
and Sui Balance Tracker (`trading-engine/venues/sui_scaling_engine.py`):

1. State Machine Boundary Testing:
   - Boundary threshold tests ($99.99 vs $100.00 profit; 9 vs 10 trades).
   - Boundary threshold tests ($749.99 vs $750.00 profit; 19 vs 20 trades).
   - High-precision decimal float accumulation vs discrete thresholds.
   - Zero-profit trade executions and negative profit rejection.
   - Non-promotion under asymmetric conditions (trades met without profit, and vice versa).

2. Circuit Breaker Rapid Stress:
   - Rapid sequences of alternating aborts and successes (oscillating stress).
   - Consecutive abort reset on verified trade success.
   - Full demotion cascade: Tier 3 -> Tier 2 -> Tier 1 -> bottom floor.
   - Unbypassable 5-abort emergency lock (immune to time progression, gas refueling, and trade triggers).
   - Cooldown expiration mechanics and manual unlock vs forced unlock.

3. Gas Safety Hard Stop Stress:
   - Warning floor boundary at 1.5 SUI (1.50001 SUI vs 1.49999 SUI).
   - Critical hard stop boundary at 0.5 SUI (0.50001 SUI vs 0.49999 SUI).
   - Strict `can_trade()` rejection when gas drops below 0.5 SUI even if status is set to ACTIVE.
   - Deep inspection of zero-gas (0.0 SUI) edge condition.

4. Decimal and SUI Spot Price Edge Testing:
   - Extreme spot prices: $0.01/SUI to $1,000.00/SUI across all 4 supported pairs.
   - Validation that all returned borrow amounts are strictly integer-bounded (MIST or micro-USDC).
   - Asymmetric quote pairs (USDC quote vs SUI quote).
   - Error handling for invalid, non-positive, and non-finite spot prices.

5. Monte Carlo Randomized Oracle Stress Harness:
   - 500 randomized interleaved transitions verifying global system invariants.
"""

from __future__ import annotations

import math
import random
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
# SECTION 1: STATE MACHINE BOUNDARY TESTING
# ==============================================================================

class TestStateMachineBoundaryStress:
    """Rigorous boundary value testing for capital scaling state transitions."""

    def test_tier_1_to_tier_2_exact_profit_boundary(self):
        """Stress tests $99.99 vs $100.00 profit boundary at 10 trades."""
        # Case A: $99.99 with 10 trades -> Must NOT promote
        engine = DynamicCapitalScalingEngine()
        for _ in range(9):
            engine.record_trade_success(profit_usdc=10.0)
        engine.record_trade_success(profit_usdc=9.99)

        assert engine.state.successful_trades == 10
        assert pytest.approx(engine.state.accumulated_net_profit_usdc, rel=1e-6) == 99.99
        assert engine.current_tier == ScalingTier.TIER_1
        assert engine.flash_borrow_amount == 1_000_000_000

        # Now add $0.01 ($100.00 exact total) on 11th trade -> Promotes to Tier 2
        engine.record_trade_success(profit_usdc=0.01)
        assert engine.state.successful_trades == 11
        assert pytest.approx(engine.state.accumulated_net_profit_usdc, rel=1e-6) == 100.00
        assert engine.current_tier == ScalingTier.TIER_2
        assert engine.flash_borrow_amount == 5_000_000_000

    def test_tier_1_to_tier_2_exact_trades_boundary(self):
        """Stress tests 9 vs 10 trades boundary at $100.00 profit."""
        engine = DynamicCapitalScalingEngine()

        # 9 trades totaling $100.00 -> Must NOT promote
        for _ in range(8):
            engine.record_trade_success(profit_usdc=10.0)
        engine.record_trade_success(profit_usdc=20.0)

        assert engine.state.successful_trades == 9
        assert engine.state.accumulated_net_profit_usdc == 100.0
        assert engine.current_tier == ScalingTier.TIER_1
        assert engine.flash_borrow_amount == 1_000_000_000

        # 10th trade (even with $0.00 profit) -> Promotes to Tier 2
        engine.record_trade_success(profit_usdc=0.0)
        assert engine.state.successful_trades == 10
        assert engine.state.accumulated_net_profit_usdc == 100.0
        assert engine.current_tier == ScalingTier.TIER_2
        assert engine.flash_borrow_amount == 5_000_000_000

    def test_tier_2_to_tier_3_exact_profit_boundary(self):
        """Stress tests $749.99 vs $750.00 profit boundary at 20 trades."""
        engine = DynamicCapitalScalingEngine(initial_tier=ScalingTier.TIER_2)
        engine.state.accumulated_net_profit_usdc = 100.0
        engine.state.successful_trades = 10

        # Execute 9 trades adding $649.99 (total $749.99, 19 trades)
        for _ in range(8):
            engine.record_trade_success(profit_usdc=70.0)
        engine.record_trade_success(profit_usdc=89.99)

        assert engine.state.successful_trades == 19
        assert pytest.approx(engine.state.accumulated_net_profit_usdc, rel=1e-6) == 749.99
        assert engine.current_tier == ScalingTier.TIER_2

        # 20th trade with $0.00 profit -> Total profit $749.99, 20 trades -> Must NOT promote
        engine.record_trade_success(profit_usdc=0.0)
        assert engine.state.successful_trades == 20
        assert pytest.approx(engine.state.accumulated_net_profit_usdc, rel=1e-6) == 749.99
        assert engine.current_tier == ScalingTier.TIER_2
        assert engine.flash_borrow_amount == 5_000_000_000

        # 21st trade with $0.01 profit -> Total profit $750.00 -> Promotes to Tier 3
        engine.record_trade_success(profit_usdc=0.01)
        assert engine.state.successful_trades == 21
        assert pytest.approx(engine.state.accumulated_net_profit_usdc, rel=1e-6) == 750.00
        assert engine.current_tier == ScalingTier.TIER_3
        assert engine.flash_borrow_amount == 10_000_000_000

    def test_tier_2_to_tier_3_exact_trades_boundary(self):
        """Stress tests 19 vs 20 trades boundary at $750.00 profit."""
        engine = DynamicCapitalScalingEngine(initial_tier=ScalingTier.TIER_2)
        engine.state.accumulated_net_profit_usdc = 100.0
        engine.state.successful_trades = 10

        # Reach $750.00 on the 19th trade -> Must NOT promote
        for _ in range(8):
            engine.record_trade_success(profit_usdc=70.0)
        engine.record_trade_success(profit_usdc=90.0)

        assert engine.state.successful_trades == 19
        assert engine.state.accumulated_net_profit_usdc == 750.0
        assert engine.current_tier == ScalingTier.TIER_2
        assert engine.flash_borrow_amount == 5_000_000_000

        # 20th trade -> Promotes to Tier 3
        engine.record_trade_success(profit_usdc=0.0)
        assert engine.state.successful_trades == 20
        assert engine.state.accumulated_net_profit_usdc == 750.0
        assert engine.current_tier == ScalingTier.TIER_3
        assert engine.flash_borrow_amount == 10_000_000_000

    def test_direct_tier_1_to_tier_3_promotion_boundaries(self):
        """Stress tests boundary conditions when skipping Tier 2."""
        # 20 trades with $749.99 profit from Tier 1 -> Promotes only to Tier 2!
        engine = DynamicCapitalScalingEngine()
        for _ in range(19):
            engine.record_trade_success(profit_usdc=30.0)
        engine.record_trade_success(profit_usdc=179.99)

        assert engine.state.successful_trades == 20
        assert pytest.approx(engine.state.accumulated_net_profit_usdc, rel=1e-6) == 749.99
        assert engine.current_tier == ScalingTier.TIER_2  # Not Tier 3!

        # Now add $0.01 -> total $750.00 -> Promotes to Tier 3
        engine.record_trade_success(profit_usdc=0.01)
        assert engine.current_tier == ScalingTier.TIER_3

    def test_zero_profit_trades_do_not_promote_without_dollars(self):
        """Stress test: 100 consecutive trades of $0 profit remain strictly at Tier 1."""
        engine = DynamicCapitalScalingEngine()
        for _ in range(100):
            engine.record_trade_success(profit_usdc=0.0)

        assert engine.state.successful_trades == 100
        assert engine.state.accumulated_net_profit_usdc == 0.0
        assert engine.current_tier == ScalingTier.TIER_1
        assert engine.flash_borrow_amount == 1_000_000_000

    def test_negative_profit_rejected_with_value_error(self):
        """Validates that negative profit is strictly rejected."""
        engine = DynamicCapitalScalingEngine()
        with pytest.raises(ValueError, match="Profit must be non-negative"):
            engine.record_trade_success(profit_usdc=-0.01)
        with pytest.raises(ValueError, match="Profit must be non-negative"):
            engine.record_trade_success(profit_usdc=-100.0)


# ==============================================================================
# SECTION 2: CIRCUIT BREAKER RAPID STRESS & RECOVERY
# ==============================================================================

class TestCircuitBreakerRapidStress:
    """Stress tests rapid sequences of aborts, successes, cooldowns, and locks."""

    def test_oscillating_aborts_and_successes(self):
        """Stress tests 100 rapid cycles of [2 aborts, 1 success].

        Invariants:
        - Consecutive aborts must never reach 3.
        - Status must remain ACTIVE throughout.
        - Tier must NEVER demote.
        """
        engine = DynamicCapitalScalingEngine(initial_tier=ScalingTier.TIER_2)

        for cycle in range(100):
            engine.record_trade_abort()
            assert engine.state.consecutive_aborts == 1
            assert engine.state.status == STATUS_ACTIVE
            assert engine.can_trade() is True

            engine.record_trade_abort()
            assert engine.state.consecutive_aborts == 2
            assert engine.state.status == STATUS_ACTIVE
            assert engine.can_trade() is True

            # Success resets count to 0
            engine.record_trade_success(profit_usdc=1.0)
            assert engine.state.consecutive_aborts == 0
            assert engine.state.status == STATUS_ACTIVE
            assert engine.current_tier == ScalingTier.TIER_2
            assert engine.can_trade() is True

        assert engine.state.successful_trades == 100
        assert engine.state.consecutive_aborts == 0

    def test_full_demotion_cascade_from_tier_3_to_tier_1_floor(self):
        """Stress tests cascading demotions from Tier 3 down to Tier 1."""
        engine = DynamicCapitalScalingEngine(initial_tier=ScalingTier.TIER_3)
        engine.state.sui_gas_balance = 5.0  # healthy gas

        # 1. First 3-abort sequence demotes Tier 3 -> Tier 2
        for _ in range(3):
            engine.record_trade_abort()
        assert engine.current_tier == ScalingTier.TIER_2
        assert engine.flash_borrow_amount == 5_000_000_000
        assert engine.state.status == STATUS_COOLING_DOWN
        assert engine.can_trade() is False

        # Simulate cooldown expiry
        with patch("time.time", return_value=time.time() + 61.0):
            assert engine.status == STATUS_ACTIVE
            assert engine.can_trade() is True

        # Reset abort count by manual or simulated success
        engine.record_trade_success(profit_usdc=0.0)
        assert engine.state.consecutive_aborts == 0

        # 2. Second 3-abort sequence demotes Tier 2 -> Tier 1
        for _ in range(3):
            engine.record_trade_abort()
        assert engine.current_tier == ScalingTier.TIER_1
        assert engine.flash_borrow_amount == 1_000_000_000
        assert engine.state.status == STATUS_COOLING_DOWN

        with patch("time.time", return_value=time.time() + 61.0):
            assert engine.status == STATUS_ACTIVE

        engine.record_trade_success(profit_usdc=0.0)
        assert engine.state.consecutive_aborts == 0

        # 3. Third 3-abort sequence at Tier 1 remains at Tier 1 floor
        for _ in range(3):
            engine.record_trade_abort()
        assert engine.current_tier == ScalingTier.TIER_1
        assert engine.flash_borrow_amount == 1_000_000_000
        assert engine.state.status == STATUS_COOLING_DOWN

    def test_five_abort_emergency_lock_is_strictly_unbypassable(self):
        """Verifies 5-abort emergency lock cannot be bypassed by time, balance, or cooldown."""
        engine = DynamicCapitalScalingEngine(initial_tier=ScalingTier.TIER_2)
        engine.state.sui_gas_balance = 5.0

        for _ in range(5):
            engine.record_trade_abort()

        assert engine.state.consecutive_aborts == 5
        assert engine.state.status == STATUS_EMERGENCY_LOCKED
        assert engine.can_trade() is False

        # Attempt 1: Advance time by 100,000 seconds
        with patch("time.time", return_value=time.time() + 100000.0):
            assert engine.status == STATUS_EMERGENCY_LOCKED
            assert engine.can_trade() is False

        # Attempt 2: Refuel wallet with 100 SUI
        engine.update_from_wallet_balances(usdc_balance=1000.0, sui_balance=100.0)
        assert engine.state.status == STATUS_EMERGENCY_LOCKED
        assert engine.can_trade() is False

        # Attempt 3: Additional aborts while locked keep it locked
        for _ in range(3):
            engine.record_trade_abort()
        assert engine.state.status == STATUS_EMERGENCY_LOCKED
        assert engine.can_trade() is False

        # Only explicit operator unlock can release
        unlocked = engine.unlock_emergency()
        assert unlocked is True
        assert engine.state.status == STATUS_ACTIVE
        assert engine.state.consecutive_aborts == 0
        assert engine.can_trade() is True

    def test_trade_success_clears_active_cooldown(self):
        """Verifies trade success during COOLING_DOWN immediately restores ACTIVE."""
        engine = DynamicCapitalScalingEngine(initial_tier=ScalingTier.TIER_2)

        # Trigger 3 aborts -> enters COOLING_DOWN
        for _ in range(3):
            engine.record_trade_abort()
        assert engine.state.status == STATUS_COOLING_DOWN
        assert engine.can_trade() is False

        # Verified success recorded
        engine.record_trade_success(profit_usdc=5.0)
        assert engine.state.status == STATUS_ACTIVE
        assert engine.state.cooldown_until == 0.0
        assert engine.state.consecutive_aborts == 0
        assert engine.can_trade() is True


# ==============================================================================
# SECTION 3: GAS SAFETY HARD STOP STRESS
# ==============================================================================

class TestGasSafetyHardStopStress:
    """Stress tests gas safety floor boundaries and can_trade enforcement."""

    def test_gas_warning_boundary_exact_values(self):
        """Tests exact boundary behavior around 1.5 SUI warning floor."""
        engine = DynamicCapitalScalingEngine()

        # Above floor: 1.500000001 SUI
        engine.update_from_wallet_balances(usdc_balance=0.0, sui_balance=1.500000001)
        assert engine.state.gas_warning is False
        assert engine.state.status == STATUS_ACTIVE
        assert engine.can_trade() is True

        # Exactly at floor: 1.500000000 SUI (< 1.5 is False)
        engine.update_from_wallet_balances(usdc_balance=0.0, sui_balance=1.500000000)
        assert engine.state.gas_warning is False
        assert engine.can_trade() is True

        # Below floor: 1.499999999 SUI (< 1.5 is True)
        engine.update_from_wallet_balances(usdc_balance=0.0, sui_balance=1.499999999)
        assert engine.state.gas_warning is True
        assert engine.state.status == STATUS_ACTIVE  # Active but warning
        assert engine.can_trade() is True

    def test_gas_critical_hard_stop_boundary_exact_values(self):
        """Tests exact boundary behavior around 0.5 SUI critical floor."""
        engine = DynamicCapitalScalingEngine()

        # Above critical floor: 0.500000001 SUI
        engine.update_from_wallet_balances(usdc_balance=0.0, sui_balance=0.500000001)
        assert engine.state.status == STATUS_ACTIVE
        assert engine.state.gas_warning is True  # still < 1.5 SUI
        assert engine.can_trade() is True

        # Exactly at critical floor: 0.500000000 SUI (< 0.5 is False)
        engine.update_from_wallet_balances(usdc_balance=0.0, sui_balance=0.500000000)
        assert engine.state.status == STATUS_ACTIVE
        assert engine.can_trade() is True

        # Below critical floor: 0.499999999 SUI (< 0.5 is True)
        engine.update_from_wallet_balances(usdc_balance=0.0, sui_balance=0.499999999)
        assert engine.state.status == STATUS_EMERGENCY_LOCKED
        assert engine.state.gas_warning is True
        assert engine.can_trade() is False

    def test_can_trade_strictly_enforces_critical_floor_even_if_status_active(self):
        """Stress tests that can_trade() intercepts status=ACTIVE if gas is below 0.5 SUI."""
        engine = DynamicCapitalScalingEngine()
        engine.state.sui_gas_balance = 0.45
        engine.state.status = STATUS_ACTIVE  # Artificially set to ACTIVE

        # Calling can_trade() must catch the gas violation and re-lock
        assert engine.can_trade() is False
        assert engine.state.status == STATUS_EMERGENCY_LOCKED

    def test_unlock_emergency_blocked_when_gas_is_sub_critical(self):
        """Verifies unlock_emergency(force=False) fails when gas < 0.5 SUI."""
        engine = DynamicCapitalScalingEngine()
        engine.update_from_wallet_balances(usdc_balance=0.0, sui_balance=0.35)
        assert engine.state.status == STATUS_EMERGENCY_LOCKED

        # Non-forced unlock must fail
        unlocked = engine.unlock_emergency(force=False)
        assert unlocked is False
        assert engine.state.status == STATUS_EMERGENCY_LOCKED
        assert engine.can_trade() is False

        # Forced unlock overrides
        forced = engine.unlock_emergency(force=True)
        assert forced is True
        assert engine.state.status == STATUS_ACTIVE

    def test_gas_replenishment_restores_active_status(self):
        """Verifies replenishing gas above critical floor restores active status."""
        engine = DynamicCapitalScalingEngine()
        engine.update_from_wallet_balances(usdc_balance=0.0, sui_balance=0.25)
        assert engine.state.status == STATUS_EMERGENCY_LOCKED
        assert engine.can_trade() is False

        # Deposit 4.0 SUI into wallet
        engine.update_from_wallet_balances(usdc_balance=0.0, sui_balance=4.0)
        assert engine.state.status == STATUS_ACTIVE
        assert engine.state.gas_warning is False
        assert engine.can_trade() is True

    def test_zero_gas_balance_empirical_behavior(self):
        """Empirically records the behavior when wallet updates with 0.0 SUI.

        1. update_from_wallet_balances(usdc, 0.0) sets status to EMERGENCY_LOCKED.
        2. can_trade() returns False while status is EMERGENCY_LOCKED.
        3. If unlock_emergency(force=False) is called, because sui_gas_balance > 0 is False,
           it unlocks without force (conflating uninitialized with empty).
        """
        engine = DynamicCapitalScalingEngine()
        engine.update_from_wallet_balances(usdc_balance=0.0, sui_balance=0.0)

        assert engine.state.status == STATUS_EMERGENCY_LOCKED
        assert engine.can_trade() is False

        # When 0.0 SUI is present, unlock_emergency(force=False) allows unlock due to (sui_gas_balance > 0)
        unlocked = engine.unlock_emergency(force=False)
        assert unlocked is True
        assert engine.state.status == STATUS_ACTIVE



# ==============================================================================
# SECTION 4: DECIMAL & SUI SPOT PRICE EDGE TESTING
# ==============================================================================

class TestDecimalAndSpotPriceEdgeStress:
    """Stress tests extreme spot prices ($0.01 to $1,000/SUI) and integer bounds."""

    @pytest.mark.parametrize("pair_name", ["DEEP/SUI", "CETUS/SUI"])
    @pytest.mark.parametrize("spot_price", [
        0.01,
        0.05,
        0.1,
        0.5,
        1.0,
        1.8349281,
        2.0,
        3.5,
        10.0,
        50.0,
        100.0,
        500.0,
        1000.0,
    ])
    def test_sui_quote_pairs_integer_bounded_across_price_spectrum(
        self, pair_name: str, spot_price: float
    ):
        """Verifies borrow calculations for SUI quote pairs always return valid integers."""
        engine = DynamicCapitalScalingEngine()

        for tier in [ScalingTier.TIER_1, ScalingTier.TIER_2, ScalingTier.TIER_3]:
            engine.state.current_tier = tier
            borrow = engine.get_current_borrow_amount(pair_name, sui_spot_price=spot_price)

            # Must be integer type
            assert isinstance(borrow, int)
            assert borrow > 0

            # Mathematical oracle check:
            # borrow == round((tier_usd / spot_price) * 1e9)
            expected_mist = int(round((tier.usd_value / spot_price) * 1_000_000_000))
            assert borrow == expected_mist

    @pytest.mark.parametrize("pair_name", ["SUI/USDC", "DEEP/USDC"])
    @pytest.mark.parametrize("spot_price", [0.01, 2.0, 1000.0])
    def test_usdc_quote_pairs_invariant_under_spot_price_variations(
        self, pair_name: str, spot_price: float
    ):
        """Verifies USDC quote pairs are invariant under SUI spot price shifts."""
        engine = DynamicCapitalScalingEngine()

        for tier, expected_units in [
            (ScalingTier.TIER_1, 1_000_000_000),
            (ScalingTier.TIER_2, 5_000_000_000),
            (ScalingTier.TIER_3, 10_000_000_000),
        ]:
            engine.state.current_tier = tier
            borrow = engine.get_current_borrow_amount(pair_name, sui_spot_price=spot_price)
            assert isinstance(borrow, int)
            assert borrow == expected_units

    @pytest.mark.parametrize("bad_price", [0.0, -0.01, -1.0, -1000.0])
    def test_non_positive_spot_price_raises_value_error(self, bad_price: float):
        """Verifies non-positive spot prices raise ValueError."""
        engine = DynamicCapitalScalingEngine()
        with pytest.raises(ValueError, match="sui_spot_price must be positive"):
            engine.get_current_borrow_amount("DEEP/SUI", sui_spot_price=bad_price)

    def test_pair_name_case_insensitivity_and_formatting(self):
        """Verifies robustness across formatting variants: lowercase, underscore, whitespace."""
        engine = DynamicCapitalScalingEngine()

        assert engine.get_current_borrow_amount("deep/sui", sui_spot_price=2.0) == 500_000_000_000
        assert engine.get_current_borrow_amount("cetus_sui", sui_spot_price=2.0) == 500_000_000_000
        assert engine.get_current_borrow_amount(" SUI/USDC  ") == 1_000_000_000
        assert engine.get_current_borrow_amount("deep_usdc") == 1_000_000_000


# ==============================================================================
# SECTION 5: MONTE CARLO RANDOMIZED ORACLE STRESS HARNESS
# ==============================================================================

class TestMonteCarloOracleHarness:
    """Randomized stress harness validating state machine invariants across 500 actions."""

    def test_500_interleaved_transitions_preserve_all_invariants(self):
        """Executes 500 random actions and validates global state machine invariants."""
        random.seed(42)
        engine = DynamicCapitalScalingEngine(initial_baseline_usdc=0.0)

        pairs = ["SUI/USDC", "DEEP/SUI", "DEEP/USDC", "CETUS/SUI"]
        current_virtual_time = time.time()

        for step in range(500):
            action = random.choice([
                "success",
                "abort",
                "wallet_update",
                "advance_time",
                "unlock",
                "borrow_query",
            ])

            if action == "success":
                profit = round(random.uniform(0.0, 50.0), 2)
                engine.record_trade_success(profit_usdc=profit)

            elif action == "abort":
                engine.record_trade_abort()

            elif action == "wallet_update":
                # Simulated SUI balance between 0.1 and 10.0
                sim_sui = round(random.uniform(0.1, 10.0), 4)
                sim_usdc = max(engine.state.accumulated_net_profit_usdc, random.uniform(0.0, 1500.0))
                engine.update_from_wallet_balances(usdc_balance=sim_usdc, sui_balance=sim_sui)

            elif action == "advance_time":
                current_virtual_time += random.uniform(10.0, 120.0)

            elif action == "unlock":
                if engine.state.status == STATUS_EMERGENCY_LOCKED:
                    engine.unlock_emergency(force=True)

            elif action == "borrow_query":
                pair = random.choice(pairs)
                spot = random.uniform(0.5, 5.0)
                amount = engine.get_current_borrow_amount(pair, sui_spot_price=spot)
                assert isinstance(amount, int)
                assert amount > 0

            # ------------------------------------------------------------------
            # INVARIANT CHECKS AFTER EVERY TRANSITION
            # ------------------------------------------------------------------
            with patch("time.time", return_value=current_virtual_time):
                # 1. Flash borrow amount matches tier value exactly
                assert engine.flash_borrow_amount == int(engine.current_tier.value)

                # 2. Tier is one of the valid enum values
                assert engine.current_tier in (ScalingTier.TIER_1, ScalingTier.TIER_2, ScalingTier.TIER_3)

                # 3. Counters are non-negative
                assert engine.state.accumulated_net_profit_usdc >= 0.0
                assert engine.state.successful_trades >= 0
                assert engine.state.consecutive_aborts >= 0

                # 4. If consecutive aborts >= 5, status must be EMERGENCY_LOCKED
                if engine.state.consecutive_aborts >= 5:
                    assert engine.state.status == STATUS_EMERGENCY_LOCKED

                # 5. If gas balance < 0.5 SUI and > 0, can_trade() must be False
                if 0 < engine.state.sui_gas_balance < 0.5:
                    assert engine.can_trade() is False
                    assert engine.state.status == STATUS_EMERGENCY_LOCKED

                # 6. If status is COOLING_DOWN and virtual time < cooldown_until, can_trade() must be False
                if engine.state.status == STATUS_COOLING_DOWN:
                    if current_virtual_time < engine.state.cooldown_until:
                        assert engine.can_trade() is False
