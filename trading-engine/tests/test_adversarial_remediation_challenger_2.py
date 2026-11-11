"""Adversarial Empirical Verification Test Suite for Remediation (Challenger 2).

Scope:
1. Live On-Chain verification of BalanceManager object 0x0c03cf4f6c841d0e7d4a939004d1a8c8a8102251d2daeaf45df2f48ba5be271c
   on Sui Mainnet GraphQL.
2. Stress testing query_live_market_spreads() and poll_market_spreads() under:
   - Network timeout (asyncio.TimeoutError)
   - HTTP 502/500/504 errors
   - Empty/corrupted JSON payloads
   - GraphQL error payloads
   - Non-numeric / malformed current_sqrt_price and EWMA
   - Partial pair responses
3. Verification that fail-safe fallback to 0.0 bps preserves zero leg risk and aborts cleanly.
4. Verification of SuiBotRunner.scan_once() multi-pair parsing across all 4 pairs and log summary.
"""

from __future__ import annotations

import asyncio
import json
import time
from typing import Any, Dict
from unittest.mock import AsyncMock, patch

import pytest
import urllib.request

from venues.sui_bot_runner import (
    ACTIVE_PAIRS,
    DEFAULT_PAIR_BASE_PRICES,
    SuiBotConfig,
    SuiBotRunner,
)
from venues.sui_deepbook_venue import (
    SUI_GRAPHQL_MAINNET,
    SuiDeepBookPTBBuilder,
    SuiDeepBookVenue,
    SuiGraphQLClient,
)
from venues.sui_ptb_validator import SuiPTBPreflightValidator


TARGET_BALANCE_MANAGER_ID = "0x0c03cf4f6c841d0e7d4a939004d1a8c8a8102251d2daeaf45df2f48ba5be271c"
OPERATOR_WALLET_ADDRESS = "0x5621a8e7199680512ee829565b96febea2587e534fd69b33f04004298d7e5ce9"


class TestOnChainBalanceManager:
    """Empirical verification of BalanceManager on Sui Mainnet GraphQL."""

    def test_on_chain_balance_manager_live_graphql(self):
        """Directly queries Sui Mainnet GraphQL to assert object existence, type, and shared ownership."""
        query = """
        query GetObject($id: SuiAddress!) {
          object(address: $id) {
            address
            version
            digest
            asMoveObject {
              contents {
                type {
                  repr
                }
                json
              }
            }
            owner {
              __typename
              ... on Shared {
                initialSharedVersion
              }
            }
            previousTransaction {
              digest
              sender {
                address
              }
            }
          }
        }
        """
        payload = json.dumps({"query": query, "variables": {"id": TARGET_BALANCE_MANAGER_ID}}).encode("utf-8")
        req = urllib.request.Request(
            SUI_GRAPHQL_MAINNET,
            data=payload,
            headers={"Content-Type": "application/json"},
        )

        with urllib.request.urlopen(req, timeout=12) as response:
            assert response.status == 200
            data = json.loads(response.read().decode("utf-8"))

        assert "data" in data, f"No data in response: {data}"
        obj = data["data"].get("object")
        assert obj is not None, f"BalanceManager {TARGET_BALANCE_MANAGER_ID} not found on Mainnet GraphQL"

        # 1. Address matches
        assert obj["address"].lower() == TARGET_BALANCE_MANAGER_ID.lower()

        # 2. Type matches BalanceManager Move struct
        move_obj = obj.get("asMoveObject")
        assert move_obj is not None, "Object is not a Move object"
        type_repr = move_obj["contents"]["type"]["repr"]
        assert type_repr.endswith("::balance_manager::BalanceManager"), f"Unexpected type: {type_repr}"

        # 3. Ownership is Shared
        owner = obj.get("owner", {})
        assert owner.get("__typename") == "Shared", f"Object is not shared: {owner}"
        assert int(owner.get("initialSharedVersion", 0)) > 0

        # 4. JSON contents owner matches operator wallet
        contents_json = move_obj["contents"]["json"]
        assert contents_json.get("owner", "").lower() == OPERATOR_WALLET_ADDRESS.lower(), (
            f"Inner owner mismatch: {contents_json.get('owner')}"
        )

        # 5. Creator transaction sender matches operator wallet
        prev_tx = obj.get("previousTransaction", {})
        assert prev_tx.get("sender", {}).get("address", "").lower() == OPERATOR_WALLET_ADDRESS.lower()


class TestLiveMarketSpreadStress:
    """Stress testing query_live_market_spreads() and fail-safe fallback mechanisms."""

    @pytest.mark.asyncio
    async def test_live_query_market_spreads_baseline(self):
        """Tests live GraphQL query returns valid entries for all 4 pairs."""
        client = SuiGraphQLClient(endpoint=SUI_GRAPHQL_MAINNET)
        spreads = await client.query_live_market_spreads()
        
        # Verify all 4 pairs present
        for pair in ACTIVE_PAIRS:
            assert pair in spreads, f"Missing pair: {pair}"
            pair_data = spreads[pair]
            assert pair_data["cetus_price"] > 0
            assert pair_data["deepbook_price"] > 0
            assert isinstance(pair_data["spread_bps"], float)
            assert pair_data["source"] == "live_graphql"

    @pytest.mark.asyncio
    async def test_poll_spreads_fallback_on_timeout(self):
        """Simulates network timeout in query_live_market_spreads and tests fallback to 0.0 bps."""
        client = SuiGraphQLClient(endpoint=SUI_GRAPHQL_MAINNET)
        validator = SuiPTBPreflightValidator(
            graphql_url=SUI_GRAPHQL_MAINNET,
            balance_manager_id=TARGET_BALANCE_MANAGER_ID,
            operator_address=OPERATOR_WALLET_ADDRESS,
        )
        validator.graphql_client = client

        # Mock execute to simulate timeout
        async def mock_timeout(*args, **kwargs):
            await asyncio.sleep(2.0)
            return {}

        client.execute = mock_timeout

        config = SuiBotConfig(
            graphql_url=SUI_GRAPHQL_MAINNET,
            operator_address=OPERATOR_WALLET_ADDRESS,
            balance_manager_id=TARGET_BALANCE_MANAGER_ID,
        )
        runner = SuiBotRunner(config=config, validator=validator)

        # Force bypass cached spreads
        runner._cached_market_spreads = None
        runner._last_spread_poll_time = 0.0

        spreads = await runner.poll_market_spreads()
        assert len(spreads) == len(ACTIVE_PAIRS)
        for pair in ACTIVE_PAIRS:
            assert spreads[pair]["spread_bps"] == 0.0
            assert spreads[pair]["source"] == "fallback"

    @pytest.mark.asyncio
    async def test_poll_spreads_fallback_on_http_502(self):
        """Simulates HTTP 502 Bad Gateway and tests fallback to 0.0 bps."""
        client = SuiGraphQLClient(endpoint=SUI_GRAPHQL_MAINNET)
        validator = SuiPTBPreflightValidator(
            graphql_url=SUI_GRAPHQL_MAINNET,
            balance_manager_id=TARGET_BALANCE_MANAGER_ID,
            operator_address=OPERATOR_WALLET_ADDRESS,
        )
        validator.graphql_client = client

        async def mock_502(*args, **kwargs):
            raise RuntimeError("502 Bad Gateway: nginx/1.24.0")

        client.execute = mock_502

        config = SuiBotConfig(
            graphql_url=SUI_GRAPHQL_MAINNET,
            operator_address=OPERATOR_WALLET_ADDRESS,
            balance_manager_id=TARGET_BALANCE_MANAGER_ID,
        )
        runner = SuiBotRunner(config=config, validator=validator)
        runner._cached_market_spreads = None
        runner._last_spread_poll_time = 0.0

        spreads = await runner.poll_market_spreads()
        assert len(spreads) == len(ACTIVE_PAIRS)
        for pair in ACTIVE_PAIRS:
            assert spreads[pair]["spread_bps"] == 0.0
            assert spreads[pair]["source"] == "fallback"

    @pytest.mark.asyncio
    async def test_poll_spreads_fallback_on_graphql_error(self):
        """Simulates GraphQL error response (e.g. Rate Limit / Code error)."""
        client = SuiGraphQLClient(endpoint=SUI_GRAPHQL_MAINNET)
        validator = SuiPTBPreflightValidator(
            graphql_url=SUI_GRAPHQL_MAINNET,
            balance_manager_id=TARGET_BALANCE_MANAGER_ID,
            operator_address=OPERATOR_WALLET_ADDRESS,
        )
        validator.graphql_client = client

        async def mock_graphql_error(*args, **kwargs):
            return {"errors": [{"message": "Rate limit exceeded"}]}

        client.execute = mock_graphql_error

        config = SuiBotConfig(
            graphql_url=SUI_GRAPHQL_MAINNET,
            operator_address=OPERATOR_WALLET_ADDRESS,
            balance_manager_id=TARGET_BALANCE_MANAGER_ID,
        )
        runner = SuiBotRunner(config=config, validator=validator)
        runner._cached_market_spreads = None
        runner._last_spread_poll_time = 0.0

        spreads = await runner.poll_market_spreads()
        assert len(spreads) == len(ACTIVE_PAIRS)
        for pair in ACTIVE_PAIRS:
            assert spreads[pair]["spread_bps"] == 0.0
            assert spreads[pair]["source"] == "fallback"

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "corrupted_payload",
        [
            {},  # Empty response
            {"data": None},  # Null data
            {"data": {"p_sui_usdc": None}},  # Null pair object
            {"data": {"p_sui_usdc": {"asMoveObject": None}}},  # Null move object
            {
                "data": {
                    "p_sui_usdc": {
                        "asMoveObject": {
                            "contents": {"json": {"current_sqrt_price": "NOT_AN_INT"}}
                        }
                    }
                }
            },  # Non-numeric sqrt_price
            {
                "data": {
                    "p_sui_usdc": {
                        "asMoveObject": {
                            "contents": {"json": {"current_sqrt_price": "-1000"}}
                        }
                    }
                }
            },  # Negative sqrt_price
            {
                "data": {
                    "p_sui_usdc": {
                        "asMoveObject": {
                            "contents": {"json": {"current_sqrt_price": "18446744073709551616"}}
                        }
                    },
                    "d_sui_usdc": {
                        "dynamicFields": {
                            "nodes": [
                                {
                                    "name": {"json": "ZXdtYQ=="},
                                    "value": {"json": {"mean": "CORRUPTED"}},
                                }
                            ]
                        }
                    },
                }
            },  # Corrupted EWMA mean
            {
                "data": {
                    "p_sui_usdc": {
                        "asMoveObject": {
                            "contents": {"json": {"current_sqrt_price": "18446744073709551616"}}
                        }
                    },
                    # Missing other 3 pairs entirely
                }
            },  # Partial pair coverage
        ],
    )
    async def test_corrupted_payload_resilience(self, corrupted_payload: Dict[str, Any]):
        """Ensures corrupted GraphQL payloads never crash the system and fall back safely."""
        client = SuiGraphQLClient(endpoint=SUI_GRAPHQL_MAINNET)
        validator = SuiPTBPreflightValidator(
            graphql_url=SUI_GRAPHQL_MAINNET,
            balance_manager_id=TARGET_BALANCE_MANAGER_ID,
            operator_address=OPERATOR_WALLET_ADDRESS,
        )
        validator.graphql_client = client

        async def mock_corrupt(*args, **kwargs):
            return corrupted_payload

        client.execute = mock_corrupt

        config = SuiBotConfig(
            graphql_url=SUI_GRAPHQL_MAINNET,
            operator_address=OPERATOR_WALLET_ADDRESS,
            balance_manager_id=TARGET_BALANCE_MANAGER_ID,
        )
        runner = SuiBotRunner(config=config, validator=validator)
        runner._cached_market_spreads = None
        runner._last_spread_poll_time = 0.0

        spreads = await runner.poll_market_spreads()
        assert len(spreads) == len(ACTIVE_PAIRS)
        for pair in ACTIVE_PAIRS:
            # Under corrupted payload, either it cleanly returns fallback 0.0 bps
            # or parsed prices within valid range with zero crash
            assert "spread_bps" in spreads[pair]
            assert isinstance(spreads[pair]["spread_bps"], (int, float))


class TestZeroLegRiskFallbackAndScanOnce:
    """Tests zero leg risk preservation during fallback and scan_once execution."""

    def test_fallback_spread_preserves_zero_leg_risk_across_all_pairs(self):
        """Asserts that 0.0 bps fallback spread always aborts cleanly with zero leg risk."""
        validator = SuiPTBPreflightValidator(
            graphql_url=SUI_GRAPHQL_MAINNET,
            balance_manager_id=TARGET_BALANCE_MANAGER_ID,
            operator_address=OPERATOR_WALLET_ADDRESS,
        )

        for pair in ACTIVE_PAIRS:
            res = validator.simulate_ptb_dry_run(
                pair_name=pair,
                spread_bps=0.0,
            )
            assert res["status"] == "ABORTED"
            assert res["zero_leg_risk_preserved"] is True
            assert res["state_mutations"] == 0
            assert res["shortfall_native"] > 0
            assert res["net_profit"] == 0.0

    @pytest.mark.asyncio
    async def test_scan_once_all_four_pairs_under_fallback(self):
        """Verifies scan_once executes all 4 pairs under fallback spreads and logs summary."""
        validator = SuiPTBPreflightValidator(
            graphql_url=SUI_GRAPHQL_MAINNET,
            balance_manager_id=TARGET_BALANCE_MANAGER_ID,
            operator_address=OPERATOR_WALLET_ADDRESS,
        )
        # Mock client so it always triggers fallback
        validator.graphql_client = SuiGraphQLClient(endpoint=SUI_GRAPHQL_MAINNET)
        validator.graphql_client.query_live_market_spreads = AsyncMock(side_effect=asyncio.TimeoutError())

        config = SuiBotConfig(
            graphql_url=SUI_GRAPHQL_MAINNET,
            operator_address=OPERATOR_WALLET_ADDRESS,
            balance_manager_id=TARGET_BALANCE_MANAGER_ID,
            dry_run_mode=True,
        )
        runner = SuiBotRunner(config=config, validator=validator)

        results = await runner.scan_once()
        assert len(results) == len(ACTIVE_PAIRS)
        pairs_scanned = [r["pair"] for r in results]
        assert pairs_scanned == list(ACTIVE_PAIRS)

        for r in results:
            assert r["status"] == "ABORTED"
            assert r["execution_status"] == "SIMULATED"
            assert r["zero_leg_risk_preserved"] is True
            assert r["spread_bps"] == 0.0

        assert runner.total_executions_attempted == 0

    @pytest.mark.asyncio
    async def test_scan_once_all_four_pairs_under_live_spreads(self):
        """Verifies scan_once parses live prices from GraphQL for all 4 pairs."""
        validator = SuiPTBPreflightValidator(
            graphql_url=SUI_GRAPHQL_MAINNET,
            balance_manager_id=TARGET_BALANCE_MANAGER_ID,
            operator_address=OPERATOR_WALLET_ADDRESS,
        )
        validator.graphql_client = SuiGraphQLClient(endpoint=SUI_GRAPHQL_MAINNET)

        config = SuiBotConfig(
            graphql_url=SUI_GRAPHQL_MAINNET,
            operator_address=OPERATOR_WALLET_ADDRESS,
            balance_manager_id=TARGET_BALANCE_MANAGER_ID,
            dry_run_mode=True,  # Ensure no actual order execution during test
        )
        runner = SuiBotRunner(config=config, validator=validator)

        results = await runner.scan_once()
        assert len(results) == len(ACTIVE_PAIRS)
        for r in results:
            assert r["pair"] in ACTIVE_PAIRS
            assert r["cetus_price"] > 0
            assert r["deepbook_price"] > 0
            assert isinstance(r["spread_bps"], float)
            assert r["zero_leg_risk_preserved"] is True
