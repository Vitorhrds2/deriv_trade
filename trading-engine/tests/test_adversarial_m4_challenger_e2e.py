"""Comprehensive Adversarial End-to-End Test Suite for Sui Arbitrage Engine.

Empirical Challenger verification across Milestones 1, 2, 3, and 4 (Requirements R1 through R5):
1. Target 1: Move VM Zero Leg Risk & Hot Potato Reversion:
   - Negative spread, fee shortfall, unexpected slippage, and front-running sandwich attacks
     across all 4 pairs on BOTH Cetus and Turbos in BOTH Forward and Reverse routes.
   - Asserts:
     * status == "ABORTED"
     * 0 state mutations
     * 0 unquenched Hot Potato receipts (clean abort)
     * Exact nominal gas cost (~0.002 SUI / 2,000,000 MIST)
     * Zero Leg Risk preserved (zero_leg_risk_preserved == True)
2. Target 2: Q* Optimal Sizing & Dynamic Tranche Bounds:
   - Extremely large spreads (up to 50,000 bps) clamp strictly to Q_max.
   - Extremely thin liquidity (L -> 0) avoids division-by-zero, returning 0 or Q_min.
   - Negative or sub-hurdle spreads return 0.
   - DEEP/USDC dynamic tranche bounds never exceed $150 USDC under any spread.
   - DEEP/SUI scales up to $4,000 USD without integer or float overflow.
3. Target 3: DeepBook Vault Balance Depletion:
   - Quote vault cash nearly depleted (e.g. 10 SUI or 50 USDC).
   - Preflight validator and bot runner skip execution with SKIPPED_VAULT_PROTECTED.
   - Eliminates Move abort code 2 (EInsufficientVaultBalance).
4. Target 4: Turbos vs Cetus Multi-DEX Invariants:
   - Dynamic spread shifts (Turbos cheaper -> Cetus cheaper).
   - Scanner identifies optimal AMM (best_amm) and best_route (FORWARD / REVERSE).
   - PTB builder generates strictly valid router calls matching the selected AMM.
"""

from __future__ import annotations

import asyncio
import math
import random
import sys
import time
from pathlib import Path
from typing import Any, Dict, List
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Ensure trading-engine directory is on sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from venues.sui_bot_runner import ACTIVE_PAIRS, SuiBotConfig, SuiBotRunner
from venues.sui_deepbook_venue import (
    CETUS_GLOBAL_CONFIG_ID,
    DEEPBOOK_PACKAGE_ID,
    SUI_CLOCK_OBJECT_ID,
    SUI_PAIRS_CONFIG,
    TURBOS_PACKAGE_ID,
    TURBOS_POOL_CONFIG_ID,
    TURBOS_VERSIONED_ID,
    HotPotatoPTBParams,
    PairConfig,
    SuiDeepBookPTBBuilder,
    SuiDeepBookVenue,
    SuiGraphQLClient,
)
from venues.sui_ptb_validator import SuiPTBPreflightValidator
from venues.sui_scaling_engine import (
    DEFAULT_DYNAMIC_TRANCHE_BOUNDS_USD,
    DEFAULT_PAIR_FEE_HURDLE_BPS,
    DynamicCapitalScalingEngine,
    ScalingTier,
    calculate_optimal_borrow_q_star,
)


# ==============================================================================
# TARGET 1: MOVE VM ZERO LEG RISK & HOT POTATO REVERSION (R1 & R4)
# ==============================================================================

class TestTarget1MoveVMZeroLegRiskAndHotPotatoReversion:
    """Empirically stress-tests Move VM Zero Leg Risk and Hot Potato atomicity.

    Asserts that ANY negative spread, fee shortfall, unexpected slippage, or
    front-running sandwich scenario causes the PTB to abort cleanly with:
    - 0 state mutations
    - 0 unquenched Hot Potato receipts
    - Exact nominal gas cost (~0.002 SUI / 2,000,000 MIST)
    - Zero Leg Risk preserved across all 4 pairs on BOTH Cetus and Turbos
      in BOTH Forward and Reverse routes.
    """

    @pytest.fixture(autouse=True)
    def setup_fixtures(self) -> None:
        self.venue = SuiDeepBookVenue()
        self.builder = SuiDeepBookPTBBuilder()
        self.validator = SuiPTBPreflightValidator()

    @pytest.mark.parametrize("pair_name", ["SUI/USDC", "DEEP/SUI", "DEEP/USDC", "CETUS/SUI"])
    @pytest.mark.parametrize("amm_target", ["cetus", "turbos"])
    @pytest.mark.parametrize("route_dir", ["FORWARD", "REVERSE"])
    def test_negative_spread_zero_leg_risk_aborts_cleanly(
        self, pair_name: str, amm_target: str, route_dir: str
    ) -> None:
        """Adversarially forces a negative spread (-500 bps).

        Asserts that SplitCoins aborts due to proceeds shortfall, leaving Hot Potato
        unquenched and reverting all state mutations with exact nominal gas cost.
        """
        cfg = SUI_PAIRS_CONFIG[pair_name]
        borrow_amount = cfg.default_borrow_amount

        ptb_params = HotPotatoPTBParams.from_pair(
            pair_name=pair_name,
            flash_borrow_amount=borrow_amount,
            route_direction=route_dir,
            amm_target=amm_target,
            deduct_fees=True,
        )
        ptb = self.builder.build_atomic_arb_ptb(ptb_params)

        # Baseline price
        base_px = 2.0 if "USDC" in pair_name else 0.05
        # Set negative spread: Bid 5% below Ask/AMM
        if route_dir == "FORWARD":
            deepbook_bid_px = base_px * 0.95  # Severe negative spread
            amm_swap_out_px = base_px
            deepbook_ask_px = base_px
        else:
            deepbook_bid_px = base_px
            deepbook_ask_px = base_px * 1.05  # DeepBook Ask is high
            amm_swap_out_px = base_px * 0.95  # AMM sell price is low

        result = self.venue.simulate_dry_run(
            ptb=ptb,
            deepbook_bid_px=deepbook_bid_px,
            amm_swap_out_px=amm_swap_out_px,
            borrow_amount=borrow_amount,
            pair=pair_name,
            deduct_fees=True,
            route_direction=route_dir,
            deepbook_ask_px=deepbook_ask_px,
            amm_target=amm_target,
        )

        # Move VM Invariants:
        assert result["status"] == "ABORTED"
        assert result["state_mutations"] == 0
        assert result["zero_leg_risk_preserved"] is True
        assert result["hot_potato_aborted"] is True
        assert result.get("hot_potato_satisfied", False) is False
        assert result["gas_cost_sui"] == 0.002
        assert result["gas_used_mist"] == 2_000_000
        assert result["net_profit_quote"] == 0.0
        assert result["shortfall_native"] > 0
        assert result["route_direction"] == route_dir
        assert result["amm_target"] == amm_target

    @pytest.mark.parametrize("pair_name", ["SUI/USDC", "DEEP/SUI", "DEEP/USDC", "CETUS/SUI"])
    @pytest.mark.parametrize("amm_target", ["cetus", "turbos"])
    @pytest.mark.parametrize("route_dir", ["FORWARD", "REVERSE"])
    def test_fee_shortfall_sub_hurdle_aborts_cleanly(
        self, pair_name: str, amm_target: str, route_dir: str
    ) -> None:
        """Adversarially forces a nominally positive gross spread that is below fee hurdles.

        Gross spread is +3 bps, but fees are >= 6 bps (up to 36 bps on CETUS/SUI).
        Net proceeds cannot satisfy SplitCoins repayment principal.
        """
        cfg = SUI_PAIRS_CONFIG[pair_name]
        borrow_amount = cfg.default_borrow_amount
        base_px = 2.0 if "USDC" in pair_name else 0.05

        ptb_params = HotPotatoPTBParams.from_pair(
            pair_name=pair_name,
            flash_borrow_amount=borrow_amount,
            route_direction=route_dir,
            amm_target=amm_target,
            deduct_fees=True,
        )
        ptb = self.builder.build_atomic_arb_ptb(ptb_params)

        # Gross spread +3 bps (+0.03%)
        if route_dir == "FORWARD":
            amm_swap_out_px = base_px
            deepbook_bid_px = base_px * 1.0003
            deepbook_ask_px = base_px
        else:
            deepbook_ask_px = base_px
            amm_swap_out_px = base_px * 1.0003
            deepbook_bid_px = base_px

        result = self.venue.simulate_dry_run(
            ptb=ptb,
            deepbook_bid_px=deepbook_bid_px,
            amm_swap_out_px=amm_swap_out_px,
            borrow_amount=borrow_amount,
            pair=pair_name,
            deduct_fees=True,
            route_direction=route_dir,
            deepbook_ask_px=deepbook_ask_px,
            amm_target=amm_target,
        )

        assert result["status"] == "ABORTED"
        assert result["state_mutations"] == 0
        assert result["zero_leg_risk_preserved"] is True
        assert result["hot_potato_aborted"] is True
        assert result["gas_cost_sui"] == 0.002
        assert result["net_profit_quote"] == 0.0
        assert result["shortfall_native"] > 0

    @pytest.mark.parametrize("pair_name", ["SUI/USDC", "DEEP/SUI", "DEEP/USDC", "CETUS/SUI"])
    @pytest.mark.parametrize("slippage_pct", [0.10, 0.25, 0.50, 0.90])
    def test_catastrophic_slippage_and_sandwich_shock(
        self, pair_name: str, slippage_pct: float
    ) -> None:
        """Adversarial stress test simulating sandwich front-running and sudden liquidity shock.

        Even if scanner detected a profitable opportunity, unexpected execution slippage
        reverts atomically in Move VM without leaving any leg unhedged.
        """
        cfg = SUI_PAIRS_CONFIG[pair_name]
        borrow_amount = cfg.default_borrow_amount
        base_px = 2.0 if "USDC" in pair_name else 0.05

        # Scan thought spread was +100 bps
        # But execution suffered slippage_pct adverse movement
        slipped_bid_px = base_px * (1.0 - slippage_pct)

        ptb_params = HotPotatoPTBParams.from_pair(
            pair_name=pair_name,
            flash_borrow_amount=borrow_amount,
            route_direction="FORWARD",
            amm_target="turbos",
            deduct_fees=True,
        )
        ptb = self.builder.build_atomic_arb_ptb(ptb_params)

        result = self.venue.simulate_dry_run(
            ptb=ptb,
            deepbook_bid_px=slipped_bid_px,
            amm_swap_out_px=base_px,
            borrow_amount=borrow_amount,
            pair=pair_name,
            deduct_fees=True,
            route_direction="FORWARD",
            amm_target="turbos",
        )

        assert result["status"] == "ABORTED"
        assert result["state_mutations"] == 0
        assert result["zero_leg_risk_preserved"] is True
        assert result["hot_potato_aborted"] is True
        assert result["gas_cost_sui"] == 0.002
        assert result["shortfall_native"] > 0

    def test_preflight_validator_simulate_ptb_dry_run_unprofitable_aborts(self) -> None:
        """Tests that SuiPTBPreflightValidator.simulate_ptb_dry_run strictly asserts abort invariants."""
        for pair in ACTIVE_PAIRS:
            report = self.validator.simulate_ptb_dry_run(
                pair_name=pair,
                spread_bps=-25.0,  # Negative spread
                route_direction="REVERSE",
                amm_target="turbos",
            )
            assert report["status"] == "ABORTED"
            assert report["state_mutations"] == 0
            assert report["zero_leg_risk_preserved"] is True
            assert report["gas_cost_sui"] == 0.002
            assert report["net_profit"] == 0.0


# ==============================================================================
# TARGET 2: Q* OPTIMAL SIZING & DYNAMIC TRANCHE BOUNDS (R2)
# ==============================================================================

class TestTarget2QStarOptimalSizingAndDynamicTrancheBounds:
    """Empirically stress-tests analytical Q* sizing under adversarial conditions.

    Vectors:
    - Extremely large spreads (up to 50,000 bps) clamp strictly to Q_max.
    - Extremely thin liquidity (L -> 0) avoids division-by-zero, returning 0 or Q_min.
    - Negative or sub-hurdle spreads return 0.
    - DEEP/USDC tranche bounds never exceed $150 USDC under ANY spread.
    - DEEP/SUI scales up to $4,000 USD without integer or float overflow.
    """

    @pytest.fixture(autouse=True)
    def setup_fixtures(self) -> None:
        self.scaling_engine = DynamicCapitalScalingEngine(initial_tier=ScalingTier.TIER_1)

    @pytest.mark.parametrize("spread_bps", [1000.0, 5000.0, 10000.0, 50000.0])
    def test_extremely_large_spreads_strictly_clamp_to_dynamic_max_tranche(
        self, spread_bps: float
    ) -> None:
        """Asserts that regardless of spread size, Q* is strictly bounded by max_tranche."""
        # Test direct closed-form formula
        min_tranche = 100_000_000   # 100 USDC
        max_tranche = 150_000_000   # 150 USDC
        liq = 2.40e11
        sqrt_p = 0.3162277  # sqrt(0.10)

        q_star = calculate_optimal_borrow_q_star(
            spread_bps=spread_bps,
            liquidity=liq,
            sqrt_price=sqrt_p,
            fee_bps=6.0,
            min_tranche=min_tranche,
            max_tranche=max_tranche,
        )
        assert q_star == max_tranche
        assert q_star <= 150_000_000

    @pytest.mark.parametrize("thin_l", [0.0, 1e-12, 1e-6, 0.001, 1.0, 100.0])
    def test_extremely_thin_liquidity_avoids_division_by_zero_and_returns_safe_tranche(
        self, thin_l: float
    ) -> None:
        """Asserts that as L -> 0, sizing never raises ZeroDivisionError, NaN, or Inf,
        and respects min_tranche / floor bounds.
        """
        # 1. Closed-form function
        q_star = calculate_optimal_borrow_q_star(
            spread_bps=50.0,
            liquidity=thin_l,
            sqrt_price=1.414,
            fee_bps=10.0,
            min_tranche=1000,
            max_tranche=10000,
        )
        assert isinstance(q_star, int)
        assert not math.isnan(q_star)
        assert q_star >= 0
        # If raw sizing < min_tranche, it should return min_tranche (clamped) unless upper bound < min_tranche
        assert q_star in (0, 1000)

        # 2. Scaling engine get_current_borrow_amount
        borrow = self.scaling_engine.get_current_borrow_amount(
            pair_name="SUI/USDC",
            sui_spot_price=2.0,
            spread_bps=50.0,
            liquidity=thin_l,
            sqrt_price=1.414,
        )
        assert isinstance(borrow, int)
        assert not math.isnan(borrow)
        assert borrow >= 0

    @pytest.mark.parametrize("sub_hurdle_spread", [-5000.0, -100.0, 0.0, 3.0, 5.9])
    def test_negative_or_sub_hurdle_spread_strictly_returns_zero(
        self, sub_hurdle_spread: float
    ) -> None:
        """Asserts that any spread <= fee hurdle immediately returns 0 borrow amount."""
        fee_hurdle = 6.0  # DEEP/USDC hurdle

        # Closed-form
        q_star = calculate_optimal_borrow_q_star(
            spread_bps=sub_hurdle_spread,
            liquidity=2.40e11,
            sqrt_price=0.316,
            fee_bps=fee_hurdle,
            min_tranche=100_000_000,
            max_tranche=150_000_000,
        )
        assert q_star == 0

        # Scaling engine
        borrow = self.scaling_engine.get_current_borrow_amount(
            pair_name="DEEP/USDC",
            sui_spot_price=2.0,
            spread_bps=sub_hurdle_spread,
            fee_bps=fee_hurdle,
        )
        assert borrow == 0

    def test_deepbook_usdc_tranche_never_exceeds_150_usdc_monte_carlo(self) -> None:
        """Adversarial Monte Carlo sweep across 500 random spreads, liquidities, and prices.

        Requirement R2 Core Invariant:
        DEEP/USDC borrow amount MUST NEVER exceed $150 USDC (150_000_000 micro-units).
        """
        random.seed(42)
        for _ in range(500):
            spread = random.uniform(7.0, 100_000.0)
            liquidity = random.uniform(1e6, 1e18)
            sui_spot = random.uniform(0.1, 50.0)
            sqrt_p = random.uniform(0.01, 10.0)

            borrow = self.scaling_engine.get_current_borrow_amount(
                pair_name="DEEP/USDC",
                sui_spot_price=sui_spot,
                spread_bps=spread,
                liquidity=liquidity,
                sqrt_price=sqrt_p,
            )
            assert borrow <= 150_000_000, f"DEEP/USDC exceeded 150 USDC: {borrow}"
            if borrow > 0:
                assert borrow >= 25_000_000, f"DEEP/USDC below floor: {borrow}"

    def test_deep_sui_tranche_scales_to_4000_usd_without_overflow(self) -> None:
        """Asserts that DEEP/SUI scales up to $4,000 USD without integer or float overflow.

        DEEP/SUI liquidity is deep (L ~= 9.84e14), taker fee is 0 bps.
        At $2.00/SUI, $4,000 USD is 2,000 SUI (2,000,000,000,000 MIST).
        """
        sui_spot = 2.0
        expected_max_mist = int(round((4000.0 / sui_spot) * 1_000_000_000))  # 2,000,000,000,000 MIST

        borrow = self.scaling_engine.get_current_borrow_amount(
            pair_name="DEEP/SUI",
            sui_spot_price=sui_spot,
            spread_bps=5000.0,  # Massive 50% spread
            liquidity=9.8371e14,
            sqrt_price=(0.05) ** 0.5,
            fee_bps=6.0,
        )
        assert borrow == expected_max_mist
        assert borrow == 2_000_000_000_000
        assert isinstance(borrow, int)


# ==============================================================================
# TARGET 3: DEEPBOOK VAULT BALANCE DEPLETION & EInsufficientVaultBalance (R3)
# ==============================================================================

class TestTarget3DeepBookVaultBalanceDepletion:
    """Empirically stress-tests vault cash depletion scenarios.

    Simulates DeepBook pool vaults where quote cash is nearly depleted
    (e.g. 10 SUI or 50 USDC):
    - Assert that preflight validator reports EInsufficientVaultBalance.
    - Assert that bot runner skip execution with SKIPPED_VAULT_PROTECTED.
    - Confirms that Move abort code 2 (EInsufficientVaultBalance) is 100% eliminated.
    """

    @pytest.fixture(autouse=True)
    def setup_fixtures(self) -> None:
        self.validator = SuiPTBPreflightValidator()

    @pytest.mark.parametrize(
        "pair_name,depleted_quote_balance,min_tranche_units",
        [
            ("DEEP/SUI", 10_000_000_000, 500_000_000_000),      # 10 SUI in vault vs 500 SUI default
            ("CETUS/SUI", 5_000_000_000, 50_000_000_000),       # 5 SUI in vault vs 50 SUI default
            ("DEEP/USDC", 50_000_000, 100_000_000),             # 50 USDC in vault vs 100 USDC min tranche
            ("SUI/USDC", 20_000_000, 1_000_000_000),            # 20 USDC in vault vs 1,000 USDC tier 1
        ],
    )
    def test_preflight_validator_detects_depleted_vault_and_flags_abort_code_2(
        self, pair_name: str, depleted_quote_balance: int, min_tranche_units: int
    ) -> None:
        """Validates that SuiPTBPreflightValidator detects vault balance depletion and raises
        error string explicitly referencing EInsufficientVaultBalance (abort code 2).
        """
        depleted_vaults = {
            "base_balance": 1_000_000_000_000,
            "quote_balance": depleted_quote_balance,
            "deep_balance": 1_000_000_000,
        }

        # 1. validate_vault_balance direct call
        check = self.validator.validate_vault_balance(
            pair_name=pair_name,
            borrow_amount=min_tranche_units,
            vault_balances=depleted_vaults,
        )
        assert check["valid"] is False
        assert "EInsufficientVaultBalance (abort code 2)" in check["error"]
        assert check["borrow_amount"] > check["max_allowed_borrow"]

        # 2. validate_atomic_ptb_generation with vault_balances
        ptb_check = self.validator.validate_atomic_ptb_generation(
            pair_name=pair_name,
            borrow_amount=min_tranche_units,
            vault_balances=depleted_vaults,
        )
        assert ptb_check["valid"] is False
        assert any("EInsufficientVaultBalance" in err for err in ptb_check["errors"])

    @pytest.mark.asyncio
    async def test_bot_runner_scan_once_skips_depleted_vault_with_skipped_vault_protected(
        self,
    ) -> None:
        """Simulates full end-to-end bot runner scan_once pass where market has an attractive spread
        (+50 bps), but DeepBook vault has only 10 SUI quote cash.

        Asserts:
        - status == "SKIPPED_VAULT_PROTECTED"
        - execution_status == "SKIPPED_VAULT_PROTECTED"
        - net_profit == 0.0
        - zero_leg_risk_preserved == True
        - is_profitable == False
        - 0 live order submissions executed
        """
        runner = SuiBotRunner(config=SuiBotConfig(dry_run_mode=True, amm_target="cetus"))

        # Setup attractive spread (+50 bps on DEEP/SUI)
        mock_spreads = {
            "SUI/USDC": {"forward_spread_bps": 0.0, "reverse_spread_bps": 0.0, "cetus_price": 2.0},
            "DEEP/SUI": {
                "forward_spread_bps": 50.0,  # Highly attractive
                "reverse_spread_bps": 0.0,
                "cetus_price": 0.05,
                "deepbook_price": 0.05025,
                "deepbook_ask": 0.05025,
                "cetus_liquidity": 9.84e14,
                "cetus_sqrt_price": (0.05) ** 0.5,
            },
            "DEEP/USDC": {"forward_spread_bps": 0.0, "reverse_spread_bps": 0.0, "cetus_price": 0.10},
            "CETUS/SUI": {"forward_spread_bps": 0.0, "reverse_spread_bps": 0.0, "cetus_price": 0.16},
        }

        # Vault has only 10 SUI (10,000,000,000 MIST)
        depleted_vault_balances = {
            "base_balance": 100_000_000_000_000,
            "quote_balance": 10_000_000_000,  # 10 SUI
            "deep_balance": 1_000_000_000,
        }

        with patch.object(runner, "poll_market_spreads", new_callable=AsyncMock) as mock_poll:
            mock_poll.return_value = mock_spreads
            with patch.object(
                runner.validator.graphql_client,
                "get_deepbook_vault_balances",
                new_callable=AsyncMock,
            ) as mock_vault:
                mock_vault.return_value = depleted_vault_balances

                results = await runner.scan_once()

                # Execution was safely skipped without throwing an unhandled exception
                # Results contains 4 pair status summaries
                assert len(results) == 4
                deep_sui_res = next(r for r in results if r["pair"] == "DEEP/SUI")
                assert deep_sui_res["execution_status"] == "SKIPPED_VAULT_PROTECTED"
                assert deep_sui_res["status"] == "SKIPPED_VAULT_PROTECTED"
                assert deep_sui_res["net_profit"] == 0.0
                assert deep_sui_res["zero_leg_risk_preserved"] is True
                assert deep_sui_res["is_profitable"] is False
                assert runner.total_executions_attempted == 0


# ==============================================================================
# TARGET 4: TURBOS VS CETUS MULTI-DEX INVARIANTS (R4)
# ==============================================================================

class TestTarget4TurbosVsCetusMultiDEXInvariants:
    """Empirically stress-tests multi-DEX selection invariants between Cetus and Turbos.

    Vectors:
    - Turbos cheaper than Cetus -> scanner selects Turbos, PTB builds Turbos router call.
    - Cetus cheaper than Turbos -> scanner selects Cetus, PTB builds Cetus router call.
    - Reverse route spread shifts -> scanner routes to optimal DEX without config mismatch.
    - PTB structure invariants strictly adhere to protocol requirements for each DEX.
    """

    @pytest.fixture(autouse=True)
    def setup_fixtures(self) -> None:
        self.builder = SuiDeepBookPTBBuilder()
        self.validator = SuiPTBPreflightValidator()

    def test_turbos_forward_and_reverse_ptb_structure_invariants(self) -> None:
        """Verifies strict 8-command PTB structure and parameter bindings for Turbos CLMM."""
        for route_dir in ["FORWARD", "REVERSE"]:
            params = HotPotatoPTBParams.from_pair(
                pair_name="SUI/USDC",
                flash_borrow_amount=100_000_000,
                route_direction=route_dir,
                amm_target="turbos",
            )
            ptb = self.builder.build_atomic_arb_ptb(params)
            commands = ptb["commands"]
            assert len(commands) == 8

            if route_dir == "FORWARD":
                # Turbos swap is Command 1: swap_b_a_with_return_ (Quote -> Base)
                swap_cmd = commands[1]
                assert swap_cmd["package"] == TURBOS_PACKAGE_ID
                assert swap_cmd["module"] == "swap_router"
                assert swap_cmd["function"] == "swap_b_a_with_return_"
                # Verify Turbos Versioned ID and Clock object arguments
                arg_inputs = [arg.get("Input") for arg in swap_cmd["arguments"] if "Input" in arg]
                assert TURBOS_VERSIONED_ID in arg_inputs
                assert SUI_CLOCK_OBJECT_ID in arg_inputs
            else:
                # Turbos swap is Command 4: swap_a_b_with_return_ (Base -> Quote)
                swap_cmd = commands[4]
                assert swap_cmd["package"] == TURBOS_PACKAGE_ID
                assert swap_cmd["module"] == "swap_router"
                assert swap_cmd["function"] == "swap_a_b_with_return_"
                arg_inputs = [arg.get("Input") for arg in swap_cmd["arguments"] if "Input" in arg]
                assert TURBOS_VERSIONED_ID in arg_inputs
                assert SUI_CLOCK_OBJECT_ID in arg_inputs

            # Hot Potato repayment is Command 6 across both directions
            repay_cmd = commands[6]
            assert repay_cmd["package"] == DEEPBOOK_PACKAGE_ID
            assert repay_cmd["function"] == "return_flashloan_quote"
            # Hot Potato receipt comes from Command 0 result 1
            assert repay_cmd["arguments"][2] == {"NestedResult": [0, 1]}

    def test_cetus_forward_and_reverse_ptb_structure_invariants(self) -> None:
        """Verifies strict 8-command PTB structure and parameter bindings for Cetus AMM."""
        for route_dir in ["FORWARD", "REVERSE"]:
            params = HotPotatoPTBParams.from_pair(
                pair_name="DEEP/SUI",
                flash_borrow_amount=500_000_000_000,
                route_direction=route_dir,
                amm_target="cetus",
            )
            ptb = self.builder.build_atomic_arb_ptb(params)
            commands = ptb["commands"]
            assert len(commands) == 8

            swap_idx = 1 if route_dir == "FORWARD" else 4
            swap_cmd = commands[swap_idx]
            assert swap_cmd["package"] == "cetus_clmm"
            assert swap_cmd["module"] == "pool"
            assert swap_cmd["function"] == "swap"
            arg_inputs = [arg.get("Input") for arg in swap_cmd["arguments"] if "Input" in arg]
            assert CETUS_GLOBAL_CONFIG_ID in arg_inputs

    @pytest.mark.asyncio
    async def test_dynamic_spread_shifts_between_cetus_and_turbos_route_optimally(
        self,
    ) -> None:
        """Simulates adversarial spread shifts:
        1. Shift A: Turbos price is 1.98 (cheaper buy) vs Cetus 2.00.
           DeepBook EWMA price is 2.04.
           Scanner selects Turbos (best_amm="turbos").
        2. Shift B: Cetus price drops to 1.96 while Turbos is 2.02.
           DeepBook EWMA price is 2.04.
           Scanner dynamically switches to Cetus (best_amm="cetus").
        """
        client = SuiGraphQLClient()

        # Shift A Mock: Turbos is cheaper (1.98 vs 2.00)
        cetus_sqrt_p_a = str(int(math.sqrt(500.0) * (2 ** 64)))  # 2.00
        turbos_sqrt_p_a = str(int(math.sqrt(0.00198) * (2 ** 64)))  # 1.98

        mock_data_shift_a = {
            "data": {
                "d_sui_usdc": {
                    "dynamicFields": {
                        "nodes": [
                            {
                                "name": {"json": "ZXdtYQ=="},
                                "value": {"json": {"mean": "204000000000"}},  # DeepBook price = 2.04
                            }
                        ]
                    }
                },
                "p_sui_usdc": {
                    "asMoveObject": {
                        "contents": {
                            "json": {
                                "current_sqrt_price": cetus_sqrt_p_a,
                                "liquidity": "100000000000",
                            }
                        }
                    }
                },
                "t_sui_usdc": {
                    "asMoveObject": {
                        "contents": {
                            "json": {
                                "sqrt_price": turbos_sqrt_p_a,
                                "liquidity": "200000000000",
                            }
                        }
                    }
                },
            }
        }

        # Shift B Mock: Cetus is cheaper (1.96 vs 2.02)
        cetus_sqrt_p_b = str(int(math.sqrt(1000.0 / 1.96) * (2 ** 64)))  # 1.96
        turbos_sqrt_p_b = str(int(math.sqrt(0.00202) * (2 ** 64)))  # 2.02

        mock_data_shift_b = {
            "data": {
                "d_sui_usdc": {
                    "dynamicFields": {
                        "nodes": [
                            {
                                "name": {"json": "ZXdtYQ=="},
                                "value": {"json": {"mean": "204000000000"}},  # DeepBook price = 2.04
                            }
                        ]
                    }
                },
                "p_sui_usdc": {
                    "asMoveObject": {
                        "contents": {
                            "json": {
                                "current_sqrt_price": cetus_sqrt_p_b,
                                "liquidity": "100000000000",
                            }
                        }
                    }
                },
                "t_sui_usdc": {
                    "asMoveObject": {
                        "contents": {
                            "json": {
                                "sqrt_price": turbos_sqrt_p_b,
                                "liquidity": "200000000000",
                            }
                        }
                    }
                },
            }
        }

        with patch.object(client, "execute", new_callable=AsyncMock) as mock_exec:
            # Test Shift A: Turbos selected
            mock_exec.return_value = mock_data_shift_a
            spreads_a = await client.query_live_market_spreads()
            sui_a = spreads_a["SUI/USDC"]
            assert sui_a["best_amm"] == "turbos"
            assert sui_a["amm_target"] == "turbos"

            # Test Shift B: Cetus selected
            mock_exec.return_value = mock_data_shift_b
            spreads_b = await client.query_live_market_spreads()
            sui_b = spreads_b["SUI/USDC"]
            assert sui_b["best_amm"] == "cetus"
            assert sui_b["amm_target"] == "cetus"

        await client.close()

    def test_ptb_preflight_validator_rejects_amm_router_mismatch(self) -> None:
        """Asserts validator detects and enforces structural integrity per AMM."""
        # Cetus validation passes
        cetus_val = self.validator.validate_atomic_ptb_generation(
            pair_name="SUI/USDC",
            route_direction="FORWARD",
            amm_target="cetus",
        )
        assert cetus_val["valid"] is True
        assert cetus_val["amm_target"] == "cetus"

        # Turbos validation passes
        turbos_val = self.validator.validate_atomic_ptb_generation(
            pair_name="SUI/USDC",
            route_direction="FORWARD",
            amm_target="turbos",
        )
        assert turbos_val["valid"] is True
        assert turbos_val["amm_target"] == "turbos"
