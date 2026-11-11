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
from typing import Any, Dict, List, Optional, Tuple, Union

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
        DEFAULT_CETUS_POOL_LIQUIDITY,
        DEFAULT_CRITICAL_GAS_FLOOR,
        DEFAULT_PAIR_FEE_HURDLE_BPS,
        DEFAULT_PAIR_MAX_BORROW_USD,
        DEFAULT_PAIR_SQRT_PRICES,
        DEFAULT_WARNING_GAS_FLOOR,
        OPERATOR_WALLET_ADDRESS,
        STATUS_ACTIVE,
        STATUS_COOLING_DOWN,
        STATUS_EMERGENCY_LOCKED,
        DynamicCapitalScalingEngine,
        ScalingTier,
        SuiBalanceTracker,
        prioritize_opportunities,
        prioritize_pairs,
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
        DEFAULT_CETUS_POOL_LIQUIDITY,
        DEFAULT_CRITICAL_GAS_FLOOR,
        DEFAULT_PAIR_FEE_HURDLE_BPS,
        DEFAULT_PAIR_MAX_BORROW_USD,
        DEFAULT_PAIR_SQRT_PRICES,
        DEFAULT_WARNING_GAS_FLOOR,
        OPERATOR_WALLET_ADDRESS,
        STATUS_ACTIVE,
        STATUS_COOLING_DOWN,
        STATUS_EMERGENCY_LOCKED,
        DynamicCapitalScalingEngine,
        ScalingTier,
        SuiBalanceTracker,
        prioritize_opportunities,
        prioritize_pairs,
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
    amm_target: str = "multi"
    min_profit_usd: float = 0.035

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

        amm_target = os.getenv("AMM_TARGET", "multi").lower()
        if amm_target not in ("cetus", "turbos", "multi"):
            amm_target = "multi"

        raw_min_profit = os.getenv("MIN_PROFIT_USD", "0.035")
        try:
            min_profit_usd = float(raw_min_profit)
        except ValueError:
            min_profit_usd = 0.035

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
            amm_target=amm_target,
            min_profit_usd=min_profit_usd,
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
            "amm_target": self.amm_target,
            "min_profit_usd": self.min_profit_usd,
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

        # Resolve initial tier from config/env:
        initial_tier = ScalingTier.TIER_1
        tier_env = os.getenv("INITIAL_TIER", "").upper().strip()
        if tier_env in ("TIER_3", "3", "10000"):
            initial_tier = ScalingTier.TIER_3
        elif tier_env in ("TIER_2", "2", "5000"):
            initial_tier = ScalingTier.TIER_2
        elif tier_env in ("TIER_1", "1", "1000"):
            initial_tier = ScalingTier.TIER_1
        elif self.config.initial_borrow_amount >= 10_000_000_000:
            initial_tier = ScalingTier.TIER_3
        elif self.config.initial_borrow_amount >= 5_000_000_000:
            initial_tier = ScalingTier.TIER_2

        self.scaling_engine = scaling_engine or DynamicCapitalScalingEngine(
            initial_tier=initial_tier,
            warning_gas_floor=self.config.warning_gas_floor,
            critical_gas_floor=self.config.critical_gas_floor,
            pair_max_borrow_usd=DEFAULT_PAIR_MAX_BORROW_USD,
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
        self._cached_deep_coin: Optional[Dict[str, Any]] = None
        self._last_deep_check_ts: float = 0.0
        self._cached_live_fees: Dict[str, Dict[str, Any]] = {}
        self._last_fee_check_ts: float = 0.0

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
                "deepbook_ask": DEFAULT_PAIR_BASE_PRICES.get(pair, 2.0),
                "spread_bps": 0.0,
                "forward_spread_bps": 0.0,
                "reverse_spread_bps": 0.0,
                "best_route": "FORWARD",
                "optimal_spread_bps": 0.0,
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

    async def _refresh_live_fee_and_deep_context(
        self, market_spreads: Dict[str, Dict[str, Any]]
    ) -> Tuple[Dict[str, Dict[str, Any]], Optional[Dict[str, Any]]]:
        """Refreshes cached DeepBook V3 fee tiers and wallet Coin<DEEP> when scanning live Mainnet."""
        has_live_source = any(
            isinstance(pm, dict) and pm.get("source") == "live_graphql"
            for pm in market_spreads.values()
        )
        graphql_client = getattr(self.validator, "graphql_client", None)
        if not has_live_source or graphql_client is None:
            return {}, None

        now_ts = time.time()
        if (now_ts - self._last_fee_check_ts) >= 300.0 or not self._cached_live_fees:
            try:
                fetched_fees = await graphql_client.get_live_deepbook_fee_params()
                if isinstance(fetched_fees, dict) and fetched_fees:
                    self._cached_live_fees = fetched_fees
                    self._last_fee_check_ts = now_ts
            except Exception as e:
                logger.debug(f"Live fee parameter refresh failed: {e}")

        if (now_ts - self._last_deep_check_ts) >= 30.0:
            try:
                op_addr = getattr(self.validator.venue, "active_address", None) or getattr(
                    graphql_client, "operator_address", ""
                )
                fetched_deep = await graphql_client.get_deep_coin(op_addr)
                if (
                    isinstance(fetched_deep, dict)
                    and fetched_deep.get("address")
                    and fetched_deep.get("digest")
                    and int(fetched_deep.get("balance", 0) or 0) > 0
                ):
                    self._cached_deep_coin = fetched_deep
                else:
                    self._cached_deep_coin = None
                self._last_deep_check_ts = now_ts
            except Exception as e:
                logger.debug(f"Coin<DEEP> balance check failed: {e}")

        live_fees = self._cached_live_fees if isinstance(self._cached_live_fees, dict) else {}
        return live_fees, self._cached_deep_coin

    def _resolve_pair_fee_and_borrow(
        self,
        pair_name: str,
        target_amm: str,
        eval_spread_bps: float,
        sui_spot: float,
        base_price: Optional[float],
        depth_to_use: Optional[float],
        cetus_liq: Any,
        cetus_sqrt_p: Any,
        vault_quote_balance: int,
        live_fee_map: Dict[str, Dict[str, Any]],
        pair_deep_coin: Optional[Dict[str, Any]],
        pair_market: Dict[str, Any],
    ) -> Tuple[float, Optional[float], int, Optional[Dict[str, Any]], int]:
        """Resolves dynamic DeepBook/AMM fee hurdles, Coin<DEEP> eligibility, and optimal Q*."""
        def _calc_borrow(spread_arg: Optional[float], hurdle_arg: float) -> int:
            return self.scaling_engine.get_current_borrow_amount(
                pair_name=pair_name,
                sui_spot_price=sui_spot,
                max_depth_quote=depth_to_use,
                spread_bps=spread_arg,
                liquidity=cetus_liq,
                sqrt_price=cetus_sqrt_p,
                vault_balance=vault_quote_balance,
                fee_bps=hurdle_arg,
            )

        pair_cfg = SUI_PAIRS_CONFIG.get(pair_name)
        live_fee_info = live_fee_map.get(pair_name)
        amm_fee_bps = (
            (
                pair_cfg.turbos_fee_rate
                if (target_amm == "turbos" and pair_cfg.turbos_pool_id)
                else pair_cfg.cetus_fee_rate
            )
            * 10000.0
            if pair_cfg is not None
            else 5.0
        )

        if isinstance(live_fee_info, dict):
            taker_raw = int(live_fee_info.get("taker_fee_raw", 0) or 0)
            is_wl = bool(live_fee_info.get("whitelisted", False))
            db_deep_bps = float(live_fee_info.get("taker_fee_bps_deep", 0.0))
            db_no_deep_bps = float(live_fee_info.get("taker_fee_bps_no_deep", 0.0))
            deep_per_asset = int(live_fee_info.get("deep_per_asset", 0) or 0)
            asset_is_base = bool(live_fee_info.get("asset_is_base", False))

            if is_wl or taker_raw == 0:
                fee_hurdle = amm_fee_bps + 1.0
                borrow_amount = _calc_borrow(
                    eval_spread_bps if eval_spread_bps > fee_hurdle else None, fee_hurdle
                )
                return fee_hurdle, 0.0, borrow_amount, None, 0

            opt_hurdle = amm_fee_bps + db_deep_bps + 1.0
            if pair_deep_coin is not None and eval_spread_bps > opt_hurdle:
                opt_borrow = _calc_borrow(eval_spread_bps, opt_hurdle)
                req_deep = SuiGraphQLClient.estimate_required_deep_raw(
                    borrow_amount_quote_raw=opt_borrow,
                    taker_fee_raw=taker_raw,
                    deep_per_asset=deep_per_asset,
                    asset_is_base=asset_is_base,
                    spot_price_quote_per_base=float(base_price or 0.0),
                    base_decimals=pair_cfg.base_decimals if pair_cfg else 9,
                    quote_decimals=pair_cfg.quote_decimals if pair_cfg else 6,
                )
                if req_deep > 0 and opt_borrow > 0 and int(pair_deep_coin.get("balance", 0) or 0) >= req_deep:
                    return opt_hurdle, db_deep_bps, opt_borrow, pair_deep_coin, req_deep

            fee_hurdle = amm_fee_bps + db_no_deep_bps + 1.0
            borrow_amount = _calc_borrow(
                eval_spread_bps if eval_spread_bps > fee_hurdle else None, fee_hurdle
            )
            return fee_hurdle, db_no_deep_bps, borrow_amount, None, 0

        # Offline / unit-test deterministic fee defaults (with optional explicit deep_coin override)
        fee_hurdle = DEFAULT_PAIR_FEE_HURDLE_BPS.get(pair_name, 10.0)
        db_fee_bps: Optional[float] = None
        active_deep_coin: Optional[Dict[str, Any]] = None
        deep_fee_amount = 0
        if pair_deep_coin is not None and pair_cfg is not None and pair_cfg.deepbook_taker_fee_bps > 0:
            discounted_db = pair_cfg.deepbook_taker_fee_bps * 0.8
            fee_hurdle = fee_hurdle - (pair_cfg.deepbook_taker_fee_bps - discounted_db)
            db_fee_bps = discounted_db
            active_deep_coin = pair_deep_coin
            deep_fee_amount = int(pair_market.get("deep_fee_amount", 0) or 0)

        borrow_amount = _calc_borrow(
            eval_spread_bps if eval_spread_bps > fee_hurdle else None, fee_hurdle
        )
        return fee_hurdle, db_fee_bps, borrow_amount, active_deep_coin, deep_fee_amount

    @staticmethod
    def _compute_amm_slippage_bps(
        pair_name: str,
        borrow_amount: int,
        cetus_liq: Any,
        cetus_sqrt_p: Any,
    ) -> float:
        """Computes average CLMM execution slippage (Q / virtual_quote_reserve) in bps."""
        if borrow_amount <= 0:
            return 0.0
        pool_l = (
            float(cetus_liq)
            if cetus_liq is not None and float(cetus_liq) > 0
            else DEFAULT_CETUS_POOL_LIQUIDITY.get(pair_name, 1e12)
        )
        if cetus_sqrt_p is not None:
            if isinstance(cetus_sqrt_p, int) and cetus_sqrt_p > (1 << 32):
                sqrt_p = float(cetus_sqrt_p) / float(1 << 64)
            else:
                sqrt_p = float(cetus_sqrt_p)
        else:
            sqrt_p = DEFAULT_PAIR_SQRT_PRICES.get(pair_name, 1.0)
        if sqrt_p <= 0:
            sqrt_p = 1.0

        pair_cfg = SUI_PAIRS_CONFIG.get(pair_name)
        quote_is_coin_a = bool(pair_cfg and pair_cfg.cetus_a2b_for_quote_in)
        denom = (pool_l / sqrt_p) if quote_is_coin_a else (pool_l * sqrt_p)
        if denom <= 0:
            return 0.0
        return (float(borrow_amount) / denom) * 10000.0

    async def _await_or_shutdown(self, awaitable: Any) -> Optional[Any]:
        """Awaits ``awaitable`` unless ``self.shutdown_event`` fires first, cancelling cleanly on shutdown."""
        if self.shutdown_event.is_set():
            close = getattr(awaitable, "close", None)
            if callable(close):
                close()
            elif asyncio.isfuture(awaitable) and not awaitable.done():
                awaitable.cancel()
            return None
        work_task = asyncio.ensure_future(awaitable)
        stop_task = asyncio.create_task(self.shutdown_event.wait())
        try:
            done, _ = await asyncio.wait(
                {work_task, stop_task},
                return_when=asyncio.FIRST_COMPLETED,
            )
            if work_task in done:
                return await work_task
            work_task.cancel()
            try:
                await work_task
            except (asyncio.CancelledError, Exception):
                pass
            return None
        finally:
            if not stop_task.done():
                stop_task.cancel()
                try:
                    await stop_task
                except asyncio.CancelledError:
                    pass

    async def scan_once(self) -> List[Dict[str, Any]]:
        """Executes a single scanning pass across all configured trading pairs."""
        results: List[Dict[str, Any]] = []

        # 1. Check if trading is allowed by safety guardrails
        if not self.scaling_engine.can_trade():
            status = self.scaling_engine.status
            logger.warning(f"Scan cycle skipped: Engine status is {status} (can_trade=False)")
            return results

        # 2. Query live market prices and spreads across all active pairs
        market_spreads = await self._await_or_shutdown(self.poll_market_spreads())
        if market_spreads is None or self.shutdown_event.is_set():
            return results

        sui_spot = market_spreads.get("SUI/USDC", {}).get("cetus_price", 2.0)

        # Fetch live fee/DEEP context and DeepBook Vault Balances concurrently (cancels cleanly on shutdown)
        async def _fetch_ctx_and_vaults() -> Any:
            return await asyncio.gather(
                self._refresh_live_fee_and_deep_context(market_spreads),
                asyncio.gather(
                    *(self.validator.graphql_client.get_deepbook_vault_balances(p) for p in ACTIVE_PAIRS),
                    return_exceptions=True,
                ),
            )

        ctx_bundle = await self._await_or_shutdown(_fetch_ctx_and_vaults())
        if ctx_bundle is None or self.shutdown_event.is_set():
            return results

        (live_fee_map, deep_coin_info), vault_results = ctx_bundle
        vault_balances_map: Dict[str, Dict[str, int]] = {}
        for p_name, v_res in zip(ACTIVE_PAIRS, vault_results):
            if isinstance(v_res, dict):
                vault_balances_map[p_name] = v_res
            else:
                vault_balances_map[p_name] = {"base_balance": 0, "quote_balance": 0, "deep_balance": 0}

        # 3. Iterate through all configured pairs
        pair_candidates: List[Dict[str, Any]] = []
        pair_results_map: Dict[str, Dict[str, Any]] = {}

        for pair_name in ACTIVE_PAIRS:
            if self.shutdown_event.is_set():
                break

            pair_market = market_spreads.get(pair_name, {})
            forward_spread = float(pair_market.get("forward_spread_bps", pair_market.get("spread_bps", 0.0)))
            reverse_spread = float(pair_market.get("reverse_spread_bps", 0.0))
            base_price = pair_market.get("cetus_price")
            deepbook_price = pair_market.get("deepbook_price", base_price)
            deepbook_ask = pair_market.get("deepbook_ask", deepbook_price)
            bid_depth_quote = pair_market.get("bid_depth_quote")
            ask_depth_quote = pair_market.get("ask_depth_quote")
            cetus_liq = pair_market.get("cetus_liquidity")
            cetus_sqrt_p = pair_market.get("cetus_sqrt_price")

            # Check both forward and reverse spreads; set route_direction = "REVERSE" when profitable and better than forward
            if reverse_spread > forward_spread and reverse_spread > 0.0:
                route_dir = "REVERSE"
                eval_spread_bps = reverse_spread
            else:
                route_dir = "FORWARD"
                eval_spread_bps = forward_spread

            # Use Ask depth for REVERSE routes (market buying on DeepBook) and Bid depth for FORWARD routes
            if route_dir == "REVERSE":
                depth_to_use = ask_depth_quote if "ask_depth_quote" in pair_market else None
            else:
                depth_to_use = bid_depth_quote if "bid_depth_quote" in pair_market else None

            # Multi-DEX target selection (Cetus vs Turbos)
            if self.config.amm_target in ("cetus", "turbos"):
                target_amm = self.config.amm_target
            else:
                target_amm = pair_market.get("best_amm", pair_market.get("amm_target", "cetus"))

            # DeepBook Vault Balance Check (Requirement R3):
            vault_balances = vault_balances_map.get(pair_name) or await self.validator.graphql_client.get_deepbook_vault_balances(pair_name)
            vault_quote_balance = vault_balances.get("quote_balance", 0)

            explicit_deep_coin = pair_market.get("deep_coin")
            pair_deep_coin = (
                explicit_deep_coin
                if isinstance(explicit_deep_coin, dict)
                and explicit_deep_coin.get("address")
                and explicit_deep_coin.get("digest")
                else deep_coin_info
            )

            # Requirement R2: Analytical Q* Optimal Sizing, Live Fee Detection & Dynamic Tranches
            (
                fee_hurdle,
                db_fee_bps_override,
                borrow_amount,
                active_deep_coin,
                deep_fee_amount,
            ) = self._resolve_pair_fee_and_borrow(
                pair_name=pair_name,
                target_amm=target_amm,
                eval_spread_bps=eval_spread_bps,
                sui_spot=sui_spot,
                base_price=base_price,
                depth_to_use=depth_to_use,
                cetus_liq=cetus_liq,
                cetus_sqrt_p=cetus_sqrt_p,
                vault_quote_balance=vault_quote_balance,
                live_fee_map=live_fee_map,
                pair_deep_coin=pair_deep_coin,
                pair_market=pair_market,
            )

            # Requirement R2/R4: Dynamic Average Execution Slippage Protection
            amm_slippage_bps = self._compute_amm_slippage_bps(
                pair_name=pair_name,
                borrow_amount=borrow_amount,
                cetus_liq=cetus_liq,
                cetus_sqrt_p=cetus_sqrt_p,
            )
            effective_hurdle_bps = fee_hurdle + amm_slippage_bps

            # Preflight Vault Balance Protection vs Shallow Orderbook Depth check
            vault_cap = int(float(vault_quote_balance) * 0.90)
            vault_protection_triggered = False
            shallow_depth_triggered = False

            is_sui_quote = pair_name.endswith("/SUI") or pair_name in ("DEEP/SUI", "CETUS/SUI")
            min_floor_units = int(round((25.0 / sui_spot) * 1_000_000_000)) if is_sui_quote else 25_000_000

            vault_insufficient = vault_cap < min_floor_units or borrow_amount > vault_cap
            if eval_spread_bps > fee_hurdle and vault_insufficient:
                vault_protection_triggered = True
                logger.warning(
                    f"VAULT PROTECTION TRIGGERED for {pair_name}: borrow_amount {borrow_amount} "
                    f"or vault_cap {vault_cap} below minimum floor {min_floor_units} "
                    f"(vault quote balance={vault_quote_balance}). "
                    f"Cleanly skipping execution to eliminate Move abort code 2 (EInsufficientVaultBalance)."
                )
            elif eval_spread_bps > fee_hurdle and borrow_amount <= 0:
                shallow_depth_triggered = True
                logger.info(
                    f"Shallow orderbook depth for {pair_name} ({route_dir}): "
                    f"spread {eval_spread_bps:+.1f} bps > fee hurdle {fee_hurdle:.1f} bps, "
                    f"usable depth_quote={depth_to_use} yields borrow <= 0 below floor {min_floor_units}. "
                    f"Cleanly skipping execution."
                )

            if vault_protection_triggered or shallow_depth_triggered:
                status = "SKIPPED_VAULT_PROTECTED" if vault_protection_triggered else "SKIPPED_SHALLOW_DEPTH"
                net_profit = 0.0
                gas_cost_sui = 0.002
                zero_leg_risk_preserved = True
                net_profit_usd = 0.0
                is_profitable = False
                dry_run = {}
            else:
                # 4. Structural validation of 8-step atomic PTB
                ptb_validation = self.validator.validate_atomic_ptb_generation(
                    pair_name=pair_name,
                    borrow_amount=borrow_amount if borrow_amount > 0 else None,
                    route_direction=route_dir,
                    vault_balances=vault_balances,
                    amm_target=target_amm,
                )
                is_valid = ptb_validation.get("valid", False) if isinstance(ptb_validation, dict) else getattr(ptb_validation, "valid", False)
                if not is_valid:
                    errors = ptb_validation.get("errors") if isinstance(ptb_validation, dict) else getattr(ptb_validation, "errors", [])
                    logger.error(f"PTB generation invalid for {pair_name}: {errors}")
                    status = "ABORTED"
                    net_profit = 0.0
                    gas_cost_sui = 0.002
                    zero_leg_risk_preserved = True
                    net_profit_usd = 0.0
                    is_profitable = False
                    dry_run = {}
                else:
                    # 5. Move VM simulation with live spread, price, and fee tier
                    dry_run = self.validator.simulate_ptb_dry_run(
                        pair_name=pair_name,
                        borrow_amount=borrow_amount if borrow_amount > 0 else None,
                        spread_bps=eval_spread_bps,
                        base_price=base_price,
                        route_direction=route_dir,
                        deepbook_ask_px=deepbook_ask,
                        amm_target=target_amm,
                        deepbook_fee_bps=db_fee_bps_override,
                    )
                    status = dry_run.get("status") if isinstance(dry_run, dict) else getattr(dry_run, "status", "ABORTED")
                    net_profit = dry_run.get("net_profit", 0.0) if isinstance(dry_run, dict) else getattr(dry_run, "net_profit", 0.0)
                    gas_cost_sui = dry_run.get("gas_cost_sui", 0.002) if isinstance(dry_run, dict) else getattr(dry_run, "gas_cost_sui", 0.002)
                    zero_leg_risk_preserved = dry_run.get("zero_leg_risk_preserved", True) if isinstance(dry_run, dict) else getattr(dry_run, "zero_leg_risk_preserved", True)

                    # Convert quote currency net profit to USD equivalent and deduct expected AMM slippage + gas
                    raw_net_profit_usd = (net_profit * sui_spot) if is_sui_quote else net_profit
                    if status == "SUCCESS" and borrow_amount > 0:
                        borrow_usd = (
                            (float(borrow_amount) / 1_000_000_000.0) * sui_spot
                            if is_sui_quote
                            else (float(borrow_amount) / 1_000_000.0)
                        )
                        slippage_cost_usd = borrow_usd * (amm_slippage_bps / 10000.0)
                        gas_cost_usd = float(gas_cost_sui) * sui_spot
                        expected_net_after_slippage = raw_net_profit_usd - slippage_cost_usd - gas_cost_usd
                        net_profit_usd = expected_net_after_slippage
                    else:
                        expected_net_after_slippage = 0.0
                        net_profit_usd = raw_net_profit_usd

                    if route_dir == "REVERSE":
                        has_deepbook_depth = (ask_depth_quote > 0) if "ask_depth_quote" in pair_market and ask_depth_quote is not None else True
                    else:
                        has_deepbook_depth = (bid_depth_quote > 0) if "bid_depth_quote" in pair_market and bid_depth_quote is not None else True

                    is_profitable = (
                        status == "SUCCESS"
                        and expected_net_after_slippage >= self.config.min_profit_usd
                        and borrow_amount > 0
                        and has_deepbook_depth
                        and eval_spread_bps > effective_hurdle_bps
                    )

                    if status == "SUCCESS" and eval_spread_bps <= effective_hurdle_bps and eval_spread_bps > fee_hurdle:
                        logger.info(
                            f"Sub-slippage spread on {pair_name} ({route_dir}): spread {eval_spread_bps:+.1f} bps "
                            f"<= effective hurdle {effective_hurdle_bps:.1f} bps (fee {fee_hurdle:.1f} + slippage {amm_slippage_bps:.1f} bps). "
                            f"Execution safely skipped to eliminate Move VM abort."
                        )
                    elif status == "SUCCESS" and eval_spread_bps > effective_hurdle_bps and expected_net_after_slippage < self.config.min_profit_usd:
                        logger.info(
                            f"Sub-min-profit spread on {pair_name} ({route_dir}): "
                            f"expected net ${expected_net_after_slippage:.4f} < min ${self.config.min_profit_usd:.4f}. "
                            f"Cleanly skipping execution."
                        )

            if vault_protection_triggered:
                execution_status = "SKIPPED_VAULT_PROTECTED"
            elif shallow_depth_triggered:
                execution_status = "SKIPPED_SHALLOW_DEPTH"
            else:
                execution_status = "SIMULATED"

            candidate_info = {
                "pair": pair_name,
                "route_direction": route_dir,
                "borrow_amount": borrow_amount,
                "amm_target": target_amm,
                "tier": self.scaling_engine.current_tier.name,
                "status": status,
                "net_profit": net_profit,
                "net_profit_usd": net_profit_usd,
                "gas_cost_sui": gas_cost_sui,
                "zero_leg_risk_preserved": zero_leg_risk_preserved,
                "spread_bps": eval_spread_bps,
                "forward_spread_bps": forward_spread,
                "reverse_spread_bps": reverse_spread,
                "fee_hurdle_bps": fee_hurdle,
                "deepbook_fee_bps": db_fee_bps_override,
                "effective_hurdle_bps": effective_hurdle_bps,
                "amm_slippage_bps": amm_slippage_bps,
                "cetus_price": base_price if base_price is not None else 0.0,
                "deepbook_price": deepbook_price if deepbook_price is not None else 0.0,
                "deepbook_ask": deepbook_ask,
                "execution_status": execution_status,
                "is_profitable": is_profitable,
                "dry_run": dry_run,
                "min_floor_units": min_floor_units,
                "deep_coin": active_deep_coin,
                "deep_fee_amount": deep_fee_amount,
            }
            pair_results_map[pair_name] = candidate_info
            if is_profitable:
                pair_candidates.append(candidate_info)

        # Route Prioritization (Requirement R3):
        # When multiple pair opportunities exceed profit thresholds, strictly prioritize DEEP/SUI over DEEP/USDC
        if pair_candidates:
            prioritized_candidates = prioritize_opportunities(pair_candidates)
            for opp in prioritized_candidates:
                pair_name = opp["pair"]
                route_dir = opp["route_direction"]
                borrow_amount = opp["borrow_amount"]
                eval_spread_bps = opp["spread_bps"]
                net_profit_usd = opp["net_profit_usd"]
                net_profit = opp["net_profit"]
                deepbook_ask = opp["deepbook_ask"]
                deepbook_price = opp["deepbook_price"]
                base_price = opp["cetus_price"]
                dry_run = opp["dry_run"]

                self.total_opportunities_found += 1
                if not self.config.dry_run_mode:
                    logger.info(
                        f"LIVE ARBITRAGE TRIGGER: Executing PTB for {pair_name} ({route_dir}) | "
                        f"Borrow: {borrow_amount} | Spread: {eval_spread_bps:+.1f} bps | Expected Net Profit: ${net_profit_usd:.2f} (native: {net_profit:.4f})"
                    )
                    self.total_executions_attempted += 1
                    try:
                        order_params = {
                            "symbol": pair_name,
                            "side": "BUY",
                            "size": borrow_amount,
                            "price": dry_run.get("deepbook_ask_px" if route_dir == "REVERSE" else "deepbook_bid_px", deepbook_price),
                            "deepbook_ask_px": deepbook_ask,
                            "amm_price": dry_run.get("amm_swap_out_px", base_price),
                            "is_arb_ptb": True,
                            "route_direction": route_dir,
                            "amm_target": opp.get("amm_target", "cetus"),
                            "deepbook_fee_bps": opp.get("deepbook_fee_bps"),
                            "enable_tranche_fallback": True,
                            "min_borrow_units": opp.get("min_floor_units", 0),
                            "deep_coin": opp.get("deep_coin"),
                            "deep_fee_amount": opp.get("deep_fee_amount", 0),
                            "live_onchain": bool(
                                self.config.sui_private_key
                                and self.config.sui_private_key.startswith("suiprivkey1")
                            ),
                        }
                        exec_res = await self.validator.venue.submit_order(order_params)
                        if order_params.get("live_onchain") and order_params.get("deep_coin") is not None and (
                            exec_res.status == "FILLED" or not exec_res.order_id.startswith("PTB-SIM-REVERT")
                        ):
                            self._last_deep_check_ts = 0.0
                        if exec_res.status == "FILLED":
                            opp["execution_status"] = "EXECUTED"
                            pair_results_map[pair_name]["execution_status"] = "EXECUTED"
                            logger.info(f"Live PTB executed successfully for {pair_name}: order_id={exec_res.order_id}")
                            self.scaling_engine.record_trade_success(profit_usdc=net_profit_usd)
                        else:
                            opp["execution_status"] = "REJECTED"
                            pair_results_map[pair_name]["execution_status"] = "REJECTED"
                            logger.info(f"Live PTB pre-flight simulation rejected for {pair_name} (0 gas cost): order_id={exec_res.order_id}")
                            if not exec_res.order_id.startswith("PTB-SIM-REVERT"):
                                self.scaling_engine.record_trade_abort()
                    except Exception as e:
                        opp["execution_status"] = "ERROR"
                        pair_results_map[pair_name]["execution_status"] = "ERROR"
                        logger.error(f"Live PTB execution error for {pair_name}: {e}")
                        self.scaling_engine.record_trade_abort()
                else:
                    logger.info(
                        f"[DRY_RUN_MODE=true] Arbitrage opportunity simulated on {pair_name} ({route_dir}) | "
                        f"Spread: {eval_spread_bps:+.1f} bps | Simulated Net Profit: ${net_profit_usd:.2f} (Execution skipped)"
                    )

        results = [pair_results_map[p] for p in ACTIVE_PAIRS if p in pair_results_map]

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
