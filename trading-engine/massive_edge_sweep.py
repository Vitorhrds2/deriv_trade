import argparse
import asyncio
import gzip
import json
import math
import os
from collections import Counter
from decimal import Decimal
from pathlib import Path
from statistics import NormalDist

import numpy as np

from deriv_client import DerivClient


HERE = Path(__file__).resolve().parent
DEFAULT_SYMBOLS = "1HZ10V,1HZ25V,1HZ50V,1HZ75V,1HZ100V,R_10,R_25,R_50,R_75,R_100"
LOOKBACKS = (1, 2, 3, 5, 8, 13, 21, 34)
HORIZONS = (1, 2, 3, 5, 8, 13, 21)
QUANTILES = (0.0, 0.5, 0.75, 0.9, 0.95, 0.99)
CLOCK_PERIODS = (2, 3, 5, 7, 10, 16, 30, 60)
FALLBACK_GROSS = {
    "CALL": 1.923,
    "PUT": 1.923,
    "DIGITDIFF": 1.087,
    "DIGITMATCH": 8.333,
    "DIGITEVEN": 1.923,
    "DIGITODD": 1.923,
}
NORMAL = NormalDist()


def wilson(successes, n, z=1.959963984540054):
    if n <= 0:
        return 0.0, 1.0
    p = successes / n
    z2 = z * z
    denominator = 1.0 + z2 / n
    center = (p + z2 / (2.0 * n)) / denominator
    margin = z * math.sqrt((p * (1.0 - p) + z2 / (4.0 * n)) / n) / denominator
    return max(0.0, center - margin), min(1.0, center + margin)


def binomial_sf(successes, n, p0):
    if n <= 0 or successes <= 0:
        return 1.0
    if successes > n:
        return 0.0
    p0 = min(max(float(p0), 1e-12), 1.0 - 1e-12)
    if n <= 5000:
        log_term = (
            math.lgamma(n + 1)
            - math.lgamma(successes + 1)
            - math.lgamma(n - successes + 1)
            + successes * math.log(p0)
            + (n - successes) * math.log1p(-p0)
        )
        term = math.exp(log_term)
        total = term
        ratio = p0 / (1.0 - p0)
        for k in range(successes, n):
            term *= (n - k) / (k + 1) * ratio
            total += term
            if term < total * 1e-15:
                break
        return min(1.0, total)
    variance = n * p0 * (1.0 - p0)
    if variance <= 0:
        return 1.0
    z = (successes - 0.5 - n * p0) / math.sqrt(variance)
    return max(0.0, min(1.0, 1.0 - NORMAL.cdf(z)))


def split_summary(successes, n, gross):
    if n <= 0:
        return {"n": 0, "wins": 0, "wr": 0.0, "wr_lo": 0.0, "wr_hi": 1.0,
                "ev": -1.0, "ev_lo": -1.0, "ev_hi": gross - 1.0, "p": 1.0}
    low, high = wilson(successes, n)
    rate = successes / n
    return {
        "n": int(n),
        "wins": int(successes),
        "wr": rate,
        "wr_lo": low,
        "wr_hi": high,
        "ev": rate * gross - 1.0,
        "ev_lo": low * gross - 1.0,
        "ev_hi": high * gross - 1.0,
        "p": binomial_sf(successes, n, 1.0 / gross),
    }


def candidate_row(family, symbol, params, gross, quote_exact, validation, test):
    return {
        "family": family,
        "symbol": symbol,
        "params": params,
        "gross_return": float(gross),
        "quote_exact": bool(quote_exact),
        "val_n": validation["n"],
        "val_wins": validation["wins"],
        "val_wr": validation["wr"],
        "val_ev": validation["ev"],
        "val_ev_lo": validation["ev_lo"],
        "val_p": validation["p"],
        "test_n": test["n"],
        "test_wins": test["wins"],
        "test_wr": test["wr"],
        "test_ev": test["ev"],
        "test_ev_lo": test["ev_lo"],
        "test_p": test["p"],
    }


def bh_adjust(rows):
    if not rows:
        return
    order = sorted(range(len(rows)), key=lambda index: rows[index]["val_p"])
    running = 1.0
    m = len(order)
    for rank_index in range(m - 1, -1, -1):
        rank = rank_index + 1
        index = order[rank_index]
        running = min(running, rows[index]["val_p"] * m / rank)
        rows[index]["val_q"] = min(1.0, running)


def finalize(rows, min_trades, max_confirm, alpha):
    eligible = [row for row in rows if row["val_n"] >= min_trades and row["test_n"] >= min_trades]
    bh_adjust(eligible)
    selected = []
    signatures = set()
    for row in sorted(eligible, key=lambda item: (item["val_p"], -item["val_ev"])):
        signature = (
            row["family"], row["symbol"], round(row["gross_return"], 10),
            row["val_n"], row["val_wins"], row["test_n"], row["test_wins"],
        )
        if signature in signatures:
            continue
        signatures.add(signature)
        selected.append(row)
        if len(selected) >= max_confirm:
            break
    final_alpha = alpha / len(selected) if selected else 0.0
    for row in selected:
        row["final_alpha"] = final_alpha
        row["confirmed"] = bool(
            row["quote_exact"]
            and row["test_p"] <= final_alpha
            and row["test_ev_lo"] > 0.0
        )
    return eligible, selected, [row for row in selected if row["confirmed"]], final_alpha


def infer_pip(prices):
    decimals = max(
        (-Decimal(str(float(value))).as_tuple().exponent for value in prices),
        default=0,
    )
    if decimals > 0:
        return 10.0 ** (-min(decimals, 8))
    diffs = np.abs(np.diff(prices))
    diffs = diffs[diffs > 0]
    if diffs.size == 0:
        return 1.0
    smallest = float(diffs.min())
    inferred = max(0, min(8, int(round(-math.log10(smallest))))) if smallest < 1 else 0
    return 10.0 ** (-inferred)


def normalize_history(prices, epochs, limit):
    if len(prices) != len(epochs):
        raise ValueError("history prices/epochs length mismatch")
    by_epoch = {int(epoch): float(price) for price, epoch in zip(prices, epochs)}
    ordered = sorted(by_epoch.items())[-limit:]
    return (
        np.asarray([price for _, price in ordered], dtype=np.float64),
        np.asarray([epoch for epoch, _ in ordered], dtype=np.int64),
    )


def signal_indices(start, end, lookback, horizon):
    first = max(start, lookback)
    stop = end - horizon - 1
    if stop <= first:
        return np.empty(0, dtype=np.int64)
    return np.arange(first, stop, horizon + 1, dtype=np.int64)


def outcome_sign(prices, indices, horizon):
    return np.sign(prices[indices + 1 + horizon] - prices[indices + 1]).astype(np.int8)


def score_stats(prediction, outcome, mask, gross):
    valid = mask & (prediction != 0) & (outcome != 0)
    n = int(valid.sum())
    wins = int((prediction[valid] == outcome[valid]).sum()) if n else 0
    return split_summary(wins, n, gross)


def quote_value(quotes, symbol, contract_type, horizon=1):
    key = f"{symbol}:{contract_type}:{horizon}"
    quote = quotes.get(key)
    if quote:
        return float(quote["gross"]), bool(quote["exact"])
    return FALLBACK_GROSS[contract_type], False


def directional_quote(quotes, symbol, horizon):
    call, call_exact = quote_value(quotes, symbol, "CALL", horizon)
    put, put_exact = quote_value(quotes, symbol, "PUT", horizon)
    return min(call, put), call_exact and put_exact


def direction_rows(symbol, prices, quotes, label=None):
    name = label or symbol
    n = len(prices)
    train_end = int(n * 0.6)
    validation_end = int(n * 0.8)
    rows = []
    for horizon in HORIZONS:
        gross, exact = directional_quote(quotes, symbol, horizon)
        for lookback in LOOKBACKS:
            train_idx = signal_indices(0, train_end, lookback, horizon)
            val_idx = signal_indices(train_end, validation_end, lookback, horizon)
            test_idx = signal_indices(validation_end, n, lookback, horizon)
            if min(len(train_idx), len(val_idx), len(test_idx)) < 30:
                continue
            train_scores = prices[train_idx] - prices[train_idx - lookback]
            val_scores = prices[val_idx] - prices[val_idx - lookback]
            test_scores = prices[test_idx] - prices[test_idx - lookback]
            val_outcome = outcome_sign(prices, val_idx, horizon)
            test_outcome = outcome_sign(prices, test_idx, horizon)
            thresholds = sorted({float(np.quantile(np.abs(train_scores), q)) for q in QUANTILES})
            for threshold in thresholds:
                val_mask = np.abs(val_scores) >= threshold
                test_mask = np.abs(test_scores) >= threshold
                for mode, mode_name in ((1, "momentum"), (-1, "reversal")):
                    validation = score_stats(np.sign(val_scores).astype(np.int8) * mode, val_outcome, val_mask, gross)
                    test = score_stats(np.sign(test_scores).astype(np.int8) * mode, test_outcome, test_mask, gross)
                    if validation["n"] < 30 or test["n"] < 30:
                        continue
                    rows.append(candidate_row(
                        "direction", name,
                        {"mode": mode_name, "lookback": lookback, "horizon": horizon,
                         "threshold": threshold},
                        gross, exact, validation, test,
                    ))
    return rows


def streak_rows(symbol, prices, quotes, label=None):
    name = label or symbol
    n = len(prices)
    train_end = int(n * 0.6)
    validation_end = int(n * 0.8)
    returns = np.sign(np.diff(prices, prepend=prices[0])).astype(np.int8)
    rows = []
    for horizon in HORIZONS:
        gross, exact = directional_quote(quotes, symbol, horizon)
        for streak in range(2, 9):
            val_idx = signal_indices(train_end, validation_end, streak, horizon)
            test_idx = signal_indices(validation_end, n, streak, horizon)
            if min(len(val_idx), len(test_idx)) < 30:
                continue
            val_windows = np.column_stack([returns[val_idx - offset] for offset in range(streak)])
            test_windows = np.column_stack([returns[test_idx - offset] for offset in range(streak)])
            val_same = (val_windows != 0).all(axis=1) & (val_windows == val_windows[:, :1]).all(axis=1)
            test_same = (test_windows != 0).all(axis=1) & (test_windows == test_windows[:, :1]).all(axis=1)
            val_outcome = outcome_sign(prices, val_idx, horizon)
            test_outcome = outcome_sign(prices, test_idx, horizon)
            for mode, mode_name in ((1, "continue"), (-1, "reverse")):
                validation = score_stats(returns[val_idx] * mode, val_outcome, val_same, gross)
                test = score_stats(returns[test_idx] * mode, test_outcome, test_same, gross)
                if validation["n"] < 30 or test["n"] < 30:
                    continue
                rows.append(candidate_row(
                    "streak", name,
                    {"mode": mode_name, "streak": streak, "horizon": horizon},
                    gross, exact, validation, test,
                ))
    return rows


def rolling_rms(prices, window):
    returns = np.diff(prices, prepend=prices[0])
    squares = returns * returns
    cumulative = np.concatenate(([0.0], np.cumsum(squares)))
    result = np.zeros(len(prices), dtype=np.float64)
    positions = np.arange(window, len(prices) + 1)
    result[window - 1:] = np.sqrt((cumulative[positions] - cumulative[positions - window]) / window)
    return result


def volatility_rows(symbol, prices, quotes, label=None):
    name = label or symbol
    n = len(prices)
    train_end = int(n * 0.6)
    validation_end = int(n * 0.8)
    returns = np.sign(np.diff(prices, prepend=prices[0])).astype(np.int8)
    rows = []
    for window in (3, 5, 10, 20, 50):
        volatility = rolling_rms(prices, window)
        train_values = volatility[window:train_end]
        low = float(np.quantile(train_values, 0.25))
        high = float(np.quantile(train_values, 0.75))
        for horizon in HORIZONS:
            gross, exact = directional_quote(quotes, symbol, horizon)
            val_idx = signal_indices(train_end, validation_end, window, horizon)
            test_idx = signal_indices(validation_end, n, window, horizon)
            val_outcome = outcome_sign(prices, val_idx, horizon)
            test_outcome = outcome_sign(prices, test_idx, horizon)
            for regime, val_mask, test_mask in (
                ("low", volatility[val_idx] <= low, volatility[test_idx] <= low),
                ("high", volatility[val_idx] >= high, volatility[test_idx] >= high),
            ):
                for mode, mode_name in ((1, "momentum"), (-1, "reversal")):
                    validation = score_stats(returns[val_idx] * mode, val_outcome, val_mask, gross)
                    test = score_stats(returns[test_idx] * mode, test_outcome, test_mask, gross)
                    if validation["n"] < 30 or test["n"] < 30:
                        continue
                    rows.append(candidate_row(
                        "volatility", name,
                        {"regime": regime, "window": window, "mode": mode_name,
                         "horizon": horizon, "low": low, "high": high},
                        gross, exact, validation, test,
                    ))
    return rows


def clock_rows(symbol, prices, epochs, quotes, label=None):
    name = label or symbol
    n = len(prices)
    train_end = int(n * 0.6)
    validation_end = int(n * 0.8)
    rows = []
    for horizon in HORIZONS:
        gross, exact = directional_quote(quotes, symbol, horizon)
        val_idx = signal_indices(train_end, validation_end, 1, horizon)
        test_idx = signal_indices(validation_end, n, 1, horizon)
        val_outcome = outcome_sign(prices, val_idx, horizon)
        test_outcome = outcome_sign(prices, test_idx, horizon)
        for period in CLOCK_PERIODS:
            for phase in range(period):
                val_mask = epochs[val_idx] % period == phase
                test_mask = epochs[test_idx] % period == phase
                for side, side_name in ((1, "CALL"), (-1, "PUT")):
                    validation = score_stats(np.full(len(val_idx), side, dtype=np.int8), val_outcome, val_mask, gross)
                    test = score_stats(np.full(len(test_idx), side, dtype=np.int8), test_outcome, test_mask, gross)
                    if validation["n"] < 30 or test["n"] < 30:
                        continue
                    rows.append(candidate_row(
                        "clock", name,
                        {"period": period, "phase": phase, "side": side_name,
                         "horizon": horizon},
                        gross, exact, validation, test,
                    ))
    return rows


def context_codes(signs, indices, depth):
    codes = np.zeros(len(indices), dtype=np.int64)
    valid = np.ones(len(indices), dtype=bool)
    for offset in range(depth):
        values = signs[indices - offset]
        valid &= values != 0
        codes |= (values > 0).astype(np.int64) << offset
    return codes, valid


def markov_rows(symbol, prices, quotes, label=None):
    name = label or symbol
    n = len(prices)
    train_end = int(n * 0.6)
    validation_end = int(n * 0.8)
    signs = np.sign(np.diff(prices, prepend=prices[0])).astype(np.int8)
    rows = []
    for horizon in HORIZONS:
        gross, exact = directional_quote(quotes, symbol, horizon)
        for depth in range(1, 9):
            train_idx = signal_indices(0, train_end, depth, horizon)
            val_idx = signal_indices(train_end, validation_end, depth, horizon)
            test_idx = signal_indices(validation_end, n, depth, horizon)
            train_codes, train_valid = context_codes(signs, train_idx, depth)
            val_codes, val_valid = context_codes(signs, val_idx, depth)
            test_codes, test_valid = context_codes(signs, test_idx, depth)
            train_outcome = outcome_sign(prices, train_idx, horizon)
            val_outcome = outcome_sign(prices, val_idx, horizon)
            test_outcome = outcome_sign(prices, test_idx, horizon)
            train_valid &= train_outcome != 0
            size = 1 << depth
            totals = np.bincount(train_codes[train_valid], minlength=size)
            ups = np.bincount(train_codes[train_valid], weights=(train_outcome[train_valid] > 0), minlength=size)
            probabilities = np.divide(ups, totals, out=np.full(size, 0.5), where=totals > 0)
            for confidence in (0.0, 0.02, 0.05, 0.1):
                val_probability = probabilities[val_codes]
                test_probability = probabilities[test_codes]
                val_mask = val_valid & (totals[val_codes] >= 50) & (np.abs(val_probability - 0.5) >= confidence)
                test_mask = test_valid & (totals[test_codes] >= 50) & (np.abs(test_probability - 0.5) >= confidence)
                validation = score_stats(np.where(val_probability >= 0.5, 1, -1).astype(np.int8), val_outcome, val_mask, gross)
                test = score_stats(np.where(test_probability >= 0.5, 1, -1).astype(np.int8), test_outcome, test_mask, gross)
                if validation["n"] < 30 or test["n"] < 30:
                    continue
                rows.append(candidate_row(
                    "markov_direction", name,
                    {"depth": depth, "confidence": confidence, "horizon": horizon},
                    gross, exact, validation, test,
                ))
    return rows


def digit_codes(digits, indices, depth):
    codes = np.zeros(len(indices), dtype=np.int64)
    power = 1
    for offset in range(depth):
        codes += digits[indices - offset] * power
        power *= 10
    return codes


def digit_rows(symbol, prices, pip, quotes, label=None):
    name = label or symbol
    digits = np.rint(prices / pip).astype(np.int64) % 10
    n = len(digits)
    train_end = int(n * 0.6)
    validation_end = int(n * 0.8)
    rows = []
    for depth in range(1, 5):
        train_idx = np.arange(depth, train_end - 1, dtype=np.int64)
        val_idx = np.arange(max(depth, train_end), validation_end - 1, dtype=np.int64)
        test_idx = np.arange(max(depth, validation_end), n - 1, dtype=np.int64)
        train_codes = digit_codes(digits, train_idx, depth)
        val_codes = digit_codes(digits, val_idx, depth)
        test_codes = digit_codes(digits, test_idx, depth)
        size = 10 ** depth
        counts = np.zeros((size, 10), dtype=np.int64)
        np.add.at(counts, (train_codes, digits[train_idx + 1]), 1)
        totals = counts.sum(axis=1)
        probabilities = np.divide(counts, totals[:, None], out=np.full_like(counts, 0.1, dtype=np.float64), where=totals[:, None] > 0)
        least = probabilities.argmin(axis=1)
        most = probabilities.argmax(axis=1)
        even_probability = probabilities[:, (0, 2, 4, 6, 8)].sum(axis=1)
        for confidence in (0.0, 0.01, 0.02):
            for family, contract, baseline, val_action, test_action, val_probability, test_probability in (
                ("digit_diff", "DIGITDIFF", 0.1, least[val_codes], least[test_codes],
                 probabilities[val_codes, least[val_codes]], probabilities[test_codes, least[test_codes]]),
                ("digit_match", "DIGITMATCH", 0.1, most[val_codes], most[test_codes],
                 probabilities[val_codes, most[val_codes]], probabilities[test_codes, most[test_codes]]),
            ):
                gross, exact = quote_value(quotes, symbol, contract, 1)
                if family == "digit_diff":
                    val_mask = (totals[val_codes] >= 100) & (val_probability <= baseline - confidence)
                    test_mask = (totals[test_codes] >= 100) & (test_probability <= baseline - confidence)
                    val_wins = int(((digits[val_idx + 1] != val_action) & val_mask).sum())
                    test_wins = int(((digits[test_idx + 1] != test_action) & test_mask).sum())
                else:
                    val_mask = (totals[val_codes] >= 100) & (val_probability >= baseline + confidence)
                    test_mask = (totals[test_codes] >= 100) & (test_probability >= baseline + confidence)
                    val_wins = int(((digits[val_idx + 1] == val_action) & val_mask).sum())
                    test_wins = int(((digits[test_idx + 1] == test_action) & test_mask).sum())
                validation = split_summary(val_wins, int(val_mask.sum()), gross)
                test = split_summary(test_wins, int(test_mask.sum()), gross)
                if validation["n"] >= 30 and test["n"] >= 30:
                    rows.append(candidate_row(
                        family, name, {"depth": depth, "confidence": confidence},
                        gross, exact, validation, test,
                    ))
            even_gross, even_exact = quote_value(quotes, symbol, "DIGITEVEN", 1)
            odd_gross, odd_exact = quote_value(quotes, symbol, "DIGITODD", 1)
            gross = min(even_gross, odd_gross)
            val_probability = even_probability[val_codes]
            test_probability = even_probability[test_codes]
            val_action = val_probability >= 0.5
            test_action = test_probability >= 0.5
            val_mask = (totals[val_codes] >= 100) & (np.abs(val_probability - 0.5) >= confidence)
            test_mask = (totals[test_codes] >= 100) & (np.abs(test_probability - 0.5) >= confidence)
            val_even = digits[val_idx + 1] % 2 == 0
            test_even = digits[test_idx + 1] % 2 == 0
            validation = split_summary(int(((val_even == val_action) & val_mask).sum()), int(val_mask.sum()), gross)
            test = split_summary(int(((test_even == test_action) & test_mask).sum()), int(test_mask.sum()), gross)
            if validation["n"] >= 30 and test["n"] >= 30:
                rows.append(candidate_row(
                    "digit_parity", name, {"depth": depth, "confidence": confidence},
                    gross, even_exact and odd_exact, validation, test,
                ))
    return rows


def cross_symbol_rows(datasets, quotes):
    rows = []
    symbols = sorted(datasets)
    for source in symbols:
        for target in symbols:
            if source == target:
                continue
            source_data = datasets[source]
            target_data = datasets[target]
            common, source_idx, target_idx = np.intersect1d(
                source_data["epochs"], target_data["epochs"], assume_unique=False,
                return_indices=True,
            )
            if len(common) < 5000:
                continue
            source_prices = source_data["prices"][source_idx]
            target_prices = target_data["prices"][target_idx]
            n = len(common)
            train_end = int(n * 0.6)
            validation_end = int(n * 0.8)
            for horizon in (1, 2, 5):
                gross, exact = directional_quote(quotes, target, horizon)
                for lookback in (1, 3, 5, 10):
                    train_indices = signal_indices(0, train_end, lookback, horizon)
                    val_indices = signal_indices(train_end, validation_end, lookback, horizon)
                    test_indices = signal_indices(validation_end, n, lookback, horizon)
                    train_scores = source_prices[train_indices] - source_prices[train_indices - lookback]
                    val_scores = source_prices[val_indices] - source_prices[val_indices - lookback]
                    test_scores = source_prices[test_indices] - source_prices[test_indices - lookback]
                    val_outcome = outcome_sign(target_prices, val_indices, horizon)
                    test_outcome = outcome_sign(target_prices, test_indices, horizon)
                    for quantile in (0.0, 0.75, 0.9):
                        threshold = float(np.quantile(np.abs(train_scores), quantile))
                        val_mask = np.abs(val_scores) >= threshold
                        test_mask = np.abs(test_scores) >= threshold
                        for mode, mode_name in ((1, "follow"), (-1, "fade")):
                            validation = score_stats(np.sign(val_scores).astype(np.int8) * mode, val_outcome, val_mask, gross)
                            test = score_stats(np.sign(test_scores).astype(np.int8) * mode, test_outcome, test_mask, gross)
                            if validation["n"] < 30 or test["n"] < 30:
                                continue
                            rows.append(candidate_row(
                                "cross_symbol", target,
                                {"source": source, "mode": mode_name, "lookback": lookback,
                                 "horizon": horizon, "threshold": threshold},
                                gross, exact, validation, test,
                            ))
    return rows


def null_prices(prices, seed):
    rng = np.random.default_rng(seed)
    returns = np.diff(prices)
    shuffled = rng.permutation(returns)
    return np.concatenate(([prices[0]], prices[0] + np.cumsum(shuffled)))


async def safe_request(client, payload, attempts=4):
    failure = None
    for attempt in range(attempts):
        try:
            response = await asyncio.wait_for(client.send_request(dict(payload)), timeout=20)
            if "error" not in response:
                return response
            failure = response["error"].get("message", "API error")
        except Exception as error:
            failure = str(error)
        await asyncio.sleep(min(8.0, 0.5 * (2 ** attempt)))
    return {"error": {"message": failure or "request failed"}}


async def active_pips(app_id):
    client = DerivClient(app_id=app_id, api_token=None)
    await client.connect()
    try:
        response = await safe_request(client, {"active_symbols": "full"})
    finally:
        await client.disconnect()
    result = {}
    for item in response.get("active_symbols", []):
        if item.get("symbol") and item.get("pip"):
            result[item["symbol"]] = float(item["pip"])
    return result


async def fetch_symbol(symbol, ticks, app_id, pip, cache_dir, refresh, offline, request_delay, semaphore):
    cache_path = cache_dir / f"{symbol}_{ticks}.json.gz"
    prices = []
    epochs = []
    display_pip_size = None
    if cache_path.exists() and not refresh:
        with gzip.open(cache_path, "rt", encoding="utf-8") as handle:
            cached = json.load(handle)
        prices_array, epochs_array = normalize_history(cached["prices"], cached["epochs"], ticks)
        prices = prices_array.tolist()
        epochs = epochs_array.tolist()
        display_pip_size = cached.get("pip_size")
        cached_pip = 10.0 ** (-int(display_pip_size)) if display_pip_size is not None else infer_pip(prices_array)
        if len(prices) >= ticks or offline:
            return symbol, {
                "prices": prices_array,
                "epochs": epochs_array,
                "pip": cached_pip,
                "pip_size": int(display_pip_size) if display_pip_size is not None else None,
                "cache": True,
            }
    if offline:
        return symbol, {
            "prices": np.empty(0, dtype=np.float64),
            "epochs": np.empty(0, dtype=np.int64),
            "pip": float(pip or 0.01),
            "pip_size": None,
            "cache": False,
        }
    async with semaphore:
        client = DerivClient(app_id=app_id, api_token=None)
        await client.connect()
        end = int(epochs[0]) - 1 if epochs else "latest"
        try:
            while len(prices) < ticks:
                batch = min(1000, ticks - len(prices))
                response = await safe_request(client, {
                    "ticks_history": symbol,
                    "adjust_start_time": 1,
                    "count": batch,
                    "end": end,
                    "style": "ticks",
                })
                history = response.get("history", {})
                if response.get("pip_size") is not None:
                    display_pip_size = int(response["pip_size"])
                current_prices = history.get("prices", [])
                current_epochs = history.get("times", [])
                if not current_prices or not current_epochs:
                    break
                if epochs and int(current_epochs[-1]) >= int(epochs[0]):
                    break
                prices = list(current_prices) + prices
                epochs = list(current_epochs) + epochs
                end = int(current_epochs[0]) - 1
                await asyncio.sleep(request_delay)
        finally:
            await client.disconnect()
    prices_array, epochs_array = normalize_history(prices, epochs, ticks)
    actual_pip = (
        10.0 ** (-display_pip_size)
        if display_pip_size is not None
        else infer_pip(prices_array) if len(prices_array) else float(pip or 0.01)
    )
    payload = {
        "symbol": symbol,
        "pip": actual_pip,
        "pip_size": display_pip_size,
        "prices": prices_array.tolist(),
        "epochs": epochs_array.tolist(),
    }
    with gzip.open(cache_path, "wt", encoding="utf-8") as handle:
        json.dump(payload, handle, separators=(",", ":"))
    return symbol, {
        "prices": prices_array,
        "epochs": epochs_array,
        "pip": actual_pip,
        "pip_size": display_pip_size,
        "cache": False,
    }


async def fetch_quotes(symbols, app_id, request_delay):
    client = DerivClient(app_id=app_id, api_token=None)
    await client.connect()
    quotes = {}
    try:
        for symbol in symbols:
            specs = [(contract, horizon, None) for horizon in HORIZONS for contract in ("CALL", "PUT")]
            specs += [
                ("DIGITDIFF", 1, "0"),
                ("DIGITMATCH", 1, "0"),
                ("DIGITEVEN", 1, None),
                ("DIGITODD", 1, None),
            ]
            for contract, horizon, barrier in specs:
                payload = {
                    "proposal": 1,
                    "amount": 10.0,
                    "basis": "stake",
                    "contract_type": contract,
                    "currency": "USD",
                    "underlying_symbol": symbol,
                    "duration": horizon,
                    "duration_unit": "t",
                }
                if barrier is not None:
                    payload["barrier"] = barrier
                response = await safe_request(client, payload, attempts=2)
                proposal = response.get("proposal", {})
                try:
                    gross = float(proposal["payout"]) / float(proposal["ask_price"])
                    exact = gross > 1.0
                except (KeyError, TypeError, ValueError, ZeroDivisionError):
                    gross = FALLBACK_GROSS[contract]
                    exact = False
                quotes[f"{symbol}:{contract}:{horizon}"] = {
                    "gross": gross,
                    "exact": exact,
                    "error": response.get("error", {}).get("message"),
                }
                await asyncio.sleep(request_delay)
    finally:
        await client.disconnect()
    return quotes


def print_selection(selected, confirmed, final_alpha):
    print("\n" + "=" * 120)
    print(f"HOLDOUT FINAL | selecionados={len(selected)} | alpha Bonferroni={final_alpha:.6g}")
    print("=" * 120)
    for index, row in enumerate(selected, 1):
        marker = "CONFIRMADO" if row.get("confirmed") else "refutado/noise"
        print(
            f"{index:02d} {row['family']:<17} {row['symbol']:<12} "
            f"val N={row['val_n']:>6} EV={row['val_ev']:+.4f} p={row['val_p']:.3g} q={row.get('val_q', 1):.3g} | "
            f"test N={row['test_n']:>6} EV={row['test_ev']:+.4f} EVlo={row['test_ev_lo']:+.4f} "
            f"p={row['test_p']:.3g} quote={'live' if row['quote_exact'] else 'fallback'} {marker}"
        )
        print(f"    {json.dumps(row['params'], sort_keys=True)}")
    print("=" * 120)
    if confirmed:
        print(f">>> {len(confirmed)} EDGE(S) CONFIRMADO(S) NO HOLDOUT.")
    else:
        print(">>> ZERO EDGES confirmados no holdout após custos e multiple testing.")


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbols", default=DEFAULT_SYMBOLS)
    parser.add_argument("--ticks", type=int, default=50000)
    parser.add_argument("--app-id", default=os.getenv("DERIV_APP_ID") or "1089")
    parser.add_argument("--cache-dir", default=str(HERE / "data" / "d117_cache"))
    parser.add_argument("--output", default=str(HERE / "data" / "d117_massive_results.json.gz"))
    parser.add_argument("--refresh", action="store_true")
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--concurrency", type=int, default=4)
    parser.add_argument("--request-delay", type=float, default=0.04)
    parser.add_argument("--min-trades", type=int, default=200)
    parser.add_argument("--max-confirm", type=int, default=25)
    parser.add_argument("--alpha", type=float, default=0.05)
    parser.add_argument("--null-controls", type=int, default=1)
    parser.add_argument("--skip-cross", action="store_true")
    args = parser.parse_args()

    symbols = [item.strip() for item in args.symbols.split(",") if item.strip()]
    cache_dir = Path(args.cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    print(f"D117 massive sweep | symbols={len(symbols)} ticks/symbol={args.ticks:,} app_id={args.app_id}")
    pips = await active_pips(args.app_id)
    semaphore = asyncio.Semaphore(max(1, args.concurrency))
    fetched = await asyncio.gather(*[
        fetch_symbol(symbol, args.ticks, args.app_id, pips.get(symbol), cache_dir,
                     args.refresh, args.offline, args.request_delay, semaphore)
        for symbol in symbols
    ])
    datasets = {symbol: data for symbol, data in fetched if len(data["prices"]) >= 5000}
    for symbol, data in datasets.items():
        print(
            f"  {symbol:<10} ticks={len(data['prices']):>7,} pip={data['pip']:.8g} "
            f"pip_size={data.get('pip_size')} cache={data['cache']}"
        )

    quotes = await fetch_quotes(sorted(datasets), args.app_id, args.request_delay)
    exact_quotes = sum(1 for value in quotes.values() if value["exact"])
    print(f"Cotações exatas: {exact_quotes}/{len(quotes)}")

    rows = []
    for symbol, data in datasets.items():
        before = len(rows)
        prices = data["prices"]
        rows.extend(direction_rows(symbol, prices, quotes))
        rows.extend(streak_rows(symbol, prices, quotes))
        rows.extend(volatility_rows(symbol, prices, quotes))
        rows.extend(clock_rows(symbol, prices, data["epochs"], quotes))
        rows.extend(markov_rows(symbol, prices, quotes))
        rows.extend(digit_rows(symbol, prices, data["pip"], quotes))
        print(f"  grid {symbol:<10}: {len(rows) - before:,} hipóteses")
    if not args.skip_cross:
        cross = cross_symbol_rows(datasets, quotes)
        rows.extend(cross)
        print(f"  grid cross-symbol: {len(cross):,} hipóteses")

    eligible, selected, confirmed, final_alpha = finalize(
        rows, args.min_trades, args.max_confirm, args.alpha
    )
    families = Counter(row["family"] for row in rows)
    print(f"Total testado={len(rows):,} | elegível={len(eligible):,} | famílias={dict(sorted(families.items()))}")
    print_selection(selected, confirmed, final_alpha)

    null_reports = []
    for control in range(args.null_controls):
        null_rows = []
        for position, (symbol, data) in enumerate(sorted(datasets.items())):
            shuffled = null_prices(data["prices"], seed=117000 + control * 100 + position)
            label = f"NULL{control + 1}_{symbol}"
            null_rows.extend(direction_rows(symbol, shuffled, quotes, label=label))
            null_rows.extend(streak_rows(symbol, shuffled, quotes, label=label))
            null_rows.extend(volatility_rows(symbol, shuffled, quotes, label=label))
            null_rows.extend(clock_rows(symbol, shuffled, data["epochs"], quotes, label=label))
            null_rows.extend(markov_rows(symbol, shuffled, quotes, label=label))
        null_eligible, null_selected, null_confirmed, null_alpha = finalize(
            null_rows, args.min_trades, args.max_confirm, args.alpha
        )
        null_report = {
            "control": control + 1,
            "tested": len(null_rows),
            "eligible": len(null_eligible),
            "selected": len(null_selected),
            "confirmed": len(null_confirmed),
            "alpha": null_alpha,
            "best_test_p": min((row["test_p"] for row in null_selected), default=1.0),
        }
        null_reports.append(null_report)
        print(f"NULL {control + 1}: {null_report}")

    payload = {
        "schema": 2,
        "symbols": sorted(datasets),
        "datasets": {
            symbol: {
                "ticks": len(data["prices"]),
                "unique_epochs": len(np.unique(data["epochs"])),
                "first_epoch": int(data["epochs"][0]),
                "last_epoch": int(data["epochs"][-1]),
                "pip": data["pip"],
                "pip_size": data.get("pip_size"),
            }
            for symbol, data in sorted(datasets.items())
        },
        "ticks_requested": args.ticks,
        "tested": len(rows),
        "eligible": len(eligible),
        "family_counts": dict(sorted(families.items())),
        "final_alpha": final_alpha,
        "confirmed_count": len(confirmed),
        "selected": selected,
        "confirmed": confirmed,
        "null_controls": null_reports,
        "quotes": quotes,
        "rows": rows,
    }
    with gzip.open(output_path, "wt", encoding="utf-8") as handle:
        json.dump(payload, handle, separators=(",", ":"), allow_nan=False)
    print(f"Resultado completo: {output_path}")


if __name__ == "__main__":
    asyncio.run(main())
