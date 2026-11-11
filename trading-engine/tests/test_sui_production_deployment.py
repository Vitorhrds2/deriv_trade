"""Automated Test Suite for Sui Production Deployment on Railway.

Milestone M4 Verification (Requirement R3):
1. sui_health_server.py:
   - Schema verification of GET /health payload (status, uptime, tier, borrow amount, gas balance, pairs, region, aborts, timestamp).
   - Latency benchmark (GET /health responds in < 50ms).
   - Degradation & Critical state handling (1.5 SUI warning, 0.5 SUI critical, abort thresholds).
   - Dynamic reflection of capital scaling promotions (Tier 1 -> Tier 2 -> Tier 3).
2. sui_bot_runner.py:
   - Configuration ingestion and validation from environment variables (with secure secret masking).
   - Pre-flight initialization and health check integration.
   - Multi-pair scanning cycle across all 4 configured trading pairs.
   - Move VM dry-run simulation and zero leg risk preservation.
   - Gas floor enforcement (throttling at 1.5 SUI, emergency halt at 0.5 SUI).
   - Graceful shutdown signal handling (SIGINT/SIGTERM) and clean resource release.
3. Dockerfile:
   - Inspection of base image (python:3.11-slim).
   - Security verification of non-root user (trader).
   - Environment variables (PYTHONUNBUFFERED=1, PORT=8080).
   - Container entrypoint specification (venues/sui_bot_runner.py).
"""

from __future__ import annotations

import asyncio
import os
import signal
import sys
import time
from pathlib import Path
from typing import Any, Dict

import aiohttp
import pytest
from unittest.mock import AsyncMock, patch

# Ensure trading-engine root is in sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from venues.sui_health_server import (
    ACTIVE_PAIRS,
    DEFAULT_HOST,
    DEFAULT_PORT,
    DEFAULT_REGION,
    SuiHealthServer,
)
from venues.sui_bot_runner import SuiBotConfig, SuiBotRunner
from venues.sui_scaling_engine import (
    DEFAULT_CRITICAL_GAS_FLOOR,
    DEFAULT_WARNING_GAS_FLOOR,
    STATUS_ACTIVE,
    STATUS_COOLING_DOWN,
    STATUS_EMERGENCY_LOCKED,
    DynamicCapitalScalingEngine,
    ScalingTier,
)


# ==============================================================================
# 1. Sui Health Server Tests
# ==============================================================================

@pytest.mark.asyncio
async def test_health_server_schema_healthy() -> None:
    """Verifies that GET /health returns 200 OK and conforms to JSON schema with synced balances."""
    test_port = 18081
    server = SuiHealthServer(
        host="127.0.0.1",
        port=test_port,
        sui_gas_balance=3.5,
        usdc_balance=12.3456,
        deep_balance=119.1576,
    )
    await server.start()

    try:
        url = f"http://127.0.0.1:{test_port}/health"
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                assert resp.status == 200
                data = await resp.json()

                # Verify all required fields
                assert data["status"] == "HEALTHY"
                assert isinstance(data["uptime_seconds"], (int, float))
                assert data["uptime_seconds"] >= 0.0
                assert data["current_tier"] in ("TIER_1", "TIER_2", "TIER_3")
                assert data["current_tier"] == "TIER_1"
                assert data["borrow_amount_usdc"] == 1_000_000_000
                assert isinstance(data["sui_gas_balance"], (int, float))
                assert data["sui_gas_balance"] == pytest.approx(3.5, abs=0.01)
                assert data["usdc_balance"] == pytest.approx(12.3456, abs=0.0001)
                assert data["deep_balance"] == pytest.approx(119.1576, abs=0.0001)
                assert data["balances_synced"] is True
                assert data["balances_source"] == "manual"
                assert isinstance(data["balances_updated_at"], (int, float))
                assert data["active_pairs"] == list(ACTIVE_PAIRS)
                assert data["region"] == "europe-west3"
                assert data["consecutive_aborts"] == 0
                assert isinstance(data["timestamp"], (int, float))
                assert data["timestamp"] > 0
    finally:
        await server.stop()


@pytest.mark.asyncio
async def test_health_server_latency_under_50ms() -> None:
    """Verifies that GET /health responds within acceptable latency (< 50ms)."""
    test_port = 18082
    server = SuiHealthServer(host="127.0.0.1", port=test_port, sui_gas_balance=3.5)
    await server.start()

    try:
        url = f"http://127.0.0.1:{test_port}/health"
        async with aiohttp.ClientSession() as session:
            start = time.perf_counter()
            async with session.get(url) as resp:
                elapsed_ms = (time.perf_counter() - start) * 1000.0
                assert resp.status == 200
                data = await resp.json()
                assert data["status"] == "HEALTHY"
                assert elapsed_ms < 50.0, f"Latency too high: {elapsed_ms:.2f}ms"
    finally:
        await server.stop()


@pytest.mark.asyncio
async def test_health_server_degraded_state_handling() -> None:
    """Verifies that gas balance < 1.5 SUI or 3 aborts transitions status to DEGRADED."""
    test_port = 18083
    engine = DynamicCapitalScalingEngine()
    engine.update_from_wallet_balances(usdc_balance=0.0, sui_balance=3.5)
    server = SuiHealthServer(host="127.0.0.1", port=test_port, scaling_engine=engine)
    await server.start()

    try:
        url = f"http://127.0.0.1:{test_port}/health"
        async with aiohttp.ClientSession() as session:
            # Baseline is healthy
            async with session.get(url) as resp:
                data = await resp.json()
                assert data["status"] == "HEALTHY"

            # 1. Trigger DEGRADED via gas warning (< 1.5 SUI)
            server.set_gas_balance(1.45)
            engine.update_from_wallet_balances(usdc_balance=0.0, sui_balance=1.45)
            async with session.get(url) as resp:
                data = await resp.json()
                assert data["status"] == "DEGRADED"
                assert data["sui_gas_balance"] == 1.45

            # Restore gas
            server.set_gas_balance(5.419)
            engine.update_from_wallet_balances(usdc_balance=0.0, sui_balance=5.419)

            # 2. Trigger DEGRADED via 3 consecutive aborts
            engine.record_trade_abort()
            engine.record_trade_abort()
            engine.record_trade_abort()
            assert engine.state.consecutive_aborts == 3
            assert engine.status == STATUS_COOLING_DOWN

            async with session.get(url) as resp:
                data = await resp.json()
                assert data["status"] == "DEGRADED"
                assert data["consecutive_aborts"] == 3
    finally:
        await server.stop()


@pytest.mark.asyncio
async def test_health_server_critical_state_handling() -> None:
    """Verifies that gas balance < 0.5 SUI or 5 aborts transitions status to CRITICAL."""
    test_port = 18084
    engine = DynamicCapitalScalingEngine()
    server = SuiHealthServer(host="127.0.0.1", port=test_port, scaling_engine=engine)
    await server.start()

    try:
        url = f"http://127.0.0.1:{test_port}/health"
        async with aiohttp.ClientSession() as session:
            # 1. Trigger CRITICAL via gas exhaustion (< 0.5 SUI)
            server.set_gas_balance(0.48)
            engine.update_from_wallet_balances(usdc_balance=0.0, sui_balance=0.48)
            async with session.get(url) as resp:
                data = await resp.json()
                assert data["status"] == "CRITICAL"
                assert data["sui_gas_balance"] == 0.48

            # Restore gas
            server.set_gas_balance(5.419)
            engine.update_from_wallet_balances(usdc_balance=0.0, sui_balance=5.419)

            # 2. Trigger CRITICAL via 5 consecutive aborts
            for _ in range(5):
                engine.record_trade_abort()
            assert engine.status == STATUS_EMERGENCY_LOCKED

            async with session.get(url) as resp:
                data = await resp.json()
                assert data["status"] == "CRITICAL"
                assert data["consecutive_aborts"] == 5
    finally:
        await server.stop()


@pytest.mark.asyncio
async def test_health_server_dynamic_scaling_tier_reflection() -> None:
    """Verifies that dynamic capital scaling promotions (1k -> 5k -> 10k USDC) are reflected."""
    test_port = 18085
    engine = DynamicCapitalScalingEngine()
    server = SuiHealthServer(host="127.0.0.1", port=test_port, scaling_engine=engine)
    await server.start()

    try:
        url = f"http://127.0.0.1:{test_port}/health"
        async with aiohttp.ClientSession() as session:
            # Initial Tier 1 (1k USDC)
            async with session.get(url) as resp:
                data = await resp.json()
                assert data["current_tier"] == "TIER_1"
                assert data["borrow_amount_usdc"] == 1_000_000_000

            # Promote to Tier 2 (>= $100 net profit, >= 10 trades)
            for _ in range(10):
                engine.record_trade_success(15.0)
            assert engine.current_tier == ScalingTier.TIER_2

            async with session.get(url) as resp:
                data = await resp.json()
                assert data["current_tier"] == "TIER_2"
                assert data["borrow_amount_usdc"] == 5_000_000_000
                assert data["accumulated_profit_usdc"] == 150.0

            # Promote to Tier 3 (>= $750 cumulative net profit, >= 20 trades)
            for _ in range(10):
                engine.record_trade_success(65.0)
            assert engine.current_tier == ScalingTier.TIER_3

            async with session.get(url) as resp:
                data = await resp.json()
                assert data["current_tier"] == "TIER_3"
                assert data["borrow_amount_usdc"] == 10_000_000_000
                assert data["accumulated_profit_usdc"] == 800.0
    finally:
        await server.stop()


@pytest.mark.asyncio
async def test_health_server_root_and_live_endpoints() -> None:
    """Verifies that GET / and GET /live return valid payloads."""
    test_port = 18086
    server = SuiHealthServer(host="127.0.0.1", port=test_port, sui_gas_balance=3.5)
    await server.start()

    try:
        async with aiohttp.ClientSession() as session:
            # Test /live endpoint
            async with session.get(f"http://127.0.0.1:{test_port}/live") as resp:
                assert resp.status == 200
                data = await resp.json()
                assert data["live"] is True
                assert data["uptime"] >= 0.0

            # Test / root endpoint
            async with session.get(f"http://127.0.0.1:{test_port}/") as resp:
                assert resp.status == 200
                data = await resp.json()
                assert data["service"] == "sui-deepbook-cetus-bot"
                assert data["status"] == "HEALTHY"
                assert data["region"] == "europe-west3"
    finally:
        await server.stop()


# ==============================================================================
# 2. Sui Bot Runner Tests
# ==============================================================================

def test_sui_bot_config_defaults_and_secret_masking(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verifies configuration default values and ensures SUI_PRIVATE_KEY is never exposed."""
    monkeypatch.delenv("PORT", raising=False)
    monkeypatch.delenv("REGION", raising=False)
    monkeypatch.delenv("SUI_PRIVATE_KEY", raising=False)

    config = SuiBotConfig.from_env()
    assert config.port == 8080
    assert config.region == "europe-west3"
    assert config.initial_borrow_amount == 1_000_000_000
    assert config.dry_run_mode is True
    assert config.warning_gas_floor == 1.5
    assert config.critical_gas_floor == 0.5
    assert config.sui_private_key is None

    # Test secret masking
    config_with_key = SuiBotConfig(sui_private_key="suiprivkey1secretmainnetkey9999999")
    repr_str = repr(config_with_key)
    safe_dict = config_with_key.to_safe_dict()

    assert "suiprivkey1secret" not in repr_str
    assert "suiprivkey1secret" not in str(safe_dict)
    assert safe_dict["has_private_key"] is True


def test_sui_bot_config_custom_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verifies that all environment variables are correctly ingested and parsed."""
    monkeypatch.setenv("PORT", "9090")
    monkeypatch.setenv("REGION", "europe-west3")
    monkeypatch.setenv("INITIAL_BORROW_AMOUNT", "5000000000")
    monkeypatch.setenv("LOG_LEVEL", "DEBUG")
    monkeypatch.setenv("DRY_RUN_MODE", "false")
    monkeypatch.setenv("SCAN_INTERVAL_SECONDS", "0.5")
    monkeypatch.setenv("THROTTLED_SCAN_INTERVAL_SECONDS", "2.0")
    monkeypatch.setenv("WARNING_GAS_FLOOR", "2.0")
    monkeypatch.setenv("CRITICAL_GAS_FLOOR", "0.8")
    monkeypatch.setenv("MAX_SCAN_CYCLES", "50")

    config = SuiBotConfig.from_env()
    assert config.port == 9090
    assert config.region == "europe-west3"
    assert config.initial_borrow_amount == 5_000_000_000
    assert config.log_level == "DEBUG"
    assert config.dry_run_mode is False
    assert config.scan_interval_seconds == 0.5
    assert config.throttled_scan_interval_seconds == 2.0
    assert config.warning_gas_floor == 2.0
    assert config.critical_gas_floor == 0.8
    assert config.max_scan_cycles == 50


def test_sui_bot_config_alias_resolution(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verifies that environment variable aliases are resolved correctly."""
    # Clear primary vars
    monkeypatch.delenv("OPERATOR_ADDRESS", raising=False)
    monkeypatch.delenv("SUI_PRIVATE_KEY", raising=False)
    monkeypatch.delenv("DEEPBOOK_BALANCE_MANAGER_ID", raising=False)
    monkeypatch.delenv("INITIAL_BORROW_AMOUNT", raising=False)
    monkeypatch.delenv("SUI_GRAPHQL_URL", raising=False)

    # Set alias vars
    monkeypatch.setenv("SUI_WALLET_ADDRESS", "0x5621a8e7199680512ee829565b96febea2587e534fd69b33f04004298d7e5ce9")
    monkeypatch.setenv("SUI_SECRET_KEY", "suiprivkey1aliassecretkey000000000000000000000000000000000000000000")
    monkeypatch.setenv("BALANCE_MANAGER_ID", "0xbm_alias_123456789")
    monkeypatch.setenv("FLASH_BORROW_AMOUNT", "2000000000")
    monkeypatch.setenv("SUI_RPC_URL", "https://graphql.mainnet.sui.io/graphql")

    config = SuiBotConfig.from_env()
    assert config.operator_address == "0x5621a8e7199680512ee829565b96febea2587e534fd69b33f04004298d7e5ce9"
    assert config.sui_private_key == "suiprivkey1aliassecretkey000000000000000000000000000000000000000000"
    assert config.balance_manager_id == "0xbm_alias_123456789"
    assert config.initial_borrow_amount == 2_000_000_000
    assert config.graphql_url == "https://graphql.mainnet.sui.io/graphql"

    # Test empty string fallback (e.g., DEEPBOOK_BALANCE_MANAGER_ID="")
    monkeypatch.setenv("DEEPBOOK_BALANCE_MANAGER_ID", "")
    monkeypatch.delenv("BALANCE_MANAGER_ID", raising=False)
    config2 = SuiBotConfig.from_env()
    assert config2.balance_manager_id == "0x0000000000000000000000000000000000000000000000000000000000000001"


@pytest.mark.asyncio
async def test_sui_bot_runner_preflight_initialization() -> None:
    """Verifies pre-flight healthcheck integration and gas state ingestion in runner."""
    config = SuiBotConfig(port=18087)
    runner = SuiBotRunner(config=config)

    mock_preflight = {
        "rpc_connected": True,
        "sui_mist": 5_419_245_048,
        "sui_balance": 5.419245048,
        "usdc_raw": 0,
        "usdc_balance": 0.0,
    }

    report = await runner.run_preflight(mock_data=mock_preflight)
    assert report["status"] == "HEALTHY"
    assert report["sui_balance"] == pytest.approx(5.419, abs=0.01)
    assert runner.scaling_engine.state.sui_gas_balance == pytest.approx(5.419, abs=0.01)
    assert runner.health_server.get_health_data()["status"] == "HEALTHY"


@pytest.mark.asyncio
async def test_sui_bot_runner_multi_pair_scan_cycle() -> None:
    """Verifies that a single scan cycle evaluates all 4 pairs with Move VM dry-run."""
    config = SuiBotConfig(port=18088)
    runner = SuiBotRunner(config=config)
    runner.update_gas_balance(5.419)

    results = await runner.scan_once()

    # Must evaluate all active pairs
    assert len(results) == len(ACTIVE_PAIRS)
    pairs_evaluated = [r["pair"] for r in results]
    assert pairs_evaluated == list(ACTIVE_PAIRS)

    for entry in results:
        assert entry["zero_leg_risk_preserved"] is True
        assert entry["gas_cost_sui"] == 0.002
        assert entry["borrow_amount"] > 0
        assert entry["tier"] == "TIER_1"


@pytest.mark.asyncio
async def test_sui_bot_runner_critical_gas_halts_trading() -> None:
    """Verifies that when gas drops below 0.5 SUI critical floor, scan_once halts trades."""
    config = SuiBotConfig(port=18089)
    runner = SuiBotRunner(config=config)

    # Set critical gas level (0.45 SUI < 0.5 SUI floor)
    runner.update_gas_balance(0.45)
    assert runner.scaling_engine.can_trade() is False
    assert runner.scaling_engine.status == STATUS_EMERGENCY_LOCKED

    # Scanning pass must abort trading execution immediately
    results = await runner.scan_once()
    assert len(results) == 0


@pytest.mark.asyncio
async def test_sui_bot_runner_graceful_shutdown_lifecycle() -> None:
    """Verifies full runner startup, cycle execution, and graceful shutdown via signal event."""
    test_port = 18090
    config = SuiBotConfig(
        port=test_port,
        scan_interval_seconds=0.05,
        max_scan_cycles=3,
    )
    runner = SuiBotRunner(config=config)

    mock_preflight = {
        "rpc_connected": True,
        "sui_mist": 5_419_245_048,
        "sui_balance": 5.419245048,
    }

    # Start runner in background task
    task = asyncio.create_task(runner.start(mock_preflight=mock_preflight))

    # Give it a moment to run cycles
    await asyncio.sleep(0.3)

    # Verify health server responded while running
    async with aiohttp.ClientSession() as session:
        async with session.get(f"http://127.0.0.1:{test_port}/health") as resp:
            assert resp.status == 200
            data = await resp.json()
            assert data["status"] == "HEALTHY"

    # Stop runner gracefully
    await runner.stop()
    await task

    # Confirm clean termination
    assert runner.is_running is False
    assert runner.completed_cycles >= 1
    assert runner.health_server.is_running is False


@pytest.mark.asyncio
async def test_sui_bot_runner_sub_slippage_spread_skips_deep_usdc() -> None:
    """Verifies that when DEEP/USDC has a spread of +10 bps (exceeds 6 bps fee hurdle
    but below ~41.3 bps effective hurdle with average Cetus CLMM slippage), execution is cleanly skipped.
    """
    config = SuiBotConfig(port=18091, dry_run_mode=False)
    runner = SuiBotRunner(config=config)
    runner.update_gas_balance(5.419)

    mock_spreads = {
        "DEEP/USDC": {
            "cetus_price": 0.0139,
            "deepbook_price": 0.0139,
            "deepbook_ask": 0.0139,
            "spread_bps": 10.0,
            "forward_spread_bps": 0.0,
            "reverse_spread_bps": 10.0,
            "best_route": "REVERSE",
            "cetus_liquidity": 2.4023e11,
            "cetus_sqrt_price": int(round((0.0139 ** 0.5) * (1 << 64))),
            "ask_depth_quote": 5000.0,
            "bid_depth_quote": 5000.0,
        }
    }

    with patch.object(runner, "poll_market_spreads", return_value=mock_spreads), \
         patch.object(runner.validator.venue, "submit_order", new_callable=AsyncMock) as mock_submit:
        results = await runner.scan_once()

        deep_res = next(r for r in results if r["pair"] == "DEEP/USDC")
        assert deep_res["is_profitable"] is False
        assert deep_res["effective_hurdle_bps"] > 40.0
        assert deep_res["execution_status"] == "SIMULATED"
        assert mock_submit.call_count == 0


@pytest.mark.asyncio
async def test_sui_bot_runner_super_slippage_spread_triggers_deep_usdc() -> None:
    """Verifies that when DEEP/USDC has a wide spread of +120 bps (exceeds effective hurdle of ~76.6 bps),
    execution is triggered.
    """
    config = SuiBotConfig(port=18092, dry_run_mode=False)
    runner = SuiBotRunner(config=config)
    runner.update_gas_balance(5.419)

    mock_spreads = {
        "DEEP/USDC": {
            "cetus_price": 0.0139,
            "deepbook_price": 0.0139,
            "deepbook_ask": 0.0139,
            "spread_bps": 120.0,
            "forward_spread_bps": 0.0,
            "reverse_spread_bps": 120.0,
            "best_route": "REVERSE",
            "cetus_liquidity": 2.4023e11,
            "cetus_sqrt_price": int(round((0.0139 ** 0.5) * (1 << 64))),
            "ask_depth_quote": 5000.0,
            "bid_depth_quote": 5000.0,
        }
    }

    from venues.sui_deepbook_venue import OrderExecutionResult
    mock_fill = OrderExecutionResult(
        venue="sui_deepbook",
        order_id="PTB-LIVE-DEEP-USDC-123",
        symbol="DEEP/USDC",
        side="BUY",
        price=0.0139,
        size=100_000_000,
        fee_bps=0.0,
        rebate_bps=0.0,
        is_maker=False,
        status="FILLED",
        latency_ms=10.0,
        timestamp_ns=1000000,
    )

    with patch.object(runner, "poll_market_spreads", return_value=mock_spreads), \
         patch.object(runner.validator.venue, "submit_order", new_callable=AsyncMock, return_value=mock_fill) as mock_submit:
        results = await runner.scan_once()

        deep_res = next(r for r in results if r["pair"] == "DEEP/USDC")
        assert deep_res["is_profitable"] is True
        assert deep_res["execution_status"] == "EXECUTED"
        assert mock_submit.call_count == 1


# ==============================================================================
# 3. Dockerfile Configuration Tests
# ==============================================================================

def test_dockerfile_hardened_specifications() -> None:
    """Verifies that Dockerfile implements hardened container specs for Railway."""
    dockerfile_path = BASE_DIR / "Dockerfile"
    assert dockerfile_path.exists(), f"Dockerfile not found at {dockerfile_path}"

    content = dockerfile_path.read_text(encoding="utf-8")

    # 1. Base Image
    assert "FROM python:3.11-slim" in content, "Base image must be python:3.11-slim"

    # 2. Non-root user
    assert "useradd" in content and "trader" in content, "Must create dedicated trader user"
    assert "USER trader" in content, "Must switch to non-root user trader"

    # 3. Environment Variables
    assert "PYTHONUNBUFFERED=1" in content, "Must set PYTHONUNBUFFERED=1"
    assert "PORT=8080" in content, "Must configure default PORT=8080"

    # 4. Working directory and source copy
    assert "WORKDIR /app" in content, "Must set WORKDIR /app"
    assert "COPY requirements.txt" in content, "Must copy requirements.txt"
    assert "pip install" in content, "Must install dependencies"

    # 5. Entry point
    assert 'CMD ["python", "venues/sui_bot_runner.py"]' in content or (
        "venues/sui_bot_runner.py" in content
    ), "Entrypoint must target venues/sui_bot_runner.py"

    # 6. Healthcheck definition
    assert "HEALTHCHECK" in content, "Must define container HEALTHCHECK"
    assert "/health" in content, "Healthcheck must probe /health endpoint"


# ==============================================================================
# 4. Live Balance Sync & Zero-Hardcoding Regression Tests
# ==============================================================================

@pytest.mark.asyncio
async def test_health_server_uninitialized_has_no_hardcoded_fallback() -> None:
    """Uninitialized /health must report None balances and DEGRADED status, never hardcoded SUI."""
    test_port = 18091
    server = SuiHealthServer(host="127.0.0.1", port=test_port)
    await server.start()

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(f"http://127.0.0.1:{test_port}/health") as resp:
                assert resp.status == 200
                data = await resp.json()
                assert data["status"] == "DEGRADED"
                assert data["sui_gas_balance"] is None
                assert data["usdc_balance"] is None
                assert data["deep_balance"] is None
                assert data["balances_synced"] is False
                assert data["balances_source"] == "uninitialized"
                assert data["balances_updated_at"] is None
    finally:
        await server.stop()


@pytest.mark.asyncio
async def test_health_server_synced_zero_sui_is_critical_not_fallback() -> None:
    """Synced 0.0 SUI balance must lock trading and report CRITICAL without falling back."""
    test_port = 18092
    engine = DynamicCapitalScalingEngine()
    engine.update_from_wallet_balances(usdc_balance=0.0, sui_balance=0.0, deep_balance=119.1576)
    assert engine.can_trade() is False
    assert engine.status == STATUS_EMERGENCY_LOCKED

    server = SuiHealthServer(host="127.0.0.1", port=test_port, scaling_engine=engine)
    await server.start()

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(f"http://127.0.0.1:{test_port}/health") as resp:
                assert resp.status == 200
                data = await resp.json()
                assert data["status"] == "CRITICAL"
                assert data["sui_gas_balance"] == 0.0
                assert data["usdc_balance"] == 0.0
                assert data["deep_balance"] == pytest.approx(119.1576, abs=0.0001)
                assert data["balances_synced"] is True
    finally:
        await server.stop()


@pytest.mark.asyncio
async def test_health_server_on_demand_refresh_endpoint() -> None:
    """GET /health?refresh=1 triggers balance_refresher while plain GET /health stays in-memory."""
    test_port = 18093
    mock_refresher = AsyncMock(
        return_value={
            "sui": 3.4158,
            "usdc": 0.0,
            "deep": 119.1576,
            "source": "onchain_graphql_refresh",
        }
    )
    server = SuiHealthServer(host="127.0.0.1", port=test_port, balance_refresher=mock_refresher)
    await server.start()

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(f"http://127.0.0.1:{test_port}/health") as resp:
                data = await resp.json()
                assert data["status"] == "DEGRADED"
                assert data["balances_synced"] is False
                assert mock_refresher.call_count == 0

            async with session.get(f"http://127.0.0.1:{test_port}/health?refresh=1") as resp:
                data = await resp.json()
                assert data["status"] == "HEALTHY"
                assert data["sui_gas_balance"] == pytest.approx(3.4158, abs=0.0001)
                assert data["usdc_balance"] == 0.0
                assert data["deep_balance"] == pytest.approx(119.1576, abs=0.0001)
                assert data["balances_synced"] is True
                assert data["balances_source"] == "onchain_graphql_refresh"
                assert mock_refresher.call_count == 1

            async with session.get(f"http://127.0.0.1:{test_port}/health") as resp:
                data = await resp.json()
                assert data["status"] == "HEALTHY"
                assert data["sui_gas_balance"] == pytest.approx(3.4158, abs=0.0001)
                assert mock_refresher.call_count == 1
    finally:
        await server.stop()


@pytest.mark.asyncio
async def test_bot_runner_live_balance_sync_preserves_usdc_and_deep() -> None:
    """Periodic runner sync propagates SUI/USDC/DEEP to /health and update_gas_balance preserves them."""
    runner = SuiBotRunner(config=SuiBotConfig(port=18094))
    runner.validator.graphql_client.operator_address = "0x5621a8e7"

    try:
        with patch.object(
            runner.validator.graphql_client,
            "get_live_deepbook_fee_params",
            new_callable=AsyncMock,
            return_value={},
        ), patch.object(
            runner.validator.graphql_client,
            "get_deep_coin",
            new_callable=AsyncMock,
            return_value=None,
        ), patch.object(
            runner.validator.graphql_client,
            "get_wallet_balances",
            new_callable=AsyncMock,
            return_value={
                "sui_mist": 3_415_753_299,
                "sui": 3.415753299,
                "usdc_raw": 25_500_000,
                "usdc": 25.5,
                "deep_raw": 119_157_562,
                "deep": 119.157562,
            },
        ):
            await runner._refresh_live_fee_and_deep_context({"SUI/USDC": {"source": "live_graphql"}})

        health = runner.health_server.get_health_data()
        assert health["status"] == "HEALTHY"
        assert health["sui_gas_balance"] == pytest.approx(3.4158, abs=0.0001)
        assert health["usdc_balance"] == pytest.approx(25.5, abs=0.0001)
        assert health["deep_balance"] == pytest.approx(119.1576, abs=0.0001)
        assert health["balances_synced"] is True
        assert health["balances_source"] == "onchain_graphql_periodic"

        # update_gas_balance must NOT overwrite tracked USDC/DEEP with hardcoded 0.0
        runner.update_gas_balance(2.9)
        updated_health = runner.health_server.get_health_data()
        assert updated_health["sui_gas_balance"] == pytest.approx(2.9, abs=0.0001)
        assert updated_health["usdc_balance"] == pytest.approx(25.5, abs=0.0001)
        assert updated_health["deep_balance"] == pytest.approx(119.1576, abs=0.0001)
    finally:
        await runner.stop()


@pytest.mark.asyncio
async def test_graphql_client_get_wallet_balances_includes_deep() -> None:
    """SuiGraphQLClient.get_wallet_balances retrieves atomic SUI, USDC, and DEEP in one query."""
    from venues.sui_deepbook_venue import SuiGraphQLClient

    mock_app = aiohttp.web.Application()

    async def handle_gql(request: aiohttp.web.Request) -> aiohttp.web.Response:
        return aiohttp.web.json_response(
            {
                "data": {
                    "address": {
                        "sui": {"totalBalance": "3415753299"},
                        "usdc": {"totalBalance": "1250000"},
                        "deep": {"totalBalance": "119157562"},
                    }
                }
            }
        )

    mock_app.router.add_post("/graphql", handle_gql)
    app_runner = aiohttp.web.AppRunner(mock_app)
    await app_runner.setup()
    site = aiohttp.web.TCPSite(app_runner, "127.0.0.1", 0)
    await site.start()
    port = site._server.sockets[0].getsockname()[1]

    client = SuiGraphQLClient(endpoint=f"http://127.0.0.1:{port}/graphql")
    try:
        balances = await client.get_wallet_balances("0x5621a8e7")
        assert balances == {
            "sui_mist": 3_415_753_299,
            "sui": pytest.approx(3.415753299, abs=1e-9),
            "usdc_raw": 1_250_000,
            "usdc": pytest.approx(1.25, abs=1e-6),
            "deep_raw": 119_157_562,
            "deep": pytest.approx(119.157562, abs=1e-6),
        }
    finally:
        await client.close()
        await app_runner.cleanup()
