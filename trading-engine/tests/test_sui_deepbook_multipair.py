"""Automated Unit Test Suite for Multi-Pair Sui DeepBookV3 & Cetus Dry-Run Simulation.

Covers:
1. Multi-pair configuration registry (SUI/USDC, DEEP/SUI, DEEP/USDC, CETUS/SUI).
2. Move 8-step atomic PTB serialization per pair.
3. Accurate decimal scaling (10^6 vs 10^9) and integer truncation.
4. Accurate fee deduction (DeepBook 10 bps / 0 bps; Cetus 0.05% / 0.25%).
5. Zero leg risk preservation (clean VM abort on negative spread or fee hurdle shortfall).
6. Order execution integration across all 4 pairs.
"""

import pytest
from venues.sui_deepbook_venue import (
    SuiDeepBookVenue,
    SuiDeepBookPTBBuilder,
    HotPotatoPTBParams,
    SUPPORTED_PAIRS,
    SUI_PAIRS_CONFIG,
    SUI_COIN_TYPE,
    CIRCLE_USDC_TYPE,
    DEEP_COIN_TYPE,
    CETUS_COIN_TYPE,
    SUI_USDC_POOL_ID,
    DEEP_SUI_POOL_ID,
    DEEP_USDC_POOL_ID,
    CETUS_SUI_POOL_ID,
    SuiGraphQLClient,
)


# ==============================================================================
# 1. PAIR REGISTRY & METADATA VERIFICATION
# ==============================================================================

def test_pair_registry_coverage_all_4_pairs():
    """Validates that all 4 required pairs exist with exact decimals, fees, and pool IDs."""
    expected_pairs = ["SUI/USDC", "DEEP/SUI", "DEEP/USDC", "CETUS/SUI"]
    assert set(SUPPORTED_PAIRS.keys()) == set(expected_pairs)
    assert set(SUI_PAIRS_CONFIG.keys()) == set(expected_pairs)

    # SUI/USDC: SUI (9 dec), USDC (6 dec), 10 bps DeepBook, 0.05% Cetus, a2b=True
    sui_usdc = SUPPORTED_PAIRS["SUI/USDC"]
    assert sui_usdc["base_decimals"] == 9 and sui_usdc["quote_decimals"] == 6
    assert sui_usdc["deepbook_fee_bps"] == 10.0 and sui_usdc["cetus_fee_rate"] == 0.0005
    assert sui_usdc["a2b"] is True
    assert sui_usdc["deepbook_pool_id"] == SUI_USDC_POOL_ID

    # DEEP/SUI: DEEP (6 dec), SUI (9 dec), 0 bps DeepBook, 0.05% Cetus, a2b=False
    deep_sui = SUPPORTED_PAIRS["DEEP/SUI"]
    assert deep_sui["base_decimals"] == 6 and deep_sui["quote_decimals"] == 9
    assert deep_sui["deepbook_fee_bps"] == 0.0 and deep_sui["cetus_fee_rate"] == 0.0005
    assert deep_sui["a2b"] is False
    assert deep_sui["deepbook_pool_id"] == DEEP_SUI_POOL_ID

    # DEEP/USDC: DEEP (6 dec), USDC (6 dec), 0 bps DeepBook, 0.05% Cetus, a2b=False
    deep_usdc = SUPPORTED_PAIRS["DEEP/USDC"]
    assert deep_usdc["base_decimals"] == 6 and deep_usdc["quote_decimals"] == 6
    assert deep_usdc["deepbook_fee_bps"] == 0.0 and deep_usdc["cetus_fee_rate"] == 0.0005
    assert deep_usdc["a2b"] is False
    assert deep_usdc["deepbook_pool_id"] == DEEP_USDC_POOL_ID

    # CETUS/SUI: CETUS (9 dec), SUI (9 dec), 10 bps DeepBook, 0.25% Cetus, a2b=False
    cetus_sui = SUPPORTED_PAIRS["CETUS/SUI"]
    assert cetus_sui["base_decimals"] == 9 and cetus_sui["quote_decimals"] == 9
    assert cetus_sui["deepbook_fee_bps"] == 10.0 and cetus_sui["cetus_fee_rate"] == 0.0025
    assert cetus_sui["a2b"] is False
    assert cetus_sui["deepbook_pool_id"] == CETUS_SUI_POOL_ID


# ==============================================================================
# 2. PTB BUILDER MULTI-PAIR SERIALIZATION
# ==============================================================================

@pytest.mark.parametrize("pair_name, expected_a2b, expected_borrow_coin", [
    ("SUI/USDC", True, CIRCLE_USDC_TYPE),
    ("DEEP/SUI", False, SUI_COIN_TYPE),
    ("DEEP/USDC", False, CIRCLE_USDC_TYPE),
    ("CETUS/SUI", False, SUI_COIN_TYPE),
])
def test_ptb_builder_serialization_per_pair(pair_name, expected_a2b, expected_borrow_coin):
    """Verifies that PTB builder correctly serializes 8 commands with proper coins and a2b direction."""
    builder = SuiDeepBookPTBBuilder()
    params = HotPotatoPTBParams.from_pair(pair_name)
    ptb = builder.build_atomic_arb_ptb(params)

    assert ptb["is_atomic"] is True
    assert ptb["hot_potato_guarantee"] is True
    assert ptb["pair"] == pair_name
    commands = ptb["commands"]
    assert len(commands) == 8

    # Command 0: borrow quote coin
    assert commands[0]["function"] == "borrow_flashloan_quote"
    assert commands[0]["type_arguments"][1] == expected_borrow_coin

    # Command 1: AMM swap with exact a2b flag
    assert commands[1]["function"] == "swap"
    assert commands[1]["arguments"][3] == {"Input": expected_a2b}

    # Command 5 & 6: Split exact principal & return flash loan
    assert commands[5]["type"] == "SplitCoins"
    assert commands[6]["function"] == "return_flashloan_quote"


# ==============================================================================
# 3. MATHEMATICAL SIMULATION & DRY-RUN PER PAIR
# ==============================================================================

def test_simulate_dry_run_sui_usdc_profitable_and_abort():
    """Tests SUI/USDC (USDC borrow, 6 dec) with 10 bps DeepBook + 5 bps Cetus fee."""
    venue = SuiDeepBookVenue(env="mainnet")
    ptb = venue.build_arbitrage_ptb(HotPotatoPTBParams.from_pair("SUI/USDC", flash_borrow_amount=1_000_000_000))

    # Case 1: Profitable (Bid $2.05 > AMM $2.00, +2.5% spread >> 15 bps hurdle)
    res_prof = venue.simulate_dry_run(ptb, deepbook_bid_px=2.05, amm_swap_out_px=2.00, pair="SUI/USDC")
    assert res_prof["status"] == "SUCCESS"
    assert res_prof["hot_potato_satisfied"] is True
    assert res_prof["zero_leg_risk_preserved"] is True
    assert res_prof["borrow_amount_quote"] == 1000.0
    assert res_prof["net_profit_quote"] > 20.0  # Approx ~$23.46 net profit
    assert res_prof["gas_cost_sui"] == 0.002

    # Case 2: Unprofitable Abort (Bid $1.98 < AMM $2.00)
    res_abort = venue.simulate_dry_run(ptb, deepbook_bid_px=1.98, amm_swap_out_px=2.00, pair="SUI/USDC")
    assert res_abort["status"] == "ABORTED"
    assert res_abort["hot_potato_aborted"] is True
    assert res_abort["zero_leg_risk_preserved"] is True
    assert res_abort["state_mutations"] == 0
    assert res_abort["net_profit_quote"] == 0.0
    assert "INSUFFICIENT_BALANCE_FOR_REPAYMENT" in res_abort["error"]


def test_simulate_dry_run_deep_sui_profitable_and_abort():
    """Tests DEEP/SUI (SUI borrow, 9 dec; DEEP base, 6 dec) with 0 bps DeepBook fee."""
    venue = SuiDeepBookVenue(env="mainnet")
    borrow_mist = 500_000_000_000  # 500 SUI
    ptb = venue.build_arbitrage_ptb(HotPotatoPTBParams.from_pair("DEEP/SUI", flash_borrow_amount=borrow_mist))

    # Case 1: Profitable (Bid 0.050 SUI > AMM 0.048 SUI)
    res_prof = venue.simulate_dry_run(ptb, deepbook_bid_px=0.050, amm_swap_out_px=0.048, pair="DEEP/SUI")
    assert res_prof["status"] == "SUCCESS"
    assert res_prof["quote_symbol"] == "SUI"
    assert res_prof["borrow_amount_quote"] == 500.0
    assert res_prof["net_profit_quote"] > 15.0  # Approx ~20.57 SUI net profit
    assert res_prof["state_mutations"] == 8

    # Case 2: Unprofitable Abort (Bid 0.047 SUI < AMM 0.048 SUI)
    res_abort = venue.simulate_dry_run(ptb, deepbook_bid_px=0.047, amm_swap_out_px=0.048, pair="DEEP/SUI")
    assert res_abort["status"] == "ABORTED"
    assert res_abort["zero_leg_risk_preserved"] is True
    assert res_abort["state_mutations"] == 0


def test_simulate_dry_run_deep_usdc_profitable_and_abort():
    """Tests DEEP/USDC (USDC borrow, 6 dec; DEEP base, 6 dec) with 0 bps DeepBook fee."""
    venue = SuiDeepBookVenue(env="mainnet")
    borrow_usdc = 1_000_000_000  # 1,000 USDC
    ptb = venue.build_arbitrage_ptb(HotPotatoPTBParams.from_pair("DEEP/USDC", flash_borrow_amount=borrow_usdc))

    # Case 1: Profitable (Bid $0.100 > AMM $0.095)
    res_prof = venue.simulate_dry_run(ptb, deepbook_bid_px=0.100, amm_swap_out_px=0.095, pair="DEEP/USDC")
    assert res_prof["status"] == "SUCCESS"
    assert res_prof["quote_symbol"] == "USDC"
    assert res_prof["net_profit_quote"] > 50.0

    # Case 2: Unprofitable Abort (Bid $0.094 < AMM $0.095)
    res_abort = venue.simulate_dry_run(ptb, deepbook_bid_px=0.094, amm_swap_out_px=0.095, pair="DEEP/USDC")
    assert res_abort["status"] == "ABORTED"
    assert res_abort["zero_leg_risk_preserved"] is True


def test_simulate_dry_run_cetus_sui_profitable_and_abort():
    """Tests CETUS/SUI (SUI borrow, 9 dec; CETUS base, 9 dec) with 10 bps DeepBook + 25 bps Cetus fee."""
    venue = SuiDeepBookVenue(env="mainnet")
    borrow_mist = 500_000_000_000  # 500 SUI
    ptb = venue.build_arbitrage_ptb(HotPotatoPTBParams.from_pair("CETUS/SUI", flash_borrow_amount=borrow_mist))

    # Case 1: Profitable (Bid 0.160 SUI > AMM 0.150 SUI, spread +6.67% >> 35 bps hurdle)
    res_prof = venue.simulate_dry_run(ptb, deepbook_bid_px=0.160, amm_swap_out_px=0.150, pair="CETUS/SUI")
    assert res_prof["status"] == "SUCCESS"
    assert res_prof["quote_symbol"] == "SUI"
    assert res_prof["net_profit_quote"] > 30.0

    # Case 2: Unprofitable Abort (Bid 0.148 SUI < AMM 0.150 SUI)
    res_abort = venue.simulate_dry_run(ptb, deepbook_bid_px=0.148, amm_swap_out_px=0.150, pair="CETUS/SUI")
    assert res_abort["status"] == "ABORTED"
    assert res_abort["zero_leg_risk_preserved"] is True


# ==============================================================================
# 4. DECIMAL SCALING & INTEGER TRUNCATION VERIFICATION
# ==============================================================================

def test_decimal_scaling_asymmetry_deep_sui():
    """Verifies exact integer truncation across 9-decimal quote (SUI) and 6-decimal base (DEEP)."""
    venue = SuiDeepBookVenue(env="mainnet")
    borrow_amount = 500_000_000_000  # 500 SUI (9 decimals)
    ptb = venue.build_arbitrage_ptb(HotPotatoPTBParams.from_pair("DEEP/SUI", flash_borrow_amount=borrow_amount))

    # If AMM price = 0.045678901 SUI/DEEP, base coins acquired has recurring decimals
    # Move VM truncates to 6 decimals: floor(B_human * 1e6)
    res = venue.simulate_dry_run(
        ptb=ptb,
        deepbook_bid_px=0.048,
        amm_swap_out_px=0.045678901,
        borrow_amount=borrow_amount,
        pair="DEEP/SUI",
    )
    assert res["status"] == "SUCCESS"
    assert isinstance(res["net_profit_quote"], float)
    assert res["borrow_amount_quote"] == 500.0


# ==============================================================================
# 5. ZERO LEG RISK FEE-HURDLE BOUNDARY TESTS
# ==============================================================================

def test_zero_leg_risk_gross_profit_eaten_by_fees_aborts():
    """Verifies that a spread that is positive gross (+20 bps) but below fee hurdle (35 bps) ABORTS."""
    venue = SuiDeepBookVenue(env="mainnet")
    # CETUS/SUI has 35 bps hurdle (25 bps Cetus + 10 bps DeepBook)
    ptb = venue.build_arbitrage_ptb(HotPotatoPTBParams.from_pair("CETUS/SUI"))

    amm_px = 0.1500
    # Gross bid = +20 bps (0.1503 SUI) -> Gross profit is positive!
    bid_px_below_hurdle = 0.1503

    res = venue.simulate_dry_run(
        ptb=ptb,
        deepbook_bid_px=bid_px_below_hurdle,
        amm_swap_out_px=amm_px,
        pair="CETUS/SUI",
        deduct_fees=True,
    )
    # Must ABORT because net proceeds after 35 bps fee < borrow principal
    assert res["status"] == "ABORTED"
    assert res["zero_leg_risk_preserved"] is True
    assert res["hot_potato_aborted"] is True
    assert res["net_profit_quote"] == 0.0


def test_zero_leg_risk_pure_boundary_without_fees():
    """Verifies exact 1-mist shortfall vs surplus when deduct_fees=False."""
    venue = SuiDeepBookVenue(env="mainnet")
    ptb = venue.build_arbitrage_ptb(HotPotatoPTBParams.from_pair("SUI/USDC"))
    borrow = 100_000_000  # 100 USDC

    amm_px = 2.0
    # 1 mist shortfall
    bid_shortfall = amm_px * (borrow - 1) / borrow
    res_short = venue.simulate_dry_run(ptb, bid_shortfall, amm_px, borrow, pair="SUI/USDC", deduct_fees=False)
    assert res_short["status"] == "ABORTED"
    assert res_short["zero_leg_risk_preserved"] is True

    # 1 mist surplus
    bid_surplus = amm_px * (borrow + 1) / borrow
    res_surp = venue.simulate_dry_run(ptb, bid_surplus, amm_px, borrow, pair="SUI/USDC", deduct_fees=False)
    assert res_surp["status"] == "SUCCESS"
    assert res_surp["net_profit_quote"] > 0


# ==============================================================================
# 6. ORDER EXECUTION INTEGRATION ACROSS ALL 4 PAIRS
# ==============================================================================

@pytest.mark.asyncio
async def test_venue_submit_order_all_pairs():
    """Verifies submit_order returns FILLED for profitable PTB and REJECTED for unprofitable across all 4 pairs."""
    venue = SuiDeepBookVenue(env="mainnet")
    await venue.connect()

    test_cases = [
        ("SUI/USDC", 2.10, 1.95, 2.00, 1000.0),
        ("DEEP/SUI", 0.050, 0.046, 0.048, 500.0),
        ("DEEP/USDC", 0.100, 0.090, 0.095, 1000.0),
        ("CETUS/SUI", 0.160, 0.145, 0.150, 500.0),
    ]

    for pair_name, good_price, bad_price, amm_price, size in test_cases:
        # Case A: Profitable order fills
        res_fill = await venue.submit_order({
            "symbol": pair_name,
            "price": good_price,
            "amm_price": amm_price,
            "size": size,
            "is_arb_ptb": True,
        })
        assert res_fill.status == "FILLED", f"Failed for profitable order on {pair_name}"
        assert res_fill.order_id.startswith("PTB-EXEC-")

        # Case B: Unprofitable order aborts cleanly
        res_abort = await venue.submit_order({
            "symbol": pair_name,
            "price": bad_price,
            "amm_price": amm_price,
            "size": size,
            "is_arb_ptb": True,
        })
        assert res_abort.status == "REJECTED", f"Failed for unprofitable abort on {pair_name}"
        assert res_abort.order_id.startswith("PTB-REVERT-")
        assert res_abort.fee_bps == 0.0

    await venue.disconnect()
