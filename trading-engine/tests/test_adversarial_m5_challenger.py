"""Milestone M5 Adversarial Challenger Verification Suite.

Adversarial Stress Testing & Empirical Invariant Challenge:
1. Zero Leg Risk Invariant:
   - Negative spread, slippage spectrum, fee exhaustion, zero liquidity.
   - Atomic rollback verification: SplitCoins fails, receipt unconsumed, 0 state mutations.
2. Gas Depletion Protection:
   - Boundary conditions around 0.5 SUI critical floor & 1.5 SUI warning floor.
   - Exact floating-point and micro-mist edge cases.
   - Rejection of PTB execution when gas depleted.
   - Gas recovery vs persistent 5-abort lock.
3. Capital Scaling Monotonicity & Cooldown:
   - Dual-hurdle requirement (net profit AND trade count).
   - Monotonicity preservation under stress and out-of-order triggers.
   - Demotion on 3 consecutive aborts (Tier 3 -> Tier 2 -> Tier 1).
   - 60s and 300s (5-minute) cooldown enforcement and auto-recovery.
   - 5 consecutive abort emergency lock.
4. Runbook & Implementation Integrity:
   - Environment variables parity against docs/sui_production_runbook.md.
   - Healthcheck schema compliance and sensitive credential masking.
"""

from __future__ import annotations

import asyncio
import os
import time
from typing import Any, Dict, List
import pytest
import aiohttp

from venues.sui_deepbook_venue import (
    CIRCLE_USDC_TYPE,
    SUI_COIN_TYPE,
    SUI_PAIRS_CONFIG,
    HotPotatoPTBParams,
    PairConfig,
    SuiDeepBookPTBBuilder,
    SuiDeepBookVenue,
)
from venues.sui_health_server import (
    ACTIVE_PAIRS,
    DEFAULT_CRITICAL_GAS_FLOOR,
    DEFAULT_PORT,
    DEFAULT_REGION,
    DEFAULT_WARNING_GAS_FLOOR,
    STATUS_ACTIVE,
    STATUS_COOLING_DOWN,
    STATUS_EMERGENCY_LOCKED,
    SuiHealthServer,
)
from venues.sui_bot_runner import SuiBotConfig, SuiBotRunner
from venues.sui_ptb_validator import SuiPTBPreflightValidator
from venues.sui_scaling_engine import (
    DynamicCapitalScalingEngine,
    ScalingState,
    ScalingTier,
    SuiBalanceTracker,
    WalletBalanceSnapshot,
)


# ==============================================================================
# Challenge 1: Zero Leg Risk Invariant Stress Testing
# ==============================================================================

class TestZeroLegRiskAdversarial:
    """Stress tests the mathematical and VM-level zero leg risk invariant."""

    @pytest.fixture(autouse=True)
    def setup_venue(self) -> None:
        self.venue = SuiDeepBookVenue()
        self.builder = SuiDeepBookPTBBuilder()

    @pytest.mark.parametrize("pair_name", list(SUI_PAIRS_CONFIG.keys()))
    def test_catastrophic_negative_spread_zero_leg_risk(self, pair_name: str) -> None:
        """Under catastrophic negative spread (-50%), execution must abort with 0 state mutations."""
        params = HotPotatoPTBParams.from_pair(pair_name=pair_name, deduct_fees=True)
        ptb = self.builder.build_atomic_arb_ptb(params)

        cfg = SUI_PAIRS_CONFIG[pair_name]
        base_px = 2.0 if "USDC" in pair_name else 0.05
        # DeepBook bid is 50% below AMM buy price
        amm_swap_out_px = base_px
        deepbook_bid_px = base_px * 0.50

        sim = self.venue.simulate_dry_run(
            ptb=ptb,
            deepbook_bid_px=deepbook_bid_px,
            amm_swap_out_px=amm_swap_out_px,
            pair=pair_name,
            deduct_fees=True,
        )

        assert sim["status"] == "ABORTED"
        assert sim["zero_leg_risk_preserved"] is True
        assert sim["state_mutations"] == 0
        assert sim["net_profit_quote"] == 0.0
        assert sim["shortfall_native"] > 0
        assert sim["gas_cost_sui"] == 0.002
        assert "INSUFFICIENT_BALANCE_FOR_REPAYMENT" in sim["error"]

    @pytest.mark.parametrize("pair_name", list(SUI_PAIRS_CONFIG.keys()))
    def test_fee_slippage_exhaustion_clean_abort(self, pair_name: str) -> None:
        """When gross spread is marginally positive (+2 bps) but fees (10-35 bps) eat profit,

        the PTB must cleanly abort with zero state changes.
        """
        params = HotPotatoPTBParams.from_pair(pair_name=pair_name, deduct_fees=True)
        ptb = self.builder.build_atomic_arb_ptb(params)

        cfg = SUI_PAIRS_CONFIG[pair_name]
        base_px = 2.0 if "USDC" in pair_name else 0.05
        amm_swap_out_px = base_px
        # Marginally positive gross spread strictly below this pool's combined fee hurdle
        total_fee_bps = cfg.cetus_fee_bps + cfg.deepbook_taker_fee_bps
        sub_hurdle_frac = min(0.0002, (0.5 * total_fee_bps) / 10000.0)
        deepbook_bid_px = base_px * (1.0 + sub_hurdle_frac)

        sim = self.venue.simulate_dry_run(
            ptb=ptb,
            deepbook_bid_px=deepbook_bid_px,
            amm_swap_out_px=amm_swap_out_px,
            pair=pair_name,
            deduct_fees=True,
        )

        assert sim["status"] == "ABORTED"
        assert sim["zero_leg_risk_preserved"] is True
        assert sim["state_mutations"] == 0
        assert sim["shortfall_native"] > 0
        assert sim["net_profit_quote"] == 0.0

    def test_exact_shortfall_one_microunit_aborts(self) -> None:
        """If proceeds Q' are exactly 1 micro-unit short of principal Q, SplitCoins must abort."""
        pair_name = "SUI/USDC"
        params = HotPotatoPTBParams.from_pair(pair_name=pair_name, deduct_fees=False)
        ptb = self.builder.build_atomic_arb_ptb(params)

        borrow_amount = 1_000_000_000  # 1k USDC
        amm_swap_out_px = 2.0
        # Target net proceeds = 999_999_999 units (shortfall = 1 unit)
        deepbook_bid_px = 2.0 * (999_999_999 / 1_000_000_000)

        sim = self.venue.simulate_dry_run(
            ptb=ptb,
            deepbook_bid_px=deepbook_bid_px,
            amm_swap_out_px=amm_swap_out_px,
            borrow_amount=borrow_amount,
            pair=pair_name,
            deduct_fees=False,
        )

        assert sim["status"] == "ABORTED"
        assert sim["zero_leg_risk_preserved"] is True
        assert sim["net_proceeds_native"] == 999_999_999
        assert sim["shortfall_native"] == 1
        assert sim["state_mutations"] == 0

    def test_exact_par_break_even_zero_profit_repayment(self) -> None:
        """If proceeds Q' exactly equal principal Q, SplitCoins splits full amount for repayment,

        leaving 0 profit, but successfully clearing debt.
        """
        pair_name = "SUI/USDC"
        params = HotPotatoPTBParams.from_pair(pair_name=pair_name, deduct_fees=False)
        ptb = self.builder.build_atomic_arb_ptb(params)

        borrow_amount = 1_000_000_000
        sim = self.venue.simulate_dry_run(
            ptb=ptb,
            deepbook_bid_px=2.0,
            amm_swap_out_px=2.0,
            borrow_amount=borrow_amount,
            pair=pair_name,
            deduct_fees=False,
        )

        assert sim["status"] == "SUCCESS"
        assert sim["zero_leg_risk_preserved"] is True
        assert sim["net_profit_quote"] == 0.0
        assert sim["repaid_amount_quote"] == 1000.0
        assert sim["state_mutations"] == 8

    @pytest.mark.parametrize("pair_name", list(SUI_PAIRS_CONFIG.keys()))
    def test_ptb_hot_potato_topological_chain(self, pair_name: str) -> None:
        """Verifies Move VM Hot Potato linkage: Command 0 outputs receipt, Command 6 quenches it."""
        params = HotPotatoPTBParams.from_pair(pair_name=pair_name)
        ptb = self.builder.build_atomic_arb_ptb(params)
        commands = ptb["commands"]

        assert len(commands) == 8
        # Command 0 produces receipt at output index 1
        cmd0 = commands[0]
        assert cmd0["outputs"] == [
            "borrowed_quote_coin" if params.borrow_asset == "quote" else "borrowed_base_coin",
            "flash_loan_receipt",
        ]

        # Command 5 splits repayment coin from Command 4 proceeds
        cmd5 = commands[5]
        assert cmd5["type"] == "SplitCoins"
        assert cmd5["coin"] == {"NestedResult": [4, 0]}

        # Command 6 consumes the repay coin from [5, 0] AND the receipt from [0, 1]
        cmd6 = commands[6]
        assert cmd6["arguments"][1] == {"NestedResult": [5, 0]}
        assert cmd6["arguments"][2] == {"NestedResult": [0, 1]}

        # Command 7 transfers leftover profit from [4, 0]
        cmd7 = commands[7]
        assert cmd7["type"] == "TransferObjects"
        assert cmd7["objects"] == [{"NestedResult": [4, 0]}]


# ==============================================================================
# Challenge 2: Gas Depletion Protection Invariant
# ==============================================================================

class TestGasDepletionAdversarial:
    """Stress tests gas exhaustion floors, boundaries, and trade blocking."""

    def test_gas_critical_floor_exact_transitions(self) -> None:
        """Exhaustively tests boundary around critical gas floor (0.5 SUI)."""
        engine = DynamicCapitalScalingEngine()

        # Above critical floor: can trade
        engine.update_from_wallet_balances(usdc_balance=0.0, sui_balance=0.500000001)
        assert engine.can_trade() is True
        assert engine.state.gas_warning is True  # In warning zone [0.5, 1.5)

        # Below critical floor by 1 nano-SUI (0.499999999 SUI): hard stop
        engine.update_from_wallet_balances(usdc_balance=0.0, sui_balance=0.499999999)
        assert engine.can_trade() is False
        assert engine.status == STATUS_EMERGENCY_LOCKED

        # Completely depleted (0.0 SUI): hard stop
        engine.update_from_wallet_balances(usdc_balance=0.0, sui_balance=0.0)
        assert engine.can_trade() is False

    @pytest.mark.asyncio
    async def test_bot_runner_refuses_ptb_execution_at_critical_gas(self) -> None:
        """Empirically verifies that SuiBotRunner refuses to submit or simulate trades when gas < 0.5."""
        runner = SuiBotRunner(config=SuiBotConfig(port=18991))
        # Set gas to 0.49 SUI
        runner.update_gas_balance(0.49)
        assert runner.scaling_engine.can_trade() is False

        # scan_once must immediately return empty without evaluating any pair
        results = await runner.scan_once()
        assert results == []
        assert runner.total_executions_attempted == 0

    def test_gas_recovery_does_not_unlock_abort_circuit_breaker(self) -> None:
        """Gas deposit must NOT unlock a system that was emergency-locked due to 5 consecutive aborts."""
        engine = DynamicCapitalScalingEngine()

        # 1. Trigger 5 aborts -> EMERGENCY_LOCKED
        for _ in range(5):
            engine.record_trade_abort()
        assert engine.status == STATUS_EMERGENCY_LOCKED
        assert engine._emergency_locked_due_to_aborts is True

        # 2. Gas drops to 0.2 SUI
        engine.update_from_wallet_balances(usdc_balance=0.0, sui_balance=0.2)
        assert engine.status == STATUS_EMERGENCY_LOCKED

        # 3. Fresh gas top-up to 10.0 SUI arrives
        engine.update_from_wallet_balances(usdc_balance=0.0, sui_balance=10.0)
        # MUST REMAIN LOCKED because abort circuit breaker is active!
        assert engine.status == STATUS_EMERGENCY_LOCKED
        assert engine.can_trade() is False

        # Only explicit operator unlock can restore it
        engine.unlock_emergency()
        assert engine.status == STATUS_ACTIVE
        assert engine.can_trade() is True


# ==============================================================================
# Challenge 3: Capital Scaling Monotonicity & Cooldown
# ==============================================================================

class TestCapitalScalingAdversarial:
    """Stress tests capital scaling state machine, dual-key hurdles, and cooldowns."""

    def test_dual_hurdle_strictness_tier_1_to_2(self) -> None:
        """Scaling from Tier 1 -> Tier 2 requires BOTH >= $100 profit AND >= 10 trades."""
        engine = DynamicCapitalScalingEngine()
        assert engine.current_tier == ScalingTier.TIER_1

        # Case A: Profit met ($100.00), trades insufficient (9)
        engine.state.accumulated_net_profit_usdc = 100.0
        engine.state.successful_trades = 9
        engine._evaluate_tier_promotions()
        assert engine.current_tier == ScalingTier.TIER_1

        # Case B: Trades met (10), profit insufficient ($99.99)
        engine.state.accumulated_net_profit_usdc = 99.99
        engine.state.successful_trades = 10
        engine._evaluate_tier_promotions()
        assert engine.current_tier == ScalingTier.TIER_1

        # Case C: Both met exactly ($100.00, 10 trades)
        engine.state.accumulated_net_profit_usdc = 100.0
        engine.state.successful_trades = 10
        engine._evaluate_tier_promotions()
        assert engine.current_tier == ScalingTier.TIER_2
        assert engine.flash_borrow_amount == 5_000_000_000

    def test_dual_hurdle_strictness_tier_2_to_3(self) -> None:
        """Scaling from Tier 2 -> Tier 3 requires BOTH >= $750 profit AND >= 20 trades."""
        engine = DynamicCapitalScalingEngine(initial_tier=ScalingTier.TIER_2)
        assert engine.current_tier == ScalingTier.TIER_2

        # Case A: Profit met ($750.00), trades insufficient (19)
        engine.state.accumulated_net_profit_usdc = 750.0
        engine.state.successful_trades = 19
        engine._evaluate_tier_promotions()
        assert engine.current_tier == ScalingTier.TIER_2

        # Case B: Trades met (20), profit insufficient ($749.99)
        engine.state.accumulated_net_profit_usdc = 749.99
        engine.state.successful_trades = 20
        engine._evaluate_tier_promotions()
        assert engine.current_tier == ScalingTier.TIER_2

        # Case C: Both met ($750.00, 20 trades)
        engine.state.accumulated_net_profit_usdc = 750.0
        engine.state.successful_trades = 20
        engine._evaluate_tier_promotions()
        assert engine.current_tier == ScalingTier.TIER_3
        assert engine.flash_borrow_amount == 10_000_000_000

    def test_three_consecutive_aborts_downgrade_ladder(self) -> None:
        """3 consecutive aborts demotes by 1 tier and triggers cooldown."""
        engine = DynamicCapitalScalingEngine(initial_tier=ScalingTier.TIER_3)

        # 3 aborts from Tier 3 -> demotes to Tier 2 + COOLING_DOWN
        for _ in range(3):
            engine.record_trade_abort()
        assert engine.current_tier == ScalingTier.TIER_2
        assert engine.status == STATUS_COOLING_DOWN
        assert engine.can_trade() is False

        # Clear cooldown via successful trade
        engine.record_trade_success(profit_usdc=10.0)
        assert engine.status == STATUS_ACTIVE
        assert engine.can_trade() is True
        assert engine.state.consecutive_aborts == 0

        # Another 3 aborts from Tier 2 -> demotes to Tier 1 + COOLING_DOWN
        for _ in range(3):
            engine.record_trade_abort()
        assert engine.current_tier == ScalingTier.TIER_1
        assert engine.status == STATUS_COOLING_DOWN

        # Another 3 aborts at Tier 1 -> stays Tier 1 + COOLING_DOWN
        engine.record_trade_success(profit_usdc=1.0)
        for _ in range(3):
            engine.record_trade_abort()
        assert engine.current_tier == ScalingTier.TIER_1
        assert engine.status == STATUS_COOLING_DOWN

    def test_configurable_cooldown_duration(self) -> None:
        """Verifies configurable cooldown parameter (e.g., 300.0s / 5 minutes)."""
        five_minute_cooldown = 300.0
        engine = DynamicCapitalScalingEngine(cooldown_duration_seconds=five_minute_cooldown)

        start_time = time.time()
        for _ in range(3):
            engine.record_trade_abort()

        assert engine.status == STATUS_COOLING_DOWN
        assert engine.state.cooldown_until >= start_time + 299.0
        assert engine.state.cooldown_until <= start_time + 301.0
        assert engine.can_trade() is False

    def test_cooldown_automatic_temporal_recovery(self) -> None:
        """After cooldown timer expires, engine returns to ACTIVE automatically."""
        # 0.1 second micro-cooldown
        engine = DynamicCapitalScalingEngine(cooldown_duration_seconds=0.1)
        for _ in range(3):
            engine.record_trade_abort()

        assert engine.status == STATUS_COOLING_DOWN
        assert engine.can_trade() is False

        # Sleep past cooldown expiry
        time.sleep(0.15)

        assert engine.status == STATUS_ACTIVE
        assert engine.can_trade() is True


# ==============================================================================
# Challenge 4: Runbook Integrity & Implementation Parity
# ==============================================================================

class TestRunbookIntegrityAdversarial:
    """Verifies complete parity between docs/sui_production_runbook.md and code."""

    def test_all_14_runbook_environment_variables_parsed(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Verifies that all 14 configuration variables in runbook Section 5 table are supported."""
        env_vars = {
            "SUI_GRAPHQL_URL": "https://graphql.mainnet.sui.io/graphql",
            "OPERATOR_ADDRESS": "0x5621a8e7199680512ee829565b96febea2587e534fd69b33f04004298d7e5ce9",
            "INITIAL_BORROW_AMOUNT": "1000000000",
            "DEEPBOOK_BALANCE_MANAGER_ID": "0xbm_11111111111111111111111111111111",
            "PORT": "8888",
            "LOG_LEVEL": "DEBUG",
            "PYTHONUNBUFFERED": "1",
            "REGION": "europe-west3",
            "DRY_RUN_MODE": "true",
            "SCAN_INTERVAL_SECONDS": "1.5",
            "THROTTLED_SCAN_INTERVAL_SECONDS": "4.0",
            "WARNING_GAS_FLOOR": "1.8",
            "CRITICAL_GAS_FLOOR": "0.6",
            "SUI_PRIVATE_KEY": "suiprivkey1testkey000000000000000000000000000000000000000000000",
        }
        for k, v in env_vars.items():
            monkeypatch.setenv(k, v)

        config = SuiBotConfig.from_env()

        assert config.graphql_url == env_vars["SUI_GRAPHQL_URL"]
        assert config.operator_address == env_vars["OPERATOR_ADDRESS"]
        assert config.initial_borrow_amount == 1_000_000_000
        assert config.balance_manager_id == env_vars["DEEPBOOK_BALANCE_MANAGER_ID"]
        assert config.port == 8888
        assert config.log_level == "DEBUG"
        assert config.region == "europe-west3"
        assert config.dry_run_mode is True
        assert config.scan_interval_seconds == 1.5
        assert config.throttled_scan_interval_seconds == 4.0
        assert config.warning_gas_floor == 1.8
        assert config.critical_gas_floor == 0.6
        assert config.sui_private_key == env_vars["SUI_PRIVATE_KEY"]

    def test_secrets_never_exposed_in_config_or_health(self) -> None:
        """Adversarial check: SUI_PRIVATE_KEY must NEVER leak into repr, str, to_safe_dict, or HTTP."""
        secret = "suiprivkey1secretcanarystring999999999999999999999999999999999999"
        config = SuiBotConfig(sui_private_key=secret)

        # 1. Repr and str
        assert secret not in repr(config)
        assert secret not in str(config)

        # 2. to_safe_dict
        safe_dict = config.to_safe_dict()
        assert secret not in str(safe_dict)
        assert "sui_private_key" not in safe_dict
        assert safe_dict["has_private_key"] is True

        # 3. Health server data
        server = SuiHealthServer()
        health_data = server.get_health_data()
        assert secret not in str(health_data)

    def test_runbook_file_exists_and_matches_mirror(self) -> None:
        """Verifies docs/sui_production_runbook.md exists and is mirrored in trading-engine/docs."""
        runbook_path = "docs/sui_production_runbook.md"
        mirror_path = "trading-engine/docs/sui_production_runbook.md"

        assert os.path.isfile(runbook_path), f"Missing {runbook_path}"
        assert os.path.isfile(mirror_path), f"Missing {mirror_path}"

        with open(runbook_path, "r", encoding="utf-8") as f1, open(mirror_path, "r", encoding="utf-8") as f2:
            c1 = f1.read()
            c2 = f2.read()
            assert c1 == c2, "Runbook mirror is desynchronized from root documentation"
            assert len(c1.splitlines()) >= 500, "Runbook documentation is incomplete"

    @pytest.mark.asyncio
    async def test_health_server_schema_matches_runbook(self) -> None:
        """Verifies that GET /health output adheres strictly to runbook JSON schema."""
        test_port = 18992
        server = SuiHealthServer(host="127.0.0.1", port=test_port)
        await server.start()

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"http://127.0.0.1:{test_port}/health") as resp:
                    assert resp.status == 200
                    data = await resp.json()

                    # Schema keys required by runbook Section 5
                    required_keys = [
                        "status",
                        "uptime_seconds",
                        "current_tier",
                        "borrow_amount_usdc",
                        "sui_gas_balance",
                        "active_pairs",
                        "region",
                        "consecutive_aborts",
                        "timestamp",
                    ]
                    for key in required_keys:
                        assert key in data, f"Missing key '{key}' in health payload"

                    assert data["status"] in ("HEALTHY", "DEGRADED", "CRITICAL")
                    assert data["active_pairs"] == list(ACTIVE_PAIRS)
                    assert data["region"] == "europe-west3"
                    assert isinstance(data["borrow_amount_usdc"], int)
                    assert isinstance(data["sui_gas_balance"], float)
        finally:
            await server.stop()
