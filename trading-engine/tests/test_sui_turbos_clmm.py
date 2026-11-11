"""Unit and Integration Tests for Turbos Finance CLMM Multi-DEX Integration (Milestone 3 / Requirement R4).

Covers:
1. Turbos Protocol Constants & Mainnet Pool Registry across all 4 trading pairs
2. Q64.64 sqrt_price integer decoding and spot price mathematical precision
3. Atomic PTB Builder for Turbos CLMM (FORWARD swap_b_a_with_return_ & REVERSE swap_a_b_with_return_)
4. Move VM Dry-Run Simulation with Turbos fee deduction and Zero Leg Risk verification
5. Multi-DEX Real-Time Quote Scanner (Cetus vs Turbos net profitability comparison)
6. SuiPTBPreflightValidator structural sequence validation for Turbos
7. SuiBotRunner continuous scanning and order dispatch with Turbos
"""

import math
from unittest.mock import AsyncMock, patch
import pytest
from typing import Any, Dict

from venues.sui_deepbook_venue import (
    TURBOS_PACKAGE_ID,
    TURBOS_VERSIONED_ID,
    TURBOS_POOL_CONFIG_ID,
    TURBOS_FEE_5BPS_TYPE,
    TURBOS_FEE_15BPS_TYPE,
    TURBOS_FEE_30BPS_TYPE,
    MIN_SQRT_PRICE,
    MAX_SQRT_PRICE,
    SUI_CLOCK_OBJECT_ID,
    SUI_PAIRS_CONFIG,
    SHARED_OBJECT_INITIAL_VERSIONS,
    HotPotatoPTBParams,
    SuiDeepBookPTBBuilder,
    SuiDeepBookVenue,
    SuiGraphQLClient,
    calculate_turbos_spot_price,
)
from venues.sui_ptb_validator import SuiPTBPreflightValidator
from venues.sui_bot_runner import SuiBotConfig, SuiBotRunner


# ==============================================================================
# 1. Turbos Protocol Constants & Registry Tests
# ==============================================================================

def test_turbos_protocol_constants():
    """Verifies that Turbos package and protocol object constants match verified Sui Mainnet IDs."""
    assert TURBOS_PACKAGE_ID == "0xa5a0c25c79e428eba04fb98b3fb2a34db45ab26d4c8faf0d7e39d66a63891e64"
    assert TURBOS_VERSIONED_ID == "0xf1cf0e81048df168ebeb1b8030fad24b3e0b53ae827c25053fff0779c1445b6f"
    assert TURBOS_POOL_CONFIG_ID == "0xc294552b2765353bcafa7c359cd28fd6bc237662e5db8f09877558d81669170c"

    # Shared object initial versions
    assert SHARED_OBJECT_INITIAL_VERSIONS[TURBOS_VERSIONED_ID] == 1621135
    assert SHARED_OBJECT_INITIAL_VERSIONS["0x0df4f02d0e210169cb6d5aabd03c3058328c06f2c4dbb0804faa041159c78443"] == 426673878
    assert SHARED_OBJECT_INITIAL_VERSIONS["0xbca476e3c744648c65b1fae5551b86be8ad7f482ca9c2268dad1d6b4fd0e2635"] == 389633758
    assert SHARED_OBJECT_INITIAL_VERSIONS["0x198af6ff81028c6577e94465d534c4e2cfcbbab06a95724ece7011c55a9d1f5a"] == 599890732
    assert SHARED_OBJECT_INITIAL_VERSIONS["0xdf9d069bdfd51515aa0316698225a26444cbdf3cccd130a226b3ac81cfe2f606"] == 561404948


def test_turbos_pool_registry_all_four_pairs():
    """Verifies all 4 trading pairs have verified Turbos pool configurations."""
    expected_pools = {
        "SUI/USDC": {
            "pool_id": "0x0df4f02d0e210169cb6d5aabd03c3058328c06f2c4dbb0804faa041159c78443",
            "fee_bps": 5,
            "fee_type": TURBOS_FEE_5BPS_TYPE,
            "fee_rate": 0.0005,
            "base_dec": 9,
            "quote_dec": 6,
        },
        "DEEP/SUI": {
            "pool_id": "0xbca476e3c744648c65b1fae5551b86be8ad7f482ca9c2268dad1d6b4fd0e2635",
            "fee_bps": 30,
            "fee_type": TURBOS_FEE_30BPS_TYPE,
            "fee_rate": 0.0030,
            "base_dec": 6,
            "quote_dec": 9,
        },
        "DEEP/USDC": {
            "pool_id": "0x198af6ff81028c6577e94465d534c4e2cfcbbab06a95724ece7011c55a9d1f5a",
            "fee_bps": 15,
            "fee_type": TURBOS_FEE_15BPS_TYPE,
            "fee_rate": 0.0015,
            "base_dec": 6,
            "quote_dec": 6,
        },
        "CETUS/SUI": {
            "pool_id": "0xdf9d069bdfd51515aa0316698225a26444cbdf3cccd130a226b3ac81cfe2f606",
            "fee_bps": 30,
            "fee_type": TURBOS_FEE_30BPS_TYPE,
            "fee_rate": 0.0030,
            "base_dec": 9,
            "quote_dec": 9,
        },
    }

    for pair_name, expected in expected_pools.items():
        assert pair_name in SUI_PAIRS_CONFIG
        cfg = SUI_PAIRS_CONFIG[pair_name]
        assert cfg.turbos_pool_id == expected["pool_id"]
        assert cfg.turbos_fee_bps == expected["fee_bps"]
        assert cfg.turbos_fee_type == expected["fee_type"]
        assert cfg.turbos_fee_rate == pytest.approx(expected["fee_rate"])
        assert cfg.base_decimals == expected["base_dec"]
        assert cfg.quote_decimals == expected["quote_dec"]


# ==============================================================================
# 2. Q64.64 Spot Price Math Tests
# ==============================================================================

def test_turbos_q64_64_spot_price_calculation():
    """Tests Turbos spot price calculation from Q64.64 sqrt_price across all decimal scales."""
    # 1. SUI/USDC: base=9, quote=6 (decimal adjustment = 10^(9 - 6) = 1000)
    # Target price: P = 2.0 SUI/USDC
    # (sqrt_price / 2^64)^2 * 1000 = 2.0 => sqrt_price / 2^64 = sqrt(0.002)
    sui_usdc_sqrt_p = int(math.sqrt(2.0 / 1000.0) * (2 ** 64))
    calc_px = calculate_turbos_spot_price(sui_usdc_sqrt_p, decimals_a=9, decimals_b=6)
    assert calc_px == pytest.approx(2.0, rel=1e-6)

    # 2. DEEP/SUI: base=6, quote=9 (decimal adjustment = 10^(6 - 9) = 0.001)
    # Target price: P = 0.05 DEEP/SUI
    # (sqrt_price / 2^64)^2 * 0.001 = 0.05 => sqrt_price / 2^64 = sqrt(50.0)
    deep_sui_sqrt_p = int(math.sqrt(0.05 / 0.001) * (2 ** 64))
    calc_px = calculate_turbos_spot_price(deep_sui_sqrt_p, decimals_a=6, decimals_b=9)
    assert calc_px == pytest.approx(0.05, rel=1e-6)

    # 3. DEEP/USDC: base=6, quote=6 (decimal adjustment = 10^0 = 1.0)
    # Target price: P = 0.10 DEEP/USDC
    deep_usdc_sqrt_p = int(math.sqrt(0.10) * (2 ** 64))
    calc_px = calculate_turbos_spot_price(deep_usdc_sqrt_p, decimals_a=6, decimals_b=6)
    assert calc_px == pytest.approx(0.10, rel=1e-6)

    # 4. CETUS/SUI: base=9, quote=9 (decimal adjustment = 10^0 = 1.0)
    # Target price: P = 0.045 CETUS/SUI
    cetus_sui_sqrt_p = int(math.sqrt(0.045) * (2 ** 64))
    calc_px = calculate_turbos_spot_price(cetus_sui_sqrt_p, decimals_a=9, decimals_b=9)
    assert calc_px == pytest.approx(0.045, rel=1e-6)


def test_turbos_q64_64_spot_price_edge_cases():
    """Verifies robustness on invalid, zero, or extreme sqrt_price inputs."""
    # Zero or negative
    assert calculate_turbos_spot_price(0, 9, 6) == 0.0
    assert calculate_turbos_spot_price(-100, 9, 6) == 0.0
    assert calculate_turbos_spot_price("invalid", 9, 6) == 0.0
    assert calculate_turbos_spot_price(None, 9, 6) == 0.0

    # Minimum and Maximum sqrt_price
    min_px = calculate_turbos_spot_price(MIN_SQRT_PRICE, 9, 6)
    assert min_px > 0.0
    max_px = calculate_turbos_spot_price(MAX_SQRT_PRICE, 9, 6)
    assert max_px > min_px


# ==============================================================================
# 3. Atomic PTB Construction Tests (FORWARD & REVERSE)
# ==============================================================================

def test_turbos_ptb_builder_forward_route():
    """Verifies Turbos FORWARD PTB:
    Command 0: DeepBook borrow_flashloan_quote
    Command 1: Turbos swap_router::swap_b_a_with_return_ (MakeMoveVec wrapped)
    Command 2: BalanceManager deposit swapped base coin
    Command 3: DeepBook place_market_order sell base
    Command 4: BalanceManager withdraw_all quote proceeds
    Command 5: SplitCoins repayment
    Command 6: DeepBook return_flashloan_quote (Hot Potato quenched)
    Command 7: TransferObjects net profit
    """
    builder = SuiDeepBookPTBBuilder()
    params = HotPotatoPTBParams.from_pair(
        pair_name="SUI/USDC",
        flash_borrow_amount=1_000_000,
        balance_manager_id="0xBM1",
        sender_address="0xOPERATOR",
        route_direction="FORWARD",
        amm_target="turbos",
    )
    ptb = builder.build_atomic_arb_ptb(params)
    commands = ptb["commands"]

    assert len(commands) == 8

    # Command 0: Borrow flashloan quote
    assert commands[0]["type"] == "MoveCall"
    assert commands[0]["function"] == "borrow_flashloan_quote"
    assert commands[0]["arguments"][0]["Input"] == SUI_PAIRS_CONFIG["SUI/USDC"].deepbook_pool_id

    # Command 1: Turbos swap_b_a_with_return_
    c1 = commands[1]
    assert c1["type"] == "MoveCall"
    assert c1["package"] == TURBOS_PACKAGE_ID
    assert c1["module"] == "swap_router"
    assert c1["function"] == "swap_b_a_with_return_"
    args1 = c1["arguments"]
    assert args1[0]["Input"] == SUI_PAIRS_CONFIG["SUI/USDC"].turbos_pool_id
    # MakeMoveVec wrapping borrowed quote coin [0, 0]
    assert args1[1]["type"] == "MakeMoveVec"
    assert args1[1]["elements"][0]["NestedResult"] == [0, 0]
    assert args1[2]["Input"] == 1_000_000  # amount_specified
    assert args1[3]["Input"] == 0          # amount_threshold
    assert args1[4]["Input"] == MAX_SQRT_PRICE  # sqrt_price_limit for b_a
    assert args1[5]["Input"] is True       # is_exact_input
    assert args1[6]["Input"] == "0xOPERATOR"
    assert args1[7]["Input"] > 0           # deadline ms
    assert args1[8]["Input"] == SUI_CLOCK_OBJECT_ID
    assert args1[9]["Input"] == TURBOS_VERSIONED_ID

    # Type arguments: [base, quote, fee_type]
    assert c1["type_arguments"] == [
        SUI_PAIRS_CONFIG["SUI/USDC"].base_coin_type,
        SUI_PAIRS_CONFIG["SUI/USDC"].quote_coin_type,
        TURBOS_FEE_5BPS_TYPE,
    ]

    # Command 2: Deposit base coin into BalanceManager
    assert commands[2]["function"] == "deposit"
    assert commands[2]["arguments"][1]["NestedResult"] == [1, 0]

    # Command 3: DeepBook place_market_order sell base
    assert commands[3]["function"] == "place_market_order"
    assert commands[3]["arguments"][4]["Input"] is False  # Sell base

    # Command 4: BalanceManager withdraw_all quote
    assert commands[4]["function"] == "withdraw_all"

    # Command 5: SplitCoins repayment
    assert commands[5]["type"] == "SplitCoins"
    assert commands[5]["coin"]["NestedResult"] == [4, 0]
    assert commands[5]["amounts"][0]["Input"] == 1_000_000

    # Command 6: DeepBook return_flashloan_quote (Hot Potato Quench)
    assert commands[6]["function"] == "return_flashloan_quote"
    assert commands[6]["arguments"][1]["NestedResult"] == [5, 0]  # Repayment coin
    assert commands[6]["arguments"][2]["NestedResult"] == [0, 1]  # Hot Potato receipt

    # Command 7: TransferObjects net profit
    assert commands[7]["type"] == "TransferObjects"
    assert commands[7]["objects"][0]["NestedResult"] == [4, 0]
    assert commands[7]["recipient"]["Input"] == "0xOPERATOR"


def test_turbos_ptb_builder_reverse_route():
    """Verifies Turbos REVERSE PTB:
    Command 0: DeepBook borrow_flashloan_quote
    Command 1: BalanceManager deposit borrowed quote coin [0, 0]
    Command 2: DeepBook place_market_order buy base (is_bid=True)
    Command 3: BalanceManager withdraw_all base coin
    Command 4: Turbos swap_router::swap_a_b_with_return_ (MakeMoveVec wrapped [3, 0])
    Command 5: SplitCoins repayment
    Command 6: DeepBook return_flashloan_quote (Hot Potato quenched)
    Command 7: TransferObjects net profit
    """
    builder = SuiDeepBookPTBBuilder()
    params = HotPotatoPTBParams.from_pair(
        pair_name="DEEP/SUI",
        flash_borrow_amount=500_000_000,
        balance_manager_id="0xBM_REV",
        sender_address="0xOPERATOR_REV",
        route_direction="REVERSE",
        amm_target="turbos",
    )
    ptb = builder.build_atomic_arb_ptb(params)
    commands = ptb["commands"]

    assert len(commands) == 8

    # Command 0: Borrow flashloan quote
    assert commands[0]["function"] == "borrow_flashloan_quote"

    # Command 1: Deposit quote to BalanceManager
    assert commands[1]["function"] == "deposit"
    assert commands[1]["arguments"][1]["NestedResult"] == [0, 0]

    # Command 2: DeepBook market buy base (lifting ask)
    assert commands[2]["function"] == "place_market_order"
    assert commands[2]["arguments"][4]["Input"] is True  # Bid / Buy base

    # Command 3: Withdraw base coin from BalanceManager
    assert commands[3]["function"] == "withdraw_all"
    assert commands[3]["type_arguments"] == [SUI_PAIRS_CONFIG["DEEP/SUI"].base_coin_type]

    # Command 4: Turbos swap_a_b_with_return_
    c4 = commands[4]
    assert c4["type"] == "MoveCall"
    assert c4["package"] == TURBOS_PACKAGE_ID
    assert c4["module"] == "swap_router"
    assert c4["function"] == "swap_a_b_with_return_"
    args4 = c4["arguments"]
    assert args4[0]["Input"] == SUI_PAIRS_CONFIG["DEEP/SUI"].turbos_pool_id
    assert args4[1]["type"] == "MakeMoveVec"
    assert args4[1]["elements"][0]["NestedResult"] == [3, 0]  # Withdrawn base coin
    assert args4[4]["Input"] == MIN_SQRT_PRICE  # sqrt_price_limit for a_b
    assert args4[5]["Input"] is True       # is_exact_input
    assert args4[6]["Input"] == "0xOPERATOR_REV"
    assert args4[8]["Input"] == SUI_CLOCK_OBJECT_ID
    assert args4[9]["Input"] == TURBOS_VERSIONED_ID

    # Command 5: SplitCoins repayment
    assert commands[5]["type"] == "SplitCoins"
    assert commands[5]["coin"]["NestedResult"] == [4, 0]

    # Command 6: Quench Hot Potato
    assert commands[6]["function"] == "return_flashloan_quote"
    assert commands[6]["arguments"][1]["NestedResult"] == [5, 0]
    assert commands[6]["arguments"][2]["NestedResult"] == [0, 1]

    # Command 7: TransferObjects net profit
    assert commands[7]["type"] == "TransferObjects"
    assert commands[7]["objects"][0]["NestedResult"] == [4, 0]


# ==============================================================================
# 4. SuiPTBPreflightValidator Structural Validation Tests
# ==============================================================================

def test_ptb_validator_all_pairs_turbos_forward_and_reverse():
    """Validates that SuiPTBPreflightValidator verifies Turbos PTBs for all 4 pairs."""
    validator = SuiPTBPreflightValidator(
        operator_address="0x5621a8e7b3014a938de8ff05e7144e53ec9103c20c0dd2802f88cfb620ceecf3",
        balance_manager_id="0x0000000000000000000000000000000000000000000000000000000000000001",
    )

    for pair_name in ("SUI/USDC", "DEEP/SUI", "DEEP/USDC", "CETUS/SUI"):
        # Test FORWARD
        rep_fwd = validator.validate_atomic_ptb_generation(
            pair_name=pair_name,
            route_direction="FORWARD",
            amm_target="turbos",
        )
        assert rep_fwd["valid"] is True, f"FORWARD validation failed for {pair_name}: {rep_fwd['errors']}"
        assert rep_fwd["strict_sequence_verified"] is True
        assert rep_fwd["turbos_pool_id_verified"] is True
        assert rep_fwd["hot_potato_quenched"] is True
        assert rep_fwd["amm_target"] == "turbos"

        # Test REVERSE
        rep_rev = validator.validate_atomic_ptb_generation(
            pair_name=pair_name,
            route_direction="REVERSE",
            amm_target="turbos",
        )
        assert rep_rev["valid"] is True, f"REVERSE validation failed for {pair_name}: {rep_rev['errors']}"
        assert rep_rev["strict_sequence_verified"] is True
        assert rep_rev["turbos_pool_id_verified"] is True
        assert rep_rev["hot_potato_quenched"] is True
        assert rep_rev["amm_target"] == "turbos"


# ==============================================================================
# 5. Move VM Dry-Run Simulation Tests with Zero Leg Risk
# ==============================================================================

def test_turbos_dry_run_profitable_and_sub_hurdle():
    """Tests Move VM dry-run execution on Turbos:
    1. Profitable spread captures net profit.
    2. Sub-hurdle spread aborts cleanly with zero_leg_risk_preserved=True and state_mutations=0.
    """
    venue = SuiDeepBookVenue()
    builder = SuiDeepBookPTBBuilder()

    # Case 1: Profitable spread on SUI/USDC (100 bps spread vs 5 bps Turbos fee)
    params = HotPotatoPTBParams.from_pair(
        pair_name="SUI/USDC",
        flash_borrow_amount=1_000_000_000,  # 1,000 USDC
        balance_manager_id="0xBM",
        sender_address="0xOP",
        route_direction="FORWARD",
        amm_target="turbos",
    )
    ptb = builder.build_atomic_arb_ptb(params)

    # Base price: 2.0. DeepBook bid: 2.02 (100 bps spread). AMM swap out: 2.0.
    sim_profit = venue.simulate_dry_run(
        ptb=ptb,
        deepbook_bid_px=2.02,
        amm_swap_out_px=2.0,
        borrow_amount=1_000_000_000,
        pair="SUI/USDC",
        deduct_fees=True,
        route_direction="FORWARD",
        amm_target="turbos",
    )
    assert sim_profit["status"] == "SUCCESS"
    assert sim_profit["net_profit_quote"] > 0.0
    assert sim_profit["zero_leg_risk_preserved"] is True
    assert sim_profit["state_mutations"] == 8

    # Case 2: Sub-hurdle spread on SUI/USDC (2 bps spread vs 5 bps Turbos fee)
    sim_abort = venue.simulate_dry_run(
        ptb=ptb,
        deepbook_bid_px=2.0004,
        amm_swap_out_px=2.0,
        borrow_amount=1_000_000_000,
        pair="SUI/USDC",
        deduct_fees=True,
        route_direction="FORWARD",
        amm_target="turbos",
    )
    assert sim_abort["status"] == "ABORTED"
    assert sim_abort["zero_leg_risk_preserved"] is True
    assert sim_abort["state_mutations"] == 0
    assert sim_abort["shortfall_native"] > 0


def test_validator_simulate_ptb_dry_run_with_turbos():
    """Verifies SuiPTBPreflightValidator.simulate_ptb_dry_run with amm_target='turbos'."""
    validator = SuiPTBPreflightValidator(
        operator_address="0x5621a8e7b3014a938de8ff05e7144e53ec9103c20c0dd2802f88cfb620ceecf3",
    )

    # Profitable dry run on Turbos
    rep_profit = validator.simulate_ptb_dry_run(
        pair_name="SUI/USDC",
        borrow_amount=1_000_000_000,
        spread_bps=120.0,
        amm_target="turbos",
    )
    assert rep_profit["status"] == "SUCCESS"
    assert rep_profit["net_profit"] > 0.0
    assert rep_profit["amm_target"] == "turbos"
    assert rep_profit["zero_leg_risk_preserved"] is True

    # Unprofitable dry run on Turbos
    rep_abort = validator.simulate_ptb_dry_run(
        pair_name="SUI/USDC",
        borrow_amount=1_000_000_000,
        spread_bps=2.0,
        amm_target="turbos",
    )
    assert rep_abort["status"] == "ABORTED"
    assert rep_abort["amm_target"] == "turbos"
    assert rep_abort["zero_leg_risk_preserved"] is True


# ==============================================================================
# 6. Multi-DEX Real-Time Quote Scanner Tests
# ==============================================================================

@pytest.mark.asyncio
async def test_multi_dex_quote_scanner_opportunity_selection():
    """Tests SuiGraphQLClient multi-DEX scanning and opportunity selection between Cetus and Turbos."""
    client = SuiGraphQLClient()

    # Pre-calculate sqrt_prices
    # Cetus price = 2.00 (sqrt_price = 18446744073709551616)
    cetus_sqrt_p = "18446744073709551616"

    # Turbos SUI/USDC sqrt_price for price = 1.99 (50 bps lower AMM price => 50 bps higher forward spread)
    turbos_sqrt_p = str(int(math.sqrt(1.99 / 1000.0) * (2 ** 64)))

    mock_graphql_data = {
        "data": {
            # DeepBook SUI/USDC
            "d_sui_usdc": {
                "asMoveObject": {
                    "contents": {
                        "json": {
                            "pool_id": SUI_PAIRS_CONFIG["SUI/USDC"].deepbook_pool_id,
                            "bids": [{"price": "2010000000", "depth": "50000000000"}],  # 2.01 bid
                            "asks": [{"price": "2020000000", "depth": "50000000000"}],  # 2.02 ask
                        }
                    }
                }
            },
            # Cetus SUI/USDC (price = 2.00, fee = 25 bps => forward spread = (2.01-2.00)/2.00 = 50 bps, net = 25 bps)
            "p_sui_usdc": {
                "asMoveObject": {
                    "contents": {
                        "json": {
                            "current_sqrt_price": cetus_sqrt_p,
                            "liquidity": "100000000000",
                        }
                    }
                }
            },
            # Turbos SUI/USDC (price = 1.99, fee = 5 bps => forward spread = (2.01-1.99)/1.99 = 100 bps, net = 95 bps)
            "t_sui_usdc": {
                "asMoveObject": {
                    "contents": {
                        "json": {
                            "sqrt_price": turbos_sqrt_p,
                            "liquidity": "200000000000",
                        }
                    }
                }
            },
        }
    }

    # Query with mock data
    with patch.object(client, "execute", new_callable=AsyncMock) as mock_exec:
        mock_exec.return_value = mock_graphql_data
        spreads = await client.query_live_market_spreads()

        sui_market = spreads["SUI/USDC"]
        assert "turbos_price" in sui_market
        assert sui_market["turbos_price"] == pytest.approx(1.99, rel=1e-3)
        assert sui_market["best_amm"] == "turbos"
        assert sui_market["net_spread_bps"] > sui_market["cetus_net_spread_bps"]
        assert sui_market["amm_target"] == "turbos"

        # Enforce Cetus explicit selection
        spreads_cetus = await client.query_live_market_spreads(amm_target="cetus")
        assert spreads_cetus["SUI/USDC"]["best_amm"] == "cetus"
        assert spreads_cetus["SUI/USDC"]["amm_target"] == "cetus"

        # Enforce Turbos explicit selection
        spreads_turbos = await client.query_live_market_spreads(amm_target="turbos")
        assert spreads_turbos["SUI/USDC"]["best_amm"] == "turbos"
        assert spreads_turbos["SUI/USDC"]["amm_target"] == "turbos"


# ==============================================================================
# 7. SuiBotRunner Integration Tests
# ==============================================================================

@pytest.mark.asyncio
async def test_bot_runner_turbos_scanning_and_execution():
    """Tests SuiBotRunner scanning loop selecting and dispatching Turbos opportunities."""
    config = SuiBotConfig(
        dry_run_mode=True,
        amm_target="turbos",
    )
    runner = SuiBotRunner(config=config)

    # Verify config parsed
    assert runner.config.amm_target == "turbos"
    safe_dict = runner.config.to_safe_dict()
    assert safe_dict["amm_target"] == "turbos"

    # Perform single scan pass
    results = await runner.scan_once()
    assert len(results) == len(SUI_PAIRS_CONFIG)

    for r in results:
        assert r["amm_target"] == "turbos"
        assert r["zero_leg_risk_preserved"] is True


# ==============================================================================
# 8. Granular Unit & Adversarial Corruption Tests for Turbos
# ==============================================================================

@pytest.mark.asyncio
async def test_turbos_get_pool_spot_price_direct_graphql():
    """Directly tests SuiGraphQLClient.get_turbos_pool_spot_price method."""
    client = SuiGraphQLClient()
    sqrt_p = int(math.sqrt(2.0 / 1000.0) * (2 ** 64))
    mock_resp = {
        "data": {
            "object": {
                "asMoveObject": {
                    "contents": {
                        "json": {
                            "sqrt_price": str(sqrt_p),
                        }
                    }
                }
            }
        }
    }
    with patch.object(client, "execute", new_callable=AsyncMock) as mock_exec:
        mock_exec.return_value = mock_resp
        px = await client.get_turbos_pool_spot_price(
            pool_id=SUI_PAIRS_CONFIG["SUI/USDC"].turbos_pool_id,
            pair_name="SUI/USDC",
        )
        assert px == pytest.approx(2.0, rel=1e-3)


def test_turbos_ptb_validator_adversarial_corruptions():
    """Verifies that SuiPTBPreflightValidator detects any structural tampering with Turbos PTBs."""
    validator = SuiPTBPreflightValidator(
        operator_address="0x5621a8e7b3014a938de8ff05e7144e53ec9103c20c0dd2802f88cfb620ceecf3",
    )

    # 1. Tamper with builder output: corrupt package ID
    class TamperedBuilder(SuiDeepBookPTBBuilder):
        def build_atomic_arb_ptb(self, params):
            ptb = super().build_atomic_arb_ptb(params)
            # Corrupt package ID of command 1
            ptb["commands"][1]["package"] = "0xBADCAFE"
            return ptb

    bad_validator = SuiPTBPreflightValidator(
        operator_address="0x5621a8e7b3014a938de8ff05e7144e53ec9103c20c0dd2802f88cfb620ceecf3",
        ptb_builder=TamperedBuilder(),
    )
    rep = bad_validator.validate_atomic_ptb_generation("SUI/USDC", amm_target="turbos")
    assert rep["valid"] is False
    assert any("Turbos swap_router::swap_b_a_with_return_" in err for err in rep["errors"])

    # 2. Tamper with builder output: missing Hot Potato quench
    class NoQuenchBuilder(SuiDeepBookPTBBuilder):
        def build_atomic_arb_ptb(self, params):
            ptb = super().build_atomic_arb_ptb(params)
            # Corrupt command 6
            ptb["commands"][6]["arguments"][2]["NestedResult"] = [9, 9]
            return ptb

    no_quench_val = SuiPTBPreflightValidator(
        operator_address="0x5621a8e7b3014a938de8ff05e7144e53ec9103c20c0dd2802f88cfb620ceecf3",
        ptb_builder=NoQuenchBuilder(),
    )
    rep_no_quench = no_quench_val.validate_atomic_ptb_generation("SUI/USDC", amm_target="turbos")
    assert rep_no_quench["valid"] is False
    assert any("Hot Potato receipt" in err for err in rep_no_quench["errors"])


def test_turbos_dry_run_all_four_pairs():
    """Verifies dry-run simulation for both forward and reverse on all 4 pairs with Turbos."""
    venue = SuiDeepBookVenue()
    builder = SuiDeepBookPTBBuilder()

    for pair_name, cfg in SUI_PAIRS_CONFIG.items():
        # FORWARD
        fwd_params = HotPotatoPTBParams.from_pair(
            pair_name=pair_name,
            flash_borrow_amount=cfg.default_borrow_amount,
            balance_manager_id="0xBM",
            sender_address="0xOP",
            route_direction="FORWARD",
            amm_target="turbos",
        )
        ptb_fwd = builder.build_atomic_arb_ptb(fwd_params)
        res_fwd = venue.simulate_dry_run(
            ptb=ptb_fwd,
            deepbook_bid_px=2.05,
            amm_swap_out_px=2.00,
            borrow_amount=cfg.default_borrow_amount,
            pair=pair_name,
            deduct_fees=True,
            route_direction="FORWARD",
            amm_target="turbos",
        )
        assert res_fwd["zero_leg_risk_preserved"] is True
        assert res_fwd["status"] in ("SUCCESS", "ABORTED")

        # REVERSE
        rev_params = HotPotatoPTBParams.from_pair(
            pair_name=pair_name,
            flash_borrow_amount=cfg.default_borrow_amount,
            balance_manager_id="0xBM",
            sender_address="0xOP",
            route_direction="REVERSE",
            amm_target="turbos",
        )
        ptb_rev = builder.build_atomic_arb_ptb(rev_params)
        res_rev = venue.simulate_dry_run(
            ptb=ptb_rev,
            deepbook_bid_px=2.00,
            amm_swap_out_px=2.05,
            borrow_amount=cfg.default_borrow_amount,
            pair=pair_name,
            deduct_fees=True,
            route_direction="REVERSE",
            deepbook_ask_px=2.00,
            amm_target="turbos",
        )
        assert res_rev["zero_leg_risk_preserved"] is True
        assert res_rev["status"] in ("SUCCESS", "ABORTED")


@pytest.mark.asyncio
async def test_multi_dex_scanner_missing_turbos_backward_compatibility():
    """Ensures 100% backward compatibility when GraphQL response has no t_* objects."""
    client = SuiGraphQLClient()
    mock_data_no_turbos = {
        "data": {
            "p_sui_usdc": {
                "asMoveObject": {
                    "contents": {
                        "json": {
                            "current_sqrt_price": "18446744073709551616",
                            "liquidity": "100000000000",
                        }
                    }
                }
            },
            "d_sui_usdc": {"dynamicFields": {"nodes": []}},
        }
    }
    with patch.object(client, "execute", new_callable=AsyncMock) as mock_exec:
        mock_exec.return_value = mock_data_no_turbos
        spreads = await client.query_live_market_spreads()
        assert "SUI/USDC" in spreads
        sui_m = spreads["SUI/USDC"]
        assert sui_m["best_amm"] == "cetus"
        assert sui_m["turbos_price"] == 0.0

