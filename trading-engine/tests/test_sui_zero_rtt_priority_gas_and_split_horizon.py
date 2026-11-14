"""Unit and integration tests for P0 Zero-RTT Local PTB Cache, P1 Split-Horizon gRPC + Auth/Failover,
P2 SIP-45 Priority Gas Scaling + Budget/Profit Guard, and Observability Log Fixes.
"""

from __future__ import annotations

import asyncio
import base64
import logging
from typing import Any, Dict, List
from unittest.mock import AsyncMock, patch

import aiohttp
from aiohttp import web
import pytest

from venues.sui_bot_runner import SuiBotConfig, SuiBotRunner
from venues.sui_deepbook_venue import (
    CETUS_GLOBAL_CONFIG_ID,
    CETUS_POOL_SUI_USDC,
    SUI_CLOCK_OBJECT_ID,
    SUI_USDC_POOL_ID,
    TURBOS_POOL_CONFIG_ID,
    TURBOS_VERSIONED_ID,
    SuiDeepBookPTBBuilder,
    SuiDeepBookVenue,
    SuiGraphQLClient,
    SuiLocalPTBCache,
    _decode_grpc_executed_tx,
    _decode_grpc_object,
    _format_exc_detail,
    _grpc_web_frame,
    _pb_encode_bytes_field,
    _pb_encode_varint,
    b58decode,
    b58encode,
    bcs_input_shared,
    compute_priority_gas_price,
    compute_safe_gas_budget,
    compute_tx_digest,
    get_grpc_auth_headers,
    normalize_sui_object_id,
)


TEST_PRIVATE_KEY = "suiprivkey1qqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqq555555"
TEST_SENDER = "0x5621a8e7199680512ee829565b96febea2587e534fd69b33f04004298d7e5ce9"
DIGEST_V100 = b58encode(b"\x11" * 32)
DIGEST_V101 = b58encode(b"\x22" * 32)
DIGEST_V102 = b58encode(b"\x33" * 32)


def _encode_grpc_changed_object(obj_id: str, out_ver: int, out_digest: str) -> bytes:
    return (
        _pb_encode_bytes_field(1, obj_id.encode("utf-8"))
        + (_pb_encode_varint((7 << 3) | 0) + _pb_encode_varint(out_ver))
        + _pb_encode_bytes_field(8, out_digest.encode("utf-8"))
    )


def _encode_grpc_executed_tx(
    digest: str,
    success: bool,
    error_desc: str = "",
    comp_cost: int = 100_000,
    storage_cost: int = 988_000,
    storage_rebate: int = 978_120,
    gas_object: Dict[str, Any] | None = None,
    changed_objects: List[Dict[str, Any]] | None = None,
) -> bytes:
    status_payload = _pb_encode_varint((1 << 3) | 0) + _pb_encode_varint(1 if success else 0)
    if not success and error_desc:
        err_msg = _pb_encode_bytes_field(1, error_desc.encode("utf-8"))
        status_payload += _pb_encode_bytes_field(2, err_msg)

    gas_payload = (
        _pb_encode_varint((1 << 3) | 0)
        + _pb_encode_varint(comp_cost)
        + _pb_encode_varint((2 << 3) | 0)
        + _pb_encode_varint(storage_cost)
        + _pb_encode_varint((3 << 3) | 0)
        + _pb_encode_varint(storage_rebate)
    )
    effects_payload = _pb_encode_bytes_field(4, status_payload) + _pb_encode_bytes_field(6, gas_payload)
    if changed_objects:
        for ch in changed_objects:
            effects_payload += _pb_encode_bytes_field(
                7,
                _encode_grpc_changed_object(ch["address"], int(ch["version"]), ch["digest"]),
            )
    if gas_object:
        effects_payload += _pb_encode_bytes_field(
            8,
            _encode_grpc_changed_object(
                gas_object["address"], int(gas_object["version"]), gas_object["digest"]
            ),
        )
    executed_tx = _pb_encode_bytes_field(1, digest.encode("utf-8")) + _pb_encode_bytes_field(4, effects_payload)
    return _pb_encode_bytes_field(1, executed_tx)


def test_p0_local_cache_separates_shared_registry_and_pool_state_and_preserves_mutability() -> None:
    """Verifies P0 separation of static BCS metadata vs economic state and strict mutability rules."""
    cache = SuiLocalPTBCache(rgp_ttl_seconds=1200.0)

    # Read-only shared objects MUST be mutable=False even if caller attempts mutable=True
    assert cache.is_shared_mutable(SUI_CLOCK_OBJECT_ID) is False
    assert cache.is_shared_mutable("0x6") is False
    assert cache.is_shared_mutable(CETUS_GLOBAL_CONFIG_ID) is False
    assert cache.is_shared_mutable(TURBOS_POOL_CONFIG_ID) is False

    # Pool objects and Turbos Versioned MUST be mutable=True
    assert cache.is_shared_mutable(SUI_USDC_POOL_ID) is True
    assert cache.is_shared_mutable(CETUS_POOL_SUI_USDC) is True
    assert cache.is_shared_mutable(TURBOS_VERSIONED_ID) is True

    # Attempting to force mutable=True on Clock or Cetus GlobalConfig in get_shared_input_bcs still encodes mutable=False
    clock_bcs = cache.get_shared_input_bcs(SUI_CLOCK_OBJECT_ID, mutable=True)
    assert clock_bcs == bcs_input_shared(SUI_CLOCK_OBJECT_ID, 1, False)

    cetus_cfg_bcs = cache.get_shared_input_bcs(CETUS_GLOBAL_CONFIG_ID, mutable=True)
    assert cetus_cfg_bcs == bcs_input_shared(CETUS_GLOBAL_CONFIG_ID, 1574190, False)

    # Updating mutable economic state in pool_state_cache never alters shared_object_registry
    before_ver = cache.get_shared_version(SUI_USDC_POOL_ID)
    cache.update_pool_state("SUI/USDC", {"cetus_price": 1.95, "deepbook_price": 1.98, "spread_bps": 153.8})
    assert cache.get_pool_state("SUI/USDC")["spread_bps"] == 153.8
    assert cache.get_shared_version(SUI_USDC_POOL_ID) == before_ver


def test_p0_ptb_builder_uses_local_cache_versions_and_preserves_immutable_shared_inputs() -> None:
    """Verifies build_atomic_arb_ptb_bcs uses local_cache versions while keeping Clock/Config immutable."""
    cache = SuiLocalPTBCache()
    cache.register_shared_object(SUI_USDC_POOL_ID, 777777777, mutable=True)
    cache.register_shared_object(CETUS_POOL_SUI_USDC, 888888888, mutable=True)

    builder = SuiDeepBookPTBBuilder()
    gas_coin = {
        "address": "0x" + "11" * 32,
        "version": 100,
        "digest": DIGEST_V100,
    }
    for route in ("FORWARD", "REVERSE"):
        tx_bytes = builder.build_atomic_arb_ptb_bcs(
            pair_name="SUI/USDC",
            borrow_amount=1_000_000_000,
            sender_address=TEST_SENDER,
            gas_coin=gas_coin,
            ref_gas_price=500,
            route_direction=route,
            local_cache=cache,
        )
        assert bcs_input_shared(SUI_USDC_POOL_ID, 777777777, True) in tx_bytes
        assert bcs_input_shared(CETUS_POOL_SUI_USDC, 888888888, True) in tx_bytes
        assert bcs_input_shared(SUI_CLOCK_OBJECT_ID, 1, False) in tx_bytes
        assert bcs_input_shared(CETUS_GLOBAL_CONFIG_ID, 1574190, False) in tx_bytes
        # Ensure Clock and Cetus GlobalConfig are never encoded with mutable=True
        assert bcs_input_shared(SUI_CLOCK_OBJECT_ID, 1, True) not in tx_bytes
        assert bcs_input_shared(CETUS_GLOBAL_CONFIG_ID, 1574190, True) not in tx_bytes


def test_p0_gas_coin_roll_forward_and_ttl_expiry() -> None:
    """Verifies gas_coin_ref + deep_coin_ref roll-forward from TransactionEffects and RGP TTL expiry."""
    cache = SuiLocalPTBCache(rgp_ttl_seconds=600.0)
    gas_addr = "0x" + "aa" * 32
    deep_addr = "0x" + "bb" * 32

    cache.set_gas_and_rgp(
        {"address": gas_addr, "version": 100, "digest": DIGEST_V100},
        rgp=505,
        owner=TEST_SENDER,
        now=1000.0,
    )
    cache.set_deep_coin({"address": deep_addr, "version": 50, "digest": DIGEST_V100, "balance": 10_000_000})

    # Hit before TTL expiry
    hit = cache.get_cached_gas_and_rgp(owner=TEST_SENDER, now=1500.0)
    assert hit is not None
    assert hit[0]["version"] == 100
    assert hit[1] == 505

    # Miss after TTL expiry (600s)
    assert cache.get_cached_gas_and_rgp(owner=TEST_SENDER, now=1601.0) is None

    # Refresh RGP and roll forward from protobuf-decoded TransactionEffects
    cache.set_reference_gas_price(505, now=1602.0)
    raw_resp = _encode_grpc_executed_tx(
        digest="TxDigestRoll1",
        success=True,
        gas_object={"address": gas_addr, "version": 101, "digest": DIGEST_V101},
        changed_objects=[
            {"address": gas_addr, "version": 101, "digest": DIGEST_V101},
            {"address": deep_addr, "version": 51, "digest": DIGEST_V102},
        ],
    )
    top = raw_resp[2:]  # strip outer field 1 tag+len (or decode via _decode_grpc_executed_tx)
    from venues.sui_deepbook_venue import _pb_decode_fields

    parsed = _decode_grpc_executed_tx(_pb_decode_fields(raw_resp)[1][0])
    norm = SuiGraphQLClient._normalize_effects_payload(
        success=parsed["success"],
        digest=parsed["digest"],
        gas_summary=parsed["gasSummary"],
        gas_object=parsed.get("gasObject"),
        changed_objects=parsed.get("changedObjects"),
    )
    rolled = cache.roll_forward_from_effects(norm["effects"])
    assert rolled is True
    assert cache.gas_coin_ref == {"address": gas_addr, "version": 101, "digest": DIGEST_V101}
    assert cache.deep_coin_ref is not None
    assert cache.deep_coin_ref["version"] == 51
    assert cache.deep_coin_ref["digest"] == DIGEST_V102


@pytest.mark.asyncio
async def test_p0_batch_get_objects_grpc_and_zero_rtt_consecutive_orders() -> None:
    """Verifies BatchGetObjects warmup and 0-RTT consecutive submit_order executions with gas roll-forward."""
    gas_addr = "0x" + "11" * 32
    calls = {"batch_get": 0, "get_gas_gql": 0, "sim_grpc": 0, "exec_grpc": 0}

    async def handle_batch_get(request: web.Request) -> web.Response:
        calls["batch_get"] += 1
        await request.read()
        # Return Clock (0x6, shared ver=1), Cetus GlobalConfig (shared ver=1574190), and SUI/USDC pool (shared ver=389750321)
        def _mk_shared_obj(oid: str, init_ver: int) -> bytes:
            owner_msg = (
                _pb_encode_varint((1 << 3) | 0)
                + _pb_encode_varint(3)  # SHARED
                + _pb_encode_varint((3 << 3) | 0)
                + _pb_encode_varint(init_ver)
            )
            obj_msg = (
                _pb_encode_bytes_field(2, oid.encode("utf-8"))
                + _pb_encode_varint((3 << 3) | 0)
                + _pb_encode_varint(init_ver)
                + _pb_encode_bytes_field(4, DIGEST_V100.encode("utf-8"))
                + _pb_encode_bytes_field(5, owner_msg)
            )
            return _pb_encode_bytes_field(1, _pb_encode_bytes_field(1, obj_msg))

        payload = (
            _mk_shared_obj(SUI_CLOCK_OBJECT_ID, 1)
            + _mk_shared_obj(CETUS_GLOBAL_CONFIG_ID, 1574190)
            + _mk_shared_obj(SUI_USDC_POOL_ID, 389750321)
        )
        return web.Response(
            body=_grpc_web_frame(payload) + b"\x80\x00\x00\x00\x0fgrpc-status: 0\r\n",
            content_type="application/grpc-web+proto",
        )

    async def handle_simulate(request: web.Request) -> web.Response:
        calls["sim_grpc"] += 1
        await request.read()
        payload = _encode_grpc_executed_tx("SimDigest", True)
        return web.Response(
            body=_grpc_web_frame(payload) + b"\x80\x00\x00\x00\x0fgrpc-status: 0\r\n",
            content_type="application/grpc-web+proto",
        )

    async def handle_execute(request: web.Request) -> web.Response:
        calls["exec_grpc"] += 1
        await request.read()
        new_ver = 100 + calls["exec_grpc"]
        new_dig = DIGEST_V101 if calls["exec_grpc"] == 1 else DIGEST_V102
        payload = _encode_grpc_executed_tx(
            f"OnChainDigest_{calls['exec_grpc']}",
            True,
            gas_object={"address": gas_addr, "version": new_ver, "digest": new_dig},
        )
        return web.Response(
            body=_grpc_web_frame(payload) + b"\x80\x00\x00\x00\x0fgrpc-status: 0\r\n",
            content_type="application/grpc-web+proto",
        )

    async def handle_graphql(request: web.Request) -> web.Response:
        body = await request.json()
        q = body.get("query", "")
        if "GetGasInfo" in q:
            calls["get_gas_gql"] += 1
            return web.json_response(
                {
                    "data": {
                        "epoch": {"referenceGasPrice": "505"},
                        "address": {
                            "objects": {
                                "nodes": [
                                    {"address": gas_addr, "version": 100, "digest": DIGEST_V100}
                                ]
                            }
                        },
                    }
                }
            )
        return web.json_response({"data": {}})

    app = web.Application()
    app.router.add_post("/sui.rpc.v2.LedgerService/BatchGetObjects", handle_batch_get)
    app.router.add_post("/sui.rpc.v2.TransactionExecutionService/SimulateTransaction", handle_simulate)
    app.router.add_post("/sui.rpc.v2.TransactionExecutionService/ExecuteTransaction", handle_execute)
    app.router.add_post("/graphql", handle_graphql)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()
    port = site._server.sockets[0].getsockname()[1]
    base_url = f"http://127.0.0.1:{port}"

    try:
        venue = SuiDeepBookVenue(
            graphql_url=f"{base_url}/graphql",
            rpc_url=base_url,
            active_address=TEST_SENDER,
            private_key=TEST_PRIVATE_KEY,
        )
        try:
            # 1. Warmup loads shared objects via BatchGetObjects and caches gas_coin_ref (v100) + RGP (505)
            warm = await venue.graphql_client.warmup_local_ptb_cache(TEST_SENDER)
            assert warm["reference_gas_price"] == 505
            assert calls["batch_get"] == 1
            assert calls["get_gas_gql"] == 1
            assert venue.local_cache.is_shared_mutable(SUI_CLOCK_OBJECT_ID) is False
            assert venue.local_cache.is_shared_mutable(CETUS_GLOBAL_CONFIG_ID) is False
            assert venue.local_cache.is_shared_mutable(SUI_USDC_POOL_ID) is True

            # 2. First live order uses cached gas_coin (0 extra GetGasInfo calls!) and rolls gas_coin to v101
            order_params = {
                "symbol": "SUI/USDC",
                "side": "BUY",
                "size": 1_000_000_000,
                "size_is_raw": True,
                "price": 2.02,
                "amm_price": 2.00,
                "is_arb_ptb": True,
                "live_onchain": True,
                "expected_net_profit_usd": 6.50,
                "min_profit_usd": 0.035,
            }
            res1 = await venue.submit_order(order_params)
            assert res1.status == "FILLED"
            assert res1.order_id == "OnChainDigest_1"
            assert calls["get_gas_gql"] == 1  # Zero-RTT! No extra GetGasInfo call!
            assert venue.local_cache.gas_coin_ref is not None
            assert venue.local_cache.gas_coin_ref["version"] == 101
            assert venue.local_cache.gas_coin_ref["digest"] == DIGEST_V101

            # 3. Second live order immediately uses rolled-forward v101 gas_coin (still 0 extra GetGasInfo calls!)
            res2 = await venue.submit_order(order_params)
            assert res2.status == "FILLED"
            assert res2.order_id == "OnChainDigest_2"
            assert calls["get_gas_gql"] == 1  # Still 1 total GetGasInfo call from warmup!
            assert venue.local_cache.gas_coin_ref["version"] == 102
            assert venue.local_cache.gas_coin_ref["digest"] == DIGEST_V102
        finally:
            await venue.disconnect()
    finally:
        await runner.cleanup()


@pytest.mark.asyncio
async def test_p0_stale_gas_version_in_simulation_triggers_immediate_refresh_and_retry() -> None:
    """Verifies ObjectVersionUnavailableForConsumption in simulation auto-refreshes gas_coin_ref and retries cleanly."""
    gas_addr = "0x" + "11" * 32
    venue = SuiDeepBookVenue(
        graphql_url="http://127.0.0.1:9/graphql",
        rpc_url="",
        active_address=TEST_SENDER,
        private_key=TEST_PRIVATE_KEY,
    )
    # Seed stale v100 in local_cache
    venue.local_cache.set_gas_and_rgp(
        {"address": gas_addr, "version": 100, "digest": DIGEST_V100},
        rgp=500,
        owner=TEST_SENDER,
    )

    sim_calls = 0

    async def mock_sim(tx_bytes: bytes) -> Dict[str, Any]:
        nonlocal sim_calls
        sim_calls += 1
        if sim_calls == 1:
            return {
                "data": {
                    "simulateTransaction": {
                        "effects": {
                            "status": "FAILURE",
                            "executionError": {
                                "message": "ObjectVersionUnavailableForConsumption: Object version 100 is not available for consumption, current version is 105"
                            },
                        }
                    }
                }
            }
        return {"data": {"simulateTransaction": {"effects": {"status": "SUCCESS"}}}}

    refresh_calls = 0

    async def mock_exec_gql(query: str, variables: Any = None, max_attempts: int = 3) -> Dict[str, Any]:
        nonlocal refresh_calls
        if "GetGasInfo" in query:
            refresh_calls += 1
            return {
                "data": {
                    "epoch": {"referenceGasPrice": "500"},
                    "address": {
                        "objects": {
                            "nodes": [{"address": gas_addr, "version": 105, "digest": DIGEST_V102}]
                        }
                    },
                }
            }
        return {
            "data": {
                "executeTransaction": {
                    "effects": {
                        "digest": "RecoveredTxDigest",
                        "status": "SUCCESS",
                        "gasEffects": {
                            "gasObject": {"address": gas_addr, "version": 106, "digest": DIGEST_V101}
                        },
                    }
                }
            }
        }

    venue.graphql_client.simulate_transaction_bcs = mock_sim  # type: ignore[assignment]
    venue.graphql_client.execute = mock_exec_gql  # type: ignore[assignment]

    res = await venue.submit_order(
        {
            "symbol": "SUI/USDC",
            "side": "BUY",
            "size": 1_000_000_000,
            "size_is_raw": True,
            "price": 2.02,
            "amm_price": 2.00,
            "is_arb_ptb": True,
            "live_onchain": True,
        }
    )
    assert res.status == "FILLED"
    assert res.order_id == "RecoveredTxDigest"
    assert sim_calls == 2
    assert refresh_calls == 1
    assert venue.local_cache.gas_coin_ref is not None
    assert venue.local_cache.gas_coin_ref["version"] == 106


def test_p1_split_horizon_and_multi_provider_auth_headers(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verifies P1 Split-Horizon endpoint separation and Chainstack/Dwellir/OnFinality auth headers."""
    monkeypatch.setenv("SUI_GRPC_ENDPOINT", "https://sui-mainnet.core.chainstack.com:443")
    monkeypatch.setenv("SUI_GRAPHQL_ENDPOINT", "https://graphql.mainnet.sui.io/graphql")
    monkeypatch.setenv("SUI_GRPC_API_KEY", "secret-token-123")
    monkeypatch.setenv("SUI_GRPC_PROVIDER", "chainstack")

    cfg = SuiBotConfig.from_env()
    assert cfg.rpc_url == "https://sui-mainnet.core.chainstack.com:443"
    assert cfg.graphql_url == "https://graphql.mainnet.sui.io/graphql"

    client = SuiGraphQLClient()
    assert client.rpc_endpoint == "https://sui-mainnet.core.chainstack.com:443"
    assert client.endpoint == "https://graphql.mainnet.sui.io/graphql"
    assert client.get_grpc_auth_headers() == {"x-token": "secret-token-123"}

    assert get_grpc_auth_headers("k1", "dwellir") == {"x-api-key": "k1"}
    assert get_grpc_auth_headers("k2", "onfinality") == {"api-key": "k2"}
    assert get_grpc_auth_headers("k3", "custom", "x-custom-auth") == {"x-custom-auth": "k3"}
    assert get_grpc_auth_headers("", "chainstack") == {}


@pytest.mark.asyncio
async def test_p1_grpc_web_endpoint_failover_and_auth_header_injection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verifies _post_grpc_web injects auth headers and fails over across rpc_endpoints."""
    monkeypatch.setenv("SUI_GRPC_API_KEY", "dwellir-key-xyz")
    monkeypatch.setenv("SUI_GRPC_PROVIDER", "dwellir")
    seen_headers: List[Dict[str, str]] = []

    async def handle_fail(request: web.Request) -> web.Response:
        seen_headers.append(dict(request.headers))
        return web.Response(status=503, text="Primary node overloaded")

    async def handle_ok(request: web.Request) -> web.Response:
        seen_headers.append(dict(request.headers))
        payload = _encode_grpc_executed_tx("FailoverDigestOk", True)
        return web.Response(
            body=_grpc_web_frame(payload) + b"\x80\x00\x00\x00\x0fgrpc-status: 0\r\n",
            content_type="application/grpc-web+proto",
        )

    app_fail = web.Application()
    app_fail.router.add_post("/sui.rpc.v2.TransactionExecutionService/SimulateTransaction", handle_fail)
    r1 = web.AppRunner(app_fail)
    await r1.setup()
    s1 = web.TCPSite(r1, "127.0.0.1", 0)
    await s1.start()
    p1 = s1._server.sockets[0].getsockname()[1]

    app_ok = web.Application()
    app_ok.router.add_post("/sui.rpc.v2.TransactionExecutionService/SimulateTransaction", handle_ok)
    r2 = web.AppRunner(app_ok)
    await r2.setup()
    s2 = web.TCPSite(r2, "127.0.0.1", 0)
    await s2.start()
    p2 = s2._server.sockets[0].getsockname()[1]

    try:
        client = SuiGraphQLClient(
            endpoint="http://127.0.0.1:9/graphql",
            rpc_endpoint=f"http://127.0.0.1:{p1},http://127.0.0.1:{p2}",
        )
        try:
            sim_res = await client.simulate_transaction_bcs(b"\x00\x00")
            effects = sim_res["data"]["simulateTransaction"]["effects"]
            assert effects["status"] == "SUCCESS"
            assert len(seen_headers) == 2
            assert seen_headers[0].get("x-api-key") == "dwellir-key-xyz"
            assert seen_headers[1].get("x-api-key") == "dwellir-key-xyz"
        finally:
            await client.close()
    finally:
        await r1.cleanup()
        await r2.cleanup()


def test_p2_compute_priority_gas_price_and_safe_budget() -> None:
    """Verifies SIP-45 priority gas scaling tiers, profit-cap guard, and safe gas budget scaling."""
    base = 500
    # 1. Scaling tiers when net_profit_usd has ample headroom
    assert compute_priority_gas_price(base, None) == 500
    assert compute_priority_gas_price(base, 0.0) == 500
    assert compute_priority_gas_price(base, 0.20, min_profit_usd=0.035) == int(500 * 1.15)
    assert compute_priority_gas_price(base, 1.00, min_profit_usd=0.035) == 1000
    assert compute_priority_gas_price(base, 6.00, min_profit_usd=0.035) == 2500
    assert compute_priority_gas_price(base, 43.07, min_profit_usd=0.035) == 6000

    # 2. Profit guard: if net_profit_usd is barely above min_profit_usd, priority gas is capped
    # Surplus = $0.036 - $0.035 = $0.001 -> at $2/SUI = 500,000 MIST -> / 3000 units = +166 MIST/unit max
    capped = compute_priority_gas_price(
        base_rgp=1000,
        net_profit_usd=0.036,
        min_profit_usd=0.035,
        sui_spot_price=2.0,
        est_computation_units=3_000,
    )
    assert 1000 <= capped <= 1166

    # 3. Safe gas budget scales up when gas_price is high
    assert compute_safe_gas_budget(500, base_gas_budget=50_000_000) == 50_000_000
    high_gp_budget = compute_safe_gas_budget(20_000, base_gas_budget=50_000_000)
    assert high_gp_budget >= 20_000 * 3_000 + 25_000_000


@pytest.mark.asyncio
async def test_observability_logs_distinguish_sim_revert_vs_onchain_revert_and_non_empty_timeout(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Verifies SuiBotRunner logs INFO for PTB-SIM-REVERT vs WARNING for on-chain revert, and non-blank TimeoutError."""
    # 1. Verify _format_exc_detail on empty message exception (e.g. asyncio.TimeoutError())
    detail = _format_exc_detail(asyncio.TimeoutError())
    assert "TimeoutError" in detail
    assert len(detail.strip()) > len("TimeoutError")

    # 2. Verify SuiBotRunner log distinction between PTB-SIM-REVERT and on-chain revert digest
    cfg = SuiBotConfig(
        dry_run_mode=False,
        sui_private_key=TEST_PRIVATE_KEY,
        min_profit_usd=0.01,
    )
    bot = SuiBotRunner(config=cfg)
    bot.update_wallet_balances(sui_balance=3.41, usdc_balance=0.0, deep_balance=118.0)

    profitable_spreads = {
        "SUI/USDC": {
            "cetus_price": 2.00,
            "deepbook_price": 2.04,
            "deepbook_ask": 2.04,
            "spread_bps": 200.0,
            "forward_spread_bps": 200.0,
            "reverse_spread_bps": -200.0,
            "best_route": "FORWARD",
            "optimal_spread_bps": 200.0,
            "bid_depth_quote": 50_000.0,
            "ask_depth_quote": 50_000.0,
            "cetus_liquidity": 1e16,
            "cetus_sqrt_price": 1 << 64,
            "source": "fallback",
        }
    }
    for p in ("DEEP/SUI", "DEEP/USDC", "CETUS/SUI", "USDSUI/USDC", "WAL/USDC", "LZWBTC/USDC", "NS/SUI", "XBTC/USDC", "NS/USDC"):
        profitable_spreads[p] = {
            "cetus_price": 1.0,
            "deepbook_price": 1.0,
            "deepbook_ask": 1.0,
            "spread_bps": 0.0,
            "forward_spread_bps": 0.0,
            "reverse_spread_bps": 0.0,
            "best_route": "FORWARD",
            "optimal_spread_bps": 0.0,
            "source": "fallback",
        }

    from venues.base import OrderExecutionResult

    bot.poll_market_spreads = AsyncMock(return_value=profitable_spreads)  # type: ignore[method-assign]

    # Case A: Pre-flight simulation rejection (PTB-SIM-REVERT-*) -> INFO log, 0 aborts
    bot.validator.venue.submit_order = AsyncMock(  # type: ignore[method-assign]
        return_value=OrderExecutionResult(
            venue="sui_deepbook",
            order_id="PTB-SIM-REVERT-deadbeef",
            symbol="SUI/USDC",
            side="BUY",
            price=2.04,
            size=1000.0,
            fee_bps=0.0,
            rebate_bps=0.0,
            is_maker=False,
            status="REJECTED",
            latency_ms=12.0,
            timestamp_ns=1,
        )
    )
    with caplog.at_level(logging.INFO):
        await bot.scan_once()
    assert "Live PTB pre-flight simulation rejected for SUI/USDC (0 gas cost): order_id=PTB-SIM-REVERT-deadbeef" in caplog.text
    assert bot.scaling_engine.state.consecutive_aborts == 0

    caplog.clear()
    # Case B: On-chain revert with real tx digest -> WARNING log, increments consecutive_aborts
    bot.validator.venue.submit_order = AsyncMock(  # type: ignore[method-assign]
        return_value=OrderExecutionResult(
            venue="sui_deepbook",
            order_id="DBduvm6k8UVQi6MvATFoZYzShrySQX6MbuvGK5KjatxQ",
            symbol="SUI/USDC",
            side="BUY",
            price=2.04,
            size=1000.0,
            fee_bps=0.0,
            rebate_bps=0.0,
            is_maker=False,
            status="REJECTED",
            latency_ms=650.0,
            timestamp_ns=2,
        )
    )
    with caplog.at_level(logging.INFO):
        await bot.scan_once()
    assert (
        "On-chain PTB reverted atomically on SUI/USDC (principal safe, ~0.0001 SUI gas spent): "
        "tx_digest=DBduvm6k8UVQi6MvATFoZYzShrySQX6MbuvGK5KjatxQ"
    ) in caplog.text
    assert bot.scaling_engine.state.consecutive_aborts == 1


@pytest.mark.asyncio
async def test_p0_ambiguous_timeout_reconciles_via_get_transaction_and_tx_lock_serializes() -> None:
    """Verifies GetTransaction reconciliation on ambiguous broadcast failure and asyncio.Lock serialization."""
    gas_addr = "0x" + "11" * 32
    venue = SuiDeepBookVenue(
        graphql_url="http://127.0.0.1:9/graphql",
        rpc_url="http://127.0.0.1:9",
        active_address=TEST_SENDER,
        private_key=TEST_PRIVATE_KEY,
    )
    venue.local_cache.set_gas_and_rgp(
        {"address": gas_addr, "version": 200, "digest": DIGEST_V100},
        rgp=505,
        owner=TEST_SENDER,
    )

    venue.graphql_client.simulate_transaction_bcs = AsyncMock(  # type: ignore[method-assign]
        return_value={"data": {"simulateTransaction": {"effects": {"status": "SUCCESS"}}}}
    )
    venue.graphql_client.execute_transaction_bcs = AsyncMock(  # type: ignore[method-assign]
        side_effect=asyncio.TimeoutError()
    )

    reconciled_digests: List[str] = []

    async def mock_get_tx(digest: str, timeout_s: float = 5.0) -> Dict[str, Any]:
        reconciled_digests.append(digest)
        eff = {
            "status": "SUCCESS",
            "digest": digest,
            "gasObject": {"address": gas_addr, "version": 201, "digest": DIGEST_V101},
        }
        venue.local_cache.roll_forward_from_effects(eff)
        return {"effects": eff}

    venue.graphql_client.get_transaction_grpc = mock_get_tx  # type: ignore[method-assign]

    res = await venue.submit_order(
        {
            "symbol": "SUI/USDC",
            "side": "BUY",
            "size": 1_000_000_000,
            "size_is_raw": True,
            "price": 2.02,
            "amm_price": 2.00,
            "is_arb_ptb": True,
            "live_onchain": True,
        }
    )
    assert res.status == "REJECTED"
    assert len(reconciled_digests) == 1
    assert venue.local_cache.gas_coin_ref == {
        "address": gas_addr,
        "version": 201,
        "digest": DIGEST_V101,
    }

