"""Comprehensive Automated Unit & Integration Tests for Milestone 2:
Requirement R2: Analytical Q* Optimal Sizing & Dynamic Tranches
Requirement R3: Pair Route Prioritization (DEEP/SUI over DEEP/USDC) & DeepBook Vault Balance Protection

Tests cover:
1. Closed-form analytical Q* formula mathematical correctness for quote and base borrow.
2. Dynamic tranche bounds clamping for all 4 pairs:
   - DEEP/USDC clamped to $100 - $150 USDC (thin pool TVL ~10k USDC).
   - DEEP/SUI scaled up to $1,000 - $4,000 USD (deep liquidity, 0 bps DB fee).
   - SUI/USDC scaled $1,000 - $10,000 USDC based on capital tier.
   - CETUS/SUI clamped to $100 - $250 USD (~50 - 120 SUI).
3. Depth capping (85%) and Vault capping (90%) with $25 floor.
4. DeepBook vault balance queries (BCS simulation mock, object mock, default empirical fallback).
5. Preflight vault balance validation eliminating Move abort code 2 (EInsufficientVaultBalance).
6. Pair route prioritization: DEEP/SUI strictly prioritized over DEEP/USDC.
7. End-to-end bot runner scan_once integration with vault protection and route prioritization.
"""

from __future__ import annotations

import asyncio
import math
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

from venues.base import OrderExecutionResult
from venues.sui_bot_runner import (
    ACTIVE_PAIRS,
    SuiBotConfig,
    SuiBotRunner,
)
from venues.sui_deepbook_venue import (
    DEFAULT_DEEPBOOK_VAULT_BALANCES,
    DEEP_SUI_POOL_ID,
    DEEP_USDC_POOL_ID,
    SUI_PAIRS_CONFIG,
    SUI_USDC_POOL_ID,
    CETUS_SUI_POOL_ID,
    SuiDeepBookVenue,
    SuiGraphQLClient,
)
from venues.sui_ptb_validator import SuiPTBPreflightValidator
from venues.sui_scaling_engine import (
    DEFAULT_CETUS_POOL_LIQUIDITY,
    DEFAULT_DYNAMIC_TRANCHE_BOUNDS_USD,
    DEFAULT_PAIR_FEE_HURDLE_BPS,
    DynamicCapitalScalingEngine,
    ScalingTier,
    calculate_optimal_borrow_q_star,
    check_deepbook_vault_balance,
    prioritize_opportunities,
    prioritize_pairs,
)


# ==============================================================================
# 1. ANALYTICAL Q* FORMULA MATHEMATICAL INTEGRITY TESTS
# ==============================================================================

def test_calculate_optimal_borrow_q_star_formula_quote_borrow():
    """Validates analytical optimal sizing formula Q* = 0.5 * (Delta_P - fees) * L * sqrt(P0)."""
    # Parameters:
    # spread_bps = 50.0 (0.0050)
    # fee_bps = 10.0 (0.0010)
    # net_spread = 40.0 bps = 0.0040
    # liquidity L = 1_000_000_000
    # sqrt_price = 1.0
    # Q* = 0.5 * 0.0040 * 1_000_000_000 * 1.0 = 2_000_000
    q_star = calculate_optimal_borrow_q_star(
        spread_bps=50.0,
        liquidity=1_000_000_000.0,
        sqrt_price=1.0,
        fee_bps=10.0,
    )
    assert q_star == 2_000_000


def test_calculate_optimal_borrow_q_star_formula_base_borrow():
    """Validates base borrow formula Q* = 0.5 * (Delta_P - fees) * L / sqrt(P0)."""
    # Parameters:
    # net_spread = 0.0040
    # L = 1_000_000_000
    # sqrt_price = 2.0
    # Q* = 0.5 * 0.0040 * 1_000_000_000 / 2.0 = 1_000_000
    q_star = calculate_optimal_borrow_q_star(
        spread_bps=50.0,
        liquidity=1_000_000_000.0,
        sqrt_price=2.0,
        fee_bps=10.0,
        is_base_borrow=True,
    )
    assert q_star == 1_000_000


def test_calculate_optimal_borrow_q_star_sub_hurdle_returns_zero():
    """Validates that spread below or equal to fee hurdle returns 0."""
    # spread 10.0 bps <= fee 10.0 bps
    assert calculate_optimal_borrow_q_star(spread_bps=10.0, liquidity=1e12, sqrt_price=1.0, fee_bps=10.0) == 0
    # spread 5.0 bps < fee 10.0 bps
    assert calculate_optimal_borrow_q_star(spread_bps=5.0, liquidity=1e12, sqrt_price=1.0, fee_bps=10.0) == 0
    # negative spread
    assert calculate_optimal_borrow_q_star(spread_bps=-20.0, liquidity=1e12, sqrt_price=1.0, fee_bps=10.0) == 0


def test_calculate_optimal_borrow_q_star_q64_sqrt_price_decoding():
    """Validates decoding of Cetus Q64.64 current_sqrt_price representation."""
    # sqrt(0.10) in Q64.64
    raw_sqrt = 0.10 ** 0.5  # ~0.316227766
    q64_val = int(raw_sqrt * (1 << 64))

    q_from_float = calculate_optimal_borrow_q_star(
        spread_bps=50.0, liquidity=2.4023e11, sqrt_price=raw_sqrt, fee_bps=6.0
    )
    q_from_q64 = calculate_optimal_borrow_q_star(
        spread_bps=50.0, liquidity=2.4023e11, sqrt_price=q64_val, fee_bps=6.0
    )
    # Difference due to round-off should be <= 1 unit
    assert abs(q_from_float - q_from_q64) <= 1


# ==============================================================================
# 2. DYNAMIC TRANCHE CLAMPING TESTS FOR ALL 4 PAIRS
# ==============================================================================

def test_dynamic_tranche_deep_usdc_clamped_100_to_150_usdc():
    """Validates that DEEP/USDC is strictly clamped to $100 - $150 USDC to eliminate Move VM slippage."""
    engine = DynamicCapitalScalingEngine()

    # Case 1: Large spread (200 bps) with thin pool L=2.40e11 -> raw Q* would exceed $300, clamped to $150 USDC
    amt_high_spread = engine.get_current_borrow_amount(
        "DEEP/USDC",
        spread_bps=200.0,
        liquidity=2.4023e11,
        sqrt_price=0.10 ** 0.5,
        fee_bps=6.0,
    )
    assert amt_high_spread == 150_000_000  # Exactly $150 USDC max tranche

    # Case 2: Moderate spread (35 bps) -> net_spread = 29 bps -> raw Q* ~= $110 USDC -> inside [$100, $150]
    amt_mid_spread = engine.get_current_borrow_amount(
        "DEEP/USDC",
        spread_bps=35.0,
        liquidity=2.4023e11,
        sqrt_price=0.10 ** 0.5,
        fee_bps=6.0,
    )
    assert 100_000_000 <= amt_mid_spread <= 150_000_000

    # Case 3: Small positive spread (10 bps) -> net_spread = 4 bps -> clamped to min tranche $100 USDC
    amt_low_spread = engine.get_current_borrow_amount(
        "DEEP/USDC",
        spread_bps=10.0,
        liquidity=2.4023e11,
        sqrt_price=0.10 ** 0.5,
        fee_bps=6.0,
    )
    assert amt_low_spread == 100_000_000  # Exactly $100 USDC min tranche

    # Case 4: Sub-hurdle spread (5 bps <= 6.0 fee) -> returns 0
    amt_sub_hurdle = engine.get_current_borrow_amount(
        "DEEP/USDC",
        spread_bps=5.0,
        fee_bps=6.0,
    )
    assert amt_sub_hurdle == 0


def test_dynamic_tranche_deep_sui_scales_1000_to_4000_usd():
    """Validates that DEEP/SUI scales up to $1,000 - $4,000 USD equivalent in SUI."""
    engine = DynamicCapitalScalingEngine()
    sui_price = 2.0  # $2.00 / SUI

    # Min tranche: $1,000 USD / 2.0 = 500 SUI = 500_000_000_000 MIST
    # Max tranche: $4,000 USD / 2.0 = 2,000 SUI = 2_000_000_000_000 MIST

    # Large spread (250 bps) -> scales and clamped to max tranche 2,000 SUI ($4,000 USD)
    amt_high = engine.get_current_borrow_amount(
        "DEEP/SUI",
        sui_spot_price=sui_price,
        spread_bps=250.0,
        liquidity=9.8371e14,
        sqrt_price=0.05 ** 0.5,
        fee_bps=6.0,
    )
    assert amt_high == 2_000_000_000_000  # Exactly 2,000 SUI ($4,000 USD)

    # Intermediate spread (150 bps) -> dynamically scales inside [$1,000, $4,000] USD
    amt_mid = engine.get_current_borrow_amount(
        "DEEP/SUI",
        sui_spot_price=sui_price,
        spread_bps=150.0,
        liquidity=9.8371e14,
        sqrt_price=0.05 ** 0.5,
        fee_bps=6.0,
    )
    assert 500_000_000_000 < amt_mid < 2_000_000_000_000

    # Moderate spread (20 bps) -> clamped to min tranche 500 SUI ($1,000 USD)
    amt_low = engine.get_current_borrow_amount(
        "DEEP/SUI",
        sui_spot_price=sui_price,
        spread_bps=20.0,
        liquidity=9.8371e14,
        sqrt_price=0.05 ** 0.5,
        fee_bps=6.0,
    )
    assert amt_low == 500_000_000_000  # Exactly 500 SUI ($1,000 USD)

    # At $0.81 / SUI (survey 3 reference):
    # $4,000 / 0.81 ~= 4,938 SUI
    amt_sui_081 = engine.get_current_borrow_amount(
        "DEEP/SUI",
        sui_spot_price=0.81,
        spread_bps=500.0,
        liquidity=9.8371e14,
        sqrt_price=0.05 ** 0.5,
        fee_bps=6.0,
    )
    assert 4_900_000_000_000 <= amt_sui_081 <= 5_000_000_000_000


def test_dynamic_tranche_sui_usdc_scales_by_tier():
    """Validates that SUI/USDC scales $1,000 - $10,000 USDC based on capital tier."""
    engine = DynamicCapitalScalingEngine()

    # Tier 1 ceiling is $1,000 USDC
    amt_tier1 = engine.get_current_borrow_amount(
        "SUI/USDC",
        spread_bps=100.0,
        liquidity=7.1189e13,
        sqrt_price=2.0 ** 0.5,
        fee_bps=16.0,
    )
    assert amt_tier1 == 1_000_000_000  # $1,000 USDC

    # Tier 2 ceiling is $5,000 USDC
    engine.state.current_tier = ScalingTier.TIER_2
    amt_tier2 = engine.get_current_borrow_amount(
        "SUI/USDC",
        spread_bps=100.0,
        liquidity=7.1189e13,
        sqrt_price=2.0 ** 0.5,
        fee_bps=16.0,
    )
    assert amt_tier2 == 5_000_000_000  # $5,000 USDC

    # Tier 3 ceiling is $10,000 USDC
    engine.state.current_tier = ScalingTier.TIER_3
    amt_tier3 = engine.get_current_borrow_amount(
        "SUI/USDC",
        spread_bps=100.0,
        liquidity=7.1189e13,
        sqrt_price=2.0 ** 0.5,
        fee_bps=16.0,
    )
    assert amt_tier3 == 10_000_000_000  # $10,000 USDC


def test_dynamic_tranche_cetus_sui_clamped_100_to_250_usd():
    """Validates that CETUS/SUI is clamped to $100 - $250 USD (~50 - 120 SUI)."""
    engine = DynamicCapitalScalingEngine()
    sui_price = 2.0

    # $100 / 2.0 = 50 SUI = 50_000_000_000 MIST
    # $250 / 2.0 = 125 SUI = 125_000_000_000 MIST

    amt_high = engine.get_current_borrow_amount(
        "CETUS/SUI",
        sui_spot_price=sui_price,
        spread_bps=100.0,
        liquidity=1.2890e16,
        sqrt_price=0.16 ** 0.5,
        fee_bps=36.0,
    )
    assert amt_high == 125_000_000_000  # Clamped to $250 USD max (125 SUI)

    # With lower liquidity (5.0e14), raw Q* is ~40 SUI, so clamped to min tranche 50 SUI ($100 USD)
    amt_low = engine.get_current_borrow_amount(
        "CETUS/SUI",
        sui_spot_price=sui_price,
        spread_bps=40.0,
        liquidity=5.0e14,
        sqrt_price=0.16 ** 0.5,
        fee_bps=36.0,
    )
    assert amt_low == 50_000_000_000  # Clamped to $100 USD min (50 SUI)


# ==============================================================================
# 3. DEPTH CAPPING AND VAULT BALANCE PROTECTION CAPPING
# ==============================================================================

def test_depth_capping_and_vault_capping_interplay():
    """Validates that borrow amounts respect 85% depth cap and 90% vault balance cap."""
    engine = DynamicCapitalScalingEngine()

    # DEEP/USDC normal tranche is $150 USDC (150_000_000)
    # Orderbook depth is $120 USDC -> 85% depth is $102 USDC (102_000_000)
    amt_depth_capped = engine.get_current_borrow_amount(
        "DEEP/USDC",
        spread_bps=100.0,
        max_depth_quote=120.0,
    )
    assert amt_depth_capped == 102_000_000

    # Vault balance is only $80 USDC (80_000_000) -> 90% vault cap is $72 USDC (72_000_000)
    amt_vault_capped = engine.get_current_borrow_amount(
        "DEEP/USDC",
        spread_bps=100.0,
        vault_balance=80_000_000,
    )
    assert amt_vault_capped == 72_000_000

    # Interplay: Depth allows $102, but Vault allows $72 -> takes min ($72)
    amt_both = engine.get_current_borrow_amount(
        "DEEP/USDC",
        spread_bps=100.0,
        max_depth_quote=120.0,
        vault_balance=80_000_000,
    )
    assert amt_both == 72_000_000

    # When vault balance is insufficient to support $25 minimum floor ($20 vault * 0.9 = $18 < $25)
    amt_sub_floor = engine.get_current_borrow_amount(
        "DEEP/USDC",
        spread_bps=100.0,
        vault_balance=20_000_000,
    )
    assert amt_sub_floor == 0


def test_base_borrow_calculation():
    """Validates base borrow calculation mode (is_base_borrow=True)."""
    engine = DynamicCapitalScalingEngine()
    sui_price = 2.0

    # Borrow base (SUI) on SUI/USDC:
    # Tranche $1,000 USD / $2.00 = 500 SUI (500_000_000_000 MIST)
    amt_base = engine.get_current_borrow_amount(
        "SUI/USDC",
        sui_spot_price=sui_price,
        spread_bps=100.0,
        liquidity=7.1189e13,
        sqrt_price=2.0 ** 0.5,
        fee_bps=16.0,
        is_base_borrow=True,
    )
    assert amt_base == 500_000_000_000


# ==============================================================================
# 4. DEEPBOOK VAULT BALANCE QUERY & MOCK PARSING
# ==============================================================================

@pytest.mark.asyncio
async def test_get_deepbook_vault_balances_simulation_mock():
    """Validates get_deepbook_vault_balances parses returnValues from simulateTransaction."""
    client = SuiGraphQLClient()

    # Mock GraphQL simulation response
    mock_sim_response = {
        "data": {
            "simulateTransaction": {
                "outputs": [
                    {
                        "returnValues": [
                            {"value": {"json": "414767840000000"}},  # base
                            {"value": {"json": "484499220000"}},     # quote
                            {"value": {"json": "3372035000000"}},    # deep
                        ]
                    }
                ]
            }
        }
    }

    with patch.object(client, "execute", new_callable=AsyncMock, return_value=mock_sim_response), \
         patch.object(client, "get_gas_coin_and_price", new_callable=AsyncMock, return_value=({"address": "0x1", "version": 1, "digest": "3u8G"}, 100)):
        balances = await client.get_deepbook_vault_balances("SUI/USDC")

        assert balances["base_balance"] == 414_767_840_000_000
        assert balances["quote_balance"] == 484_499_220_000
        assert balances["deep_balance"] == 3_372_035_000_000

    await client.close()


@pytest.mark.asyncio
async def test_get_deepbook_vault_balances_empirical_fallback():
    """Validates get_deepbook_vault_balances falls back to verified empirical mainnet reserves."""
    client = SuiGraphQLClient()

    # Execute raises exception (simulating offline/mock network failure)
    with patch.object(client, "execute", side_effect=RuntimeError("Offline network")):
        balances = await client.get_deepbook_vault_balances("DEEP/SUI")

        expected = DEFAULT_DEEPBOOK_VAULT_BALANCES["DEEP/SUI"]
        assert balances["base_balance"] == expected["base_balance"]
        assert balances["quote_balance"] == expected["quote_balance"]
        assert balances["deep_balance"] == expected["deep_balance"]

    await client.close()


@pytest.mark.asyncio
async def test_check_deepbook_vault_balance_standalone():
    """Validates check_deepbook_vault_balance standalone helper."""
    balances = await check_deepbook_vault_balance("DEEP/USDC")
    assert balances["base_balance"] > 0
    assert balances["quote_balance"] > 0
    assert "deep_balance" in balances

    mock_client = AsyncMock()
    mock_client.get_deepbook_vault_balances.return_value = {
        "base_balance": 5538696000000,
        "quote_balance": 26892600000,
        "deep_balance": 70000,
    }
    mocked = await check_deepbook_vault_balance("DEEP/USDC", client=mock_client)
    assert mocked["base_balance"] == 5538696000000
    assert mocked["quote_balance"] == 26892600000


# ==============================================================================
# 5. PREFLIGHT VAULT BALANCE PROTECTION (ABORT CODE 2 PREVENTION)
# ==============================================================================

def test_validate_vault_balance_preflight():
    """Validates SuiPTBPreflightValidator.validate_vault_balance enforcing 90% vault cap."""
    validator = SuiPTBPreflightValidator()

    # CETUS/SUI quote vault has 135.80 SUI (135_800_000_000 MIST)
    # 90% cap is 122.22 SUI (122_220_000_000 MIST)
    vault_balances = {"base_balance": 1_000_000_000, "quote_balance": 135_800_000_000, "deep_balance": 70_000}

    # Case 1: Borrow 50 SUI (50_000_000_000) <= 90% cap -> Valid
    check_ok = validator.validate_vault_balance("CETUS/SUI", 50_000_000_000, vault_balances=vault_balances)
    assert check_ok["valid"] is True
    assert check_ok["error"] is None

    # Case 2: Borrow 130 SUI (130_000_000_000) > 90% cap -> Rejected with EInsufficientVaultBalance
    check_fail = validator.validate_vault_balance("CETUS/SUI", 130_000_000_000, vault_balances=vault_balances)
    assert check_fail["valid"] is False
    assert "EInsufficientVaultBalance (abort code 2)" in check_fail["error"]


def test_validate_atomic_ptb_generation_with_vault_balance_rejection():
    """Validates validate_atomic_ptb_generation rejects transactions violating vault balance cap."""
    validator = SuiPTBPreflightValidator()

    vault_balances = {"base_balance": 1000, "quote_balance": 100_000_000, "deep_balance": 100}
    # 90% cap is 90_000_000 micro-USDC ($90 USDC)
    # Attempting to borrow $100 USDC (100_000_000) fails validation
    res = validator.validate_atomic_ptb_generation(
        "DEEP/USDC",
        borrow_amount=100_000_000,
        vault_balances=vault_balances,
    )
    assert res["valid"] is False
    assert any("EInsufficientVaultBalance" in e for e in res["errors"])


# ==============================================================================
# 6. ROUTE PRIORITIZATION (DEEP/SUI OVER DEEP/USDC)
# ==============================================================================

def test_prioritize_pairs_orders_deep_sui_first():
    """Validates prioritize_pairs strictly places DEEP/SUI first and ahead of DEEP/USDC."""
    pairs = ["DEEP/USDC", "CETUS/SUI", "SUI/USDC", "DEEP/SUI"]
    ordered = prioritize_pairs(pairs)

    assert ordered[0] == "DEEP/SUI"
    assert ordered.index("DEEP/SUI") < ordered.index("DEEP/USDC")


def test_prioritize_opportunities_selects_deep_sui_over_deep_usdc():
    """Validates prioritize_opportunities prioritizes DEEP/SUI over DEEP/USDC when both profitable."""
    opp_deep_usdc = {
        "pair": "DEEP/USDC",
        "net_profit_usd": 15.0,
        "spread_bps": 50.0,
    }
    opp_deep_sui = {
        "pair": "DEEP/SUI",
        "net_profit_usd": 12.0,  # Even with slightly lower profit, DEEP/SUI prioritized due to 0 bps taker fee & 4000x depth
        "spread_bps": 30.0,
    }
    opp_sui_usdc = {
        "pair": "SUI/USDC",
        "net_profit_usd": 10.0,
        "spread_bps": 25.0,
    }

    candidates = [opp_deep_usdc, opp_sui_usdc, opp_deep_sui]
    prioritized = prioritize_opportunities(candidates)

    # Top priority must be DEEP/SUI
    assert prioritized[0]["pair"] == "DEEP/SUI"
    assert prioritized[1]["pair"] == "SUI/USDC"
    assert prioritized[2]["pair"] == "DEEP/USDC"


# ==============================================================================
# 7. BOT RUNNER INTEGRATION: ROUTE PRIORITIZATION & VAULT PROTECTION
# ==============================================================================

@pytest.mark.asyncio
async def test_bot_runner_vault_protection_skips_execution():
    """Validates that SuiBotRunner.scan_once skips execution when vault balance is insufficient."""
    config = SuiBotConfig(dry_run_mode=False)
    validator = SuiPTBPreflightValidator()
    runner = SuiBotRunner(config=config, validator=validator)
    runner.update_gas_balance(5.0)

    # Mock market spreads: CETUS/SUI has profitable spread, but vault is shallow (10 SUI)
    mock_spreads = {
        "CETUS/SUI": {
            "cetus_price": 0.16,
            "deepbook_price": 0.18,
            "deepbook_ask": 0.18,
            "forward_spread_bps": 1250.0,
            "reverse_spread_bps": 0.0,
            "bid_depth_quote": 500.0,
        },
        "SUI/USDC": {"cetus_price": 2.0, "deepbook_price": 2.0, "forward_spread_bps": 0.0, "reverse_spread_bps": 0.0},
        "DEEP/SUI": {"cetus_price": 0.05, "deepbook_price": 0.05, "forward_spread_bps": 0.0, "reverse_spread_bps": 0.0},
        "DEEP/USDC": {"cetus_price": 0.10, "deepbook_price": 0.10, "forward_spread_bps": 0.0, "reverse_spread_bps": 0.0},
    }

    # Mock shallow vault balance: 10 SUI (10_000_000_000 MIST) -> 90% cap is 9 SUI (< 25 SUI floor)
    mock_shallow_vault = {"base_balance": 1_000_000, "quote_balance": 10_000_000_000, "deep_balance": 100}

    with patch.object(runner, "poll_market_spreads", return_value=mock_spreads), \
         patch.object(validator.graphql_client, "get_deepbook_vault_balances", return_value=mock_shallow_vault), \
         patch.object(validator.venue, "submit_order", new_callable=AsyncMock) as mock_submit:
        results = await runner.scan_once()

        cetus_res = next(r for r in results if r["pair"] == "CETUS/SUI")
        # Vault protection triggered: status is SKIPPED_VAULT_PROTECTED and no live order submitted
        assert cetus_res["execution_status"] == "SKIPPED_VAULT_PROTECTED"
        mock_submit.assert_not_called()


@pytest.mark.asyncio
async def test_bot_runner_prioritizes_deep_sui_execution():
    """Validates that when both DEEP/SUI and DEEP/USDC are profitable, DEEP/SUI is executed first."""
    config = SuiBotConfig(dry_run_mode=False)
    validator = SuiPTBPreflightValidator()
    runner = SuiBotRunner(config=config, validator=validator)
    runner.update_gas_balance(5.0)

    # Both DEEP/SUI and DEEP/USDC have profitable spreads
    mock_spreads = {
        "DEEP/SUI": {
            "cetus_price": 0.05,
            "deepbook_price": 0.052,
            "deepbook_ask": 0.052,
            "forward_spread_bps": 400.0,
            "reverse_spread_bps": 0.0,
            "bid_depth_quote": 2000.0,
        },
        "DEEP/USDC": {
            "cetus_price": 0.10,
            "deepbook_price": 0.105,
            "deepbook_ask": 0.105,
            "forward_spread_bps": 500.0,
            "reverse_spread_bps": 0.0,
            "bid_depth_quote": 500.0,
        },
        "SUI/USDC": {"cetus_price": 2.0, "deepbook_price": 2.0, "forward_spread_bps": 0.0, "reverse_spread_bps": 0.0},
        "CETUS/SUI": {"cetus_price": 0.16, "deepbook_price": 0.16, "forward_spread_bps": 0.0, "reverse_spread_bps": 0.0},
    }

    mock_res = OrderExecutionResult(
        venue="sui_deepbook",
        order_id="PTB-FILLED-1",
        symbol="DEEP/SUI",
        side="BUY",
        price=0.052,
        size=500_000_000_000,
        fee_bps=0.0,
        rebate_bps=0.0,
        is_maker=False,
        status="FILLED",
        latency_ms=10.0,
        timestamp_ns=time.time_ns(),
    )

    submitted_pairs: List[str] = []

    async def mock_submit_order(params):
        submitted_pairs.append(params["symbol"])
        return mock_res

    with patch.object(runner, "poll_market_spreads", return_value=mock_spreads), \
         patch.object(validator.venue, "submit_order", side_effect=mock_submit_order):
        results = await runner.scan_once()

        # DEEP/SUI must be submitted before DEEP/USDC
        assert len(submitted_pairs) >= 2
        assert submitted_pairs[0] == "DEEP/SUI"
        assert submitted_pairs[1] == "DEEP/USDC"
