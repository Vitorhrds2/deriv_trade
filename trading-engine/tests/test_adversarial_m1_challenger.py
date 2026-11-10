"""Milestone M1 Adversarial Stress Test Suite: Empirical Challenger.

Empirical stress testing of Multi-Pair Sui DeepBookV3 & Cetus AMM PTB Engine:
1. Multi-Pair Decimal Boundary Testing:
   - Price spectrum from 10^-5 to 10^5 across all 4 pairs (SUI/USDC, DEEP/SUI, DEEP/USDC, CETUS/SUI).
   - Decimal scaling asymmetry (6 vs 9 decimals) and Move VM integer truncation.
   - Tiny (1 mist) to massive (10^14 mist) borrow amounts.
   - Monte Carlo randomized oracle validation (zero false-positive profit, zero underflows).
2. Zero Leg Risk Under Hostile Conditions:
   - Severe price slippage (-50%, -75%, -90%, -99%).
   - Cetus front-run sandwich attacks (+50%, +100%, +1000%, +10000% AMM spike).
   - Inverted spreads (bid < ask).
   - Mathematical guarantee that status == 'ABORTED', zero_leg_risk_preserved == True,
     hot_potato_aborted == True, state_mutations == 0.
3. Fee Hurdle Edge Scenarios:
   - Nominally positive gross spreads below fee friction:
     * CETUS/SUI (35 bps friction): test +1 to +34 bps.
     * SUI/USDC (15 bps friction): test +1 to +14 bps.
     * DEEP/SUI & DEEP/USDC (5 bps whitelisted friction): test +1 to +4 bps.
   - High-resolution (0.1 bps step) boundary inflection sweep.
4. Venue Integration & Order Execution Stress:
   - End-to-end `submit_order` validation with hostile market conditions across all 4 pairs.
"""

from __future__ import annotations

import math
import random
import sys
from pathlib import Path
from typing import Any, Dict, List
import pytest

# Ensure trading-engine root directory is on sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from venues.sui_deepbook_venue import (
    SuiDeepBookVenue,
    SuiDeepBookPTBBuilder,
    HotPotatoPTBParams,
    SUPPORTED_PAIRS,
    SUI_PAIRS_CONFIG,
    PairConfig,
)


# ==============================================================================
# SECTION 1: MULTI-PAIR DECIMAL BOUNDARY & EXTREME PRICE STRESS TESTS
# ==============================================================================

class TestMultiPairDecimalBoundaryStress:
    """Stress tests simulate_dry_run across extreme prices (10^-5 to 10^5) and decimal scaling."""

    @pytest.mark.parametrize("pair_name", ["SUI/USDC", "DEEP/SUI", "DEEP/USDC", "CETUS/SUI"])
    @pytest.mark.parametrize("base_price", [1e-5, 1e-4, 1e-3, 1e-2, 1e-1, 1.0, 10.0, 100.0, 1000.0, 10000.0, 100000.0])
    def test_extreme_price_profitable_spread_no_crash(self, pair_name: str, base_price: float):
        """Verifies simulate_dry_run handles prices from 10^-5 to 10^5 with +2% spread without crashing or underflow."""
        venue = SuiDeepBookVenue(env="mainnet")
        cfg = SUI_PAIRS_CONFIG[pair_name]
        borrow_amount = cfg.default_borrow_amount
        ptb = venue.build_arbitrage_ptb(HotPotatoPTBParams.from_pair(pair_name, flash_borrow_amount=borrow_amount))

        amm_px = base_price
        bid_px = base_price * 1.02  # +2.0% spread (well above fee hurdle)

        res = venue.simulate_dry_run(
            ptb=ptb,
            deepbook_bid_px=bid_px,
            amm_swap_out_px=amm_px,
            borrow_amount=borrow_amount,
            pair=pair_name,
            deduct_fees=True,
        )

        assert res["zero_leg_risk_preserved"] is True
        assert res["pair"] == pair_name

        # For very high prices (e.g. 100,000), if borrow amount yields < 1 base unit native,
        # integer truncation forces base_coins_acquired_native == 0, leading to clean ABORT.
        # Otherwise, it must SUCCEED with positive net profit.
        if res["status"] == "SUCCESS":
            assert res["net_profit_quote"] > 0.0
            assert res["hot_potato_satisfied"] is True
            assert res["state_mutations"] == 8
            assert not math.isnan(res["net_profit_quote"])
            assert not math.isinf(res["net_profit_quote"])
        else:
            assert res["status"] == "ABORTED"
            assert res["hot_potato_aborted"] is True
            assert res["state_mutations"] == 0
            assert res["net_profit_quote"] == 0.0

    @pytest.mark.parametrize("pair_name", ["SUI/USDC", "DEEP/SUI", "DEEP/USDC", "CETUS/SUI"])
    @pytest.mark.parametrize("base_price", [1e-5, 1e-4, 1e-3, 1e-2, 1e-1, 1.0, 10.0, 100.0, 1000.0, 10000.0, 100000.0])
    def test_extreme_price_unprofitable_spread_clean_abort(self, pair_name: str, base_price: float):
        """Verifies simulate_dry_run strictly aborts on -2% spread across 10^-5 to 10^5, never producing false-positive profit."""
        venue = SuiDeepBookVenue(env="mainnet")
        cfg = SUI_PAIRS_CONFIG[pair_name]
        borrow_amount = cfg.default_borrow_amount
        ptb = venue.build_arbitrage_ptb(HotPotatoPTBParams.from_pair(pair_name, flash_borrow_amount=borrow_amount))

        amm_px = base_price
        bid_px = base_price * 0.98  # -2.0% spread (strictly negative gross)

        res = venue.simulate_dry_run(
            ptb=ptb,
            deepbook_bid_px=bid_px,
            amm_swap_out_px=amm_px,
            borrow_amount=borrow_amount,
            pair=pair_name,
            deduct_fees=True,
        )

        assert res["status"] == "ABORTED"
        assert res["zero_leg_risk_preserved"] is True
        assert res["hot_potato_aborted"] is True
        assert res["net_profit_quote"] == 0.0
        assert res["state_mutations"] == 0
        assert res["shortfall_native"] > 0

    @pytest.mark.parametrize("pair_name", ["SUI/USDC", "DEEP/SUI", "DEEP/USDC", "CETUS/SUI"])
    @pytest.mark.parametrize("borrow_amount", [1, 10, 100, 1_000, 1_000_000, 100_000_000, 1_000_000_000, 10_000_000_000, 100_000_000_000_000])
    def test_extreme_borrow_amounts(self, pair_name: str, borrow_amount: int):
        """Verifies borrow amounts from 1 mist up to 100 trillion mist never cause arithmetic overflow or negative profit."""
        venue = SuiDeepBookVenue(env="mainnet")
        ptb = venue.build_arbitrage_ptb(HotPotatoPTBParams.from_pair(pair_name, flash_borrow_amount=borrow_amount))

        amm_px = 1.0
        bid_px = 1.05  # +5% spread

        res = venue.simulate_dry_run(
            ptb=ptb,
            deepbook_bid_px=bid_px,
            amm_swap_out_px=amm_px,
            borrow_amount=borrow_amount,
            pair=pair_name,
            deduct_fees=True,
        )

        assert res["zero_leg_risk_preserved"] is True
        if res["status"] == "SUCCESS":
            assert res["net_profit_quote"] >= 0.0
            assert res["net_proceeds_quote"] >= res["borrow_amount_quote"]
        else:
            assert res["status"] == "ABORTED"
            assert res["net_profit_quote"] == 0.0

    def test_randomized_monte_carlo_oracle_consistency(self):
        """Monte Carlo stress test: 2,000 random trials across all 4 pairs verifying strict mathematical consistency."""
        venue = SuiDeepBookVenue(env="mainnet")
        rng = random.Random(42)

        for _ in range(2000):
            pair_name = rng.choice(["SUI/USDC", "DEEP/SUI", "DEEP/USDC", "CETUS/SUI"])
            cfg = SUI_PAIRS_CONFIG[pair_name]

            # Price uniformly sampled in log-space from 10^-4 to 10^4
            log_p = rng.uniform(-4.0, 4.0)
            amm_px = 10.0 ** log_p

            # Spread ratio sampled from -50% to +50%
            spread_mult = rng.uniform(0.5, 1.5)
            bid_px = amm_px * spread_mult

            # Borrow amount sampled from 100,000 to 10^12 mist
            log_borrow = rng.uniform(5.0, 12.0)
            borrow_amt = int(10.0 ** log_borrow)

            ptb = venue.build_arbitrage_ptb(HotPotatoPTBParams.from_pair(pair_name, flash_borrow_amount=borrow_amt))

            res = venue.simulate_dry_run(
                ptb=ptb,
                deepbook_bid_px=bid_px,
                amm_swap_out_px=amm_px,
                borrow_amount=borrow_amt,
                pair=pair_name,
                deduct_fees=True,
            )

            # Independent Oracle Evaluation
            quote_scale = 10 ** cfg.quote_decimals
            base_scale = 10 ** cfg.base_decimals
            principal_human = borrow_amt / quote_scale

            c_fee = cfg.cetus_fee_rate
            d_fee_rate = cfg.deepbook_taker_fee_bps / 10000.0

            q_in_net = principal_human * (1.0 - c_fee)
            b_human = q_in_net / amm_px
            b_native = int(b_human * base_scale)
            b_exact = b_native / base_scale

            gross_q = b_exact * bid_px
            net_q = gross_q * (1.0 - d_fee_rate)
            net_native = int(net_q * quote_scale)

            oracle_is_profitable = (net_native >= borrow_amt)

            if oracle_is_profitable:
                assert res["status"] == "SUCCESS", f"Oracle expected SUCCESS for {pair_name}"
                assert res["net_profit_quote"] == (net_native - borrow_amt) / quote_scale
            else:
                assert res["status"] == "ABORTED", f"Oracle expected ABORT for {pair_name}"
                assert res["net_profit_quote"] == 0.0
                assert res["zero_leg_risk_preserved"] is True


# ==============================================================================
# SECTION 2: ZERO LEG RISK UNDER HOSTILE CONDITIONS (SLIPPAGE, SANDWICH, INVERSION)
# ==============================================================================

class TestZeroLegRiskHostileConditions:
    """Stress tests catastrophic market conditions: severe slippage, sandwich attacks, and inverted spreads."""

    @pytest.mark.parametrize("pair_name", ["SUI/USDC", "DEEP/SUI", "DEEP/USDC", "CETUS/SUI"])
    @pytest.mark.parametrize("bid_collapse_factor", [0.50, 0.25, 0.10, 0.01])
    def test_severe_bid_price_slippage_aborts(self, pair_name: str, bid_collapse_factor: float):
        """DeepBook bid crashes by -50%, -75%, -90%, or -99% relative to AMM acquisition price."""
        venue = SuiDeepBookVenue(env="mainnet")
        ptb = venue.build_arbitrage_ptb(HotPotatoPTBParams.from_pair(pair_name))
        amm_px = 1.0
        bid_px = amm_px * bid_collapse_factor

        res = venue.simulate_dry_run(
            ptb=ptb,
            deepbook_bid_px=bid_px,
            amm_swap_out_px=amm_px,
            pair=pair_name,
            deduct_fees=True,
        )

        assert res["status"] == "ABORTED"
        assert res["zero_leg_risk_preserved"] is True
        assert res["hot_potato_aborted"] is True
        assert res["state_mutations"] == 0
        assert res["net_profit_quote"] == 0.0
        assert res["shortfall_native"] > 0
        assert res["gas_cost_sui"] == 0.002

    @pytest.mark.parametrize("pair_name", ["SUI/USDC", "DEEP/SUI", "DEEP/USDC", "CETUS/SUI"])
    @pytest.mark.parametrize("amm_spike_factor", [1.5, 2.0, 5.0, 10.0, 100.0])
    def test_sandwich_attack_amm_frontrun_spike_aborts(self, pair_name: str, amm_spike_factor: float):
        """Attacker front-runs Cetus pool pushing price up by +50% to +10,000% before our swap."""
        venue = SuiDeepBookVenue(env="mainnet")
        ptb = venue.build_arbitrage_ptb(HotPotatoPTBParams.from_pair(pair_name))
        normal_px = 2.0
        bid_px = normal_px  # Our target sell price on CLOB
        hostile_amm_px = normal_px * amm_spike_factor  # Sandwiched AMM price

        res = venue.simulate_dry_run(
            ptb=ptb,
            deepbook_bid_px=bid_px,
            amm_swap_out_px=hostile_amm_px,
            pair=pair_name,
            deduct_fees=True,
        )

        assert res["status"] == "ABORTED"
        assert res["zero_leg_risk_preserved"] is True
        assert res["hot_potato_aborted"] is True
        assert res["state_mutations"] == 0
        assert res["net_profit_quote"] == 0.0
        assert res["shortfall_native"] > 0

    @pytest.mark.parametrize("pair_name", ["SUI/USDC", "DEEP/SUI", "DEEP/USDC", "CETUS/SUI"])
    def test_inverted_spread_adverse_boundary(self, pair_name: str):
        """Tests inverted spread where bid is strictly below AMM by 1 to 500 bps."""
        venue = SuiDeepBookVenue(env="mainnet")
        ptb = venue.build_arbitrage_ptb(HotPotatoPTBParams.from_pair(pair_name))
        amm_px = 1.0

        for bps_under in [1, 5, 10, 50, 100, 500]:
            bid_px = amm_px * (1.0 - (bps_under / 10000.0))
            res = venue.simulate_dry_run(
                ptb=ptb,
                deepbook_bid_px=bid_px,
                amm_swap_out_px=amm_px,
                pair=pair_name,
                deduct_fees=True,
            )
            assert res["status"] == "ABORTED", f"Failed for {pair_name} at -{bps_under} bps"
            assert res["zero_leg_risk_preserved"] is True
            assert res["net_profit_quote"] == 0.0


# ==============================================================================
# SECTION 3: FEE HURDLE EDGE SCENARIOS & INFLECTION POINT SWEEP
# ==============================================================================

class TestFeeHurdleEdgeScenarios:
    """Stress tests nominal positive spreads that fall below total fee friction."""

    def test_cetus_sui_fee_hurdle_35_bps(self):
        """CETUS/SUI has 35 bps total fee friction (25 bps Cetus + 10 bps DeepBook).

        Tests:
        - Nominally positive spreads from +1 bps to +34 bps MUST ABORT.
        - Spreads above +36 bps MUST SUCCEED.
        """
        venue = SuiDeepBookVenue(env="mainnet")
        pair_name = "CETUS/SUI"
        ptb = venue.build_arbitrage_ptb(HotPotatoPTBParams.from_pair(pair_name))
        amm_px = 0.1500

        # Sub-hurdle spreads (nominally profitable gross, but net loss after 35 bps fees)
        sub_hurdle_bps = [1, 5, 10, 15, 20, 25, 30, 34]
        for bps in sub_hurdle_bps:
            bid_px = amm_px * (1.0 + (bps / 10000.0))
            res = venue.simulate_dry_run(
                ptb=ptb,
                deepbook_bid_px=bid_px,
                amm_swap_out_px=amm_px,
                pair=pair_name,
                deduct_fees=True,
            )
            assert res["status"] == "ABORTED", f"CETUS/SUI should abort at +{bps} bps"
            assert res["zero_leg_risk_preserved"] is True
            assert res["net_profit_quote"] == 0.0

        # Super-hurdle spreads (sufficient to overcome 35 bps hurdle)
        super_hurdle_bps = [36, 40, 50, 100]
        for bps in super_hurdle_bps:
            bid_px = amm_px * (1.0 + (bps / 10000.0))
            res = venue.simulate_dry_run(
                ptb=ptb,
                deepbook_bid_px=bid_px,
                amm_swap_out_px=amm_px,
                pair=pair_name,
                deduct_fees=True,
            )
            assert res["status"] == "SUCCESS", f"CETUS/SUI should succeed at +{bps} bps"
            assert res["net_profit_quote"] > 0.0
            assert res["zero_leg_risk_preserved"] is True

    def test_sui_usdc_fee_hurdle_15_bps(self):
        """SUI/USDC has 15 bps total fee friction (5 bps Cetus + 10 bps DeepBook).

        Tests:
        - Nominally positive spreads from +1 bps to +14 bps MUST ABORT.
        - Spreads above +16 bps MUST SUCCEED.
        """
        venue = SuiDeepBookVenue(env="mainnet")
        pair_name = "SUI/USDC"
        ptb = venue.build_arbitrage_ptb(HotPotatoPTBParams.from_pair(pair_name))
        amm_px = 2.0000

        sub_hurdle_bps = [1, 3, 5, 8, 10, 12, 14]
        for bps in sub_hurdle_bps:
            bid_px = amm_px * (1.0 + (bps / 10000.0))
            res = venue.simulate_dry_run(
                ptb=ptb,
                deepbook_bid_px=bid_px,
                amm_swap_out_px=amm_px,
                pair=pair_name,
                deduct_fees=True,
            )
            assert res["status"] == "ABORTED", f"SUI/USDC should abort at +{bps} bps"
            assert res["zero_leg_risk_preserved"] is True

        super_hurdle_bps = [16, 20, 30, 50]
        for bps in super_hurdle_bps:
            bid_px = amm_px * (1.0 + (bps / 10000.0))
            res = venue.simulate_dry_run(
                ptb=ptb,
                deepbook_bid_px=bid_px,
                amm_swap_out_px=amm_px,
                pair=pair_name,
                deduct_fees=True,
            )
            assert res["status"] == "SUCCESS", f"SUI/USDC should succeed at +{bps} bps"
            assert res["net_profit_quote"] > 0.0

    @pytest.mark.parametrize("whitelisted_pair", ["DEEP/SUI", "DEEP/USDC"])
    def test_whitelisted_fee_hurdle_5_bps(self, whitelisted_pair: str):
        """DEEP/SUI & DEEP/USDC have 5 bps total fee friction (5 bps Cetus + 0 bps DeepBook).

        Tests:
        - Nominally positive spreads from +1 bps to +4 bps MUST ABORT.
        - Spreads above +6 bps MUST SUCCEED.
        """
        venue = SuiDeepBookVenue(env="mainnet")
        ptb = venue.build_arbitrage_ptb(HotPotatoPTBParams.from_pair(whitelisted_pair))
        amm_px = 0.05 if whitelisted_pair == "DEEP/SUI" else 0.10

        sub_hurdle_bps = [1, 2, 3, 4]
        for bps in sub_hurdle_bps:
            bid_px = amm_px * (1.0 + (bps / 10000.0))
            res = venue.simulate_dry_run(
                ptb=ptb,
                deepbook_bid_px=bid_px,
                amm_swap_out_px=amm_px,
                pair=whitelisted_pair,
                deduct_fees=True,
            )
            assert res["status"] == "ABORTED", f"{whitelisted_pair} should abort at +{bps} bps"
            assert res["zero_leg_risk_preserved"] is True

        super_hurdle_bps = [6, 10, 20]
        for bps in super_hurdle_bps:
            bid_px = amm_px * (1.0 + (bps / 10000.0))
            res = venue.simulate_dry_run(
                ptb=ptb,
                deepbook_bid_px=bid_px,
                amm_swap_out_px=amm_px,
                pair=whitelisted_pair,
                deduct_fees=True,
            )
            assert res["status"] == "SUCCESS", f"{whitelisted_pair} should succeed at +{bps} bps"
            assert res["net_profit_quote"] > 0.0

    def test_fine_grained_inflection_point_sweep(self):
        """Fine-grained 0.1 bps step sweep around the fee hurdle boundary verifying monotonicity."""
        venue = SuiDeepBookVenue(env="mainnet")
        pair_name = "SUI/USDC"
        ptb = venue.build_arbitrage_ptb(HotPotatoPTBParams.from_pair(pair_name))
        amm_px = 2.0

        # Exact hurdle is (1 - 0.0005) * (1 - 0.0010) = 0.9985005 -> ~15.02 bps
        transition_found = False
        last_status = "ABORTED"

        # Sweep from 14.0 bps to 16.0 bps in 0.1 bps steps
        for step in range(140, 161):
            bps = step / 10.0
            bid_px = amm_px * (1.0 + (bps / 10000.0))
            res = venue.simulate_dry_run(
                ptb=ptb,
                deepbook_bid_px=bid_px,
                amm_swap_out_px=amm_px,
                pair=pair_name,
                deduct_fees=True,
            )
            current_status = res["status"]
            if last_status == "ABORTED" and current_status == "SUCCESS":
                transition_found = True
                # Inflection must happen precisely around ~15 bps
                assert 14.8 <= bps <= 15.3, f"Unexpected inflection point at {bps} bps"
            if last_status == "SUCCESS":
                assert current_status == "SUCCESS", f"Monotonicity violated: reverted to abort at {bps} bps"
            last_status = current_status

        assert transition_found, "Monotonic inflection point was not observed"


# ==============================================================================
# SECTION 4: VENUE INTEGRATION SUBMIT_ORDER UNDER HOSTILE STRESS
# ==============================================================================

class TestVenueSubmitOrderAdversarial:
    """Stress tests high-level submit_order integration under adversarial market conditions."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize("pair_name", ["SUI/USDC", "DEEP/SUI", "DEEP/USDC", "CETUS/SUI"])
    async def test_submit_order_hostile_slippage_rejection(self, pair_name: str):
        """Verifies submit_order returns REJECTED with 0 fee when market condition collapses."""
        venue = SuiDeepBookVenue(env="mainnet")
        await venue.connect()

        base_px = 2.0 if "USDC" in pair_name else 0.1
        # Severe -50% collapse
        res = await venue.submit_order({
            "symbol": pair_name,
            "price": base_px * 0.5,
            "amm_price": base_px,
            "size": 100.0,
            "is_arb_ptb": True,
        })

        assert res.status == "REJECTED"
        assert res.order_id.startswith("PTB-REVERT-")
        assert res.fee_bps == 0.0

        await venue.disconnect()

    @pytest.mark.asyncio
    @pytest.mark.parametrize("pair_name", ["SUI/USDC", "DEEP/SUI", "DEEP/USDC", "CETUS/SUI"])
    async def test_submit_order_sub_hurdle_rejection(self, pair_name: str):
        """Verifies submit_order rejects nominally positive spread (+2 bps) below fee friction."""
        venue = SuiDeepBookVenue(env="mainnet")
        await venue.connect()

        base_px = 2.0 if "USDC" in pair_name else 0.1
        # +2 bps is below 5 bps, 15 bps, and 35 bps hurdles for all pairs
        res = await venue.submit_order({
            "symbol": pair_name,
            "price": base_px * 1.0002,
            "amm_price": base_px,
            "size": 100.0,
            "is_arb_ptb": True,
        })

        assert res.status == "REJECTED"
        assert res.order_id.startswith("PTB-REVERT-")

        await venue.disconnect()
