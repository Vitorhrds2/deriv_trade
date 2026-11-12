"""Regression tests for the 4 Sui Mainnet arbitrage audit fixes.

Covers:
1. Sub-$100 USDC raw atomic size preservation (`size_is_raw=True`) in `submit_order`
   vs legacy human-unit scaling preservation when omitted.
2. Zero-liquidity Turbos pool exclusion (`turbos_liquidity <= 0`, e.g., CETUS/SUI)
   in `query_live_market_spreads`.
3. Multi-level asks VWAP + quote depth aggregation (`REVERSE`) via shared
   `_aggregate_orderbook_side` helper.
4. Pre-broadcast shrunk-tranche `min_profit_usd` gate, realistic 0.005 SUI gas floor,
   proportional profit scaling on shrunk fills, and 6-decimal `/health` precision.
"""

from __future__ import annotations

import math
from typing import Any, Dict, List
from unittest.mock import AsyncMock, patch

import pytest

from venues.base import OrderExecutionResult
from venues.sui_bot_runner import SuiBotConfig, SuiBotRunner
from venues.sui_deepbook_venue import (
    SUI_GRAPHQL_MAINNET,
    SUI_PAIRS_CONFIG,
    SuiDeepBookVenue,
    SuiGraphQLClient,
)


def _setup_live_mock_venue(
    sim_statuses: List[str],
    exec_digest: str = "6AGVmMockedLiveDigest",
):
    """Creates a SuiDeepBookVenue configured for mocked live-signed submit_order calls."""
    venue = SuiDeepBookVenue(env="mainnet")
    venue.private_key = "suiprivkey1qztestdummyseedvaluethatmatchesbech32prefixonly123456"

    mock_gql = AsyncMock()
    mock_gql.get_gas_coin_and_price = AsyncMock(
        return_value=({"address": "0x" + "1" * 64, "version": 1, "digest": "11111111111111111111111111111111"}, 1000)
    )
    mock_gql.get_live_deepbook_fee_params = AsyncMock(
        return_value={"taker_bps": 2.0, "maker_bps": 0.0, "is_whitelisted": False, "deep_per_base": 0.0}
    )

    sim_iter = iter(sim_statuses)

    async def _sim(_tx_bytes):
        status = next(sim_iter, "ABORTED")
        if status == "SUCCESS":
            return {"data": {"simulateTransaction": {"effects": {"status": "SUCCESS"}}}}
        return {
            "data": {
                "simulateTransaction": {
                    "effects": {
                        "status": "ABORTED",
                        "executionError": {"message": "MoveAbort 104"},
                    }
                }
            }
        }

    mock_gql.simulate_transaction_bcs = AsyncMock(side_effect=_sim)
    mock_gql.execute_transaction_bcs = AsyncMock(
        return_value={"data": {"executeTransaction": {"effects": {"digest": exec_digest, "status": "SUCCESS"}}}}
    )
    venue.graphql_client = mock_gql
    return venue, mock_gql


@pytest.mark.asyncio
async def test_submit_order_size_is_raw_preserves_sub_100_usdc_and_legacy_float() -> None:
    """Fixes 10^6x over-borrowing on $25-$99.99 atomic trades while preserving legacy human sizes."""
    # 1. WAL/USDC $34.05 USDC atomic borrow with size_is_raw=True -> must NOT multiply by 10^6
    venue_raw, mock_gql_raw = _setup_live_mock_venue(["SUCCESS"], exec_digest="WALDigestRaw")
    captured_borrows: List[int] = []
    orig_bcs = venue_raw.ptb_builder.build_atomic_arb_ptb_bcs

    def _capture_bcs(*args, **kwargs):
        captured_borrows.append(int(kwargs["borrow_amount"]))
        return orig_bcs(*args, **kwargs)

    with patch.object(venue_raw.ptb_builder, "build_atomic_arb_ptb_bcs", side_effect=_capture_bcs), \
         patch.object(venue_raw.ptb_builder, "sign_transaction_bcs", return_value="SIG_B64"):
        res_wal = await venue_raw.submit_order(
            {
                "symbol": "WAL/USDC",
                "side": "BUY",
                "size": 34_053_308,
                "size_is_raw": True,
                "price": 0.12,
                "amm_price": 0.1206,
                "is_arb_ptb": True,
                "route_direction": "REVERSE",
                "amm_target": "cetus",
                "live_onchain": True,
            }
        )
        assert res_wal.status == "FILLED"
        assert res_wal.size == 34_053_308
        assert captured_borrows == [34_053_308]

        # Same check for DEEP/USDC $46.24 USDC
        captured_borrows.clear()
        mock_gql_raw.simulate_transaction_bcs = AsyncMock(
            return_value={"data": {"simulateTransaction": {"effects": {"status": "SUCCESS"}}}}
        )
        res_deep = await venue_raw.submit_order(
            {
                "symbol": "DEEP/USDC",
                "side": "BUY",
                "size": 46_239_999,
                "size_is_raw": True,
                "price": 0.014,
                "amm_price": 0.0141,
                "is_arb_ptb": True,
                "route_direction": "REVERSE",
                "amm_target": "cetus",
                "live_onchain": True,
            }
        )
        assert res_deep.status == "FILLED"
        assert res_deep.size == 46_239_999
        assert captured_borrows == [46_239_999]

    # 2. Legacy caller WITHOUT size_is_raw passing size=50.0 -> still converts to 50_000_000 atomic USDC
    venue_legacy, _ = _setup_live_mock_venue(["SUCCESS"], exec_digest="WALLegacyFloat")
    legacy_borrows: List[int] = []
    orig_legacy_bcs = venue_legacy.ptb_builder.build_atomic_arb_ptb_bcs

    def _capture_legacy(*args, **kwargs):
        legacy_borrows.append(int(kwargs["borrow_amount"]))
        return orig_legacy_bcs(*args, **kwargs)

    with patch.object(venue_legacy.ptb_builder, "build_atomic_arb_ptb_bcs", side_effect=_capture_legacy), \
         patch.object(venue_legacy.ptb_builder, "sign_transaction_bcs", return_value="SIG_B64"):
        res_legacy = await venue_legacy.submit_order(
            {
                "symbol": "WAL/USDC",
                "side": "BUY",
                "size": 50.0,
                "price": 0.12,
                "amm_price": 0.1206,
                "is_arb_ptb": True,
                "route_direction": "REVERSE",
                "amm_target": "cetus",
                "live_onchain": True,
            }
        )
        assert res_legacy.status == "FILLED"
        assert legacy_borrows == [50_000_000]


@pytest.mark.asyncio
async def test_query_live_market_spreads_ignores_zero_liquidity_turbos_pool() -> None:
    """Empty Turbos pools (turbos_liquidity == 0, e.g., CETUS/SUI) must not emit phantom spreads."""
    client = SuiGraphQLClient(endpoint=SUI_GRAPHQL_MAINNET)

    # Cetus spot = 0.023287, Turbos stale sqrt_price = 0.02368 (+170 bps phantom REVERSE spread) with liquidity="0"
    cetus_sqrt = str(int(math.sqrt(0.023287) * (2 ** 64)))
    turbos_stale_sqrt = str(int(math.sqrt(0.023680) * (2 ** 64)))
    db_ewma = str(int(0.023287 * 1_000_000_000))  # 1e9 scale for CETUS/SUI

    mock_data = {
        "data": {
            "cetus_bids": {},  # activates is_live_graphql path
            "p_cetus_sui": {
                "asMoveObject": {
                    "contents": {
                        "json": {
                            "current_sqrt_price": cetus_sqrt,
                            "liquidity": "5000000000",
                        }
                    }
                }
            },
            "t_cetus_sui": {
                "asMoveObject": {
                    "contents": {
                        "json": {
                            "sqrt_price": turbos_stale_sqrt,
                            "liquidity": "0",
                        }
                    }
                }
            },
            "d_cetus_sui": {
                "dynamicFields": {
                    "nodes": [
                        {
                            "name": {"json": "ZXdtYQ=="},
                            "value": {"json": {"mean": db_ewma}},
                        }
                    ]
                }
            },
        }
    }

    with patch.object(client, "execute", new_callable=AsyncMock, return_value=mock_data), \
         patch.object(client, "_fetch_deepbook_indexer_orderbook", new_callable=AsyncMock, return_value={}):
        spreads = await client.query_live_market_spreads()
        cetus_sui = spreads["CETUS/SUI"]
        assert cetus_sui["turbos_liquidity"] == 0.0
        assert cetus_sui["best_amm"] == "cetus"
        assert cetus_sui["amm_target"] == "cetus"
        assert cetus_sui["turbos_forward_spread_bps"] == 0.0
        assert cetus_sui["turbos_reverse_spread_bps"] == 0.0
        assert cetus_sui["turbos_net_spread_bps"] == -999999.0
        assert abs(cetus_sui["reverse_spread_bps"]) < 1.0

    await client.close()


@pytest.mark.asyncio
async def test_query_live_market_spreads_aggregates_multi_level_asks_vwap() -> None:
    """REVERSE ask depth must aggregate multi-level asks VWAP cleanly via shared helper."""
    client = SuiGraphQLClient(endpoint=SUI_GRAPHQL_MAINNET)
    cetus_sqrt = str(int(math.sqrt(0.01450) * (2 ** 64)))  # DEEP/USDC base=6, quote=6

    mock_indexer = {
        "DEEP_USDC": {
            "bids": [["0.01380", "500"]],
            "asks": [
                ["0.01395", "1000"],  # +13.95 USDC quote depth
                ["0.01397", "2000"],  # +27.94 USDC quote depth (within +50 bps of best ask & <= 0.01450*0.9994)
                ["0.01500", "5000"],  # Unprofitable (> Cetus spot 0.01450) -> must be excluded
            ],
        }
    }

    async def _mock_ob(sym: str) -> Dict[str, Any]:
        return mock_indexer.get(sym, {})

    mock_data = {
        "data": {
            "cetus_bids": {},  # activates is_live_graphql path
            "p_deep_usdc": {
                "asMoveObject": {
                    "contents": {
                        "json": {
                            "current_sqrt_price": cetus_sqrt,
                            "liquidity": "240000000000",
                        }
                    }
                }
            }
        }
    }

    with patch.object(client, "execute", new_callable=AsyncMock, return_value=mock_data), \
         patch.object(client, "_fetch_deepbook_indexer_orderbook", side_effect=_mock_ob):
        spreads = await client.query_live_market_spreads()
        deep_usdc = spreads["DEEP/USDC"]
        expected_quote_depth = 1000.0 * 0.01395 + 2000.0 * 0.01397
        expected_vwap = expected_quote_depth / 3000.0
        assert deep_usdc["ask_size"] == pytest.approx(3000.0)
        assert deep_usdc["ask_depth_quote"] == pytest.approx(expected_quote_depth, rel=1e-6)
        assert deep_usdc["deepbook_ask"] == pytest.approx(expected_vwap, rel=1e-6)

    await client.close()


@pytest.mark.asyncio
async def test_shrunk_tranche_min_profit_gate_blocks_unprofitable_fallback() -> None:
    """When full 1.0x fails dry-run and 0.5x/0.25x drops below min_profit_usd, do NOT broadcast."""
    # Reproduces LZWBTC/USDC scenario: $149.52 expected +$0.04; 0.5x = $74.76 yields ~$0.018 < $0.035 min_profit
    venue, mock_gql = _setup_live_mock_venue(["ABORTED", "SUCCESS", "SUCCESS"])

    with patch.object(venue.ptb_builder, "sign_transaction_bcs", return_value="SIG_B64"):
        res = await venue.submit_order(
            {
                "symbol": "LZWBTC/USDC",
                "side": "BUY",
                "size": 149_518_600,
                "size_is_raw": True,
                "price": 73800.0,
                "amm_price": 73980.0,
                "is_arb_ptb": True,
                "route_direction": "REVERSE",
                "amm_target": "cetus",
                "enable_tranche_fallback": True,
                "min_borrow_units": 25_000_000,
                "expected_net_profit_usd": 0.04,
                "gas_cost_usd": 0.00415,
                "min_profit_usd": 0.035,
                "live_onchain": True,
            }
        )

    assert res.status == "REJECTED"
    assert res.order_id.startswith("PTB-SIM-REVERT")
    # Only 1.0x was simulated; 0.5x and 0.25x were pruned before dry-run/broadcast
    assert mock_gql.simulate_transaction_bcs.call_count == 1
    assert mock_gql.execute_transaction_bcs.call_count == 0


@pytest.mark.asyncio
async def test_runner_scales_realized_profit_on_shrunk_fill_and_health_precision() -> None:
    """SuiBotRunner must proportionally scale shrunk fill profit and expose sub-cent precision on /health."""
    config = SuiBotConfig(port=18199, dry_run_mode=False, min_profit_usd=0.035)
    runner = SuiBotRunner(config=config)
    runner.update_gas_balance(5.0)

    mock_spreads = {
        "DEEP/USDC": {
            "cetus_price": 0.0150,
            "deepbook_price": 0.0140,
            "deepbook_ask": 0.0142,  # Wide +563 bps reverse spread -> profitable even on 0.5x shrink
            "spread_bps": 563.0,
            "forward_spread_bps": 0.0,
            "reverse_spread_bps": 563.0,
            "best_route": "REVERSE",
            "cetus_liquidity": 2.4023e11,
            "cetus_sqrt_price": int(round((0.0150 ** 0.5) * (1 << 64))),
            "ask_depth_quote": 500.0,
            "bid_depth_quote": 500.0,
        },
        "SUI/USDC": {
            "cetus_price": 1.0,
            "deepbook_price": 1.0,
            "deepbook_ask": 1.0,
            "spread_bps": 0.0,
            "forward_spread_bps": 0.0,
            "reverse_spread_bps": 0.0,
            "best_route": "FORWARD",
            "cetus_liquidity": 1e14,
            "cetus_sqrt_price": 1 << 64,
            "ask_depth_quote": 5000.0,
            "bid_depth_quote": 5000.0,
        },
    }

    submitted_params: List[Dict[str, Any]] = []

    async def _shrunk_submit(params: Dict[str, Any]) -> OrderExecutionResult:
        submitted_params.append(dict(params))
        raw_borrow = int(params["size"])
        return OrderExecutionResult(
            venue="sui_deepbook",
            order_id="RealLiveDigestShrunkHalf",
            symbol=params["symbol"],
            side="BUY",
            price=float(params["price"]),
            size=raw_borrow // 2,  # Executed at 0.5x fallback tranche
            fee_bps=0.0,
            rebate_bps=0.0,
            is_maker=False,
            status="FILLED",
            latency_ms=5.0,
            timestamp_ns=1000,
        )

    with patch.object(runner, "poll_market_spreads", return_value=mock_spreads), \
         patch.object(runner.validator.venue, "submit_order", side_effect=_shrunk_submit):
        results = await runner.scan_once()

    assert len(submitted_params) == 1
    assert submitted_params[0]["size_is_raw"] is True
    assert submitted_params[0]["gas_cost_usd"] == pytest.approx(0.005 * 1.0, rel=1e-6)

    deep_res = next(r for r in results if r["pair"] == "DEEP/USDC")
    assert deep_res["execution_status"] == "EXECUTED"
    assert deep_res["executed_borrow_amount"] == deep_res["borrow_amount"] // 2

    # Un-shrunk expected profit minus 0.5x gas adjustment: realized ~ half of pre-gas profit minus full gas
    pre_exec_net = submitted_params[0]["expected_net_profit_usd"]
    gas_usd = submitted_params[0]["gas_cost_usd"]
    expected_shrunk_net = (pre_exec_net + gas_usd) * 0.5 - gas_usd
    assert deep_res["net_profit_usd"] == pytest.approx(expected_shrunk_net, rel=1e-6)
    assert runner.scaling_engine.state.accumulated_net_profit_usdc == pytest.approx(expected_shrunk_net, rel=1e-6)

    # Also verify /health preserves 6-decimal sub-cent precision
    runner.scaling_engine.state.accumulated_net_profit_usdc = 0.002892
    health_payload = runner.health_server.get_health_data()
    assert health_payload["accumulated_profit_usdc"] == pytest.approx(0.002892, abs=1e-9)
