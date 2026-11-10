"""Automated Test Suite for Bidirectional Reverse Route DeepBook <-> Cetus (Milestone M1 / R1).

Verifies:
1. PTB construction for route_direction="REVERSE" across all 4 active pairs (SUI/USDC, DEEP/SUI, DEEP/USDC, CETUS/SUI).
   - Strict 8-command sequence:
     Command 0: borrow_flashloan_quote (produces borrowed_quote_coin, flash_loan_receipt)
     Command 1: balance_manager::deposit (deposits borrowed quote coin)
     Command 2: pool::place_market_order with is_bid=True (market buy lifting Ask)
     Command 3: balance_manager::withdraw_all (withdraws acquired base coin)
     Command 4: Cetus swap (swaps base coin for quote coin with opposite a2b flag)
     Command 5: SplitCoins (splits exact repayment principal from swap proceeds)
     Command 6: return_flashloan_quote (repayment coin and Hot Potato receipt quench)
     Command 7: TransferObjects (remaining profit to sender wallet)
2. Preflight PTB validation via SuiPTBPreflightValidator.validate_atomic_ptb_generation for REVERSE route.
3. Move VM dry-run simulation via SuiDeepBookVenue.simulate_dry_run:
   - Profitable reverse spread: status="SUCCESS", net_profit > 0, state_mutations=8, zero leg risk preserved.
   - Unprofitable reverse spread: status="ABORTED", net_profit=0, state_mutations=0, zero leg risk preserved.
4. Preflight dry-run simulation via SuiPTBPreflightValidator.simulate_ptb_dry_run for REVERSE route.
5. Bidirectional market spread calculation in SuiGraphQLClient.query_live_market_spreads:
   - forward_spread_bps, reverse_spread_bps, best_route, and optimal_spread_bps.
6. SuiBotRunner.scan_once route selection and execution triggering REVERSE route when profitable.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Ensure trading-engine directory is on sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from venues.sui_deepbook_venue import (
    CETUS_GLOBAL_CONFIG_ID,
    DEEPBOOK_PACKAGE_ID,
    SUI_PAIRS_CONFIG,
    HotPotatoPTBParams,
    OrderExecutionResult,
    SuiDeepBookPTBBuilder,
    SuiDeepBookVenue,
    SuiGraphQLClient,
)
from venues.sui_health_server import ACTIVE_PAIRS
from venues.sui_ptb_validator import (
    PTBDryRunReport,
    PTBValidationReport,
    SuiPTBPreflightValidator,
)
from venues.sui_scaling_engine import (
    OPERATOR_WALLET_ADDRESS,
    DynamicCapitalScalingEngine,
    ScalingTier,
)
from venues.sui_bot_runner import SuiBotConfig, SuiBotRunner


# ============================================================================
# Section 1: PTB Construction for Reverse Route Across All Pairs
# ============================================================================

class TestReverseRoutePTBConstruction:
    """Verifies that Hot Potato PTB Builder constructs valid 8-step reverse route transactions."""

    @pytest.mark.parametrize("pair_name", ACTIVE_PAIRS)
    def test_reverse_ptb_8_command_sequence(self, pair_name: str):
        """Validates exact 8-command sequence, types, arguments, and Hot Potato links for REVERSE route."""
        builder = SuiDeepBookPTBBuilder()
        cfg = SUI_PAIRS_CONFIG[pair_name]
        borrow_amt = cfg.default_borrow_amount

        params = HotPotatoPTBParams.from_pair(
            pair_name=pair_name,
            flash_borrow_amount=borrow_amt,
            route_direction="REVERSE",
        )
        assert params.route_direction == "REVERSE"
        assert params.a2b == (not cfg.cetus_a2b_for_quote_in)

        ptb = builder.build_atomic_arb_ptb(params)

        assert ptb["is_atomic"] is True
        assert ptb["hot_potato_guarantee"] is True
        assert ptb["route_direction"] == "REVERSE"
        assert ptb["pair"] == pair_name
        assert ptb["borrow_amount"] == borrow_amt

        commands = ptb["commands"]
        assert len(commands) == 8, f"Expected exactly 8 Move commands, got {len(commands)}"

        # Command 0: Borrow Quote Coin via DeepBook Flash Loan
        c0 = commands[0]
        assert c0["type"] == "MoveCall"
        assert c0["function"] == "borrow_flashloan_quote"
        assert c0["package"] == DEEPBOOK_PACKAGE_ID
        assert c0["arguments"][0] == {"Input": cfg.deepbook_pool_id}
        assert c0["arguments"][1] == {"Input": borrow_amt}
        assert c0["outputs"] == ["borrowed_quote_coin", "flash_loan_receipt"]

        # Command 1: Deposit Q into Balance Manager
        c1 = commands[1]
        assert c1["type"] == "MoveCall"
        assert c1["module"] == "balance_manager"
        assert c1["function"] == "deposit"
        assert c1["type_arguments"] == [cfg.quote_coin_type]
        assert c1["arguments"][1] == {"NestedResult": [0, 0]}  # borrowed quote coin

        # Command 2: Market buy base coin on DeepBook Ask (is_bid = True, lifting Ask)
        c2 = commands[2]
        assert c2["type"] == "MoveCall"
        assert c2["module"] == "pool"
        assert c2["function"] == "place_market_order"
        assert c2["arguments"][0] == {"Input": cfg.deepbook_pool_id}
        assert c2["arguments"][4] == {"Input": True}  # is_bid = True
        assert c2["outputs"] == ["fill_summary"]

        # Command 3: Withdraw acquired base coin B from Balance Manager
        c3 = commands[3]
        assert c3["type"] == "MoveCall"
        assert c3["module"] == "balance_manager"
        assert c3["function"] == "withdraw_all"
        assert c3["type_arguments"] == [cfg.base_coin_type]
        assert c3["outputs"] == ["withdrawn_base_coin"]

        # Command 4: AMM swap Base for Quote on Cetus (opposite directional swap)
        c4 = commands[4]
        assert c4["type"] == "MoveCall"
        assert c4["module"] == "pool"
        assert c4["function"] == "swap"
        assert c4["arguments"][0] == {"Input": CETUS_GLOBAL_CONFIG_ID}
        assert c4["arguments"][1] == {"Input": cfg.cetus_pool_id}
        assert c4["arguments"][2] == {"NestedResult": [3, 0]}  # withdrawn base coin
        assert c4["arguments"][3] == {"Input": not cfg.cetus_a2b_for_quote_in}  # reverse a2b
        assert c4["outputs"] == ["swapped_quote_coin"]

        # Command 5: SplitCoins exact repayment principal Q from AMM swap proceeds
        c5 = commands[5]
        assert c5["type"] == "SplitCoins"
        assert c5["coin"] == {"NestedResult": [4, 0]}  # swapped quote coin
        assert c5["amounts"] == [{"Input": borrow_amt}]
        assert c5["outputs"] == ["repay_quote_coin"]

        # Command 6: return_flashloan_quote with repayment coin and Hot Potato receipt
        c6 = commands[6]
        assert c6["type"] == "MoveCall"
        assert c6["module"] == "pool"
        assert c6["function"] == "return_flashloan_quote"
        assert c6["arguments"][0] == {"Input": cfg.deepbook_pool_id}
        assert c6["arguments"][1] == {"NestedResult": [5, 0]}  # repay coin from Command 5
        assert c6["arguments"][2] == {"NestedResult": [0, 1]}  # Hot Potato receipt from Command 0

        # Command 7: TransferObjects remaining quote profit to sender wallet
        c7 = commands[7]
        assert c7["type"] == "TransferObjects"
        assert c7["objects"] == [{"NestedResult": [4, 0]}]  # remaining profit
        assert c7["recipient"] == {"Input": params.sender_address}


# ============================================================================
# Section 2: Preflight PTB Validator for Reverse Route
# ============================================================================

class TestReverseRoutePTBValidator:
    """Verifies that SuiPTBPreflightValidator validates reverse route PTBs."""

    @pytest.fixture
    def validator(self):
        return SuiPTBPreflightValidator(
            graphql_url="https://graphql.mainnet.sui.io/graphql",
            balance_manager_id="0x0000000000000000000000000000000000000000000000000000000000000001",
            operator_address=OPERATOR_WALLET_ADDRESS,
        )

    @pytest.mark.parametrize("pair_name", ACTIVE_PAIRS)
    def test_validate_atomic_ptb_generation_reverse(self, validator, pair_name: str):
        """Verifies validate_atomic_ptb_generation passes for route_direction='REVERSE'."""
        report = validator.validate_atomic_ptb_generation(
            pair_name=pair_name,
            route_direction="REVERSE",
        )
        assert report["valid"] is True
        assert report["strict_sequence_verified"] is True
        assert report["hot_potato_borrow_linked"] is True
        assert report["hot_potato_repay_linked"] is True
        assert report["hot_potato_quenched"] is True
        assert report["pool_id_verified"] is True
        assert report["cetus_pool_id_verified"] is True
        assert report["a2b_verified"] is True
        assert report["balance_manager_verified"] is True
        assert report["command_count"] == 8
        assert report["errors"] == []
        assert report["route_direction"] == "REVERSE"


# ============================================================================
# Section 3: Move VM Dry-Run Simulation for Reverse Route
# ============================================================================

class TestReverseRouteDryRunSimulation:
    """Verifies Move VM dry-run simulation and zero leg risk guarantees for REVERSE route."""

    @pytest.fixture
    def venue(self):
        return SuiDeepBookVenue(env="mainnet")

    def test_simulate_dry_run_profitable_reverse(self, venue):
        """When Cetus price > DeepBook ask, reverse route produces SUCCESS and positive net profit."""
        # DeepBook Ask = $2.00, Cetus Price = $2.05 (+250 bps gross spread)
        pair = "SUI/USDC"
        cfg = SUI_PAIRS_CONFIG[pair]
        borrow_amt = cfg.default_borrow_amount  # 1,000 USDC = 1_000_000_000

        params = HotPotatoPTBParams.from_pair(
            pair_name=pair,
            flash_borrow_amount=borrow_amt,
            route_direction="REVERSE",
            deduct_fees=True,
        )
        ptb = venue.ptb_builder.build_atomic_arb_ptb(params)

        sim = venue.simulate_dry_run(
            ptb=ptb,
            deepbook_bid_px=1.98,
            amm_swap_out_px=2.05,
            borrow_amount=borrow_amt,
            pair=pair,
            deduct_fees=True,
            route_direction="REVERSE",
            deepbook_ask_px=2.00,
        )

        assert sim["status"] == "SUCCESS"
        assert sim["hot_potato_satisfied"] is True
        assert sim["zero_leg_risk_preserved"] is True
        assert sim["net_profit_quote"] > 0.0
        assert sim["state_mutations"] == 8
        assert sim["gas_cost_sui"] == 0.002
        assert sim["route_direction"] == "REVERSE"

    def test_simulate_dry_run_unprofitable_reverse_clean_abort_zero_leg_risk(self, venue):
        """When Cetus price < DeepBook ask, SplitCoins fails and Move VM aborts cleanly with 0 leg risk."""
        # DeepBook Ask = $2.00, Cetus Price = $1.95 (negative spread for reverse route)
        pair = "SUI/USDC"
        cfg = SUI_PAIRS_CONFIG[pair]
        borrow_amt = cfg.default_borrow_amount

        params = HotPotatoPTBParams.from_pair(
            pair_name=pair,
            flash_borrow_amount=borrow_amt,
            route_direction="REVERSE",
            deduct_fees=True,
        )
        ptb = venue.ptb_builder.build_atomic_arb_ptb(params)

        sim = venue.simulate_dry_run(
            ptb=ptb,
            deepbook_bid_px=1.90,
            amm_swap_out_px=1.95,
            borrow_amount=borrow_amt,
            pair=pair,
            deduct_fees=True,
            route_direction="REVERSE",
            deepbook_ask_px=2.00,
        )

        assert sim["status"] == "ABORTED"
        assert sim["hot_potato_aborted"] is True
        assert sim["zero_leg_risk_preserved"] is True
        assert sim["net_profit_quote"] == 0.0
        assert sim["state_mutations"] == 0
        assert sim["shortfall_native"] > 0
        assert "INSUFFICIENT_BALANCE_FOR_REPAYMENT" in sim["error"]
        assert sim["route_direction"] == "REVERSE"

    def test_validator_simulate_ptb_dry_run_reverse(self):
        """Tests SuiPTBPreflightValidator.simulate_ptb_dry_run for REVERSE route."""
        validator = SuiPTBPreflightValidator(
            graphql_url="https://graphql.mainnet.sui.io/graphql",
            balance_manager_id="0x0000000000000000000000000000000000000000000000000000000000000001",
            operator_address=OPERATOR_WALLET_ADDRESS,
        )

        # Profitable: +120 bps reverse spread
        rep_success = validator.simulate_ptb_dry_run(
            pair_name="SUI/USDC",
            spread_bps=120.0,
            base_price=2.00,
            route_direction="REVERSE",
            deepbook_ask_px=2.00,
        )
        assert rep_success["status"] == "SUCCESS"
        assert rep_success["net_profit"] > 0.0
        assert rep_success["zero_leg_risk_preserved"] is True
        assert rep_success["route_direction"] == "REVERSE"

        # Unprofitable: -30 bps reverse spread (clean abort)
        rep_abort = validator.simulate_ptb_dry_run(
            pair_name="SUI/USDC",
            spread_bps=-30.0,
            base_price=2.00,
            route_direction="REVERSE",
            deepbook_ask_px=2.00,
        )
        assert rep_abort["status"] == "ABORTED"
        assert rep_abort["net_profit"] == 0.0
        assert rep_abort["zero_leg_risk_preserved"] is True
        assert rep_abort["state_mutations"] == 0
        assert rep_abort["route_direction"] == "REVERSE"


# ============================================================================
# Section 4: Live Market Spread Calculation (Bidirectional)
# ============================================================================

class TestBidirectionalMarketSpreads:
    """Verifies that query_live_market_spreads calculates forward, reverse, best route, and optimal spreads."""

    @pytest.mark.asyncio
    async def test_spread_calculation_reverse_opportunity(self):
        """When Cetus price > DeepBook Ask, best_route must be 'REVERSE' and reverse_spread_bps > 0."""
        client = SuiGraphQLClient(endpoint="https://graphql.mainnet.sui.io/graphql")

        mock_data = {
            "p_sui_usdc": {"asMoveObject": {"contents": {"json": {}}}},
            "p_deep_sui": None,
            "p_deep_usdc": None,
            "p_cetus_sui": None,
            "d_sui_usdc": None,
            "d_deep_sui": None,
            "d_deep_usdc": None,
            "d_cetus_sui": None,
            "cetus_bids": {},
        }

        # Indexer books with Ask at 1.90 (cheaper than Cetus 2.00) and Bid at 1.88
        mock_orderbooks = {
            "SUI/USDC": {
                "bids": [["1.88", "1000.0"]],
                "asks": [["1.90", "1000.0"]],
            }
        }

        with patch.object(client, "execute", new_callable=AsyncMock) as mock_exec, \
             patch.object(client, "_fetch_deepbook_indexer_orderbook", side_effect=lambda sym: mock_orderbooks.get(sym.replace("_", "/"), {})):
            mock_exec.return_value = {"data": mock_data}

            spreads = await client.query_live_market_spreads()
            sui_usdc = spreads["SUI/USDC"]

            assert sui_usdc["cetus_price"] == 2.0
            assert sui_usdc["deepbook_ask"] == 1.90
            assert sui_usdc["deepbook_price"] == 1.88
            assert sui_usdc["forward_spread_bps"] < 0.0
            assert sui_usdc["reverse_spread_bps"] > 0.0
            assert sui_usdc["best_route"] == "REVERSE"
            assert sui_usdc["optimal_spread_bps"] == sui_usdc["reverse_spread_bps"]

        await client.close()

    @pytest.mark.asyncio
    async def test_spread_calculation_forward_opportunity(self):
        """When DeepBook Bid > Cetus price, best_route must be 'FORWARD' and forward_spread_bps > 0."""
        client = SuiGraphQLClient(endpoint="https://graphql.mainnet.sui.io/graphql")

        mock_data = {
            "p_sui_usdc": {"asMoveObject": {"contents": {"json": {}}}},
            "p_deep_sui": None,
            "p_deep_usdc": None,
            "p_cetus_sui": None,
            "d_sui_usdc": None,
            "d_deep_sui": None,
            "d_deep_usdc": None,
            "d_cetus_sui": None,
            "cetus_bids": {},
        }

        # Indexer books with Bid at 2.10 (higher than Cetus 2.00) and Ask at 2.12
        mock_orderbooks = {
            "SUI/USDC": {
                "bids": [["2.10", "1000.0"]],
                "asks": [["2.12", "1000.0"]],
            }
        }

        with patch.object(client, "execute", new_callable=AsyncMock) as mock_exec, \
             patch.object(client, "_fetch_deepbook_indexer_orderbook", side_effect=lambda sym: mock_orderbooks.get(sym.replace("_", "/"), {})):
            mock_exec.return_value = {"data": mock_data}

            spreads = await client.query_live_market_spreads()
            sui_usdc = spreads["SUI/USDC"]

            assert sui_usdc["cetus_price"] == 2.0
            assert sui_usdc["deepbook_price"] == 2.10
            assert sui_usdc["deepbook_ask"] == 2.12
            assert sui_usdc["forward_spread_bps"] > 0.0
            assert sui_usdc["reverse_spread_bps"] < 0.0
            assert sui_usdc["best_route"] == "FORWARD"
            assert sui_usdc["optimal_spread_bps"] == sui_usdc["forward_spread_bps"]

        await client.close()


# ============================================================================
# Section 5: Bot Runner Route Selection & Live Execution
# ============================================================================

class TestBotRunnerReverseRouteExecution:
    """Verifies that SuiBotRunner scans, detects, and executes reverse routes when profitable."""

    @pytest.mark.asyncio
    async def test_scan_once_triggers_reverse_route_when_profitable(self):
        """Validates that scan_once sets route_direction='REVERSE' and triggers order submission."""
        config = SuiBotConfig(
            graphql_url="https://graphql.mainnet.sui.io/graphql",
            operator_address=OPERATOR_WALLET_ADDRESS,
            balance_manager_id="0x0000000000000000000000000000000000000000000000000000000000000001",
            dry_run_mode=False,
        )
        validator = SuiPTBPreflightValidator(
            graphql_url=config.graphql_url,
            balance_manager_id=config.balance_manager_id,
            operator_address=config.operator_address,
        )
        runner = SuiBotRunner(config=config, validator=validator)

        # Mock market spreads: SUI/USDC has reverse spread of +150 bps
        mock_spreads = {
            "SUI/USDC": {
                "cetus_price": 2.05,
                "deepbook_price": 1.98,
                "deepbook_ask": 2.00,
                "spread_bps": -341.5,
                "forward_spread_bps": -341.5,
                "reverse_spread_bps": 250.0,
                "best_route": "REVERSE",
                "optimal_spread_bps": 250.0,
                "bid_size": 50000.0,
                "bid_depth_quote": 100000.0,
                "source": "mock",
            },
            "DEEP/SUI": {
                "cetus_price": 0.05,
                "deepbook_price": 0.05,
                "deepbook_ask": 0.05,
                "spread_bps": 0.0,
                "forward_spread_bps": 0.0,
                "reverse_spread_bps": 0.0,
                "best_route": "FORWARD",
                "optimal_spread_bps": 0.0,
                "source": "mock",
            },
            "DEEP/USDC": {
                "cetus_price": 0.10,
                "deepbook_price": 0.10,
                "deepbook_ask": 0.10,
                "spread_bps": 0.0,
                "forward_spread_bps": 0.0,
                "reverse_spread_bps": 0.0,
                "best_route": "FORWARD",
                "optimal_spread_bps": 0.0,
                "source": "mock",
            },
            "CETUS/SUI": {
                "cetus_price": 0.20,
                "deepbook_price": 0.20,
                "deepbook_ask": 0.20,
                "spread_bps": 0.0,
                "forward_spread_bps": 0.0,
                "reverse_spread_bps": 0.0,
                "best_route": "FORWARD",
                "optimal_spread_bps": 0.0,
                "source": "mock",
            },
        }

        # Mock submit_order returning FILLED
        mock_result = OrderExecutionResult(
            venue="sui_deepbook",
            order_id="PTB-REVERSE-EXEC-12345",
            symbol="SUI/USDC",
            side="BUY",
            price=2.00,
            size=1_000_000_000,
            fee_bps=0.0,
            rebate_bps=0.0,
            is_maker=False,
            status="FILLED",
            latency_ms=12.5,
            timestamp_ns=1000000,
        )

        with patch.object(runner, "poll_market_spreads", return_value=mock_spreads), \
             patch.object(validator.venue, "submit_order", new_callable=AsyncMock, return_value=mock_result) as mock_submit:
            results = await runner.scan_once()

            sui_res = next(r for r in results if r["pair"] == "SUI/USDC")
            assert sui_res["route_direction"] == "REVERSE"
            assert sui_res["status"] == "SUCCESS"
            assert sui_res["net_profit_usd"] >= 0.05
            assert sui_res["execution_status"] == "EXECUTED"

            # Check that submit_order was called with route_direction="REVERSE"
            assert mock_submit.call_count == 1
            call_args = mock_submit.call_args[0][0]
            assert call_args["route_direction"] == "REVERSE"
            assert call_args["symbol"] == "SUI/USDC"


# ============================================================================
# Section 6: Reverse Route Across All Scaling Tiers & Multi-Pair Invariants
# ============================================================================

class TestReverseRouteMultiPairScaling:
    """Verifies that reverse route PTB and simulation maintain invariants across all pairs and tiers."""

    @pytest.mark.parametrize("pair_name", ACTIVE_PAIRS)
    @pytest.mark.parametrize("tier_amount", [1_000_000_000, 5_000_000_000, 10_000_000_000])
    def test_reverse_ptb_invariants_all_pairs_and_tiers(self, pair_name: str, tier_amount: int):
        """Verifies PTB construction and validation across all 4 pairs and 3 scaling tiers."""
        validator = SuiPTBPreflightValidator(
            graphql_url="https://graphql.mainnet.sui.io/graphql",
            balance_manager_id="0x0000000000000000000000000000000000000000000000000000000000000001",
            operator_address=OPERATOR_WALLET_ADDRESS,
        )
        report = validator.validate_atomic_ptb_generation(
            pair_name=pair_name,
            borrow_amount=tier_amount,
            route_direction="REVERSE",
        )
        assert report["valid"] is True
        assert report["borrow_amount"] == tier_amount
        assert report["route_direction"] == "REVERSE"
        assert report["strict_sequence_verified"] is True
        assert report["hot_potato_quenched"] is True
        assert report["errors"] == []

    @pytest.mark.parametrize("pair_name", ACTIVE_PAIRS)
    def test_reverse_dry_run_zero_spread_clean_abort_zero_leg_risk(self, pair_name: str):
        """When spread is 0.0 bps, fee hurdles cause SplitCoins to abort with 0 leg risk and 0 state mutations."""
        validator = SuiPTBPreflightValidator(
            graphql_url="https://graphql.mainnet.sui.io/graphql",
            balance_manager_id="0x0000000000000000000000000000000000000000000000000000000000000001",
            operator_address=OPERATOR_WALLET_ADDRESS,
        )
        res = validator.simulate_ptb_dry_run(
            pair_name=pair_name,
            spread_bps=0.0,
            route_direction="REVERSE",
            deduct_fees=True,
        )
        assert res["status"] == "ABORTED"
        assert res["zero_leg_risk_preserved"] is True
        assert res["state_mutations"] == 0
        assert res["net_profit"] == 0.0
        assert res["route_direction"] == "REVERSE"
        assert res["shortfall_native"] > 0
        assert res["hot_potato_aborted"] is True

    @pytest.mark.parametrize("pair_name", ACTIVE_PAIRS)
    def test_reverse_dry_run_profitable_spread_all_pairs(self, pair_name: str):
        """When spread is +200 bps (> fee hurdle), reverse route simulation succeeds with profit extraction."""
        validator = SuiPTBPreflightValidator(
            graphql_url="https://graphql.mainnet.sui.io/graphql",
            balance_manager_id="0x0000000000000000000000000000000000000000000000000000000000000001",
            operator_address=OPERATOR_WALLET_ADDRESS,
        )
        res = validator.simulate_ptb_dry_run(
            pair_name=pair_name,
            spread_bps=200.0,
            route_direction="REVERSE",
            deduct_fees=True,
        )
        assert res["status"] == "SUCCESS"
        assert res["zero_leg_risk_preserved"] is True
        assert res["state_mutations"] == 8
        assert res["net_profit"] > 0.0
        assert res["route_direction"] == "REVERSE"
        assert res["hot_potato_satisfied"] is True

