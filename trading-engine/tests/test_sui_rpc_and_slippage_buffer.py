"""Tests for low-latency Sui gRPC-Web / JSON-RPC execution & dynamic 2-3 bps slippage buffer."""

from __future__ import annotations

import json
import logging
import socket
import struct
import sys
from pathlib import Path
from typing import Any, Dict, Tuple
from unittest.mock import AsyncMock, patch

import pytest
from aiohttp import web

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from venues.sui_bot_runner import SuiBotConfig, SuiBotRunner  # noqa: E402
from venues.sui_deepbook_venue import (  # noqa: E402
    SUI_GRAPHQL_MAINNET,
    SUI_GRPC_MAINNET,
    SuiGraphQLClient,
    _pb_encode_bytes_field,
    _pb_encode_varint,
)


def _encode_grpc_executed_tx(
    *,
    digest: str,
    success: bool,
    error_desc: str = "",
    comp_cost: int = 100_000,
    storage_cost: int = 2_000_000,
    storage_rebate: int = 1_900_000,
) -> bytes:
    """Builds a minimal protobuf wire payload for sui.rpc.v2.ExecutedTransaction."""
    status_bytes = _pb_encode_varint((1 << 3) | 0) + _pb_encode_varint(1 if success else 0)
    if not success and error_desc:
        err_msg = _pb_encode_bytes_field(1, error_desc.encode("utf-8"))
        status_bytes += _pb_encode_bytes_field(2, err_msg)

    gas_bytes = (
        _pb_encode_varint((1 << 3) | 0) + _pb_encode_varint(comp_cost)
        + _pb_encode_varint((2 << 3) | 0) + _pb_encode_varint(storage_cost)
        + _pb_encode_varint((3 << 3) | 0) + _pb_encode_varint(storage_rebate)
    )
    eff_bytes = _pb_encode_bytes_field(4, status_bytes) + _pb_encode_bytes_field(6, gas_bytes)
    etx_bytes = _pb_encode_bytes_field(1, digest.encode("utf-8")) + _pb_encode_bytes_field(4, eff_bytes)
    return _pb_encode_bytes_field(1, etx_bytes)  # ExecuteTransactionResponse / SimulateTransactionResponse


def _pack_grpc_web_body(msg: bytes, grpc_status: str = "0") -> bytes:
    trailer = f"grpc-status:{grpc_status}\r\n".encode("utf-8")
    return (
        b"\x00" + struct.pack(">I", len(msg)) + msg
        + b"\x80" + struct.pack(">I", len(trailer)) + trailer
    )


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


@pytest.mark.asyncio
async def test_grpc_web_execute_transaction_success_and_onchain_failure_no_graphql_fallback() -> None:
    """Verifies low-latency gRPC-Web ExecuteTransaction handles SUCCESS and finalized FAILURE without GraphQL fallback."""
    port = _free_port()
    state: Dict[str, Any] = {"mode": "success", "exec_calls": 0, "gql_calls": 0}

    async def handle_grpc_exec(request: web.Request) -> web.Response:
        state["exec_calls"] += 1
        assert request.headers.get("Content-Type") == "application/grpc-web+proto"
        _ = await request.read()
        if state["mode"] == "success":
            payload = _encode_grpc_executed_tx(digest="GRPC-EXEC-OK-1", success=True)
        else:
            payload = _encode_grpc_executed_tx(
                digest="GRPC-EXEC-FAIL-1",
                success=False,
                error_desc="InsufficientCoinBalance in command 10",
            )
        return web.Response(
            body=_pack_grpc_web_body(payload),
            headers={"Content-Type": "application/grpc-web+proto"},
        )

    async def handle_graphql(request: web.Request) -> web.Response:
        state["gql_calls"] += 1
        return web.json_response({"data": {}})

    app = web.Application()
    app.router.add_post("/sui.rpc.v2.TransactionExecutionService/ExecuteTransaction", handle_grpc_exec)
    app.router.add_post("/graphql", handle_graphql)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", port)
    await site.start()

    sig_b64 = "A" * 128  # valid base64 dummy bytes
    client = SuiGraphQLClient(
        endpoint=f"http://127.0.0.1:{port}/graphql",
        rpc_endpoint=f"http://127.0.0.1:{port}",
    )
    try:
        res_ok = await client.execute_transaction_bcs(b"\x00\x01\x02", [sig_b64])
        eff_ok = res_ok["data"]["executeTransaction"]["effects"]
        assert eff_ok["status"] == "SUCCESS"
        assert eff_ok["digest"] == "GRPC-EXEC-OK-1"
        assert eff_ok["gasEffects"]["gasSummary"]["computationCost"] == 100_000
        assert state["gql_calls"] == 0

        state["mode"] = "failure"
        res_fail = await client.execute_transaction_bcs(b"\x00\x01\x02", [sig_b64])
        eff_fail = res_fail["data"]["executeTransaction"]["effects"]
        assert eff_fail["status"] == "FAILURE"
        assert eff_fail["digest"] == "GRPC-EXEC-FAIL-1"
        assert "InsufficientCoinBalance" in eff_fail["executionError"]["message"]
        # Finalized on-chain failure MUST NOT retry or hit GraphQL
        assert state["gql_calls"] == 0
        assert state["exec_calls"] == 2
    finally:
        await client.close()
        await runner.cleanup()


@pytest.mark.asyncio
async def test_grpc_web_simulate_and_transport_fallback_to_graphql() -> None:
    """Verifies SimulateTransaction via gRPC-Web and single-shot GraphQL fallback when RPC errors."""
    port = _free_port()
    state: Dict[str, Any] = {"rpc_fail": False, "gql_sim": 0, "gql_exec": 0}

    async def handle_grpc_sim(request: web.Request) -> web.Response:
        if state["rpc_fail"]:
            return web.Response(status=503, text="Service Unavailable")
        payload = _encode_grpc_executed_tx(digest="SIM-DIGEST", success=True)
        return web.Response(
            body=_pack_grpc_web_body(payload),
            headers={"Content-Type": "application/grpc-web+proto"},
        )

    async def handle_grpc_exec(request: web.Request) -> web.Response:
        return web.Response(status=503, text="Service Unavailable")

    async def handle_graphql(request: web.Request) -> web.Response:
        body = await request.json()
        q = body.get("query", "")
        if "simulateTransaction" in q:
            state["gql_sim"] += 1
            return web.json_response({"data": {"simulateTransaction": {"effects": {"status": "SUCCESS"}}}})
        state["gql_exec"] += 1
        return web.json_response(
            {"data": {"executeTransaction": {"effects": {"digest": "GQL-FALLBACK-DIGEST", "status": "SUCCESS"}}}}
        )

    app = web.Application()
    app.router.add_post("/sui.rpc.v2.TransactionExecutionService/SimulateTransaction", handle_grpc_sim)
    app.router.add_post("/sui.rpc.v2.TransactionExecutionService/ExecuteTransaction", handle_grpc_exec)
    app.router.add_post("/graphql", handle_graphql)

    runner = web.AppRunner(app)
    await runner.setup()
    await web.TCPSite(runner, "127.0.0.1", port).start()

    client = SuiGraphQLClient(
        endpoint=f"http://127.0.0.1:{port}/graphql",
        rpc_endpoint=f"http://127.0.0.1:{port}",
    )
    try:
        # 1. Primary gRPC-Web simulation works without touching GraphQL
        sim_ok = await client.simulate_transaction_bcs(b"\x01\x02")
        assert sim_ok["data"]["simulateTransaction"]["effects"]["status"] == "SUCCESS"
        assert state["gql_sim"] == 0

        # 2. When RPC returns 503, simulation and execution fall back cleanly to GraphQL
        state["rpc_fail"] = True
        sim_fb = await client.simulate_transaction_bcs(b"\x01\x02")
        assert sim_fb["data"]["simulateTransaction"]["effects"]["status"] == "SUCCESS"
        assert state["gql_sim"] == 1

        exec_fb = await client.execute_transaction_bcs(b"\x01\x02", ["AAAA"])
        assert exec_fb["data"]["executeTransaction"]["effects"]["digest"] == "GQL-FALLBACK-DIGEST"
        assert state["gql_exec"] == 1
    finally:
        await client.close()
        await runner.cleanup()


@pytest.mark.asyncio
async def test_custom_json_rpc_wait_for_effects_cert(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verifies JSON-RPC sui_executeTransactionBlock WaitForEffectsCert mode works for custom gateways."""
    port = _free_port()
    captured: Dict[str, Any] = {}

    async def handle_json_rpc(request: web.Request) -> web.Response:
        body = await request.json()
        captured["method"] = body["method"]
        captured["params"] = body["params"]
        return web.json_response(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "result": {
                    "digest": "JSONRPC-DIGEST-777",
                    "effects": {
                        "status": {"status": "success"},
                        "gasUsed": {"computationCost": "120000", "storageCost": "500000", "storageRebate": "490000"},
                    },
                },
            }
        )

    app = web.Application()
    app.router.add_post("/", handle_json_rpc)
    runner = web.AppRunner(app)
    await runner.setup()
    await web.TCPSite(runner, "127.0.0.1", port).start()

    monkeypatch.setenv("SUI_RPC_PROTOCOL", "jsonrpc")
    client = SuiGraphQLClient(
        endpoint=f"http://127.0.0.1:{port}/graphql",
        rpc_endpoint=f"http://127.0.0.1:{port}/",
    )
    try:
        res = await client.execute_transaction_bcs(b"\x01\x02\x03", ["SIG1"])
        eff = res["data"]["executeTransaction"]["effects"]
        assert eff["status"] == "SUCCESS"
        assert eff["digest"] == "JSONRPC-DIGEST-777"
        assert captured["method"] == "sui_executeTransactionBlock"
        assert captured["params"][3] == "WaitForEffectsCert"
    finally:
        await client.close()
        await runner.cleanup()


def test_config_and_dynamic_slippage_buffer_bounds(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verifies SuiBotConfig parses SLIPPAGE_SAFETY_BUFFER_BPS & rpc_url, and buffer stays within 2.5-3.0 bps."""
    monkeypatch.delenv("SLIPPAGE_SAFETY_BUFFER_BPS", raising=False)
    monkeypatch.delenv("SUI_SLIPPAGE_BUFFER_BPS", raising=False)
    monkeypatch.delenv("SUI_RPC_URL", raising=False)
    monkeypatch.delenv("SUI_GRPC_URL", raising=False)

    cfg = SuiBotConfig.from_env()
    assert cfg.graphql_url == SUI_GRAPHQL_MAINNET
    assert cfg.rpc_url == SUI_GRPC_MAINNET
    assert cfg.slippage_safety_buffer_bps == 2.0

    # Buffer stays strictly between 2.0 and 3.0 bps across realistic AMM slippage values
    assert SuiBotRunner._compute_dynamic_slippage_buffer_bps(2.0, 0.0) == 2.0
    b_mid = SuiBotRunner._compute_dynamic_slippage_buffer_bps(2.0, 4.24)
    assert 2.0 < b_mid < 3.0
    assert SuiBotRunner._compute_dynamic_slippage_buffer_bps(2.0, 25.0) == 3.0
    assert SuiBotRunner._compute_dynamic_slippage_buffer_bps(0.0, 5.0) == 0.0


@pytest.mark.asyncio
async def test_dynamic_slippage_buffer_gates_marginal_drift_and_passes_wide_spread(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Spreads passing effective_hurdle_bps (20.24) by < buffer (~2.21 bps) are blocked; wide spreads execute."""
    runner = SuiBotRunner(
        config=SuiBotConfig(port=18190, dry_run_mode=False, slippage_safety_buffer_bps=2.0)
    )
    runner.update_gas_balance(5.0)

    def _market(spread: float) -> Dict[str, Any]:
        return {
            "SUI/USDC": {
                "cetus_price": 0.90,
                "deepbook_price": 0.9018,
                "deepbook_ask": 0.9020,
                "spread_bps": spread,
                "forward_spread_bps": spread,
                "reverse_spread_bps": 0.0,
                "cetus_liquidity": 7.8679e13,
                "cetus_sqrt_price": 33.33,
                "bid_depth_quote": 50_000.0,
                "ask_depth_quote": 50_000.0,
            }
        }

    # fee=16.0, amm_slippage~=4.24 -> effective_hurdle_bps~=20.24; dynamic_buffer~=2.21 -> execution_hurdle~=22.45
    # Marginal spread 21.5 bps beats fee+amm_slippage (margin 1.26 bps) but must be skipped by buffer!
    mock_fill = AsyncMock(return_value=type("R", (), {"status": "FILLED", "order_id": "OK-1", "size": 1_000_000_000})())
    try:
        with caplog.at_level(logging.INFO), \
             patch.object(runner, "poll_market_spreads", return_value=_market(21.5)), \
             patch.object(runner.validator.venue, "submit_order", new=mock_fill):
            results = await runner.scan_once()
            sui = next(r for r in results if r["pair"] == "SUI/USDC")
            assert sui["effective_hurdle_bps"] < 21.0
            assert 2.0 <= sui["slippage_buffer_bps"] <= 3.0
            assert sui["execution_hurdle_bps"] > 22.0
            assert sui["is_profitable"] is False
            assert mock_fill.await_count == 0
            assert "Sub-slippage spread on SUI/USDC" in caplog.text

        # Wide spread 26.0 bps clears fee + amm_slippage + 2-3 bps buffer + min_profit_usd -> executes!
        with patch.object(runner, "poll_market_spreads", return_value=_market(26.0)), \
             patch.object(runner.validator.venue, "submit_order", new=mock_fill):
            results = await runner.scan_once()
            sui = next(r for r in results if r["pair"] == "SUI/USDC")
            assert sui["is_profitable"] is True
            assert mock_fill.await_count == 1
    finally:
        await runner.stop()
