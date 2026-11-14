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
    effects_payload = (
        _pb_encode_bytes_field(4, status_payload)
        + _pb_encode_bytes_field(6, gas_payload)
        + _pb_encode_bytes_field(7, digest.encode("utf-8"))
    )
    if gas_object:
        effects_payload += _pb_encode_bytes_field(
            8,
            _encode_grpc_changed_object(
                gas_object["address"], int(gas_object["version"]), gas_object["digest"]
            ),
        )
    if changed_objects:
        for ch in changed_objects:
            effects_payload += _pb_encode_bytes_field(
                12,
                _encode_grpc_changed_object(ch["address"], int(ch["version"]), ch["digest"]),
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


@pytest.mark.asyncio
async def test_p0_grpc_status_3_stale_gas_and_deep_coin_refresh_without_graphql_crash() -> None:
    """Verifies gRPC status 3 (unavailable for consumption) and GraphQL data=None errors refresh gas+deep coins and retry cleanly."""
    gas_addr = "0x" + "11" * 32
    deep_addr = "0x" + "dd" * 32
    calls = {"sim_grpc": 0, "exec_grpc": 0, "gql_gas": 0, "gql_deep": 0, "gql_sim": 0}

    async def handle_simulate(request: web.Request) -> web.Response:
        calls["sim_grpc"] += 1
        raw_req = await request.read()
        if calls["sim_grpc"] == 1:
            # Real Sui Mainnet returns grpc-status: 3 when input object version is stale
            msg = (
                f"Error checking transaction input objects: Transaction needs to be rebuilt because "
                f"object {gas_addr} version 0x64 ({DIGEST_V100}) is unavailable for consumption, current version: 0x69"
            )
            return web.Response(
                body=f"\x80\x00\x00\x00\x00grpc-status: 3\r\ngrpc-message: {msg}\r\n".encode("utf-8"),
                headers={"grpc-status": "3", "grpc-message": msg},
                content_type="application/grpc-web+proto",
            )
        # Verify the retry PTB contains both refreshed gas_coin (v105, DIGEST_V101) and refreshed deep_coin (v61, DIGEST_V102)
        from venues.sui_deepbook_venue import bcs_input_owned

        assert bcs_input_owned(deep_addr, 61, DIGEST_V102) in raw_req
        payload = _encode_grpc_executed_tx("SimDigestRetryOk", True)
        return web.Response(
            body=_grpc_web_frame(payload) + b"\x80\x00\x00\x00\x0fgrpc-status: 0\r\n",
            content_type="application/grpc-web+proto",
        )

    async def handle_execute(request: web.Request) -> web.Response:
        calls["exec_grpc"] += 1
        await request.read()
        payload = _encode_grpc_executed_tx(
            "OnChainRecoveredTx",
            True,
            gas_object={"address": gas_addr, "version": 106, "digest": DIGEST_V102},
        )
        return web.Response(
            body=_grpc_web_frame(payload) + b"\x80\x00\x00\x00\x0fgrpc-status: 0\r\n",
            content_type="application/grpc-web+proto",
        )

    async def handle_graphql(request: web.Request) -> web.Response:
        body = await request.json()
        q = body.get("query", "")
        if "GetGasInfo" in q:
            calls["gql_gas"] += 1
            return web.json_response(
                {
                    "data": {
                        "epoch": {"referenceGasPrice": "505"},
                        "address": {
                            "objects": {
                                "nodes": [
                                    {"address": gas_addr, "version": 105, "digest": DIGEST_V101}
                                ]
                            }
                        },
                    }
                }
            )
        if "GetDeepCoins" in q:
            calls["gql_deep"] += 1
            return web.json_response(
                {
                    "data": {
                        "address": {
                            "objects": {
                                "nodes": [
                                    {
                                        "address": deep_addr,
                                        "version": 61,
                                        "digest": DIGEST_V102,
                                        "contents": {"json": {"balance": "50000000"}},
                                    }
                                ]
                            }
                        }
                    }
                }
            )
        if "SimPTB" in q:
            calls["gql_sim"] += 1
        return web.json_response({"data": None, "errors": [{"message": "unavailable for consumption"}]})

    app = web.Application()
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
            # Seed stale gas_coin (v100) and stale deep_coin (v60)
            venue.local_cache.set_gas_and_rgp(
                {"address": gas_addr, "version": 100, "digest": DIGEST_V100},
                rgp=505,
                owner=TEST_SENDER,
            )
            stale_deep = {"address": deep_addr, "version": 60, "digest": DIGEST_V100, "balance": 50_000_000}
            venue.local_cache.set_deep_coin(stale_deep)

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
                    "deep_coin": stale_deep,
                    "deep_fee_amount": 500_000,
                }
            )
            assert res.status == "FILLED"
            assert res.order_id == "OnChainRecoveredTx"
            assert calls["sim_grpc"] == 2
            assert calls["gql_sim"] == 0  # Did NOT waste time falling back to GraphQL on gRPC status 3!
            assert calls["gql_gas"] == 1
            assert calls["gql_deep"] == 1
            assert venue.local_cache.gas_coin_ref["version"] == 106
            assert venue.local_cache.deep_coin_ref["version"] == 61
        finally:
            await venue.disconnect()
    finally:
        await runner.cleanup()


def test_p0_decode_grpc_executed_tx_field_12_changed_objects_and_no_corrupt_gas_fallback() -> None:
    """Verifies field 12 changed_objects decoding and ensures gasObject is never corrupted with changed_objects[0]."""
    from venues.sui_deepbook_venue import _pb_decode_fields

    pool_addr = SUI_USDC_POOL_ID
    deep_addr = "0x" + "dd" * 32
    gas_addr = "0x" + "aa" * 32

    # Build a TransactionEffects payload where field 8 (gas_object) is omitted and changed_objects[0] is a pool!
    raw = _encode_grpc_executed_tx(
        digest="9eXQRYHDzeEW8wAAhEEG8pwTdRQqB4pAi2rtw8bk1YkW",
        success=True,
        gas_object=None,
        changed_objects=[
            {"address": pool_addr, "version": 500, "digest": DIGEST_V100},
            {"address": deep_addr, "version": 61, "digest": DIGEST_V101},
            {"address": gas_addr, "version": 102, "digest": DIGEST_V102},
        ],
    )
    parsed = _decode_grpc_executed_tx(_pb_decode_fields(raw)[1][0])
    assert "gasObject" not in parsed  # Must NOT blindly pick changed_objects[0] (pool_addr)!
    assert len(parsed["changedObjects"]) == 3

    cache = SuiLocalPTBCache()
    cache.set_gas_and_rgp({"address": gas_addr, "version": 101, "digest": DIGEST_V100}, rgp=100, owner=TEST_SENDER)
    cache.set_deep_coin({"address": deep_addr, "version": 60, "digest": DIGEST_V100, "balance": 10_000_000})

    norm = SuiGraphQLClient._normalize_effects_payload(
        success=True,
        digest=parsed["digest"],
        changed_objects=parsed["changedObjects"],
    )
    rolled = cache.roll_forward_from_effects(norm["effects"])
    assert rolled is True
    # gas_coin_ref matched gas_addr (index 2), NOT pool_addr (index 0)!
    assert cache.gas_coin_ref == {"address": gas_addr, "version": 102, "digest": DIGEST_V102}
    assert cache.deep_coin_ref["version"] == 61
    assert cache.deep_coin_ref["digest"] == DIGEST_V101


@pytest.mark.asyncio
async def test_p0_submit_order_prefers_newer_cached_deep_coin_and_validator_shares_cache() -> None:
    """Verifies submit_order uses higher-version local_cache.deep_coin_ref over stale order_params['deep_coin']."""
    from venues.sui_ptb_validator import SuiPTBPreflightValidator
    from venues.sui_deepbook_venue import bcs_input_owned

    validator = SuiPTBPreflightValidator(graphql_url="http://127.0.0.1:9/graphql", rpc_url="")
    assert validator.venue.local_cache is validator.graphql_client.local_cache

    gas_addr = "0x" + "11" * 32
    deep_addr = "0x" + "dd" * 32
    venue = validator.venue
    venue.private_key = TEST_PRIVATE_KEY

    venue.local_cache.set_gas_and_rgp(
        {"address": gas_addr, "version": 100, "digest": DIGEST_V100},
        rgp=500,
        owner=venue.active_address,
    )
    # local_cache has rolled-forward deep_coin version 55 (DIGEST_V102), while caller passes stale version 50 (DIGEST_V100)
    venue.local_cache.set_deep_coin(
        {"address": deep_addr, "version": 55, "digest": DIGEST_V102, "balance": 20_000_000}
    )

    captured_tx_bytes: List[bytes] = []

    async def mock_sim(tx_bytes: bytes) -> Dict[str, Any]:
        captured_tx_bytes.append(tx_bytes)
        return {"data": {"simulateTransaction": {"effects": {"status": "FAILURE"}}}}

    venue.graphql_client.simulate_transaction_bcs = mock_sim  # type: ignore[assignment]

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
            "deep_coin": {"address": deep_addr, "version": 50, "digest": DIGEST_V100, "balance": 20_000_000},
            "deep_fee_amount": 500_000,
        }
    )
    assert res.status == "REJECTED"
    assert len(captured_tx_bytes) == 1
    assert bcs_input_owned(deep_addr, 55, DIGEST_V102) in captured_tx_bytes[0]
    assert bcs_input_owned(deep_addr, 50, DIGEST_V100) not in captured_tx_bytes[0]


@pytest.mark.asyncio
async def test_p0_execute_transaction_bcs_reconciles_via_get_transaction_when_graphql_fallback_fails() -> None:
    """Verifies execute_transaction_bcs reconciles via GetTransaction if gRPC times out after tx landed and GraphQL fails."""
    gas_addr = "0x" + "11" * 32
    client = SuiGraphQLClient(endpoint="http://127.0.0.1:9/graphql", rpc_endpoint="http://127.0.0.1:9")
    client._post_grpc_web = AsyncMock(side_effect=asyncio.TimeoutError())  # type: ignore[method-assign]
    client.execute = AsyncMock(side_effect=RuntimeError("GraphQL Errors: Object already consumed"))  # type: ignore[method-assign]

    expected_tx_bytes = b"sample_signed_tx_data"
    expected_digest = compute_tx_digest(expected_tx_bytes)

    async def mock_get_tx(digest: str, timeout_s: float = 5.0) -> Dict[str, Any]:
        assert digest == expected_digest
        norm = client._normalize_effects_payload(
            success=True,
            digest=digest,
            gas_object={"address": gas_addr, "version": 301, "digest": DIGEST_V101},
        )
        client.local_cache.roll_forward_from_effects(norm["effects"])
        return norm

    client.get_transaction_grpc = mock_get_tx  # type: ignore[method-assign]
    res = await client.execute_transaction_bcs(expected_tx_bytes, [base64.b64encode(b"sig").decode("utf-8")])
    eff = res["data"]["executeTransaction"]["effects"]
    assert eff["status"] == "SUCCESS"
    assert eff["digest"] == expected_digest
    assert client.local_cache.gas_coin_ref == {"address": gas_addr, "version": 301, "digest": DIGEST_V101}


def test_p1_normalize_url_and_per_endpoint_provider_discovery_and_auth(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verifies bare host:443 URL normalization, provider endpoint discovery, and per-endpoint auth headers."""
    from venues.sui_deepbook_venue import (
        classify_grpc_provider,
        discover_configured_grpc_endpoints,
        get_grpc_auth_headers_for_endpoint,
        normalize_grpc_endpoint_url,
    )

    assert normalize_grpc_endpoint_url("sui-mainnet.core.chainstack.com:443") == (
        "https://sui-mainnet.core.chainstack.com:443"
    )
    assert normalize_grpc_endpoint_url("api-sui-mainnet-full.n.dwellir.com:443") == (
        "https://api-sui-mainnet-full.n.dwellir.com:443"
    )
    assert normalize_grpc_endpoint_url("sui.api.onfinality.io:443") == (
        "https://sui.api.onfinality.io:443"
    )
    assert normalize_grpc_endpoint_url("127.0.0.1:9000/") == "http://127.0.0.1:9000"
    assert normalize_grpc_endpoint_url("localhost:9000") == "http://localhost:9000"
    assert normalize_grpc_endpoint_url("") == ""

    monkeypatch.setenv("SUI_CHAINSTACK_GRPC_URL", "sui-mainnet.core.chainstack.com:443")
    monkeypatch.setenv("SUI_CHAINSTACK_GRPC_API_KEY", "cs-secret-token")
    monkeypatch.setenv("SUI_DWELLIR_GRPC_URL", "api-sui-mainnet-full.n.dwellir.com:443")
    monkeypatch.setenv("SUI_DWELLIR_GRPC_API_KEY", "dw-secret-key")
    monkeypatch.setenv("SUI_ONFINALITY_GRPC_URL", "sui.api.onfinality.io:443")
    monkeypatch.setenv("SUI_ONFINALITY_GRPC_API_KEY", "of-secret-key")

    discovered = discover_configured_grpc_endpoints()
    assert discovered == [
        "https://sui-mainnet.core.chainstack.com:443",
        "https://api-sui-mainnet-full.n.dwellir.com:443",
        "https://sui.api.onfinality.io:443",
    ]

    assert classify_grpc_provider("sui-mainnet.core.chainstack.com:443") == "chainstack"
    assert classify_grpc_provider("api-sui-mainnet-full.n.dwellir.com:443") == "dwellir"
    assert classify_grpc_provider("sui.api.onfinality.io:443") == "onfinality"
    assert classify_grpc_provider("https://fullnode.mainnet.sui.io:443") == "sui_foundation"

    assert get_grpc_auth_headers_for_endpoint("https://sui-mainnet.core.chainstack.com:443") == {
        "x-token": "cs-secret-token"
    }
    assert get_grpc_auth_headers_for_endpoint("https://api-sui-mainnet-full.n.dwellir.com:443") == {
        "x-api-key": "dw-secret-key"
    }
    assert get_grpc_auth_headers_for_endpoint("https://sui.api.onfinality.io:443") == {
        "x-api-key": "of-secret-key",
        "apikey": "of-secret-key",
        "api-key": "of-secret-key",
    }
    assert get_grpc_auth_headers_for_endpoint("https://fullnode.mainnet.sui.io:443") == {}


@pytest.mark.asyncio
async def test_p1_per_endpoint_auth_switching_and_h2_transport_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verifies _post_grpc_web resolves per-endpoint headers during failover and upgrades to HTTP/2 on HTTP 426."""
    monkeypatch.setenv("SUI_CHAINSTACK_GRPC_URL", "http://127.0.0.1:19001")
    monkeypatch.setenv("SUI_CHAINSTACK_GRPC_API_KEY", "cs-token-111")
    monkeypatch.setenv("SUI_DWELLIR_GRPC_URL", "http://127.0.0.1:19002")
    monkeypatch.setenv("SUI_DWELLIR_GRPC_API_KEY", "dw-key-222")

    seen_requests: List[Tuple[str, Dict[str, str]]] = []

    async def handle_cs_503(request: web.Request) -> web.Response:
        seen_requests.append(("cs", dict(request.headers)))
        return web.Response(status=503, text="Chainstack maintenance")

    async def handle_dw_426(request: web.Request) -> web.Response:
        seen_requests.append(("dw_h1", dict(request.headers)))
        return web.Response(status=426, text="Please use HTTP2 protocol")

    app1 = web.Application()
    app1.router.add_post("/sui.rpc.v2.TransactionExecutionService/SimulateTransaction", handle_cs_503)
    r1 = web.AppRunner(app1)
    await r1.setup()
    s1 = web.TCPSite(r1, "127.0.0.1", 0)
    await s1.start()
    p1 = s1._server.sockets[0].getsockname()[1]

    app2 = web.Application()
    app2.router.add_post("/sui.rpc.v2.TransactionExecutionService/SimulateTransaction", handle_dw_426)
    r2 = web.AppRunner(app2)
    await r2.setup()
    s2 = web.TCPSite(r2, "127.0.0.1", 0)
    await s2.start()
    p2 = s2._server.sockets[0].getsockname()[1]

    cs_ep = f"http://127.0.0.1:{p1}"
    dw_ep = f"http://127.0.0.1:{p2}"
    monkeypatch.setenv("SUI_CHAINSTACK_GRPC_URL", cs_ep)
    monkeypatch.setenv("SUI_DWELLIR_GRPC_URL", dw_ep)

    try:
        client = SuiGraphQLClient(
            endpoint="http://127.0.0.1:9/graphql",
            rpc_endpoint=f"{cs_ep},{dw_ep}",
        )
        try:
            h2_calls: List[Tuple[str, Dict[str, str]]] = []

            async def mock_post_h2(
                url: str,
                framed_payload: bytes,
                auth_headers: Dict[str, str],
                timeout_s: float = 8.0,
                service_path: str = "",
            ) -> bytes:
                h2_calls.append((url, dict(auth_headers)))
                return _encode_grpc_executed_tx("H2UpgradeOkDigest", True)

            client._post_grpc_h2 = mock_post_h2  # type: ignore[method-assign]
            sim_res = await client.simulate_transaction_bcs(b"\x00\x00")
            eff = sim_res["data"]["simulateTransaction"]["effects"]
            assert eff["status"] == "SUCCESS"

            # First endpoint received Chainstack's x-token (and NOT Dwellir's x-api-key)
            assert seen_requests[0][0] == "cs"
            assert seen_requests[0][1].get("x-token") == "cs-token-111"
            assert "x-api-key" not in seen_requests[0][1]

            # Second endpoint received Dwellir's x-api-key (and NOT Chainstack's x-token)
            assert seen_requests[1][0] == "dw_h1"
            assert seen_requests[1][1].get("x-api-key") == "dw-key-222"
            assert "x-token" not in seen_requests[1][1]

            # HTTP 426 triggered _post_grpc_h2 with Dwellir's auth headers
            assert len(h2_calls) == 1
            assert h2_calls[0][1] == {"x-api-key": "dw-key-222"}
        finally:
            await client.close()
    finally:
        await r1.cleanup()
        await r2.cleanup()


@pytest.mark.asyncio
async def test_p1_benchmark_grpc_endpoints_reorders_by_lowest_warm_latency() -> None:
    """Verifies benchmark_grpc_endpoints probes all endpoints and promotes the lowest-RTT healthy node."""
    from venues.sui_deepbook_venue import _pb_encode_bytes_field, _pb_encode_varint

    service_info_bytes = (
        _pb_encode_bytes_field(1, b"35834a8a")
        + _pb_encode_bytes_field(2, b"mainnet")
        + (_pb_encode_varint((3 << 3) | 0) + _pb_encode_varint(1140))
        + (_pb_encode_varint((4 << 3) | 0) + _pb_encode_varint(262_800_000))
        + _pb_encode_bytes_field(8, b"1.69.1-fast")
    )

    client = SuiGraphQLClient(
        endpoint="http://127.0.0.1:9/graphql",
        rpc_endpoint="https://sui-mainnet.core.chainstack.com:443,https://api-sui-mainnet-full.n.dwellir.com:443,https://sui.api.onfinality.io:443",
    )
    try:
        simulated_delays = {
            "https://sui-mainnet.core.chainstack.com:443": 0.035,
            "https://api-sui-mainnet-full.n.dwellir.com:443": 0.004,
            "https://sui.api.onfinality.io:443": 0.015,
        }

        async def mock_post(
            service_path: str,
            req_bytes: bytes,
            timeout_s: float = 8.0,
            target_endpoints: Optional[List[str]] = None,
        ) -> bytes:
            assert service_path == "/sui.rpc.v2.LedgerService/GetServiceInfo"
            ep = target_endpoints[0] if target_endpoints else ""
            await asyncio.sleep(simulated_delays.get(ep, 0.02))
            return service_info_bytes

        client._post_grpc_web = mock_post  # type: ignore[method-assign]
        results = await client.benchmark_grpc_endpoints(samples=2)
        assert len(results) == 3
        assert results[0]["provider"] == "dwellir"
        assert results[0]["ok"] is True
        assert results[0]["checkpoint_height"] == 262_800_000
        assert client.rpc_endpoint == "https://api-sui-mainnet-full.n.dwellir.com:443"
        assert client.rpc_endpoints == [
            "https://api-sui-mainnet-full.n.dwellir.com:443",
            "https://sui.api.onfinality.io:443",
            "https://sui-mainnet.core.chainstack.com:443",
        ]
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_live_multi_provider_grpc_benchmark_mainnet() -> None:
    """Live integration benchmark across configured Chainstack, Dwellir, OnFinality, and Sui Foundation gRPC nodes."""
    import os

    if not (
        os.getenv("SUI_CHAINSTACK_GRPC_API_KEY")
        and os.getenv("SUI_DWELLIR_GRPC_API_KEY")
        and os.getenv("SUI_ONFINALITY_GRPC_API_KEY")
    ):
        pytest.skip("Dedicated Sui gRPC provider API keys not present in environment")

    client = SuiGraphQLClient()
    try:
        assert len(client.rpc_endpoints) >= 4
        results = await client.benchmark_grpc_endpoints(samples=2)
        ok_results = [r for r in results if r.get("ok")]
        assert len(ok_results) >= 3
        for r in ok_results:
            assert r["chain"] == "mainnet"
            assert int(r["checkpoint_height"]) > 200_000_000
            assert float(r["warm_ms"]) > 0.0
        # Ensure rpc_endpoint was updated to the fastest healthy provider
        assert client.rpc_endpoint == ok_results[0]["endpoint"]
    finally:
        await client.close()



