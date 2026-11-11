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

def test_pair_registry_coverage_all_10_pairs():
    """Validates that all 10 required pairs exist with exact decimals, fees, and pool IDs."""
    expected_pairs = [
        "SUI/USDC",
        "DEEP/SUI",
        "DEEP/USDC",
        "CETUS/SUI",
        "USDSUI/USDC",
        "WAL/USDC",
        "LZWBTC/USDC",
        "NS/SUI",
        "XBTC/USDC",
        "NS/USDC",
    ]
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


_NEW_SIX_PAIRS = (
    "USDSUI/USDC",
    "WAL/USDC",
    "LZWBTC/USDC",
    "NS/SUI",
    "XBTC/USDC",
    "NS/USDC",
)


def test_new_six_pairs_ptb_params_and_bcs_generation():
    """Verify HotPotatoPTBParams and FORWARD/REVERSE BCS PTBs for all 6 newly activated pairs."""
    from venues.sui_deepbook_venue import (
        HotPotatoPTBParams,
        SuiDeepBookPTBBuilder,
    )
    from venues.sui_health_server import ACTIVE_PAIRS

    assert len(ACTIVE_PAIRS) == 10
    assert set(ACTIVE_PAIRS) == set(SUI_PAIRS_CONFIG.keys())
    for pair in _NEW_SIX_PAIRS:
        assert pair in ACTIVE_PAIRS

    dummy_gas = {
        "address": "0x" + "11" * 32,
        "version": 123,
        "digest": "11111111111111111111111111111111",
    }
    sender = "0x" + "22" * 32
    builder = SuiDeepBookPTBBuilder()

    for pair in _NEW_SIX_PAIRS:
        cfg = SUI_PAIRS_CONFIG[pair]
        assert cfg.turbos_pool_id is None
        expected_a2b = cfg.cetus_coin_a_type == cfg.quote_coin_type
        assert cfg.cetus_a2b_for_quote_in is expected_a2b

        for direction in ("FORWARD", "REVERSE"):
            params = HotPotatoPTBParams.from_pair(pair, route_direction=direction)
            assert params.pair_name == pair
            assert params.pool_id == cfg.deepbook_pool_id
            assert params.cetus_pool_id == cfg.cetus_pool_id
            assert params.turbos_pool_id is None
            assert params.route_direction == direction
            assert params.a2b == (cfg.cetus_a2b_for_quote_in if direction == "FORWARD" else not cfg.cetus_a2b_for_quote_in)

            raw_bcs = builder.build_atomic_arb_ptb_bcs(
                pair_name=pair,
                borrow_amount=cfg.default_borrow_amount,
                sender_address=sender,
                gas_coin=dummy_gas,
                route_direction=direction,
            )
            assert isinstance(raw_bcs, bytes)
            assert len(raw_bcs) > 500


def test_new_pairs_virtual_reserve_orientation_scaling_and_slippage():
    """Verify L/sqrt_p (quote-in-CoinA) vs L*sqrt_p (base-in-CoinA) reserve math."""
    from venues.sui_bot_runner import SuiBotRunner
    from venues.sui_scaling_engine import (
        DEFAULT_PAIR_SQRT_PRICES,
        DynamicCapitalScalingEngine,
    )

    eng = DynamicCapitalScalingEngine()
    liq_hi = 1e16
    liq_lo = 1e12

    for pair in _NEW_SIX_PAIRS:
        cfg = SUI_PAIRS_CONFIG[pair]
        sqrt_p = DEFAULT_PAIR_SQRT_PRICES[pair]
        slip_hi = SuiBotRunner._compute_amm_slippage_bps(pair, cfg.default_borrow_amount, liq_hi, sqrt_p)
        slip_lo = SuiBotRunner._compute_amm_slippage_bps(pair, cfg.default_borrow_amount, liq_lo, sqrt_p)
        assert slip_lo > slip_hi

        # Doubling sqrt_p shrinks virtual quote reserve L/sqrt_p (2x slippage) when quote is CoinA,
        # and grows virtual quote reserve L*sqrt_p (0.5x slippage) when base is CoinA (NS/SUI).
        slip_1x = SuiBotRunner._compute_amm_slippage_bps(pair, cfg.default_borrow_amount, 1e14, sqrt_p)
        slip_2x = SuiBotRunner._compute_amm_slippage_bps(pair, cfg.default_borrow_amount, 1e14, sqrt_p * 2.0)
        expected_ratio = 2.0 if cfg.cetus_a2b_for_quote_in else 0.5
        assert slip_2x / slip_1x == pytest.approx(expected_ratio, rel=1e-6)

        borrow_hi = eng.get_current_borrow_amount(pair, spread_bps=200.0, liquidity=liq_hi, sqrt_price=sqrt_p)
        borrow_lo = eng.get_current_borrow_amount(pair, spread_bps=200.0, liquidity=liq_lo, sqrt_price=sqrt_p)
        assert borrow_hi >= borrow_lo > 0


@pytest.mark.asyncio
async def test_query_live_market_spreads_asymmetric_decimals_new_pairs():
    """Verify Q64.64 spot price decoding across asymmetric decimal configs for all 6 new pairs."""
    import math
    from unittest.mock import AsyncMock, patch
    from venues.sui_deepbook_venue import (
        PAIR_GRAPHQL_ALIASES,
        SuiGraphQLClient,
    )

    targets = {
        "USDSUI/USDC": 1.0005,
        "WAL/USDC": 0.08,
        "LZWBTC/USDC": 70000.0,
        "NS/SUI": 0.025,
        "XBTC/USDC": 70000.0,
        "NS/USDC": 0.02,
    }
    gql_data = {"cetus_bids": {}}
    db_books = {}

    for pair, spot in targets.items():
        cfg = SUI_PAIRS_CONFIG[pair]
        c_key, _, d_key, _pf, indexer_name = PAIR_GRAPHQL_ALIASES[pair]
        if cfg.cetus_coin_a_type == cfg.quote_coin_type:
            raw_p = (1.0 / spot) * (10 ** (cfg.base_decimals - cfg.quote_decimals))
        else:
            raw_p = spot * (10 ** (cfg.quote_decimals - cfg.base_decimals))
        sqrt_q64 = int(round(math.sqrt(raw_p) * (2 ** 64)))
        gql_data[c_key] = {
            "asMoveObject": {
                "contents": {
                    "json": {
                        "current_sqrt_price": str(sqrt_q64),
                        "liquidity": "1000000000000000",
                    }
                }
            }
        }
        gql_data[d_key] = {"asMoveObject": {"contents": {"json": {"id": cfg.deepbook_pool_id}}}}
        db_books[indexer_name] = {
            "bids": [[str(spot * 1.005), "100.0"]],
            "asks": [[str(spot * 1.006), "100.0"]],
        }

    client = SuiGraphQLClient()

    async def mock_fetch(sym: str):
        return db_books.get(sym, {})

    try:
        with patch.object(client, "execute", AsyncMock(return_value={"data": gql_data})), patch.object(
            client, "_fetch_deepbook_indexer_orderbook", side_effect=mock_fetch
        ):
            spreads = await client.query_live_market_spreads()
    finally:
        await client.close()

    assert len(spreads) == 10
    for pair, spot in targets.items():
        row = spreads[pair]
        assert row["cetus_price"] == pytest.approx(spot, rel=1e-6)
        assert row["deepbook_price"] == pytest.approx(spot * 1.005, rel=1e-6)
        assert row["deepbook_ask"] == pytest.approx(spot * 1.006, rel=1e-6)
        assert row["best_amm"] == "cetus"
        assert row["turbos_price"] == 0.0
        assert row["forward_spread_bps"] == pytest.approx(50.0, abs=0.05)
