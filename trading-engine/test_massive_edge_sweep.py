import math

import numpy as np

from massive_edge_sweep import (
    bh_adjust,
    binomial_sf,
    direction_rows,
    finalize,
    infer_pip,
    normalize_history,
    signal_indices,
    split_summary,
    wilson,
)


def test_binomial_sf_exact_tail():
    assert math.isclose(binomial_sf(10, 10, 0.5), 1.0 / 1024.0, rel_tol=1e-10)
    assert binomial_sf(0, 10, 0.5) == 1.0


def test_wilson_orders_and_contains_rate():
    low, high = wilson(60, 100)
    assert 0.0 < low < 0.6 < high < 1.0


def test_bh_adjust_is_monotone_by_p_value():
    rows = [{"val_p": value} for value in (0.04, 0.001, 0.02, 0.8)]
    bh_adjust(rows)
    ordered = sorted(rows, key=lambda row: row["val_p"])
    assert all(ordered[index]["val_q"] <= ordered[index + 1]["val_q"] for index in range(len(ordered) - 1))
    assert ordered[0]["val_q"] <= 0.0041


def test_infer_pip_uses_observed_quote_granularity():
    assert infer_pip(np.array([52701.4451, 52691.4227, 52707.2549, 52702.3033])) == 0.0001
    assert infer_pip(np.array([803727.04, 803736.47, 803734.45, 803768.30])) == 0.01


def test_normalize_history_sorts_and_deduplicates_wrapped_pages():
    prices, epochs = normalize_history([10.1, 10.2, 10.3, 10.1, 10.2], [1, 2, 3, 1, 2], 10)
    assert epochs.tolist() == [1, 2, 3]
    assert prices.tolist() == [10.1, 10.2, 10.3]


def test_normalize_history_rejects_length_mismatch():
    try:
        normalize_history([1.0, 2.0], [1], 10)
    except ValueError:
        pass
    else:
        raise AssertionError("length mismatch must fail")


def test_signal_indices_keep_outcomes_inside_split_and_nonoverlapping():
    indices = signal_indices(100, 200, 8, 5)
    assert indices[0] >= 100
    assert indices[-1] + 1 + 5 < 200
    assert np.all(np.diff(indices) == 6)


def test_split_summary_prices_house_edge():
    fair = split_summary(500, 1000, 2.0)
    house = split_summary(500, 1000, 1.923)
    assert abs(fair["ev"]) < 1e-12
    assert house["ev"] < 0.0


def test_direction_sweep_detects_execution_lag_signal():
    signs = np.where(np.arange(12000) % 2 == 0, 1.0, -1.0)
    prices = 1000.0 + np.cumsum(signs)
    quotes = {
        f"S:CALL:{horizon}": {"gross": 1.923, "exact": True}
        for horizon in (1, 2, 3, 5, 8, 13, 21)
    }
    quotes.update({
        f"S:PUT:{horizon}": {"gross": 1.923, "exact": True}
        for horizon in (1, 2, 3, 5, 8, 13, 21)
    })
    rows = direction_rows("S", prices, quotes)
    matching = [
        row for row in rows
        if row["params"]["mode"] == "momentum"
        and row["params"]["lookback"] == 1
        and row["params"]["horizon"] == 1
    ]
    assert matching
    assert max(row["test_wr"] for row in matching) == 1.0


def test_finalize_requires_exact_quote():
    validation = split_summary(900, 1000, 1.923)
    test = split_summary(900, 1000, 1.923)
    base = {
        "family": "x",
        "symbol": "S",
        "params": {},
        "gross_return": 1.923,
        "quote_exact": False,
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
    _, selected, confirmed, _ = finalize([base], 100, 25, 0.05)
    assert selected and not confirmed
