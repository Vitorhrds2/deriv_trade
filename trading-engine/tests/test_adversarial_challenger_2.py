"""Adversarial Stress Test Suite: Challenger 2.

Empirical verification of fee friction, atomic reversion, extreme boundary math,
and mechanical protections across quantitative execution vectors:
1. Sui DeepBookV3 Hot Potato atomic reversion on simulated AMM slippage:
   - Move PTB 8-step structure and Hot Potato non-droppable contract.
   - Clean abort on unprofitable spreads and AMM slippage.
   - 0 lingering debt / 0 state mutations / zero leg risk guarantee.
   - Infinitesimal boundary shortfall down to 1 mist ($10^-6 USDC).
   - Catastrophic sandwich attacks and flash crash resilience.
2. GMX v2 dynamic price impact fee explosion and acceptablePrice slippage ceiling:
   - Dynamic price impact fee formula scaling and explosion.
   - Sizing stress: dynamic fee exceeding arbitrage edge turning EV negative.
   - Degenerate and boundary input handling (zero depth, negative size).
   - acceptablePrice slippage ceiling cancellation for BUY orders.
   - acceptablePrice slippage floor cancellation for SELL orders.
   - Lead-lag signal detection deadband and reversal stability.
3. Velocity SWIFT Dutch auction pricing at extreme boundary timestamps:
   - Zero duration (D = 0) and negative duration (D < 0) division-by-zero protection.
   - Extreme negative timestamps and clock-skew pre-start arrival.
   - Huge future offsets (up to 10^18 ms / 2^63 - 1).
   - Monotonicity verification for climbing (BUY) and decaying (SELL) curves.
   - Toxic flow gating on extreme oracle divergence.
4. Maker rebate vs taker fee inversion verification:
   - Hyperliquid ALO crossing cancellation preventing taker fee payment.
   - Hyperliquid taker orders strictly incurring positive taker fees.
   - dYdX v4 institutional tier maker rebate (-0.7 bps, -1.1 bps) vs taker fee (+2.5 bps).
   - Velocity SWIFT maker rebate exclusivity.
   - Universal cross-venue fee inversion invariant: taker rebate is strictly 0.0.
"""

from __future__ import annotations

import asyncio
import json
import math
import sys
import time
from pathlib import Path
from typing import Any, Dict, List
from unittest.mock import MagicMock, patch

import aiohttp
from aiohttp import ClientResponseError, ContentTypeError, web
import pytest

# Ensure trading-engine root directory is on sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from venues.base import MarketUpdate, OrderExecutionResult, UnifiedVenue
from venues.registry import get_venue, list_venues
from venues.sui_deepbook_venue import (
    SuiDeepBookVenue,
    SuiDeepBookPTBBuilder,
    HotPotatoPTBParams,
    SuiGraphQLClient,
    SUI_PAIRS_CONFIG,
    SUI_USDC_POOL_ID,
    CIRCLE_USDC_TYPE,
    SUI_COIN_TYPE,
)
from venues.gmx_cex_venue import GmxCexVenue, compute_gmx_price_impact_fee
from venues.velocity_swift_venue import (
    VelocitySwiftVenue,
    compute_swift_auction_price,
    DEFAULT_SLOT_DURATION_MS,
)
from venues.hyperliquid_venue import HyperliquidVenue, HYPERLIQUID_FEE_TIERS
from venues.dydx_v4_venue import DydxV4Venue, DYDX_FEE_TIERS
from venues.kalshi_fix_venue import KalshiFixVenue


# ==============================================================================
# SECTION 1: SUI DEEPBOOKV3 HOT POTATO ATOMIC REVERSION & ZERO LINGERING DEBT
# ==============================================================================

class TestSuiDeepBookHotPotatoReversion:
    """Stress tests Sui Move VM Hot Potato semantics and atomic PTB reversion."""

    def test_sui_ptb_hot_potato_structure_and_invariants(self):
        """Verifies PTB builder creates an 8-command atomic block enforcing Hot Potato receipt."""
        builder = SuiDeepBookPTBBuilder()
        params = HotPotatoPTBParams(
            pool_id=SUI_USDC_POOL_ID,
            base_coin_type=SUI_COIN_TYPE,
            quote_coin_type=CIRCLE_USDC_TYPE,
            flash_borrow_amount=100_000_000,  # 100 USDC
            amm_target="cetus",
            min_repay_amount=100_000_000,
        )
        ptb = builder.build_atomic_arb_ptb(params)

        assert ptb["is_atomic"] is True
        assert ptb["hot_potato_guarantee"] is True
        commands = ptb["commands"]
        assert len(commands) == 8, f"Expected 8 Move commands, got {len(commands)}"

        # Command 0: Flash borrow produces Hot Potato receipt
        assert commands[0]["function"] == "borrow_flashloan_quote"
        assert commands[0]["outputs"] == ["borrowed_quote_coin", "flash_loan_receipt"]

        # Command 1: AMM swap leg
        assert commands[1]["function"] == "swap"
        assert commands[1]["arguments"][2] == {"NestedResult": [0, 0]}

        # Command 2: Deposit to Balance Manager
        assert commands[2]["function"] == "deposit"

        # Command 3: Place market sell order on DeepBook CLOB
        assert commands[3]["function"] == "place_market_order"

        # Command 4: Withdraw all proceeds from Balance Manager
        assert commands[4]["function"] == "withdraw_all"

        # Command 5: Split exact repayment coin
        assert commands[5]["type"] == "SplitCoins"
        assert commands[5]["amounts"] == [{"Input": params.min_repay_amount}]

        # Command 6: Return flash loan, consuming Hot Potato receipt
        assert commands[6]["function"] == "return_flashloan_quote"
        assert commands[6]["arguments"][1] == {"NestedResult": [5, 0]}  # Repay coin
        assert commands[6]["arguments"][2] == {"NestedResult": [0, 1]}  # Hot Potato receipt

        # Command 7: Transfer remaining profit to sender
        assert commands[7]["type"] == "TransferObjects"

    @pytest.mark.asyncio
    async def test_sui_hot_potato_clean_abort_on_slippage_spectrum(self):
        """Tests that adverse AMM slippage causes clean VM abort with 0 state mutations."""
        venue = SuiDeepBookVenue(env="mainnet")
        await venue.connect()
        ptb = venue.build_arbitrage_ptb()

        # Sweep slippage levels where AMM buy price is higher than DeepBook bid ($2.00)
        # AMM price ranges from $2.0001 (slight slippage) to $4.00 (100% adverse slippage)
        slippage_amm_prices = [2.0001, 2.001, 2.01, 2.05, 2.20, 2.50, 3.00, 4.00]

        for amm_px in slippage_amm_prices:
            sim = venue.simulate_dry_run(
                ptb=ptb,
                deepbook_bid_px=2.00,
                amm_swap_out_px=amm_px,
                borrow_amount=100_000_000,
            )
            # Under Move VM Hot Potato semantics:
            # Insufficient funds -> SplitCoins fails -> Command 6 never reached -> VM aborts
            assert sim["status"] == "ABORTED", f"Expected abort at AMM px {amm_px}"
            assert sim["hot_potato_aborted"] is True
            assert sim["zero_leg_risk_preserved"] is True
            assert sim["state_mutations"] == 0, "Move VM must commit ZERO state mutations on abort"
            assert sim["net_profit_quote"] == 0.0
            assert "INSUFFICIENT_BALANCE_FOR_REPAYMENT" in sim["error"]
            assert sim["gas_cost_sui"] == 0.002  # Only gas fee burned

        await venue.disconnect()

    @pytest.mark.asyncio
    async def test_sui_hot_potato_zero_lingering_debt_in_order_execution(self):
        """Verifies that OrderExecutionResult reflects clean abort with 0 lingering debt or fees."""
        venue = SuiDeepBookVenue(env="mainnet")
        await venue.connect()

        # Submit an arbitrage order that is unprofitable due to AMM slippage
        res = await venue.submit_order({
            "symbol": "SUI/USDC",
            "price": 2.00,      # DeepBook bid
            "amm_price": 2.05,  # AMM price higher -> negative spread
            "size": 100.0,
            "is_arb_ptb": True,
        })

        assert res.status == "REJECTED", f"Status must be REJECTED, got {res.status}"
        assert res.order_id.startswith("PTB-REVERT-")
        assert res.fee_bps == 0.0, "Aborted PTB must charge 0 fee"
        assert res.rebate_bps == 0.0
        assert res.size == 100.0

        await venue.disconnect()

    def test_sui_hot_potato_infinitesimal_boundary_shortfall(self):
        """Tests exact 1-mist shortfall vs exact breakeven boundary."""
        venue = SuiDeepBookVenue(env="mainnet")
        ptb = venue.build_arbitrage_ptb()
        borrow_amount = 100_000_000  # 100 USDC (100,000,000 mist)

        # 1. Exact breakeven: DeepBook Bid == AMM Swap Out
        sim_breakeven = venue.simulate_dry_run(
            ptb=ptb,
            deepbook_bid_px=2.00,
            amm_swap_out_px=2.00,
            borrow_amount=borrow_amount,
        )
        assert sim_breakeven["status"] == "SUCCESS"
        assert sim_breakeven["net_profit_quote"] == 0.0
        assert sim_breakeven["state_mutations"] == 8

        # 2. Shortfall of exactly 1 mist: proceeds = 99,999,999 mist
        # We find deepbook_bid_px such that proceeds = 99,999,999
        # proceeds = (borrow / 1e6 / amm_px) * deepbook_bid * 1e6 = borrow * (deepbook_bid / amm_px)
        # So deepbook_bid = amm_px * (borrow - 1) / borrow
        amm_px = 2.0
        bid_px_shortfall = amm_px * (borrow_amount - 1) / borrow_amount
        sim_shortfall = venue.simulate_dry_run(
            ptb=ptb,
            deepbook_bid_px=bid_px_shortfall,
            amm_swap_out_px=amm_px,
            borrow_amount=borrow_amount,
        )
        assert sim_shortfall["status"] == "ABORTED"
        assert sim_shortfall["hot_potato_aborted"] is True
        assert sim_shortfall["state_mutations"] == 0

        # 3. Surplus of exactly 1 mist: proceeds = 100,000,001 mist
        bid_px_surplus = amm_px * (borrow_amount + 1) / borrow_amount
        sim_surplus = venue.simulate_dry_run(
            ptb=ptb,
            deepbook_bid_px=bid_px_surplus,
            amm_swap_out_px=amm_px,
            borrow_amount=borrow_amount,
        )
        assert sim_surplus["status"] == "SUCCESS"
        assert sim_surplus["net_profit_quote"] > 0

    @pytest.mark.asyncio
    async def test_sui_hot_potato_catastrophic_sandwich_and_flash_crash(self):
        """Stress tests extreme adversarial events: 10x AMM price spike and 99% CLOB crash."""
        venue = SuiDeepBookVenue(env="mainnet")
        await venue.connect()
        ptb = venue.build_arbitrage_ptb()

        # Scenario A: Massive AMM sandwich attack drains AMM pool (AMM px spikes 10x)
        sim_sandwich = venue.simulate_dry_run(
            ptb=ptb,
            deepbook_bid_px=2.00,
            amm_swap_out_px=20.00,  # 10x price spike on AMM
            borrow_amount=500_000_000,
        )
        assert sim_sandwich["status"] == "ABORTED"
        assert sim_sandwich["state_mutations"] == 0
        assert sim_sandwich["zero_leg_risk_preserved"] is True

        # Scenario B: DeepBook CLOB crash: bid price collapses by 99%
        sim_crash = venue.simulate_dry_run(
            ptb=ptb,
            deepbook_bid_px=0.02,   # 99% bid collapse
            amm_swap_out_px=2.00,
            borrow_amount=500_000_000,
        )
        assert sim_crash["status"] == "ABORTED"
        assert sim_crash["state_mutations"] == 0
        assert sim_crash["zero_leg_risk_preserved"] is True

        await venue.disconnect()


class TestSuiM1ChallengerStructuralInvariantsAndResilience:
    """Adversarial stress tests for PTB structural invariants and GraphQL client resilience."""

    @pytest.mark.parametrize("pair_name", ["SUI/USDC", "DEEP/SUI", "DEEP/USDC", "CETUS/SUI"])
    @pytest.mark.parametrize("amount", [1_000_000_000, 5_000_000_000, 10_000_000_000])
    def test_ptb_structural_invariants_4_pairs_3_amounts(self, pair_name: str, amount: int):
        """Stress tests PTB structural invariants across all 4 pairs and 3 dynamic scaling tiers."""
        builder = SuiDeepBookPTBBuilder()
        params = HotPotatoPTBParams.from_pair(pair_name, flash_borrow_amount=amount)
        ptb = builder.build_atomic_arb_ptb(params)

        assert ptb["is_atomic"] is True
        assert ptb["hot_potato_guarantee"] is True
        assert ptb["borrow_amount"] == amount
        assert ptb["pair"] == pair_name
        commands = ptb["commands"]
        assert len(commands) == 8, f"Expected 8 Move commands, got {len(commands)}"

        # 1. Check commands[0] always outputs ["borrowed_quote_coin", "flash_loan_receipt"]
        cmd0 = commands[0]
        assert cmd0["type"] == "MoveCall"
        assert cmd0["function"] == "borrow_flashloan_quote"
        assert cmd0["outputs"] == ["borrowed_quote_coin", "flash_loan_receipt"]
        assert cmd0["arguments"][1] == {"Input": amount}

        # 2. Check commands[1] references {"NestedResult": [0, 0]}
        cmd1 = commands[1]
        assert cmd1["type"] == "MoveCall"
        assert cmd1["function"] == "swap"
        assert cmd1["arguments"][2] == {"NestedResult": [0, 0]}

        # 3. Check commands[2] (deposit into BalanceManager) references swapped coin
        cmd2 = commands[2]
        assert cmd2["type"] == "MoveCall"
        assert cmd2["function"] == "deposit"
        assert cmd2["arguments"][1] == {"NestedResult": [1, 0]}

        # 4. Check commands[3] (place_market_order)
        cmd3 = commands[3]
        assert cmd3["type"] == "MoveCall"
        assert cmd3["function"] == "place_market_order"
        assert cmd3["outputs"] == ["fill_summary"]

        # 5. Check commands[4] (withdraw_all)
        cmd4 = commands[4]
        assert cmd4["type"] == "MoveCall"
        assert cmd4["function"] == "withdraw_all"
        assert cmd4["outputs"] == ["withdrawn_quote_coin"]

        # 6. Check commands[5] (SplitCoins) splits the exact borrow amount
        cmd5 = commands[5]
        assert cmd5["type"] == "SplitCoins"
        assert cmd5["coin"] == {"NestedResult": [4, 0]}
        assert cmd5["amounts"] == [{"Input": amount}]
        assert cmd5["outputs"] == ["repay_quote_coin"]

        # 7. Check commands[6] (return_flashloan_quote) references [5, 0] and [0, 1]
        cmd6 = commands[6]
        assert cmd6["type"] == "MoveCall"
        assert cmd6["function"] == "return_flashloan_quote"
        assert cmd6["arguments"][1] == {"NestedResult": [5, 0]}
        assert cmd6["arguments"][2] == {"NestedResult": [0, 1]}

        # 8. Check commands[7] (TransferObjects) transfers profit [4, 0] to sender
        cmd7 = commands[7]
        assert cmd7["type"] == "TransferObjects"
        assert cmd7["objects"] == [{"NestedResult": [4, 0]}]
        assert cmd7["recipient"] == {"Input": params.sender_address}

    def test_ptb_builder_backward_compatibility_default_params(self):
        """Verifies calling build_atomic_arb_ptb(HotPotatoPTBParams()) produces legacy structure."""
        builder = SuiDeepBookPTBBuilder()
        params = HotPotatoPTBParams()
        ptb = builder.build_atomic_arb_ptb(params)

        assert ptb["version"] == 1
        assert ptb["pair"] == "SUI/USDC"
        assert ptb["borrow_amount"] == 100_000_000
        assert ptb["base_coin_type"] == SUI_COIN_TYPE
        assert ptb["quote_coin_type"] == CIRCLE_USDC_TYPE
        assert ptb["is_atomic"] is True
        assert ptb["hot_potato_guarantee"] is True
        assert len(ptb["commands"]) == 8

        # Invariants matching existing test suites
        assert ptb["commands"][0]["function"] == "borrow_flashloan_quote"
        assert ptb["commands"][0]["outputs"] == ["borrowed_quote_coin", "flash_loan_receipt"]
        assert ptb["commands"][1]["arguments"][2] == {"NestedResult": [0, 0]}
        assert ptb["commands"][2]["arguments"][1] == {"NestedResult": [1, 0]}
        assert ptb["commands"][4]["outputs"] == ["withdrawn_quote_coin"]
        assert ptb["commands"][5]["type"] == "SplitCoins"
        assert ptb["commands"][5]["amounts"] == [{"Input": 100_000_000}]
        assert ptb["commands"][6]["function"] == "return_flashloan_quote"
        assert ptb["commands"][6]["arguments"][1] == {"NestedResult": [5, 0]}
        assert ptb["commands"][6]["arguments"][2] == {"NestedResult": [0, 1]}
        assert ptb["commands"][7]["type"] == "TransferObjects"

    @pytest.mark.asyncio
    async def test_graphql_client_edge_conditions_http_500(self):
        """Tests that SuiGraphQLClient cleanly raises HTTP error on HTTP 500 without crashing."""
        app = web.Application()

        async def handle_500(request):
            return web.Response(status=500, text="Internal Server Error")

        app.router.add_post("/graphql", handle_500)
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, "127.0.0.1", 0)
        await site.start()
        port = site._server.sockets[0].getsockname()[1]

        client = SuiGraphQLClient(endpoint=f"http://127.0.0.1:{port}/graphql")
        with pytest.raises(Exception) as exc_info:
            await client.execute("query { test }")

        assert "500" in str(exc_info.value)
        await client.close()
        await runner.cleanup()

    @pytest.mark.asyncio
    async def test_graphql_client_edge_conditions_timeout(self):
        """Tests that SuiGraphQLClient cleanly raises TimeoutError on network timeout."""
        from unittest.mock import AsyncMock

        client = SuiGraphQLClient(endpoint="http://127.0.0.1:9999/graphql")
        mock_session = MagicMock()
        mock_session.closed = False
        mock_session.close = AsyncMock()

        class TimeoutMockPost:
            async def __aenter__(self):
                raise asyncio.TimeoutError("Network read timeout")

            async def __aexit__(self, exc_type, exc_val, exc_tb):
                pass

        mock_session.post.return_value = TimeoutMockPost()
        client._session = mock_session

        with patch("urllib.request.urlopen", side_effect=TimeoutError("Urllib timeout")):
            with pytest.raises(asyncio.TimeoutError):
                await client.execute("query { test }")
        await client.close()

    @pytest.mark.asyncio
    async def test_graphql_client_edge_conditions_malformed_json(self):
        """Tests that SuiGraphQLClient cleanly raises JSON decoding errors on invalid payload."""
        app = web.Application()

        async def handle_malformed(request):
            return web.Response(
                status=200, text="not a valid json {", content_type="application/json"
            )

        app.router.add_post("/graphql", handle_malformed)
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, "127.0.0.1", 0)
        await site.start()
        port = site._server.sockets[0].getsockname()[1]

        client = SuiGraphQLClient(endpoint=f"http://127.0.0.1:{port}/graphql")
        with pytest.raises(Exception) as exc_info:
            await client.execute("query { test }")

        assert isinstance(exc_info.value, (json.JSONDecodeError, ContentTypeError))
        await client.close()
        await runner.cleanup()

    @pytest.mark.asyncio
    async def test_graphql_client_edge_conditions_empty_balance_responses(self):
        """Tests get_wallet_balances() behavior with empty address and zero balances."""
        app = web.Application()

        responses = [
            {"data": {"address": None}},  # Uninitialized address
            {"data": {}},                 # Empty data
            {"data": {"address": {"sui": {"totalBalance": "0"}, "usdc": {"totalBalance": "0"}}}},
        ]
        curr_idx = 0

        async def handle_balance(request):
            nonlocal curr_idx
            res = responses[curr_idx]
            curr_idx = min(curr_idx + 1, len(responses) - 1)
            return web.json_response(res)

        app.router.add_post("/graphql", handle_balance)
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, "127.0.0.1", 0)
        await site.start()
        port = site._server.sockets[0].getsockname()[1]

        client = SuiGraphQLClient(endpoint=f"http://127.0.0.1:{port}/graphql")

        # 1. Uninitialized wallet (address is None) -> clean 0 balances
        curr_idx = 0
        b1 = await client.get_wallet_balances("0x123")
        assert b1 == {"sui_mist": 0, "sui": 0.0, "usdc_raw": 0, "usdc": 0.0}

        # 2. Empty data dictionary -> clean 0 balances
        curr_idx = 1
        b2 = await client.get_wallet_balances("0x123")
        assert b2 == {"sui_mist": 0, "sui": 0.0, "usdc_raw": 0, "usdc": 0.0}

        # 3. Explicit zero balance strings -> clean 0 balances
        curr_idx = 2
        b3 = await client.get_wallet_balances("0x123")
        assert b3 == {"sui_mist": 0, "sui": 0.0, "usdc_raw": 0, "usdc": 0.0}

        await client.close()
        await runner.cleanup()

    @pytest.mark.asyncio
    async def test_graphql_client_null_subfield_vulnerability(self):
        """Challenges get_wallet_balances() when subfields sui or usdc are None."""
        app = web.Application()

        async def handle_null_subfields(request):
            return web.json_response({"data": {"address": {"sui": None, "usdc": None}}})

        app.router.add_post("/graphql", handle_null_subfields)
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, "127.0.0.1", 0)
        await site.start()
        port = site._server.sockets[0].getsockname()[1]

        client = SuiGraphQLClient(endpoint=f"http://127.0.0.1:{port}/graphql")

        # When subfields are None, addr_data.get('sui', {}) returns None, causing AttributeError.
        with pytest.raises(AttributeError):
            await client.get_wallet_balances("0x123")

        await client.close()
        await runner.cleanup()


# ==============================================================================
# SECTION 2: GMX V2 DYNAMIC FEE EXPLOSION & SLIPPAGE CEILING CANCELLATION
# ==============================================================================

class TestGmxV2DynamicFeeAndSlippageCeiling:
    """Stress tests GMX v2 dynamic price impact fee explosion and acceptablePrice barrier."""

    def test_gmx_price_impact_fee_formula_and_scaling(self):
        """Validates dynamic fee scaling across order sizes from $10k to $100M."""
        pool_depth = 10_000_000.0  # $10M pool
        base_fee = 5.0
        impact_factor = 50.0

        test_cases = [
            (10_000.0, 5.05),        # $10k -> 5.0 + 50 * (0.01M / 10M) = 5.05 bps
            (100_000.0, 5.50),       # $100k -> 5.0 + 50 * (0.1M / 10M) = 5.50 bps
            (1_000_000.0, 10.00),    # $1M -> 5.0 + 50 * (1M / 10M) = 10.00 bps
            (5_000_000.0, 30.00),    # $5M -> 5.0 + 50 * (5M / 10M) = 30.00 bps
            (10_000_000.0, 55.00),   # $10M (100% pool) -> 5.0 + 50 = 55.00 bps
            (50_000_000.0, 255.00),  # $50M (500% pool) -> 5.0 + 250 = 255.00 bps
            (100_000_000.0, 505.00), # $100M (1000% pool) -> 5.0 + 500 = 505.00 bps
        ]

        for size_usd, expected_fee in test_cases:
            fee = compute_gmx_price_impact_fee(
                order_size_usd=size_usd,
                pool_depth_usd=pool_depth,
                base_fee_bps=base_fee,
                impact_factor=impact_factor,
            )
            assert math.isclose(fee, expected_fee, rel_tol=1e-5), (
                f"Size ${size_usd}: expected {expected_fee} bps, got {fee} bps"
            )

    @pytest.mark.asyncio
    async def test_gmx_dynamic_fee_explosion_destroys_arbitrage_edge(self):
        """Simulates adversarial sizing where dynamic fee exceeds the lead-lag edge."""
        venue = GmxCexVenue(
            env="mainnet",
            gmx_pool_depth_usd=10_000_000.0,
            base_fee_bps=5.0,
            impact_factor=50.0,
        )
        await venue.connect()

        # Set up a 12 bps lead-lag price divergence: CEX=3003.60, GMX=3000.00
        venue.update_gmx_oracle_price("ETH/USD", price=3000.0, ts_ns=1_000_000_000)
        venue.parse_mexc_ticker({
            "s": "ETH/USD",
            "t": 1000,
            "d": {"b": "3003.60", "B": "50.0", "a": "3003.60", "A": "50.0"}
        })
        signal = venue.detect_lead_lag("ETH/USD")
        assert signal["has_signal"] is True
        gross_edge_bps = signal["divergence_bps"]
        assert math.isclose(gross_edge_bps, 12.0, rel_tol=1e-3)

        # Case A: Small order (10 ETH = $30k USD)
        # Dynamic fee = 5.0 + 50 * (30,000 / 10,000,000) = 5.15 bps < 12 bps -> PROFITABLE
        res_small = await venue.submit_order({
            "symbol": "ETH/USD",
            "side": "BUY",
            "size": 10.0,
            "price": 3000.0,
            "acceptable_price": 3010.0,
        })
        assert res_small.status == "FILLED"
        assert res_small.fee_bps < gross_edge_bps, "Small order fee should be below gross edge"
        net_edge_small = gross_edge_bps - res_small.fee_bps
        assert net_edge_small > 0, "Small order must yield positive net edge"

        # Case B: Adversarially huge order (1000 ETH = $3,000,000 USD)
        # Dynamic fee = 5.0 + 50 * (3,000,000 / 10,000,000) = 20.0 bps > 12 bps -> UNPROFITABLE
        res_huge = await venue.submit_order({
            "symbol": "ETH/USD",
            "side": "BUY",
            "size": 1000.0,
            "price": 3000.0,
            "acceptable_price": 3010.0,
        })
        assert res_huge.status == "FILLED"
        assert res_huge.fee_bps > gross_edge_bps, "Huge order fee must exceed gross edge"
        net_edge_huge = gross_edge_bps - res_huge.fee_bps
        assert net_edge_huge < 0, f"Huge order net edge must be negative: {net_edge_huge} bps"

        await venue.disconnect()

    def test_gmx_dynamic_fee_degenerate_and_boundary_inputs(self):
        """Verifies zero depth, negative size, and zero size robustness."""
        # Zero pool depth -> must return base_fee_bps without ZeroDivisionError
        fee_zero_depth = compute_gmx_price_impact_fee(order_size_usd=100_000.0, pool_depth_usd=0.0)
        assert fee_zero_depth == 5.0

        # Negative pool depth -> must return base_fee_bps without ZeroDivisionError
        fee_neg_depth = compute_gmx_price_impact_fee(order_size_usd=100_000.0, pool_depth_usd=-1_000_000.0)
        assert fee_neg_depth == 5.0

        # Negative order size -> absolute value must be used
        fee_neg_size = compute_gmx_price_impact_fee(order_size_usd=-500_000.0, pool_depth_usd=10_000_000.0)
        assert fee_neg_size == 5.0 + 50.0 * (500_000.0 / 10_000_000.0)

        # Zero order size -> returns base_fee_bps
        fee_zero_size = compute_gmx_price_impact_fee(order_size_usd=0.0, pool_depth_usd=10_000_000.0)
        assert fee_zero_size == 5.0

    @pytest.mark.asyncio
    async def test_gmx_acceptable_price_slippage_ceiling_cancellation_buy(self):
        """Validates that BUY orders cleanly CANCEL when oracle price exceeds acceptablePrice ceiling."""
        venue = GmxCexVenue(env="mainnet")
        await venue.connect()

        acceptable_ceiling = 3000.00

        # Sub-case 1: Oracle exactly at ceiling -> Fills
        venue.update_gmx_oracle_price("ETH/USD", price=3000.00)
        res_at_ceiling = await venue.submit_order({
            "symbol": "ETH/USD",
            "side": "BUY",
            "size": 1.0,
            "price": 3000.00,
            "acceptable_price": acceptable_ceiling,
        })
        assert res_at_ceiling.status == "FILLED"

        # Sub-case 2: Oracle price 1 cent above ceiling ($3000.01) -> CANCELLED
        venue.update_gmx_oracle_price("ETH/USD", price=3000.01)
        res_cent_over = await venue.submit_order({
            "symbol": "ETH/USD",
            "side": "BUY",
            "size": 1.0,
            "price": 3000.01,
            "acceptable_price": acceptable_ceiling,
        })
        assert res_cent_over.status == "CANCELLED"
        assert res_cent_over.order_id.startswith("GMX-ABORT-")
        assert res_cent_over.fee_bps == 0.0
        assert res_cent_over.rebate_bps == 0.0

        # Sub-case 3: Extreme flash pump ($3500.00) -> CANCELLED
        venue.update_gmx_oracle_price("ETH/USD", price=3500.00)
        res_pump = await venue.submit_order({
            "symbol": "ETH/USD",
            "side": "BUY",
            "size": 1.0,
            "price": 3500.00,
            "acceptable_price": acceptable_ceiling,
        })
        assert res_pump.status == "CANCELLED"
        assert res_pump.fee_bps == 0.0

        await venue.disconnect()

    @pytest.mark.asyncio
    async def test_gmx_acceptable_price_slippage_floor_cancellation_sell(self):
        """Validates that SELL orders cleanly CANCEL when oracle price drops below acceptablePrice floor."""
        venue = GmxCexVenue(env="mainnet")
        await venue.connect()

        acceptable_floor = 3000.00

        # Sub-case 1: Oracle exactly at floor -> Fills
        venue.update_gmx_oracle_price("ETH/USD", price=3000.00)
        res_at_floor = await venue.submit_order({
            "symbol": "ETH/USD",
            "side": "SELL",
            "size": 1.0,
            "price": 3000.00,
            "acceptable_price": acceptable_floor,
        })
        assert res_at_floor.status == "FILLED"

        # Sub-case 2: Oracle price 1 cent below floor ($2999.99) -> CANCELLED
        venue.update_gmx_oracle_price("ETH/USD", price=2999.99)
        res_cent_under = await venue.submit_order({
            "symbol": "ETH/USD",
            "side": "SELL",
            "size": 1.0,
            "price": 2999.99,
            "acceptable_price": acceptable_floor,
        })
        assert res_cent_under.status == "CANCELLED"
        assert res_cent_under.order_id.startswith("GMX-ABORT-")
        assert res_cent_under.fee_bps == 0.0
        assert res_cent_under.rebate_bps == 0.0

        # Sub-case 3: Extreme flash dump ($2200.00) -> CANCELLED
        venue.update_gmx_oracle_price("ETH/USD", price=2200.00)
        res_dump = await venue.submit_order({
            "symbol": "ETH/USD",
            "side": "SELL",
            "size": 1.0,
            "price": 2200.00,
            "acceptable_price": acceptable_floor,
        })
        assert res_dump.status == "CANCELLED"
        assert res_dump.fee_bps == 0.0

        await venue.disconnect()


# ==============================================================================
# SECTION 3: VELOCITY SWIFT DUTCH AUCTION PRICING AT EXTREME BOUNDARY TIMESTAMPS
# ==============================================================================

class TestVelocitySwiftDutchAuctionBoundaries:
    """Stress tests SWIFT Dutch auction mathematical curve P(t) at extreme boundaries."""

    def test_swift_auction_zero_and_negative_duration(self):
        """Validates that duration_ms <= 0 returns end_price immediately without ZeroDivisionError."""
        start_px = 100.0
        end_px = 110.0
        now = 1_000_000

        # Duration = 0
        p_zero = compute_swift_auction_price(
            start_price=start_px,
            end_price=end_px,
            start_time=now,
            duration_ms=0,
            current_time=now,
        )
        assert p_zero == end_px, f"Expected {end_px}, got {p_zero}"

        # Duration < 0 (corrupt duration)
        p_neg = compute_swift_auction_price(
            start_price=start_px,
            end_price=end_px,
            start_time=now,
            duration_ms=-400,
            current_time=now + 200,
        )
        assert p_neg == end_px, f"Expected {end_px}, got {p_neg}"

    def test_swift_auction_extreme_negative_timestamps(self):
        """Tests negative timestamps, epoch offsets, and pre-start arrival."""
        start_px = 150.0
        end_px = 160.0
        duration_ms = 4000

        # Current time is negative and before start_time
        p_pre_epoch = compute_swift_auction_price(
            start_price=start_px,
            end_price=end_px,
            start_time=0,
            duration_ms=duration_ms,
            current_time=-5000,
        )
        assert p_pre_epoch == start_px, "Pre-start time must clamp to start_price"

        # Both start_time and current_time are negative (historical/simulated offset)
        # start = -10,000, current = -8,000 -> elapsed = 2000 ms (50% progress)
        p_neg_mid = compute_swift_auction_price(
            start_price=start_px,
            end_price=end_px,
            start_time=-10_000,
            duration_ms=duration_ms,
            current_time=-8_000,
        )
        expected_mid = start_px + 0.5 * (end_px - start_px)
        assert math.isclose(p_neg_mid, expected_mid, rel_tol=1e-5)

        # start = -10,000, current = -4,000 -> elapsed = 6000 ms > 4000 ms -> clamps to end_price
        p_neg_end = compute_swift_auction_price(
            start_price=start_px,
            end_price=end_px,
            start_time=-10_000,
            duration_ms=duration_ms,
            current_time=-4_000,
        )
        assert p_neg_end == end_px

    def test_swift_auction_huge_future_offsets(self):
        """Tests astronomical future timestamps ensuring strict clamping to end_price."""
        start_px = 200.0
        end_px = 210.0
        start_time = 1_700_000_000_000
        duration_ms = 4000

        # Future offset of 10^12 ms (~31,000 years)
        p_far_future = compute_swift_auction_price(
            start_price=start_px,
            end_price=end_px,
            start_time=start_time,
            duration_ms=duration_ms,
            current_time=start_time + 10**12,
        )
        assert p_far_future == end_px

        # Max int64 timestamp (9,223,372,036,854,775,807)
        max_int64 = 2**63 - 1
        p_max_int = compute_swift_auction_price(
            start_price=start_px,
            end_price=end_px,
            start_time=start_time,
            duration_ms=duration_ms,
            current_time=max_int64,
        )
        assert p_max_int == end_px

    def test_swift_auction_monotonicity_for_buy_and_sell(self):
        """Verifies mathematical monotonicity across 1000 sub-millisecond timeline points."""
        start_time = 1_000_000
        duration_ms = 4000

        # 1. Climbing auction (Taker BUY): start=100.0, end=110.0
        buy_prices = [
            compute_swift_auction_price(100.0, 110.0, start_time, duration_ms, start_time + t)
            for t in range(0, duration_ms + 1, 4)
        ]
        for i in range(len(buy_prices) - 1):
            assert buy_prices[i] <= buy_prices[i + 1], "BUY auction curve must be non-decreasing"

        assert buy_prices[0] == 100.0
        assert buy_prices[-1] == 110.0

        # 2. Decaying auction (Taker SELL): start=110.0, end=100.0
        sell_prices = [
            compute_swift_auction_price(110.0, 100.0, start_time, duration_ms, start_time + t)
            for t in range(0, duration_ms + 1, 4)
        ]
        for i in range(len(sell_prices) - 1):
            assert sell_prices[i] >= sell_prices[i + 1], "SELL auction curve must be non-increasing"

        assert sell_prices[0] == 110.0
        assert sell_prices[-1] == 100.0

        # 3. Flat auction: start=100.0, end=100.0
        flat_prices = [
            compute_swift_auction_price(100.0, 100.0, start_time, duration_ms, start_time + t)
            for t in range(0, duration_ms + 1, 4)
        ]
        assert all(p == 100.0 for p in flat_prices)

    @pytest.mark.asyncio
    async def test_swift_toxic_flow_rejection_at_boundaries(self):
        """Validates that orders deviating beyond toxic divergence threshold are rejected with 0 rebate."""
        venue = VelocitySwiftVenue(env="devnet", max_toxic_divergence_bps=50.0)
        await venue.connect()

        venue.update_reference_oracle("SOL-PERP", 100.0)

        # Order within safe tolerance: price = 100.40 (40 bps divergence < 50 bps)
        res_safe = await venue.submit_order({
            "symbol": "SOL-PERP",
            "side": "BUY",
            "price": 100.40,
            "size": 1.0,
            "taker_order_id": "TAKER-SAFE-1",
        })
        assert res_safe.status == "FILLED"
        assert res_safe.rebate_bps == 0.25
        assert res_safe.fee_bps == -0.25

        # Order in toxic territory: price = 100.60 (60 bps divergence > 50 bps)
        res_toxic = await venue.submit_order({
            "symbol": "SOL-PERP",
            "side": "BUY",
            "price": 100.60,
            "size": 1.0,
            "taker_order_id": "TAKER-TOXIC-1",
        })
        assert res_toxic.status == "REJECTED"
        assert res_toxic.rebate_bps == 0.0
        assert res_toxic.fee_bps == 0.0

        await venue.disconnect()


# ==============================================================================
# SECTION 4: MAKER REBATE VS TAKER FEE INVERSION VERIFICATION
# ==============================================================================

class TestMakerRebateVsTakerFeeInversion:
    """Stress tests maker rebate vs taker fee invariants across execution venues."""

    @pytest.mark.asyncio
    async def test_hyperliquid_taker_order_cannot_receive_maker_rebate(self):
        """Verifies that orders with taker intent (post_only=False) strictly pay positive taker fees."""
        # Test across multiple fee tiers
        for tier in [0, 1, 2, 3, 4, 5, 6]:
            venue = HyperliquidVenue(env="testnet", fee_tier=tier)
            await venue.connect()

            tier_info = HYPERLIQUID_FEE_TIERS[tier]
            expected_taker_fee = tier_info["taker_bps"]
            assert expected_taker_fee > 0, "Taker fee must be strictly positive"

            # Submit order with post_only=False (taker execution)
            res = await venue.submit_order({
                "coin": "SOL",
                "side": "BUY",
                "price": 150.0,
                "size": 1.0,
                "post_only": False,
            })

            assert res.is_maker is False, "Order must NOT be classified as maker"
            assert res.fee_bps == expected_taker_fee, (
                f"Tier {tier}: expected taker fee {expected_taker_fee} bps, got {res.fee_bps}"
            )
            assert res.rebate_bps == 0.0, "Taker order MUST NOT receive maker rebate"
            assert res.status == "FILLED"

            await venue.disconnect()

    @pytest.mark.asyncio
    async def test_hyperliquid_alo_crossing_cancels_instead_of_paying_taker_fee(self):
        """Verifies that crossing ALO orders auto-cancel rather than filling as taker."""
        venue = HyperliquidVenue(env="testnet")
        await venue.connect()

        # Seed local orderbook with ask at $150.00
        venue.parse_l2_book({
            "channel": "l2Book",
            "data": {
                "coin": "SOL",
                "time": 1720000000000,
                "levels": [
                    [{"px": "149.00", "sz": "10.0", "n": 1}],
                    [{"px": "150.00", "sz": "5.0", "n": 1}],
                ],
            },
        })

        # Submit ALO buy order crossing the book at $151.00
        res_crossing = await venue.submit_order({
            "coin": "SOL",
            "side": "BUY",
            "price": 151.00,
            "size": 2.0,
            "post_only": True,
        })

        # ALO defense: must cancel immediately with 0 fees, never execute as taker
        assert res_crossing.status == "CANCELLED"
        assert res_crossing.fee_bps == 0.0
        assert res_crossing.rebate_bps == 0.0
        assert res_crossing.is_maker is False

        await venue.disconnect()

    @pytest.mark.asyncio
    async def test_dydx_v4_maker_rebate_vs_taker_fee_inversion(self):
        """Verifies that in dYdX v4 institutional tiers with maker rebates, takers still pay positive fees."""
        # Institutional tiers 6 and 7 offer negative maker fees (rebates)
        for tier in [6, 7]:
            venue = DydxV4Venue(env="testnet", fee_tier=tier)
            await venue.connect()

            tier_info = DYDX_FEE_TIERS[tier]
            assert tier_info["maker_bps"] < 0, "Institutional tier must have negative maker fee (rebate)"
            assert tier_info["taker_bps"] > 0, "Taker fee must be positive"

            # Case A: Maker order (post_only=True) earns rebate
            res_maker = await venue.submit_order({
                "symbol": "BTC-USD",
                "side": "BUY",
                "price": 60_000.0,
                "size": 0.1,
                "post_only": True,
            })
            assert res_maker.is_maker is True
            assert res_maker.fee_bps == tier_info["maker_bps"]
            assert res_maker.rebate_bps == abs(tier_info["maker_bps"])
            assert res_maker.status == "OPEN"

            # Case B: Taker order (post_only=False) must NOT earn rebate; must pay positive taker fee
            res_taker = await venue.submit_order({
                "symbol": "BTC-USD",
                "side": "BUY",
                "price": 60_000.0,
                "size": 0.1,
                "post_only": False,
            })
            assert res_taker.is_maker is False
            assert res_taker.fee_bps == tier_info["taker_bps"]
            assert res_taker.rebate_bps == 0.0, "Taker order must never earn maker rebate"
            assert res_taker.fee_bps > 0
            assert res_taker.status == "FILLED"

            await venue.disconnect()

    @pytest.mark.asyncio
    async def test_velocity_swift_maker_rebate_exclusivity(self):
        """Verifies that SWIFT 0.25 bps rebate is exclusively accessible to valid non-duplicate maker fills."""
        venue = VelocitySwiftVenue(env="devnet")
        await venue.connect()

        # 1. Valid maker fill against taker intent -> 0.25 bps rebate
        res_maker = await venue.submit_order({
            "symbol": "SOL-PERP",
            "side": "BUY",
            "price": 100.0,
            "size": 1.0,
            "taker_order_id": "INTENT-UNIQUE-1",
        })
        assert res_maker.status == "FILLED"
        assert res_maker.is_maker is True
        assert res_maker.rebate_bps == 0.25
        assert res_maker.fee_bps == -0.25

        # 2. Duplicate order submission -> Rejected, 0 rebate
        res_dup = await venue.submit_order({
            "symbol": "SOL-PERP",
            "side": "BUY",
            "price": 100.0,
            "size": 1.0,
            "taker_order_id": "INTENT-UNIQUE-1",
        })
        assert res_dup.status == "REJECTED"
        assert res_dup.rebate_bps == 0.0
        assert res_dup.fee_bps == 0.0

        await venue.disconnect()

    @pytest.mark.asyncio
    async def test_universal_cross_venue_fee_inversion_invariant(self):
        """Universal Invariant: For all venues, non-maker execution strictly has rebate_bps == 0.0 and fee_bps >= 0.0."""
        venues_to_test = [
            HyperliquidVenue(env="testnet", fee_tier=0),
            HyperliquidVenue(env="testnet", fee_tier=4),
            DydxV4Venue(env="testnet", fee_tier=1),
            DydxV4Venue(env="testnet", fee_tier=6),
            GmxCexVenue(env="mainnet"),
            SuiDeepBookVenue(env="mainnet"),
            KalshiFixVenue(env="mock"),
        ]

        for venue in venues_to_test:
            await venue.connect()

            # Execute standard taker or aborted order
            if isinstance(venue, SuiDeepBookVenue):
                res = await venue.submit_order({
                    "symbol": "SUI/USDC",
                    "price": 2.0,
                    "amm_price": 2.05,
                    "is_arb_ptb": True,
                })
            elif isinstance(venue, GmxCexVenue):
                res = await venue.submit_order({
                    "symbol": "ETH/USD",
                    "side": "BUY",
                    "size": 1.0,
                    "price": 3000.0,
                })
            elif isinstance(venue, KalshiFixVenue):
                res = await venue.submit_order({
                    "symbol": "KXFEDDEC26-YES",
                    "side": "BUY",
                    "price": 0.50,
                    "size": 10.0,
                })
            else:
                res = await venue.submit_order({
                    "symbol": "SOL",
                    "side": "BUY",
                    "price": 100.0,
                    "size": 1.0,
                    "post_only": False,
                })

            if not res.is_maker:
                assert res.rebate_bps == 0.0, (
                    f"Venue {venue.name}: non-maker order received non-zero rebate: {res.rebate_bps}"
                )
                assert res.fee_bps >= 0.0, (
                    f"Venue {venue.name}: non-maker order incurred negative fee: {res.fee_bps}"
                )

            await venue.disconnect()
