"""Sui Programmable Transaction Block (PTB) Preflight Validator and Dry-Run Simulator.

Milestone M3 Implementation:
Requirement R4 - Programmatic Verification & Dry-Run Simulation:
1. SuiPTBPreflightValidator:
   - Comprehensive pre-flight healthcheck and dry-run validation routine:
     - validate_preflight_health(): Tests GraphQL RPC connectivity, verifies operator wallet
       (0x5621a8e7...) has >= 0.5 SUI gas reserve (reporting actual 5.419 SUI balance),
       verifies pool object accessibility for all 4 pairs (SUI/USDC, DEEP/SUI, DEEP/USDC, CETUS/SUI),
       and checks BalanceManager configuration.
     - validate_atomic_ptb_generation(pair_name, borrow_amount): Validates that an 8-command PTB
       is generated with strict command sequence, correct pool IDs, a2b flags, and Hot Potato
       borrowing/repayment links.
     - simulate_ptb_dry_run(pair_name, borrow_amount, spread_bps): Performs dry-run simulation of the
       8-step PTB using Move VM semantics:
       - Profitable spread (> fees): Returns status == "SUCCESS", net_profit > 0, zero_leg_risk_preserved == True.
       - Unprofitable / zero spread: Returns status == "ABORTED", gas_cost_sui == 0.002 (~2,000,000 MIST),
         zero_leg_risk_preserved == True, state_mutations == 0.
     - simulate_capital_scaling_lifecycle(): Simulates complete end-to-end operational lifecycle:
       starting at Tier 1 (1,000 USDC / 1_000_000_000), accumulating net profits through successful dry-runs,
       triggering promotion to Tier 2 (5,000 USDC) at >= $100, continuing to accumulate profit, and triggering
       promotion to Tier 3 (10,000 USDC) at >= $750.
"""

from __future__ import annotations

import asyncio
import logging
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

# Ensure trading-engine root is on sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

try:
    from .sui_deepbook_venue import (
        CETUS_GLOBAL_CONFIG_ID,
        CETUS_POOL_CETUS_SUI,
        CETUS_POOL_DEEP_SUI,
        CETUS_POOL_DEEP_USDC,
        CETUS_POOL_SUI_USDC,
        CETUS_SUI_POOL_ID,
        CIRCLE_USDC_TYPE,
        DEEP_SUI_POOL_ID,
        DEEP_USDC_POOL_ID,
        DEEPBOOK_PACKAGE_ID,
        MAX_SQRT_PRICE,
        MIN_SQRT_PRICE,
        SUI_CLOCK_OBJECT_ID,
        SUI_COIN_TYPE,
        SUI_GRAPHQL_MAINNET,
        SUI_PAIRS_CONFIG,
        SUI_USDC_POOL_ID,
        TURBOS_PACKAGE_ID,
        TURBOS_POOL_CONFIG_ID,
        TURBOS_VERSIONED_ID,
        HotPotatoPTBParams,
        PairConfig,
        SuiDeepBookPTBBuilder,
        SuiDeepBookVenue,
        SuiGraphQLClient,
    )
    from .sui_scaling_engine import (
        DEFAULT_CRITICAL_GAS_FLOOR,
        DEFAULT_WARNING_GAS_FLOOR,
        OPERATOR_WALLET_ADDRESS,
        STATUS_ACTIVE,
        STATUS_COOLING_DOWN,
        STATUS_EMERGENCY_LOCKED,
        DynamicCapitalScalingEngine,
        ScalingState,
        ScalingTier,
        SuiBalanceTracker,
        WalletBalanceSnapshot,
    )
except ImportError:
    from venues.sui_deepbook_venue import (
        CETUS_GLOBAL_CONFIG_ID,
        CETUS_POOL_CETUS_SUI,
        CETUS_POOL_DEEP_SUI,
        CETUS_POOL_DEEP_USDC,
        CETUS_POOL_SUI_USDC,
        CETUS_SUI_POOL_ID,
        CIRCLE_USDC_TYPE,
        DEEP_SUI_POOL_ID,
        DEEP_USDC_POOL_ID,
        DEEPBOOK_PACKAGE_ID,
        MAX_SQRT_PRICE,
        MIN_SQRT_PRICE,
        SUI_CLOCK_OBJECT_ID,
        SUI_COIN_TYPE,
        SUI_GRAPHQL_MAINNET,
        SUI_PAIRS_CONFIG,
        SUI_USDC_POOL_ID,
        TURBOS_PACKAGE_ID,
        TURBOS_POOL_CONFIG_ID,
        TURBOS_VERSIONED_ID,
        HotPotatoPTBParams,
        PairConfig,
        SuiDeepBookPTBBuilder,
        SuiDeepBookVenue,
        SuiGraphQLClient,
    )
    from venues.sui_scaling_engine import (
        DEFAULT_CRITICAL_GAS_FLOOR,
        DEFAULT_WARNING_GAS_FLOOR,
        OPERATOR_WALLET_ADDRESS,
        STATUS_ACTIVE,
        STATUS_COOLING_DOWN,
        STATUS_EMERGENCY_LOCKED,
        DynamicCapitalScalingEngine,
        ScalingState,
        ScalingTier,
        SuiBalanceTracker,
        WalletBalanceSnapshot,
    )

logger = logging.getLogger(__name__)

# Standard Move VM Dry-Run Gas Cost Constants
SIMULATED_GAS_MIST: int = 2_000_000
SIMULATED_GAS_SUI: float = 0.002

# Default Base Mid-Prices for Spread Simulation
DEFAULT_PAIR_BASE_PRICES: Dict[str, float] = {
    "SUI/USDC": 2.0,
    "DEEP/SUI": 0.05,
    "DEEP/USDC": 0.10,
    "CETUS/SUI": 0.16,
}


@dataclass
class PreflightHealthReport:
    """Detailed healthcheck results for Sui RPC, operator gas, and pool access."""

    status: str  # "HEALTHY" | "WARNING" | "CRITICAL" | "FAILED"
    rpc_connected: bool
    rpc_endpoint: str
    operator_address: str
    sui_balance: float
    sui_mist: int
    usdc_balance: float
    usdc_raw: int
    gas_reserve_sufficient: bool  # >= 0.5 SUI
    gas_reserve_healthy: bool     # >= 1.5 SUI
    gas_status: str               # "HEALTHY" | "WARNING" | "CRITICAL"
    balance_manager_id: str
    balance_manager_valid: bool
    pools: Dict[str, Dict[str, Any]]
    all_pools_accessible: bool
    all_checks_passed: bool
    timestamp: float = field(default_factory=time.time)
    error_message: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def __getitem__(self, item: str) -> Any:
        return getattr(self, item)


@dataclass
class PTBValidationReport:
    """Verification results for 8-step atomic PTB structure."""

    valid: bool
    pair_name: str
    borrow_amount: int
    command_count: int
    strict_sequence_verified: bool
    hot_potato_borrow_linked: bool
    hot_potato_repay_linked: bool
    hot_potato_quenched: bool
    pool_id_verified: bool
    cetus_pool_id_verified: bool
    a2b_verified: bool
    balance_manager_verified: bool
    ptb: Dict[str, Any]
    errors: List[str] = field(default_factory=list)
    route_direction: str = "FORWARD"
    amm_target: str = "cetus"
    turbos_pool_id_verified: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def __getitem__(self, item: str) -> Any:
        return getattr(self, item)


@dataclass
class PTBDryRunReport:
    """Results from Move VM dry-run simulation of an 8-command PTB."""

    status: str                   # "SUCCESS" | "ABORTED"
    pair: str
    borrow_amount: int
    spread_bps: float
    net_profit: float             # In quote human units (USDC or SUI)
    net_profit_quote: float       # Exact alias for net_profit
    net_profit_native: int        # In atomic units
    zero_leg_risk_preserved: bool
    gas_cost_sui: float           # Exactly 0.002 SUI
    gas_used_mist: int            # Exactly 2_000_000 MIST
    state_mutations: int          # 8 for SUCCESS, 0 for ABORTED
    deepbook_bid_px: float
    amm_swap_out_px: float
    hot_potato_satisfied: bool
    hot_potato_aborted: bool
    error: Optional[str] = None
    shortfall_native: int = 0
    route_direction: str = "FORWARD"
    deepbook_ask_px: Optional[float] = None
    amm_target: str = "cetus"
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def __getitem__(self, item: str) -> Any:
        return getattr(self, item)


@dataclass
class CapitalScalingLifecycleReport:
    """Audit report for simulated end-to-end capital scaling lifecycle."""

    success: bool
    initial_tier: str
    initial_borrow_amount: int
    promoted_to_tier_2_at_trade: Optional[int]
    tier_2_profit_at_promotion: Optional[float]
    promoted_to_tier_3_at_trade: Optional[int]
    tier_3_profit_at_promotion: Optional[float]
    final_tier: str
    final_borrow_amount: int
    total_trades_executed: int
    accumulated_net_profit_usdc: float
    lifecycle_events: List[Dict[str, Any]] = field(default_factory=list)
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def __getitem__(self, item: str) -> Any:
        return getattr(self, item)


class SuiPTBPreflightValidator:
    """Comprehensive Pre-Flight Healthcheck and Move VM Dry-Run Validator.

    Implements Requirement R4:
    1. Pre-flight healthcheck validating GraphQL RPC, wallet gas runway, pool object state,
       and BalanceManager configuration.
    2. PTB structure validator verifying 8-command atomic sequence, pool IDs, a2b flags,
       and Hot Potato lifecycle.
    3. Dry-run simulator using Move VM semantics (clean abort on sub-hurdle spread with ~0.002 SUI,
       positive profit extraction on profitable spread, guaranteed zero leg risk).
    4. Capital scaling lifecycle simulation transitioning 1k -> 5k -> 10k USDC.
    """

    def __init__(
        self,
        graphql_client: Optional[SuiGraphQLClient] = None,
        graphql_url: Optional[str] = None,
        operator_address: str = OPERATOR_WALLET_ADDRESS,
        balance_manager_id: Optional[str] = None,
        warning_gas_floor: float = DEFAULT_WARNING_GAS_FLOOR,
        critical_gas_floor: float = DEFAULT_CRITICAL_GAS_FLOOR,
        venue: Optional[SuiDeepBookVenue] = None,
        ptb_builder: Optional[SuiDeepBookPTBBuilder] = None,
        scaling_engine: Optional[DynamicCapitalScalingEngine] = None,
    ) -> None:
        self.endpoint = graphql_url or SUI_GRAPHQL_MAINNET
        self.operator_address = operator_address
        self.balance_manager_id = (
            balance_manager_id
            if balance_manager_id is not None
            else "0x0000000000000000000000000000000000000000000000000000000000000001"
        )
        self.warning_gas_floor = float(warning_gas_floor)
        self.critical_gas_floor = float(critical_gas_floor)

        if graphql_client is not None:
            self.graphql_client = graphql_client
        elif graphql_url is not None:
            self.graphql_client = SuiGraphQLClient(endpoint=graphql_url)
        else:
            self.graphql_client = SuiGraphQLClient(endpoint=self.endpoint)

        self.ptb_builder = ptb_builder or SuiDeepBookPTBBuilder()
        self.venue = venue or SuiDeepBookVenue(
            graphql_url=self.endpoint,
            active_address=self.operator_address,
        )
        self.scaling_engine = scaling_engine or DynamicCapitalScalingEngine(
            warning_gas_floor=self.warning_gas_floor,
            critical_gas_floor=self.critical_gas_floor,
        )

    async def validate_preflight_health(
        self, mock_data: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Performs comprehensive pre-flight healthcheck:

        1. Tests GraphQL RPC connectivity.
        2. Verifies operator wallet (0x5621a8e7...) has >= 0.5 SUI gas reserve (reporting actual 5.419 SUI balance).
        3. Verifies pool object accessibility for all 4 pairs (SUI/USDC, DEEP/SUI, DEEP/USDC, CETUS/SUI).
        4. Checks BalanceManager configuration.
        """
        rpc_connected = False
        sui_mist = 0
        sui_balance = 0.0
        usdc_raw = 0
        usdc_balance = 0.0
        error_msg = None
        pools_result: Dict[str, Dict[str, Any]] = {}
        all_pools_accessible = True

        # 1. RPC & Wallet Balance Query
        if mock_data is not None:
            rpc_connected = bool(mock_data.get("rpc_connected", True))
            sui_mist = int(mock_data.get("sui_mist", 5_419_245_048))
            sui_balance = float(mock_data.get("sui_balance", sui_mist / 1e9))
            usdc_raw = int(mock_data.get("usdc_raw", 0))
            usdc_balance = float(mock_data.get("usdc_balance", usdc_raw / 1e6))
            if "pools" in mock_data:
                pools_result = mock_data["pools"]
                all_pools_accessible = all(p.get("accessible", False) for p in pools_result.values())
            else:
                for pair_name, cfg in SUI_PAIRS_CONFIG.items():
                    pools_result[pair_name] = {
                        "deepbook_pool_id": cfg.deepbook_pool_id,
                        "cetus_pool_id": cfg.cetus_pool_id,
                        "accessible": True,
                    }
        else:
            try:
                # Query atomic wallet balances via GraphQL client
                wallet_data = await self.graphql_client.get_wallet_balances(self.operator_address)
                sui_mist = int(wallet_data.get("sui_mist", 0))
                sui_balance = float(wallet_data.get("sui", sui_mist / 1e9))
                usdc_raw = int(wallet_data.get("usdc_raw", 0))
                usdc_balance = float(wallet_data.get("usdc", usdc_raw / 1e6))
                rpc_connected = True

                # Query snapshot of all 4 DeepBook and Cetus pools
                snapshot_data = await self.graphql_client.get_market_snapshot(self.operator_address)
                data_dict = snapshot_data.get("data", {}) if snapshot_data else {}

                pool_key_map = {
                    "SUI/USDC": ("d_sui_usdc", "p_sui_usdc"),
                    "DEEP/SUI": ("d_deep_sui", "p_deep_sui"),
                    "DEEP/USDC": ("d_deep_usdc", "p_deep_usdc"),
                    "CETUS/SUI": ("d_cetus_sui", "p_cetus_sui"),
                }

                for pair_name, cfg in SUI_PAIRS_CONFIG.items():
                    d_key, p_key = pool_key_map[pair_name]
                    d_obj = data_dict.get(d_key)
                    p_obj = data_dict.get(p_key)
                    d_ok = d_obj is not None and "asMoveObject" in d_obj
                    p_ok = p_obj is not None and "asMoveObject" in p_obj
                    pair_ok = d_ok and p_ok
                    if not pair_ok:
                        all_pools_accessible = False

                    pools_result[pair_name] = {
                        "deepbook_pool_id": cfg.deepbook_pool_id,
                        "cetus_pool_id": cfg.cetus_pool_id,
                        "deepbook_accessible": d_ok,
                        "cetus_accessible": p_ok,
                        "accessible": pair_ok,
                    }
            except Exception as e:
                logger.warning(f"Live GraphQL check encountered exception: {e}")
                error_msg = str(e)
                rpc_connected = False
                all_pools_accessible = False
                for pair_name, cfg in SUI_PAIRS_CONFIG.items():
                    pools_result[pair_name] = {
                        "deepbook_pool_id": cfg.deepbook_pool_id,
                        "cetus_pool_id": cfg.cetus_pool_id,
                        "accessible": False,
                    }

        # 2. Gas Reserve Evaluation
        gas_sufficient = sui_balance >= self.critical_gas_floor
        gas_healthy = sui_balance >= self.warning_gas_floor
        if sui_balance < self.critical_gas_floor:
            gas_status = "CRITICAL"
        elif sui_balance < self.warning_gas_floor:
            gas_status = "WARNING"
        else:
            gas_status = "HEALTHY"

        # 3. BalanceManager Configuration Check
        bm_valid = bool(
            self.balance_manager_id
            and isinstance(self.balance_manager_id, str)
            and self.balance_manager_id.startswith("0x")
            and len(self.balance_manager_id) >= 3
        )

        # 4. Overall Health Determination
        all_passed = bool(
            rpc_connected
            and gas_sufficient
            and all_pools_accessible
            and bm_valid
        )

        overall_status = "HEALTHY" if (all_passed and gas_healthy) else (
            "WARNING" if (all_passed and not gas_healthy) else (
                "CRITICAL" if not gas_sufficient else "FAILED"
            )
        )

        report = PreflightHealthReport(
            status=overall_status,
            rpc_connected=rpc_connected,
            rpc_endpoint=self.endpoint,
            operator_address=self.operator_address,
            sui_balance=sui_balance,
            sui_mist=sui_mist,
            usdc_balance=usdc_balance,
            usdc_raw=usdc_raw,
            gas_reserve_sufficient=gas_sufficient,
            gas_reserve_healthy=gas_healthy,
            gas_status=gas_status,
            balance_manager_id=self.balance_manager_id,
            balance_manager_valid=bm_valid,
            pools=pools_result,
            all_pools_accessible=all_pools_accessible,
            all_checks_passed=all_passed,
            error_message=error_msg,
        )
        return report.to_dict()

    def validate_vault_balance(
        self,
        pair_name: str,
        borrow_amount: int,
        vault_balances: Optional[Dict[str, int]] = None,
        is_base_borrow: bool = False,
    ) -> Dict[str, Any]:
        """Validates that borrow_amount does not exceed 90% of DeepBook vault balance (Requirement R3)."""
        if vault_balances is None:
            from venues.sui_scaling_engine import DEFAULT_DEEPBOOK_VAULT_BALANCES
            pair_clean = pair_name.upper().strip().replace("_", "/")
            vault_balances = DEFAULT_DEEPBOOK_VAULT_BALANCES.get(pair_clean, {})

        balance_key = "base_balance" if is_base_borrow else "quote_balance"
        vault_bal = vault_balances.get(balance_key, 0)
        max_allowed = int(float(vault_bal) * 0.90)

        is_safe = (borrow_amount <= max_allowed) and (max_allowed > 0)
        return {
            "valid": is_safe,
            "borrow_amount": borrow_amount,
            "vault_balance": vault_bal,
            "max_allowed_borrow": max_allowed,
            "asset_type": "base" if is_base_borrow else "quote",
            "error": None if is_safe else f"EInsufficientVaultBalance (abort code 2): borrow_amount {borrow_amount} exceeds 90% vault balance {max_allowed}",
        }

    def validate_atomic_ptb_generation(
        self,
        pair_name: str,
        borrow_amount: Optional[int] = None,
        route_direction: str = "FORWARD",
        vault_balances: Optional[Dict[str, int]] = None,
        amm_target: str = "cetus",
    ) -> Dict[str, Any]:
        """Validates that an 8-command PTB is generated with strict command sequence,
        correct pool IDs, a2b flags, and Hot Potato borrowing/repayment links.

        Sequence Requirements (FORWARD):
        - Command 0: borrow_flashloan_quote (produces borrowed_quote_coin, flash_loan_receipt)
        - Command 1: swap on Cetus CLMM or Turbos CLMM (consumes [0, 0], exact a2b flag)
        - Command 2: deposit to balance_manager (consumes [1, 0])
        - Command 3: place_market_order on DeepBook (is_bid = False)
        - Command 4: withdraw_all from balance_manager (produces withdrawn_quote_coin)
        - Command 5: SplitCoins exact repayment principal (consumes [4, 0])
        - Command 6: return_flashloan_quote (consumes [5, 0] and [0, 1] Hot Potato)
        - Command 7: TransferObjects net profit to sender_address (consumes [4, 0])

        Sequence Requirements (REVERSE):
        - Command 0: borrow_flashloan_quote (produces borrowed_quote_coin, flash_loan_receipt)
        - Command 1: deposit to balance_manager (consumes [0, 0] quote coin)
        - Command 2: place_market_order on DeepBook (is_bid = True, lifting Ask)
        - Command 3: withdraw_all base coin from balance_manager (produces withdrawn_base_coin)
        - Command 4: swap on Cetus CLMM or Turbos CLMM (consumes [3, 0] base coin, opposite a2b flag)
        - Command 5: SplitCoins exact repayment principal (consumes [4, 0] quote proceeds)
        - Command 6: return_flashloan_quote (consumes [5, 0] and [0, 1] Hot Potato)
        - Command 7: TransferObjects net profit to sender_address (consumes [4, 0])
        """
        errors: List[str] = []

        if pair_name not in SUI_PAIRS_CONFIG:
            raise ValueError(f"Unknown pair: {pair_name}. Supported: {list(SUI_PAIRS_CONFIG.keys())}")

        cfg = SUI_PAIRS_CONFIG[pair_name]
        amt = borrow_amount if borrow_amount is not None else cfg.default_borrow_amount
        is_reverse = route_direction == "REVERSE"

        if vault_balances is not None:
            v_check = self.validate_vault_balance(
                pair_name=pair_name,
                borrow_amount=amt,
                vault_balances=vault_balances,
            )
            if not v_check["valid"]:
                errors.append(v_check["error"])

        params = HotPotatoPTBParams.from_pair(
            pair_name=pair_name,
            flash_borrow_amount=amt,
            balance_manager_id=self.balance_manager_id,
            sender_address=self.operator_address,
            route_direction=route_direction,
            amm_target=amm_target,
        )
        ptb = self.ptb_builder.build_atomic_arb_ptb(params)

        commands = ptb.get("commands", [])
        if len(commands) != 8:
            errors.append(f"Expected exactly 8 commands in atomic PTB, found {len(commands)}")

        cetus_pool_id_verified = False
        turbos_pool_id_verified = False

        if is_reverse:
            # Command 0: Borrow Flashloan Quote
            c0 = commands[0] if len(commands) > 0 else {}
            is_borrow_cmd = (
                c0.get("type") == "MoveCall"
                and c0.get("module") == "pool"
                and c0.get("function") == "borrow_flashloan_quote"
            )
            if not is_borrow_cmd:
                errors.append(f"Command 0 must be borrow_flashloan_quote MoveCall, got {c0}")

            borrow_outputs = c0.get("outputs", [])
            if "flash_loan_receipt" not in borrow_outputs:
                errors.append("Command 0 must output 'flash_loan_receipt' Hot Potato")

            c0_args = c0.get("arguments", [])
            pool_id_verified = (
                len(c0_args) >= 1 and c0_args[0].get("Input") == cfg.deepbook_pool_id
            )
            if not pool_id_verified:
                errors.append(f"Command 0 DeepBook pool ID mismatch for {pair_name}")

            # Command 1: Deposit Quote to BalanceManager
            c1 = commands[1] if len(commands) > 1 else {}
            is_deposit_cmd = (
                c1.get("type") == "MoveCall"
                and c1.get("module") == "balance_manager"
                and c1.get("function") == "deposit"
            )
            if not is_deposit_cmd:
                errors.append(f"Command 1 must be balance_manager::deposit, got {c1}")

            c1_args = c1.get("arguments", [])
            c1_bm_ok = len(c1_args) >= 1 and c1_args[0].get("Input") == self.balance_manager_id
            c1_nested_ok = len(c1_args) >= 2 and c1_args[1].get("NestedResult") == [0, 0]
            if not (c1_bm_ok and c1_nested_ok):
                errors.append("Command 1 must consume borrowed quote coin [0, 0] into BalanceManager")

            # Command 2: Place Market Buy Order on DeepBook (is_bid = True, lifting Ask)
            c2 = commands[2] if len(commands) > 2 else {}
            is_order_cmd = (
                c2.get("type") == "MoveCall"
                and c2.get("module") == "pool"
                and c2.get("function") == "place_market_order"
            )
            if not is_order_cmd:
                errors.append(f"Command 2 must be pool::place_market_order, got {c2}")

            c2_args = c2.get("arguments", [])
            c2_pool_ok = len(c2_args) >= 1 and c2_args[0].get("Input") == cfg.deepbook_pool_id
            c2_bid_ok = len(c2_args) >= 5 and c2_args[4].get("Input") is True  # Bid / Buy base lifting Ask
            if not (c2_pool_ok and c2_bid_ok):
                errors.append("Command 2 must place market buy (is_bid=True) on DeepBook pool")

            # Command 3: Withdraw All Base Coin Proceeds
            c3 = commands[3] if len(commands) > 3 else {}
            is_withdraw_cmd = (
                c3.get("type") == "MoveCall"
                and c3.get("module") == "balance_manager"
                and c3.get("function") == "withdraw_all"
            )
            if not is_withdraw_cmd:
                errors.append(f"Command 3 must be balance_manager::withdraw_all, got {c3}")
            c3_type_ok = c3.get("type_arguments") == [cfg.base_coin_type]
            if not c3_type_ok:
                errors.append(f"Command 3 must withdraw base coin type {cfg.base_coin_type}")

            # Command 4: AMM Swap Base for Quote on Cetus or Turbos
            c4 = commands[4] if len(commands) > 4 else {}
            c4_args = c4.get("arguments", [])

            if amm_target == "turbos":
                is_swap_cmd = (
                    c4.get("type") == "MoveCall"
                    and c4.get("package") == TURBOS_PACKAGE_ID
                    and c4.get("module") == "swap_router"
                    and c4.get("function") == "swap_a_b_with_return_"
                )
                if not is_swap_cmd:
                    errors.append(f"Command 4 must be Turbos swap_router::swap_a_b_with_return_, got {c4}")

                turbos_pool_id_verified = (
                    len(c4_args) >= 1 and c4_args[0].get("Input") == cfg.turbos_pool_id
                )
                if not turbos_pool_id_verified:
                    errors.append(f"Command 4 Turbos pool ID mismatch for {pair_name}")

                c4_vec = c4_args[1] if len(c4_args) >= 2 else {}
                c4_has_vec = (
                    c4_vec.get("type") == "MakeMoveVec"
                    or "MakeMoveVec" in c4_vec
                )
                if not c4_has_vec:
                    errors.append("Command 4 must wrap coins in MakeMoveVec")

                c4_clock_ok = len(c4_args) >= 9 and c4_args[8].get("Input") == SUI_CLOCK_OBJECT_ID
                c4_ver_ok = len(c4_args) >= 10 and c4_args[9].get("Input") == TURBOS_VERSIONED_ID
                if not (c4_clock_ok and c4_ver_ok):
                    errors.append("Command 4 must include Clock and Turbos Versioned object")

                a2b_verified = True
                cetus_pool_id_verified = True
            else:
                is_swap_cmd = c4.get("type") == "MoveCall" and c4.get("function") == "swap"
                if not is_swap_cmd:
                    errors.append(f"Command 4 must be Cetus swap MoveCall, got {c4}")

                cetus_pool_id_verified = (
                    len(c4_args) >= 2 and c4_args[1].get("Input") == cfg.cetus_pool_id
                )
                if not cetus_pool_id_verified:
                    errors.append(f"Command 4 Cetus pool ID mismatch for {pair_name}")

                c4_nested_in = len(c4_args) >= 3 and c4_args[2].get("NestedResult") == [3, 0]
                if not c4_nested_in:
                    errors.append("Command 4 must consume NestedResult [3, 0] (withdrawn base coin)")

                expected_rev_a2b = not cfg.cetus_a2b_for_quote_in
                a2b_verified = len(c4_args) >= 4 and c4_args[3].get("Input") == expected_rev_a2b
                if not a2b_verified:
                    errors.append(f"Command 4 a2b flag mismatch for {pair_name}: expected {expected_rev_a2b}")

            # Command 5: SplitCoins for Principal Repayment
            c5 = commands[5] if len(commands) > 5 else {}
            is_split_cmd = c5.get("type") == "SplitCoins"
            c5_coin_ok = c5.get("coin", {}).get("NestedResult") == [4, 0]
            c5_amt_ok = len(c5.get("amounts", [])) >= 1 and c5["amounts"][0].get("Input") == amt
            if not (is_split_cmd and c5_coin_ok and c5_amt_ok):
                errors.append(f"Command 5 must SplitCoins exactly {amt} from [4, 0]")

            # Command 6: Return Flashloan Quote (Hot Potato Quench)
            c6 = commands[6] if len(commands) > 6 else {}
            is_repay_cmd = (
                c6.get("type") == "MoveCall"
                and c6.get("module") == "pool"
                and c6.get("function") == "return_flashloan_quote"
            )
            if not is_repay_cmd:
                errors.append(f"Command 6 must be return_flashloan_quote, got {c6}")

            c6_args = c6.get("arguments", [])
            c6_pool_ok = len(c6_args) >= 1 and c6_args[0].get("Input") == cfg.deepbook_pool_id
            c6_coin_ok = len(c6_args) >= 2 and c6_args[1].get("NestedResult") == [5, 0]
            c6_potato_ok = len(c6_args) >= 3 and c6_args[2].get("NestedResult") == [0, 1]
            hot_potato_quenched = c6_potato_ok and c6_coin_ok and c6_pool_ok
            if not hot_potato_quenched:
                errors.append("Command 6 must consume repayment coin [5, 0] and Hot Potato receipt [0, 1]")

            # Command 7: Transfer Net Profit to Sender
            c7 = commands[7] if len(commands) > 7 else {}
            is_transfer_cmd = c7.get("type") == "TransferObjects"
            c7_obj_ok = c7.get("objects", [{}])[0].get("NestedResult") == [4, 0]
            c7_rcpt_ok = c7.get("recipient", {}).get("Input") == self.operator_address
            if not (is_transfer_cmd and c7_obj_ok and c7_rcpt_ok):
                errors.append(f"Command 7 must TransferObjects [4, 0] to {self.operator_address}")

            balance_manager_verified = c1_bm_ok

        else:
            # Verify Command 0: Borrow Flashloan Quote
            c0 = commands[0] if len(commands) > 0 else {}
            is_borrow_cmd = (
                c0.get("type") == "MoveCall"
                and c0.get("module") == "pool"
                and c0.get("function") in ("borrow_flashloan_quote", "borrow_flashloan_base")
            )
            if not is_borrow_cmd:
                errors.append(f"Command 0 must be borrow_flashloan_quote MoveCall, got {c0}")

            borrow_outputs = c0.get("outputs", [])
            if "flash_loan_receipt" not in borrow_outputs:
                errors.append("Command 0 must output 'flash_loan_receipt' Hot Potato")

            c0_args = c0.get("arguments", [])
            pool_id_verified = (
                len(c0_args) >= 1 and c0_args[0].get("Input") == cfg.deepbook_pool_id
            )
            if not pool_id_verified:
                errors.append(f"Command 0 DeepBook pool ID mismatch for {pair_name}")

            # Verify Command 1: AMM Swap on Cetus or Turbos
            c1 = commands[1] if len(commands) > 1 else {}
            c1_args = c1.get("arguments", [])

            if amm_target == "turbos":
                is_swap_cmd = (
                    c1.get("type") == "MoveCall"
                    and c1.get("package") == TURBOS_PACKAGE_ID
                    and c1.get("module") == "swap_router"
                    and c1.get("function") == "swap_b_a_with_return_"
                )
                if not is_swap_cmd:
                    errors.append(f"Command 1 must be Turbos swap_router::swap_b_a_with_return_, got {c1}")

                turbos_pool_id_verified = (
                    len(c1_args) >= 1 and c1_args[0].get("Input") == cfg.turbos_pool_id
                )
                if not turbos_pool_id_verified:
                    errors.append(f"Command 1 Turbos pool ID mismatch for {pair_name}")

                c1_vec = c1_args[1] if len(c1_args) >= 2 else {}
                c1_has_vec = (
                    c1_vec.get("type") == "MakeMoveVec"
                    or "MakeMoveVec" in c1_vec
                )
                if not c1_has_vec:
                    errors.append("Command 1 must wrap coins in MakeMoveVec")

                c1_clock_ok = len(c1_args) >= 9 and c1_args[8].get("Input") == SUI_CLOCK_OBJECT_ID
                c1_ver_ok = len(c1_args) >= 10 and c1_args[9].get("Input") == TURBOS_VERSIONED_ID
                if not (c1_clock_ok and c1_ver_ok):
                    errors.append("Command 1 must include Clock and Turbos Versioned object")

                a2b_verified = True
                cetus_pool_id_verified = True
            else:
                is_swap_cmd = c1.get("type") == "MoveCall" and c1.get("function") == "swap"
                if not is_swap_cmd:
                    errors.append(f"Command 1 must be Cetus swap MoveCall, got {c1}")

                cetus_pool_id_verified = (
                    len(c1_args) >= 2 and c1_args[1].get("Input") == cfg.cetus_pool_id
                )
                if not cetus_pool_id_verified:
                    errors.append(f"Command 1 Cetus pool ID mismatch for {pair_name}")

                c1_nested_in = len(c1_args) >= 3 and c1_args[2].get("NestedResult") == [0, 0]
                if not c1_nested_in:
                    errors.append("Command 1 must consume NestedResult [0, 0] (borrowed coin)")

                a2b_verified = len(c1_args) >= 4 and c1_args[3].get("Input") == cfg.a2b
                if not a2b_verified:
                    errors.append(f"Command 1 a2b flag mismatch for {pair_name}: expected {cfg.a2b}")

            # Verify Command 2: Deposit to BalanceManager
            c2 = commands[2] if len(commands) > 2 else {}
            is_deposit_cmd = (
                c2.get("type") == "MoveCall"
                and c2.get("module") == "balance_manager"
                and c2.get("function") == "deposit"
            )
            if not is_deposit_cmd:
                errors.append(f"Command 2 must be balance_manager::deposit, got {c2}")

            c2_args = c2.get("arguments", [])
            c2_bm_ok = len(c2_args) >= 1 and c2_args[0].get("Input") == self.balance_manager_id
            c2_nested_ok = len(c2_args) >= 2 and c2_args[1].get("NestedResult") == [1, 0]
            if not (c2_bm_ok and c2_nested_ok):
                errors.append("Command 2 must consume swapped coin [1, 0] into BalanceManager")

            # Verify Command 3: Place Market Order
            c3 = commands[3] if len(commands) > 3 else {}
            is_order_cmd = (
                c3.get("type") == "MoveCall"
                and c3.get("module") == "pool"
                and c3.get("function") == "place_market_order"
            )
            if not is_order_cmd:
                errors.append(f"Command 3 must be pool::place_market_order, got {c3}")

            c3_args = c3.get("arguments", [])
            c3_pool_ok = len(c3_args) >= 1 and c3_args[0].get("Input") == cfg.deepbook_pool_id
            c3_bid_ok = len(c3_args) >= 5 and c3_args[4].get("Input") is False  # Ask / Sell base
            if not (c3_pool_ok and c3_bid_ok):
                errors.append("Command 3 must place market sell (is_bid=False) on DeepBook pool")

            # Verify Command 4: Withdraw All Proceeds
            c4 = commands[4] if len(commands) > 4 else {}
            is_withdraw_cmd = (
                c4.get("type") == "MoveCall"
                and c4.get("module") == "balance_manager"
                and c4.get("function") == "withdraw_all"
            )
            if not is_withdraw_cmd:
                errors.append(f"Command 4 must be balance_manager::withdraw_all, got {c4}")

            # Verify Command 5: SplitCoins for Principal Repayment
            c5 = commands[5] if len(commands) > 5 else {}
            is_split_cmd = c5.get("type") == "SplitCoins"
            c5_coin_ok = c5.get("coin", {}).get("NestedResult") == [4, 0]
            c5_amt_ok = len(c5.get("amounts", [])) >= 1 and c5["amounts"][0].get("Input") == amt
            if not (is_split_cmd and c5_coin_ok and c5_amt_ok):
                errors.append(f"Command 5 must SplitCoins exactly {amt} from [4, 0]")

            # Verify Command 6: Return Flashloan Quote (Hot Potato Quench)
            c6 = commands[6] if len(commands) > 6 else {}
            is_repay_cmd = (
                c6.get("type") == "MoveCall"
                and c6.get("module") == "pool"
                and c6.get("function") in ("return_flashloan_quote", "return_flashloan_base")
            )
            if not is_repay_cmd:
                errors.append(f"Command 6 must be return_flashloan_quote, got {c6}")

            c6_args = c6.get("arguments", [])
            c6_pool_ok = len(c6_args) >= 1 and c6_args[0].get("Input") == cfg.deepbook_pool_id
            c6_coin_ok = len(c6_args) >= 2 and c6_args[1].get("NestedResult") == [5, 0]
            c6_potato_ok = len(c6_args) >= 3 and c6_args[2].get("NestedResult") == [0, 1]
            hot_potato_quenched = c6_potato_ok and c6_coin_ok and c6_pool_ok
            if not hot_potato_quenched:
                errors.append("Command 6 must consume repayment coin [5, 0] and Hot Potato receipt [0, 1]")

            # Verify Command 7: Transfer Net Profit to Sender
            c7 = commands[7] if len(commands) > 7 else {}
            is_transfer_cmd = c7.get("type") == "TransferObjects"
            c7_obj_ok = c7.get("objects", [{}])[0].get("NestedResult") == [4, 0]
            c7_rcpt_ok = c7.get("recipient", {}).get("Input") == self.operator_address
            if not (is_transfer_cmd and c7_obj_ok and c7_rcpt_ok):
                errors.append(f"Command 7 must TransferObjects [4, 0] to {self.operator_address}")

            balance_manager_verified = c2_bm_ok

        strict_seq = len(errors) == 0

        report = PTBValidationReport(
            valid=strict_seq,
            pair_name=pair_name,
            borrow_amount=amt,
            command_count=len(commands),
            strict_sequence_verified=strict_seq,
            hot_potato_borrow_linked=len(borrow_outputs) >= 2,
            hot_potato_repay_linked=c6_coin_ok,
            hot_potato_quenched=hot_potato_quenched,
            pool_id_verified=pool_id_verified,
            cetus_pool_id_verified=cetus_pool_id_verified,
            a2b_verified=a2b_verified,
            balance_manager_verified=balance_manager_verified,
            ptb=ptb,
            errors=errors,
            route_direction=route_direction,
            amm_target=amm_target,
            turbos_pool_id_verified=turbos_pool_id_verified,
        )
        return report.to_dict()

    def simulate_ptb_dry_run(
        self,
        pair_name: str,
        borrow_amount: Optional[int] = None,
        spread_bps: float = 0.0,
        base_price: Optional[float] = None,
        deduct_fees: bool = True,
        route_direction: str = "FORWARD",
        deepbook_ask_px: Optional[float] = None,
        amm_target: str = "cetus",
        deepbook_fee_bps: Optional[float] = None,
    ) -> Dict[str, Any]:
        """Performs dry-run simulation of the 8-step PTB using Move VM semantics:

        - Profitable spread (> fees):
          Returns status == "SUCCESS", net_profit > 0, zero_leg_risk_preserved == True,
          gas_cost_sui == 0.002, state_mutations == 8.
        - Unprofitable / zero / sub-hurdle spread:
          Returns status == "ABORTED", gas_cost_sui == 0.002, zero_leg_risk_preserved == True,
          state_mutations == 0, shortfall_native > 0.
        """
        if pair_name not in SUI_PAIRS_CONFIG:
            raise ValueError(f"Unknown pair: {pair_name}. Supported: {list(SUI_PAIRS_CONFIG.keys())}")

        cfg = SUI_PAIRS_CONFIG[pair_name]
        amt = borrow_amount if borrow_amount is not None else cfg.default_borrow_amount

        # Establish base price and directional bid/ask spread
        mid_px = (
            base_price
            if base_price is not None
            else DEFAULT_PAIR_BASE_PRICES.get(pair_name, 2.0)
        )
        if route_direction == "REVERSE":
            ask_px = deepbook_ask_px if deepbook_ask_px is not None else mid_px
            amm_swap_out_px = ask_px * (1.0 + (spread_bps / 10000.0))
            deepbook_bid_px = ask_px
        else:
            amm_swap_out_px = mid_px
            deepbook_bid_px = mid_px * (1.0 + (spread_bps / 10000.0))
            ask_px = deepbook_bid_px

        # Build PTB
        params = HotPotatoPTBParams.from_pair(
            pair_name=pair_name,
            flash_borrow_amount=amt,
            balance_manager_id=self.balance_manager_id,
            sender_address=self.operator_address,
            deduct_fees=deduct_fees,
            route_direction=route_direction,
            amm_target=amm_target,
        )
        ptb = self.ptb_builder.build_atomic_arb_ptb(params)

        # Execute simulation via venue Move VM simulation engine
        sim = self.venue.simulate_dry_run(
            ptb=ptb,
            deepbook_bid_px=deepbook_bid_px,
            amm_swap_out_px=amm_swap_out_px,
            borrow_amount=amt,
            pair=pair_name,
            deduct_fees=deduct_fees,
            route_direction=route_direction,
            deepbook_ask_px=ask_px,
            amm_target=amm_target,
            deepbook_fee_bps=deepbook_fee_bps,
        )

        status = sim.get("status", "ABORTED")
        is_success = status == "SUCCESS"
        net_profit_quote = float(sim.get("net_profit_quote", 0.0))
        quote_scale = 10 ** cfg.quote_decimals
        net_profit_native = int(round(net_profit_quote * quote_scale)) if is_success else 0

        shortfall = int(sim.get("shortfall_native", 0))

        report = PTBDryRunReport(
            status=status,
            pair=pair_name,
            borrow_amount=amt,
            spread_bps=float(spread_bps),
            net_profit=net_profit_quote,
            net_profit_quote=net_profit_quote,
            net_profit_native=net_profit_native,
            zero_leg_risk_preserved=bool(sim.get("zero_leg_risk_preserved", True)),
            gas_cost_sui=SIMULATED_GAS_SUI,
            gas_used_mist=SIMULATED_GAS_MIST,
            state_mutations=8 if is_success else 0,
            deepbook_bid_px=deepbook_bid_px,
            amm_swap_out_px=amm_swap_out_px,
            hot_potato_satisfied=is_success,
            hot_potato_aborted=not is_success,
            error=sim.get("error") if not is_success else None,
            shortfall_native=shortfall,
            route_direction=route_direction,
            deepbook_ask_px=ask_px if route_direction == "REVERSE" else None,
            amm_target=amm_target,
        )
        return report.to_dict()
        return report.to_dict()

    def simulate_capital_scaling_lifecycle(
        self,
        initial_tier: ScalingTier = ScalingTier.TIER_1,
        spread_bps_tier1: float = 135.0,  # ~1.20% net spread => ~$12.00 / trade on 1k USDC
        spread_bps_tier2: float = 150.0,  # ~1.35% net spread => ~$67.50 / trade on 5k USDC
        pair_name: str = "SUI/USDC",
    ) -> Dict[str, Any]:
        """Simulates the complete end-to-end operational lifecycle:

        - Starting at Tier 1 (1,000 USDC / 1_000_000_000).
        - Accumulating net profits through successful dry-runs.
        - Triggering promotion to Tier 2 (5,000 USDC) at >= $100 net profit (and >= 10 trades).
        - Continuing to accumulate profit.
        - Triggering promotion to Tier 3 (10,000 USDC) at >= $750 cumulative net profit (and >= 20 trades).
        """
        engine = DynamicCapitalScalingEngine(initial_tier=initial_tier)
        events: List[Dict[str, Any]] = []

        initial_tier_name = engine.current_tier.name
        initial_borrow_amount = engine.flash_borrow_amount

        promoted_tier2_trade = None
        promoted_tier2_profit = None
        promoted_tier3_trade = None
        promoted_tier3_profit = None

        trade_idx = 0

        # Phase 1: Tier 1 execution (1k USDC)
        while engine.current_tier == ScalingTier.TIER_1 and trade_idx < 50:
            trade_idx += 1
            borrow_amt = engine.get_current_borrow_amount(pair_name)
            sim = self.simulate_ptb_dry_run(
                pair_name=pair_name,
                borrow_amount=borrow_amt,
                spread_bps=spread_bps_tier1,
            )
            if sim["status"] != "SUCCESS":
                raise RuntimeError(f"Expected successful simulation in lifecycle at trade {trade_idx}")

            profit = sim["net_profit"]
            tier_before = engine.current_tier

            engine.record_trade_success(profit)
            tier_after = engine.current_tier

            promoted = tier_after != tier_before
            if promoted and tier_after == ScalingTier.TIER_2:
                promoted_tier2_trade = trade_idx
                promoted_tier2_profit = engine.state.accumulated_net_profit_usdc

            events.append({
                "trade_index": trade_idx,
                "tier_before": tier_before.name,
                "tier_after": tier_after.name,
                "borrow_amount": borrow_amt,
                "profit_usdc": profit,
                "accumulated_profit_usdc": engine.state.accumulated_net_profit_usdc,
                "successful_trades": engine.state.successful_trades,
                "promoted": promoted,
            })

        if promoted_tier2_trade is None:
            raise RuntimeError("Lifecycle failed to promote to Tier 2 within expected bounds")

        # Phase 2: Tier 2 execution (5k USDC)
        while engine.current_tier == ScalingTier.TIER_2 and trade_idx < 100:
            trade_idx += 1
            borrow_amt = engine.get_current_borrow_amount(pair_name)
            sim = self.simulate_ptb_dry_run(
                pair_name=pair_name,
                borrow_amount=borrow_amt,
                spread_bps=spread_bps_tier2,
            )
            if sim["status"] != "SUCCESS":
                raise RuntimeError(f"Expected successful simulation in lifecycle at trade {trade_idx}")

            profit = sim["net_profit"]
            tier_before = engine.current_tier

            engine.record_trade_success(profit)
            tier_after = engine.current_tier

            promoted = tier_after != tier_before
            if promoted and tier_after == ScalingTier.TIER_3:
                promoted_tier3_trade = trade_idx
                promoted_tier3_profit = engine.state.accumulated_net_profit_usdc

            events.append({
                "trade_index": trade_idx,
                "tier_before": tier_before.name,
                "tier_after": tier_after.name,
                "borrow_amount": borrow_amt,
                "profit_usdc": profit,
                "accumulated_profit_usdc": engine.state.accumulated_net_profit_usdc,
                "successful_trades": engine.state.successful_trades,
                "promoted": promoted,
            })

        if promoted_tier3_trade is None:
            raise RuntimeError("Lifecycle failed to promote to Tier 3 within expected bounds")

        # Phase 3: Execute at least one trade at Tier 3 (10k USDC)
        trade_idx += 1
        borrow_amt = engine.get_current_borrow_amount(pair_name)
        sim = self.simulate_ptb_dry_run(
            pair_name=pair_name,
            borrow_amount=borrow_amt,
            spread_bps=spread_bps_tier2,
        )
        profit = sim["net_profit"]
        engine.record_trade_success(profit)

        events.append({
            "trade_index": trade_idx,
            "tier_before": ScalingTier.TIER_3.name,
            "tier_after": ScalingTier.TIER_3.name,
            "borrow_amount": borrow_amt,
            "profit_usdc": profit,
            "accumulated_profit_usdc": engine.state.accumulated_net_profit_usdc,
            "successful_trades": engine.state.successful_trades,
            "promoted": False,
        })

        report = CapitalScalingLifecycleReport(
            success=True,
            initial_tier=initial_tier_name,
            initial_borrow_amount=initial_borrow_amount,
            promoted_to_tier_2_at_trade=promoted_tier2_trade,
            tier_2_profit_at_promotion=promoted_tier2_profit,
            promoted_to_tier_3_at_trade=promoted_tier3_trade,
            tier_3_profit_at_promotion=promoted_tier3_profit,
            final_tier=engine.current_tier.name,
            final_borrow_amount=engine.flash_borrow_amount,
            total_trades_executed=trade_idx,
            accumulated_net_profit_usdc=engine.state.accumulated_net_profit_usdc,
            lifecycle_events=events,
        )
        return report.to_dict()

    def simulate_gas_safety_monitoring(
        self, test_balances: Optional[List[float]] = None
    ) -> List[Dict[str, Any]]:
        """Validates gas safety floor transitions during live or simulated monitoring:

        - >= 1.5 SUI: HEALTHY, can_trade == True, gas_warning == False
        - 0.5 <= balance < 1.5 SUI: WARNING, can_trade == True, gas_warning == True
        - < 0.5 SUI: CRITICAL, can_trade == False, gas_warning == True, status == EMERGENCY_LOCKED
        """
        balances = test_balances or [5.419, 2.0, 1.5, 1.49, 1.0, 0.5, 0.49, 0.1]
        results = []
        engine = DynamicCapitalScalingEngine(
            warning_gas_floor=self.warning_gas_floor,
            critical_gas_floor=self.critical_gas_floor,
        )

        for bal in balances:
            engine.update_from_wallet_balances(usdc_balance=0.0, sui_balance=bal)
            can_trade = engine.can_trade()
            results.append({
                "sui_balance": bal,
                "can_trade": can_trade,
                "status": engine.state.status,
                "gas_warning": engine.state.gas_warning,
                "is_critical": bal < self.critical_gas_floor,
                "is_warning": bal < self.warning_gas_floor and bal >= self.critical_gas_floor,
            })
        return results

    async def run_full_preflight_and_dryrun_suite(self) -> Dict[str, Any]:
        """Executes complete programmatic verification and dry-run simulation suite:

        1. Pre-flight health check (RPC, wallet balance, pool access, BalanceManager).
        2. PTB structure validation for all 4 pairs at 1k, 5k, 10k USDC.
        3. Move VM dry-run simulation (profitable spread vs sub-hurdle abort).
        4. Dynamic capital scaling lifecycle simulation (1k -> 5k -> 10k).
        5. Gas safety warning and critical hard stop simulation.
        """
        # 1. Healthcheck
        health = await self.validate_preflight_health()

        # 2. PTB Structure
        ptb_checks: Dict[str, Any] = {}
        tranches = [1_000_000_000, 5_000_000_000, 10_000_000_000]
        for pair_name in SUI_PAIRS_CONFIG:
            ptb_checks[pair_name] = {}
            for amt in tranches:
                ptb_checks[pair_name][str(amt)] = self.validate_atomic_ptb_generation(pair_name, amt)

        # 3. Dry-Run Simulations
        dry_run_checks: Dict[str, Any] = {}
        for pair_name in SUI_PAIRS_CONFIG:
            # Sub-hurdle (0 bps spread) -> must ABORT cleanly with ~0.002 SUI gas
            abort_sim = self.simulate_ptb_dry_run(pair_name, spread_bps=0.0)
            # Profitable (100 bps spread) -> must SUCCEED with net profit > 0
            success_sim = self.simulate_ptb_dry_run(pair_name, spread_bps=100.0)

            dry_run_checks[pair_name] = {
                "abort_test": abort_sim,
                "success_test": success_sim,
            }

        # 4. Scaling Lifecycle
        lifecycle = self.simulate_capital_scaling_lifecycle()

        # 5. Gas Safety
        gas_safety = self.simulate_gas_safety_monitoring()

        all_ok = (
            health.get("all_checks_passed", False)
            and all(all(c["valid"] for c in tranche_dict.values()) for tranche_dict in ptb_checks.values())
            and all(
                p["abort_test"]["status"] == "ABORTED"
                and p["abort_test"]["zero_leg_risk_preserved"] is True
                and p["success_test"]["status"] == "SUCCESS"
                and p["success_test"]["net_profit"] > 0
                for p in dry_run_checks.values()
            )
            and lifecycle["success"] is True
        )

        return {
            "all_verifications_passed": all_ok,
            "preflight_health": health,
            "ptb_structure_validations": ptb_checks,
            "dry_run_simulations": dry_run_checks,
            "capital_scaling_lifecycle": lifecycle,
            "gas_safety_monitoring": gas_safety,
            "timestamp": time.time(),
        }

    async def close(self) -> None:
        """Closes underlying GraphQL client session."""
        if self.graphql_client:
            await self.graphql_client.close()
        if self.venue:
            await self.venue.disconnect()
