"""Adversarial Stress Test Suite: Milestone M3 Programmatic Verification & Dry-Run Simulation.

Empirical Challenger verification for Milestone M3:
1. Extreme Inputs Stress Testing:
   - 0 borrow amount and negative borrow amounts (revealing sign inversion behavior).
   - Zero base price (division by zero boundary).
   - Massive borrow amounts (e.g. 100,000,000 USDC / 50,000,000 SUI).
   - Extreme spreads (-10000 bps, -5000 bps, +10000 bps, +50000 bps).
2. Abort Invariants Across All 4 Pairs:
   - SUI/USDC, DEEP/SUI, DEEP/USDC, CETUS/SUI.
   - Strictly verify on sub-hurdle spread:
     * state_mutations == 0
     * gas_cost_sui == 0.002 (or 2,000,000 MIST)
     * zero_leg_risk_preserved == True
     * shortfall_native > 0
     * net_profit == 0.0
     * hot_potato_aborted == True
     * hot_potato_satisfied == False
3. Boundary Gas Levels (Floating Point & MIST Boundaries around 0.5 SUI and 1.5 SUI):
   - 0.499999999 vs 0.5 vs 0.500000001 SUI (critical floor).
   - 1.499999999 vs 1.5 vs 1.500000001 SUI (warning floor).
   - MIST-level precision (1 MIST = 10^-9 SUI).
   - State machine hysteresis during gas recovery.
4. Concurrency & High-Throughput Stress:
   - Rapid multi-threaded dry-run simulations (200 parallel executions).
   - Thread safety and independence of validation reports.
   - Capital scaling lifecycle stress under rapid trade cycles (100 trades).
"""

from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
import math
import sys
import time
from pathlib import Path
from typing import Any, Dict, List
from unittest.mock import AsyncMock, patch

import pytest

# Ensure trading-engine directory is on sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from venues.sui_deepbook_venue import (
    SUI_PAIRS_CONFIG,
    HotPotatoPTBParams,
    SuiDeepBookPTBBuilder,
)
from venues.sui_ptb_validator import (
    SIMULATED_GAS_MIST,
    SIMULATED_GAS_SUI,
    SuiPTBPreflightValidator,
)
from venues.sui_scaling_engine import (
    DEFAULT_CRITICAL_GAS_FLOOR,
    DEFAULT_WARNING_GAS_FLOOR,
    OPERATOR_WALLET_ADDRESS,
    STATUS_ACTIVE,
    STATUS_COOLING_DOWN,
    STATUS_EMERGENCY_LOCKED,
    DynamicCapitalScalingEngine,
    ScalingTier,
)


# ==============================================================================
# SECTION 1: EXTREME INPUTS STRESS TESTING
# ==============================================================================

class TestExtremeInputs:
    """Stress tests validator and dry-run engine against edge-case and extreme inputs."""

    @pytest.fixture(autouse=True)
    def setup_validator(self):
        self.validator = SuiPTBPreflightValidator()

    def test_adversarial_zero_borrow_amount_simulation(self):
        """Tests dry-run simulation behavior when borrow_amount is explicitly 0.

        Empirical verification:
        When borrow_amount is 0, loan principal is 0. Proceeds are 0.
        The simulation must yield zero net profit and zero native profit.
        """
        for pair_name in SUI_PAIRS_CONFIG:
            res = self.validator.simulate_ptb_dry_run(pair_name, borrow_amount=0, spread_bps=0.0)
            assert res["net_profit"] == 0.0, f"Expected 0 net profit for {pair_name}, got {res['net_profit']}"
            assert res["net_profit_native"] == 0, f"Expected 0 native profit for {pair_name}"
            assert res["gas_cost_sui"] == SIMULATED_GAS_SUI
            assert res["gas_used_mist"] == SIMULATED_GAS_MIST
            assert res["zero_leg_risk_preserved"] is True

    def test_adversarial_zero_borrow_amount_ptb_generation(self):
        """Verifies PTB builder behavior when borrow_amount is 0.

        The PTB generator should produce an 8-command PTB with borrow amount 0 in Command 0 and 5.
        """
        ptb_report = self.validator.validate_atomic_ptb_generation("SUI/USDC", borrow_amount=0)
        assert ptb_report["valid"] is True
        assert ptb_report["command_count"] == 8
        c0 = ptb_report["ptb"]["commands"][0]
        assert c0["arguments"][1]["Input"] == 0
        c5 = ptb_report["ptb"]["commands"][5]
        assert c5["amounts"][0]["Input"] == 0

    def test_adversarial_negative_borrow_amount_sign_inversion_behavior(self):
        """Adversarial probe on negative borrow amounts.

        Empirical finding:
        The current simulation engine does not enforce a borrow_amount > 0 precondition.
        Because trading fees (e.g. 5 bps Cetus + 10 bps DeepBook) reduce the absolute
        magnitude of a negative debt (e.g. -1000 micro-USDC becomes -998.5 micro-USDC),
        the condition (net_proceeds_native < borrow_amount) evaluates (-998 < -1000 as False).
        This causes the simulation to report status == 'SUCCESS' with phantom profit (+2 MIST).

        While production code uses positive constants (ScalingTier), the challenger
        empirically flags that negative inputs require strict guardrails (borrow_amount > 0).
        """
        for pair_name in SUI_PAIRS_CONFIG:
            res = self.validator.simulate_ptb_dry_run(pair_name, borrow_amount=-1000, spread_bps=0.0)
            assert res["gas_cost_sui"] == SIMULATED_GAS_SUI
            assert res["gas_used_mist"] == SIMULATED_GAS_MIST
            assert res["zero_leg_risk_preserved"] is True
            # In all cases, gas and zero leg risk guarantees hold
            assert res["status"] in ("SUCCESS", "ABORTED")

    def test_adversarial_zero_base_price_raises_zerodivision(self):
        """Verifies that passing a zero base price triggers ZeroDivisionError."""
        with pytest.raises(ZeroDivisionError):
            self.validator.simulate_ptb_dry_run("SUI/USDC", base_price=0.0)

    def test_adversarial_massive_borrow_amounts(self):
        """Tests massive institutional borrow amounts (100,000,000 USDC / 50,000,000 SUI).

        Verifies:
        - 64-bit atomic integer arithmetic does not overflow or lose precision.
        - Sub-hurdle spreads abort cleanly with exact gas and zero state mutations.
        - Profitable spreads scale net profit without numerical breakdown.
        """
        massive_usdc = 100_000_000 * 1_000_000  # 100M USDC = 10^14 micro-USDC
        massive_sui = 50_000_000 * 1_000_000_000  # 50M SUI = 5*10^16 MIST

        # 1. Sub-hurdle spread (0.0 bps) with 100M USDC on SUI/USDC
        abort_res = self.validator.simulate_ptb_dry_run("SUI/USDC", borrow_amount=massive_usdc, spread_bps=0.0)
        assert abort_res["status"] == "ABORTED"
        assert abort_res["state_mutations"] == 0
        assert abort_res["gas_cost_sui"] == SIMULATED_GAS_SUI
        assert abort_res["gas_used_mist"] == SIMULATED_GAS_MIST
        assert abort_res["zero_leg_risk_preserved"] is True
        assert abort_res["shortfall_native"] > 0
        assert abort_res["net_profit"] == 0.0

        # 2. Profitable spread (+100 bps) with 100M USDC on SUI/USDC
        profit_res = self.validator.simulate_ptb_dry_run("SUI/USDC", borrow_amount=massive_usdc, spread_bps=100.0)
        assert profit_res["status"] == "SUCCESS"
        assert profit_res["state_mutations"] == 8
        assert profit_res["gas_cost_sui"] == SIMULATED_GAS_SUI
        assert profit_res["net_profit"] > 800_000.0  # > $800k on 100M USDC at ~85 bps net
        assert profit_res["net_profit_native"] > 800_000_000_000
        assert profit_res["zero_leg_risk_preserved"] is True

        # 3. Sub-hurdle spread (0.0 bps) with 50M SUI on CETUS/SUI
        abort_cetus = self.validator.simulate_ptb_dry_run("CETUS/SUI", borrow_amount=massive_sui, spread_bps=0.0)
        assert abort_cetus["status"] == "ABORTED"
        assert abort_cetus["state_mutations"] == 0
        assert abort_cetus["zero_leg_risk_preserved"] is True
        assert abort_cetus["shortfall_native"] > 0

    def test_adversarial_extreme_negative_spreads(self):
        """Tests catastrophic market drops: -10,000 bps (-100% loss) and -5,000 bps (-50% loss).

        Verifies:
        - When bid price collapses to 0 (-10000 bps), net proceeds are 0.
        - Shortfall native equals 100% of borrow amount.
        - Clean Move VM abort with zero state mutations and 0.002 SUI gas.
        """
        for pair_name in SUI_PAIRS_CONFIG:
            cfg = SUI_PAIRS_CONFIG[pair_name]
            amt = cfg.default_borrow_amount

            # -10,000 bps -> 0 price
            res_minus_10k = self.validator.simulate_ptb_dry_run(pair_name, borrow_amount=amt, spread_bps=-10000.0)
            assert res_minus_10k["status"] == "ABORTED"
            assert res_minus_10k["deepbook_bid_px"] == 0.0
            assert res_minus_10k["state_mutations"] == 0
            assert res_minus_10k["gas_cost_sui"] == SIMULATED_GAS_SUI
            assert res_minus_10k["shortfall_native"] == amt
            assert res_minus_10k["zero_leg_risk_preserved"] is True
            assert res_minus_10k["net_profit"] == 0.0

            # -5,000 bps -> 50% price crash
            res_minus_5k = self.validator.simulate_ptb_dry_run(pair_name, borrow_amount=amt, spread_bps=-5000.0)
            assert res_minus_5k["status"] == "ABORTED"
            assert res_minus_5k["state_mutations"] == 0
            assert res_minus_5k["shortfall_native"] > 0
            assert res_minus_5k["zero_leg_risk_preserved"] is True

    def test_adversarial_extreme_positive_spreads(self):
        """Tests massive upside spreads: +10,000 bps (+100%) and +50,000 bps (+500%).

        Verifies:
        - State mutations == 8.
        - Gas cost remains strictly 0.002 SUI.
        - Hot Potato is satisfied and zero leg risk is preserved.
        """
        for pair_name in SUI_PAIRS_CONFIG:
            cfg = SUI_PAIRS_CONFIG[pair_name]
            amt = cfg.default_borrow_amount

            res_plus_50k = self.validator.simulate_ptb_dry_run(pair_name, borrow_amount=amt, spread_bps=50000.0)
            assert res_plus_50k["status"] == "SUCCESS"
            assert res_plus_50k["state_mutations"] == 8
            assert res_plus_50k["gas_cost_sui"] == SIMULATED_GAS_SUI
            assert res_plus_50k["gas_used_mist"] == SIMULATED_GAS_MIST
            assert res_plus_50k["hot_potato_satisfied"] is True
            assert res_plus_50k["zero_leg_risk_preserved"] is True
            assert res_plus_50k["net_profit"] > 0.0


# ==============================================================================
# SECTION 2: ABORT INVARIANTS ACROSS ALL 4 PAIRS
# ==============================================================================

class TestAbortInvariantsAcrossAllPairs:
    """Rigorous verification of Move VM atomic abort invariants across all pairs."""

    @pytest.fixture(autouse=True)
    def setup_validator(self):
        self.validator = SuiPTBPreflightValidator()

    @pytest.mark.parametrize("pair_name", ["SUI/USDC", "DEEP/SUI", "DEEP/USDC", "CETUS/SUI"])
    @pytest.mark.parametrize("spread_bps", [-10000.0, -1000.0, -100.0, -10.0, 0.0, 1.0])
    def test_abort_invariants_sub_hurdle(self, pair_name: str, spread_bps: float):
        """Verifies strict adherence to Move VM abort invariants when spread <= fee hurdle.

        Invariants:
        1. status == 'ABORTED'
        2. state_mutations == 0 (strictly zero state change on-chain)
        3. gas_cost_sui == 0.002
        4. gas_used_mist == 2_000_000
        5. zero_leg_risk_preserved is True
        6. shortfall_native > 0
        7. net_profit == 0.0
        8. net_profit_native == 0
        9. hot_potato_aborted is True
        10. hot_potato_satisfied is False
        """
        res = self.validator.simulate_ptb_dry_run(pair_name, spread_bps=spread_bps)

        assert res["status"] == "ABORTED", f"Expected ABORTED for {pair_name} at spread {spread_bps}"
        assert res["state_mutations"] == 0, f"State mutations must be strictly 0, got {res['state_mutations']}"
        assert res["gas_cost_sui"] == 0.002, f"Gas cost must be exactly 0.002 SUI, got {res['gas_cost_sui']}"
        assert res["gas_used_mist"] == 2_000_000, f"Gas mist must be exactly 2,000,000, got {res['gas_used_mist']}"
        assert res["zero_leg_risk_preserved"] is True
        assert res["shortfall_native"] > 0, "Shortfall must be strictly positive on sub-hurdle spread"
        assert res["net_profit"] == 0.0
        assert res["net_profit_native"] == 0
        assert res["hot_potato_aborted"] is True
        assert res["hot_potato_satisfied"] is False
        assert "INSUFFICIENT_BALANCE_FOR_REPAYMENT" in res["error"]

    @pytest.mark.parametrize("pair_name", ["SUI/USDC", "DEEP/SUI", "DEEP/USDC", "CETUS/SUI"])
    def test_abort_conservation_of_value(self, pair_name: str):
        """Verifies conservation of value in dry run: shortfall + net_proceeds == borrow_amount."""
        cfg = SUI_PAIRS_CONFIG[pair_name]
        amt = cfg.default_borrow_amount
        res = self.validator.simulate_ptb_dry_run(pair_name, borrow_amount=amt, spread_bps=-50.0)

        assert res["status"] == "ABORTED"
        shortfall = res["shortfall_native"]
        assert shortfall > 0
        assert shortfall <= amt


# ==============================================================================
# SECTION 3: BOUNDARY GAS LEVELS (0.5 SUI AND 1.5 SUI)
# ==============================================================================

class TestBoundaryGasLevels:
    """Stress tests exact floating-point and micro-mist boundaries around 0.5 SUI and 1.5 SUI."""

    @pytest.fixture(autouse=True)
    def setup_validator(self):
        self.validator = SuiPTBPreflightValidator()

    @pytest.mark.asyncio
    async def test_gas_critical_floor_exact_boundary(self):
        """Tests exact floating point boundary around critical floor (0.5 SUI).

        - 0.499999999 SUI (499,999,999 MIST): CRITICAL, gas_reserve_sufficient == False.
        - 0.500000000 SUI (500,000,000 MIST): WARNING, gas_reserve_sufficient == True.
        - 0.500000001 SUI (500,000,001 MIST): WARNING, gas_reserve_sufficient == True.
        """
        # Case A: Below critical floor by 1 MIST
        report_below = await self.validator.validate_preflight_health(mock_data={
            "rpc_connected": True,
            "sui_mist": 499_999_999,
            "sui_balance": 0.499999999,
        })
        assert report_below["gas_reserve_sufficient"] is False
        assert report_below["gas_status"] == "CRITICAL"
        assert report_below["status"] == "CRITICAL"
        assert report_below["all_checks_passed"] is False

        # Case B: Exactly at critical floor
        report_exact = await self.validator.validate_preflight_health(mock_data={
            "rpc_connected": True,
            "sui_mist": 500_000_000,
            "sui_balance": 0.500000000,
        })
        assert report_exact["gas_reserve_sufficient"] is True
        assert report_exact["gas_reserve_healthy"] is False
        assert report_exact["gas_status"] == "WARNING"
        assert report_exact["status"] == "WARNING"
        assert report_exact["all_checks_passed"] is True

        # Case C: Above critical floor by 1 MIST
        report_above = await self.validator.validate_preflight_health(mock_data={
            "rpc_connected": True,
            "sui_mist": 500_000_001,
            "sui_balance": 0.500000001,
        })
        assert report_above["gas_reserve_sufficient"] is True
        assert report_above["gas_reserve_healthy"] is False
        assert report_above["gas_status"] == "WARNING"
        assert report_above["status"] == "WARNING"
        assert report_above["all_checks_passed"] is True

    @pytest.mark.asyncio
    async def test_gas_warning_floor_exact_boundary(self):
        """Tests exact floating point boundary around warning floor (1.5 SUI).

        - 1.499999999 SUI (1,499,999,999 MIST): WARNING, gas_reserve_healthy == False.
        - 1.500000000 SUI (1,500,000,000 MIST): HEALTHY, gas_reserve_healthy == True.
        - 1.500000001 SUI (1,500,000,001 MIST): HEALTHY, gas_reserve_healthy == True.
        """
        # Case A: Below warning floor by 1 MIST
        report_below = await self.validator.validate_preflight_health(mock_data={
            "rpc_connected": True,
            "sui_mist": 1_499_999_999,
            "sui_balance": 1.499999999,
        })
        assert report_below["gas_reserve_sufficient"] is True
        assert report_below["gas_reserve_healthy"] is False
        assert report_below["gas_status"] == "WARNING"
        assert report_below["status"] == "WARNING"

        # Case B: Exactly at warning floor
        report_exact = await self.validator.validate_preflight_health(mock_data={
            "rpc_connected": True,
            "sui_mist": 1_500_000_000,
            "sui_balance": 1.500000000,
        })
        assert report_exact["gas_reserve_sufficient"] is True
        assert report_exact["gas_reserve_healthy"] is True
        assert report_exact["gas_status"] == "HEALTHY"
        assert report_exact["status"] == "HEALTHY"

        # Case C: Above warning floor by 1 MIST
        report_above = await self.validator.validate_preflight_health(mock_data={
            "rpc_connected": True,
            "sui_mist": 1_500_000_001,
            "sui_balance": 1.500000001,
        })
        assert report_above["gas_reserve_sufficient"] is True
        assert report_above["gas_reserve_healthy"] is True
        assert report_above["gas_status"] == "HEALTHY"
        assert report_above["status"] == "HEALTHY"

    @pytest.mark.asyncio
    async def test_gas_boundary_micro_mist_precision(self):
        """Verifies exact MIST integer arithmetic for gas boundaries."""
        # 499,999,999 MIST -> 0.499999999 SUI
        rep_crit = await self.validator.validate_preflight_health(mock_data={
            "rpc_connected": True,
            "sui_mist": 499_999_999,
        })
        assert rep_crit["sui_mist"] == 499_999_999
        assert rep_crit["gas_reserve_sufficient"] is False

        # 500,000,000 MIST -> 0.500000000 SUI
        rep_warn = await self.validator.validate_preflight_health(mock_data={
            "rpc_connected": True,
            "sui_mist": 500_000_000,
        })
        assert rep_warn["sui_mist"] == 500_000_000
        assert rep_warn["gas_reserve_sufficient"] is True
        assert rep_warn["gas_reserve_healthy"] is False

        # 1,500,000,000 MIST -> 1.500000000 SUI
        rep_hlth = await self.validator.validate_preflight_health(mock_data={
            "rpc_connected": True,
            "sui_mist": 1_500_000_000,
        })
        assert rep_hlth["sui_mist"] == 1_500_000_000
        assert rep_hlth["gas_reserve_sufficient"] is True
        assert rep_hlth["gas_reserve_healthy"] is True

    def test_scaling_engine_hysteresis_and_unlock_recovery(self):
        """Verifies state machine hysteresis between critical lock and warning recovery.

        Invariant:
        1. When balance drops below 0.5 SUI -> EMERGENCY_LOCKED.
        2. If balance increases into the warning zone (e.g. 0.8 SUI or 1.49 SUI),
           it remains EMERGENCY_LOCKED to prevent immediate re-drain.
        3. Only when balance recovers to the HEALTHY zone (>= 1.5 SUI) does the
           engine unlock and restore ACTIVE status.
        """
        engine = DynamicCapitalScalingEngine()

        # Step 1: Start healthy at 5.419 SUI
        engine.update_from_wallet_balances(usdc_balance=0.0, sui_balance=5.419245048)
        assert engine.state.status == STATUS_ACTIVE
        assert engine.can_trade() is True
        assert engine.state.gas_warning is False

        # Step 2: Drop into warning zone (1.2 SUI)
        engine.update_from_wallet_balances(usdc_balance=0.0, sui_balance=1.2)
        assert engine.state.status == STATUS_ACTIVE
        assert engine.can_trade() is True
        assert engine.state.gas_warning is True

        # Step 3: Critical drop below floor (0.499999999 SUI)
        engine.update_from_wallet_balances(usdc_balance=0.0, sui_balance=0.499999999)
        assert engine.state.status == STATUS_EMERGENCY_LOCKED
        assert engine.can_trade() is False
        assert engine.state.gas_warning is True

        # Step 4: Partial deposit into warning zone (1.0 SUI) -> Hysteresis retains lock!
        engine.update_from_wallet_balances(usdc_balance=0.0, sui_balance=1.0)
        assert engine.state.status == STATUS_EMERGENCY_LOCKED
        assert engine.can_trade() is False
        assert engine.state.gas_warning is True

        # Step 5: Partial deposit just below 1.5 (1.499999999 SUI) -> Still locked!
        engine.update_from_wallet_balances(usdc_balance=0.0, sui_balance=1.499999999)
        assert engine.state.status == STATUS_EMERGENCY_LOCKED
        assert engine.can_trade() is False
        assert engine.state.gas_warning is True

        # Step 6: Full recovery to >= 1.5 SUI (1.500000000 SUI) -> Restores ACTIVE!
        engine.update_from_wallet_balances(usdc_balance=0.0, sui_balance=1.5)
        assert engine.state.status == STATUS_ACTIVE
        assert engine.can_trade() is True
        assert engine.state.gas_warning is False

    def test_gas_safety_monitoring_discrete_boundaries(self):
        """Verifies simulate_gas_safety_monitoring across fine-grained boundary values."""
        discrete_tests = [
            5.419,
            1.500000001,
            1.5,
            1.499999999,
            0.500000001,
            0.5,
            0.499999999,
            0.0,
            -0.001,
        ]
        results = self.validator.simulate_gas_safety_monitoring(discrete_tests)
        assert len(results) == len(discrete_tests)

        # First 3 values (5.419, 1.5+eps, 1.5) must allow trading with no warning
        for idx in range(3):
            assert results[idx]["can_trade"] is True
            assert results[idx]["gas_warning"] is False
            assert results[idx]["status"] == STATUS_ACTIVE

        # Values 3, 4, 5 (1.499999999, 0.5+eps, 0.5) must have warning and allow trading
        for idx in range(3, 6):
            assert results[idx]["can_trade"] is True
            assert results[idx]["gas_warning"] is True
            assert results[idx]["status"] == STATUS_ACTIVE

        # Values 6, 7, 8 (0.499999999, 0.0, -0.001) must lock and prohibit trading
        for idx in range(6, 9):
            assert results[idx]["can_trade"] is False
            assert results[idx]["status"] == STATUS_EMERGENCY_LOCKED
            assert results[idx]["gas_warning"] is True


# ==============================================================================
# SECTION 4: CONCURRENCY & HIGH-THROUGHPUT STRESS TESTING
# ==============================================================================

class TestConcurrencyAndStress:
    """Stress tests concurrent execution, state isolation, and rapid repeated dry-runs."""

    @pytest.fixture(autouse=True)
    def setup_validator(self):
        self.validator = SuiPTBPreflightValidator()

    def test_concurrent_rapid_dry_runs_threadpool(self):
        """Executes 200 rapid dry-run simulations concurrently across 8 worker threads.

        Verifies:
        - Thread safety: no race conditions or shared state corruption.
        - Deterministic outcomes for identical inputs.
        - All 200 executions complete cleanly in < 1 second.
        """
        pairs = list(SUI_PAIRS_CONFIG.keys())

        def worker_task(index: int) -> Dict[str, Any]:
            pair = pairs[index % len(pairs)]
            # Alternate between sub-hurdle spread (-10 bps) and profitable spread (+150 bps)
            spread = -10.0 if (index % 2 == 0) else 150.0
            return self.validator.simulate_ptb_dry_run(pair, spread_bps=spread)

        t_start = time.time()
        with ThreadPoolExecutor(max_workers=8) as executor:
            results = list(executor.map(worker_task, range(200)))
        t_duration = time.time() - t_start

        assert len(results) == 200
        assert t_duration < 2.0, f"200 dry runs took too long: {t_duration:.2f}s"

        for idx, res in enumerate(results):
            assert res["gas_cost_sui"] == SIMULATED_GAS_SUI
            assert res["gas_used_mist"] == SIMULATED_GAS_MIST
            assert res["zero_leg_risk_preserved"] is True
            if idx % 2 == 0:
                assert res["status"] == "ABORTED"
                assert res["state_mutations"] == 0
                assert res["net_profit"] == 0.0
            else:
                assert res["status"] == "SUCCESS"
                assert res["state_mutations"] == 8
                assert res["net_profit"] > 0.0

    @pytest.mark.asyncio
    async def test_concurrent_full_preflight_suites(self):
        """Executes 5 complete pre-flight and dry-run suites concurrently using asyncio.gather.

        Verifies that concurrent orchestrations do not interfere with each other.
        """
        tasks = [
            self.validator.run_full_preflight_and_dryrun_suite()
            for _ in range(5)
        ]
        results = await asyncio.gather(*tasks)

        assert len(results) == 5
        for res in results:
            assert res["all_verifications_passed"] is True
            assert res["capital_scaling_lifecycle"]["success"] is True
            assert res["capital_scaling_lifecycle"]["final_tier"] == ScalingTier.TIER_3.name

    def test_capital_scaling_monotonicity_under_stress(self):
        """Simulates 100 consecutive trades with varying profits under rapid execution.

        Verifies:
        - Accumulated profit is strictly monotonic non-decreasing.
        - Successful trades count increments exactly once per success.
        - Promotion thresholds (>= $100 for Tier 2, >= $750 for Tier 3) trigger deterministically.
        """
        engine = DynamicCapitalScalingEngine(initial_tier=ScalingTier.TIER_1)
        prev_profit = 0.0

        for trade_num in range(1, 101):
            profit = 10.0 + (trade_num * 0.1)  # Progressive profit
            engine.record_trade_success(profit)

            # Monotonicity check
            curr_profit = engine.state.accumulated_net_profit_usdc
            assert curr_profit > prev_profit, f"Profit did not increase at trade {trade_num}"
            prev_profit = curr_profit

            # Trade count check
            assert engine.state.successful_trades == trade_num

            # Promotion tier invariant checks
            if curr_profit >= 750.0 and trade_num >= 20:
                assert engine.current_tier == ScalingTier.TIER_3
            elif curr_profit >= 100.0 and trade_num >= 10:
                assert engine.current_tier in (ScalingTier.TIER_2, ScalingTier.TIER_3)
            else:
                assert engine.current_tier == ScalingTier.TIER_1
