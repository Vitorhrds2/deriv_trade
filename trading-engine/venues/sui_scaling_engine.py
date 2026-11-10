"""Dynamic Capital Scaling Engine and Sui Balance Tracker.

Governs dynamic flash loan tranche sizing and risk guardrails for Sui DeepBookV3 & Cetus AMM arbitrage:
1. ScalingTier:
   - TIER_1 = 1_000_000_000 (1,000 USDC nativo, 6 decimals)
   - TIER_2 = 5_000_000_000 (5,000 USDC nativo, 6 decimals)
   - TIER_3 = 10_000_000_000 (10,000 USDC nativo, 6 decimals)
2. ScalingState:
   - Tracks current tier, accumulated net profit, successful trade count, consecutive aborts,
     SUI gas balance, and system status ("ACTIVE", "COOLING_DOWN", "EMERGENCY_LOCKED").
3. DynamicCapitalScalingEngine:
   - Automatic tier promotion:
     - Tier 1 -> Tier 2 upon >= $100.00 net profit and >= 10 successful executions.
     - Tier 2 -> Tier 3 upon >= $750.00 cumulative net profit and >= 20 successful executions.
   - Dynamic borrow amount resolution:
     - 1k/5k/10k USDC for USDC quote pairs (SUI/USDC, DEEP/USDC).
     - Proportional SUI amount for SUI quote pairs (DEEP/SUI, CETUS/SUI) based on SUI spot price.
   - Gas safety floors:
     - Warning floor at 1.5 SUI (throttles scan rate, emits alert).
     - Critical hard stop at 0.5 SUI (sets status to EMERGENCY_LOCKED, halts execution immediately).
   - Drawdown circuit breakers:
     - 3 consecutive aborts: Demotes 1 tier, enters 60-second cooldown (COOLING_DOWN).
     - 5 consecutive aborts: Emergency lock (EMERGENCY_LOCKED).
4. SuiBalanceTracker:
   - Wraps SuiGraphQLClient for atomic dual SUI/USDC balance queries.
   - Validates gas safety floors against operator wallet 0x5621a8e7199680512ee829565b96febea2587e534fd69b33f04004298d7e5ce9.
"""

from __future__ import annotations

import asyncio
import logging
import sys
import time
from dataclasses import dataclass, field
from enum import IntEnum
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

# Ensure trading-engine root is in sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

try:
    from .sui_deepbook_venue import (
        CIRCLE_USDC_TYPE,
        SUI_COIN_TYPE,
        SUI_PAIRS_CONFIG,
        SuiGraphQLClient,
    )
except ImportError:
    from venues.sui_deepbook_venue import (
        CIRCLE_USDC_TYPE,
        SUI_COIN_TYPE,
        SUI_PAIRS_CONFIG,
        SuiGraphQLClient,
    )

logger = logging.getLogger(__name__)

# System Status Constants
STATUS_ACTIVE = "ACTIVE"
STATUS_COOLING_DOWN = "COOLING_DOWN"
STATUS_EMERGENCY_LOCKED = "EMERGENCY_LOCKED"

# Gas Floor Constants (in SUI units)
DEFAULT_WARNING_GAS_FLOOR: float = 1.5
DEFAULT_CRITICAL_GAS_FLOOR: float = 0.5

# Cooldown Duration
DEFAULT_COOLDOWN_SECONDS: float = 60.0

# Operator Wallet on Sui Mainnet
OPERATOR_WALLET_ADDRESS: str = (
    "0x5621a8e7199680512ee829565b96febea2587e534fd69b33f04004298d7e5ce9"
)

# Default Per-Pair Maximum Borrow Tranches in USD:
# Calibrated against Cetus pool TVL and DeepBook orderbook depth:
# - SUI/USDC: $10,000 (deepest pool on Sui, $18.5M TVL, <0.2 bps impact)
# - DEEP/SUI: $4,000 (~4,900 SUI at ~$0.81; captures Level 2 wall of 8,950 SUI with controlled impact)
# - DEEP/USDC: $1,000 (pool TVL is $241k; keeps price impact under ~25 bps)
# - CETUS/SUI: $2,500 (~3,000 SUI; balances Cetus pool depth and fees)
DEFAULT_PAIR_MAX_BORROW_USD: Dict[str, float] = {
    "SUI/USDC": 10000.0,
    "DEEP/SUI": 4000.0,
    "DEEP/USDC": 1000.0,
    "CETUS/SUI": 2500.0,
}


class ScalingTier(IntEnum):
    """Capital scaling tiers defining flash borrow tranche sizes in native micro-units (6 decimals)."""

    TIER_1 = 1_000_000_000  # 1,000 USDC (initial baseline)
    TIER_2 = 5_000_000_000  # 5,000 USDC (Trigger: >= $100 net profit, >= 10 trades)
    TIER_3 = 10_000_000_000  # 10,000 USDC (Trigger: >= $750 cumulative net profit, >= 20 trades)

    @property
    def usd_value(self) -> float:
        """Nominal USD value represented by this tier."""
        return self.value / 1_000_000.0


@dataclass
class ScalingState:
    """Runtime state of the dynamic capital scaling engine."""

    current_tier: ScalingTier = ScalingTier.TIER_1
    accumulated_net_profit_usdc: float = 0.0
    successful_trades: int = 0
    consecutive_aborts: int = 0
    sui_gas_balance: float = 0.0
    status: str = STATUS_ACTIVE  # "ACTIVE" | "COOLING_DOWN" | "EMERGENCY_LOCKED"
    cooldown_until: float = 0.0
    gas_warning: bool = False

    @property
    def flash_borrow_amount(self) -> int:
        """Current borrow tranche in USDC atomic micro-units."""
        return int(self.current_tier.value)


@dataclass
class WalletBalanceSnapshot:
    """Atomic snapshot of SUI and USDC balances retrieved from on-chain GraphQL."""

    sui_mist: int
    sui_balance: float  # SUI float (sui_mist / 1e9)
    usdc_raw: int
    usdc_balance: float  # USDC float (usdc_raw / 1e6)
    timestamp: float = field(default_factory=time.time)
    is_gas_warning: bool = False
    is_gas_critical: bool = False
    status: str = "HEALTHY"  # "HEALTHY" | "WARNING" | "CRITICAL"

    @property
    def sui_float(self) -> float:
        return self.sui_balance

    @property
    def usdc_float(self) -> float:
        return self.usdc_balance

    @property
    def usdc_units(self) -> int:
        return self.usdc_raw

    def __getitem__(self, item: str) -> Any:
        return getattr(self, item)


class DynamicCapitalScalingEngine:
    """State machine governing dynamic flash loan tranche sizing and risk guardrails.

    Starting parameter:
    - Initial flash_borrow_amount = 1_000_000_000 (1,000 USDC nativo, 6 decimals).

    Automatic tier upgrades:
    - Tier 1 -> Tier 2: Triggers upon reaching >= $100.00 net profit AND >= 10 successful executions.
    - Tier 2 -> Tier 3: Triggers upon reaching >= $750.00 cumulative net profit AND >= 20 successful executions.

    Dynamic borrow amount resolution:
    - get_current_borrow_amount(pair_name, sui_spot_price=None):
      - Returns 1k/5k/10k USDC for USDC quote pairs (SUI/USDC, DEEP/USDC).
      - Returns equivalent SUI amount for SUI quote pairs (DEEP/SUI, CETUS/SUI) based on SUI spot price.

    Gas safety floors:
    - Warning floor at 1.5 SUI (throttles scan rate, emits alert).
    - Critical hard stop at 0.5 SUI (sets status to EMERGENCY_LOCKED, halts execution immediately).

    Drawdown circuit breakers:
    - 3 consecutive aborts: Demote by 1 tier and enter 60-second cooldown (COOLING_DOWN).
    - 5 consecutive aborts: Emergency lock (EMERGENCY_LOCKED).
    """

    def __init__(
        self,
        balance_tracker: Optional[SuiBalanceTracker] = None,
        initial_tier: ScalingTier = ScalingTier.TIER_1,
        tier1_profit_threshold: float = 100.0,
        tier2_profit_threshold: float = 750.0,
        min_tier1_trades: int = 10,
        min_tier2_trades: int = 20,
        warning_gas_floor: float = DEFAULT_WARNING_GAS_FLOOR,
        critical_gas_floor: float = DEFAULT_CRITICAL_GAS_FLOOR,
        cooldown_duration_seconds: float = DEFAULT_COOLDOWN_SECONDS,
        initial_baseline_usdc: Optional[float] = None,
        pair_max_borrow_usd: Optional[Dict[str, float]] = None,
    ) -> None:
        self.balance_tracker = balance_tracker
        self.tier1_profit_threshold = float(tier1_profit_threshold)
        self.tier2_profit_threshold = float(tier2_profit_threshold)
        self.min_tier1_trades = int(min_tier1_trades)
        self.min_tier2_trades = int(min_tier2_trades)
        self.warning_gas_floor = float(warning_gas_floor)
        self.critical_gas_floor = float(critical_gas_floor)
        self.cooldown_duration_seconds = float(cooldown_duration_seconds)
        self.baseline_usdc_balance: Optional[float] = (
            float(initial_baseline_usdc) if initial_baseline_usdc is not None else None
        )
        self.pair_max_borrow_usd = (
            dict(pair_max_borrow_usd) if pair_max_borrow_usd is not None else None
        )

        self.state = ScalingState(
            current_tier=initial_tier,
            accumulated_net_profit_usdc=0.0,
            successful_trades=0,
            consecutive_aborts=0,
            sui_gas_balance=0.0,
            status=STATUS_ACTIVE,
            cooldown_until=0.0,
            gas_warning=False,
        )
        self._emergency_locked_due_to_aborts = False

    @property
    def flash_borrow_amount(self) -> int:
        """Current flash borrow amount in USDC atomic micro-units (1_000_000_000 initially)."""
        return int(self.state.current_tier.value)

    @property
    def current_tier(self) -> ScalingTier:
        return self.state.current_tier

    @property
    def status(self) -> str:
        self._check_cooldown_expiry()
        return self.state.status

    def _check_cooldown_expiry(self) -> None:
        """Checks if a cooling-down state has expired and can transition back to ACTIVE."""
        if self.state.status == STATUS_COOLING_DOWN:
            if time.time() >= self.state.cooldown_until:
                if (
                    self.state.sui_gas_balance > 0
                    and self.state.sui_gas_balance < self.critical_gas_floor
                ):
                    self.state.status = STATUS_EMERGENCY_LOCKED
                else:
                    self.state.status = STATUS_ACTIVE
                    logger.info("Cooldown period elapsed. Status restored to ACTIVE.")

    def can_trade(self) -> bool:
        """Determines whether the engine currently permits trade execution."""
        self._check_cooldown_expiry()
        if self.state.status != STATUS_ACTIVE:
            return False
        if (
            self.state.sui_gas_balance > 0
            and self.state.sui_gas_balance < self.critical_gas_floor
        ):
            self.state.status = STATUS_EMERGENCY_LOCKED
            return False
        return True

    def record_trade_success(self, profit_usdc: float) -> None:
        """Records a successful trade execution, updates profit, resets abort count, and checks promotions."""
        if profit_usdc < 0:
            raise ValueError(f"Profit must be non-negative: {profit_usdc}")

        self.state.accumulated_net_profit_usdc += float(profit_usdc)
        self.state.successful_trades += 1
        self.state.consecutive_aborts = 0
        self._emergency_locked_due_to_aborts = False

        # Clear cooldown on verified success
        if self.state.status == STATUS_COOLING_DOWN:
            self.state.status = STATUS_ACTIVE
            self.state.cooldown_until = 0.0

        self._evaluate_tier_promotions()

    def record_trade_abort(self) -> None:
        """Records a trade abort / failure, tracks consecutive aborts, and triggers circuit breakers."""
        self.state.consecutive_aborts += 1

        if self.state.consecutive_aborts >= 5:
            self.state.status = STATUS_EMERGENCY_LOCKED
            self._emergency_locked_due_to_aborts = True
            logger.critical(
                f"Circuit Breaker TRIGGERED: {self.state.consecutive_aborts} consecutive aborts. "
                f"State changed to {STATUS_EMERGENCY_LOCKED}."
            )
        elif self.state.consecutive_aborts >= 3:
            # Demote by 1 tier upon hitting 3 consecutive aborts
            if self.state.consecutive_aborts == 3:
                if self.state.current_tier == ScalingTier.TIER_3:
                    self.state.current_tier = ScalingTier.TIER_2
                    logger.warning("Demoted from Tier 3 to Tier 2 due to 3 consecutive aborts.")
                elif self.state.current_tier == ScalingTier.TIER_2:
                    self.state.current_tier = ScalingTier.TIER_1
                    logger.warning("Demoted from Tier 2 to Tier 1 due to 3 consecutive aborts.")
                else:
                    logger.warning("3 consecutive aborts at Tier 1; tier unchanged at Tier 1.")

            self.state.status = STATUS_COOLING_DOWN
            self.state.cooldown_until = time.time() + self.cooldown_duration_seconds
            logger.warning(
                f"Entered {STATUS_COOLING_DOWN} for {self.cooldown_duration_seconds}s. "
                f"Current tier: {self.state.current_tier.name}."
            )

    def _evaluate_tier_promotions(self) -> None:
        """Evaluates tier upgrade conditions based on accumulated profit and trade counts."""
        # Tier 1 -> Tier 2 (or Tier 3 directly if thresholds met)
        if self.state.current_tier == ScalingTier.TIER_1:
            if (
                self.state.accumulated_net_profit_usdc >= self.tier1_profit_threshold
                and self.state.successful_trades >= self.min_tier1_trades
            ):
                if (
                    self.state.accumulated_net_profit_usdc >= self.tier2_profit_threshold
                    and self.state.successful_trades >= self.min_tier2_trades
                ):
                    self.state.current_tier = ScalingTier.TIER_3
                    logger.info(
                        f"Tier Upgrade: Promoted to TIER_3 (borrow_amount={self.state.current_tier.value:,} micro-USDC) "
                        f"with ${self.state.accumulated_net_profit_usdc:.2f} profit and {self.state.successful_trades} trades."
                    )
                else:
                    self.state.current_tier = ScalingTier.TIER_2
                    logger.info(
                        f"Tier Upgrade: Promoted to TIER_2 (borrow_amount={self.state.current_tier.value:,} micro-USDC) "
                        f"with ${self.state.accumulated_net_profit_usdc:.2f} profit and {self.state.successful_trades} trades."
                    )
        # Tier 2 -> Tier 3
        elif self.state.current_tier == ScalingTier.TIER_2:
            if (
                self.state.accumulated_net_profit_usdc >= self.tier2_profit_threshold
                and self.state.successful_trades >= self.min_tier2_trades
            ):
                self.state.current_tier = ScalingTier.TIER_3
                logger.info(
                    f"Tier Upgrade: Promoted to TIER_3 (borrow_amount={self.state.current_tier.value:,} micro-USDC) "
                    f"with ${self.state.accumulated_net_profit_usdc:.2f} profit and {self.state.successful_trades} trades."
                )

    def update_from_wallet_balances(
        self, usdc_balance: float, sui_balance: float
    ) -> None:
        """Updates gas balance, checks safety floors, and reconciles USDC profit from wallet."""
        self.state.sui_gas_balance = float(sui_balance)

        # 1. Evaluate Gas Safety Floors
        if sui_balance < self.critical_gas_floor:
            self.state.status = STATUS_EMERGENCY_LOCKED
            self.state.gas_warning = True
            logger.critical(
                f"CRITICAL GAS HARD STOP: Balance {sui_balance:.4f} SUI is below critical floor "
                f"{self.critical_gas_floor} SUI. Execution halted immediately."
            )
        elif sui_balance < self.warning_gas_floor:
            self.state.gas_warning = True
            logger.warning(
                f"GAS WARNING: Balance {sui_balance:.4f} SUI is below warning floor "
                f"{self.warning_gas_floor} SUI. Scan rate throttled."
            )
        else:
            self.state.gas_warning = False
            # If gas recovered and not locked by 5 consecutive aborts
            if (
                self.state.status == STATUS_EMERGENCY_LOCKED
                and not self._emergency_locked_due_to_aborts
            ):
                self.state.status = STATUS_ACTIVE
                logger.info(f"Gas restored ({sui_balance:.4f} SUI). Resumed ACTIVE status.")

        # 2. Reconcile USDC profit from wallet balance
        if self.baseline_usdc_balance is None:
            self.baseline_usdc_balance = float(usdc_balance)
            logger.info(f"Established initial USDC baseline: ${self.baseline_usdc_balance:.4f}")
        else:
            onchain_profit = float(usdc_balance) - self.baseline_usdc_balance
            if onchain_profit > self.state.accumulated_net_profit_usdc:
                self.state.accumulated_net_profit_usdc = onchain_profit
                self._evaluate_tier_promotions()

    def get_current_borrow_amount(
        self,
        pair_name: str,
        sui_spot_price: Optional[float] = None,
        max_depth_quote: Optional[float] = None,
    ) -> int:
        """Resolves dynamic borrow amount in native atomic units for a given trading pair.

        For USDC quote pairs (SUI/USDC, DEEP/USDC):
          Returns current tier value: 1k (1_000_000_000), 5k (5_000_000_000), or 10k (10_000_000_000) micro-USDC.
          When max_depth_quote is provided, caps borrow amount to 85% of available top-of-book depth
          (subject to a $25 USDC minimum floor) to prevent orderbook depth slippage.

        For SUI quote pairs (DEEP/SUI, CETUS/SUI):
          Converts current tier USDC value to equivalent SUI amount in MIST (9 decimals)
          based on sui_spot_price.
          When max_depth_quote is provided, caps borrow amount to 85% of available top-of-book depth
          (subject to a 25 SUI minimum floor).
        """
        pair_clean = pair_name.upper().strip().replace("_", "/")
        tier_usdc_units = self.state.current_tier.value
        tier_usd = tier_usdc_units / 1_000_000.0  # 1000.0, 5000.0, 10000.0

        # Apply per-pair maximum ceiling if configured (liquidity-aware protection)
        if self.pair_max_borrow_usd and pair_clean in self.pair_max_borrow_usd:
            tier_usd = min(tier_usd, float(self.pair_max_borrow_usd[pair_clean]))

        # Determine quote asset
        is_sui_quote = False
        if pair_clean.endswith("/SUI") or pair_clean in ("DEEP/SUI", "CETUS/SUI"):
            is_sui_quote = True
        elif pair_clean.endswith("/USDC") or pair_clean in ("SUI/USDC", "DEEP/USDC"):
            is_sui_quote = False
        elif pair_clean in SUI_PAIRS_CONFIG:
            is_sui_quote = SUI_PAIRS_CONFIG[pair_clean].quote_symbol == "SUI"

        if is_sui_quote:
            if sui_spot_price is not None:
                if sui_spot_price <= 0:
                    raise ValueError(f"sui_spot_price must be positive, got {sui_spot_price}")
                price = float(sui_spot_price)
            else:
                price = 2.0

            sui_amount = tier_usd / price
            if max_depth_quote is not None and max_depth_quote > 0:
                depth_cap_sui = max_depth_quote * 0.85
                sui_amount = min(sui_amount, max(25.0, depth_cap_sui))

            sui_mist = int(round(sui_amount * 1_000_000_000))
            return sui_mist
        else:
            if max_depth_quote is not None and max_depth_quote > 0:
                depth_cap_usd = max_depth_quote * 0.85
                target_usd = min(tier_usd, max(25.0, depth_cap_usd))
                return int(round(target_usd * 1_000_000))
            return int(round(tier_usd * 1_000_000))

    def unlock_emergency(self, force: bool = False) -> bool:
        """Allows manual operator reset of EMERGENCY_LOCKED status."""
        if (
            self.state.sui_gas_balance > 0
            and self.state.sui_gas_balance < self.critical_gas_floor
            and not force
        ):
            logger.error(
                f"Cannot unlock: SUI gas balance ({self.state.sui_gas_balance} SUI) is below critical floor ({self.critical_gas_floor} SUI)."
            )
            return False
        self.state.status = STATUS_ACTIVE
        self.state.consecutive_aborts = 0
        self._emergency_locked_due_to_aborts = False
        logger.info("Emergency lock reset. Engine status is now ACTIVE.")
        return True

    def set_baseline_usdc(self, baseline: float) -> None:
        """Sets or overrides baseline USDC balance."""
        self.baseline_usdc_balance = float(baseline)


class SuiBalanceTracker:
    """Tracks on-chain SUI gas and USDC balances via Sui GraphQL RPC.

    Provides single-roundtrip atomic querying of SUI and USDC balances,
    evaluates gas safety floors against the operator wallet, and synchronizes
    with DynamicCapitalScalingEngine.
    """

    def __init__(
        self,
        client: Optional[SuiGraphQLClient] = None,
        wallet_address: str = OPERATOR_WALLET_ADDRESS,
        warning_gas_floor: float = DEFAULT_WARNING_GAS_FLOOR,
        critical_gas_floor: float = DEFAULT_CRITICAL_GAS_FLOOR,
        graphql_url: Optional[str] = None,
    ) -> None:
        self.wallet_address = wallet_address
        self.warning_gas_floor = float(warning_gas_floor)
        self.critical_gas_floor = float(critical_gas_floor)
        if client is not None:
            self.client = client
        elif graphql_url is not None:
            self.client = SuiGraphQLClient(endpoint=graphql_url)
        else:
            self.client = SuiGraphQLClient()
        self._last_snapshot: Optional[WalletBalanceSnapshot] = None

    async def fetch_balances(self) -> WalletBalanceSnapshot:
        """Queries atomic SUI and native USDC balances for the operator wallet."""
        balances = await self.client.get_wallet_balances(self.wallet_address)
        sui_mist = int(balances.get("sui_mist", 0))
        sui_balance = float(balances.get("sui", sui_mist / 1e9))
        usdc_raw = int(balances.get("usdc_raw", 0))
        usdc_balance = float(balances.get("usdc", usdc_raw / 1e6))

        is_critical = sui_balance < self.critical_gas_floor
        is_warning = sui_balance < self.warning_gas_floor

        status = "CRITICAL" if is_critical else ("WARNING" if is_warning else "HEALTHY")

        snapshot = WalletBalanceSnapshot(
            sui_mist=sui_mist,
            sui_balance=sui_balance,
            usdc_raw=usdc_raw,
            usdc_balance=usdc_balance,
            timestamp=time.time(),
            is_gas_warning=is_warning,
            is_gas_critical=is_critical,
            status=status,
        )
        self._last_snapshot = snapshot
        return snapshot

    def validate_gas_safety(self, sui_balance: float) -> Tuple[bool, str]:
        """Validates gas safety floors: returns (can_trade, alert_level)."""
        if sui_balance < self.critical_gas_floor:
            return False, "CRITICAL"
        if sui_balance < self.warning_gas_floor:
            return True, "WARNING"
        return True, "HEALTHY"

    async def update_scaling_engine(
        self, engine: DynamicCapitalScalingEngine
    ) -> WalletBalanceSnapshot:
        """Fetches balances and updates the scaling engine state."""
        snapshot = await self.fetch_balances()
        engine.update_from_wallet_balances(
            usdc_balance=snapshot.usdc_balance,
            sui_balance=snapshot.sui_balance,
        )
        return snapshot

    async def close(self) -> None:
        """Closes the underlying GraphQL client session."""
        if self.client:
            await self.client.close()
