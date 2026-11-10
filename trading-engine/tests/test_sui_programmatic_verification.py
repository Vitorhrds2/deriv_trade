"""Automated Test Suite for Programmatic Verification & Dry-Run Simulation (Milestone M3).

Requirement R4 Verification:
1. Preflight health checks with live or mock Sui GraphQL RPC (connectivity, operator gas runway >= 0.5 SUI,
   pool accessibility across all 4 pairs, and BalanceManager configuration).
2. PTB generation across all 4 pairs (SUI/USDC, DEEP/SUI, DEEP/USDC, CETUS/SUI) with 1k, 5k, and 10k USDC amounts.
3. Dry-run simulation: clean Move VM abort on sub-hurdle spread with ~0.002 SUI gas (~2,000,000 MIST).
4. Dry-run simulation: successful profit extraction on positive spread (> fees) with zero leg risk preserved.
5. Dynamic capital scaling lifecycle through simulated trades (Tier 1 -> Tier 2 -> Tier 3).
6. Gas safety warning (1.5 SUI) and critical stop (0.5 SUI) during simulation.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Ensure trading-engine directory is on sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from venues.sui_deepbook_venue import (
    CETUS_POOL_CETUS_SUI,
    CETUS_POOL_DEEP_SUI,
    CETUS_POOL_DEEP_USDC,
    CETUS_POOL_SUI_USDC,
    CETUS_SUI_POOL_ID,
    CIRCLE_USDC_TYPE,
    DEEP_SUI_POOL_ID,
    DEEP_USDC_POOL_ID,
    DEEPBOOK_PACKAGE_ID,
    SUI_COIN_TYPE,
    SUI_PAIRS_CONFIG,
    SUI_USDC_POOL_ID,
    SuiGraphQLClient,
)
from venues.sui_ptb_validator import (
    SIMULATED_GAS_MIST,
    SIMULATED_GAS_SUI,
    CapitalScalingLifecycleReport,
    PTBDryRunReport,
    PTBValidationReport,
    PreflightHealthReport,
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
# 1. PRE-FLIGHT HEALTHCHECK TESTS (RPC, WALLET GAS, POOLS, BALANCE MANAGER)
# ==============================================================================

@pytest.mark.asyncio
async def test_preflight_health_live_or_mock_rpc():
    """Validates preflight healthcheck against live GraphQL RPC or mock fallback.

    Verifies:
    - RPC connectivity is validated.
    - Operator wallet (0x5621a8e7...) has >= 0.5 SUI gas reserve (reports 5.419 SUI on mainnet).
    - Pool object accessibility is verified for all 4 pairs:
      SUI/USDC, DEEP/SUI, DEEP/USDC, CETUS/SUI.
    - BalanceManager configuration is validated.
    - Returns overall status HEALTHY with all_checks_passed == True.
    """
    validator = SuiPTBPreflightValidator()
    try:
        health = await validator.validate_preflight_health()
        assert isinstance(health, dict)
        assert health["operator_address"] == OPERATOR_WALLET_ADDRESS
        assert health["balance_manager_valid"] is True

        # Check gas reserve: operator wallet has 5.419245048 SUI on mainnet
        if health["rpc_connected"]:
            assert health["sui_balance"] >= 0.5, "Gas reserve must be >= 0.5 SUI"
            assert health["sui_balance"] >= 1.5, "Operator wallet has >= 1.5 SUI runway"
            assert health["gas_reserve_sufficient"] is True
            assert health["gas_reserve_healthy"] is True
            assert health["gas_status"] == "HEALTHY"
            assert health["all_pools_accessible"] is True
            assert health["all_checks_passed"] is True
            assert health["status"] == "HEALTHY"

            # Verify pool details for all 4 pairs
            for pair_name in ["SUI/USDC", "DEEP/SUI", "DEEP/USDC", "CETUS/SUI"]:
                assert pair_name in health["pools"]
                p_info = health["pools"][pair_name]
                assert p_info["accessible"] is True
                assert p_info["deepbook_pool_id"] == SUI_PAIRS_CONFIG[pair_name].deepbook_pool_id
                assert p_info["cetus_pool_id"] == SUI_PAIRS_CONFIG[pair_name].cetus_pool_id
        else:
            # If network is unavailable during CI, test mock mode
            mock_health = await validator.validate_preflight_health(mock_data={
                "rpc_connected": True,
                "sui_mist": 5_419_245_048,
                "sui_balance": 5.419245048,
                "usdc_raw": 0,
                "usdc_balance": 0.0,
            })
            assert mock_health["sui_balance"] == 5.419245048
            assert mock_health["gas_reserve_sufficient"] is True
            assert mock_health["all_checks_passed"] is True
            assert mock_health["status"] == "HEALTHY"
    finally:
        await validator.close()


@pytest.mark.asyncio
async def test_preflight_health_mock_insufficient_gas_critical():
    """Validates preflight fails when SUI gas balance drops below 0.5 SUI critical floor."""
    validator = SuiPTBPreflightValidator()
    try:
        report = await validator.validate_preflight_health(mock_data={
            "rpc_connected": True,
            "sui_mist": 450_000_000,
            "sui_balance": 0.45,
            "usdc_raw": 0,
            "usdc_balance": 0.0,
        })
        assert report["sui_balance"] == 0.45
        assert report["gas_reserve_sufficient"] is False
        assert report["gas_reserve_healthy"] is False
        assert report["gas_status"] == "CRITICAL"
        assert report["status"] == "CRITICAL"
        assert report["all_checks_passed"] is False
    finally:
        await validator.close()


@pytest.mark.asyncio
async def test_preflight_health_mock_gas_warning_level():
    """Validates preflight enters WARNING when SUI balance is between 0.5 and 1.5 SUI."""
    validator = SuiPTBPreflightValidator()
    try:
        report = await validator.validate_preflight_health(mock_data={
            "rpc_connected": True,
            "sui_mist": 1_200_000_000,
            "sui_balance": 1.2,
            "usdc_raw": 0,
            "usdc_balance": 0.0,
        })
        assert report["sui_balance"] == 1.2
        assert report["gas_reserve_sufficient"] is True
        assert report["gas_reserve_healthy"] is False
        assert report["gas_status"] == "WARNING"
        assert report["status"] == "WARNING"
        assert report["all_checks_passed"] is True
    finally:
        await validator.close()


@pytest.mark.asyncio
async def test_preflight_health_mock_missing_pool_fails():
    """Validates preflight detects inaccessible or unconfigured pool objects."""
    validator = SuiPTBPreflightValidator()
    try:
        mock_pools = {
            "SUI/USDC": {"deepbook_pool_id": SUI_USDC_POOL_ID, "cetus_pool_id": CETUS_POOL_SUI_USDC, "accessible": True},
            "DEEP/SUI": {"deepbook_pool_id": DEEP_SUI_POOL_ID, "cetus_pool_id": CETUS_POOL_DEEP_SUI, "accessible": False},  # Failed
            "DEEP/USDC": {"deepbook_pool_id": DEEP_USDC_POOL_ID, "cetus_pool_id": CETUS_POOL_DEEP_USDC, "accessible": True},
            "CETUS/SUI": {"deepbook_pool_id": CETUS_SUI_POOL_ID, "cetus_pool_id": CETUS_POOL_CETUS_SUI, "accessible": True},
        }
        report = await validator.validate_preflight_health(mock_data={
            "rpc_connected": True,
            "sui_mist": 5_419_245_048,
            "sui_balance": 5.419,
            "pools": mock_pools,
        })
        assert report["all_pools_accessible"] is False
        assert report["all_checks_passed"] is False
        assert report["status"] == "FAILED"
    finally:
        await validator.close()


@pytest.mark.asyncio
async def test_preflight_health_invalid_balance_manager():
    """Validates preflight detects missing or malformed BalanceManager ID."""
    validator = SuiPTBPreflightValidator(balance_manager_id="")
    try:
        report = await validator.validate_preflight_health(mock_data={
            "rpc_connected": True,
            "sui_balance": 5.419,
        })
        assert report["balance_manager_valid"] is False
        assert report["all_checks_passed"] is False
    finally:
        await validator.close()


# ==============================================================================
# 2. ATOMIC PTB GENERATION & STRUCTURE VERIFICATION (4 PAIRS x 1k, 5k, 10k)
# ==============================================================================

@pytest.mark.parametrize("pair_name", ["SUI/USDC", "DEEP/SUI", "DEEP/USDC", "CETUS/SUI"])
@pytest.mark.parametrize("borrow_amount", [1_000_000_000, 5_000_000_000, 10_000_000_000])
def test_atomic_ptb_generation_all_pairs_and_tranches(pair_name: str, borrow_amount: int):
    """Validates 8-command atomic PTB construction across all 4 pairs and scaling tranches.

    Verifies:
    - Exactly 8 commands in strict Move execution sequence.
    - Command 0: borrow_flashloan_quote producing Hot Potato receipt.
    - Command 1: swap on Cetus CLMM with exact pair pool ID and a2b direction.
    - Command 2: deposit to BalanceManager.
    - Command 3: place_market_order (is_bid = False) on DeepBook.
    - Command 4: withdraw_all from BalanceManager.
    - Command 5: SplitCoins exact repayment principal.
    - Command 6: return_flashloan_quote consuming repayment coin and Hot Potato receipt.
    - Command 7: TransferObjects net profit to operator address.
    """
    validator = SuiPTBPreflightValidator()
    report = validator.validate_atomic_ptb_generation(pair_name=pair_name, borrow_amount=borrow_amount)

    assert report["valid"] is True, f"PTB validation failed: {report['errors']}"
    assert report["pair_name"] == pair_name
    assert report["borrow_amount"] == borrow_amount
    assert report["command_count"] == 8
    assert report["strict_sequence_verified"] is True
    assert report["hot_potato_borrow_linked"] is True
    assert report["hot_potato_repay_linked"] is True
    assert report["hot_potato_quenched"] is True
    assert report["pool_id_verified"] is True
    assert report["cetus_pool_id_verified"] is True
    assert report["a2b_verified"] is True
    assert report["balance_manager_verified"] is True

    # Validate PTB payload invariants
    ptb = report["ptb"]
    assert ptb["pair"] == pair_name
    assert ptb["borrow_amount"] == borrow_amount
    assert ptb["sender"] == OPERATOR_WALLET_ADDRESS
    assert len(ptb["commands"]) == 8

    # Verify a2b flag matches pair configuration
    expected_a2b = SUI_PAIRS_CONFIG[pair_name].a2b
    assert ptb["a2b"] == expected_a2b

    # Verify Command 1 (swap) inputs
    c1 = ptb["commands"][1]
    assert c1["arguments"][1]["Input"] == SUI_PAIRS_CONFIG[pair_name].cetus_pool_id
    assert c1["arguments"][3]["Input"] == expected_a2b

    # Verify Command 5 (SplitCoins) amount
    c5 = ptb["commands"][5]
    assert c5["amounts"][0]["Input"] == borrow_amount

    # Verify Command 6 (Hot Potato quench) consumes [0, 1] receipt
    c6 = ptb["commands"][6]
    assert c6["arguments"][2]["NestedResult"] == [0, 1]


def test_atomic_ptb_generation_invalid_pair_raises_error():
    """Validates that requesting an unsupported pair raises ValueError."""
    validator = SuiPTBPreflightValidator()
    with pytest.raises(ValueError, match="Unknown pair"):
        validator.validate_atomic_ptb_generation("BTC/USDC")


# ==============================================================================
# 3. DRY-RUN SIMULATION TESTS (SUB-HURDLE ABORT VS PROFIT EXTRACTION)
# ==============================================================================

@pytest.mark.parametrize("pair_name", ["SUI/USDC", "DEEP/SUI", "DEEP/USDC", "CETUS/SUI"])
def test_dry_run_simulation_sub_hurdle_aborts_cleanly(pair_name: str):
    """Validates that zero or sub-hurdle spread causes Move VM SplitCoins abort with minimal gas.

    Verifies:
    - status == "ABORTED"
    - gas_cost_sui == 0.002 SUI (~2,000,000 MIST)
    - zero_leg_risk_preserved == True
    - state_mutations == 0 (no lingering debt, no partial state mutations)
    - net_profit == 0.0
    - shortfall_native > 0
    - hot_potato_aborted == True
    """
    validator = SuiPTBPreflightValidator()
    # 0 spread bps is strictly below the fee hurdle for all 4 pairs
    sim = validator.simulate_ptb_dry_run(pair_name=pair_name, spread_bps=0.0)

    assert sim["status"] == "ABORTED"
    assert sim["gas_cost_sui"] == SIMULATED_GAS_SUI
    assert sim["gas_used_mist"] == SIMULATED_GAS_MIST
    assert sim["zero_leg_risk_preserved"] is True
    assert sim["state_mutations"] == 0
    assert sim["net_profit"] == 0.0
    assert sim["net_profit_native"] == 0
    assert sim["shortfall_native"] > 0
    assert sim["hot_potato_aborted"] is True
    assert sim["hot_potato_satisfied"] is False
    assert "INSUFFICIENT_BALANCE_FOR_REPAYMENT" in sim["error"]


@pytest.mark.parametrize("pair_name", ["SUI/USDC", "DEEP/SUI", "DEEP/USDC", "CETUS/SUI"])
def test_dry_run_simulation_profitable_spread_succeeds(pair_name: str):
    """Validates that positive spread exceeding fee hurdles succeeds with profit extraction.

    Verifies:
    - status == "SUCCESS"
    - net_profit > 0
    - zero_leg_risk_preserved == True
    - gas_cost_sui == 0.002 SUI
    - state_mutations == 8
    - hot_potato_satisfied == True
    - shortfall_native == 0
    """
    validator = SuiPTBPreflightValidator()
    # 100 bps (1.00%) spread is strictly greater than fee hurdles across all 4 pairs
    # (SUI/USDC: 15 bps, DEEP/SUI: 5 bps, DEEP/USDC: 5 bps, CETUS/SUI: 35 bps)
    sim = validator.simulate_ptb_dry_run(pair_name=pair_name, spread_bps=100.0)

    assert sim["status"] == "SUCCESS"
    assert sim["net_profit"] > 0.0
    assert sim["net_profit_quote"] == sim["net_profit"]
    assert sim["net_profit_native"] > 0
    assert sim["zero_leg_risk_preserved"] is True
    assert sim["gas_cost_sui"] == SIMULATED_GAS_SUI
    assert sim["gas_used_mist"] == SIMULATED_GAS_MIST
    assert sim["state_mutations"] == 8
    assert sim["hot_potato_satisfied"] is True
    assert sim["hot_potato_aborted"] is False
    assert sim["shortfall_native"] == 0
    assert sim["error"] is None


def test_dry_run_simulation_slippage_spectrum_sui_usdc():
    """Validates sharp step-function transition around the 15 bps fee hurdle for SUI/USDC.

    Hurdle: Cetus (5 bps) + DeepBook (10 bps) = 15 bps total.
    - Spreads <= 15 bps MUST abort cleanly with state_mutations == 0 and gas == 0.002 SUI.
    - Spreads > 15 bps MUST succeed with net_profit > 0 and state_mutations == 8.
    """
    validator = SuiPTBPreflightValidator()

    # Sub-hurdle spreads
    for spread in [-50.0, -10.0, 0.0, 5.0, 10.0, 14.0]:
        sim = validator.simulate_ptb_dry_run("SUI/USDC", spread_bps=spread)
        assert sim["status"] == "ABORTED", f"Expected ABORT at {spread} bps spread"
        assert sim["zero_leg_risk_preserved"] is True
        assert sim["state_mutations"] == 0
        assert sim["gas_cost_sui"] == 0.002

    # Profitable spreads
    for spread in [25.0, 50.0, 100.0, 200.0]:
        sim = validator.simulate_ptb_dry_run("SUI/USDC", spread_bps=spread)
        assert sim["status"] == "SUCCESS", f"Expected SUCCESS at {spread} bps spread"
        assert sim["zero_leg_risk_preserved"] is True
        assert sim["state_mutations"] == 8
        assert sim["net_profit"] > 0.0


# ==============================================================================
# 4. DYNAMIC CAPITAL SCALING LIFECYCLE SIMULATION (1k -> 5k -> 10k)
# ==============================================================================

def test_capital_scaling_lifecycle_end_to_end():
    """Validates end-to-end operational capital scaling lifecycle:

    1. Starts at Tier 1 (1,000 USDC / 1_000_000_000).
    2. Accumulates net profits through successful dry-runs.
    3. Triggers promotion to Tier 2 (5,000 USDC) upon reaching >= $100 profit and >= 10 trades.
    4. Continues accumulating profit at 5,000 USDC tranche.
    5. Triggers promotion to Tier 3 (10,000 USDC) upon reaching >= $750 cumulative profit and >= 20 trades.
    6. Confirms zero leg risk is preserved across every lifecycle step.
    """
    validator = SuiPTBPreflightValidator()
    lifecycle = validator.simulate_capital_scaling_lifecycle(
        initial_tier=ScalingTier.TIER_1,
        spread_bps_tier1=135.0,  # yields ~$12.00 / trade on 1k USDC
        spread_bps_tier2=150.0,  # yields ~$67.50 / trade on 5k USDC
        pair_name="SUI/USDC",
    )

    assert lifecycle["success"] is True
    assert lifecycle["initial_tier"] == ScalingTier.TIER_1.name
    assert lifecycle["initial_borrow_amount"] == 1_000_000_000

    # Tier 2 Promotion Check
    assert lifecycle["promoted_to_tier_2_at_trade"] is not None
    assert lifecycle["promoted_to_tier_2_at_trade"] >= 10
    assert lifecycle["tier_2_profit_at_promotion"] >= 100.0

    # Tier 3 Promotion Check
    assert lifecycle["promoted_to_tier_3_at_trade"] is not None
    assert lifecycle["promoted_to_tier_3_at_trade"] >= 20
    assert lifecycle["tier_3_profit_at_promotion"] >= 750.0

    # Final State Check
    assert lifecycle["final_tier"] == ScalingTier.TIER_3.name
    assert lifecycle["final_borrow_amount"] == 10_000_000_000
    assert lifecycle["accumulated_net_profit_usdc"] >= 750.0

    # Audit lifecycle events
    events = lifecycle["lifecycle_events"]
    assert len(events) >= 21

    # Verify tranche sizes scaled correctly in logged events
    tier1_events = [e for e in events if e["tier_before"] == "TIER_1"]
    for e in tier1_events:
        assert e["borrow_amount"] == 1_000_000_000

    tier2_events = [e for e in events if e["tier_before"] == "TIER_2"]
    for e in tier2_events:
        assert e["borrow_amount"] == 5_000_000_000

    tier3_events = [e for e in events if e["tier_before"] == "TIER_3"]
    assert len(tier3_events) >= 1
    for e in tier3_events:
        assert e["borrow_amount"] == 10_000_000_000


# ==============================================================================
# 5. GAS SAFETY WARNING & CRITICAL STOP TESTS
# ==============================================================================

def test_gas_safety_monitoring_progression():
    """Validates gas runway safety floor monitoring:

    - 5.419 SUI: HEALTHY, can_trade == True, gas_warning == False
    - 2.000 SUI: HEALTHY, can_trade == True, gas_warning == False
    - 1.500 SUI: HEALTHY, can_trade == True, gas_warning == False
    - 1.490 SUI: WARNING, can_trade == True, gas_warning == True
    - 1.000 SUI: WARNING, can_trade == True, gas_warning == True
    - 0.500 SUI: WARNING, can_trade == True, gas_warning == True
    - 0.490 SUI: CRITICAL, can_trade == False, gas_warning == True, status == EMERGENCY_LOCKED
    - 0.100 SUI: CRITICAL, can_trade == False, gas_warning == True, status == EMERGENCY_LOCKED
    """
    validator = SuiPTBPreflightValidator()
    test_balances = [5.419, 2.0, 1.5, 1.49, 1.0, 0.5, 0.49, 0.1]
    results = validator.simulate_gas_safety_monitoring(test_balances)

    assert len(results) == len(test_balances)

    # 5.419 SUI (actual wallet balance)
    assert results[0]["sui_balance"] == 5.419
    assert results[0]["can_trade"] is True
    assert results[0]["gas_warning"] is False
    assert results[0]["status"] == STATUS_ACTIVE

    # 1.49 SUI (below 1.5 warning floor)
    assert results[3]["sui_balance"] == 1.49
    assert results[3]["can_trade"] is True
    assert results[3]["gas_warning"] is True
    assert results[3]["is_warning"] is True

    # 0.49 SUI (below 0.5 critical hard stop floor)
    assert results[6]["sui_balance"] == 0.49
    assert results[6]["can_trade"] is False
    assert results[6]["gas_warning"] is True
    assert results[6]["is_critical"] is True
    assert results[6]["status"] == STATUS_EMERGENCY_LOCKED

    # 0.10 SUI
    assert results[7]["sui_balance"] == 0.10
    assert results[7]["can_trade"] is False
    assert results[7]["status"] == STATUS_EMERGENCY_LOCKED


def test_gas_safety_recovery_after_deposit():
    """Validates that depositing funds and restoring gas balance above 1.5 SUI
    clears warning and restores ACTIVE status (when not locked by 5 aborts)."""
    validator = SuiPTBPreflightValidator()
    engine = DynamicCapitalScalingEngine()

    # Drop to critical stop
    engine.update_from_wallet_balances(usdc_balance=0.0, sui_balance=0.3)
    assert engine.status == STATUS_EMERGENCY_LOCKED
    assert engine.can_trade() is False
    assert engine.state.gas_warning is True

    # Restore balance to 5.419 SUI
    engine.update_from_wallet_balances(usdc_balance=0.0, sui_balance=5.419)
    assert engine.status == STATUS_ACTIVE
    assert engine.can_trade() is True
    assert engine.state.gas_warning is False


# ==============================================================================
# 6. FULL VERIFICATION SUITE INTEGRATION TEST
# ==============================================================================

@pytest.mark.asyncio
async def test_run_full_preflight_and_dryrun_suite():
    """Validates master orchestration routine running the complete verification suite."""
    validator = SuiPTBPreflightValidator()
    try:
        report = await validator.run_full_preflight_and_dryrun_suite()
        assert isinstance(report, dict)
        assert report["all_verifications_passed"] is True
        assert report["preflight_health"]["all_checks_passed"] is True
        assert report["capital_scaling_lifecycle"]["success"] is True

        # Check all 4 pairs have both abort and success tests passing
        for pair_name in ["SUI/USDC", "DEEP/SUI", "DEEP/USDC", "CETUS/SUI"]:
            p_dry = report["dry_run_simulations"][pair_name]
            assert p_dry["abort_test"]["status"] == "ABORTED"
            assert p_dry["abort_test"]["zero_leg_risk_preserved"] is True
            assert p_dry["abort_test"]["gas_cost_sui"] == 0.002
            assert p_dry["success_test"]["status"] == "SUCCESS"
            assert p_dry["success_test"]["net_profit"] > 0
            assert p_dry["success_test"]["zero_leg_risk_preserved"] is True
    finally:
        await validator.close()
