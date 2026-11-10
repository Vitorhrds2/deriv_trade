"""Production Runtime Orchestrator for Continuous Arbitrage Execution on Railway.

Coordinates:
1. Configuration ingestion strictly via environment variables (zero hardcoded secrets).
2. Pre-flight healthcheck via SuiPTBPreflightValidator.validate_preflight_health().
3. Concurrent background HTTP health server on $PORT for Railway supervision.
4. Continuous multi-pair scanning loop across SUI/USDC, DEEP/SUI, DEEP/USDC, CETUS/SUI:
   - DynamicCapitalScalingEngine tranche sizing (1k -> 5k -> 10k USDC).
   - Move VM dry-run PTB simulation before live execution.
   - Safety floors: 1.5 SUI throttled scan, 0.5 SUI critical halt.
   - Drawdown circuit breakers: 3-abort tier demote/cooldown, 5-abort emergency lock.
5. Graceful signal handling (SIGINT, SIGTERM) with clean session shutdown.
"""

from __future__ import annotations

import asyncio
import logging
import os
import signal
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

# Ensure trading-engine root is in sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

try:
    from venues.sui_deepbook_venue import (
        CIRCLE_USDC_TYPE,
        SUI_COIN_TYPE,
        SUI_GRAPHQL_MAINNET,
        SUI_PAIRS_CONFIG,
        SuiGraphQLClient,
    )
    from venues.sui_health_server import DEFAULT_PORT, DEFAULT_REGION, ACTIVE_PAIRS, SuiHealthServer
    from venues.sui_ptb_validator import DEFAULT_PAIR_BASE_PRICES, SuiPTBPreflightValidator
    from venues.sui_scaling_engine import (
        DEFAULT_CRITICAL_GAS_FLOOR,
        DEFAULT_WARNING_GAS_FLOOR,
        OPERATOR_WALLET_ADDRESS,
        STATUS_ACTIVE,
        STATUS_COOLING_DOWN,
        STATUS_EMERGENCY_LOCKED,
        DynamicCapitalScalingEngine,
        ScalingTier,
        SuiBalanceTracker,
    )
except ImportError:
    from .sui_deepbook_venue import (
        CIRCLE_USDC_TYPE,
        SUI_COIN_TYPE,
        SUI_GRAPHQL_MAINNET,
        SUI_PAIRS_CONFIG,
        SuiGraphQLClient,
    )
    from .sui_health_server import DEFAULT_PORT, DEFAULT_REGION, ACTIVE_PAIRS, SuiHealthServer
    from .sui_ptb_validator import DEFAULT_PAIR_BASE_PRICES, SuiPTBPreflightValidator
    from .sui_scaling_engine import (
        DEFAULT_CRITICAL_GAS_FLOOR,
        DEFAULT_WARNING_GAS_FLOOR,
        OPERATOR_WALLET_ADDRESS,
        STATUS_ACTIVE,
        STATUS_COOLING_DOWN,
        STATUS_EMERGENCY_LOCKED,
        DynamicCapitalScalingEngine,
        ScalingTier,
        SuiBalanceTracker,
    )

logger = logging.getLogger("sui_bot_runner")


@dataclass
class SuiBotConfig:
    """Runtime configuration parsed exclusively from environment variables."""

    graphql_url: str = SUI_GRAPHQL_MAINNET
    operator_address: str = OPERATOR_WALLET_ADDRESS
    initial_borrow_amount: int = 1_000_000_000
    port: int = DEFAULT_PORT
    log_level: str = "INFO"
    region: str = DEFAULT_REGION
    balance_manager_id: str = "0x0000000000000000000000000000000000000000000000000000000000000001"
    dry_run_mode: bool = True
    scan_interval_seconds: float = 1.0
    throttled_scan_interval_seconds: float = 3.0
    warning_gas_floor: float = DEFAULT_WARNING_GAS_FLOOR
    critical_gas_floor: float = DEFAULT_CRITICAL_GAS_FLOOR
    max_scan_cycles: Optional[int] = None
    sui_private_key: Optional[str] = field(default=None, repr=False)

    @classmethod
    def from_env(cls) -> SuiBotConfig:
        """Constructs configuration from environment variables with safe defaults."""
        graphql_url = (
            os.getenv("SUI_GRAPHQL_URL")
            or os.getenv("SUI_RPC_URL")
            or SUI_GRAPHQL_MAINNET
        )
        operator_address = (
            os.getenv("OPERATOR_ADDRESS")
            or os.getenv("SUI_WALLET_ADDRESS")
            or OPERATOR_WALLET_ADDRESS
        )
        
        raw_borrow = (
            os.getenv("INITIAL_BORROW_AMOUNT")
            or os.getenv("FLASH_BORROW_AMOUNT")
            or "1000000000"
        )
        try:
            initial_borrow_amount = int(raw_borrow)
        except ValueError:
            initial_borrow_amount = 1_000_000_000

        raw_port = os.getenv("PORT", str(DEFAULT_PORT))
        try:
            port = int(raw_port)
        except ValueError:
            port = DEFAULT_PORT

        log_level = os.getenv("LOG_LEVEL", "INFO").upper()
        region = os.getenv("REGION", DEFAULT_REGION)
        balance_manager_id = (
            os.getenv("DEEPBOOK_BALANCE_MANAGER_ID")
            or os.getenv("BALANCE_MANAGER_ID")
            or os.getenv("SUI_DEEPBOOK_BALANCE_MANAGER_ID")
            or "0x0000000000000000000000000000000000000000000000000000000000000001"
        )

        dry_run_str = os.getenv("DRY_RUN_MODE", "true").lower()
        dry_run_mode = dry_run_str in ("true", "1", "yes")

        scan_interval = float(os.getenv("SCAN_INTERVAL_SECONDS", "1.0"))
        throttled_interval = float(os.getenv("THROTTLED_SCAN_INTERVAL_SECONDS", "3.0"))
        warning_floor = float(os.getenv("WARNING_GAS_FLOOR", str(DEFAULT_WARNING_GAS_FLOOR)))
        critical_floor = float(os.getenv("CRITICAL_GAS_FLOOR", str(DEFAULT_CRITICAL_GAS_FLOOR)))

        raw_max_cycles = os.getenv("MAX_SCAN_CYCLES")
        max_scan_cycles = int(raw_max_cycles) if raw_max_cycles else None

        sui_private_key = (
            os.getenv("SUI_PRIVATE_KEY")
            or os.getenv("SUI_SECRET_KEY")
        )

        return cls(
            graphql_url=graphql_url,
            operator_address=operator_address,
            initial_borrow_amount=initial_borrow_amount,
            port=port,
            log_level=log_level,
            region=region,
            balance_manager_id=balance_manager_id,
            dry_run_mode=dry_run_mode,
            scan_interval_seconds=scan_interval,
            throttled_scan_interval_seconds=throttled_interval,
            warning_gas_floor=warning_floor,
            critical_gas_floor=critical_floor,
            max_scan_cycles=max_scan_cycles,
            sui_private_key=sui_private_key,
        )

    def to_safe_dict(self) -> Dict[str, Any]:
        """Returns non-sensitive configuration parameters for logging and inspection."""
        return {
            "graphql_url": self.graphql_url,
            "operator_address": self.operator_address,
            "initial_borrow_amount": self.initial_borrow_amount,
            "port": self.port,
            "log_level": self.log_level,
            "region": self.region,
            "balance_manager_id": self.balance_manager_id,
            "dry_run_mode": self.dry_run_mode,
            "scan_interval_seconds": self.scan_interval_seconds,
            "throttled_scan_interval_seconds": self.throttled_scan_interval_seconds,
            "warning_gas_floor": self.warning_gas_floor,
            "critical_gas_floor": self.critical_gas_floor,
            "has_private_key": self.sui_private_key is not None and len(self.sui_private_key) > 0,
        }


class SuiBotRunner:
    """Production runtime orchestrator for Sui DeepBookV3 & Cetus arbitrage."""

    def __init__(
        self,
        config: Optional[SuiBotConfig] = None,
        validator: Optional[SuiPTBPreflightValidator] = None,
        scaling_engine: Optional[DynamicCapitalScalingEngine] = None,
        health_server: Optional[SuiHealthServer] = None,
    ) -> None:
        self.config = config or SuiBotConfig.from_env()
        self.scaling_engine = scaling_engine or DynamicCapitalScalingEngine(
            warning_gas_floor=self.config.warning_gas_floor,
            critical_gas_floor=self.config.critical_gas_floor,
        )
        self.validator = validator or SuiPTBPreflightValidator(
            graphql_url=self.config.graphql_url,
            operator_address=self.config.operator_address,
            balance_manager_id=self.config.balance_manager_id,
            warning_gas_floor=self.config.warning_gas_floor,
            critical_gas_floor=self.config.critical_gas_floor,
            scaling_engine=self.scaling_engine,
        )
        self.health_server = health_server or SuiHealthServer(
            port=self.config.port,
            region=self.config.region,
            scaling_engine=self.scaling_engine,
        )

        # Propagate private key to venue for live on-chain execution if available
        if self.config.sui_private_key and not getattr(self.validator.venue, "private_key", None):
            self.validator.venue.private_key = self.config.sui_private_key

        self.shutdown_event = asyncio.Event()
        self.is_running = False
        self.completed_cycles: int = 0
        self.total_opportunities_found: int = 0
        self.total_executions_attempted: int = 0
        self.latest_preflight_report: Optional[Dict[str, Any]] = None
        self._cached_market_spreads: Optional[Dict[str, Dict[str, Any]]] = None
        self._last_spread_poll_time: float = 0.0

    def setup_signal_handlers(self) -> None:
        """Installs SIGINT and SIGTERM handlers for graceful shutdown."""
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(sig, lambda s=sig: self._handle_signal(s))
            except NotImplementedError:
                signal.signal(sig, lambda s, f: self._handle_signal(sig))

    def _handle_signal(self, sig: signal.Signals) -> None:
        """Handles termination signals gracefully."""
        sig_name = sig.name if hasattr(sig, "name") else str(sig)
        logger.info(f"Received termination signal {sig_name}. Initiating graceful shutdown...")
        self.shutdown_event.set()

    def update_gas_balance(self, sui_balance: float) -> None:
        """Updates gas balance across engine and health server."""
        self.scaling_engine.update_from_wallet_balances(usdc_balance=0.0, sui_balance=sui_balance)
        self.health_server.set_gas_balance(sui_balance)

    async def run_preflight(self, mock_data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Executes pre-flight healthcheck validating GraphQL RPC and wallet gas runway."""
        logger.info(f"Initiating pre-flight healthcheck against {self.config.graphql_url}...")
        report = await self.validator.validate_preflight_health(mock_data=mock_data)
        self.latest_preflight_report = report

        sui_balance = float(report.get("sui_balance", 0.0) if isinstance(report, dict) else getattr(report, "sui_balance", 0.0))
        status = report.get("status") if isinstance(report, dict) else getattr(report, "status", "UNKNOWN")
        pools_ok = report.get("all_pools_accessible") if isinstance(report, dict) else getattr(report, "all_pools_accessible", False)
        gas_status = report.get("gas_status") if isinstance(report, dict) else getattr(report, "gas_status", "UNKNOWN")

        # Update scaling engine gas balance from preflight check
        if sui_balance > 0:
            self.update_gas_balance(sui_balance)

        logger.info(
            f"Pre-flight health result: status={status}, "
            f"SUI balance={sui_balance:.4f} SUI, "
            f"all_pools_accessible={pools_ok}, "
            f"gas_status={gas_status}"
        )
        return report

    async def poll_market_spreads(self) -> Dict[str, Dict[str, Any]]:
        """Queries live pool prices from Sui GraphQL and computes spreads across 4 pairs.
        
        Falls back cleanly to spread_bps=0.0 when offline, during unit testing, or if RPC fails,
        ensuring 100% test compatibility.
        """
        fallback_spreads: Dict[str, Dict[str, Any]] = {
            pair: {
                "cetus_price": DEFAULT_PAIR_BASE_PRICES.get(pair, 2.0),
                "deepbook_price": DEFAULT_PAIR_BASE_PRICES.get(pair, 2.0),
                "spread_bps": 0.0,
                "source": "fallback",
            }
            for pair in ACTIVE_PAIRS
        }

        # Check if GraphQL client is available
        graphql_client = getattr(self.validator, "graphql_client", None)
        if graphql_client is None:
            return fallback_spreads

        # Short TTL cache (0.5s) to prevent spamming RPC in rapid loops/tests
        now = time.time()
        if self._cached_market_spreads:
            if (now - self._last_spread_poll_time) < 0.5:
                return self._cached_market_spreads

        try:
            spreads = await asyncio.wait_for(
                graphql_client.query_live_market_spreads(),
                timeout=1.5,
            )
            if spreads and len(spreads) == len(ACTIVE_PAIRS):
                self._cached_market_spreads = spreads
                self._last_spread_poll_time = now
                return spreads
        except Exception as e:
            logger.debug(f"Live market spread polling fallback to 0.0: {e}")

        self._cached_market_spreads = fallback_spreads
        self._last_spread_poll_time = now
        return fallback_spreads

    async def scan_once(self) -> List[Dict[str, Any]]:
        """Executes a single scanning pass across all 4 configured trading pairs."""
        results: List[Dict[str, Any]] = []

        # 1. Check if trading is allowed by safety guardrails
        if not self.scaling_engine.can_trade():
            status = self.scaling_engine.status
            logger.warning(f"Scan cycle skipped: Engine status is {status} (can_trade=False)")
            return results

        # 2. Query live market prices and spreads across 4 pairs
        market_spreads = await self.poll_market_spreads()
        sui_spot = market_spreads.get("SUI/USDC", {}).get("cetus_price", 2.0)

        # 3. Iterate through 4 configured pairs
        for pair_name in ACTIVE_PAIRS:
            if self.shutdown_event.is_set():
                break

            pair_market = market_spreads.get(pair_name, {})
            spread_bps = float(pair_market.get("spread_bps", 0.0))
            base_price = pair_market.get("cetus_price")
            deepbook_price = pair_market.get("deepbook_price", base_price)
            bid_depth_quote = pair_market.get("bid_depth_quote")

            # Dynamic Depth-Aware borrow sizing: caps borrow to 85% of L1 book depth to eliminate depth slippage
            borrow_amount = self.scaling_engine.get_current_borrow_amount(
                pair_name=pair_name,
                sui_spot_price=sui_spot,
                max_depth_quote=bid_depth_quote,
            )
            
            # 4. Structural validation of 8-step atomic PTB
            ptb_validation = self.validator.validate_atomic_ptb_generation(
                pair_name=pair_name,
                borrow_amount=borrow_amount,
            )
            is_valid = ptb_validation.get("valid", False) if isinstance(ptb_validation, dict) else getattr(ptb_validation, "valid", False)
            if not is_valid:
                errors = ptb_validation.get("errors") if isinstance(ptb_validation, dict) else getattr(ptb_validation, "errors", [])
                logger.error(f"PTB generation invalid for {pair_name}: {errors}")
                continue

            # 5. Move VM simulation with live spread and price
            dry_run = self.validator.simulate_ptb_dry_run(
                pair_name=pair_name,
                borrow_amount=borrow_amount,
                spread_bps=spread_bps,
                base_price=base_price,
            )

            status = dry_run.get("status") if isinstance(dry_run, dict) else getattr(dry_run, "status", "ABORTED")
            net_profit = dry_run.get("net_profit", 0.0) if isinstance(dry_run, dict) else getattr(dry_run, "net_profit", 0.0)
            gas_cost_sui = dry_run.get("gas_cost_sui", 0.002) if isinstance(dry_run, dict) else getattr(dry_run, "gas_cost_sui", 0.002)
            zero_leg_risk_preserved = dry_run.get("zero_leg_risk_preserved", True) if isinstance(dry_run, dict) else getattr(dry_run, "zero_leg_risk_preserved", True)

            # Convert quote currency net profit to USD equivalent
            is_sui_quote = pair_name.endswith("/SUI") or pair_name in ("DEEP/SUI", "CETUS/SUI")
            net_profit_usd = (net_profit * sui_spot) if is_sui_quote else net_profit

            # 6. Arbitrage Execution Handling (DRY_RUN_MODE vs Live)
            # Require at least $0.05 expected net profit (~30x Sui gas cost of ~$0.0016)
            # to buffer against pool price impact while executing viable micro-arbitrages
            is_profitable = (status == "SUCCESS" and net_profit_usd >= 0.05)
            execution_status = "SIMULATED"

            if is_profitable:
                self.total_opportunities_found += 1
                if not self.config.dry_run_mode:
                    logger.info(
                        f"LIVE ARBITRAGE TRIGGER: Executing PTB for {pair_name} | "
                        f"Borrow: {borrow_amount} | Spread: {spread_bps:+.1f} bps | Expected Net Profit: ${net_profit_usd:.2f} (native: {net_profit:.4f})"
                    )
                    self.total_executions_attempted += 1
                    try:
                        order_params = {
                            "symbol": pair_name,
                            "side": "BUY",
                            "size": borrow_amount,
                            "price": dry_run.get("deepbook_bid_px", deepbook_price),
                            "amm_price": dry_run.get("amm_swap_out_px", base_price),
                            "is_arb_ptb": True,
                            "live_onchain": bool(
                                self.config.sui_private_key
                                and self.config.sui_private_key.startswith("suiprivkey1")
                            ),
                        }
                        exec_res = await self.validator.venue.submit_order(order_params)
                        if exec_res.status == "FILLED":
                            execution_status = "EXECUTED"
                            logger.info(f"Live PTB executed successfully for {pair_name}: order_id={exec_res.order_id}")
                            self.scaling_engine.record_trade_success(profit_usdc=net_profit_usd)
                        else:
                            execution_status = "REJECTED"
                            logger.info(f"Live PTB pre-flight simulation rejected for {pair_name} (0 gas cost): order_id={exec_res.order_id}")
                            # Only penalize circuit breaker if an actual on-chain broadcast failed or unexpected rejection occurred
                            if not exec_res.order_id.startswith("PTB-SIM-REVERT"):
                                self.scaling_engine.record_trade_abort()
                    except Exception as e:
                        execution_status = "ERROR"
                        logger.error(f"Live PTB execution error for {pair_name}: {e}")
                        self.scaling_engine.record_trade_abort()
                else:
                    logger.info(
                        f"[DRY_RUN_MODE=true] Arbitrage opportunity simulated on {pair_name} | "
                        f"Spread: {spread_bps:+.1f} bps | Simulated Net Profit: ${net_profit_usd:.2f} (Execution skipped)"
                    )

            result_entry = {
                "pair": pair_name,
                "borrow_amount": borrow_amount,
                "tier": self.scaling_engine.current_tier.name,
                "status": status,
                "net_profit": net_profit,
                "net_profit_usd": net_profit_usd,
                "gas_cost_sui": gas_cost_sui,
                "zero_leg_risk_preserved": zero_leg_risk_preserved,
                "spread_bps": spread_bps,
                "cetus_price": base_price if base_price is not None else 0.0,
                "deepbook_price": deepbook_price if deepbook_price is not None else 0.0,
                "execution_status": execution_status,
            }
            results.append(result_entry)

        # 7. Informative cycle summary line for Railway runtime logs
        logger.info(
            f"Scan pass completed ({len(results)} pairs): "
            + " | ".join(
                f"{r['pair']}: Cetus={r['cetus_price']:.4f} DB={r['deepbook_price']:.4f} "
                f"spread={r['spread_bps']:+.1f}bps ({r['status']})"
                for r in results
            )
        )

        return results

    async def run_scan_loop(self) -> None:
        """Continuous execution loop scanning spreads and monitoring gas floors."""
        logger.info("Entering continuous arbitrage scanning loop...")
        self.is_running = True

        while not self.shutdown_event.is_set():
            self.completed_cycles += 1

            try:
                cycle_results = await self.scan_once()
                logger.debug(f"Cycle {self.completed_cycles} completed with {len(cycle_results)} pair evaluations.")
            except Exception as e:
                logger.error(f"Error in scan cycle {self.completed_cycles}: {e}", exc_info=True)

            # Check termination criteria
            if self.config.max_scan_cycles and self.completed_cycles >= self.config.max_scan_cycles:
                logger.info(f"Reached max_scan_cycles limit ({self.config.max_scan_cycles}). Halting loop.")
                break

            # Dynamic scan rate throttling based on gas runway
            is_warning = self.scaling_engine.state.gas_warning or (
                self.scaling_engine.state.sui_gas_balance > 0
                and self.scaling_engine.state.sui_gas_balance < self.config.warning_gas_floor
            )
            sleep_duration = (
                self.config.throttled_scan_interval_seconds
                if is_warning
                else self.config.scan_interval_seconds
            )

            # Responsive sleep honoring shutdown_event
            try:
                await asyncio.wait_for(self.shutdown_event.wait(), timeout=sleep_duration)
                break
            except asyncio.TimeoutError:
                pass

        self.is_running = False
        logger.info(f"Scanning loop terminated after {self.completed_cycles} cycles.")

    async def start(self, mock_preflight: Optional[Dict[str, Any]] = None) -> None:
        """Main startup sequence: starts health server, runs preflight, and enters scan loop."""
        logger.info(f"Starting SuiBotRunner (Region: {self.config.region}, Port: {self.config.port})...")
        logger.info(f"Config: {self.config.to_safe_dict()}")

        # 1. Setup graceful signal handlers
        self.setup_signal_handlers()

        # 2. Launch background HTTP health server for Railway supervision
        await self.health_server.start()
        logger.info("Health server background supervisor started successfully.")

        # 3. Perform pre-flight healthcheck
        await self.run_preflight(mock_data=mock_preflight)

        # 4. Enter continuous scanning loop
        await self.run_scan_loop()

    async def stop(self) -> None:
        """Graceful shutdown sequence: sets event, stops health server, and closes sessions."""
        logger.info("Stopping SuiBotRunner...")
        self.shutdown_event.set()

        # Stop HTTP health server
        if self.health_server.is_running:
            await self.health_server.stop()

        # Close GraphQL client sessions
        try:
            await self.validator.graphql_client.close()
        except Exception as e:
            logger.debug(f"Error closing GraphQL client session: {e}")

        logger.info(
            f"SuiBotRunner stopped cleanly. Total cycles executed: {self.completed_cycles}, "
            f"Successful trades: {self.scaling_engine.state.successful_trades}, "
            f"Net profit: ${self.scaling_engine.state.accumulated_net_profit_usdc:.2f} USDC, "
            f"Final tier: {self.scaling_engine.current_tier.name}"
        )


async def main() -> None:
    """Production entry point for Railway container."""
    config = SuiBotConfig.from_env()
    logging.basicConfig(
        level=getattr(logging, config.log_level, logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    runner = SuiBotRunner(config=config)
    try:
        await runner.start()
    except (asyncio.CancelledError, KeyboardInterrupt):
        await runner.stop()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        sys.exit(0)
