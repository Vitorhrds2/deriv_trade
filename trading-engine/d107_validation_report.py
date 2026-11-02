#!/usr/bin/env python3
"""Offline validation and bankroll report for D107.

This tool reads the append-only D107 event log and optional persisted state. It
never sends trading requests. It separates operational reliability, lifecycle
outcomes, fixed-horizon mark-to-market results, simple counterfactuals, market
regime coverage, and hypothetical bankroll scenarios.
"""
from __future__ import annotations

import argparse
import json
import math
import random
import statistics
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence


DEFAULT_HORIZONS_HOURS = (1, 6, 24)
DEFAULT_MIN_OPERATIONAL_BUYS = 100
DEFAULT_MIN_ECONOMIC_BUYS = 200
DEFAULT_MIN_REGIMES = 3
DEFAULT_TARGET_WITHDRAWAL = 1000.0
DEFAULT_DEPLOYED_PCT = 0.20
DEFAULT_MAX_POSITIONS = 10
DEFAULT_STAKE = 1.0
DEFAULT_MULTIPLIER = 400
DEFAULT_CANCELLATION_FEE = 0.04
REGIME_BLOCK_HOURS = 24


@dataclass
class Observation:
    timestamp: float
    pnl: Optional[float]
    source: str
    classification: str
    api_profit: Optional[float] = None
    reconstructed_profit: Optional[float] = None
    entry_spot: Optional[float] = None
    current_spot: Optional[float] = None
    event: str = ""


@dataclass
class ContractRecord:
    contract_id: str
    direction: Optional[str] = None
    stake: float = DEFAULT_STAKE
    multiplier: int = DEFAULT_MULTIPLIER
    buy_price: Optional[float] = None
    cancellation_fee: float = 0.0
    entry_time: Optional[float] = None
    purchase_time: Optional[float] = None
    confirmed_timestamp: Optional[float] = None
    cancellation_expiry: Optional[float] = None
    lifecycle: str = "unknown"
    boundary_action: Optional[str] = None
    boundary_time: Optional[float] = None
    boundary_pnl: Optional[float] = None
    boundary_source: Optional[str] = None
    boundary_bid: Optional[float] = None
    sold_for: Optional[float] = None
    terminal_time: Optional[float] = None
    terminal_net_pnl: Optional[float] = None
    external_close_pnl: Optional[float] = None
    observations: list[Observation] = field(default_factory=list)
    unresolved_events: int = 0

    @property
    def terminal(self) -> bool:
        return self.terminal_net_pnl is not None or self.lifecycle in {
            "closed_loser",
            "closed_external",
            "auto_stopped",
        }

    @property
    def latest_observation(self) -> Optional[Observation]:
        return max(self.observations, key=lambda item: item.timestamp) if self.observations else None

    @property
    def peak_pnl(self) -> Optional[float]:
        values = [item.pnl for item in self.observations if item.pnl is not None]
        if self.boundary_pnl is not None:
            values.append(self.boundary_pnl)
        return max(values) if values else None

    @property
    def maximum_adverse_pnl(self) -> Optional[float]:
        values = [item.pnl for item in self.observations if item.pnl is not None]
        if self.boundary_pnl is not None:
            values.append(self.boundary_pnl)
        if self.terminal_net_pnl is not None:
            values.append(self.terminal_net_pnl)
        return min(values) if values else None


def finite_float(value: Any) -> Optional[float]:
    if value is None or isinstance(value, bool):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def parse_timestamp(value: Any) -> Optional[float]:
    numeric = finite_float(value)
    if numeric is not None and numeric > 100_000_000:
        return numeric
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.timestamp()


def iso_timestamp(value: Optional[float]) -> Optional[str]:
    if value is None:
        return None
    return datetime.fromtimestamp(value, tz=timezone.utc).isoformat(timespec="seconds")


def load_jsonl(path: str) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    with open(path, encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            try:
                value = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"invalid JSONL at line {line_number}: {path}") from exc
            if isinstance(value, dict):
                records.append(value)
    return records


def load_state(path: Optional[str]) -> dict[str, Any]:
    if not path or not Path(path).exists():
        return {}
    with open(path, encoding="utf-8") as handle:
        value = json.load(handle)
    return value if isinstance(value, dict) else {}


def _get_or_create(ledger: dict[str, ContractRecord], contract_id: Any) -> Optional[ContractRecord]:
    if contract_id is None:
        return None
    key = str(contract_id)
    if key not in ledger:
        ledger[key] = ContractRecord(contract_id=key)
    return ledger[key]


def _add_observation(record: ContractRecord, event: Mapping[str, Any], event_name: str, timestamp: float) -> None:
    pnl = finite_float(event.get("profit_at_action"))
    source = str(event.get("pnl_source") or "unknown")
    classification = str(event.get("classification") or "unknown")
    observation = Observation(
        timestamp=timestamp,
        pnl=pnl,
        source=source,
        classification=classification,
        api_profit=finite_float(event.get("api_profit")),
        reconstructed_profit=finite_float(event.get("reconstructed_profit")),
        entry_spot=finite_float(event.get("entry_spot")),
        current_spot=finite_float(event.get("current_spot")),
        event=event_name,
    )
    key = (round(timestamp, 3), observation.pnl, observation.source, observation.event)
    existing = {
        (round(item.timestamp, 3), item.pnl, item.source, item.event)
        for item in record.observations
    }
    if key not in existing:
        record.observations.append(observation)


def _apply_buy(record: ContractRecord, event: Mapping[str, Any], timestamp: float) -> None:
    record.direction = event.get("direction") or event.get("contract_type") or record.direction
    record.stake = finite_float(event.get("stake")) or record.stake
    record.multiplier = int(finite_float(event.get("multiplier")) or record.multiplier)
    record.buy_price = finite_float(event.get("buy_price")) or record.buy_price
    record.purchase_time = parse_timestamp(event.get("purchase_time")) or record.purchase_time
    record.entry_time = record.purchase_time or timestamp
    record.confirmed_timestamp = timestamp
    record.cancellation_fee = finite_float(event.get("cancellation_fee")) or record.cancellation_fee
    record.cancellation_expiry = (
        finite_float(event.get("cancellation_expiry")) or record.cancellation_expiry
    )
    record.lifecycle = "cancellation_window_monitoring"


def _apply_terminal(record: ContractRecord, event: Mapping[str, Any], timestamp: float) -> None:
    action = event.get("action")
    record.boundary_action = str(action) if action else record.boundary_action
    record.boundary_time = timestamp
    record.boundary_pnl = finite_float(event.get("profit_at_action"))
    record.boundary_source = event.get("pnl_source")
    record.boundary_bid = finite_float(event.get("bid_price_at_action"))
    record.sold_for = finite_float(event.get("sold_for")) or record.sold_for
    if action == "sold_winner_target":
        record.lifecycle = "closed_target"
        realized = finite_float(event.get("realized_pnl"))
        sold_for = finite_float(event.get("sold_for"))
        if realized is not None:
            record.terminal_net_pnl = realized
        elif sold_for is not None and record.buy_price is not None:
            record.terminal_net_pnl = sold_for - record.buy_price
        record.terminal_time = timestamp
        return
    if action == "cancelled_loser":
        record.lifecycle = "closed_loser"
        if record.sold_for is not None and record.buy_price is not None:
            record.terminal_net_pnl = record.sold_for - record.buy_price
        elif record.cancellation_fee:
            record.terminal_net_pnl = -record.cancellation_fee
        record.terminal_time = timestamp
        return
    if action in {"manual_reconciliation", "external_close"}:
        external = finite_float(event.get("external_close_pnl"))
        if external is not None:
            record.external_close_pnl = external
            record.terminal_net_pnl = external
            record.terminal_time = timestamp
        record.lifecycle = "closed_external"
        return
    if action in {"held_winner", "held_winner_reconciled"}:
        record.lifecycle = "held_winner"
        return
    if action == "unresolved":
        record.lifecycle = "unresolved"
        record.unresolved_events += 1


def build_ledger(
    events: Sequence[Mapping[str, Any]],
    state: Optional[Mapping[str, Any]] = None,
) -> dict[str, ContractRecord]:
    ledger: dict[str, ContractRecord] = {}
    sorted_events = sorted(events, key=lambda item: parse_timestamp(item.get("timestamp")) or 0.0)
    for event in sorted_events:
        timestamp = parse_timestamp(event.get("timestamp"))
        if timestamp is None:
            continue
        action = str(event.get("action") or "")
        event_name = str(event.get("event") or action)
        record = _get_or_create(ledger, event.get("contract_id"))
        if action == "buy_confirmed" and record is not None:
            _apply_buy(record, event, timestamp)
        if record is not None:
            if action in {
                "contract_observation",
                "held_winner",
                "held_winner_reconciled",
                "cancelled_loser",
                "unresolved",
            }:
                _add_observation(record, event, event_name, timestamp)
            if action in {
                "cancelled_loser",
                "sold_winner_target",
                "held_winner",
                "held_winner_reconciled",
                "manual_reconciliation",
                "external_close",
                "unresolved",
            }:
                _apply_terminal(record, event, timestamp)
        if event_name == "portfolio_snapshot":
            positions = event.get("positions") or []
            if isinstance(positions, list):
                for position in positions:
                    if not isinstance(position, Mapping):
                        continue
                    position_record = _get_or_create(ledger, position.get("contract_id"))
                    if position_record is None:
                        continue
                    _add_observation(position_record, position, "portfolio_snapshot", timestamp)
    if state:
        for contract_id, state_record in (state.get("contracts") or {}).items():
            record = _get_or_create(ledger, contract_id)
            if record is None or not isinstance(state_record, Mapping):
                continue
            record.direction = state_record.get("direction") or record.direction
            record.stake = finite_float(state_record.get("stake")) or record.stake
            record.multiplier = int(finite_float(state_record.get("multiplier")) or record.multiplier)
            record.buy_price = finite_float(state_record.get("buy_price")) or record.buy_price
            record.cancellation_fee = (
                finite_float(state_record.get("cancellation_fee")) or record.cancellation_fee
            )
            record.purchase_time = parse_timestamp(state_record.get("purchase_time")) or record.purchase_time
            record.entry_time = record.purchase_time or record.entry_time
            record.cancellation_expiry = (
                finite_float(state_record.get("cancellation_expiry")) or record.cancellation_expiry
            )
            record.lifecycle = str(state_record.get("lifecycle") or record.lifecycle)
            if record.lifecycle == "closed_external":
                record.external_close_pnl = (
                    finite_float(state_record.get("external_close_pnl")) or record.external_close_pnl
                )
                record.terminal_net_pnl = record.external_close_pnl
            if record.lifecycle == "closed_loser" and record.terminal_net_pnl is None:
                sold_for = finite_float(state_record.get("sold_for"))
                if sold_for is not None and record.buy_price is not None:
                    record.terminal_net_pnl = sold_for - record.buy_price
    return ledger


def _percentile(values: Sequence[float], probability: float) -> Optional[float]:
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * probability
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    weight = position - lower
    return ordered[lower] * (1 - weight) + ordered[upper] * weight


def bootstrap_mean_ci(
    values: Sequence[float],
    *,
    iterations: int = 2000,
    seed: int = 42,
) -> tuple[Optional[float], Optional[float]]:
    if len(values) < 2:
        return None, None
    rng = random.Random(seed)
    sample = list(values)
    means = []
    for _ in range(iterations):
        means.append(statistics.fmean(rng.choice(sample) for _ in sample))
    return _percentile(means, 0.025), _percentile(means, 0.975)


def wilson_interval(wins: int, total: int) -> tuple[Optional[float], Optional[float]]:
    if total <= 0:
        return None, None
    z = 1.959963984540054
    p = wins / total
    denominator = 1 + z * z / total
    center = (p + z * z / (2 * total)) / denominator
    radius = z * math.sqrt((p * (1 - p) + z * z / (4 * total)) / total) / denominator
    return max(0.0, center - radius), min(1.0, center + radius)


def _metric(values: Sequence[Optional[float]]) -> dict[str, Any]:
    clean = [value for value in values if value is not None and math.isfinite(value)]
    if not clean:
        return {"n": 0, "sum": None, "mean": None, "median": None, "ci95": [None, None]}
    lo, hi = bootstrap_mean_ci(clean)
    return {
        "n": len(clean),
        "sum": sum(clean),
        "mean": statistics.fmean(clean),
        "median": statistics.median(clean),
        "min": min(clean),
        "max": max(clean),
        "ci95": [lo, hi],
        "positive": sum(value > 0 for value in clean),
        "win_rate": sum(value > 0 for value in clean) / len(clean),
    }


def horizon_value(record: ContractRecord, hours: int) -> dict[str, Any]:
    if is_manual_external(record):
        return {"value": None, "status": "manual_external_excluded"}
    if record.entry_time is None:
        return {"value": None, "status": "missing_entry_time"}
    target = record.entry_time + hours * 3600
    future = [item for item in record.observations if item.timestamp >= target and item.pnl is not None]
    if future:
        chosen = min(future, key=lambda item: item.timestamp)
        return {
            "value": chosen.pnl,
            "status": "observed",
            "timestamp": iso_timestamp(chosen.timestamp),
            "source": chosen.source,
        }
    if record.terminal_time is not None and record.terminal_time < target and record.terminal_net_pnl is not None:
        return {
            "value": record.terminal_net_pnl,
            "status": "terminal_before_horizon",
            "timestamp": iso_timestamp(record.terminal_time),
            "source": "terminal",
        }
    return {"value": None, "status": "not_reached", "target": iso_timestamp(target)}


def reconstruct_pnl(direction: Optional[str], entry: Any, current: Any, stake: Any, multiplier: Any) -> Optional[float]:
    entry_value = finite_float(entry)
    current_value = finite_float(current)
    stake_value = finite_float(stake)
    multiplier_value = finite_float(multiplier)
    if not all(value is not None and value > 0 for value in (entry_value, current_value, stake_value, multiplier_value)):
        return None
    if direction == "MULTUP":
        return (current_value - entry_value) / entry_value * stake_value * multiplier_value
    if direction == "MULTDOWN":
        return (entry_value - current_value) / entry_value * stake_value * multiplier_value
    return None


def current_spot_from_ledger(ledger: Mapping[str, ContractRecord]) -> Optional[float]:
    candidates = []
    for record in ledger.values():
        for observation in record.observations:
            if observation.current_spot is not None:
                candidates.append((observation.timestamp, observation.current_spot))
    return max(candidates, key=lambda item: item[0])[1] if candidates else None


def is_manual_external(record: ContractRecord) -> bool:
    return record.lifecycle == "closed_external"


def strategy_net_value(record: ContractRecord) -> Optional[float]:
    if is_manual_external(record):
        return None
    if record.terminal_net_pnl is not None:
        return record.terminal_net_pnl
    latest = record.latest_observation
    return latest.pnl if latest else None


def current_net_value(record: ContractRecord) -> Optional[float]:
    return strategy_net_value(record)


def regime_summary(ledger: Mapping[str, ContractRecord], block_hours: int = REGIME_BLOCK_HOURS) -> dict[str, Any]:
    points = []
    for record in ledger.values():
        for observation in record.observations:
            if observation.current_spot is not None:
                points.append((observation.timestamp, observation.current_spot))
    if not points:
        return {"blocks": [], "distinct_regimes": 0, "coverage_hours": 0.0}
    points.sort()
    first_time = points[0][0]
    last_time = points[-1][0]
    coverage_hours = (last_time - first_time) / 3600
    blocks = []
    cursor = first_time
    while cursor + block_hours * 3600 <= last_time:
        window_end = cursor + block_hours * 3600
        window = [point for point in points if cursor <= point[0] <= window_end]
        if len(window) >= 2:
            start = window[0][1]
            end = window[-1][1]
            change = (end - start) / start if start else None
            if change is None:
                label = "unknown"
            elif change > 0.001:
                label = "up"
            elif change < -0.001:
                label = "down"
            else:
                label = "flat"
            blocks.append({
                "start": iso_timestamp(cursor),
                "end": iso_timestamp(window_end),
                "start_spot": start,
                "end_spot": end,
                "return": change,
                "regime": label,
                "observations": len(window),
            })
        cursor = window_end
    return {
        "blocks": blocks,
        "distinct_regimes": len({item["regime"] for item in blocks if item["regime"] != "unknown"}),
        "coverage_hours": coverage_hours,
    }


def benchmark_summary(ledger: Mapping[str, ContractRecord], current_spot: Optional[float]) -> dict[str, Any]:
    actual_values = [strategy_net_value(record) for record in ledger.values()]
    boundary_close_values = []
    buy_hold_values = []
    for record in ledger.values():
        if is_manual_external(record):
            continue
        if record.boundary_pnl is not None:
            if record.boundary_bid is not None and record.buy_price is not None:
                boundary_close_values.append(record.boundary_bid - record.buy_price)
            else:
                boundary_close_values.append(record.boundary_pnl)
        if current_spot is not None:
            value = reconstruct_pnl(
                record.direction,
                next((item.entry_spot for item in record.observations if item.entry_spot is not None), None),
                current_spot,
                record.stake,
                record.multiplier,
            )
            if value is not None and record.buy_price is not None:
                value = max(value, -record.buy_price)
            buy_hold_values.append(value)
    return {
        "d107_current_marked_net": _metric(actual_values),
        "close_at_boundary_counterfactual": _metric(boundary_close_values),
        "buy_and_hold_to_current_counterfactual": _metric(buy_hold_values),
        "current_spot_used": current_spot,
        "warning": "Counterfactuals are not causal and do not account for path-dependent stopout execution unless explicitly observed.",
    }


def bankroll_scenarios(
    target_daily_withdrawal: float = DEFAULT_TARGET_WITHDRAWAL,
    deployed_pct: float = DEFAULT_DEPLOYED_PCT,
    *,
    rates: Sequence[float] = (0.0025, 0.005, 0.01, 0.02, 0.05, 0.10, 0.20),
    periods_days: Sequence[int] = (1, 7, 30, 90, 365),
) -> dict[str, Any]:
    rows = []
    for rate in rates:
        rows.append({
            "net_daily_return_on_total_bankroll": rate,
            "required_bankroll": target_daily_withdrawal / rate,
            "required_deployed_capital_if_return_is_on_deployed_capital": target_daily_withdrawal / rate,
            "required_bankroll_at_deployed_pct": target_daily_withdrawal / (rate * deployed_pct),
        })
    return {
        "target_daily_withdrawal": target_daily_withdrawal,
        "deployed_pct": deployed_pct,
        "cumulative_withdrawal_by_period": {
            str(days): target_daily_withdrawal * days for days in periods_days
        },
        "scenarios": rows,
        "formula_total_bankroll_return": "bankroll = daily_withdrawal / net_daily_return",
        "formula_deployed_return": "bankroll = daily_withdrawal / (deployed_return * deployed_pct)",
        "warning": "These are arithmetic scenarios, not forecasts or guarantees of return.",
    }


def capacity_scenario(
    target_daily_withdrawal: float = DEFAULT_TARGET_WITHDRAWAL,
    max_positions: int = DEFAULT_MAX_POSITIONS,
    stake: float = DEFAULT_STAKE,
    multiplier: int = DEFAULT_MULTIPLIER,
    cancellation_fee: float = DEFAULT_CANCELLATION_FEE,
) -> dict[str, Any]:
    max_deployed = max_positions * (stake + cancellation_fee)
    favorable_move = target_daily_withdrawal / (max_positions * stake * multiplier)
    return {
        "max_positions": max_positions,
        "stake": stake,
        "multiplier": multiplier,
        "estimated_max_deployed_at_buy": max_deployed,
        "all_positions_same_direction_move_required_for_target": favorable_move,
        "warning": "This assumes every position moves favorably together and ignores losses, fees, stopouts, and turnover; it is only a capacity illustration.",
    }


def throughput_summary(ledger: Mapping[str, ContractRecord], now: Optional[float] = None) -> dict[str, Any]:
    entries = [record.entry_time for record in ledger.values() if record.entry_time is not None]
    if not entries:
        return {"confirmed_buys": 0, "buy_rate_per_hour": None, "coverage_hours": 0.0}
    first = min(entries)
    last = max(entries)
    coverage = max(0.0, (last - first) / 3600)
    rate = len(entries) / coverage if coverage > 0 else None
    result = {
        "confirmed_buys": len(entries),
        "first_buy": iso_timestamp(first),
        "last_buy": iso_timestamp(last),
        "coverage_hours": coverage,
        "buy_rate_per_hour": rate,
        "capacity_adjusted": False,
        "warning": "Observed buy rate is not a sustainable forecast because the 10-position cap and five-minute windows create pauses.",
    }
    if rate:
        for target in (100, 200, 300, 500):
            missing = max(0, target - len(entries))
            result[f"hours_to_{target}_at_observed_rate"] = missing / rate
    return result


def build_sell_waves(
    events: Sequence[Mapping[str, Any]],
    ledger: Mapping[str, ContractRecord],
    gap_seconds: int = 120,
) -> list[dict[str, Any]]:
    sells = []
    for event in events:
        if event.get("action") != "sold_winner_target":
            continue
        timestamp = parse_timestamp(event.get("timestamp"))
        if timestamp is None:
            continue
        record = ledger.get(str(event.get("contract_id")))
        sells.append({
            "timestamp": timestamp,
            "contract_id": str(event.get("contract_id")),
            "direction": event.get("direction") or (record.direction if record else None),
            "realized_pnl": finite_float(event.get("realized_pnl")) or 0.0,
            "multiple": (
                finite_float(event.get("sold_for")) / finite_float(event.get("buy_price"))
                if finite_float(event.get("sold_for")) and finite_float(event.get("buy_price"))
                else None
            ),
            "hold_seconds": (
                timestamp - record.entry_time
                if record and record.entry_time is not None else None
            ),
        })
    sells.sort(key=lambda item: item["timestamp"])
    waves: list[list[dict[str, Any]]] = []
    for sell in sells:
        if not waves or sell["timestamp"] - waves[-1][-1]["timestamp"] > gap_seconds:
            waves.append([sell])
        else:
            waves[-1].append(sell)
    output = []
    for index, wave in enumerate(waves, 1):
        holds = [item["hold_seconds"] for item in wave if item["hold_seconds"] is not None]
        output.append({
            "wave": index,
            "start": iso_timestamp(wave[0]["timestamp"]),
            "end": iso_timestamp(wave[-1]["timestamp"]),
            "count": len(wave),
            "realized_pnl": sum(item["realized_pnl"] for item in wave),
            "directions": dict(Counter(item["direction"] for item in wave)),
            "mean_hold_seconds": statistics.fmean(holds) if holds else None,
            "min_multiple": min((item["multiple"] for item in wave if item["multiple"] is not None), default=None),
            "max_multiple": max((item["multiple"] for item in wave if item["multiple"] is not None), default=None),
            "contracts": [item["contract_id"] for item in wave],
        })
    return output


def validation_gates(
    ledger: Mapping[str, ContractRecord],
    state: Mapping[str, Any],
    horizons: Mapping[str, Mapping[str, Any]],
    regimes: Mapping[str, Any],
    *,
    min_operational_buys: int = DEFAULT_MIN_OPERATIONAL_BUYS,
    min_economic_buys: int = DEFAULT_MIN_ECONOMIC_BUYS,
    min_regimes: int = DEFAULT_MIN_REGIMES,
) -> dict[str, Any]:
    strategy_records = [record for record in ledger.values() if not is_manual_external(record)]
    buys = len(ledger)
    strategy_buys = len(strategy_records)
    terminal = sum(record.terminal for record in strategy_records)
    active_unresolved = len(state.get("unresolved_contracts") or [])
    operational = {
        "status": "PASS" if buys >= min_operational_buys and active_unresolved == 0 else "IN_PROGRESS",
        "confirmed_buys": buys,
        "strategy_contracts_excluding_manual_external": strategy_buys,
        "required_buys": min_operational_buys,
        "terminal_outcomes": terminal,
        "active_unresolved": active_unresolved,
        "criteria": "minimum buys reached and current state has zero unresolved contracts",
    }
    economic_samples = {
        name: int(values.get("n", 0)) for name, values in horizons.items()
    }
    required_horizon_samples = {
        "1h": min_economic_buys,
        "6h": max(1, min_economic_buys // 2),
        "24h": max(1, min_economic_buys // 4),
    }
    enough_horizons = all(
        economic_samples.get(name, 0) >= required
        for name, required in required_horizon_samples.items()
    )
    economic = {
        "status": "IN_PROGRESS",
        "confirmed_buys": buys,
        "strategy_contracts_excluding_manual_external": strategy_buys,
        "required_buys": min_economic_buys,
        "terminal_outcomes": terminal,
        "horizon_samples": economic_samples,
        "required_horizon_samples": required_horizon_samples,
        "distinct_regimes": regimes.get("distinct_regimes", 0),
        "required_regimes": min_regimes,
        "criteria": "positive net expectancy with confidence bounds across fixed horizons and multiple regimes",
    }
    one_hour = horizons.get("1h", {})
    ci = one_hour.get("ci95", [None, None])
    if (
        buys >= min_economic_buys
        and terminal >= min_economic_buys // 2
        and enough_horizons
        and regimes.get("distinct_regimes", 0) >= min_regimes
        and ci[0] is not None
        and ci[0] > 0
    ):
        economic["status"] = "PASS"
    return {
        "operational": operational,
        "economic": economic,
        "wealth_question": {
            "status": "NOT_ASSESSABLE" if economic["status"] != "PASS" else "SCENARIO_ONLY",
            "answer": "Current Demo data cannot establish whether this creates wealth; bankroll scenarios require a validated net return first.",
        },
    }


def build_report(
    events: Sequence[Mapping[str, Any]],
    state: Optional[Mapping[str, Any]] = None,
    *,
    now: Optional[float] = None,
    horizons_hours: Sequence[int] = DEFAULT_HORIZONS_HOURS,
    target_daily_withdrawal: float = DEFAULT_TARGET_WITHDRAWAL,
    min_operational_buys: int = DEFAULT_MIN_OPERATIONAL_BUYS,
    min_economic_buys: int = DEFAULT_MIN_ECONOMIC_BUYS,
    min_regimes: int = DEFAULT_MIN_REGIMES,
) -> dict[str, Any]:
    state = state or {}
    ledger = build_ledger(events, state)
    horizon_results: dict[str, list[dict[str, Any]]] = {}
    horizon_metrics: dict[str, dict[str, Any]] = {}
    for hours in horizons_hours:
        results = [horizon_value(record, hours) for record in ledger.values()]
        horizon_results[f"{hours}h"] = results
        horizon_metrics[f"{hours}h"] = _metric([result.get("value") for result in results])
        horizon_metrics[f"{hours}h"]["statuses"] = dict(Counter(result.get("status") for result in results))
    spot = current_spot_from_ledger(ledger)
    regimes = regime_summary(ledger)
    sell_waves = build_sell_waves(events, ledger)
    manual_external_records = [record for record in ledger.values() if is_manual_external(record)]
    strategy_records = [record for record in ledger.values() if not is_manual_external(record)]
    report = {
        "generated_at": iso_timestamp(now or datetime.now(timezone.utc).timestamp()),
        "hypothesis": "D107",
        "account_type": "demo",
        "contract_count": len(ledger),
        "action_counts": dict(Counter(str(event.get("action")) for event in events)),
        "lifecycle_counts": dict(Counter(record.lifecycle for record in ledger.values())),
        "current_state": {
            key: state.get(key)
            for key in (
                "confirmed_buys",
                "new_buys_enabled",
                "stop_reason",
                "unresolved_contracts",
                "session_realized_pnl",
                "cancellation_fees",
                "deployed_capital",
            )
        },
        "manual_external_closes": {
            "count": len(manual_external_records),
            "pnl_excluded_from_strategy": sum(
                record.external_close_pnl or 0.0 for record in manual_external_records
            ),
            "positive": sum((record.external_close_pnl or 0.0) > 0 for record in manual_external_records),
            "negative": sum((record.external_close_pnl or 0.0) < 0 for record in manual_external_records),
            "classification": "manual_external_close_by_operator_instruction",
        },
        "current_metrics": _metric([strategy_net_value(record) for record in ledger.values()]),
        "realized_contract_net": _metric([
            record.terminal_net_pnl for record in strategy_records if record.terminal_net_pnl is not None
        ]),
        "open_unrealized": _metric([
            record.latest_observation.pnl
            for record in ledger.values()
            if not record.terminal and record.latest_observation is not None
        ]),
        "cancellation_fee_quotes_total": sum(record.cancellation_fee for record in ledger.values()),
        "cancellation_fees_on_cancel_actions": sum(
            record.cancellation_fee
            for record in ledger.values()
            if record.boundary_action == "cancelled_loser"
        ),
        "state_cancellation_fees": finite_float(state.get("cancellation_fees")),
        "max_adverse_pnl": _metric([record.maximum_adverse_pnl for record in ledger.values()]),
        "peak_pnl": _metric([record.peak_pnl for record in ledger.values()]),
        "by_direction": {
            direction: {
                "buys": sum(record.direction == direction for record in strategy_records),
                "terminal": sum(record.direction == direction and record.terminal for record in strategy_records),
                "current_net": _metric([
                    strategy_net_value(record) for record in strategy_records if record.direction == direction
                ]),
            }
            for direction in ("MULTUP", "MULTDOWN")
        },
        "horizons": horizon_metrics,
        "horizon_contract_results": {
            key: {
                record.contract_id: result
                for record, result in zip(ledger.values(), results)
            }
            for key, results in horizon_results.items()
        },
        "benchmarks": benchmark_summary(ledger, spot),
        "sell_waves": {
            "count": len(sell_waves),
            "total_sells": sum(wave["count"] for wave in sell_waves),
            "total_realized_pnl": sum(wave["realized_pnl"] for wave in sell_waves),
            "waves": sell_waves,
            "unit_of_analysis": "wave",
            "gap_seconds": 120,
        },
        "regimes": regimes,
        "throughput": throughput_summary(ledger, now=now),
        "bankroll_scenarios": bankroll_scenarios(target_daily_withdrawal),
        "fixed_v0_capacity": capacity_scenario(target_daily_withdrawal),
    }
    report["validation_gates"] = validation_gates(
        ledger,
        state,
        horizon_metrics,
        regimes,
        min_operational_buys=min_operational_buys,
        min_economic_buys=min_economic_buys,
        min_regimes=min_regimes,
    )
    report["observation_window"] = {
        "minimum_for_24h_horizon_hours": 24,
        "minimum_for_three_24h_regimes_hours": 72,
        "stronger_demo_observation_window_hours": 336,
        "explanation": "A concrete economic answer needs fixed-horizon outcomes plus multiple market regimes; buy count alone is insufficient.",
    }
    return report


def _format_money(value: Any) -> str:
    numeric = finite_float(value)
    return "n/a" if numeric is None else f"${numeric:+.2f}"


def print_report(report: Mapping[str, Any]) -> None:
    state = report.get("current_state", {})
    gates = report.get("validation_gates", {})
    throughput = report.get("throughput", {})
    print("D107 VALIDATION REPORT")
    print("=" * 72)
    print(f"Contracts: {report.get('contract_count')} | Demo account")
    print(f"Current state: buys_enabled={state.get('new_buys_enabled')} stop={state.get('stop_reason')}")
    print(f"Realized contract net: {_format_money(report.get('realized_contract_net', {}).get('sum'))}")
    print(f"Current marked net: {_format_money(report.get('current_metrics', {}).get('sum'))}")
    print(
        "Cancellation fees: quotes_total="
        f"{_format_money(report.get('cancellation_fee_quotes_total'))} "
        "cancel_actions="
        f"{_format_money(report.get('cancellation_fees_on_cancel_actions'))}"
    )
    print(f"Observed buy rate: {throughput.get('buy_rate_per_hour') or 'n/a'} / hour")
    print()
    print("HORIZONS")
    for horizon, metrics in (report.get("horizons") or {}).items():
        print(
            f"  {horizon}: n={metrics.get('n')} mean={_format_money(metrics.get('mean'))} "
            f"CI95=[{_format_money(metrics.get('ci95', [None, None])[0])}, "
            f"{_format_money(metrics.get('ci95', [None, None])[1])}]"
        )
    print()
    print("VALIDATION GATES")
    for name, gate in gates.items():
        print(f"  {name}: {gate.get('status')}")
    print()
    print("BANKROLL SCENARIOS FOR $1,000/DAY")
    for row in report.get("bankroll_scenarios", {}).get("scenarios", []):
        rate = row["net_daily_return_on_total_bankroll"] * 100
        print(
            f"  {rate:g}% net/day: bankroll=${row['required_bankroll']:,.0f} "
            f"or ${row['required_bankroll_at_deployed_pct']:,.0f} if return is measured on deployed capital"
        )
    print()
    print("DECISION")
    print(f"  {gates.get('wealth_question', {}).get('status')}: {gates.get('wealth_question', {}).get('answer')}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results-file", default="d107_rate_limit_winner_holding_results.jsonl")
    parser.add_argument("--state-file", default="d107_rate_limit_winner_holding_state.json")
    parser.add_argument("--json-out", default=None)
    parser.add_argument("--target-daily-withdrawal", type=float, default=DEFAULT_TARGET_WITHDRAWAL)
    parser.add_argument("--min-operational-buys", type=int, default=DEFAULT_MIN_OPERATIONAL_BUYS)
    parser.add_argument("--min-economic-buys", type=int, default=DEFAULT_MIN_ECONOMIC_BUYS)
    parser.add_argument("--min-regimes", type=int, default=DEFAULT_MIN_REGIMES)
    args = parser.parse_args()
    events = load_jsonl(args.results_file)
    state = load_state(args.state_file)
    report = build_report(
        events,
        state,
        target_daily_withdrawal=args.target_daily_withdrawal,
        min_operational_buys=args.min_operational_buys,
        min_economic_buys=args.min_economic_buys,
        min_regimes=args.min_regimes,
    )
    print_report(report)
    if args.json_out:
        with open(args.json_out, "w", encoding="utf-8") as handle:
            json.dump(report, handle, ensure_ascii=False, indent=2, allow_nan=False)
            handle.write("\n")


if __name__ == "__main__":
    main()
