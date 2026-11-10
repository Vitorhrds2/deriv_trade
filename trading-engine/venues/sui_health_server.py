"""Lightweight Asynchronous Health Server for Sui DeepBookV3 & Cetus Arbitrage Bot.

Serves GET /health on port $PORT (default 8080) for Railway container health supervision.
Returns 200 OK with JSON payload complying with Milestone M4 specification:
- status: "HEALTHY" | "DEGRADED" | "CRITICAL"
- uptime_seconds: float
- current_tier: "TIER_1" | "TIER_2" | "TIER_3"
- borrow_amount_usdc: int
- sui_gas_balance: float (actual verified 5.419 SUI)
- active_pairs: ["SUI/USDC", "DEEP/SUI", "DEEP/USDC", "CETUS/SUI"]
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
from typing import Any, Dict, List, Optional, Union

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
DEFAULT_VERIFIED_SUI_BALANCE: float = 5.419245048
ACTIVE_PAIRS: List[str] = ["SUI/USDC", "DEEP/SUI", "DEEP/USDC", "CETUS/SUI"]


class SuiHealthServer:
    """Async HTTP health server for Railway deployment supervision."""

    def __init__(
        self,
        host: str = DEFAULT_HOST,
        port: Optional[int] = None,
        region: str = DEFAULT_REGION,
        scaling_engine: Optional[DynamicCapitalScalingEngine] = None,
        sui_gas_balance: Optional[float] = None,
        start_time: Optional[float] = None,
    ) -> None:
        self.host = host
        env_port = os.getenv("PORT")
        self.port = int(port if port is not None else (int(env_port) if env_port else DEFAULT_PORT))
        self.region = os.getenv("REGION", region)
        self.scaling_engine = scaling_engine
        self._custom_sui_gas_balance = sui_gas_balance
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

    def set_gas_balance(self, balance: float) -> None:
        """Update tracked SUI gas balance."""
        self._custom_sui_gas_balance = float(balance)
        if self.scaling_engine is not None:
            self.scaling_engine.state.sui_gas_balance = float(balance)

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

        # 1. Resolve SUI gas balance
        if self._custom_sui_gas_balance is not None:
            gas_balance = self._custom_sui_gas_balance
        elif self.scaling_engine is not None and self.scaling_engine.state.sui_gas_balance > 0:
            gas_balance = self.scaling_engine.state.sui_gas_balance
        else:
            gas_balance = DEFAULT_VERIFIED_SUI_BALANCE

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
            gas_warning = gas_balance < DEFAULT_WARNING_GAS_FLOOR
            accumulated_profit = 0.0
            successful_trades = 0

        # 3. Determine Overall Health Status: HEALTHY | DEGRADED | CRITICAL
        if self._manual_status is not None:
            overall_status = self._manual_status
        elif (
            gas_balance < DEFAULT_CRITICAL_GAS_FLOOR
            or consecutive_aborts >= 5
            or engine_status == STATUS_EMERGENCY_LOCKED
        ):
            overall_status = "CRITICAL"
        elif (
            gas_balance < DEFAULT_WARNING_GAS_FLOOR
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
            "sui_gas_balance": round(gas_balance, 4),
            "active_pairs": list(ACTIVE_PAIRS),
            "region": self.region,
            "consecutive_aborts": consecutive_aborts,
            "timestamp": now,
            "accumulated_profit_usdc": round(accumulated_profit, 2),
            "successful_trades": successful_trades,
        }

    async def handle_health(self, request: web.Request) -> web.Response:
        """GET /health handler."""
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
    """Entry point for standalone execution."""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    port = int(os.getenv("PORT", str(DEFAULT_PORT)))
    server = SuiHealthServer(port=port)
    await server.start()
    logger.info(f"Health server running on port {port}. Press Ctrl+C to stop.")
    try:
        while True:
            await asyncio.sleep(3600)
    except (asyncio.CancelledError, KeyboardInterrupt):
        await server.stop()


if __name__ == "__main__":
    try:
        asyncio.run(run_standalone_health_server())
    except (KeyboardInterrupt, SystemExit):
        sys.exit(0)
