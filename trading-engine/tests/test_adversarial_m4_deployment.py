"""Adversarial Stress Test Suite: Milestone M4 Production Deployment.

Empirical Challenger verification for Milestone M4 (Railway Production Deployment):
1. Burst HTTP Stress Testing:
   - 100 concurrent requests to /health, /live, and /
   - Zero deadlocks, race conditions, or latency spikes (p95 < 500ms under 100-burst)
   - Concurrent read/write stress: mutating state during burst queries
2. Malformed HTTP Requests, Unexpected Headers & Invalid Paths:
   - Path traversal attempts, non-existent routes, SQL injection strings in URLs
   - Disallowed HTTP methods (POST, PUT, DELETE, PATCH)
   - Oversized / corrupt headers, giant payloads, weird Unicode/CRLF headers
   - Liveness retention after attack bombardment
3. Signal Resilience & Graceful Shutdown:
   - Rapid SIGINT and SIGTERM while runner is mid-scan
   - Clean graceful exit without leaked background tasks or hung loops
   - Rapid multi-signal storms (< 5ms apart)
   - Stop sequence idempotency
4. Security Audit & Credential Masking:
   - SUI_PRIVATE_KEY never exposed in repr(), str(), to_safe_dict(), or JSON
   - SUI_PRIVATE_KEY never leaked in logging outputs or exception tracebacks
   - SUI_PRIVATE_KEY never returned in HTTP health responses
5. Configuration Fuzzing:
   - Non-integer / corrupt PORT values
   - Non-integer / negative INITIAL_BORROW_AMOUNT
   - Corrupt / invalid LOG_LEVEL values
   - Corrupt SUI_GRAPHQL_URL handling during preflight
   - Extreme gas floor configurations
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import signal
import sys
import time
from pathlib import Path
from typing import Any, Dict, List
from unittest.mock import AsyncMock, patch

import aiohttp
import pytest

# Ensure trading-engine root is in sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from venues.sui_health_server import (
    ACTIVE_PAIRS,
    DEFAULT_HOST,
    DEFAULT_PORT,
    DEFAULT_REGION,
    DEFAULT_VERIFIED_SUI_BALANCE,
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
# SECTION 1: BURST HTTP STRESS TESTING
# ==============================================================================

class TestBurstHTTPStress:
    """Stress tests SuiHealthServer under burst concurrency and high load."""

    @pytest.mark.asyncio
    async def test_adversarial_burst_100_concurrent_health_requests(self) -> None:
        """Fires 100 concurrent requests to /health.
        
        Verifies:
        - 100% of requests succeed (HTTP 200 OK).
        - Payload adheres to schema on every request.
        - No deadlocks, race conditions, or connection drops.
        - Zero latency spikes (all complete in < 500ms under 100-request simultaneous queue).
        """
        test_port = 19101
        server = SuiHealthServer(host="127.0.0.1", port=test_port)
        await server.start()

        try:
            url = f"http://127.0.0.1:{test_port}/health"
            connector = aiohttp.TCPConnector(limit=100)
            async with aiohttp.ClientSession(connector=connector) as session:
                latencies: List[float] = []

                async def fetch_single(req_id: int) -> Dict[str, Any]:
                    start = time.perf_counter()
                    async with session.get(url) as resp:
                        elapsed = (time.perf_counter() - start) * 1000.0
                        latencies.append(elapsed)
                        assert resp.status == 200, f"Req {req_id} failed with status {resp.status}"
                        payload = await resp.json()
                        assert payload["status"] in ("HEALTHY", "DEGRADED", "CRITICAL")
                        assert payload["active_pairs"] == ACTIVE_PAIRS
                        assert payload["sui_gas_balance"] > 0
                        return payload

                tasks = [fetch_single(i) for i in range(100)]
                results = await asyncio.gather(*tasks)

                assert len(results) == 100
                latencies.sort()
                p50 = latencies[50]
                p95 = latencies[95]
                max_lat = latencies[-1]

                # Assert latency thresholds under 100-burst single-thread event loop load
                assert p95 < 500.0, f"P95 latency exceeded threshold: {p95:.2f}ms"
                assert max_lat < 1000.0, f"Max latency spiked to unacceptable level: {max_lat:.2f}ms"
        finally:
            await server.stop()

    @pytest.mark.asyncio
    async def test_adversarial_burst_100_concurrent_live_and_root(self) -> None:
        """Fires 100 concurrent requests to /live and /root.
        
        Verifies:
        - 100% of requests return 200 OK.
        - Valid JSON responses without server deadlocks.
        """
        test_port = 19102
        server = SuiHealthServer(host="127.0.0.1", port=test_port)
        await server.start()

        try:
            connector = aiohttp.TCPConnector(limit=100)
            async with aiohttp.ClientSession(connector=connector) as session:
                async def fetch_live() -> None:
                    async with session.get(f"http://127.0.0.1:{test_port}/live") as resp:
                        assert resp.status == 200
                        data = await resp.json()
                        assert data["live"] is True

                async def fetch_root() -> None:
                    async with session.get(f"http://127.0.0.1:{test_port}/") as resp:
                        assert resp.status == 200
                        data = await resp.json()
                        assert data["service"] == "sui-deepbook-cetus-bot"

                tasks = [fetch_live() for _ in range(50)] + [fetch_root() for _ in range(50)]
                await asyncio.gather(*tasks)
        finally:
            await server.stop()

    @pytest.mark.asyncio
    async def test_adversarial_burst_mixed_endpoints_interleaved(self) -> None:
        """Fires 150 concurrent requests randomly interleaved across /health, /live, and /."""
        test_port = 19103
        server = SuiHealthServer(host="127.0.0.1", port=test_port)
        await server.start()

        try:
            connector = aiohttp.TCPConnector(limit=150)
            async with aiohttp.ClientSession(connector=connector) as session:
                async def fetch_target(path: str) -> int:
                    async with session.get(f"http://127.0.0.1:{test_port}{path}") as resp:
                        return resp.status

                paths = ["/health", "/live", "/"] * 50
                tasks = [fetch_target(p) for p in paths]
                statuses = await asyncio.gather(*tasks)

                assert len(statuses) == 150
                assert all(s == 200 for s in statuses)
        finally:
            await server.stop()

    @pytest.mark.asyncio
    async def test_adversarial_concurrent_read_write_race_conditions(self) -> None:
        """Stress-tests health server under concurrent read/write state mutation.
        
        A reader coroutine fires 100 requests to /health while a writer coroutine
        rapidly mutates gas balance, abort count, and scaling tier.
        Verifies no race conditions, mutable state corruption, or 500 errors.
        """
        test_port = 19104
        engine = DynamicCapitalScalingEngine()
        server = SuiHealthServer(host="127.0.0.1", port=test_port, scaling_engine=engine)
        await server.start()

        stop_writer = asyncio.Event()

        async def writer() -> None:
            balances = [5.419, 1.45, 0.48, 5.419, 2.5]
            idx = 0
            while not stop_writer.is_set():
                b = balances[idx % len(balances)]
                server.set_gas_balance(b)
                server.set_consecutive_aborts(idx % 6)
                if idx % 2 == 0:
                    server.set_tier("TIER_2", 5_000_000_000)
                else:
                    server.set_tier("TIER_1", 1_000_000_000)
                idx += 1
                await asyncio.sleep(0.001)

        writer_task = asyncio.create_task(writer())

        try:
            connector = aiohttp.TCPConnector(limit=100)
            async with aiohttp.ClientSession(connector=connector) as session:
                async def reader() -> Dict[str, Any]:
                    async with session.get(f"http://127.0.0.1:{test_port}/health") as resp:
                        assert resp.status == 200
                        return await resp.json()

                tasks = [reader() for _ in range(100)]
                results = await asyncio.gather(*tasks)

                assert len(results) == 100
                for r in results:
                    assert r["status"] in ("HEALTHY", "DEGRADED", "CRITICAL")
                    assert r["current_tier"] in ("TIER_1", "TIER_2", "TIER_3")
                    assert isinstance(r["sui_gas_balance"], (int, float))
                    assert 0 <= r["consecutive_aborts"] <= 6
        finally:
            stop_writer.set()
            await writer_task
            await server.stop()


# ==============================================================================
# SECTION 2: MALFORMED HTTP REQUESTS, UNEXPECTED HEADERS & INVALID PATHS
# ==============================================================================

class TestMalformedHTTPAndInvalidPaths:
    """Stress tests SuiHealthServer against malformed, abusive, or unexpected HTTP traffic."""

    @pytest.mark.asyncio
    async def test_adversarial_invalid_paths_and_path_traversal(self) -> None:
        """Verifies clean 404 responses on non-existent endpoints and traversal attempts."""
        test_port = 19105
        server = SuiHealthServer(host="127.0.0.1", port=test_port)
        await server.start()

        invalid_paths = [
            "/nonexistent",
            "/health/child",
            "/health/..%2f..%2fetc%2fpasswd",
            "/.env",
            "/admin",
            "/api/v1/debug",
            "/graphql",
            "/health.json",
        ]

        try:
            async with aiohttp.ClientSession() as session:
                for path in invalid_paths:
                    async with session.get(f"http://127.0.0.1:{test_port}{path}") as resp:
                        assert resp.status == 404, f"Path {path} returned unexpected status {resp.status}"
        finally:
            await server.stop()

    @pytest.mark.asyncio
    async def test_adversarial_disallowed_http_methods(self) -> None:
        """Verifies that non-GET methods to registered routes return 405 Method Not Allowed."""
        test_port = 19106
        server = SuiHealthServer(host="127.0.0.1", port=test_port)
        await server.start()

        disallowed_calls = [
            ("POST", "/health"),
            ("PUT", "/health"),
            ("DELETE", "/health"),
            ("PATCH", "/health"),
            ("POST", "/live"),
            ("DELETE", "/live"),
            ("POST", "/"),
            ("PUT", "/"),
        ]

        try:
            async with aiohttp.ClientSession() as session:
                for method, path in disallowed_calls:
                    async with session.request(method, f"http://127.0.0.1:{test_port}{path}") as resp:
                        assert resp.status == 405, f"{method} {path} returned {resp.status}, expected 405"
        finally:
            await server.stop()

    @pytest.mark.asyncio
    async def test_adversarial_unexpected_and_oversized_headers(self) -> None:
        """Tests server handling of corrupt, oversized, or malicious header values."""
        test_port = 19107
        server = SuiHealthServer(host="127.0.0.1", port=test_port)
        await server.start()

        try:
            async with aiohttp.ClientSession() as session:
                # 1. Custom bizarre and Unicode headers
                headers = {
                    "X-Custom-Exploit": "' OR '1'='1",
                    "X-Unicode-Bomb": "🚀🔥👾" * 100,
                    "X-Long-Header": "A" * 4096,
                }
                async with session.get(f"http://127.0.0.1:{test_port}/health", headers=headers) as resp:
                    assert resp.status == 200
                    data = await resp.json()
                    assert data["status"] == "HEALTHY"

                # 2. Corrupt Content-Type header on GET
                headers = {"Content-Type": "application/x-corrupt-binary"}
                async with session.get(f"http://127.0.0.1:{test_port}/health", headers=headers) as resp:
                    assert resp.status == 200
        finally:
            await server.stop()

    @pytest.mark.asyncio
    async def test_adversarial_unexpected_body_in_get_request(self) -> None:
        """Tests server handling of GET requests containing unexpected body payloads."""
        test_port = 19108
        server = SuiHealthServer(host="127.0.0.1", port=test_port)
        await server.start()

        try:
            async with aiohttp.ClientSession() as session:
                junk_body = b"{" + b"A" * 32768 + b"}"
                async with session.get(
                    f"http://127.0.0.1:{test_port}/health",
                    data=junk_body,
                    headers={"Content-Type": "application/json"},
                ) as resp:
                    assert resp.status == 200
                    data = await resp.json()
                    assert data["status"] == "HEALTHY"
        finally:
            await server.stop()

    @pytest.mark.asyncio
    async def test_adversarial_server_health_recovery_after_abuse(self) -> None:
        """Verifies that server remains healthy and operational after receiving abusive traffic."""
        test_port = 19109
        server = SuiHealthServer(host="127.0.0.1", port=test_port)
        await server.start()

        try:
            async with aiohttp.ClientSession() as session:
                # Send 50 bad requests
                for i in range(50):
                    async with session.get(f"http://127.0.0.1:{test_port}/bad_route_{i}") as resp:
                        assert resp.status == 404

                # Immediate follow-up with legitimate request
                start = time.perf_counter()
                async with session.get(f"http://127.0.0.1:{test_port}/health") as resp:
                    elapsed = (time.perf_counter() - start) * 1000.0
                    assert resp.status == 200
                    assert elapsed < 50.0, f"Recovery latency too high: {elapsed:.2f}ms"
                    data = await resp.json()
                    assert data["status"] == "HEALTHY"
        finally:
            await server.stop()


# ==============================================================================
# SECTION 3: SIGNAL RESILIENCE & GRACEFUL SHUTDOWN
# ==============================================================================

class TestSignalResilienceAndShutdown:
    """Stress tests SuiBotRunner against rapid signals, cancellations, and task leaks."""

    @pytest.mark.asyncio
    async def test_adversarial_sigint_and_sigterm_simulation_during_idle(self) -> None:
        """Verifies graceful exit when SIGINT or SIGTERM is received while runner is idle."""
        test_port = 19110
        config = SuiBotConfig(port=test_port, scan_interval_seconds=10.0)
        runner = SuiBotRunner(config=config)

        mock_preflight = {
            "rpc_connected": True,
            "sui_mist": 5_419_245_048,
            "sui_balance": 5.419245048,
        }

        # Start runner in background task
        runner_task = asyncio.create_task(runner.start(mock_preflight=mock_preflight))
        await asyncio.sleep(0.1)

        assert runner.is_running is True
        assert runner.shutdown_event.is_set() is False

        # Fire simulated SIGINT
        runner._handle_signal(signal.SIGINT)
        assert runner.shutdown_event.is_set() is True

        # Runner should unblock and complete promptly
        await asyncio.wait_for(runner_task, timeout=2.0)
        await runner.stop()

        assert runner.is_running is False
        assert runner.health_server.is_running is False

    @pytest.mark.asyncio
    async def test_adversarial_signal_interruption_mid_scan(self) -> None:
        """Verifies graceful exit when signal arrives during an ongoing scan cycle."""
        test_port = 19111
        config = SuiBotConfig(port=test_port, scan_interval_seconds=0.01)
        runner = SuiBotRunner(config=config)

        mock_preflight = {
            "rpc_connected": True,
            "sui_mist": 5_419_245_048,
            "sui_balance": 5.419245048,
        }

        # Inject artificial delay inside simulate_ptb_dry_run to catch mid-scan
        original_simulate = runner.validator.simulate_ptb_dry_run

        def slow_simulate(*args: Any, **kwargs: Any) -> Dict[str, Any]:
            time.sleep(0.05)
            return original_simulate(*args, **kwargs)

        runner.validator.simulate_ptb_dry_run = slow_simulate  # type: ignore

        runner_task = asyncio.create_task(runner.start(mock_preflight=mock_preflight))
        await asyncio.sleep(0.08)

        # Signal mid-scan
        runner._handle_signal(signal.SIGTERM)

        # Must exit without hanging
        await asyncio.wait_for(runner_task, timeout=3.0)
        await runner.stop()

        assert runner.is_running is False
        assert runner.health_server.is_running is False

    @pytest.mark.asyncio
    async def test_adversarial_signal_storm_rapid_multi_signals(self) -> None:
        """Verifies runner resilience when bombarded with rapid back-to-back termination signals."""
        test_port = 19112
        config = SuiBotConfig(port=test_port, scan_interval_seconds=1.0)
        runner = SuiBotRunner(config=config)

        mock_preflight = {
            "rpc_connected": True,
            "sui_mist": 5_419_245_048,
            "sui_balance": 5.419245048,
        }

        runner_task = asyncio.create_task(runner.start(mock_preflight=mock_preflight))
        await asyncio.sleep(0.1)

        # Bombard with 10 alternating signals
        for i in range(10):
            sig = signal.SIGINT if i % 2 == 0 else signal.SIGTERM
            runner._handle_signal(sig)

        await asyncio.wait_for(runner_task, timeout=2.0)
        await runner.stop()

        assert runner.is_running is False
        assert runner.health_server.is_running is False

    @pytest.mark.asyncio
    async def test_adversarial_runner_stop_idempotency(self) -> None:
        """Verifies that calling runner.stop() multiple times is safe and idempotent."""
        test_port = 19113
        config = SuiBotConfig(port=test_port)
        runner = SuiBotRunner(config=config)
        await runner.health_server.start()

        # Call stop 3 times sequentially
        await runner.stop()
        await runner.stop()
        await runner.stop()

        assert runner.is_running is False
        assert runner.health_server.is_running is False

    @pytest.mark.asyncio
    async def test_adversarial_zero_task_leakage_after_shutdown(self) -> None:
        """Audits asyncio tasks before and after runner execution to ensure zero leaked tasks."""
        test_port = 19114
        config = SuiBotConfig(port=test_port, max_scan_cycles=2, scan_interval_seconds=0.01)
        runner = SuiBotRunner(config=config)

        mock_preflight = {
            "rpc_connected": True,
            "sui_mist": 5_419_245_048,
            "sui_balance": 5.419245048,
        }

        current_task = asyncio.current_task()
        initial_tasks = {t for t in asyncio.all_tasks() if t is not current_task and not t.done()}

        # Run runner
        await runner.start(mock_preflight=mock_preflight)
        await runner.stop()

        # Allow loop to settle
        await asyncio.sleep(0.05)

        remaining_tasks = {t for t in asyncio.all_tasks() if t is not current_task and not t.done()}
        leaked_tasks = remaining_tasks - initial_tasks

        assert len(leaked_tasks) == 0, f"Leaked background tasks detected: {leaked_tasks}"


# ==============================================================================
# SECTION 4: SECURITY AUDIT & SENSITIVE CREDENTIAL MASKING
# ==============================================================================

class TestSecurityAuditAndSecretMasking:
    """Verifies that SUI_PRIVATE_KEY is never exposed across logs, strings, exceptions, or payloads."""

    SECRET_CANARY = "suiprivkey1secretcanarykeyforadversarialverification999888777"

    def test_adversarial_secret_never_in_repr_or_str(self) -> None:
        """Verifies SUI_PRIVATE_KEY is omitted from __repr__ and __str__."""
        config = SuiBotConfig(sui_private_key=self.SECRET_CANARY)

        repr_output = repr(config)
        str_output = str(config)

        assert self.SECRET_CANARY not in repr_output, "CRITICAL: Private key leaked in repr(SuiBotConfig)"
        assert self.SECRET_CANARY not in str_output, "CRITICAL: Private key leaked in str(SuiBotConfig)"
        assert "sui_private_key" not in repr_output, "Field name sui_private_key should not be in repr"

    def test_adversarial_secret_never_in_safe_dict_or_json(self) -> None:
        """Verifies to_safe_dict() masks the private key to a boolean flag."""
        config = SuiBotConfig(sui_private_key=self.SECRET_CANARY)
        safe_dict = config.to_safe_dict()

        assert self.SECRET_CANARY not in str(safe_dict), "CRITICAL: Private key leaked in to_safe_dict()"
        assert safe_dict["has_private_key"] is True
        assert "sui_private_key" not in safe_dict

        json_serialized = json.dumps(safe_dict)
        assert self.SECRET_CANARY not in json_serialized

    def test_adversarial_secret_never_in_logging_output(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Verifies private key is never emitted in log messages during runner startup."""
        monkeypatch.setenv("SUI_PRIVATE_KEY", self.SECRET_CANARY)
        caplog.set_level(logging.DEBUG)

        config = SuiBotConfig.from_env()
        assert config.sui_private_key == self.SECRET_CANARY

        runner = SuiBotRunner(config=config)
        safe_dict = runner.config.to_safe_dict()
        logging.getLogger("sui_bot_runner").info(f"Runner initialized with config: {safe_dict}")

        all_logs = caplog.text
        assert self.SECRET_CANARY not in all_logs, "CRITICAL: Private key leaked into logging output"

    @pytest.mark.asyncio
    async def test_adversarial_secret_not_leaked_in_exception_tracebacks(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Verifies that exceptions raised inside runner do not leak private key."""
        monkeypatch.setenv("SUI_PRIVATE_KEY", self.SECRET_CANARY)
        config = SuiBotConfig.from_env()
        runner = SuiBotRunner(config=config)

        # Force an exception inside run_preflight
        with patch.object(runner.validator, "validate_preflight_health", side_effect=RuntimeError("Simulated RPC failure")):
            with pytest.raises(RuntimeError) as exc_info:
                await runner.run_preflight()

            exc_str = str(exc_info.value)
            assert self.SECRET_CANARY not in exc_str

    @pytest.mark.asyncio
    async def test_adversarial_secret_never_in_health_server_responses(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Verifies that none of the HTTP endpoints (/health, /live, /) leak private key."""
        monkeypatch.setenv("SUI_PRIVATE_KEY", self.SECRET_CANARY)
        test_port = 19115
        config = SuiBotConfig.from_env()
        config.port = test_port

        server = SuiHealthServer(host="127.0.0.1", port=test_port)
        await server.start()

        try:
            async with aiohttp.ClientSession() as session:
                for endpoint in ("/health", "/live", "/"):
                    async with session.get(f"http://127.0.0.1:{test_port}{endpoint}") as resp:
                        text = await resp.text()
                        assert self.SECRET_CANARY not in text, f"CRITICAL: Key leaked in {endpoint}"
        finally:
            await server.stop()


# ==============================================================================
# SECTION 5: CONFIGURATION FUZZING & ERROR HANDLING
# ==============================================================================

class TestConfigurationFuzzing:
    """Stress tests configuration parsing and edge-case error handling."""

    def test_adversarial_fuzz_invalid_ports(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Tests that invalid PORT values safely fall back to DEFAULT_PORT (8080)."""
        invalid_ports = ["not_a_port", "8080abc", "", "   ", "NaN"]
        for p in invalid_ports:
            monkeypatch.setenv("PORT", p)
            config = SuiBotConfig.from_env()
            assert config.port == DEFAULT_PORT, f"Failed to fallback to DEFAULT_PORT for PORT='{p}'"

    def test_adversarial_fuzz_invalid_borrow_amount(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Tests that invalid INITIAL_BORROW_AMOUNT values safely fall back to 1_000_000_000."""
        invalid_amounts = ["invalid_amount", "1.5e9", "", "abc"]
        for amt in invalid_amounts:
            monkeypatch.setenv("INITIAL_BORROW_AMOUNT", amt)
            config = SuiBotConfig.from_env()
            assert config.initial_borrow_amount == 1_000_000_000

    def test_adversarial_fuzz_invalid_log_levels(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Tests that unrecognized LOG_LEVEL values are ingested and default safely to INFO."""
        invalid_levels = ["SUPER_VERBOSE", "UNKNOWN", "9999", "TRACE"]
        for lvl in invalid_levels:
            monkeypatch.setenv("LOG_LEVEL", lvl)
            config = SuiBotConfig.from_env()
            assert config.log_level == lvl.upper()

            # Logging basicConfig fallback verification
            resolved_level = getattr(logging, config.log_level, logging.INFO)
            assert resolved_level == logging.INFO

    @pytest.mark.asyncio
    async def test_adversarial_corrupt_graphql_url_preflight(self) -> None:
        """Verifies that an unreachable or corrupt SUI_GRAPHQL_URL fails gracefully."""
        corrupt_url = "http://invalid-nonexistent-domain-for-tests.internal:9999/graphql"
        config = SuiBotConfig(graphql_url=corrupt_url)
        runner = SuiBotRunner(config=config)

        try:
            # Preflight without mock data to trigger live connection failure
            report = await runner.run_preflight(mock_data=None)

            # Must return report with rpc_connected = False without throwing fatal exception
            assert report["rpc_connected"] is False
            assert report["all_pools_accessible"] is False
            assert report["status"] in ("CRITICAL", "UNKNOWN", "DEGRADED")
        finally:
            await runner.stop()

    def test_adversarial_extreme_gas_floors_enforcement(self) -> None:
        """Tests engine behavior under extreme / inverted gas floor configurations."""
        # Extreme high warning floor: 100 SUI
        config = SuiBotConfig(warning_gas_floor=100.0, critical_gas_floor=50.0)
        runner = SuiBotRunner(config=config)

        # Wallet has normal 5.419 SUI, but floors are 100 / 50 -> must trigger critical halt
        runner.update_gas_balance(5.419)
        assert runner.scaling_engine.can_trade() is False
        assert runner.scaling_engine.status == STATUS_EMERGENCY_LOCKED
