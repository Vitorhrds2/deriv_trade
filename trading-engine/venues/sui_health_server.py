"""Lightweight Asynchronous Health Server for Sui DeepBookV3 & Cetus Arbitrage Bot.

Serves GET /health on port $PORT (default 8080) for Railway container health supervision.
Returns 200 OK with JSON payload complying with Milestone M4 specification:
- status: "HEALTHY" | "DEGRADED" | "CRITICAL"
- uptime_seconds: float
- current_tier: "TIER_1" | "TIER_2" | "TIER_3"
- borrow_amount_usdc: int
- sui_gas_balance: Optional[float] (live/synced SUI gas balance, or None if uninitialized)
- usdc_balance: Optional[float] (live/synced USDC wallet balance, or None if uninitialized)
- deep_balance: Optional[float] (live/synced DEEP wallet balance, or None if uninitialized)
- balances_synced: bool
- balances_source: str
- balances_updated_at: Optional[float]
- active_pairs: list of monitored pair names
- region: "europe-west3" (Frankfurt)
- consecutive_aborts: int
- timestamp: float
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
import time
from pathlib import Path
from typing import Any, Awaitable, Callable, Dict, List, Optional, Union

from aiohttp import web

# Ensure trading-engine root is in sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

try:
    from venues.sui_deepbook_venue import SUI_PAIRS_CONFIG
    from venues.sui_scaling_engine import (
        DEFAULT_CRITICAL_GAS_FLOOR,
        DEFAULT_WARNING_GAS_FLOOR,
        STATUS_ACTIVE,
        STATUS_COOLING_DOWN,
        STATUS_EMERGENCY_LOCKED,
        DynamicCapitalScalingEngine,
        ScalingTier,
    )
except ImportError:
    from .sui_deepbook_venue import SUI_PAIRS_CONFIG
    from .sui_scaling_engine import (
        DEFAULT_CRITICAL_GAS_FLOOR,
        DEFAULT_WARNING_GAS_FLOOR,
        STATUS_ACTIVE,
        STATUS_COOLING_DOWN,
        STATUS_EMERGENCY_LOCKED,
        DynamicCapitalScalingEngine,
        ScalingTier,
    )

logger = logging.getLogger(__name__)

# Default Constants
DEFAULT_PORT: int = 8080
DEFAULT_HOST: str = "0.0.0.0"
DEFAULT_REGION: str = "europe-west3"
ACTIVE_PAIRS: List[str] = [
    "SUI/USDC",
    "DEEP/SUI",
    "DEEP/USDC",
    "CETUS/SUI",
    "USDSUI/USDC",
    "WAL/USDC",
    "LZWBTC/USDC",
    "NS/SUI",
    "XBTC/USDC",
    "NS/USDC",
]


class SuiHealthServer:
    """Async HTTP health server for Railway deployment supervision."""

    def __init__(
        self,
        host: str = DEFAULT_HOST,
        port: Optional[int] = None,
        region: str = DEFAULT_REGION,
        scaling_engine: Optional[DynamicCapitalScalingEngine] = None,
        sui_gas_balance: Optional[float] = None,
        usdc_balance: Optional[float] = None,
        deep_balance: Optional[float] = None,
        balance_refresher: Optional[Callable[[], Awaitable[Optional[Dict[str, Any]]]]] = None,
        start_time: Optional[float] = None,
    ) -> None:
        self.host = host
        env_port = os.getenv("PORT")
        self.port = int(port if port is not None else (int(env_port) if env_port else DEFAULT_PORT))
        self.region = os.getenv("REGION", region)
        self.scaling_engine = scaling_engine
        self._custom_sui_gas_balance: Optional[float] = (
            float(sui_gas_balance) if sui_gas_balance is not None else None
        )
        self._custom_usdc_balance: Optional[float] = (
            float(usdc_balance) if usdc_balance is not None else None
        )
        self._custom_deep_balance: Optional[float] = (
            float(deep_balance) if deep_balance is not None else None
        )
        self._balance_source: str = "manual" if sui_gas_balance is not None else "uninitialized"
        self._balances_updated_at: Optional[float] = (
            time.time() if sui_gas_balance is not None else None
        )
        self._balance_refresher = balance_refresher
        self._consecutive_aborts: int = 0
        self._manual_status: Optional[str] = None
        self._custom_tier: str = "TIER_1"
        self._custom_borrow_amount: int = 1_000_000_000
        self.start_time = start_time or time.time()
        self.app: web.Application = web.Application()
        self._setup_routes()
        self.runner: Optional[web.AppRunner] = None
        self.site: Optional[web.TCPSite] = None
        self._is_running = False

    def _setup_routes(self) -> None:
        self.app.router.add_get("/health", self.handle_health)
        self.app.router.add_get("/live", self.handle_live)
        self.app.router.add_get("/", self.handle_root)

    def set_balance_refresher(
        self,
        refresher: Optional[Callable[[], Awaitable[Optional[Dict[str, Any]]]]],
    ) -> None:
        """Attach an optional async callback used by GET /health?refresh=1."""
        self._balance_refresher = refresher

    def update_wallet_balances(
        self,
        sui_balance: float,
        usdc_balance: Optional[float] = None,
        deep_balance: Optional[float] = None,
        source: str = "onchain_graphql",
        updated_at: Optional[float] = None,
    ) -> None:
        """Update tracked live SUI, USDC, and DEEP wallet balances."""
        ts = float(updated_at) if updated_at is not None else time.time()
        sui_val = float(sui_balance)
        self._custom_sui_gas_balance = sui_val
        if usdc_balance is not None:
            self._custom_usdc_balance = float(usdc_balance)
        if deep_balance is not None:
            self._custom_deep_balance = float(deep_balance)
        self._balance_source = source
        self._balances_updated_at = ts
        if self.scaling_engine is not None:
            self.scaling_engine.state.sui_gas_balance = sui_val
            if usdc_balance is not None:
                self.scaling_engine.state.usdc_balance = float(usdc_balance)
            if deep_balance is not None:
                self.scaling_engine.state.deep_balance = float(deep_balance)
            self.scaling_engine.state.balances_synced = True
            self.scaling_engine.state.balances_updated_at = ts

    def set_gas_balance(self, balance: float) -> None:
        """Update tracked SUI gas balance."""
        self.update_wallet_balances(sui_balance=float(balance), source="manual")

    def set_consecutive_aborts(self, aborts: int) -> None:
        """Update tracked consecutive aborts count."""
        self._consecutive_aborts = int(aborts)
        if self.scaling_engine is not None:
            self.scaling_engine.state.consecutive_aborts = int(aborts)

    def set_status(self, status: str) -> None:
        """Manually override status ("HEALTHY", "DEGRADED", "CRITICAL")."""
        self._manual_status = status

    def set_tier(self, tier_name: str, borrow_amount: int) -> None:
        """Manually update scaling tier and borrow amount."""
        self._custom_tier = tier_name
        self._custom_borrow_amount = int(borrow_amount)

    def get_health_data(self) -> Dict[str, Any]:
        """Calculates and constructs the health payload adhering to M4 specification."""
        now = time.time()
        uptime = round(now - self.start_time, 2)

        # 1. Resolve tracked SUI, USDC, and DEEP balances (never hardcoded)
        engine_state = self.scaling_engine.state if self.scaling_engine is not None else None
        engine_updated_at = getattr(engine_state, "balances_updated_at", None) if engine_state is not None else None
        engine_synced = bool(getattr(engine_state, "balances_synced", False)) if engine_state is not None else False
        engine_has_legacy_gas = bool(engine_state is not None and engine_state.sui_gas_balance > 0)
        engine_available = engine_state is not None and (engine_synced or engine_has_legacy_gas)
        server_available = self._custom_sui_gas_balance is not None

        use_engine = False
        if engine_available and not server_available:
            use_engine = True
        elif engine_available and server_available:
            if (engine_updated_at or 0.0) >= (self._balances_updated_at or 0.0):
                use_engine = True

        gas_balance: Optional[float]
        usdc_balance: Optional[float]
        deep_balance: Optional[float]

        if use_engine and engine_state is not None:
            gas_balance = float(engine_state.sui_gas_balance)
            usdc_balance = (
                float(engine_state.usdc_balance)
                if engine_synced
                else self._custom_usdc_balance
            )
            deep_balance = (
                float(engine_state.deep_balance)
                if engine_synced
                else self._custom_deep_balance
            )
            balances_synced = True
            balances_source = (
                self._balance_source
                if self._balances_updated_at is not None and engine_updated_at == self._balances_updated_at
                else "scaling_engine"
            )
            balances_updated_at = engine_updated_at
        elif server_available:
            gas_balance = float(self._custom_sui_gas_balance)
            usdc_balance = self._custom_usdc_balance
            if usdc_balance is None and engine_state is not None and engine_synced:
                usdc_balance = float(engine_state.usdc_balance)
            deep_balance = self._custom_deep_balance
            if deep_balance is None and engine_state is not None and engine_synced:
                deep_balance = float(engine_state.deep_balance)
            balances_synced = True
            balances_source = self._balance_source
            balances_updated_at = self._balances_updated_at
        else:
            gas_balance = None
            usdc_balance = None
            deep_balance = None
            balances_synced = False
            balances_source = "uninitialized"
            balances_updated_at = None

        # 2. Resolve Tier and Borrow Amount
        if self.scaling_engine is not None:
            tier_name = self.scaling_engine.current_tier.name
            borrow_amount = self.scaling_engine.flash_borrow_amount
            consecutive_aborts = self.scaling_engine.state.consecutive_aborts
            engine_status = self.scaling_engine.status
            gas_warning = self.scaling_engine.state.gas_warning
            accumulated_profit = self.scaling_engine.state.accumulated_net_profit_usdc
            successful_trades = self.scaling_engine.state.successful_trades
        else:
            tier_name = self._custom_tier
            borrow_amount = self._custom_borrow_amount
            consecutive_aborts = self._consecutive_aborts
            engine_status = STATUS_ACTIVE
            gas_warning = (
                gas_balance < DEFAULT_WARNING_GAS_FLOOR
                if gas_balance is not None
                else True
            )
            accumulated_profit = 0.0
            successful_trades = 0

        # 3. Determine Overall Health Status: HEALTHY | DEGRADED | CRITICAL
        if self._manual_status is not None:
            overall_status = self._manual_status
        elif (
            (gas_balance is not None and gas_balance < DEFAULT_CRITICAL_GAS_FLOOR)
            or consecutive_aborts >= 5
            or engine_status == STATUS_EMERGENCY_LOCKED
        ):
            overall_status = "CRITICAL"
        elif (
            gas_balance is None
            or gas_balance < DEFAULT_WARNING_GAS_FLOOR
            or consecutive_aborts >= 3
            or engine_status == STATUS_COOLING_DOWN
            or gas_warning
        ):
            overall_status = "DEGRADED"
        else:
            overall_status = "HEALTHY"

        return {
            "status": overall_status,
            "uptime_seconds": uptime,
            "current_tier": tier_name,
            "borrow_amount_usdc": borrow_amount,
            "sui_gas_balance": round(gas_balance, 4) if gas_balance is not None else None,
            "usdc_balance": round(usdc_balance, 4) if usdc_balance is not None else None,
            "deep_balance": round(deep_balance, 4) if deep_balance is not None else None,
            "balances_synced": balances_synced,
            "balances_source": balances_source,
            "balances_updated_at": round(balances_updated_at, 3) if balances_updated_at is not None else None,
            "active_pairs": list(ACTIVE_PAIRS),
            "region": self.region,
            "consecutive_aborts": consecutive_aborts,
            "timestamp": now,
            "accumulated_profit_usdc": round(accumulated_profit, 2),
            "successful_trades": successful_trades,
        }

    async def handle_health(self, request: web.Request) -> web.Response:
        """GET /health handler (supports optional ?refresh=1 when balance_refresher is attached)."""
        refresh_param = request.query.get("refresh", "").strip().lower()
        if refresh_param in ("1", "true", "yes") and self._balance_refresher is not None:
            try:
                refreshed = await self._balance_refresher()
                if isinstance(refreshed, dict) and "sui" in refreshed:
                    self.update_wallet_balances(
                        sui_balance=float(refreshed.get("sui", 0.0)),
                        usdc_balance=float(refreshed["usdc"]) if "usdc" in refreshed else None,
                        deep_balance=float(refreshed["deep"]) if "deep" in refreshed else None,
                        source=str(refreshed.get("source", "onchain_graphql_refresh")),
                    )
            except Exception as exc:
                logger.warning(f"On-demand /health balance refresh failed: {exc}")
        data = self.get_health_data()
        return web.json_response(data, status=200)

    async def handle_live(self, request: web.Request) -> web.Response:
        """GET /live liveness probe handler."""
        return web.json_response({"live": True, "uptime": round(time.time() - self.start_time, 2)}, status=200)

    async def handle_root(self, request: web.Request) -> web.Response:
        """GET / root handler returning status summary."""
        data = self.get_health_data()
        service_name = os.getenv("SERVICE_NAME", "sui-deepbook-cetus-bot")
        summary = {
            "service": service_name,
            "status": data["status"],
            "tier": data["current_tier"],
            "region": data["region"],
            "uptime_seconds": data["uptime_seconds"],
            "endpoints": ["/health", "/live"],
        }
        return web.json_response(summary, status=200)

    async def start(self) -> None:
        """Starts the aiohttp web server asynchronously."""
        if self._is_running:
            return
        self.runner = web.AppRunner(self.app)
        await self.runner.setup()
        self.site = web.TCPSite(self.runner, self.host, self.port)
        await self.site.start()
        self._is_running = True
        logger.info(f"SuiHealthServer listening on http://{self.host}:{self.port} (Region: {self.region})")

    async def stop(self) -> None:
        """Gracefully stops the health server."""
        if not self._is_running:
            return
        if self.site is not None:
            await self.site.stop()
            self.site = None
        if self.runner is not None:
            await self.runner.cleanup()
            self.runner = None
        self._is_running = False
        logger.info("SuiHealthServer stopped successfully.")

    @property
    def is_running(self) -> bool:
        return self._is_running


async def run_standalone_health_server() -> None:
    """Entry point for standalone execution backed by live GraphQL balance polling."""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    port = int(os.getenv("PORT", str(DEFAULT_PORT)))

    try:
        from venues.sui_deepbook_venue import SuiGraphQLClient
    except ImportError:
        from .sui_deepbook_venue import SuiGraphQLClient

    graphql_client = SuiGraphQLClient()
    op_addr = graphql_client.operator_address

    async def _refresh_standalone_balances() -> Optional[Dict[str, Any]]:
        if not op_addr:
            return None
        balances = await graphql_client.get_wallet_balances(op_addr)
        return {
            "sui": float(balances.get("sui", 0.0)),
            "usdc": float(balances.get("usdc", 0.0)),
            "deep": float(balances.get("deep", 0.0)),
            "source": "onchain_graphql_standalone",
        }

    server = SuiHealthServer(port=port, balance_refresher=_refresh_standalone_balances)

    async def _sync_once() -> None:
        try:
            refreshed = await _refresh_standalone_balances()
            if refreshed is not None:
                server.update_wallet_balances(
                    sui_balance=refreshed["sui"],
                    usdc_balance=refreshed["usdc"],
                    deep_balance=refreshed["deep"],
                    source=refreshed["source"],
                )
        except Exception as exc:
            logger.warning(f"Standalone health server balance sync failed: {exc}")

    await _sync_once()
    await server.start()
    logger.info(f"Health server running on port {port}. Press Ctrl+C to stop.")
    try:
        while True:
            await asyncio.sleep(15.0)
            await _sync_once()
    except (asyncio.CancelledError, KeyboardInterrupt):
        pass
    finally:
        await server.stop()
        await graphql_client.close()


if __name__ == "__main__":
    try:
        asyncio.run(run_standalone_health_server())
    except (KeyboardInterrupt, SystemExit):
        sys.exit(0)
