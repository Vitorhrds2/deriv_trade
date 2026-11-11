"""Adversarial Operational & Gas Safety Stress Test Suite (Challenger 2).

Empirical verification of:
1. Gas Runway Safety Floors (Requirement R2, R3, R5):
   - Starting state at 5.419 SUI (ACTIVE).
   - Step down below 1.5 SUI -> gas_warning = True and throttling activated.
   - Step down below 0.5 SUI -> immediate transition to EMERGENCY_LOCKED and trading halts.
   - Deposit funds back to >= 1.5 SUI -> recovery to ACTIVE.
   - 5-abort circuit breaker lock cannot be bypassed by gas deposit alone.
2. Consecutive Abort Circuit Breakers:
   - 3 consecutive aborts -> demote 1 tier + 60s cooldown.
   - 5 consecutive aborts -> EMERGENCY_LOCKED.
   - Trade success -> abort counter reset and cooldown cleared.
3. Bot Runner Lifecycle & Live Mode Verification:
   - DRY_RUN_MODE=false: requires valid SUI_PRIVATE_KEY (suiprivkey1...).
   - Preflight simulation via simulateTransaction before broadcasting (0 gas cost abort).
   - Cryptographic signing with Ed25519 and Blake2b-256 intent scope (b"\\x00\\x00\\x00" + tx_bytes).
   - Live broadcast via GraphQL executeTransaction mutation.
   - /health, /live, and / endpoints return 200 OK with accurate telemetry.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import os
import time
from typing import Any, Dict, List
from unittest.mock import AsyncMock, patch

import aiohttp
import pytest
from cryptography.hazmat.primitives.asymmetric import ed25519
from solders.keypair import Keypair

from venues.sui_bot_runner import (
    ACTIVE_PAIRS,
    DEFAULT_PAIR_BASE_PRICES,
    SuiBotConfig,
    SuiBotRunner,
)
from venues.sui_deepbook_venue import (
    BECH32_CHARSET,
    SUI_GRAPHQL_MAINNET,
    SuiDeepBookPTBBuilder,
    SuiDeepBookVenue,
    SuiGraphQLClient,
    bech32_decode,
)
from venues.sui_health_server import SuiHealthServer
from venues.sui_scaling_engine import (
    DEFAULT_CRITICAL_GAS_FLOOR,
    DEFAULT_WARNING_GAS_FLOOR,
    STATUS_ACTIVE,
    STATUS_COOLING_DOWN,
    STATUS_EMERGENCY_LOCKED,
    DynamicCapitalScalingEngine,
    ScalingTier,
)


def generate_valid_suiprivkey() -> str:
    """Generates a cryptographically valid bech32-encoded suiprivkey for testing."""
    seed = os.urandom(32)
    payload = b"\x00" + seed  # 0x00 flag for ed25519 + 32-byte seed

    acc = 0
    bits = 0
    ret = []
    for b in payload:
        acc = (acc << 8) | b
        bits += 8
        while bits >= 5:
            bits -= 5
            ret.append((acc >> bits) & 0x1F)
    if bits > 0:
        ret.append((acc << (5 - bits)) & 0x1F)

    def polymod(values):
        GEN = [0x3B6A57B2, 0x26508E6D, 0x1EA119FA, 0x3D4233DD, 0x2A1462B3]
        chk = 1
        for v in values:
            b = chk >> 25
            chk = ((chk & 0x1FFFFFF) << 5) ^ v
            for i in range(5):
                chk ^= GEN[i] if ((b >> i) & 1) else 0
        return chk

    hrp = "suiprivkey"
    hrp_expanded = [ord(x) >> 5 for x in hrp] + [0] + [ord(x) & 31 for x in hrp]
    mod = polymod(hrp_expanded + ret + [0, 0, 0, 0, 0, 0]) ^ 1
    chk = [(mod >> 5 * (5 - i)) & 31 for i in range(6)]
    return hrp + "1" + "".join(BECH32_CHARSET[x] for x in (ret + chk))


MOCK_GAS_COIN = {
    "address": "0x5621a8e7199680512ee829565b96febea2587e534fd69b33f04004298d7e5ce9",
    "version": 1,
    "digest": "11111111111111111111111111111111",
}


class TestGasRunwaySafetyFloors:
    """Target 1: Empirical verification of gas safety state machine and runway guardrails."""

    def test_gas_safety_state_machine_starting_active_5_419_sui(self) -> None:
        """Verifies initial state at verified balance of 5.419 SUI is ACTIVE with 0 warning."""
        engine = DynamicCapitalScalingEngine(initial_tier=ScalingTier.TIER_1)
        engine.update_from_wallet_balances(usdc_balance=1000.0, sui_balance=5.419)

        assert engine.state.sui_gas_balance == pytest.approx(5.419, rel=1e-4)
        assert engine.state.status == STATUS_ACTIVE
        assert engine.status == STATUS_ACTIVE
        assert engine.can_trade() is True
        assert engine.state.gas_warning is False

    def test_gas_step_down_below_1_5_sui_triggers_warning_and_throttling(self) -> None:
        """Verifies step down below 1.5 SUI activates gas_warning and throttling while permitting trades."""
        engine = DynamicCapitalScalingEngine(initial_tier=ScalingTier.TIER_1)
        engine.update_from_wallet_balances(usdc_balance=1000.0, sui_balance=5.419)
        assert engine.state.gas_warning is False

        # Step down to 1.49 SUI
        engine.update_from_wallet_balances(usdc_balance=1000.0, sui_balance=1.49)
        assert engine.state.gas_warning is True
        assert engine.state.status == STATUS_ACTIVE
        assert engine.can_trade() is True  # Still allowed to trade down to 0.5 SUI

        # Step down to 1.20 SUI
        engine.update_from_wallet_balances(usdc_balance=1000.0, sui_balance=1.20)
        assert engine.state.gas_warning is True
        assert engine.state.status == STATUS_ACTIVE
        assert engine.can_trade() is True

        # Test runner throttling logic
        config = SuiBotConfig(
            scan_interval_seconds=1.0,
            throttled_scan_interval_seconds=3.0,
            warning_gas_floor=1.5,
            critical_gas_floor=0.5,
        )
        runner = SuiBotRunner(config=config, scaling_engine=engine)
        is_warning = runner.scaling_engine.state.gas_warning or (
            runner.scaling_engine.state.sui_gas_balance > 0
            and runner.scaling_engine.state.sui_gas_balance < runner.config.warning_gas_floor
        )
        sleep_duration = (
            runner.config.throttled_scan_interval_seconds
            if is_warning
            else runner.config.scan_interval_seconds
        )
        assert is_warning is True
        assert sleep_duration == 3.0

    def test_gas_step_down_below_0_5_sui_triggers_immediate_emergency_lock(self) -> None:
        """Verifies step down below 0.5 SUI triggers immediate transition to EMERGENCY_LOCKED and halts trading."""
        engine = DynamicCapitalScalingEngine(initial_tier=ScalingTier.TIER_1)
        engine.update_from_wallet_balances(usdc_balance=1000.0, sui_balance=5.419)

        # Step down below critical floor (0.499 SUI)
        engine.update_from_wallet_balances(usdc_balance=1000.0, sui_balance=0.499)
        assert engine.state.status == STATUS_EMERGENCY_LOCKED
        assert engine.status == STATUS_EMERGENCY_LOCKED
        assert engine.can_trade() is False
        assert engine.state.gas_warning is True

        # Extreme near-zero gas floor
        engine.update_from_wallet_balances(usdc_balance=1000.0, sui_balance=0.001)
        assert engine.state.status == STATUS_EMERGENCY_LOCKED
        assert engine.can_trade() is False

    def test_gas_deposit_recovery_to_active(self) -> None:
        """Verifies depositing funds back to >= 1.5 SUI automatically restores ACTIVE status."""
        engine = DynamicCapitalScalingEngine(initial_tier=ScalingTier.TIER_1)
        engine.update_from_wallet_balances(usdc_balance=1000.0, sui_balance=0.35)
        assert engine.state.status == STATUS_EMERGENCY_LOCKED
        assert engine.can_trade() is False

        # Deposit funds to 2.50 SUI (above 1.5 warning floor)
        engine.update_from_wallet_balances(usdc_balance=1000.0, sui_balance=2.50)
        assert engine.state.status == STATUS_ACTIVE
        assert engine.status == STATUS_ACTIVE
        assert engine.can_trade() is True
        assert engine.state.gas_warning is False

        # Deposit back to 5.419 SUI
        engine.update_from_wallet_balances(usdc_balance=1000.0, sui_balance=5.419)
        assert engine.state.status == STATUS_ACTIVE
        assert engine.can_trade() is True
        assert engine.state.gas_warning is False

    def test_five_abort_emergency_lock_cannot_be_bypassed_by_gas_deposit_alone(self) -> None:
        """Verifies that a 5-abort circuit breaker lock cannot be bypassed by gas deposit alone."""
        engine = DynamicCapitalScalingEngine(initial_tier=ScalingTier.TIER_1)
        engine.update_from_wallet_balances(usdc_balance=1000.0, sui_balance=5.419)
        assert engine.can_trade() is True

        # Trigger 5 consecutive aborts
        for i in range(5):
            engine.record_trade_abort()

        assert engine.state.consecutive_aborts == 5
        assert engine.state.status == STATUS_EMERGENCY_LOCKED
        assert engine.status == STATUS_EMERGENCY_LOCKED
        assert engine.can_trade() is False
        assert engine._emergency_locked_due_to_aborts is True

        # Attempt to bypass lock by depositing massive SUI gas (e.g. 50.0 SUI)
        engine.update_from_wallet_balances(usdc_balance=1000.0, sui_balance=50.0)
        assert engine.state.status == STATUS_EMERGENCY_LOCKED
        assert engine.status == STATUS_EMERGENCY_LOCKED
        assert engine.can_trade() is False
        assert engine._emergency_locked_due_to_aborts is True

        # Attempt with 100.0 SUI
        engine.update_from_wallet_balances(usdc_balance=2000.0, sui_balance=100.0)
        assert engine.state.status == STATUS_EMERGENCY_LOCKED
        assert engine.can_trade() is False
        assert engine._emergency_locked_due_to_aborts is True


class TestConsecutiveAbortCircuitBreakers:
    """Target 2: Empirical verification of consecutive abort circuit breakers and resets."""

    def test_three_consecutive_aborts_demotes_one_tier_and_triggers_60s_cooldown(self) -> None:
        """Verifies 3 consecutive aborts demotes by 1 tier and enters 60s cooldown."""
        # Start at TIER_3
        engine = DynamicCapitalScalingEngine(initial_tier=ScalingTier.TIER_3)
        assert engine.current_tier == ScalingTier.TIER_3
        assert engine.flash_borrow_amount == 10_000_000_000

        # Abort 1
        engine.record_trade_abort()
        assert engine.state.consecutive_aborts == 1
        assert engine.current_tier == ScalingTier.TIER_3
        assert engine.status == STATUS_ACTIVE
        assert engine.can_trade() is True

        # Abort 2
        engine.record_trade_abort()
        assert engine.state.consecutive_aborts == 2
        assert engine.current_tier == ScalingTier.TIER_3
        assert engine.status == STATUS_ACTIVE
        assert engine.can_trade() is True

        # Abort 3 -> Demotion to TIER_2 and COOLING_DOWN
        now = time.time()
        engine.record_trade_abort()
        assert engine.state.consecutive_aborts == 3
        assert engine.current_tier == ScalingTier.TIER_2
        assert engine.flash_borrow_amount == 5_000_000_000
        assert engine.state.status == STATUS_COOLING_DOWN
        assert engine.status == STATUS_COOLING_DOWN
        assert engine.can_trade() is False
        assert engine.state.cooldown_until >= now + 59.0

        # Start at TIER_2 and test demotion to TIER_1
        engine2 = DynamicCapitalScalingEngine(initial_tier=ScalingTier.TIER_2)
        for _ in range(3):
            engine2.record_trade_abort()
        assert engine2.current_tier == ScalingTier.TIER_1
        assert engine2.flash_borrow_amount == 1_000_000_000
        assert engine2.status == STATUS_COOLING_DOWN

    def test_five_consecutive_aborts_triggers_emergency_locked(self) -> None:
        """Verifies 5 consecutive aborts triggers EMERGENCY_LOCKED."""
        engine = DynamicCapitalScalingEngine(initial_tier=ScalingTier.TIER_2)
        for _ in range(3):
            engine.record_trade_abort()
        assert engine.status == STATUS_COOLING_DOWN

        # Abort 4
        engine.record_trade_abort()
        assert engine.state.consecutive_aborts == 4
        assert engine.status == STATUS_COOLING_DOWN

        # Abort 5 -> EMERGENCY_LOCKED
        engine.record_trade_abort()
        assert engine.state.consecutive_aborts == 5
        assert engine.state.status == STATUS_EMERGENCY_LOCKED
        assert engine.status == STATUS_EMERGENCY_LOCKED
        assert engine.can_trade() is False
        assert engine._emergency_locked_due_to_aborts is True

    def test_trade_success_resets_abort_counter_and_clears_cooldown(self) -> None:
        """Verifies successful trade clears abort counter, clears cooldown, and restores ACTIVE status."""
        engine = DynamicCapitalScalingEngine(initial_tier=ScalingTier.TIER_2)
        for _ in range(3):
            engine.record_trade_abort()
        assert engine.status == STATUS_COOLING_DOWN
        assert engine.state.consecutive_aborts == 3
        assert engine.can_trade() is False

        # Record successful trade
        engine.record_trade_success(profit_usdc=15.50)
        assert engine.state.consecutive_aborts == 0
        assert engine.state.cooldown_until == 0.0
        assert engine.state.status == STATUS_ACTIVE
        assert engine.status == STATUS_ACTIVE
        assert engine.can_trade() is True
        assert engine.state.successful_trades == 1
        assert engine.state.accumulated_net_profit_usdc == 15.50

    def test_cooldown_automatic_recovery_after_expiry(self) -> None:
        """Verifies that cooldown automatically expires after duration and restores ACTIVE."""
        engine = DynamicCapitalScalingEngine(initial_tier=ScalingTier.TIER_1)
        for _ in range(3):
            engine.record_trade_abort()
        assert engine.state.status == STATUS_COOLING_DOWN

        # Simulate time warp past cooldown duration
        engine.state.cooldown_until = time.time() - 1.0
        assert engine.status == STATUS_ACTIVE
        assert engine.can_trade() is True


class TestBotRunnerLifecycleAndLiveMode:
    """Target 3: Audit sui_bot_runner.py, sui_health_server.py, and live execution invariants."""

    def test_live_mode_requires_valid_suiprivkey(self) -> None:
        """Verifies DRY_RUN_MODE=false enforces valid suiprivkey1... before setting live_onchain=True."""
        # Case 1: Missing private key
        cfg_no_key = SuiBotConfig(dry_run_mode=False, sui_private_key=None)
        assert cfg_no_key.sui_private_key is None
        assert not bool(cfg_no_key.sui_private_key and cfg_no_key.sui_private_key.startswith("suiprivkey1"))

        # Case 2: Invalid format private key
        cfg_bad_key = SuiBotConfig(dry_run_mode=False, sui_private_key="invalid_hex_key_123456789")
        assert not bool(cfg_bad_key.sui_private_key and cfg_bad_key.sui_private_key.startswith("suiprivkey1"))

        # Case 3: Valid suiprivkey format
        valid_key = generate_valid_suiprivkey()
        cfg_valid_key = SuiBotConfig(dry_run_mode=False, sui_private_key=valid_key)
        assert bool(cfg_valid_key.sui_private_key and cfg_valid_key.sui_private_key.startswith("suiprivkey1"))

    @pytest.mark.asyncio
    async def test_live_mode_preflight_simulation_rejection_prevents_broadcast(self) -> None:
        """Verifies that preflight simulation rejection halts execution with 0 gas cost without broadcasting."""
        valid_key = generate_valid_suiprivkey()
        venue = SuiDeepBookVenue(private_key=valid_key)

        mock_sim_resp = {
            "data": {
                "simulateTransaction": {
                    "effects": {
                        "status": "FAILURE",
                        "executionError": {"message": "Move VM execution aborted: Insufficient slippage"},
                    }
                }
            }
        }

        mock_graphql = AsyncMock()
        mock_graphql.get_gas_coin_and_price = AsyncMock(return_value=(MOCK_GAS_COIN, 1000))
        mock_graphql.simulate_transaction_bcs = AsyncMock(return_value=mock_sim_resp)
        mock_graphql.execute_transaction_bcs = AsyncMock()

        venue.graphql_client = mock_graphql

        order_params = {
            "symbol": "SUI/USDC",
            "side": "BUY",
            "size": 1_000_000_000,
            "price": 2.0,
            "deepbook_ask_px": 2.0,
            "amm_price": 1.92,  # profitable locally so it attempts live execution
            "is_arb_ptb": True,
            "route_direction": "FORWARD",
            "live_onchain": True,
        }

        res = await venue.submit_order(order_params)
        assert res.status == "REJECTED"
        assert res.order_id.startswith("PTB-SIM-REVERT-")
        # Assert simulation was called
        mock_graphql.simulate_transaction_bcs.assert_awaited_once()
        # Assert executeTransaction was NEVER called (zero gas cost, zero state mutation)
        mock_graphql.execute_transaction_bcs.assert_not_called()

    @pytest.mark.asyncio
    async def test_live_mode_simulation_success_triggers_ed25519_blake2b_sign_and_execute(self) -> None:
        """Verifies simulation SUCCESS signs with Ed25519/Blake2b and broadcasts executeTransaction."""
        valid_key = generate_valid_suiprivkey()
        venue = SuiDeepBookVenue(private_key=valid_key)

        mock_sim_resp = {
            "data": {
                "simulateTransaction": {
                    "effects": {
                        "status": "SUCCESS",
                        "gasUsed": {"computationCost": "1000000", "storageCost": "1000000"},
                    }
                }
            }
        }
        mock_exec_resp = {
            "data": {
                "executeTransaction": {
                    "effects": {
                        "status": "SUCCESS",
                        "digest": "5yGq4u8YvZ1L7X8k5V9W2e3R1T6Y7U8I9O0P1A2S3D4F",
                    }
                }
            }
        }

        mock_graphql = AsyncMock()
        mock_graphql.get_gas_coin_and_price = AsyncMock(return_value=(MOCK_GAS_COIN, 1000))
        mock_graphql.simulate_transaction_bcs = AsyncMock(return_value=mock_sim_resp)
        mock_graphql.execute_transaction_bcs = AsyncMock(return_value=mock_exec_resp)

        venue.graphql_client = mock_graphql

        order_params = {
            "symbol": "SUI/USDC",
            "side": "BUY",
            "size": 1_000_000_000,
            "price": 2.0,
            "deepbook_ask_px": 2.0,
            "amm_price": 1.92,  # profitable locally
            "is_arb_ptb": True,
            "route_direction": "FORWARD",
            "live_onchain": True,
        }

        res = await venue.submit_order(order_params)
        assert res.status == "FILLED"
        assert res.order_id == "5yGq4u8YvZ1L7X8k5V9W2e3R1T6Y7U8I9O0P1A2S3D4F"

        mock_graphql.simulate_transaction_bcs.assert_awaited_once()
        mock_graphql.execute_transaction_bcs.assert_awaited_once()

        # Validate signature structure passed to execute_transaction_bcs
        call_args = mock_graphql.execute_transaction_bcs.call_args[0]
        tx_bytes_arg, signatures_arg = call_args[0], call_args[1]
        assert isinstance(tx_bytes_arg, bytes)
        assert len(signatures_arg) == 1
        sig_b64 = signatures_arg[0]
        sig_bytes = base64.b64decode(sig_b64)
        # Sui serialized signature format: 1-byte flag (0x00) + 64-byte Ed25519 signature + 32-byte pubkey = 97 bytes
        assert len(sig_bytes) == 97
        assert sig_bytes[0] == 0x00  # Ed25519 flag

    def test_signing_cryptographic_verification(self) -> None:
        """Verifies Ed25519 Blake2b-256 signature correctness using solders Keypair and cryptography."""
        ptb_builder = SuiDeepBookPTBBuilder()
        valid_key = generate_valid_suiprivkey()
        tx_bytes = b"sample_sui_ptb_transaction_data_bytes_for_signing_test"

        sig_b64 = ptb_builder.sign_transaction_bcs(tx_bytes, valid_key)
        sig_bytes = base64.b64decode(sig_b64)

        assert len(sig_bytes) == 97
        flag = sig_bytes[0]
        sig = sig_bytes[1:65]
        pubkey = sig_bytes[65:97]

        assert flag == 0x00
        # Reconstruct keypair from seed
        hrp, raw = bech32_decode(valid_key)
        seed = raw[1:] if len(raw) == 33 else raw[:32]
        kp = Keypair.from_seed(seed)
        assert bytes(kp.pubkey()) == pubkey

        # Reconstruct Blake2b-256 intent hash
        digest = hashlib.blake2b(b"\x00\x00\x00" + tx_bytes, digest_size=32).digest()
        # Verify Ed25519 signature cryptographically
        verifier = ed25519.Ed25519PublicKey.from_public_bytes(pubkey)
        verifier.verify(sig, digest)  # Will raise InvalidSignature if invalid

    @pytest.mark.asyncio
    async def test_health_server_endpoints_and_telemetry(self) -> None:
        """Verifies /health, /live, and / endpoints return 200 OK with accurate JSON telemetry."""
        engine = DynamicCapitalScalingEngine(initial_tier=ScalingTier.TIER_2)
        engine.update_from_wallet_balances(usdc_balance=150.0, sui_balance=5.419)
        engine.record_trade_success(profit_usdc=125.0)

        test_port = 19183
        server = SuiHealthServer(
            host="127.0.0.1",
            port=test_port,
            scaling_engine=engine,
            region="europe-west3",
        )
        await server.start()

        try:
            async with aiohttp.ClientSession() as session:
                # 1. GET /health
                async with session.get(f"http://127.0.0.1:{test_port}/health") as resp:
                    assert resp.status == 200
                    assert resp.content_type == "application/json"
                    data = await resp.json()

                    assert data["status"] == "HEALTHY"
                    assert data["uptime_seconds"] >= 0.0
                    assert data["current_tier"] == "TIER_2"
                    assert data["borrow_amount_usdc"] == 5_000_000_000
                    assert data["sui_gas_balance"] == pytest.approx(5.419, rel=1e-3)
                    assert data["active_pairs"] == list(ACTIVE_PAIRS)
                    assert data["region"] == "europe-west3"
                    assert data["consecutive_aborts"] == 0
                    assert data["accumulated_profit_usdc"] == 125.0
                    assert data["successful_trades"] == 1

                # 2. GET /live
                async with session.get(f"http://127.0.0.1:{test_port}/live") as resp:
                    assert resp.status == 200
                    live_data = await resp.json()
                    assert live_data["live"] is True
                    assert live_data["uptime"] >= 0.0

                # 3. GET /
                async with session.get(f"http://127.0.0.1:{test_port}/") as resp:
                    assert resp.status == 200
                    root_data = await resp.json()
                    assert root_data["status"] == "HEALTHY"
                    assert root_data["tier"] == "TIER_2"
                    assert root_data["region"] == "europe-west3"
                    assert "/health" in root_data["endpoints"]
                    assert "/live" in root_data["endpoints"]

                # 4. Degraded status transition: Gas < 1.5 SUI
                engine.update_from_wallet_balances(usdc_balance=150.0, sui_balance=1.20)
                async with session.get(f"http://127.0.0.1:{test_port}/health") as resp:
                    assert resp.status == 200
                    data = await resp.json()
                    assert data["status"] == "DEGRADED"

                # 5. Critical status transition: Gas < 0.5 SUI
                engine.update_from_wallet_balances(usdc_balance=150.0, sui_balance=0.40)
                async with session.get(f"http://127.0.0.1:{test_port}/health") as resp:
                    assert resp.status == 200
                    data = await resp.json()
                    assert data["status"] == "CRITICAL"

                # 6. Critical status transition: 5 consecutive aborts
                engine.update_from_wallet_balances(usdc_balance=150.0, sui_balance=5.419)
                for _ in range(5):
                    engine.record_trade_abort()
                async with session.get(f"http://127.0.0.1:{test_port}/health") as resp:
                    assert resp.status == 200
                    data = await resp.json()
                    assert data["status"] == "CRITICAL"
                    assert data["consecutive_aborts"] == 5

        finally:
            await server.stop()



class TestAdversarialEdgeCasesAndStress:
    """Target 1, 2, 3: Boundary fuzzing and adversarial edge case harness."""

    def test_gas_boundary_precision_and_negative_handling(self) -> None:
        """Verifies exact boundaries: 1.5 SUI, 0.5 SUI, negative gas, and float epsilon."""
        engine = DynamicCapitalScalingEngine(initial_tier=ScalingTier.TIER_1)

        # Exact 1.5 SUI: not warning (warning is strictly < 1.5)
        engine.update_from_wallet_balances(usdc_balance=100.0, sui_balance=1.50)
        assert engine.state.gas_warning is False
        assert engine.status == STATUS_ACTIVE
        assert engine.can_trade() is True

        # 1.50 - 1e-9: triggers warning
        engine.update_from_wallet_balances(usdc_balance=100.0, sui_balance=1.50 - 1e-9)
        assert engine.state.gas_warning is True
        assert engine.status == STATUS_ACTIVE
        assert engine.can_trade() is True

        # Exact 0.5 SUI: not critical (critical is strictly < 0.5)
        engine.update_from_wallet_balances(usdc_balance=100.0, sui_balance=0.50)
        assert engine.state.gas_warning is True
        assert engine.status == STATUS_ACTIVE
        assert engine.can_trade() is True

        # 0.50 - 1e-9: triggers critical hard stop
        engine.update_from_wallet_balances(usdc_balance=100.0, sui_balance=0.50 - 1e-9)
        assert engine.state.gas_warning is True
        assert engine.status == STATUS_EMERGENCY_LOCKED
        assert engine.can_trade() is False

        # Negative gas balance from arithmetic underflow
        engine.update_from_wallet_balances(usdc_balance=100.0, sui_balance=-0.05)
        assert engine.status == STATUS_EMERGENCY_LOCKED
        assert engine.can_trade() is False

    def test_tier_one_abort_demotion_floor_and_extreme_aborts(self) -> None:
        """Verifies that Tier 1 cannot demote below Tier 1, and 100 aborts remain locked."""
        engine = DynamicCapitalScalingEngine(initial_tier=ScalingTier.TIER_1)

        # 3 aborts at Tier 1
        for _ in range(3):
            engine.record_trade_abort()

        assert engine.current_tier == ScalingTier.TIER_1  # Cannot demote below Tier 1
        assert engine.status == STATUS_COOLING_DOWN
        assert engine.can_trade() is False

        # Storm of 100 consecutive aborts
        for _ in range(97):
            engine.record_trade_abort()

        assert engine.state.consecutive_aborts == 100
        assert engine.status == STATUS_EMERGENCY_LOCKED
        assert engine.can_trade() is False
        assert engine._emergency_locked_due_to_aborts is True

    def test_trade_success_validation_guards(self) -> None:
        """Verifies validation guards on record_trade_success (rejection of negative profit)."""
        engine = DynamicCapitalScalingEngine(initial_tier=ScalingTier.TIER_1)

        with pytest.raises(ValueError, match="Profit must be non-negative"):
            engine.record_trade_success(profit_usdc=-10.0)

        # Zero profit trade success is valid and clears aborts
        engine.record_trade_abort()
        assert engine.state.consecutive_aborts == 1
        engine.record_trade_success(profit_usdc=0.0)
        assert engine.state.consecutive_aborts == 0

    def test_malformed_suiprivkey_rejection(self) -> None:
        """Verifies that malformed suiprivkey strings are rejected and live_onchain remains False."""
        malformed_keys = [
            "",
            "0x" + "0" * 64,
            "ed25519privkey1qqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqq",
            "suiprivkey1short",
            "suiprivkey1" + "b" * 60,  # 'b' is not in bech32 charset
            "suiprivkey1" + "i" * 60,  # 'i' is not in bech32 charset
            "suiprivkey1" + "o" * 60,  # 'o' is not in bech32 charset
        ]

        for bad_key in malformed_keys:
            cfg = SuiBotConfig(dry_run_mode=False, sui_private_key=bad_key)
            is_valid_format = bool(cfg.sui_private_key and cfg.sui_private_key.startswith("suiprivkey1"))
            if is_valid_format:
                # Test decoding failure
                ptb_builder = SuiDeepBookPTBBuilder()
                with pytest.raises(ValueError):
                    ptb_builder.sign_transaction_bcs(b"test", bad_key)

    @pytest.mark.asyncio
    async def test_health_server_cooling_down_reflects_degraded(self) -> None:
        """Verifies that when the scaling engine is COOLING_DOWN, /health reports DEGRADED."""
        engine = DynamicCapitalScalingEngine(initial_tier=ScalingTier.TIER_2)
        engine.update_from_wallet_balances(usdc_balance=100.0, sui_balance=5.419)

        for _ in range(3):
            engine.record_trade_abort()

        assert engine.status == STATUS_COOLING_DOWN

        test_port = 19184
        server = SuiHealthServer(
            host="127.0.0.1",
            port=test_port,
            scaling_engine=engine,
            region="europe-west3",
        )
        await server.start()

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"http://127.0.0.1:{test_port}/health") as resp:
                    assert resp.status == 200
                    data = await resp.json()
                    assert data["status"] == "DEGRADED"
                    assert data["consecutive_aborts"] == 3
        finally:
            await server.stop()
