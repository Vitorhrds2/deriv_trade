#!/usr/bin/env python3
"""D107 intentional winner holding prototype for the Deriv Demo account.

The implementation deliberately manages only D107-created 1HZ10V 400x
MULTUP/MULTDOWN contracts. It cancels a validated loser at the API-confirmed
5-minute cancellation boundary and records a validated winner as held. The v0
path has no automated winner sale.
"""
from __future__ import annotations

import asyncio
import json
import math
import os
import random
import re
import shutil
import tempfile
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence

from dotenv import load_dotenv

from deriv_client import DerivClient

load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))


HYPOTHESIS = "D107"
SYMBOL = "1HZ10V"
CONTRACT_TYPES = ("MULTUP", "MULTDOWN")
MULTIPLIER = 400
CANCELLATION = "5m"
MIN_STAKE = 0.35
HARD_MAX_STAKE = 10.00
DEFAULT_STAKE = 1.00
DEFAULT_MAX_OPEN_POSITIONS = 10
DEFAULT_MAX_DEPLOYED_PCT = 0.20
DEFAULT_SESSION_LOSS_STOP_PCT = 0.50
DEFAULT_MODE = "canary"
DEFAULT_CANARY_BUYS = 5
DEFAULT_INTER_TRIAL_SECONDS = 15.0
DEFAULT_BOUNDARY_BUFFER_SECONDS = 15.0
DEFAULT_PORTFOLIO_SNAPSHOT_SECONDS = 60.0
DEFAULT_OBSERVATION_LOG_SECONDS = 300.0
DEFAULT_MIN_FREE_BYTES = 100 * 1024 * 1024
DEFAULT_LOG_RAW_OBSERVATIONS = False
DEFAULT_UNRESOLVED_LOSS_ACTION = "sell"
DEFAULT_RESULTS_FILE = "d107_rate_limit_winner_holding_results.jsonl"
DEFAULT_STATE_FILE = "d107_rate_limit_winner_holding_state.json"
MAX_CANCEL_RETRIES = 3
MAX_SELL_RETRIES = 3
CANCEL_RETRY_SAFETY_SECONDS = 0.5
OPEN_LIFECYCLES = {
    "buy_confirmed",
    "cancellation_window_monitoring",
    "cancel_requested",
    "held_winner",
}
TERMINAL_LIFECYCLES = {
    "closed_loser",
    "closed_target",
    "closed_external",
    "auto_stopped",
    "closed_unresolved_loss",
    "cancellation_window_missed",
    "cancel_failed",
    "sell_failed",
    "unresolved",
}
TERMINAL_STATUSES = {"sold", "expired", "cancelled", "closed", "settled"}
RECOVERABLE_GUARDRAIL_STOPS = {
    "max_open_positions",
    "max_deployed_capital",
    "portfolio_snapshot_failure",
    "reconciliation_required",
}


class D107Error(RuntimeError):
    """Base error for fail-closed D107 operation."""


class ConfigError(D107Error, ValueError):
    """Raised when a locked v0 parameter is unsafe or malformed."""


class StateError(D107Error):
    """Raised when persisted state cannot be trusted."""


class ReconciliationRequired(D107Error):
    """Raised when live portfolio and persisted lifecycle cannot be matched."""


class ApiRequestError(D107Error):
    """Transport error with an explicit indication of request ambiguity."""

    def __init__(self, message: str, *, ambiguous: bool = False):
        super().__init__(message)
        self.ambiguous = ambiguous


_DURATION_RE = re.compile(r"^(\d+)([smhd])$")
_SHORTCODE_RE = re.compile(
    r"^(?P<contract_type>MULTUP|MULTDOWN)_(?P<symbol>.+?)_"
    r"(?P<stake>[0-9]+(?:\.[0-9]+)?)_(?P<multiplier>\d+)_"
    r"(?P<purchase_time>\d+)"
)
_SECRET_KEY_RE = re.compile(r"(?i)(token|secret|password|authorization|api[_-]?key|private[_-]?key)")
_SECRET_VALUE_RE = re.compile(r"(?i)\bpat_[A-Za-z0-9_-]+\b")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def _finite_float(value: Any) -> Optional[float]:
    if value is None or isinstance(value, bool):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def _positive_float(value: Any) -> Optional[float]:
    result = _finite_float(value)
    return result if result is not None and result > 0 else None


def _finite_int(value: Any) -> Optional[int]:
    result = _finite_float(value)
    if result is None or not result.is_integer():
        return None
    return int(result)


def _api_bool(value: Any) -> Optional[bool]:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)) and math.isfinite(float(value)):
        if value == 1:
            return True
        if value == 0:
            return False
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes"}:
            return True
        if normalized in {"0", "false", "no"}:
            return False
    return None


def _api_contract_id(contract_id: Any) -> Any:
    s = str(contract_id)
    return int(s) if s.isdigit() else contract_id


def _safe_error_message(value: Any) -> str:
    message = str(value)
    message = _SECRET_VALUE_RE.sub("<redacted>", message)
    return message[:500]


def redact_for_log(value: Any, key: Optional[str] = None) -> Any:
    """Remove credential-like fields before anything reaches state or JSONL."""
    if key and _SECRET_KEY_RE.search(key):
        return "<redacted>"
    if isinstance(value, Mapping):
        return {str(k): redact_for_log(v, str(k)) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [redact_for_log(item) for item in value]
    if isinstance(value, str):
        return _SECRET_VALUE_RE.sub("<redacted>", value)
    return value


def parse_duration(value: str) -> int:
    if not isinstance(value, str):
        raise ConfigError(f"Invalid duration: {value!r}")
    match = _DURATION_RE.fullmatch(value.strip())
    if not match:
        raise ConfigError(f"Invalid duration: {value!r}")
    amount, unit = match.groups()
    return int(amount) * {"s": 1, "m": 60, "h": 3600, "d": 86400}[unit]


def _env_value(env: Mapping[str, str], key: str, default: str) -> str:
    value = env.get(key, default)
    if value is None or not str(value).strip():
        raise ConfigError(f"{key} must not be empty")
    return str(value).strip()


def _env_float(env: Mapping[str, str], key: str, default: float) -> float:
    raw = env.get(key)
    if raw is None:
        return float(default)
    try:
        value = float(raw)
    except (TypeError, ValueError) as exc:
        raise ConfigError(f"{key} must be numeric") from exc
    if not math.isfinite(value):
        raise ConfigError(f"{key} must be finite")
    return value


def _env_int(env: Mapping[str, str], key: str, default: int) -> int:
    raw = env.get(key)
    if raw is None:
        return int(default)
    try:
        value = int(raw)
    except (TypeError, ValueError) as exc:
        raise ConfigError(f"{key} must be an integer") from exc
    return value


def _env_bool(env: Mapping[str, str], key: str, default: bool) -> bool:
    raw = env.get(key)
    if raw is None:
        return default
    normalized = str(raw).strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ConfigError(f"{key} must be boolean")


@dataclass(frozen=True)
class D107Config:
    symbol: str = SYMBOL
    stake: float = DEFAULT_STAKE
    max_stake: float = HARD_MAX_STAKE
    multiplier: int = MULTIPLIER
    cancellation: str = CANCELLATION
    max_open_positions: int = DEFAULT_MAX_OPEN_POSITIONS
    max_deployed_pct: float = DEFAULT_MAX_DEPLOYED_PCT
    session_loss_stop_pct: float = DEFAULT_SESSION_LOSS_STOP_PCT
    mode: str = DEFAULT_MODE
    canary_buys: int = DEFAULT_CANARY_BUYS
    inter_trial_seconds: float = DEFAULT_INTER_TRIAL_SECONDS
    boundary_buffer_seconds: float = DEFAULT_BOUNDARY_BUFFER_SECONDS
    portfolio_snapshot_seconds: float = DEFAULT_PORTFOLIO_SNAPSHOT_SECONDS
    observation_log_seconds: float = DEFAULT_OBSERVATION_LOG_SECONDS
    min_free_bytes: int = DEFAULT_MIN_FREE_BYTES
    log_raw_observations: bool = DEFAULT_LOG_RAW_OBSERVATIONS
    unresolved_loss_action: str = DEFAULT_UNRESOLVED_LOSS_ACTION
    results_file: str = DEFAULT_RESULTS_FILE
    state_file: str = DEFAULT_STATE_FILE
    expected_account_id: Optional[str] = None
    auto_sell_winners: bool = False
    winner_exit_multiple: float = 8.0
    winner_trailing_stop_pct: float = 0.50
    winner_min_profit_to_trail: float = 1.0
    winner_max_hold_seconds: float = 900.0
    winner_capital_preservation_loss: float = 0.35
    check_regime_supervisor: bool = False
    regime_policy_file: str = "market_regime_policy.json"
    min_regime_hurst: float = 0.48
    in_window_auto_sell: bool = False
    in_window_take_profit: Optional[float] = 0.35
    in_window_trailing_stop_pct: Optional[float] = 0.30
    in_window_min_profit_to_trail: float = 0.25
    dynamic_asset_rotation: bool = False
    trend_alignment_enabled: bool = False

    @classmethod
    def from_env(cls, env: Optional[Mapping[str, str]] = None) -> "D107Config":
        source = os.environ if env is None else env
        expected = source.get("D107_EXPECTED_ACCOUNT_ID") or None
        config = cls(
            symbol=_env_value(source, "D107_SYMBOL", SYMBOL),
            stake=_env_float(source, "D107_STAKE", DEFAULT_STAKE),
            max_stake=_env_float(source, "D107_MAX_STAKE", HARD_MAX_STAKE),
            multiplier=_env_int(source, "D107_MULTIPLIER", MULTIPLIER),
            cancellation=_env_value(source, "D107_CANCELLATION", CANCELLATION),
            max_open_positions=_env_int(source, "D107_MAX_OPEN_POSITIONS", DEFAULT_MAX_OPEN_POSITIONS),
            max_deployed_pct=_env_float(source, "D107_MAX_DEPLOYED_PCT", DEFAULT_MAX_DEPLOYED_PCT),
            session_loss_stop_pct=_env_float(
                source, "D107_SESSION_LOSS_STOP_PCT", DEFAULT_SESSION_LOSS_STOP_PCT
            ),
            mode=_env_value(source, "D107_MODE", DEFAULT_MODE).lower(),
            canary_buys=_env_int(source, "D107_CANARY_BUYS", DEFAULT_CANARY_BUYS),
            inter_trial_seconds=_env_float(
                source, "D107_INTER_TRIAL_SECONDS", DEFAULT_INTER_TRIAL_SECONDS
            ),
            boundary_buffer_seconds=_env_float(
                source, "D107_BOUNDARY_BUFFER_SECONDS", DEFAULT_BOUNDARY_BUFFER_SECONDS
            ),
            portfolio_snapshot_seconds=_env_float(
                source, "D107_PORTFOLIO_SNAPSHOT_SECONDS", DEFAULT_PORTFOLIO_SNAPSHOT_SECONDS
            ),
            observation_log_seconds=_env_float(
                source, "D107_OBSERVATION_LOG_SECONDS", DEFAULT_OBSERVATION_LOG_SECONDS
            ),
            min_free_bytes=_env_int(source, "D107_MIN_FREE_BYTES", DEFAULT_MIN_FREE_BYTES),
            log_raw_observations=_env_bool(
                source, "D107_LOG_RAW_OBSERVATIONS", DEFAULT_LOG_RAW_OBSERVATIONS
            ),
            unresolved_loss_action=_env_value(
                source, "D107_UNRESOLVED_LOSS_ACTION", DEFAULT_UNRESOLVED_LOSS_ACTION
            ).lower(),
            results_file=_env_value(source, "D107_RESULTS_FILE", DEFAULT_RESULTS_FILE),
            state_file=_env_value(source, "D107_STATE_FILE", DEFAULT_STATE_FILE),
            expected_account_id=expected,
            auto_sell_winners=_env_bool(source, "D107_AUTO_SELL_WINNERS", False),
            winner_exit_multiple=_env_float(source, "D107_WINNER_EXIT_MULTIPLE", 8.0),
            winner_trailing_stop_pct=_env_float(
                source, "D107_WINNER_TRAILING_STOP_PCT", 0.50
            ),
            winner_min_profit_to_trail=_env_float(
                source, "D107_WINNER_MIN_PROFIT_TO_TRAIL", 1.0
            ),
            winner_max_hold_seconds=_env_float(
                source, "D107_WINNER_MAX_HOLD_SECONDS", 900.0
            ),
            winner_capital_preservation_loss=_env_float(
                source, "D107_WINNER_CAPITAL_PRESERVATION_LOSS", 0.35
            ),
            check_regime_supervisor=_env_bool(
                source, "D107_CHECK_REGIME_SUPERVISOR", False
            ),
            regime_policy_file=_env_value(
                source, "D107_REGIME_POLICY_FILE", "market_regime_policy.json"
            ),
            min_regime_hurst=_env_float(
                source, "D107_MIN_REGIME_HURST", 0.48
            ),
            in_window_auto_sell=_env_bool(
                source, "D107_IN_WINDOW_AUTO_SELL", False
            ),
            in_window_take_profit=_env_float(
                source, "D107_IN_WINDOW_TP", 0.35
            ),
            in_window_trailing_stop_pct=_env_float(
                source, "D107_IN_WINDOW_TRAILING_STOP_PCT", 0.30
            ),
            in_window_min_profit_to_trail=_env_float(
                source, "D107_IN_WINDOW_MIN_PROFIT_TO_TRAIL", 0.25
            ),
            dynamic_asset_rotation=_env_bool(
                source, "D107_DYNAMIC_ASSET_ROTATION", False
            ),
            trend_alignment_enabled=_env_bool(
                source, "D107_TREND_ALIGNMENT", False
            ),
        )
        config.validate()
        return config

    @property
    def cancellation_seconds(self) -> int:
        return parse_duration(self.cancellation)

    def validate(self) -> None:
        errors = []
        allowed_symbols = {SYMBOL, "1HZ100V", "R_100", "1HZ75V", "R_75"}
        if self.symbol not in allowed_symbols:
            errors.append(f"symbol must be one of {sorted(allowed_symbols)}")
        allowed_multipliers = {100, 400}
        if self.multiplier not in allowed_multipliers:
            errors.append(f"multiplier must be one of {sorted(allowed_multipliers)}")
        if self.cancellation != CANCELLATION:
            errors.append(f"cancellation must be {CANCELLATION}")
        try:
            cancellation_seconds = self.cancellation_seconds
        except ConfigError as exc:
            errors.append(str(exc))
            cancellation_seconds = 0
        if self.stake < MIN_STAKE:
            errors.append(f"stake must be at least {MIN_STAKE:.2f}")
        if self.stake > HARD_MAX_STAKE:
            errors.append(f"stake must not exceed hard maximum {HARD_MAX_STAKE:.2f}")
        if self.max_stake < MIN_STAKE or self.max_stake > HARD_MAX_STAKE:
            errors.append(f"max_stake must be between {MIN_STAKE:.2f} and {HARD_MAX_STAKE:.2f}")
        if self.stake > self.max_stake:
            errors.append("stake must not exceed max_stake")
        if not 0 < self.max_open_positions <= DEFAULT_MAX_OPEN_POSITIONS:
            errors.append(f"max_open_positions must be in (0, {DEFAULT_MAX_OPEN_POSITIONS}]")
        if not 0 < self.max_deployed_pct <= DEFAULT_MAX_DEPLOYED_PCT:
            errors.append(f"max_deployed_pct must be in (0, {DEFAULT_MAX_DEPLOYED_PCT}]")
        if not 0 < self.session_loss_stop_pct <= DEFAULT_SESSION_LOSS_STOP_PCT:
            errors.append(
                f"session_loss_stop_pct must be in (0, {DEFAULT_SESSION_LOSS_STOP_PCT}]"
            )
        if self.mode not in {"canary", "continuous"}:
            errors.append("mode must be canary or continuous")
        if self.canary_buys <= 0:
            errors.append("canary_buys must be positive")
        for name, value in (
            ("inter_trial_seconds", self.inter_trial_seconds),
            ("boundary_buffer_seconds", self.boundary_buffer_seconds),
            ("portfolio_snapshot_seconds", self.portfolio_snapshot_seconds),
            ("observation_log_seconds", self.observation_log_seconds),
        ):
            if not math.isfinite(value) or value <= 0:
                errors.append(f"{name} must be positive and finite")
        if self.min_free_bytes <= 0:
            errors.append("min_free_bytes must be positive")
        if cancellation_seconds and self.boundary_buffer_seconds >= cancellation_seconds:
            errors.append("boundary_buffer_seconds must be less than cancellation duration")
        if not self.results_file or not self.state_file:
            errors.append("results_file and state_file must not be empty")
        if self.expected_account_id is not None and not self.expected_account_id.strip():
            errors.append("expected_account_id must not be empty")
        if not math.isfinite(self.winner_exit_multiple) or self.winner_exit_multiple < 1.0:
            errors.append("winner_exit_multiple must be finite and at least 1.0")
        if not 0.0 < self.winner_trailing_stop_pct <= 1.0:
            errors.append("winner_trailing_stop_pct must be in (0, 1.0]")
        if self.winner_min_profit_to_trail < 0.0:
            errors.append("winner_min_profit_to_trail must be non-negative")
        if self.winner_max_hold_seconds <= 0.0:
            errors.append("winner_max_hold_seconds must be positive")
        if self.winner_capital_preservation_loss < 0.0:
            errors.append("winner_capital_preservation_loss must be non-negative")
        if self.unresolved_loss_action not in {"sell", "pause"}:
            errors.append("unresolved_loss_action must be sell or pause")
        if errors:
            raise ConfigError("D107 configuration invalid: " + "; ".join(errors))

    def prepare_paths(self) -> None:
        self.validate()
        results_path = os.path.abspath(os.path.expanduser(self.results_file))
        state_path = os.path.abspath(os.path.expanduser(self.state_file))
        if results_path == state_path:
            raise ConfigError("results_file and state_file must be different files")
        for raw_path in (self.results_file, self.state_file):
            path = Path(raw_path).expanduser()
            parent = path.parent if str(path.parent) else Path(".")
            try:
                parent.mkdir(parents=True, exist_ok=True)
                if path.exists() and (not path.is_file() or not os.access(path, os.W_OK)):
                    raise OSError(f"path is not a writable file: {path}")
                if not os.access(parent, os.W_OK):
                    raise OSError(f"directory is not writable: {parent}")
            except OSError as exc:
                raise ConfigError(f"D107 path is not writable: {path}") from exc


def validate_config(config: D107Config) -> D107Config:
    config.validate()
    return config


def parse_shortcode(shortcode: Any) -> dict[str, Any]:
    if not isinstance(shortcode, str):
        return {}
    match = _SHORTCODE_RE.match(shortcode.strip())
    if not match:
        return {}
    values = match.groupdict()
    return {
        "contract_type": values["contract_type"],
        "symbol": values["symbol"],
        "stake": float(values["stake"]),
        "multiplier": int(values["multiplier"]),
        "purchase_time": int(values["purchase_time"]),
    }


def contract_metadata(contract: Mapping[str, Any]) -> dict[str, Any]:
    shortcode = contract.get("shortcode", "")
    parsed = parse_shortcode(shortcode)
    contract_type = contract.get("contract_type") or parsed.get("contract_type")
    symbol = (
        contract.get("underlying_symbol")
        or contract.get("underlying")
        or contract.get("symbol")
        or parsed.get("symbol")
    )
    multiplier = _finite_int(contract.get("multiplier")) or parsed.get("multiplier")
    stake = _positive_float(contract.get("amount"))
    if stake is None:
        stake = _positive_float(contract.get("stake"))
    if stake is None:
        stake = parsed.get("stake")
    purchase_time = _finite_float(contract.get("purchase_time"))
    if purchase_time is None:
        purchase_time = _finite_float(contract.get("date_start"))
    if purchase_time is None:
        purchase_time = parsed.get("purchase_time")
    return {
        "contract_id": contract.get("contract_id"),
        "contract_type": contract_type,
        "symbol": symbol,
        "multiplier": multiplier,
        "stake": stake,
        "shortcode": shortcode,
        "purchase_time": purchase_time,
        "buy_price": _positive_float(contract.get("buy_price")),
    }


def is_matching_position(contract: Mapping[str, Any], config: D107Config) -> bool:
    metadata = contract_metadata(contract)
    contract_symbol = metadata.get("symbol")
    symbol_matches = (contract_symbol == config.symbol) or (
        config.dynamic_asset_rotation
        and contract_symbol in {SYMBOL, config.symbol, "1HZ100V", "R_100", "1HZ75V", "R_75"}
    )
    return (
        metadata.get("contract_type") in CONTRACT_TYPES
        and symbol_matches
        and metadata.get("multiplier") == config.multiplier
    )


def classify_portfolio_contracts(
    contracts: Sequence[Mapping[str, Any]], config: D107Config
) -> tuple[list[Mapping[str, Any]], list[Mapping[str, Any]]]:
    matching: list[Mapping[str, Any]] = []
    unknown: list[Mapping[str, Any]] = []
    allowed_symbols = (
        {SYMBOL, config.symbol, "1HZ100V", "R_100", "1HZ75V", "R_75"}
        if config.dynamic_asset_rotation
        else {config.symbol}
    )
    for contract in contracts:
        metadata = contract_metadata(contract)
        contract_type = metadata.get("contract_type")
        symbol = metadata.get("symbol")
        multiplier = metadata.get("multiplier")
        if contract_type not in CONTRACT_TYPES:
            continue
        if symbol is not None and symbol not in allowed_symbols:
            continue
        if multiplier is not None and multiplier != config.multiplier:
            continue
        matching_candidate = is_matching_position(contract, config)
        if matching_candidate and contract.get("contract_id") is not None:
            matching.append(contract)
        else:
            unknown.append(contract)
    return matching, unknown


def reconstruct_directional_pnl(
    contract_type: str,
    entry_spot: Any,
    current_spot: Any,
    stake: Any,
    multiplier: Any,
) -> Optional[float]:
    entry = _positive_float(entry_spot)
    current = _positive_float(current_spot)
    amount = _positive_float(stake)
    mult = _positive_float(multiplier)
    if entry is None or current is None or amount is None or mult is None:
        return None
    if contract_type == "MULTUP":
        return (current - entry) / entry * amount * mult
    if contract_type == "MULTDOWN":
        return (entry - current) / entry * amount * mult
    return None


@dataclass(frozen=True)
class PnlDecision:
    classification: str
    pnl_source: str
    pnl: Optional[float]
    api_profit: Optional[float]
    reconstructed_profit: Optional[float]
    reason: str


def _pnl_sign(value: Optional[float], epsilon: float = 1e-9) -> int:
    if value is None or abs(value) <= epsilon:
        return 0
    return 1 if value > 0 else -1


def classify_pnl(
    api_profit: Any,
    reconstructed_profit: Any,
    *,
    api_coherent: bool = False,
    epsilon: float = 1e-9,
) -> PnlDecision:
    api_value = _finite_float(api_profit)
    reconstructed_value = _finite_float(reconstructed_profit)
    api_sign = _pnl_sign(api_value, epsilon)
    reconstructed_sign = _pnl_sign(reconstructed_value, epsilon)

    if api_value is not None and reconstructed_value is not None:
        if api_sign and reconstructed_sign and api_sign != reconstructed_sign:
            return PnlDecision(
                "unresolved", "unknown", None, api_value, reconstructed_value,
                "API profit contradicts independent reconstruction",
            )
        if api_sign == 0 and reconstructed_sign != 0:
            selected = reconstructed_value
            source = "reconstructed"
        elif reconstructed_sign == 0 and api_sign != 0:
            return PnlDecision(
                "unresolved", "unknown", None, api_value, reconstructed_value,
                "API profit contradicts break-even reconstruction",
            )
        elif api_coherent:
            selected = api_value
            source = "api"
        else:
            selected = reconstructed_value
            source = "reconstructed"
    elif api_value is not None and api_coherent:
        selected = api_value
        source = "api"
    elif reconstructed_value is not None:
        selected = reconstructed_value
        source = "reconstructed"
    else:
        return PnlDecision("unresolved", "unknown", None, api_value, reconstructed_value, "no reliable P&L evidence")

    selected_sign = _pnl_sign(selected, epsilon)
    if selected_sign > 0:
        classification = "validated_winner"
    elif selected_sign < 0:
        classification = "validated_loss"
    else:
        classification = "neutral"
        source = "neutral"
    return PnlDecision(classification, source, selected, api_value, reconstructed_value, "coherent P&L evidence")


@dataclass(frozen=True)
class PnlEvidence:
    decision: PnlDecision
    entry_spot: Optional[float]
    current_spot: Optional[float]
    bid_price: Optional[float]
    is_valid_to_cancel: Optional[bool]
    is_valid_to_sell: Optional[bool]
    contract_id: Optional[Any]
    raw: Mapping[str, Any]

    def as_log_record(self) -> dict[str, Any]:
        return {
            "classification": self.decision.classification,
            "pnl_source": self.decision.pnl_source,
            "profit_at_action": self.decision.pnl,
            "api_profit": self.decision.api_profit,
            "reconstructed_profit": self.decision.reconstructed_profit,
            "pnl_reason": self.decision.reason,
            "entry_spot": self.entry_spot,
            "current_spot": self.current_spot,
            "bid_price_at_action": self.bid_price,
            "is_valid_to_cancel": self.is_valid_to_cancel,
            "is_valid_to_sell": self.is_valid_to_sell,
        }


def pnl_evidence_from_contract(
    raw: Mapping[str, Any],
    metadata: Mapping[str, Any],
    *,
    fallback_entry_spot: Any = None,
    fallback_current_spot: Any = None,
) -> PnlEvidence:
    direct_entry = _positive_float(raw.get("entry_spot"))
    direct_current = _positive_float(raw.get("current_spot"))
    entry = direct_entry or _positive_float(fallback_entry_spot)
    current = direct_current or _positive_float(fallback_current_spot)
    contract_type = raw.get("contract_type") or metadata.get("contract_type")
    stake = _positive_float(raw.get("amount")) or _positive_float(metadata.get("stake"))
    multiplier = _positive_float(raw.get("multiplier")) or _positive_float(metadata.get("multiplier"))
    reconstructed = reconstruct_directional_pnl(contract_type, entry, current, stake, multiplier)
    api_profit = _finite_float(raw.get("profit")) if "profit" in raw else None
    bid_price = _finite_float(raw.get("bid_price"))
    valid_cancel = _api_bool(raw.get("is_valid_to_cancel")) if "is_valid_to_cancel" in raw else None
    valid_sell = _api_bool(raw.get("is_valid_to_sell")) if "is_valid_to_sell" in raw else None
    api_coherent = all(
        value is not None
        for value in (
            api_profit,
            entry,
            current,
            bid_price,
            valid_cancel,
            valid_sell,
            raw.get("contract_id") or metadata.get("contract_id"),
        )
    )
    decision = classify_pnl(api_profit, reconstructed, api_coherent=api_coherent)
    return PnlEvidence(
        decision=decision,
        entry_spot=entry,
        current_spot=current,
        bid_price=bid_price,
        is_valid_to_cancel=valid_cancel,
        is_valid_to_sell=valid_sell,
        contract_id=raw.get("contract_id") or metadata.get("contract_id"),
        raw=raw,
    )


@dataclass(frozen=True)
class TrendAlignmentSignal:
    direction: str  # "MULTUP", "MULTDOWN", or "NONE"
    macro_trend: str  # "BULLISH", "BEARISH", "NEUTRAL"
    adx_value: float  # Current ADX on M1/M5
    is_aligned: bool  # True if macro + momentum agree
    confidence: float  # 0.0 to 1.0


def calculate_adx_and_trend(
    prices: Sequence[float],
    period: int = 14,
) -> TrendAlignmentSignal:
    """
    Computes Wilder's ADX, Directional Indicators (+DI, -DI), and EMA macro trend
    from a sequence of prices.
    """
    clean = [p for p in prices if math.isfinite(p) and p > 0]
    if len(clean) < max(30, period + 5):
        return TrendAlignmentSignal(
            direction="NONE",
            macro_trend="NEUTRAL",
            adx_value=0.0,
            is_aligned=False,
            confidence=0.0,
        )

    # 1. Macro Trend: Fast (30 ticks) vs Slow (120 ticks) Mean/EMA
    fast_window = clean[-30:]
    slow_window = clean[-120:] if len(clean) >= 120 else clean
    fast_mean = sum(fast_window) / len(fast_window)
    slow_mean = sum(slow_window) / len(slow_window)
    rel_diff = (fast_mean - slow_mean) / slow_mean if slow_mean > 0 else 0.0

    if rel_diff >= 0.00005:
        macro_trend = "BULLISH"
    elif rel_diff <= -0.00005:
        macro_trend = "BEARISH"
    else:
        macro_trend = "NEUTRAL"

    # 2. ADX and Directional Movement (Wilder's calculation)
    deltas = [clean[i] - clean[i - 1] for i in range(1, len(clean))]
    plus_dm = [max(0.0, d) for d in deltas]
    minus_dm = [max(0.0, -d) for d in deltas]
    tr = [max(abs(d), 1e-6) for d in deltas]

    alpha = 1.0 / float(period)
    smoothed_plus_dm = plus_dm[0]
    smoothed_minus_dm = minus_dm[0]
    smoothed_tr = tr[0]

    dx_series: list[float] = []
    for p_dm, m_dm, t in zip(plus_dm[1:], minus_dm[1:], tr[1:]):
        smoothed_plus_dm = alpha * p_dm + (1.0 - alpha) * smoothed_plus_dm
        smoothed_minus_dm = alpha * m_dm + (1.0 - alpha) * smoothed_minus_dm
        smoothed_tr = alpha * t + (1.0 - alpha) * smoothed_tr

        plus_di = 100.0 * (smoothed_plus_dm / smoothed_tr) if smoothed_tr > 0 else 0.0
        minus_di = 100.0 * (smoothed_minus_dm / smoothed_tr) if smoothed_tr > 0 else 0.0

        di_sum = plus_di + minus_di
        dx = 100.0 * abs(plus_di - minus_di) / di_sum if di_sum > 0 else 0.0
        dx_series.append(dx)

    if not dx_series:
        adx = 0.0
    else:
        adx = dx_series[0]
        for val in dx_series[1:]:
            adx = alpha * val + (1.0 - alpha) * adx

    # 3. Trend Alignment Evaluation: requires ADX >= 20 (strong when >= 25) and directional concordance
    is_strong = adx >= 20.0
    if macro_trend == "BULLISH" and plus_di >= minus_di and is_strong:
        direction = "MULTUP"
        is_aligned = True
        confidence = min(1.0, adx / 50.0)
    elif macro_trend == "BEARISH" and minus_di >= plus_di and is_strong:
        direction = "MULTDOWN"
        is_aligned = True
        confidence = min(1.0, adx / 50.0)
    else:
        direction = "NONE"
        is_aligned = False
        confidence = max(0.0, round(adx / 100.0, 3))

    return TrendAlignmentSignal(
        direction=direction,
        macro_trend=macro_trend,
        adx_value=round(adx, 2),
        is_aligned=is_aligned,
        confidence=round(confidence, 3),
    )


async def evaluate_market_trend(
    symbol: str,
    client: Any,
    *,
    count: int = 180,
) -> TrendAlignmentSignal:
    """
    Evaluates market trend for the given symbol via DerivClient.
    Requests ticks_history or candles and computes TrendAlignmentSignal.
    """
    try:
        response: Any = None
        if hasattr(client, "send_request"):
            response = await client.send_request({
                "ticks_history": symbol,
                "count": count,
                "end": "latest",
                "style": "ticks",
            })
        elif hasattr(client, "request"):
            response = await client.request({
                "ticks_history": symbol,
                "count": count,
                "end": "latest",
                "style": "ticks",
            })

        if isinstance(response, Mapping):
            history = response.get("history", {})
            if isinstance(history, Mapping):
                prices = history.get("prices", [])
                if isinstance(prices, list) and len(prices) >= 30:
                    clean_prices = [_positive_float(p) for p in prices]
                    valid_prices = [p for p in clean_prices if p is not None]
                    return calculate_adx_and_trend(valid_prices)

            candles = response.get("candles", [])
            if isinstance(candles, list) and len(candles) >= 20:
                closes = [_positive_float(c.get("close")) for c in candles if isinstance(c, Mapping)]
                valid_closes = [c for c in closes if c is not None]
                return calculate_adx_and_trend(valid_closes)
    except Exception:
        pass

    return TrendAlignmentSignal(
        direction="NONE",
        macro_trend="NEUTRAL",
        adx_value=0.0,
        is_aligned=False,
        confidence=0.0,
    )


@dataclass(frozen=True)
class PerpetualRatchetState:
    peak_profit: float
    current_tier: int  # 0, 1, 2, 3, 4
    guaranteed_floor: float  # Min profit to lock in
    take_profit_target: float  # 8.0 * stake
    should_exit: bool
    exit_reason: str


def evaluate_perpetual_ratchet(
    profit: float,
    stake: float,
    peak_profit: float,
    *,
    take_profit_multiple: float = 8.0,
) -> PerpetualRatchetState:
    """
    Evaluates the 4-Tier Progressive Perpetual Ratchet on held_winner contracts.
    
    Tiers:
      - Tier 0 (< 1.0x stake): No trailing stop. Breathing room to ride the macro trend.
      - Tier 1 (+1.0x stake / +$1.00): Lock in breakeven floor at +0.20 * stake.
      - Tier 2 (+2.0x stake / +$2.00): Ratchet guaranteed floor to +1.00 * stake.
      - Tier 3 (+4.0x stake / +$4.00): Ratchet guaranteed floor to +2.50 * stake.
      - Tier 4 (+8.0x stake / +$8.00): Target take-profit / 80% trailing stop.
    """
    tp_target = take_profit_multiple * stake

    # Target take profit reached
    if profit >= tp_target - 1e-9:
        return PerpetualRatchetState(
            peak_profit=peak_profit,
            current_tier=4,
            guaranteed_floor=tp_target,
            take_profit_target=tp_target,
            should_exit=True,
            exit_reason="winner_exit_multiple",
        )

    if peak_profit >= tp_target:
        current_tier = 4
        # 80% trailing stop: locks in 80% of peak net profit, floor at least 2.50 * stake
        floor = max(2.50 * stake, peak_profit * 0.80)
    elif peak_profit >= 4.0 * stake:
        current_tier = 3
        floor = 2.50 * stake
    elif peak_profit >= 2.0 * stake:
        current_tier = 2
        floor = 1.00 * stake
    elif peak_profit >= 1.0 * stake:
        current_tier = 1
        floor = 0.20 * stake
    else:
        current_tier = 0
        floor = -float("inf")

    should_exit = False
    exit_reason = "holding"

    if current_tier > 0 and profit <= floor + 1e-9:
        should_exit = True
        exit_reason = "winner_trailing_stop"

    return PerpetualRatchetState(
        peak_profit=peak_profit,
        current_tier=current_tier,
        guaranteed_floor=floor if current_tier > 0 else 0.0,
        take_profit_target=tp_target,
        should_exit=should_exit,
        exit_reason=exit_reason,
    )


def cancellation_decision_timestamp(expiry: Any, buffer_seconds: Any) -> Optional[float]:
    expiry_value = _finite_float(expiry)
    buffer_value = _finite_float(buffer_seconds)
    if expiry_value is None or buffer_value is None or buffer_value < 0:
        return None
    return expiry_value - buffer_value


def cancellation_retry_allowed(
    now: Any,
    expiry: Any,
    safety_buffer_seconds: float = CANCEL_RETRY_SAFETY_SECONDS,
) -> bool:
    now_value = _finite_float(now)
    expiry_value = _finite_float(expiry)
    safety = _finite_float(safety_buffer_seconds)
    return (
        now_value is not None
        and expiry_value is not None
        and safety is not None
        and safety >= 0
        and now_value < expiry_value - safety
    )


def next_cancel_backoff(attempt: int, *, rng: Optional[random.Random] = None) -> float:
    random_source = rng or random
    base = min(2.0, 0.25 * (2 ** max(0, attempt - 1)))
    return base + random_source.uniform(0.0, 0.15)


def calculate_deployed_capital(positions: Sequence[Mapping[str, Any]]) -> Optional[float]:
    total = 0.0
    for position in positions:
        value = _positive_float(position.get("buy_price"))
        if value is None:
            return None
        total += value
    return total


def max_deployed_capital(balance: Any, max_deployed_pct: Any) -> Optional[float]:
    balance_value = _finite_float(balance)
    pct_value = _finite_float(max_deployed_pct)
    if balance_value is None or pct_value is None or balance_value < 0 or not 0 < pct_value <= 1:
        return None
    return balance_value * pct_value


def session_loss_limit(balance: Any, config: D107Config) -> Optional[float]:
    limit = max_deployed_capital(balance, config.max_deployed_pct)
    return limit * config.session_loss_stop_pct if limit is not None else None


def evaluate_new_buy_guardrails(
    *,
    balance: Any,
    open_count: int,
    deployed_capital: Any,
    next_buy_cost: Any,
    realized_pnl: Any,
    cancellation_fees: Any,
    config: D107Config,
) -> tuple[bool, str]:
    balance_value = _finite_float(balance)
    deployed_value = _finite_float(deployed_capital)
    next_cost = _positive_float(next_buy_cost)
    realized_value = _finite_float(realized_pnl)
    fees_value = _finite_float(cancellation_fees)
    if balance_value is None or balance_value <= 0:
        return False, "balance_unavailable"
    if deployed_value is None or next_cost is None or realized_value is None or fees_value is None:
        return False, "portfolio_accounting_unresolved"
    if open_count >= config.max_open_positions:
        return False, "max_open_positions"
    capital_limit = max_deployed_capital(balance_value, config.max_deployed_pct)
    if capital_limit is None or deployed_value + next_cost > capital_limit + 1e-9:
        return False, "max_deployed_capital"
    loss_limit = session_loss_limit(balance_value, config)
    session_loss = max(0.0, -realized_value) + max(0.0, fees_value)
    if loss_limit is None or session_loss >= loss_limit:
        return False, "session_loss_stop"
    return True, "ok"


def new_state() -> dict[str, Any]:
    return {
        "state_version": 1,
        "hypothesis": HYPOTHESIS,
        "session_id": str(uuid.uuid4()),
        "session_started_at": utc_now(),
        "account_id": None,
        "preflight_completed": False,
        "machine_state": "STARTUP_PREFLIGHT",
        "next_direction": "MULTUP",
        "last_confirmed_direction": None,
        "direction_sequence": [],
        "trial": 0,
        "confirmed_buys": 0,
        "pending_buy": None,
        "contracts": {},
        "session_realized_pnl": 0.0,
        "cancellation_fees": 0.0,
        "deployed_capital": 0.0,
        "unresolved_contracts": [],
        "last_portfolio_snapshot_at": None,
        "new_buys_enabled": False,
        "stop_reason": None,
    }


class AtomicStateStore:
    def __init__(self, path: str, *, min_free_bytes: int = DEFAULT_MIN_FREE_BYTES):
        self.path = os.path.abspath(os.path.expanduser(path))
        self.min_free_bytes = min_free_bytes

    def load(self) -> dict[str, Any]:
        if not os.path.exists(self.path):
            return new_state()
        try:
            with open(self.path, encoding="utf-8") as handle:
                state = json.load(handle)
        except (OSError, json.JSONDecodeError) as exc:
            raise StateError(f"cannot load D107 state: {self.path}") from exc
        if not isinstance(state, dict) or state.get("state_version") != 1:
            raise StateError("D107 state has an unsupported format")
        if state.get("hypothesis") != HYPOTHESIS:
            raise StateError("D107 state belongs to another hypothesis")
        if not isinstance(state.get("contracts"), dict):
            raise StateError("D107 state contracts are malformed")
        if not isinstance(state.get("unresolved_contracts"), list):
            raise StateError("D107 unresolved state is malformed")
        if state.get("next_direction") not in CONTRACT_TYPES:
            raise StateError("D107 alternation state is malformed")
        if not state.get("session_id"):
            raise StateError("D107 session identity is missing")
        return state

    def save(self, state: Mapping[str, Any]) -> None:
        parent = os.path.dirname(self.path) or "."
        os.makedirs(parent, exist_ok=True)
        free_bytes = shutil.disk_usage(parent).free
        if free_bytes < self.min_free_bytes:
            raise StateError(
                f"D107 state filesystem below safety threshold: {free_bytes} < {self.min_free_bytes}"
            )
        temporary_path = None
        try:
            fd, temporary_path = tempfile.mkstemp(prefix=".d107-state-", dir=parent, text=True)
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(redact_for_log(dict(state)), handle, ensure_ascii=False, sort_keys=True)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary_path, self.path)
            temporary_path = None
        except OSError as exc:
            raise StateError(f"cannot atomically save D107 state: {self.path}") from exc
        finally:
            if temporary_path:
                try:
                    os.unlink(temporary_path)
                except OSError:
                    pass


class AppendOnlyEventLog:
    def __init__(self, path: str, *, min_free_bytes: int = DEFAULT_MIN_FREE_BYTES):
        self.path = os.path.abspath(os.path.expanduser(path))
        self.min_free_bytes = min_free_bytes

    def append(self, event: str, **fields: Any) -> None:
        parent = os.path.dirname(self.path) or "."
        os.makedirs(parent, exist_ok=True)
        free_bytes = shutil.disk_usage(parent).free
        if free_bytes < self.min_free_bytes:
            raise StateError(
                f"D107 results filesystem below safety threshold: {free_bytes} < {self.min_free_bytes}"
            )
        record = {"event": event, "timestamp": utc_now()}
        record.update(redact_for_log(fields))
        with open(self.path, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False, allow_nan=False, default=str) + "\n")
            handle.flush()
            os.fsync(handle.fileno())


def _proposal_duration(proposal: Mapping[str, Any], cancellation: Mapping[str, Any]) -> Optional[str]:
    duration = cancellation.get("duration")
    unit = cancellation.get("duration_unit") or cancellation.get("unit")
    if duration is not None and unit is not None:
        parsed = _finite_int(duration)
        if parsed is not None:
            return f"{parsed}{str(unit).lower()}"
    for value in (cancellation.get("duration"), proposal.get("cancellation_duration")):
        if isinstance(value, str) and _DURATION_RE.fullmatch(value.strip()):
            return value.strip()
    shortcode = proposal.get("shortcode")
    if isinstance(shortcode, str):
        match = re.search(r"_(\d+[smhd])(?:_|$)", shortcode)
        if match:
            return match.group(1)
    return None


@dataclass(frozen=True)
class ValidatedProposal:
    proposal_id: str
    ask_price: float
    stake: float
    cancellation_fee: float
    date_start: float
    cancellation_expiry: float
    contract_type: str
    symbol: str
    multiplier: int
    shortcode: str
    raw: Mapping[str, Any]


def validate_proposal(
    proposal: Mapping[str, Any],
    config: D107Config,
    direction: str,
    *,
    expected_symbol: Optional[str] = None,
    now: Optional[float] = None,
) -> ValidatedProposal:
    if direction not in CONTRACT_TYPES:
        raise ConfigError(f"invalid D107 direction: {direction}")
    if not isinstance(proposal, Mapping):
        raise ConfigError("proposal response is malformed")
    cancellation = proposal.get("cancellation")
    if not isinstance(cancellation, Mapping):
        raise ConfigError("proposal has no cancellation data")
    parsed_shortcode = parse_shortcode(proposal.get("shortcode", ""))
    returned_type = proposal.get("contract_type") or parsed_shortcode.get("contract_type")
    returned_symbol = (
        proposal.get("underlying_symbol")
        or proposal.get("underlying")
        or parsed_shortcode.get("symbol")
    )
    returned_multiplier = _finite_int(proposal.get("multiplier")) or parsed_shortcode.get("multiplier")
    if returned_type is not None and returned_type != direction:
        raise ConfigError("proposal contract type differs from locked direction")
    target_symbol = expected_symbol or config.symbol
    if returned_symbol is not None and returned_symbol != target_symbol:
        raise ConfigError("proposal symbol differs from locked symbol")
    if returned_multiplier is not None and returned_multiplier != config.multiplier:
        raise ConfigError("proposal multiplier differs from locked multiplier")

    proposal_id = proposal.get("id") or proposal.get("proposal_id")
    ask_price = _positive_float(proposal.get("ask_price"))
    if not proposal_id or ask_price is None:
        raise ConfigError("proposal id or ask price is missing")

    returned_stake = _positive_float(proposal.get("amount")) or _positive_float(proposal.get("stake"))
    if returned_stake is None:
        returned_stake = parsed_shortcode.get("stake")
    if returned_stake is not None and abs(returned_stake - config.stake) > 0.011:
        raise ConfigError("proposal stake differs from locked stake")

    cancellation_fee = _finite_float(cancellation.get("ask_price"))
    date_start = _finite_float(proposal.get("date_start"))
    cancellation_expiry = _finite_float(cancellation.get("date_expiry"))
    if cancellation_fee is None or cancellation_fee < 0:
        raise ConfigError("proposal cancellation fee is missing")
    if date_start is None or cancellation_expiry is None:
        raise ConfigError("API-confirmed cancellation timestamps are missing")
    if cancellation_expiry <= date_start:
        raise ConfigError("API-confirmed cancellation expiry is not after date_start")
    if abs((cancellation_expiry - date_start) - config.cancellation_seconds) > 10:
        raise ConfigError("API-confirmed cancellation duration differs from locked duration")
    returned_duration = _proposal_duration(proposal, cancellation)
    if returned_duration is not None and returned_duration != config.cancellation:
        raise ConfigError("proposal cancellation duration differs from locked duration")
    current_time = time.time() if now is None else now
    if cancellation_expiry <= current_time:
        raise ConfigError("proposal cancellation window is already expired")
    shortcode = str(proposal.get("shortcode") or "")
    return ValidatedProposal(
        proposal_id=str(proposal_id),
        ask_price=ask_price,
        stake=config.stake,
        cancellation_fee=cancellation_fee,
        date_start=date_start,
        cancellation_expiry=cancellation_expiry,
        contract_type=direction,
        symbol=target_symbol,
        multiplier=config.multiplier,
        shortcode=shortcode,
        raw=proposal,
    )


def _api_error(response: Any) -> Optional[dict[str, Any]]:
    if not isinstance(response, Mapping) or "error" not in response:
        return None
    error = response.get("error")
    if isinstance(error, Mapping):
        code = error.get("code")
        message = error.get("message")
    else:
        code = None
        message = error
    return {"code": code, "message": _safe_error_message(message)}


def is_rate_limit_error(error: Optional[Mapping[str, Any]]) -> bool:
    if not error:
        return False
    text = f"{error.get('code', '')} {error.get('message', '')}".lower()
    return "rate" in text or "limit" in text or "too many" in text


def _terminal_contract(raw: Mapping[str, Any]) -> bool:
    if _api_bool(raw.get("is_sold")) is True or _api_bool(raw.get("is_expired")) is True:
        return True
    return str(raw.get("status", "")).lower() in TERMINAL_STATUSES


class D107Bot:
    def __init__(
        self,
        client: Any,
        config: D107Config,
        *,
        state_store: Optional[AtomicStateStore] = None,
        event_log: Optional[AppendOnlyEventLog] = None,
    ):
        config.validate()
        self.client = client
        self.config = config
        self.state_store = state_store or AtomicStateStore(
            config.state_file, min_free_bytes=config.min_free_bytes
        )
        self.event_log = event_log or AppendOnlyEventLog(
            config.results_file, min_free_bytes=config.min_free_bytes
        )
        self.state: dict[str, Any] = new_state()
        self.account_id: Optional[str] = None
        self.machine_state = "STARTUP_PREFLIGHT"
        self.portfolio_positions: list[Mapping[str, Any]] = []
        self.portfolio_unknown: list[Mapping[str, Any]] = []
        self.balance: Optional[float] = None
        self.monitor_tasks: dict[str, asyncio.Task[Any]] = {}
        self.subscribed_contracts: set[str] = set()
        self.stop_event = asyncio.Event()
        self._last_observation_log: dict[str, float] = {}
        self._last_exit_reason: dict[str, str] = {}

    def _save_state(self) -> None:
        self.state["machine_state"] = self.machine_state
        self.state_store.save(self.state)

    def emit(self, event: str, **fields: Any) -> None:
        record = {
            "state": self.machine_state,
            "trial": self.state.get("trial"),
            "session_id": self.state.get("session_id"),
            "account_id": self.account_id,
            "account_type": "demo" if self.account_id else None,
            "symbol": self.config.symbol,
            "stake": self.config.stake,
            "multiplier": self.config.multiplier,
            "cancellation": self.config.cancellation,
            "session_realized_pnl": self.state.get("session_realized_pnl", 0.0),
            "cancellation_fees": self.state.get("cancellation_fees", 0.0),
            "deployed_capital": self.state.get("deployed_capital", 0.0),
            "open_count": len(self.portfolio_positions),
            "new_buys_enabled": self.state.get("new_buys_enabled", False),
            "is_valid_to_buy": self.state.get("new_buys_enabled", False),
        }
        record.update(fields)
        self.event_log.append(event, **record)

    def disable_new_buys(self, reason: str, contract_id: Optional[str] = None) -> None:
        self.state["new_buys_enabled"] = False
        self.state["stop_reason"] = reason
        if contract_id and contract_id not in self.state["unresolved_contracts"]:
            self.state["unresolved_contracts"].append(contract_id)
        self._save_state()

    def verify_demo_account(self) -> None:
        if getattr(self.client, "use_demo", False) is not True:
            raise ConfigError("D107 requires a Demo account")
        account_id = getattr(self.client, "account_id", None)
        if not account_id:
            raise ConfigError("Demo account identity was not returned by authentication")
        expected_account_id = self.config.expected_account_id or self.state.get("account_id")
        if expected_account_id and account_id != expected_account_id:
            raise ConfigError("connected Demo account does not match the expected D107 identity")
        account_type = getattr(self.client, "account_type", "demo")
        if account_type not in {None, "demo"}:
            raise ConfigError("authenticated account is not Demo")
        self.account_id = str(account_id)
        self.state["account_id"] = self.account_id

    async def request(self, payload: Mapping[str, Any], *, timeout: float = 20.0) -> Mapping[str, Any]:
        try:
            response = await asyncio.wait_for(
                self.client.send_request(dict(payload)), timeout=max(0.1, timeout)
            )
        except asyncio.TimeoutError as exc:
            raise ApiRequestError("Deriv request timed out", ambiguous=True) from exc
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            raise ApiRequestError(_safe_error_message(exc), ambiguous=False) from exc
        if not isinstance(response, Mapping):
            raise ApiRequestError("Deriv returned a malformed response", ambiguous=False)
        return response

    async def fetch_balance(self) -> float:
        response = await self.request({"balance": 1})
        error = _api_error(response)
        if error:
            raise ReconciliationRequired(f"balance request failed: {error['message']}")
        balance_data = response.get("balance")
        balance = _finite_float(balance_data.get("balance")) if isinstance(balance_data, Mapping) else None
        if balance is None or balance < 0:
            raise ReconciliationRequired("Demo balance could not be verified")
        self.balance = balance
        return balance

    async def fetch_portfolio(self) -> list[Mapping[str, Any]]:
        response = await self.request({"portfolio": 1})
        error = _api_error(response)
        if error:
            raise ReconciliationRequired(f"portfolio request failed: {error['message']}")
        portfolio = response.get("portfolio")
        contracts = portfolio.get("contracts") if isinstance(portfolio, Mapping) else None
        if not isinstance(contracts, list):
            raise ReconciliationRequired("portfolio contracts could not be verified")
        return [contract for contract in contracts if isinstance(contract, Mapping)]

    async def reconcile_missing_contract(
        self,
        contract_id: str,
        record: dict[str, Any],
    ) -> bool:
        try:
            raw = await self.open_contract(contract_id)
        except (ApiRequestError, ReconciliationRequired):
            return False
        if not _terminal_contract(raw):
            return False
        lifecycle_before = record.get("lifecycle")
        status = str(raw.get("status", "")).lower()
        record["lifecycle"] = "auto_stopped" if status in {"cancelled", "expired"} else "closed_external"
        record["closed_at"] = utc_now()
        record["reconciled_terminal"] = True
        record["terminal_status"] = raw.get("status")
        sell_price = _finite_float(raw.get("sell_price"))
        buy_price = _finite_float(record.get("buy_price"))
        if sell_price is not None and buy_price is not None:
            record["external_close_pnl"] = round(sell_price - buy_price, 10)
        self.state["unresolved_contracts"] = [
            item for item in self.state.get("unresolved_contracts", []) if item != contract_id
        ]
        if not self.state["unresolved_contracts"] and self.state.get("stop_reason") != "session_loss_stop":
            self.state["stop_reason"] = None
        self._save_state()
        self.emit(
            "manual_reconciliation",
            action="manual_reconciliation",
            contract_id=contract_id,
            lifecycle_before=lifecycle_before,
            terminal_status=raw.get("status"),
            external_close_pnl=record.get("external_close_pnl"),
            reconciled_terminal=True,
            raw_contract=raw,
        )
        return True

    async def reconcile_unresolved_open_contract(
        self,
        contract_id: str,
        record: dict[str, Any],
    ) -> bool:
        try:
            raw = await self.open_contract(contract_id)
            evidence = await self.collect_evidence(record, raw)
        except (ApiRequestError, ReconciliationRequired):
            return False
        self.update_observation(record, raw, evidence)
        if evidence.decision.classification == "validated_loss":
            if (
                self.config.unresolved_loss_action == "sell"
                and evidence.is_valid_to_sell is True
            ):
                return await self.sell_unresolved_loss(record, evidence)
            return False
        if evidence.decision.classification != "validated_winner":
            return False
        lifecycle_before = record.get("lifecycle")
        record["lifecycle"] = "held_winner"
        record["reconciled_winner_at"] = utc_now()
        record["winner_pnl_source"] = evidence.decision.pnl_source
        record["winner_profit_at_reconciliation"] = evidence.decision.pnl
        record["held_peak_unrealized_pnl"] = max(0.0, _finite_float(evidence.decision.pnl) or 0.0)
        self.state["unresolved_contracts"] = [
            item for item in self.state.get("unresolved_contracts", []) if item != contract_id
        ]
        if not self.state["unresolved_contracts"] and self.state.get("stop_reason") != "session_loss_stop":
            self.state["stop_reason"] = None
        self._save_state()
        self.emit(
            "held_winner_reconciled",
            action="held_winner",
            contract_id=contract_id,
            lifecycle_before=lifecycle_before,
            **evidence.as_log_record(),
        )
        if self.machine_state != "STARTUP_PREFLIGHT":
            self.start_monitor(contract_id)
        return True

    async def sell_unresolved_loss(
        self,
        record: dict[str, Any],
        evidence: PnlEvidence,
    ) -> bool:
        self.machine_state = "SELL_REQUESTED"
        contract_id = str(record["contract_id"])
        record["lifecycle"] = "sell_requested"
        self._save_state()
        for attempt in range(1, MAX_SELL_RETRIES + 1):
            started = time.monotonic()
            try:
                response = await self.request({"sell": _api_contract_id(contract_id), "price": 0}, timeout=10.0)
            except ApiRequestError as exc:
                self.emit(
                    "sell_attempt",
                    action="sell_requested",
                    contract_id=contract_id,
                    retry_count=attempt,
                    api_error_message=_safe_error_message(exc),
                    ambiguous=exc.ambiguous,
                    unresolved_loss_exit=True,
                    elapsed_request_seconds=time.monotonic() - started,
                )
                self.mark_unresolved(record, "sell_failed", "unresolved loss sell became ambiguous")
                return False
            error = _api_error(response)
            sell_data = response.get("sell") if not error else None
            sold_for = _finite_float(sell_data.get("sold_for")) if isinstance(sell_data, Mapping) else None
            self.emit(
                "sell_attempt",
                action="sell_requested",
                contract_id=contract_id,
                retry_count=attempt,
                api_error_code=error.get("code") if error else None,
                api_error_message=error.get("message") if error else None,
                rate_limit=is_rate_limit_error(error),
                unresolved_loss_exit=True,
                elapsed_request_seconds=time.monotonic() - started,
            )
            if not error and sold_for is not None:
                buy_price = _positive_float(record.get("buy_price")) or self.config.stake
                record["lifecycle"] = "closed_unresolved_loss"
                record["closed_at"] = utc_now()
                record["sold_for"] = sold_for
                record["close_reason"] = "unresolved_loss_exit"
                record["realized_pnl"] = round(sold_for - buy_price, 10)
                self.state["session_realized_pnl"] = round(
                    float(self.state.get("session_realized_pnl", 0.0)) + sold_for - buy_price,
                    10,
                )
                self.state["unresolved_contracts"] = [
                    item for item in self.state.get("unresolved_contracts", []) if item != contract_id
                ]
                if not self.state["unresolved_contracts"] and self.state.get("stop_reason") != "session_loss_stop":
                    self.state["stop_reason"] = None
                self._save_state()
                self.emit(
                    "sell_confirmed",
                    action="sold_unresolved_loss",
                    contract_id=contract_id,
                    sold_for=sold_for,
                    buy_price=buy_price,
                    realized_pnl=record["realized_pnl"],
                    unresolved_loss_exit=True,
                    retry_count=attempt,
                    **evidence.as_log_record(),
                )
                return True
            if attempt < MAX_SELL_RETRIES and error:
                await asyncio.sleep(next_cancel_backoff(attempt))
        self.mark_unresolved(record, "sell_failed", "unresolved loss sell failed after bounded retries")
        return False

    async def reconcile_portfolio(
        self,
        contracts: Optional[Sequence[Mapping[str, Any]]] = None,
        *,
        strict: bool = False,
    ) -> bool:
        live_contracts = list(contracts) if contracts is not None else await self.fetch_portfolio()
        matching, unknown = classify_portfolio_contracts(live_contracts, self.config)
        issues: list[str] = []
        if unknown:
            issues.append("portfolio contains an unclassifiable multiplier position")
        live_ids = {str(item.get("contract_id")) for item in matching if item.get("contract_id") is not None}
        missing_open_ids = set()
        for contract_id, record in self.state.get("contracts", {}).items():
            contract_key = str(contract_id)
            lifecycle = record.get("lifecycle")
            if (
                lifecycle in {"unresolved", "cancellation_window_missed", "cancel_failed", "sell_failed"}
                and contract_key in live_ids
            ):
                if await self.reconcile_unresolved_open_contract(contract_key, record):
                    continue
                missing_open_ids.add(contract_key)
                issues.append(f"unresolved contract still lacks coherent P&L evidence: {contract_id}")
                continue
            needs_reconciliation = lifecycle in OPEN_LIFECYCLES or contract_key in self.state.get("unresolved_contracts", [])
            if needs_reconciliation and contract_key not in live_ids:
                if await self.reconcile_missing_contract(contract_key, record):
                    continue
                missing_open_ids.add(contract_key)
                issues.append(f"known open contract missing from portfolio: {contract_id}")
        deployed = calculate_deployed_capital(matching)
        if deployed is None:
            issues.append("matching portfolio position has no reliable buy_price")
        self.portfolio_positions = matching
        self.portfolio_unknown = unknown
        if deployed is not None:
            self.state["deployed_capital"] = round(deployed, 10)
        self.state["last_portfolio_snapshot_at"] = utc_now()
        if issues:
            self.disable_new_buys("reconciliation_required")
            self.state["unresolved_contracts"] = sorted(
                set(self.state.get("unresolved_contracts", []))
                | missing_open_ids
                | {str(item.get("contract_id")) for item in matching if item.get("contract_id") is None}
            )
            self._save_state()
            if strict:
                raise ReconciliationRequired("; ".join(issues))
            return False
        self._save_state()
        return True

    def start_monitor(self, contract_id: str) -> None:
        current = self.monitor_tasks.get(contract_id)
        if current is not None and not current.done():
            return
        self.monitor_tasks[contract_id] = asyncio.create_task(self.monitor_contract(contract_id))

    def refresh_continuous_buy_gate(self, balance: float) -> None:
        if self.config.mode != "continuous" or self.state.get("new_buys_enabled"):
            return
        previous_reason = self.state.get("stop_reason")
        if previous_reason is not None and previous_reason not in RECOVERABLE_GUARDRAIL_STOPS:
            return
        if previous_reason == "reconciliation_required" and bool(self.state.get("unresolved_contracts")):
            return
        allowed, reason = evaluate_new_buy_guardrails(
            balance=balance,
            open_count=len(self.portfolio_positions),
            deployed_capital=self.state.get("deployed_capital"),
            next_buy_cost=self.config.stake,
            realized_pnl=self.state.get("session_realized_pnl", 0.0),
            cancellation_fees=self.state.get("cancellation_fees", 0.0),
            config=self.config,
        )
        if allowed:
            self.state["new_buys_enabled"] = True
            self.state["stop_reason"] = None
            self._save_state()
            self.emit(
                "guardrail_released",
                action="guardrail_released",
                previous_stop_reason=previous_reason,
            )
        elif reason != previous_reason:
            self.state["stop_reason"] = reason
            self._save_state()

    async def preflight(self) -> None:
        self.machine_state = "STARTUP_PREFLIGHT"
        self.state = self.state_store.load()
        self.verify_demo_account()
        balance = await self.fetch_balance()
        await self.reconcile_portfolio(strict=True)
        if self.state.get("pending_buy") or self.state.get("unresolved_contracts"):
            self.state["new_buys_enabled"] = False
            self.state["stop_reason"] = "reconciliation_required"
        elif (
            self.state.get("stop_reason") not in {None, "canary_complete"}
            and not (
                self.config.mode == "continuous"
                and self.state.get("stop_reason") in RECOVERABLE_GUARDRAIL_STOPS
            )
        ):
            self.state["new_buys_enabled"] = False
        elif self.config.mode == "canary" and self.state.get("confirmed_buys", 0) >= self.config.canary_buys:
            self.state["new_buys_enabled"] = False
            self.state["stop_reason"] = "canary_complete"
        else:
            allowed, reason = evaluate_new_buy_guardrails(
                balance=balance,
                open_count=len(self.portfolio_positions),
                deployed_capital=self.state.get("deployed_capital"),
                next_buy_cost=self.config.stake,
                realized_pnl=self.state.get("session_realized_pnl", 0.0),
                cancellation_fees=self.state.get("cancellation_fees", 0.0),
                config=self.config,
            )
            self.state["new_buys_enabled"] = allowed
            self.state["stop_reason"] = None if allowed else reason
        self.state["preflight_completed"] = True
        self.machine_state = "READY"
        self._save_state()
        self.emit(
            "startup_preflight",
            action="manual_reconciliation",
            balance=balance,
            portfolio_open_count=len(self.portfolio_positions),
            portfolio_deployed_capital=self.state.get("deployed_capital"),
            external_positions=sum(
                1
                for position in self.portfolio_positions
                if str(position.get("contract_id")) not in self.state.get("contracts", {})
            ),
            locked_parameters={
                "symbol": self.config.symbol,
                "contract_types": list(CONTRACT_TYPES),
                "multiplier": self.config.multiplier,
                "cancellation": self.config.cancellation,
                "stake": self.config.stake,
                "max_stake": self.config.max_stake,
                "mode": self.config.mode,
                "auto_sell_winners": self.config.auto_sell_winners,
                "winner_exit_multiple": self.config.winner_exit_multiple,
            },
        )
        live_ids = {
            str(position.get("contract_id"))
            for position in self.portfolio_positions
            if position.get("contract_id") is not None
        }
        for contract_id, record in self.state.get("contracts", {}).items():
            if record.get("lifecycle") in OPEN_LIFECYCLES and str(contract_id) in live_ids:
                self.start_monitor(str(contract_id))
        print(
            f"[D107] Demo account={self.account_id} symbol={self.config.symbol} "
            f"multiplier={self.config.multiplier} cancellation={self.config.cancellation} "
            f"stake=${self.config.stake:.2f} open={len(self.portfolio_positions)} "
            f"new_buys_enabled={self.state['new_buys_enabled']}",
            flush=True,
        )

    def _unresolved_buy_present(self) -> bool:
        return bool(self.state.get("pending_buy")) or bool(self.state.get("unresolved_contracts"))

    def evaluate_market_regime(self) -> tuple[bool, str]:
        policy_path = os.path.abspath(os.path.expanduser(self.config.regime_policy_file))
        if not os.path.exists(policy_path):
            return True, "policy_file_absent"
        try:
            with open(policy_path) as f:
                data = json.load(f)
            epoch = _finite_float(data.get("epoch"))
            if epoch and time.time() - epoch > 900:
                return True, "policy_stale"
            allowed_symbols = {SYMBOL, "R_100", "1HZ100V", "1HZ75V", "R_75"}
            rec_sym = data.get("deriv_primary_asset")
            target_sym = (
                rec_sym
                if (self.config.dynamic_asset_rotation and rec_sym in allowed_symbols)
                else self.config.symbol
            )
            metrics = data.get("deriv_metrics", {}).get(target_sym, {})
            hurst = _finite_float(metrics.get("hurst"))
            strat = str(metrics.get("recommended_strategy") or "")
            vol = _finite_float(metrics.get("volatility_5m_pct"))
            if hurst is not None and hurst < self.config.min_regime_hurst:
                if vol is not None and vol >= 0.25 and hurst >= 0.45:
                    return True, f"regime_vol_expansion_{hurst:.4f}"
                return False, f"hurst_too_low_{hurst:.4f}"
            if strat == "RSI_MEAN_REVERSION":
                return False, "regime_mean_reverting_chop"
            return True, f"regime_ok_{strat}"
        except Exception as exc:
            return True, f"regime_check_error_{_safe_error_message(exc)}"

    def get_regime_recommendations(
        self, symbol: Optional[str] = None
    ) -> tuple[Optional[str], Optional[str]]:
        policy_path = os.path.abspath(os.path.expanduser(self.config.regime_policy_file))
        if not os.path.exists(policy_path):
            return None, None
        try:
            with open(policy_path) as f:
                data = json.load(f)
            epoch = _finite_float(data.get("epoch"))
            if epoch and time.time() - epoch > 900:
                return None, None
            allowed_symbols = {SYMBOL, "R_100", "1HZ100V", "1HZ75V", "R_75"}
            rec_sym = data.get("deriv_primary_asset")
            if rec_sym not in allowed_symbols:
                rec_sym = None
            sym_key = (
                symbol
                or (rec_sym if self.config.dynamic_asset_rotation else self.config.symbol)
                or self.config.symbol
            )
            deriv_metrics = (
                data.get("deriv_metrics") if isinstance(data.get("deriv_metrics"), Mapping) else {}
            )
            assets_map = data.get("assets") if isinstance(data.get("assets"), Mapping) else {}
            metrics = deriv_metrics.get(sym_key) or assets_map.get(sym_key) or {}
            if not isinstance(metrics, Mapping):
                metrics = {}
            rec_dir = metrics.get("recommended_direction") or metrics.get("direction")
            if rec_dir not in CONTRACT_TYPES and (
                sym_key == rec_sym or (rec_sym is None and not metrics)
            ):
                rec_dir = data.get("recommended_direction")
            if rec_dir not in CONTRACT_TYPES:
                rec_dir = None
            return rec_sym, rec_dir
        except Exception:
            return None, None

    async def detect_realtime_micro_trend(self, symbol: str) -> Optional[str]:
        """
        Determines the multi-minute trend on Deriv from recent ticks (count=180),
        comparing a 30-tick fast mean against a 120-tick slow mean with threshold 0.0003
        and an anti-exhaustion check so it does not chase late 10-tick spikes.
        """
        try:
            response = await self.request(
                {
                    "ticks_history": symbol,
                    "count": 180,
                    "end": "latest",
                    "style": "ticks",
                },
                timeout=10.0,
            )
            history = response.get("history", {})
            prices = history.get("prices", []) if isinstance(history, Mapping) else []
            if not isinstance(prices, list):
                return None
            clean_prices = [val for p in prices if (val := _positive_float(p)) is not None]
            if len(clean_prices) < 30:
                return None
            fast_window = clean_prices[-30:]
            slow_window = clean_prices[-120:] if len(clean_prices) >= 120 else clean_prices
            fast_mean = sum(fast_window) / len(fast_window)
            slow_mean = sum(slow_window) / len(slow_window)
            if slow_mean <= 0:
                return None
            rel_diff = (fast_mean - slow_mean) / slow_mean
            move_10 = abs(clean_prices[-1] - clean_prices[-10])
            move_30 = abs(clean_prices[-1] - clean_prices[-30])
            mean_move_30 = abs(fast_mean - slow_mean)
            if move_10 > 2.0 * move_30 or move_10 > 2.0 * mean_move_30:
                return None
            if rel_diff >= 0.0003:
                return "MULTUP"
            if rel_diff <= -0.0003:
                return "MULTDOWN"
            return None
        except Exception:
            return None

    async def _reconcile_and_adopt_after_buy_error(
        self,
        *,
        proposal: ValidatedProposal,
        direction: str,
        chosen_symbol: str,
        pre_buy_ids: set[str],
        started: float,
        error: Mapping[str, Any],
    ) -> Optional[str]:
        try:
            await self.reconcile_portfolio(strict=False)
        except (ApiRequestError, ReconciliationRequired):
            return None
        for position in self.portfolio_positions:
            metadata = contract_metadata(position)
            cid = metadata.get("contract_id")
            if cid is None:
                continue
            cid_str = str(cid)
            if cid_str in pre_buy_ids or cid_str in self.state.get("contracts", {}):
                continue
            pos_symbol = metadata.get("symbol") or chosen_symbol
            pos_type = metadata.get("contract_type")
            pos_buy_price = _positive_float(metadata.get("buy_price"))
            if pos_symbol != chosen_symbol or pos_type != direction:
                continue
            if pos_buy_price is not None and abs(pos_buy_price - proposal.ask_price) > 0.02:
                continue
            buy_price = pos_buy_price or proposal.ask_price
            self.machine_state = "BUY_CONFIRMED"
            if self.config.trend_alignment_enabled:
                alternation_after = direction
            else:
                alternation_after = "MULTDOWN" if direction == "MULTUP" else "MULTUP"
            record = {
                "owner": "d107_created",
                "contract_id": cid_str,
                "lifecycle": "cancellation_window_monitoring",
                "direction": direction,
                "contract_type": direction,
                "symbol": chosen_symbol,
                "stake": proposal.stake,
                "multiplier": self.config.multiplier,
                "cancellation": self.config.cancellation,
                "cancellation_fee": proposal.cancellation_fee,
                "buy_price": buy_price,
                "date_start": proposal.date_start,
                "purchase_time": metadata.get("purchase_time") or proposal.date_start,
                "cancellation_expiry": proposal.cancellation_expiry,
                "shortcode": metadata.get("shortcode") or proposal.shortcode,
                "alternation_before": direction,
                "alternation_after": alternation_after,
                "confirmed_at": utc_now(),
                "peak_unrealized_pnl": None,
                "adopted_after_buy_error": True,
                "buy_error_code": error.get("code"),
            }
            self.state["contracts"][cid_str] = record
            self.state["pending_buy"] = None
            self.state["last_confirmed_direction"] = direction
            self.state["next_direction"] = alternation_after
            self.state["direction_sequence"].append(direction)
            self.state["confirmed_buys"] = int(self.state.get("confirmed_buys", 0)) + 1
            if self.config.mode == "canary" and self.state["confirmed_buys"] >= self.config.canary_buys:
                self.state["new_buys_enabled"] = False
                self.state["stop_reason"] = "canary_complete"
            self._save_state()
            self.emit(
                "buy_confirmed",
                action="buy_confirmed",
                contract_id=cid_str,
                contract_type=direction,
                direction=direction,
                alternation_before=direction,
                alternation_after=alternation_after,
                direction_sequence=self.state["direction_sequence"],
                buy_price=buy_price,
                date_start=proposal.date_start,
                purchase_time=record["purchase_time"],
                cancellation_expiry=proposal.cancellation_expiry,
                shortcode=record["shortcode"],
                adopted_after_buy_error=True,
                api_error_code=error.get("code"),
                elapsed_request_seconds=time.monotonic() - started,
            )
            self.start_monitor(cid_str)
            return cid_str
        return None

    async def try_buy(self) -> None:
        if not self.state.get("new_buys_enabled") or self._unresolved_buy_present():
            return
        if self.config.check_regime_supervisor:
            regime_ok, regime_reason = self.evaluate_market_regime()
            if not regime_ok:
                self.emit("regime_filter_pause", action="waiting_regime", reason=regime_reason)
                return
        self.machine_state = "READY"
        try:
            balance = await self.fetch_balance()
            if not await self.reconcile_portfolio(strict=False):
                return
        except (ApiRequestError, ReconciliationRequired) as exc:
            self.disable_new_buys("pre_buy_reconciliation_failure")
            self.emit("reconciliation_required", action="unresolved", error=_safe_error_message(exc))
            return

        allowed, reason = evaluate_new_buy_guardrails(
            balance=balance,
            open_count=len(self.portfolio_positions),
            deployed_capital=self.state.get("deployed_capital"),
            next_buy_cost=self.config.stake,
            realized_pnl=self.state.get("session_realized_pnl", 0.0),
            cancellation_fees=self.state.get("cancellation_fees", 0.0),
            config=self.config,
        )
        if not allowed:
            self.disable_new_buys(reason)
            self.emit("guardrail_block", action="unresolved", guardrail=reason)
            return

        chosen_symbol = self.config.symbol
        direction = self.state.get("next_direction")
        if self.config.dynamic_asset_rotation:
            rec_sym, _ = self.get_regime_recommendations()
            if rec_sym:
                chosen_symbol = rec_sym

        if self.config.trend_alignment_enabled:
            # Multi-timeframe trend alignment (Macro Tide + Trend Momentum + ADX)
            trend_signal = await evaluate_market_trend(chosen_symbol, self.client)
            if trend_signal.is_aligned and trend_signal.direction in CONTRACT_TYPES:
                direction = trend_signal.direction
            else:
                # 1. Fallback: Fresh regime supervisor recommendation for chosen_symbol
                _, rec_dir = self.get_regime_recommendations(chosen_symbol)
                if rec_dir in CONTRACT_TYPES:
                    direction = rec_dir
                else:
                    # 2. Fallback: Multi-minute micro-trend with anti-exhaustion filter
                    live_trend = await self.detect_realtime_micro_trend(chosen_symbol)
                    if live_trend in CONTRACT_TYPES:
                        direction = live_trend
                    else:
                        # When trend alignment is enabled, DO NOT alternate blindly! Pause and wait for aligned trend.
                        self.emit(
                            "trend_alignment_pause",
                            action="waiting_trend",
                            symbol=chosen_symbol,
                            macro_trend=trend_signal.macro_trend,
                            adx=trend_signal.adx_value,
                            reason="no_aligned_trend",
                        )
                        return

        if direction not in CONTRACT_TYPES:
            self.disable_new_buys("alternation_state_invalid")
            self.emit("reconciliation_required", action="unresolved")
            return
        trial = int(self.state.get("trial", 0)) + 1
        self.state["trial"] = trial
        self.state["pending_buy"] = {
            "trial": trial,
            "direction": direction,
            "alternation_before": direction,
            "symbol": chosen_symbol,
            "submitted_at": utc_now(),
        }
        self._save_state()
        payload = {
            "proposal": 1,
            "amount": self.config.stake,
            "basis": "stake",
            "contract_type": direction,
            "currency": "USD",
            "underlying_symbol": chosen_symbol,
            "multiplier": self.config.multiplier,
            "cancellation": self.config.cancellation,
        }
        self.machine_state = "PROPOSAL_REQUESTED"
        started = time.monotonic()
        try:
            proposal_response = await self.request(payload)
        except ApiRequestError as exc:
            self.state["pending_buy"] = None
            self.disable_new_buys("proposal_request_failure")
            self.emit(
                "proposal_error",
                action="proposal_error",
                error=_safe_error_message(exc),
                elapsed_request_seconds=time.monotonic() - started,
                ambiguous=exc.ambiguous,
            )
            return
        error = _api_error(proposal_response)
        if error:
            self.state["pending_buy"] = None
            self._save_state()
            self.emit(
                "proposal_error",
                action="proposal_error",
                api_error_code=error.get("code"),
                api_error_message=error.get("message"),
                rate_limit=is_rate_limit_error(error),
                elapsed_request_seconds=time.monotonic() - started,
            )
            return
        try:
            proposal = validate_proposal(
                proposal_response.get("proposal", {}),
                self.config,
                direction,
                expected_symbol=chosen_symbol,
            )
        except ConfigError as exc:
            self.state["pending_buy"] = None
            self.disable_new_buys("proposal_validation_failure")
            self.emit(
                "proposal_error",
                action="proposal_error",
                error=_safe_error_message(exc),
                proposal=proposal_response,
                elapsed_request_seconds=time.monotonic() - started,
            )
            return
        self.state["pending_buy"].update(
            {
                "proposal_id": proposal.proposal_id,
                "ask_price": proposal.ask_price,
                "cancellation_fee": proposal.cancellation_fee,
                "date_start": proposal.date_start,
                "cancellation_expiry": proposal.cancellation_expiry,
                "shortcode": proposal.shortcode,
            }
        )
        self._save_state()
        self.emit(
            "proposal_requested",
            action="proposal_requested",
            direction=direction,
            alternation_before=direction,
            proposal=proposal.raw,
            cancellation_expiry=proposal.cancellation_expiry,
            cancellation_fee=proposal.cancellation_fee,
            elapsed_request_seconds=time.monotonic() - started,
        )
        allowed, reason = evaluate_new_buy_guardrails(
            balance=balance,
            open_count=len(self.portfolio_positions),
            deployed_capital=self.state.get("deployed_capital"),
            next_buy_cost=proposal.ask_price,
            realized_pnl=self.state.get("session_realized_pnl", 0.0),
            cancellation_fees=self.state.get("cancellation_fees", 0.0),
            config=self.config,
        )
        if not allowed:
            self.state["pending_buy"] = None
            self.disable_new_buys(reason)
            self.emit("guardrail_block", action="unresolved", guardrail=reason)
            return

        pre_buy_ids = {
            str(item.get("contract_id"))
            for item in self.portfolio_positions
            if item.get("contract_id") is not None
        } | set(self.state.get("contracts", {}).keys())
        self.machine_state = "BUY_SUBMITTED"
        self.emit(
            "buy_submitted",
            action="buy_submitted",
            direction=direction,
            proposal_id=proposal.proposal_id,
            buy_request={"buy": proposal.proposal_id, "price": proposal.ask_price},
        )
        started = time.monotonic()
        try:
            buy_response = await self.request(
                {"buy": proposal.proposal_id, "price": proposal.ask_price}, timeout=20.0
            )
        except ApiRequestError as exc:
            adopted_id = await self._reconcile_and_adopt_after_buy_error(
                proposal=proposal,
                direction=direction,
                chosen_symbol=chosen_symbol,
                pre_buy_ids=pre_buy_ids,
                started=started,
                error={"code": "BuyRequestAmbiguous", "message": _safe_error_message(exc)},
            )
            if adopted_id:
                return
            self.machine_state = "BUY_AMBIGUOUS"
            self.state["pending_buy"]["lifecycle"] = "buy_ambiguous"
            self.disable_new_buys("buy_ambiguous", f"buy_trial_{trial}")
            self.emit(
                "buy_ambiguous",
                action="buy_ambiguous",
                error=_safe_error_message(exc),
                rate_limit=False,
                elapsed_request_seconds=time.monotonic() - started,
            )
            return
        error = _api_error(buy_response)
        if error:
            self.emit(
                "buy_error",
                action="buy_error",
                api_error_code=error.get("code"),
                api_error_message=error.get("message"),
                rate_limit=is_rate_limit_error(error),
                elapsed_request_seconds=time.monotonic() - started,
            )
            adopted_id = await self._reconcile_and_adopt_after_buy_error(
                proposal=proposal,
                direction=direction,
                chosen_symbol=chosen_symbol,
                pre_buy_ids=pre_buy_ids,
                started=started,
                error=error,
            )
            if adopted_id:
                return
            self.state["pending_buy"] = None
            self._save_state()
            return
        buy = buy_response.get("buy")
        if not isinstance(buy, Mapping):
            self.disable_new_buys("buy_response_malformed", f"buy_trial_{trial}")
            self.emit("buy_ambiguous", action="buy_ambiguous", error="buy response is malformed")
            return
        buy_metadata = contract_metadata(buy)
        if (
            buy_metadata.get("contract_type") is not None
            and buy_metadata.get("contract_type") != direction
        ) or (
            buy_metadata.get("symbol") is not None
            and buy_metadata.get("symbol") != chosen_symbol
        ) or (
            buy_metadata.get("multiplier") is not None
            and buy_metadata.get("multiplier") != self.config.multiplier
        ):
            self.disable_new_buys("buy_response_mismatch", f"buy_trial_{trial}")
            self.emit("buy_ambiguous", action="buy_ambiguous", error="buy response parameters differ")
            return
        contract_id = buy.get("contract_id")
        raw_buy_price = _finite_float(buy.get("buy_price"))
        if raw_buy_price is not None and raw_buy_price <= 0:
            self.disable_new_buys("buy_response_unresolved", f"buy_trial_{trial}")
            self.emit("buy_ambiguous", action="buy_ambiguous", error="buy price is invalid")
            return
        buy_price = raw_buy_price or proposal.ask_price
        if not contract_id or buy_price is None:
            self.disable_new_buys("buy_response_unresolved", f"buy_trial_{trial}")
            self.emit("buy_ambiguous", action="buy_ambiguous", error="contract id or buy price missing")
            return
        self.machine_state = "BUY_CONFIRMED"
        if self.config.trend_alignment_enabled:
            alternation_after = direction
        else:
            alternation_after = "MULTDOWN" if direction == "MULTUP" else "MULTUP"
        record = {
            "owner": "d107_created",
            "contract_id": str(contract_id),
            "lifecycle": "cancellation_window_monitoring",
            "direction": direction,
            "contract_type": direction,
            "symbol": chosen_symbol,
            "stake": proposal.stake,
            "multiplier": self.config.multiplier,
            "cancellation": self.config.cancellation,
            "cancellation_fee": proposal.cancellation_fee,
            "buy_price": buy_price,
            "date_start": proposal.date_start,
            "purchase_time": _finite_float(buy.get("purchase_time")) or proposal.date_start,
            "cancellation_expiry": proposal.cancellation_expiry,
            "shortcode": buy.get("shortcode") or proposal.shortcode,
            "alternation_before": direction,
            "alternation_after": alternation_after,
            "confirmed_at": utc_now(),
            "peak_unrealized_pnl": None,
        }
        self.state["contracts"][str(contract_id)] = record
        self.state["pending_buy"] = None
        self.state["last_confirmed_direction"] = direction
        self.state["next_direction"] = alternation_after
        self.state["direction_sequence"].append(direction)
        self.state["confirmed_buys"] = int(self.state.get("confirmed_buys", 0)) + 1
        if self.config.mode == "canary" and self.state["confirmed_buys"] >= self.config.canary_buys:
            self.state["new_buys_enabled"] = False
            self.state["stop_reason"] = "canary_complete"
        self._save_state()
        self.emit(
            "buy_confirmed",
            action="buy_confirmed",
            contract_id=str(contract_id),
            contract_type=direction,
            direction=direction,
            alternation_before=direction,
            alternation_after=alternation_after,
            direction_sequence=self.state["direction_sequence"],
            buy_price=buy_price,
            date_start=proposal.date_start,
            purchase_time=record["purchase_time"],
            cancellation_expiry=proposal.cancellation_expiry,
            shortcode=record["shortcode"],
            elapsed_request_seconds=time.monotonic() - started,
        )
        self.start_monitor(str(contract_id))

    async def open_contract(
        self,
        contract_id: str,
        *,
        force_request: bool = False,
        max_age_seconds: float = 12.0,
    ) -> Mapping[str, Any]:
        cid = _api_contract_id(contract_id)
        if not force_request and hasattr(self.client, "contract_streams"):
            cached = self.client.contract_streams.get(cid)
            cache_time = getattr(self.client, "contract_stream_times", {}).get(cid, 0.0)
            now_mono = time.monotonic()
            if isinstance(cached, Mapping) and (now_mono - cache_time) <= max_age_seconds:
                return cached

        payload: dict[str, Any] = {"proposal_open_contract": 1, "contract_id": cid}
        if str(contract_id) not in self.subscribed_contracts:
            payload["subscribe"] = 1
            self.subscribed_contracts.add(str(contract_id))
        response = await self.request(payload, timeout=20.0)
        error = _api_error(response)
        if error:
            raise ReconciliationRequired(f"open contract request failed: {error['message']}")
        contract = response.get("proposal_open_contract")
        if not isinstance(contract, Mapping):
            raise ReconciliationRequired("open contract response is empty")
        if hasattr(self.client, "contract_streams"):
            self.client.contract_streams[cid] = dict(contract)
            self.client.contract_streams[str(cid)] = dict(contract)
            if hasattr(self.client, "contract_stream_times"):
                now_ts = time.monotonic()
                self.client.contract_stream_times[cid] = now_ts
                self.client.contract_stream_times[str(cid)] = now_ts
        return contract

    async def current_spot(self, symbol: Optional[str] = None) -> Optional[float]:
        target = symbol or self.config.symbol
        response = await self.request({"ticks": target}, timeout=10.0)
        error = _api_error(response)
        if error:
            return None
        tick = response.get("tick")
        return _positive_float(tick.get("quote")) if isinstance(tick, Mapping) else None

    async def entry_spot_from_history(self, purchase_time: Any, symbol: Optional[str] = None) -> Optional[float]:
        timestamp = _finite_int(purchase_time)
        if timestamp is None or timestamp <= 0:
            return None
        target = symbol or self.config.symbol
        response = await self.request(
            {
                "ticks_history": target,
                "start": timestamp - 5,
                "end": timestamp + 5,
                "count": 10,
                "style": "ticks",
            },
            timeout=15.0,
        )
        error = _api_error(response)
        if error:
            return None
        history = response.get("history")
        if not isinstance(history, Mapping):
            return None
        prices = history.get("prices")
        times = history.get("times")
        if not isinstance(prices, list) or not prices:
            return None
        if isinstance(times, list) and len(times) == len(prices):
            candidates = []
            for raw_time, raw_price in zip(times, prices):
                numeric_time = _finite_float(raw_time)
                numeric_price = _positive_float(raw_price)
                if numeric_time is not None and numeric_price is not None:
                    candidates.append((abs(numeric_time - timestamp), numeric_price))
            if candidates:
                return min(candidates, key=lambda item: item[0])[1]
        return _positive_float(prices[-1])

    async def collect_evidence(
        self,
        record: Mapping[str, Any],
        raw: Mapping[str, Any],
    ) -> PnlEvidence:
        pos_symbol = record.get("symbol") or self.config.symbol
        fallback_entry = _positive_float(raw.get("entry_spot")) or _positive_float(
            record.get("entry_spot")
        )
        if fallback_entry is None:
            fallback_entry = await self.entry_spot_from_history(
                raw.get("date_start") or record.get("purchase_time"),
                symbol=pos_symbol,
            )
        fallback_current = _positive_float(raw.get("current_spot"))
        if fallback_current is None:
            fallback_current = await self.current_spot(symbol=pos_symbol)
        metadata = dict(record)
        metadata.setdefault("contract_id", record.get("contract_id"))
        metadata.setdefault("contract_type", record.get("direction"))
        metadata.setdefault("multiplier", self.config.multiplier)
        evidence = pnl_evidence_from_contract(
            raw,
            metadata,
            fallback_entry_spot=fallback_entry,
            fallback_current_spot=fallback_current,
        )
        return evidence

    def update_observation(self, record: dict[str, Any], raw: Mapping[str, Any], evidence: PnlEvidence) -> None:
        record["last_observation_at"] = utc_now()
        record["last_profit"] = evidence.decision.pnl
        record["api_profit"] = evidence.decision.api_profit
        record["reconstructed_profit"] = evidence.decision.reconstructed_profit
        record["pnl_source"] = evidence.decision.pnl_source
        record["entry_spot"] = evidence.entry_spot
        record["current_spot"] = evidence.current_spot
        record["bid_price"] = evidence.bid_price
        record["is_valid_to_cancel"] = evidence.is_valid_to_cancel
        record["is_valid_to_sell"] = evidence.is_valid_to_sell
        if evidence.decision.pnl is not None:
            peak = _finite_float(record.get("peak_unrealized_pnl"))
            record["peak_unrealized_pnl"] = (
                evidence.decision.pnl if peak is None else max(peak, evidence.decision.pnl)
            )
            if record.get("lifecycle") == "held_winner":
                held_peak = _finite_float(record.get("held_peak_unrealized_pnl"))
                record["held_peak_unrealized_pnl"] = (
                    evidence.decision.pnl if held_peak is None else max(held_peak, evidence.decision.pnl)
                )
        self._save_state()
        now = time.time()
        last_log = self._last_observation_log.get(str(record["contract_id"]), 0.0)
        if now - last_log >= self.config.observation_log_seconds:
            self._last_observation_log[str(record["contract_id"])] = now
            fields = {
                "action": "contract_observation",
                "contract_id": record["contract_id"],
                "direction": record.get("direction"),
                **evidence.as_log_record(),
            }
            if self.config.log_raw_observations:
                fields["raw_contract"] = raw
            self.emit("contract_observation", **fields)

    def mark_unresolved(self, record: Mapping[str, Any], action: str, reason: str, **fields: Any) -> None:
        contract_id = str(record["contract_id"])
        mutable = self.state["contracts"].setdefault(contract_id, dict(record))
        lifecycle = "cancellation_window_missed" if action == "cancel_window_missed" else (
            "unresolved" if action == "unresolved" else action
        )
        mutable["lifecycle"] = lifecycle
        mutable["unresolved_reason"] = reason
        self.machine_state = "RECONCILIATION_REQUIRED"
        self.disable_new_buys(reason, contract_id)
        self.emit(
            "reconciliation_required",
            action=action,
            contract_id=contract_id,
            error=reason,
            **fields,
        )

    async def handle_boundary(self, record: dict[str, Any], raw: Mapping[str, Any]) -> None:
        self.machine_state = "BOUNDARY_CLASSIFICATION"
        try:
            evidence = await self.collect_evidence(record, raw)
        except (ApiRequestError, ReconciliationRequired) as exc:
            self.mark_unresolved(record, "unresolved", _safe_error_message(exc))
            return
        self.update_observation(record, raw, evidence)
        decision = evidence.decision
        if decision.classification == "validated_loss":
            if evidence.is_valid_to_cancel is True:
                await self.cancel_loser(record, evidence)
            elif evidence.is_valid_to_cancel is False:
                self.mark_unresolved(
                    record,
                    "cancel_window_missed",
                    "validated loss arrived after cancellation validity ended",
                    **evidence.as_log_record(),
                )
            else:
                self.mark_unresolved(
                    record,
                    "unresolved",
                    "cancellation validity was not returned by the API",
                    **evidence.as_log_record(),
                )
        elif decision.classification == "validated_winner":
            # STRICT WINNER QUALIFICATION FOR PERPETUAL CONVERSION:
            # Positions only transition to held_winner at 4m45s boundary if
            # net profit >= cancel fee AND trend momentum supports continuation.
            stake = _positive_float(record.get("stake")) or self.config.stake
            buy_price = (
                _positive_float(record.get("buy_price"))
                or _positive_float(raw.get("buy_price"))
                or stake
            )
            cancel_fee = _finite_float(record.get("cancellation_fee"))
            if cancel_fee is None:
                cancel_fee = max(0.0, round(buy_price - stake, 10))
            gross_profit = _finite_float(decision.pnl) or 0.0
            net_profit = round(gross_profit - cancel_fee, 10)

            trend_supports = True
            direction = record.get("direction")
            if self.config.trend_alignment_enabled:
                trend_signal = await evaluate_market_trend(
                    record.get("symbol") or self.config.symbol, self.client
                )
                if trend_signal.is_aligned and trend_signal.direction in CONTRACT_TYPES:
                    if trend_signal.direction != direction:
                        trend_supports = False
                else:
                    live_trend = await self.detect_realtime_micro_trend(
                        record.get("symbol") or self.config.symbol
                    )
                    if live_trend is not None and live_trend != direction:
                        trend_supports = False

            if net_profit < cancel_fee or not trend_supports:
                if evidence.is_valid_to_cancel is True:
                    self.emit(
                        "defensive_cancel_marginal_winner",
                        action="cancel_requested",
                        contract_id=record.get("contract_id"),
                        gross_profit=gross_profit,
                        net_profit=net_profit,
                        cancel_fee=cancel_fee,
                        trend_supports=trend_supports,
                        **evidence.as_log_record(),
                    )
                    await self.cancel_loser(record, evidence)
                elif evidence.is_valid_to_cancel is False:
                    self.mark_unresolved(
                        record,
                        "cancel_window_missed",
                        "marginal winner below cancellation fee or contrary trend arrived after cancellation validity ended",
                        **evidence.as_log_record(),
                    )
                else:
                    self.mark_unresolved(
                        record,
                        "unresolved",
                        "cancellation validity was not returned by the API",
                        **evidence.as_log_record(),
                    )
            else:
                await self.hold_winner(record, evidence)
        elif decision.classification == "neutral":
            self.mark_unresolved(
                record,
                "unresolved",
                "neutral P&L is not a validated winner or loss",
                **evidence.as_log_record(),
            )
        else:
            self.mark_unresolved(
                record,
                "unresolved",
                decision.reason,
                **evidence.as_log_record(),
            )

    async def cancel_loser(self, record: dict[str, Any], evidence: PnlEvidence) -> None:
        self.machine_state = "CANCEL_REQUESTED"
        contract_id = str(record["contract_id"])
        record["lifecycle"] = "cancel_requested"
        self._save_state()
        expiry = _finite_float(record.get("cancellation_expiry"))
        if expiry is None:
            self.mark_unresolved(record, "unresolved", "cancellation expiry is missing")
            return
        for attempt in range(1, MAX_CANCEL_RETRIES + 1):
            if not cancellation_retry_allowed(time.time(), expiry):
                self.mark_unresolved(
                    record,
                    "cancel_window_missed",
                    "cancellation deadline passed before retry",
                    retry_count=attempt - 1,
                )
                return
            started = time.monotonic()
            try:
                response = await self.request({"cancel": _api_contract_id(contract_id)}, timeout=10.0)
            except ApiRequestError as exc:
                error = {"code": None, "message": _safe_error_message(exc)}
                self.emit(
                    "cancel_attempt",
                    action="cancel_requested",
                    contract_id=contract_id,
                    retry_count=attempt,
                    api_error_message=error["message"],
                    rate_limit=False,
                    elapsed_request_seconds=time.monotonic() - started,
                )
                self.mark_unresolved(record, "cancel_failed", "cancel request became ambiguous")
                return
            error = _api_error(response)
            self.emit(
                "cancel_attempt",
                action="cancel_requested",
                contract_id=contract_id,
                retry_count=attempt,
                api_error_code=error.get("code") if error else None,
                api_error_message=error.get("message") if error else None,
                rate_limit=is_rate_limit_error(error),
                elapsed_request_seconds=time.monotonic() - started,
            )
            cancel_data = response.get("cancel") if not error else None
            sold_for = _finite_float(cancel_data.get("sold_for")) if isinstance(cancel_data, Mapping) else None
            if not error and sold_for is not None:
                self.machine_state = "CANCEL_CONFIRMED"
                stake = _positive_float(record.get("stake")) or self.config.stake
                fee = _finite_float(record.get("cancellation_fee"))
                if fee is None:
                    fee = max(0.0, (_finite_float(record.get("buy_price")) or stake) - stake)
                record["lifecycle"] = "closed_loser"
                record["cancelled_at"] = utc_now()
                record["sold_for"] = sold_for
                record["cancel_attempts"] = attempt
                self.state["session_realized_pnl"] = round(
                    float(self.state.get("session_realized_pnl", 0.0)) + sold_for - stake, 10
                )
                self.state["cancellation_fees"] = round(
                    float(self.state.get("cancellation_fees", 0.0)) + fee, 10
                )
                self.state["unresolved_contracts"] = [
                    item for item in self.state.get("unresolved_contracts", []) if item != contract_id
                ]
                self.machine_state = "READY"
                self._save_state()
                self.emit(
                    "cancel_confirmed",
                    action="cancelled_loser",
                    contract_id=contract_id,
                    sold_for=sold_for,
                    cancellation_fee=fee,
                    retry_count=attempt,
                    **evidence.as_log_record(),
                )
                return
            if attempt < MAX_CANCEL_RETRIES:
                delay = next_cancel_backoff(attempt)
                remaining = expiry - time.time() - CANCEL_RETRY_SAFETY_SECONDS
                if remaining <= 0:
                    break
                await asyncio.sleep(min(delay, remaining))
        self.mark_unresolved(
            record,
            "cancel_failed",
            "cancellation failed before the API-confirmed expiry",
            retry_count=MAX_CANCEL_RETRIES,
        )

    async def hold_winner(self, record: dict[str, Any], evidence: PnlEvidence) -> None:
        self.machine_state = "HELD_WINNER"
        contract_id = str(record["contract_id"])
        record["lifecycle"] = "held_winner"
        record["held_at"] = utc_now()
        record["winner_pnl_source"] = evidence.decision.pnl_source
        record["winner_profit_at_boundary"] = evidence.decision.pnl
        record["held_peak_unrealized_pnl"] = max(0.0, _finite_float(evidence.decision.pnl) or 0.0)
        self.state["unresolved_contracts"] = [
            item for item in self.state.get("unresolved_contracts", []) if item != contract_id
        ]
        self._save_state()
        self.emit(
            "held_winner",
            action="held_winner",
            contract_id=contract_id,
            direction=record.get("direction"),
            **evidence.as_log_record(),
        )
        await self.monitor_held_winner(record)

    async def mark_external_close(self, record: dict[str, Any], raw: Mapping[str, Any]) -> None:
        contract_id = str(record["contract_id"])
        lifecycle_before = record.get("lifecycle")
        record["lifecycle"] = "auto_stopped" if lifecycle_before == "held_winner" else "closed_external"
        record["closed_at"] = utc_now()
        record["terminal_status"] = raw.get("status")
        self._save_state()
        self.disable_new_buys("external_or_platform_close", contract_id)
        self.emit(
            "manual_reconciliation",
            action="manual_reconciliation",
            contract_id=contract_id,
            lifecycle_before=lifecycle_before,
            terminal_status=raw.get("status"),
            raw_contract=raw,
        )

    def evaluate_winner_exit(
        self,
        record: Mapping[str, Any],
        raw: Mapping[str, Any],
        evidence: PnlEvidence,
        *,
        now: Optional[float] = None,
    ) -> tuple[bool, str]:
        if not self.config.auto_sell_winners:
            return False, "auto_sell_disabled"
        if evidence.is_valid_to_sell is not True:
            return False, "not_valid_to_sell"
        bid_price = _positive_float(raw.get("bid_price"))
        buy_price = (
            _positive_float(record.get("buy_price"))
            or _positive_float(raw.get("buy_price"))
            or self.config.stake
        )
        if bid_price is None or buy_price is None or buy_price <= 0:
            return False, "invalid_prices"

        stake = _positive_float(record.get("stake")) or self.config.stake
        cancel_fee = _finite_float(record.get("cancellation_fee"))
        if cancel_fee is None:
            cancel_fee = max(0.0, round(buy_price - stake, 10))
        net_pnl = round(bid_price - buy_price, 10)

        # -------------------------------------------------------------
        # CASO 1: DENTRO DA JANELA DE CANCELAMENTO (is_valid_to_cancel is True)
        # -------------------------------------------------------------
        if evidence.is_valid_to_cancel is True:
            # Intra-window premature micro-scalping exits are abolished.
            # The 5-minute cancellation window exists solely as an asymmetric option
            # to filter out losers at the 4m45s boundary while letting strong winners
            # cross into perpetual runners.
            if not self.config.in_window_auto_sell:
                return False, "in_window_auto_sell_disabled"
            return False, "cancellation_window_monitoring"

        # -------------------------------------------------------------
        # CASO 2: CONVERTIDO EM PERPÉTUO (held_winner, pós-boundary)
        # -------------------------------------------------------------
        # 1. Take-profit target perpétuo (bid_price >= buy_price * winner_exit_multiple)
        if self.config.winner_exit_multiple and bid_price >= buy_price * self.config.winner_exit_multiple:
            return True, "winner_exit_multiple"

        # Peak NET PnL pós-transição perpétua (NET vs NET)
        held_peak = _finite_float(record.get("held_peak_unrealized_pnl"))
        peak_pnl = held_peak if held_peak is not None else (_finite_float(record.get("peak_unrealized_pnl")) or 0.0)
        peak_net_pnl = max(0.0, round(peak_pnl - cancel_fee, 10))

        # 2. 4-Tier Progressive Perpetual Ratchet on peak_net_pnl (captura de 1x-8x do stake)
        ratchet = evaluate_perpetual_ratchet(
            net_pnl,
            stake,
            peak_net_pnl,
            take_profit_multiple=self.config.winner_exit_multiple or 8.0,
        )
        if ratchet.should_exit:
            return True, ratchet.exit_reason

        # Held duration
        held_at_str = record.get("held_at") or record.get("confirmed_at")
        time_held = 0.0
        if held_at_str:
            try:
                clean_str = str(held_at_str).replace("Z", "+00:00")
                dt = datetime.fromisoformat(clean_str)
                held_ts = dt.timestamp()
                current_time = time.time() if now is None else now
                time_held = max(0.0, current_time - held_ts)
            except Exception:
                time_held = 0.0

        # 2. Capital preservation (relaxed to 0.35 * stake to avoid cutting viable runners on normal noise)
        if (
            self.config.winner_capital_preservation_loss is not None
            and self.config.winner_capital_preservation_loss > 0.0
        ):
            loss_cap = self.config.winner_capital_preservation_loss * stake
            if peak_net_pnl < 1.0 * stake and time_held >= 30.0 and net_pnl <= -loss_cap:
                return True, "winner_capital_preservation"

        # 3. Time-based exit: max hold time exceeded
        if self.config.winner_max_hold_seconds and time_held >= self.config.winner_max_hold_seconds:
            return True, "winner_time_stop"

        return False, "holding"

    def should_auto_sell_winner(
        self,
        record: Mapping[str, Any],
        raw: Mapping[str, Any],
        evidence: PnlEvidence,
        *,
        now: Optional[float] = None,
    ) -> bool:
        should_sell, reason = self.evaluate_winner_exit(record, raw, evidence, now=now)
        if should_sell:
            cid = str(record.get("contract_id"))
            self._last_exit_reason[cid] = reason
        return should_sell

    async def sell_winner(self, record: dict[str, Any], evidence: PnlEvidence) -> None:
        self.machine_state = "SELL_REQUESTED"
        contract_id = str(record["contract_id"])
        record["lifecycle"] = "sell_requested"
        self._save_state()
        for attempt in range(1, MAX_SELL_RETRIES + 1):
            started = time.monotonic()
            try:
                response = await self.request({"sell": _api_contract_id(contract_id), "price": 0}, timeout=10.0)
            except ApiRequestError as exc:
                self.emit(
                    "sell_attempt",
                    action="sell_requested",
                    contract_id=contract_id,
                    retry_count=attempt,
                    api_error_message=_safe_error_message(exc),
                    ambiguous=exc.ambiguous,
                    elapsed_request_seconds=time.monotonic() - started,
                )
                self.mark_unresolved(record, "sell_failed", "winner sell request became ambiguous")
                return
            error = _api_error(response)
            sell_data = response.get("sell") if not error else None
            sold_for = _finite_float(sell_data.get("sold_for")) if isinstance(sell_data, Mapping) else None
            self.emit(
                "sell_attempt",
                action="sell_requested",
                contract_id=contract_id,
                retry_count=attempt,
                api_error_code=error.get("code") if error else None,
                api_error_message=error.get("message") if error else None,
                rate_limit=is_rate_limit_error(error),
                elapsed_request_seconds=time.monotonic() - started,
            )
            if not error and sold_for is not None:
                buy_price = _positive_float(record.get("buy_price")) or self.config.stake
                exit_reason = self._last_exit_reason.get(contract_id, "winner_exit_multiple")
                record["lifecycle"] = "closed_target"
                record["closed_at"] = utc_now()
                record["sold_for"] = sold_for
                record["close_reason"] = exit_reason
                record["winner_exit_multiple"] = self.config.winner_exit_multiple
                record["realized_pnl"] = round(sold_for - buy_price, 10)
                self.state["session_realized_pnl"] = round(
                    float(self.state.get("session_realized_pnl", 0.0)) + sold_for - buy_price, 10
                )
                self.state["unresolved_contracts"] = [
                    item for item in self.state.get("unresolved_contracts", []) if item != contract_id
                ]
                self.machine_state = "READY"
                self._save_state()
                self.emit(
                    "sell_confirmed",
                    action=f"sold_{exit_reason}",
                    contract_id=contract_id,
                    sold_for=sold_for,
                    buy_price=buy_price,
                    realized_pnl=record["realized_pnl"],
                    close_reason=exit_reason,
                    winner_exit_multiple=self.config.winner_exit_multiple,
                    retry_count=attempt,
                    **evidence.as_log_record(),
                )
                return
            if attempt < MAX_SELL_RETRIES and not error:
                break
            if attempt < MAX_SELL_RETRIES:
                await asyncio.sleep(next_cancel_backoff(attempt))
        self.mark_unresolved(record, "sell_failed", "winner sell failed after bounded retries")

    async def set_native_stop_loss(self, contract_id: str, stop_loss_amount: float) -> bool:
        """Sets a catastrophic native hard stop loss directly on Deriv broker servers."""
        try:
            started = time.monotonic()
            response = await self.request({
                "contract_update": 1,
                "contract_id": _api_contract_id(contract_id),
                "limit_order": {
                    "stop_loss": round(stop_loss_amount, 2)
                }
            }, timeout=10.0)
            error = _api_error(response)
            if not error:
                self.emit(
                    "native_stop_loss_set",
                    action="native_stop_loss_set",
                    contract_id=contract_id,
                    stop_loss=stop_loss_amount,
                    elapsed_request_seconds=time.monotonic() - started,
                )
                return True
            self.emit(
                "native_stop_loss_rejected",
                action="native_stop_loss_rejected",
                contract_id=contract_id,
                api_error_code=error.get("code"),
                api_error_message=error.get("message"),
            )
        except Exception as exc:
            self.emit(
                "native_stop_loss_error",
                action="native_stop_loss_error",
                contract_id=contract_id,
                error=_safe_error_message(exc),
            )
        return False

    async def monitor_held_winner(self, record: dict[str, Any]) -> None:
        contract_id = str(record["contract_id"])
        while self.state["contracts"].get(contract_id, {}).get("lifecycle") == "held_winner":
            try:
                # Set native broker stop loss only when capital preservation is explicitly enabled
                if (
                    self.config.winner_capital_preservation_loss
                    and self.config.winner_capital_preservation_loss > 0.0
                    and not record.get("native_stop_loss_set")
                    and record.get("native_stop_loss_attempts", 0) < 5
                ):
                    expiry = _finite_float(record.get("cancellation_expiry"))
                    if expiry is None:
                        start = _finite_float(record.get("purchase_time")) or _finite_float(record.get("date_start"))
                        if start is not None:
                            expiry = start + 300.0
                    now_ts = time.time()
                    if expiry is None or now_ts >= expiry + 5.0:
                        record["native_stop_loss_attempts"] = record.get("native_stop_loss_attempts", 0) + 1
                        stake = _positive_float(record.get("stake")) or self.config.stake
                        if await self.set_native_stop_loss(contract_id, stake * 0.35):
                            record["native_stop_loss_set"] = True
                            self._save_state()

                raw = await self.open_contract(contract_id)
                if _terminal_contract(raw):
                    await self.mark_external_close(record, raw)
                    return
                evidence = await self.collect_evidence(record, raw)
                self.update_observation(record, raw, evidence)
                if self.should_auto_sell_winner(record, raw, evidence):
                    await self.sell_winner(record, evidence)
                    return
                if time.time() - self._last_observation_log.get(contract_id, 0.0) >= self.config.portfolio_snapshot_seconds:
                    self.emit(
                        "held_winner_monitor",
                        action="held_winner",
                        contract_id=contract_id,
                        **evidence.as_log_record(),
                    )
                await asyncio.sleep(min(3.0, self.config.portfolio_snapshot_seconds))
            except (ApiRequestError, ReconciliationRequired) as exc:
                self.mark_unresolved(record, "unresolved", _safe_error_message(exc))
                return

    async def monitor_contract(self, contract_id: str) -> None:
        try:
            self.machine_state = "CANCELLATION_WINDOW_MONITORING"
            record = self.state["contracts"].get(contract_id)
            if not record:
                self.disable_new_buys("unknown_contract", contract_id)
                return
            if record.get("lifecycle") == "held_winner":
                await self.monitor_held_winner(record)
                return
            expiry = _finite_float(record.get("cancellation_expiry"))
            decision_at = cancellation_decision_timestamp(
                expiry, self.config.boundary_buffer_seconds
            )
            if expiry is None or decision_at is None:
                self.mark_unresolved(record, "unresolved", "cancellation expiry is not valid")
                return
            while self.state["contracts"].get(contract_id, {}).get("lifecycle") in {
                "cancellation_window_monitoring",
                "buy_confirmed",
                "cancel_requested",
            }:
                now = time.time()
                raw = await self.open_contract(contract_id)
                if _terminal_contract(raw):
                    await self.mark_external_close(record, raw)
                    return
                evidence = await self.collect_evidence(record, raw)
                self.update_observation(record, raw, evidence)
                if self.should_auto_sell_winner(record, raw, evidence, now=now):
                    await self.sell_winner(record, evidence)
                    return
                if now >= decision_at or now >= expiry:
                    await self.handle_boundary(record, raw)
                    if self.state["contracts"].get(contract_id, {}).get("lifecycle") == "held_winner":
                        await self.monitor_held_winner(record)
                    return
                remaining_to_decision = decision_at - now
                await asyncio.sleep(min(3.0, max(0.25, remaining_to_decision)))
        except (ApiRequestError, ReconciliationRequired) as exc:
            record = self.state.get("contracts", {}).get(contract_id, {"contract_id": contract_id})
            self.mark_unresolved(record, "unresolved", _safe_error_message(exc))
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            record = self.state.get("contracts", {}).get(contract_id, {"contract_id": contract_id})
            self.mark_unresolved(record, "unresolved", _safe_error_message(exc))

    def snapshot_summary(self, unrealized_pnl: float, unknown_positions: int) -> dict[str, Any]:
        contracts = self.state.get("contracts", {}).values()
        return {
            "opened": self.state.get("confirmed_buys", 0),
            "cancelled": sum(1 for item in contracts if item.get("lifecycle") == "closed_loser"),
            "held_winners": sum(1 for item in contracts if item.get("lifecycle") == "held_winner"),
            "cancel_failures": sum(1 for item in contracts if item.get("lifecycle") == "cancel_failed"),
            "sell_winners": sum(1 for item in contracts if item.get("lifecycle") == "closed_target"),
            "unresolved_loss_exits": sum(
                1 for item in contracts if item.get("lifecycle") == "closed_unresolved_loss"
            ),
            "sell_failures": sum(1 for item in contracts if item.get("lifecycle") == "sell_failed"),
            "unresolved": len(self.state.get("unresolved_contracts", [])) + unknown_positions,
            "fees_paid": self.state.get("cancellation_fees", 0.0),
            "realized_pnl": self.state.get("session_realized_pnl", 0.0),
            "unrealized_pnl": unrealized_pnl,
            "open_count": len(self.portfolio_positions),
            "deployed_capital": self.state.get("deployed_capital", 0.0),
            "new_buys_enabled": self.state.get("new_buys_enabled", False),
        }

    async def write_portfolio_snapshot(self) -> None:
        try:
            balance = await self.fetch_balance()
            contracts = await self.fetch_portfolio()
            await self.reconcile_portfolio(contracts, strict=False)
            self.refresh_continuous_buy_gate(balance)
            positions = []
            total_unrealized = 0.0
            unknown_positions = len(self.portfolio_unknown)
            for position in self.portfolio_positions:
                metadata = contract_metadata(position)
                contract_id = str(metadata.get("contract_id"))
                owner_record = self.state.get("contracts", {}).get(contract_id)
                if owner_record:
                    owner = "d107_created"
                    record = owner_record
                else:
                    owner = "legacy_external"
                    record = {
                        **metadata,
                        "contract_id": contract_id,
                        "direction": metadata.get("contract_type"),
                        "stake": metadata.get("stake"),
                    }
                try:
                    raw = await self.open_contract(contract_id)
                    evidence = await self.collect_evidence(record, raw)
                    if evidence.decision.pnl is not None:
                        total_unrealized += evidence.decision.pnl
                    position_data = {
                        "ownership": owner,
                        "lifecycle": owner_record.get("lifecycle") if owner_record else "legacy_external",
                        "contract_id": contract_id,
                        "contract_type": metadata.get("contract_type"),
                        "buy_price": metadata.get("buy_price"),
                        **evidence.as_log_record(),
                    }
                except (ApiRequestError, ReconciliationRequired) as exc:
                    unknown_positions += 1
                    position_data = {
                        "ownership": owner,
                        "contract_id": contract_id,
                        "classification": "unknown",
                        "pnl_source": "unknown",
                        "error": _safe_error_message(exc),
                    }
                positions.append(position_data)
            summary = self.snapshot_summary(total_unrealized, unknown_positions)
            self.state["last_portfolio_snapshot_at"] = utc_now()
            self._save_state()
            self.emit(
                "portfolio_snapshot",
                action="portfolio_snapshot",
                balance=balance,
                positions=positions,
                summary=summary,
                unknown_positions=unknown_positions,
            )
            print(
                f"[D107] opened={summary['opened']} cancelled={summary['cancelled']} "
                f"held_winners={summary['held_winners']} cancel_failures={summary['cancel_failures']} "
                f"unresolved={summary['unresolved']} fees=${summary['fees_paid']:.2f} "
                f"realized=${summary['realized_pnl']:.2f} unrealized=${summary['unrealized_pnl']:.2f} "
                f"open={summary['open_count']} deployed=${summary['deployed_capital']:.2f} "
                f"new_buys_enabled={summary['new_buys_enabled']}",
                flush=True,
            )
        except (ApiRequestError, ReconciliationRequired) as exc:
            self.disable_new_buys("portfolio_snapshot_failure")
            self.emit("reconciliation_required", action="unresolved", error=_safe_error_message(exc))

    async def operation_loop(self) -> None:
        next_snapshot = 0.0
        while not self.stop_event.is_set():
            now = time.time()
            if now >= next_snapshot:
                await self.write_portfolio_snapshot()
                next_snapshot = time.time() + self.config.portfolio_snapshot_seconds
            if self.state.get("new_buys_enabled"):
                await self.try_buy()
            await asyncio.sleep(min(self.config.inter_trial_seconds, self.config.portfolio_snapshot_seconds))

    async def run(self) -> None:
        self.config.prepare_paths()
        app_id = os.getenv("DERIV_APP_ID")
        token = os.getenv("DERIV_API_TOKEN")
        if not app_id or not token:
            raise ConfigError("DERIV_APP_ID and DERIV_API_TOKEN are required")
        connected = False
        for attempt in range(3):
            try:
                await self.client.connect()
                connected = True
                break
            except Exception:
                if attempt == 2:
                    raise
                await asyncio.sleep(30 * (attempt + 1))
        if not connected:
            raise ReconciliationRequired("D107 could not establish the Demo WebSocket")
        try:
            await self.preflight()
            await self.operation_loop()
        finally:
            self.stop_event.set()
            current = asyncio.current_task()
            tasks = [task for task in self.monitor_tasks.values() if task is not current and not task.done()]
            for task in tasks:
                task.cancel()
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)
            await self.client.disconnect()


async def async_main() -> None:
    config = D107Config.from_env()
    client = DerivClient(
        app_id=os.getenv("DERIV_APP_ID"),
        api_token=os.getenv("DERIV_API_TOKEN"),
        use_demo=True,
    )
    bot = D107Bot(client, config)
    await bot.run()


def main() -> None:
    try:
        asyncio.run(async_main())
    except KeyboardInterrupt:
        print("[D107] stopped by operator", flush=True)
    except D107Error as exc:
        print(f"[D107] stopped safely: {_safe_error_message(exc)}", flush=True)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
