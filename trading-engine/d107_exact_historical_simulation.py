#!/usr/bin/env python3
"""Deterministic D107 market-path simulation using real Deriv ticks.

This script is read-only with respect to Deriv: it requests ticks and proposal
quotes only, never buys or sells. Demo and Real profiles use the same
DERIV_APP_ID/DERIV_API_TOKEN with DerivClient(use_demo=True/False).
"""
from __future__ import annotations

import argparse
import asyncio
import gzip
import json
import math
import os
import statistics
import time
from bisect import bisect_left
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

from dotenv import load_dotenv

from deriv_client import DerivClient
from d107_rate_limit_winner_holding import calculate_adx_and_trend

load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))

SYMBOL = "1HZ10V"
DIRECTIONS = ("MULTUP", "MULTDOWN")
MULTIPLIER = 400
CANCELLATION_SECONDS = 300
ENTRY_INTERVAL_SECONDS = 15
MAX_POSITIONS = 10
STAKE_LEVELS = (1.0, 10.0)
BANKROLLS = (10.40, 52.0, 104.0)
CAPITAL_POLICIES = ("all_in", "20pct")
EXIT_SCENARIOS = (
    ("hold", None),
    ("sell_boundary", None),
    ("sell_target", 0.10),
    ("sell_target", 0.25),
    ("sell_target", 0.50),
    ("trailing_50", None),
    ("micro_scalp_baseline", 0.25),
    ("perpetual_ladder_1x_8x", 8.0),
)


def finite(value: Any) -> Optional[float]:
    if value is None or isinstance(value, bool):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def iso(epoch: float) -> str:
    return datetime.fromtimestamp(epoch, timezone.utc).isoformat(timespec="seconds")


def directional_gross(direction: str, entry: float, current: float, stake: float, multiplier: int = MULTIPLIER) -> float:
    move = (current - entry) / entry
    return move * stake * multiplier if direction == "MULTUP" else -move * stake * multiplier


@dataclass(frozen=True)
class Quote:
    profile: str
    direction: str
    stake: float
    ask_price: float
    cancellation_fee: float
    commission: float
    spot: Optional[float]
    raw_fields: tuple[str, ...]


@dataclass
class Position:
    position_id: int
    entry_index: int
    entry_time: int
    entry_price: float
    direction: str
    stake: float
    cost: float
    cancellation_fee: float
    commission: float
    multiplier: int = MULTIPLIER
    boundary_index: Optional[int] = None
    boundary_time: Optional[int] = None
    boundary_price: Optional[float] = None
    boundary_mark: Optional[float] = None
    status: str = "open"
    terminal_time: Optional[int] = None
    terminal_net: Optional[float] = None
    peak_net: float = 0.0
    held_peak_net: float = 0.0
    adverse_min: float = 0.0
    observations: int = 0

    def mark(self, price: float) -> float:
        return directional_gross(self.direction, self.entry_price, price, self.stake, self.multiplier) - self.commission


@dataclass
class SimulationResult:
    profile: str
    stake: float
    bankroll: float
    capital_policy: str
    exit_policy: str = "hold"
    target_multiple: Optional[float] = None
    manual_sell_cooldown_seconds: int = 0
    manual_sells: int = 0
    buys: int = 0
    cancellations: int = 0
    held_winners: int = 0
    stopouts: int = 0
    unresolved: int = 0
    cancellation_fees: float = 0.0
    realized_net: float = 0.0
    current_unrealized: float = 0.0
    peak_equity: float = 0.0
    trough_equity: float = 0.0
    final_equity: float = 0.0
    max_drawdown: float = 0.0
    positions: list[dict[str, Any]] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        final_balance = self.bankroll + self.final_equity
        runners_1x = sum(1 for p in self.positions if (p.get("peak_net") or 0.0) >= 1.0 * self.stake)
        runners_2x = sum(1 for p in self.positions if (p.get("peak_net") or 0.0) >= 2.0 * self.stake)
        runners_4x = sum(1 for p in self.positions if (p.get("peak_net") or 0.0) >= 4.0 * self.stake)
        runners_8x = sum(1 for p in self.positions if (p.get("peak_net") or 0.0) >= 8.0 * self.stake)
        expected_net_per_trade = self.realized_net / self.buys if self.buys > 0 else 0.0
        gains = sum(p["terminal_net"] for p in self.positions if (p.get("terminal_net") or 0.0) > 0)
        losses = sum(abs(p["terminal_net"]) for p in self.positions if (p.get("terminal_net") or 0.0) < 0)
        profit_factor = gains / losses if losses > 0 else (float("inf") if gains > 0 else 0.0)
        return {
            "profile": self.profile,
            "stake": self.stake,
            "bankroll": self.bankroll,
            "capital_policy": self.capital_policy,
            "exit_policy": self.exit_policy,
            "target_multiple": self.target_multiple,
            "manual_sell_cooldown_seconds": self.manual_sell_cooldown_seconds,
            "manual_sells": self.manual_sells,
            "buys": self.buys,
            "cancellations": self.cancellations,
            "held_winners": self.held_winners,
            "stopouts": self.stopouts,
            "unresolved": self.unresolved,
            "cancellation_fees": self.cancellation_fees,
            "realized_net": self.realized_net,
            "current_unrealized": self.current_unrealized,
            "peak_equity": self.peak_equity,
            "trough_equity": self.trough_equity,
            "final_equity": self.final_equity,
            "final_balance": final_balance,
            "marked_return_pct": self.final_equity / self.bankroll * 100 if self.bankroll else None,
            "max_drawdown": self.max_drawdown,
            "max_drawdown_pct_of_initial": self.max_drawdown / self.bankroll * 100 if self.bankroll else None,
            "expected_net_per_trade": expected_net_per_trade,
            "profit_factor": profit_factor,
            "runners_1x": runners_1x,
            "runners_2x": runners_2x,
            "runners_4x": runners_4x,
            "runners_8x": runners_8x,
            "positions": self.positions,
        }


SimulationResults = SimulationResult


def _history_payload(symbol: str, end: int) -> dict[str, Any]:
    return {
        "ticks_history": symbol,
        "count": 1000,
        "end": end,
        "start": 1,
        "style": "ticks",
    }


async def fetch_ticks(use_demo: bool, start: int, end: int, *, delay: float = 0.12) -> dict[str, Any]:
    app_id = os.getenv("DERIV_APP_ID")
    token = os.getenv("DERIV_API_TOKEN")
    if not app_id or not token:
        raise RuntimeError("DERIV_APP_ID and DERIV_API_TOKEN must be configured")
    profile = "demo" if use_demo else "real"
    client = DerivClient(app_id=app_id, api_token=token, use_demo=use_demo)
    await client.connect()
    pages = 0
    pairs: list[tuple[int, float]] = []
    cursor = end
    try:
        while cursor >= start:
            response = await client.send_request(_history_payload(SYMBOL, cursor))
            if "error" in response:
                raise RuntimeError(f"{profile} ticks_history error: {response['error'].get('message')}")
            history = response.get("history", {})
            times = history.get("times", []) if isinstance(history, dict) else []
            prices = history.get("prices", []) if isinstance(history, dict) else []
            if not times or not prices:
                break
            page = [
                (int(t), float(p))
                for t, p in zip(times, prices)
                if start <= int(t) <= end and finite(p) is not None
            ]
            pairs.extend(page)
            pages += 1
            oldest = min(int(t) for t in times)
            if oldest >= cursor:
                break
            cursor = oldest - 1
            if delay:
                await asyncio.sleep(delay)
    finally:
        await client.disconnect()
    dedup = dict(pairs)
    ordered = sorted(dedup.items())
    times = [item[0] for item in ordered]
    prices = [item[1] for item in ordered]
    intervals = [b - a for a, b in zip(times, times[1:]) if b > a]
    return {
        "profile": profile,
        "metadata": {
            "symbol": SYMBOL,
            "start": times[0] if times else start,
            "end": times[-1] if times else end,
            "start_iso": iso(times[0]) if times else iso(start),
            "end_iso": iso(times[-1]) if times else iso(end),
            "count": len(times),
            "coverage_seconds": times[-1] - times[0] if times else 0,
            "median_interval_seconds": statistics.median(intervals) if intervals else None,
            "max_gap_seconds": max(intervals) if intervals else None,
            "requests": pages,
        },
        "times": times,
        "prices": prices,
    }


async def fetch_quotes(use_demo: bool) -> dict[str, Any]:
    app_id = os.getenv("DERIV_APP_ID")
    token = os.getenv("DERIV_API_TOKEN")
    if not app_id or not token:
        raise RuntimeError("DERIV_APP_ID and DERIV_API_TOKEN must be configured")
    profile = "demo" if use_demo else "real"
    client = DerivClient(app_id=app_id, api_token=token, use_demo=use_demo)
    await client.connect()
    quotes: dict[str, dict[str, Any]] = {}
    try:
        for stake in STAKE_LEVELS:
            for direction in DIRECTIONS:
                response = await client.send_request({
                    "proposal": 1,
                    "amount": stake,
                    "basis": "stake",
                    "contract_type": direction,
                    "currency": "USD",
                    "underlying_symbol": SYMBOL,
                    "multiplier": MULTIPLIER,
                    "cancellation": "5m",
                })
                key = f"{stake}:{direction}"
                if "error" in response:
                    quotes[key] = {"error": response["error"].get("message")}
                    continue
                proposal = response.get("proposal", {})
                cancellation = proposal.get("cancellation", {})
                quotes[key] = {
                    "profile": profile,
                    "direction": direction,
                    "stake": stake,
                    "ask_price": finite(proposal.get("ask_price")),
                    "cancellation_fee": finite(cancellation.get("ask_price")),
                    "commission": finite(proposal.get("commission")) or 0.0,
                    "spot": finite(proposal.get("spot")),
                    "date_start": proposal.get("date_start"),
                    "cancellation_expiry": cancellation.get("date_expiry"),
                    "raw_fields": sorted(proposal.keys()),
                }
    finally:
        await client.disconnect()
    return {"profile": profile, "account_verified": bool(client.account_id), "quotes": quotes}


def price_index(times: list[int], timestamp: int) -> Optional[int]:
    index = bisect_left(times, timestamp)
    return index if index < len(times) else None


def simulate(
    profile: str,
    times: list[int],
    prices: list[float],
    quote_map: dict[str, Any],
    stake: float,
    bankroll: float,
    capital_policy: str,
    exit_policy: str = "hold",
    target_multiple: Optional[float] = None,
    manual_sell_cooldown_seconds: int = 0,
    trend_alignment_enabled: bool = False,
    multiplier: int = MULTIPLIER,
) -> SimulationResult:
    result = SimulationResult(
        profile,
        stake,
        bankroll,
        capital_policy,
        exit_policy,
        target_multiple,
        manual_sell_cooldown_seconds,
    )
    if not times:
        return result
    cash = bankroll
    open_positions: list[Position] = []
    next_entry_time = times[0]
    direction_index = 0
    position_id = 0
    equity_peak = bankroll
    equity_trough = bankroll
    quote_by_direction = {
        direction: quote_map.get(f"{stake}:{direction}", {}) for direction in DIRECTIONS
    }
    target = (target_multiple or 0.0) * stake
    next_manual_sell_at = -math.inf

    def close_manual(position: Position, timestamp: int, price: float, mark: float, status: str) -> bool:
        nonlocal next_manual_sell_at
        if timestamp < next_manual_sell_at:
            return False
        next_manual_sell_at = timestamp + manual_sell_cooldown_seconds
        nonlocal cash
        net_pnl = mark - position.cancellation_fee
        position.status = status
        position.terminal_time = timestamp
        position.terminal_net = net_pnl
        cash += position.stake + mark
        result.cancellation_fees += position.cancellation_fee
        result.realized_net += net_pnl
        result.manual_sells += 1
        result.positions.append(_position_record(position, price))
        return True

    for index, (timestamp, price) in enumerate(zip(times, prices)):
        survivors: list[Position] = []
        for position in open_positions:
            mark = position.mark(price)
            position.peak_net = max(position.peak_net, mark)
            position.adverse_min = min(position.adverse_min, mark)
            position.observations += 1
            if position.status == "held_winner":
                position.held_peak_net = max(getattr(position, "held_peak_net", 0.0), mark)

            if mark <= -position.stake:
                position.status = "stopout"
                position.terminal_time = timestamp
                position.terminal_net = -position.cost
                result.stopouts += 1
                result.cancellation_fees += position.cancellation_fee
                result.realized_net += position.terminal_net
                result.positions.append(_position_record(position, price))
                continue

            # PRE-BOUNDARY (intra-window):
            if position.boundary_index is None and timestamp < position.entry_time + CANCELLATION_SECONDS:
                if exit_policy == "micro_scalp_baseline":
                    scalp_target = (target_multiple or 0.25) * position.stake
                    if mark >= scalp_target:
                        if close_manual(position, timestamp, price, mark, "sold_winner_micro_scalp"):
                            continue

            # BOUNDARY QUALIFICATION (at 5m / 300s):
            if position.boundary_index is None and timestamp >= position.entry_time + CANCELLATION_SECONDS:
                position.boundary_index = index
                position.boundary_time = timestamp
                position.boundary_price = price
                position.boundary_mark = mark
                if exit_policy == "perpetual_ladder_1x_8x":
                    net_profit = mark - position.cancellation_fee
                    trend_ok = True
                    if trend_alignment_enabled and index >= 30:
                        sig = calculate_adx_and_trend(prices[max(0, index - 180):index + 1])
                        if sig.is_aligned and sig.direction in DIRECTIONS and sig.direction != position.direction:
                            trend_ok = False
                    if net_profit < position.cancellation_fee or not trend_ok:
                        position.status = "cancelled_loser"
                        position.terminal_time = timestamp
                        position.terminal_net = -position.cancellation_fee
                        result.cancellations += 1
                        result.cancellation_fees += position.cancellation_fee
                        result.realized_net += position.terminal_net
                        cash += position.stake
                        result.positions.append(_position_record(position, price))
                        continue
                    else:
                        position.status = "held_winner"
                        position.held_peak_net = mark
                        result.held_winners += 1
                else:
                    if mark < 0:
                        position.status = "cancelled_loser"
                        position.terminal_time = timestamp
                        position.terminal_net = -position.cancellation_fee
                        result.cancellations += 1
                        result.cancellation_fees += position.cancellation_fee
                        result.realized_net += position.terminal_net
                        cash += position.stake
                        result.positions.append(_position_record(position, price))
                        continue
                    if mark > 0:
                        position.status = "held_winner"
                        position.held_peak_net = mark
                        result.held_winners += 1
                        if exit_policy in {"sell_boundary", "sell_first_positive", "micro_scalp_baseline"}:
                            if close_manual(position, timestamp, price, mark, "sold_winner_boundary"):
                                continue
                        if exit_policy.startswith("sell_target") and mark >= target:
                            if close_manual(position, timestamp, price, mark, "sold_winner_target"):
                                continue
                    else:
                        position.status = "unresolved"
                        result.unresolved += 1
                        result.positions.append(_position_record(position, price))
                        continue

            # POST-BOUNDARY HELD_WINNER EVALUATION:
            if position.status == "held_winner":
                if exit_policy == "perpetual_ladder_1x_8x":
                    position.held_peak_net = max(getattr(position, "held_peak_net", 0.0), mark)
                    # 1. Capital preservation floor at -0.35 * stake
                    if mark <= -0.35 * position.stake:
                        if close_manual(position, timestamp, price, mark, "sold_winner_capital_preservation"):
                            continue
                    # 2. Target TP at 8.0x
                    tp_target = (target_multiple or 8.0) * position.stake
                    if mark >= tp_target - 1e-9:
                        if close_manual(position, timestamp, price, mark, "sold_winner_target"):
                            continue
                    # 3. 4-Tier Progressive Perpetual Ratchet
                    peak = position.held_peak_net
                    if peak >= tp_target:
                        floor = max(2.50 * position.stake, peak * 0.80)
                    elif peak >= 4.0 * position.stake:
                        floor = 2.50 * position.stake
                    elif peak >= 2.0 * position.stake:
                        floor = 1.00 * position.stake
                    elif peak >= 1.0 * position.stake:
                        floor = 0.20 * position.stake
                    else:
                        floor = -float("inf")
                    if floor > -float("inf") and mark <= floor:
                        if close_manual(position, timestamp, price, mark, "sold_winner_trailing"):
                            continue
                elif exit_policy == "sell_first_positive" and mark > 0:
                    if close_manual(position, timestamp, price, mark, "sold_winner_positive"):
                        continue
                elif exit_policy.startswith("sell_target") and mark >= target:
                    if close_manual(position, timestamp, price, mark, "sold_winner_target"):
                        continue
                elif exit_policy == "trailing_50" and position.peak_net > 0 and mark <= position.peak_net * 0.5:
                    if close_manual(position, timestamp, price, mark, "sold_winner_trailing"):
                        continue
            survivors.append(position)

        open_positions = survivors
        if timestamp >= next_entry_time and len(open_positions) < MAX_POSITIONS:
            direction = None
            if trend_alignment_enabled and index >= 30:
                sig = calculate_adx_and_trend(prices[max(0, index - 180):index + 1])
                if sig.is_aligned and sig.direction in DIRECTIONS:
                    direction = sig.direction
                elif exit_policy == "perpetual_ladder_1x_8x":
                    next_entry_time = timestamp + ENTRY_INTERVAL_SECONDS
                    direction = None

            if direction is None and exit_policy != "perpetual_ladder_1x_8x":
                direction = DIRECTIONS[direction_index % len(DIRECTIONS)]
            elif direction is None and not trend_alignment_enabled:
                direction = DIRECTIONS[direction_index % len(DIRECTIONS)]

            if direction in DIRECTIONS:
                quote = quote_by_direction[direction]
                cost = finite(quote.get("ask_price"))
                fee = finite(quote.get("cancellation_fee"))
                commission = finite(quote.get("commission")) or 0.0
                if cost is not None and fee is not None:
                    deployed = sum(item.cost for item in open_positions)
                    capital_ok = cash >= cost - 1e-9
                    if capital_policy == "20pct":
                        capital_ok = deployed + cost <= bankroll * 0.20 + 1e-9
                    if capital_ok:
                        cash -= cost
                        open_positions.append(Position(
                            position_id=position_id,
                            entry_index=index,
                            entry_time=timestamp,
                            entry_price=price,
                            direction=direction,
                            stake=stake,
                            cost=cost,
                            cancellation_fee=fee,
                            commission=commission,
                            multiplier=multiplier,
                        ))
                        result.buys += 1
                        position_id += 1
                        if not trend_alignment_enabled:
                            direction_index += 1
            next_entry_time = timestamp + ENTRY_INTERVAL_SECONDS

        equity = cash + sum(item.stake + item.mark(price) for item in open_positions)
        equity_peak = max(equity_peak, equity)
        equity_trough = min(equity_trough, equity)
        result.max_drawdown = max(result.max_drawdown, equity_peak - equity)

    final_price = prices[-1]
    for position in open_positions:
        mark = position.mark(final_price)
        position.peak_net = max(position.peak_net, mark)
        position.adverse_min = min(position.adverse_min, mark)
        result.current_unrealized += mark - position.cancellation_fee
        result.positions.append(_position_record(position, final_price))
    result.peak_equity = equity_peak - bankroll
    result.trough_equity = equity_trough - bankroll
    result.final_equity = result.realized_net + result.current_unrealized
    return result


def _position_record(position: Position, final_price: float) -> dict[str, Any]:
    return {
        "position_id": position.position_id,
        "entry_time": position.entry_time,
        "entry_iso": iso(position.entry_time),
        "entry_price": position.entry_price,
        "direction": position.direction,
        "stake": position.stake,
        "ask_price": position.cost,
        "cancellation_fee": position.cancellation_fee,
        "boundary_time": position.boundary_time,
        "boundary_iso": iso(position.boundary_time) if position.boundary_time else None,
        "boundary_price": position.boundary_price,
        "boundary_net": position.boundary_mark,
        "status": position.status,
        "terminal_time": position.terminal_time,
        "terminal_net": position.terminal_net,
        "final_price": final_price,
        "final_mark": position.mark(final_price),
        "peak_net": position.peak_net,
        "held_peak_net": getattr(position, "held_peak_net", 0.0),
        "adverse_min": position.adverse_min,
        "observations": position.observations,
    }


def run_simulation(
    ticks: Any,
    exit_scenario: str = "perpetual_ladder_1x_8x",
    trend_alignment_enabled: bool = True,
    stake: float = 1.0,
    multiplier: int = MULTIPLIER,
    bankroll: float = 104.0,
    capital_policy: str = "all_in",
    target_multiple: Optional[float] = None,
) -> SimulationResults:
    """
    Interface contract function adhering to PROJECT.md § Architecture.
    Runs discrete-event simulation over provided tick stream.
    """
    if isinstance(ticks, (str, os.PathLike)):
        p = str(ticks)
        if p.endswith(".gz"):
            with gzip.open(p, "rt", encoding="utf-8") as h:
                raw_data = json.load(h)
        else:
            with open(p, "r", encoding="utf-8") as h:
                raw_data = json.load(h)
        ticks = raw_data

    if isinstance(ticks, dict):
        if "times" in ticks and "prices" in ticks:
            times = [int(t) for t in ticks["times"]]
            prices = [float(p) for p in ticks["prices"]]
        elif "demo" in ticks and isinstance(ticks["demo"], dict):
            times = [int(t) for t in ticks["demo"]["times"]]
            prices = [float(p) for p in ticks["demo"]["prices"]]
        else:
            raise ValueError("Unsupported dict format for ticks")
    elif isinstance(ticks, list):
        if not ticks:
            times, prices = [], []
        elif isinstance(ticks[0], dict):
            times = [int(item.get("time") or item.get("epoch") or 0) for item in ticks]
            prices = [float(item.get("price") or item.get("quote") or 0.0) for item in ticks]
        elif isinstance(ticks[0], (list, tuple)):
            times = [int(item[0]) for item in ticks]
            prices = [float(item[1]) for item in ticks]
        else:
            raise ValueError("Unsupported list format for ticks")
    else:
        raise ValueError("ticks must be a filepath, dict, or list")

    target = target_multiple
    if target is None:
        if exit_scenario == "perpetual_ladder_1x_8x":
            target = 8.0
        elif exit_scenario == "micro_scalp_baseline":
            target = 0.25

    quote_map = {
        f"{stake}:MULTUP": {
            "ask_price": round(stake * 1.04, 4),
            "cancellation_fee": round(stake * 0.04, 4),
            "commission": 0.0,
        },
        f"{stake}:MULTDOWN": {
            "ask_price": round(stake * 1.04, 4),
            "cancellation_fee": round(stake * 0.04, 4),
            "commission": 0.0,
        },
    }

    return simulate(
        profile="demo",
        times=times,
        prices=prices,
        quote_map=quote_map,
        stake=stake,
        bankroll=bankroll,
        capital_policy=capital_policy,
        exit_policy=exit_scenario,
        target_multiple=target,
        trend_alignment_enabled=trend_alignment_enabled,
        multiplier=multiplier,
    )


def integrity_report(left: dict[str, Any], right: dict[str, Any]) -> dict[str, Any]:
    left_pairs = list(zip(left["times"], left["prices"]))
    right_pairs = list(zip(right["times"], right["prices"]))
    same = left_pairs == right_pairs
    first_difference = None
    if not same:
        for index, (a, b) in enumerate(zip(left_pairs, right_pairs)):
            if a != b:
                first_difference = {"index": index, "demo": a, "real": b}
                break
        if first_difference is None and len(left_pairs) != len(right_pairs):
            first_difference = {"index": min(len(left_pairs), len(right_pairs)), "lengths": [len(left_pairs), len(right_pairs)]}
    return {
        "identical_times_and_prices": same,
        "demo_count": len(left_pairs),
        "real_count": len(right_pairs),
        "first_difference": first_difference,
        "note": "The underlying synthetic-index tick stream is market data and is expected to be shared; account-specific differences are in authenticated quotes/permissions, not a separate price path.",
    }


async def collect_and_simulate(days: int, output: str) -> dict[str, Any]:
    end = int(time.time())
    start = end - days * 86400
    demo_ticks, real_ticks, demo_quotes, real_quotes = await asyncio.gather(
        fetch_ticks(True, start, end),
        fetch_ticks(False, start, end),
        fetch_quotes(True),
        fetch_quotes(False),
    )
    simulations = []
    for profile, ticks, quotes in (("demo", demo_ticks, demo_quotes), ("real", real_ticks, real_quotes)):
        for stake in STAKE_LEVELS:
            for bankroll in BANKROLLS:
                for policy in CAPITAL_POLICIES:
                    for exit_policy, target_multiple in EXIT_SCENARIOS:
                        simulations.append(simulate(
                            profile,
                            ticks["times"],
                            ticks["prices"],
                            quotes["quotes"],
                            stake,
                            bankroll,
                            policy,
                            exit_policy=exit_policy,
                            target_multiple=target_multiple,
                        ).as_dict())
    result = {
        "generated_at": iso(int(time.time())),
        "data_window": {
            "requested_days": days,
            "requested_start": start,
            "requested_end": end,
            "requested_start_iso": iso(start),
            "requested_end_iso": iso(end),
        },
        "profiles": {
            "demo": {"account_verified": demo_quotes["account_verified"], "quotes": demo_quotes["quotes"], "ticks": demo_ticks["metadata"]},
            "real": {"account_verified": real_quotes["account_verified"], "quotes": real_quotes["quotes"], "ticks": real_ticks["metadata"]},
        },
        "tick_integrity": integrity_report(demo_ticks, real_ticks),
        "parameters": {
            "symbol": SYMBOL,
            "multiplier": MULTIPLIER,
            "cancellation_seconds": CANCELLATION_SECONDS,
            "entry_interval_seconds": ENTRY_INTERVAL_SECONDS,
            "max_positions": MAX_POSITIONS,
            "stakes": list(STAKE_LEVELS),
            "bankrolls": list(BANKROLLS),
            "capital_policies": list(CAPITAL_POLICIES),
            "exit_scenarios": [
                {"policy": policy, "target_multiple": target}
                for policy, target in EXIT_SCENARIOS
            ],
            "randomness": False,
        },
        "simulations": simulations,
        "limitations": [
            "Ticks are collected independently through Demo and Real authenticated sessions and compared; the price path is expected to be identical market data.",
            "Proposal quotes are current read-only quotes at simulation time, not historical quote snapshots; the exact historical purchase cost is unavailable from ticks_history alone.",
            "No buy, sell, cancel, or account mutation is performed by this script.",
            "Stop-out is deterministic at the multiplier loss threshold and must be interpreted as a model of the documented contract rule, not a historical execution fill.",
            "Held winners are marked at the final tick and are not realized withdrawals.",
        ],
    }
    with gzip.open(output, "wt", encoding="utf-8") as handle:
        json.dump(result, handle, ensure_ascii=False, indent=2, allow_nan=False)
        handle.write("\n")
    ticks_output = output[:-8] + ".ticks.json.gz" if output.endswith(".json.gz") else output + ".ticks.json.gz"
    with gzip.open(ticks_output, "wt", encoding="utf-8") as handle:
        json.dump(
            {
                "demo": {"times": demo_ticks["times"], "prices": demo_ticks["prices"]},
                "real": {"times": real_ticks["times"], "prices": real_ticks["prices"]},
            },
            handle,
            separators=(",", ":"),
        )
    summary_output = output[:-8] + ".summary.json" if output.endswith(".json.gz") else output + ".summary.json"
    with open(summary_output, "w", encoding="utf-8") as handle:
        json.dump(result, handle, ensure_ascii=False, indent=2, allow_nan=False)
        handle.write("\n")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--days", type=int, default=7)
    parser.add_argument("--output", default="d107_exact_historical_simulation.json.gz")
    args = parser.parse_args()
    if args.days <= 0:
        raise SystemExit("--days must be positive")
    result = asyncio.run(collect_and_simulate(args.days, args.output))
    print(json.dumps({
        "output": args.output,
        "demo_ticks": result["profiles"]["demo"]["ticks"],
        "real_ticks": result["profiles"]["real"]["ticks"],
        "tick_integrity": result["tick_integrity"],
        "quote_profiles": {
            name: {"account_verified": profile["account_verified"], "keys": sorted(profile["quotes"])}
            for name, profile in result["profiles"].items()
        },
        "simulation_count": len(result["simulations"]),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
