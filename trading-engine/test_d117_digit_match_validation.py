import numpy as np

from d117_digit_match_validation import digit_from_tick, evaluate_model, fit_model


def test_digit_from_tick_uses_stream_pip_size():
    assert digit_from_tick({"quote": 52701.4451, "pip_size": "4"}, 0.01) == 1
    assert digit_from_tick({"quote": 803727.04, "pip_size": "2"}, 0.1) == 4


def test_model_learns_deterministic_two_digit_context():
    digits = np.tile(np.arange(10), 1200)
    prices = 1000.0 + digits * 0.01
    model = fit_model(prices, 0.01, confidence=0.02, minimum_context=10)
    assert model["selected"].any()
    summary = evaluate_model(model, model["train_end"], len(prices), 1, 8.929)
    assert summary["n"] > 1000
    assert summary["wr"] == 1.0


def test_execution_lag_changes_deterministic_target():
    digits = np.tile(np.arange(10), 1200)
    prices = 1000.0 + digits * 0.01
    model = fit_model(prices, 0.01, confidence=0.02, minimum_context=10)
    lag_one = evaluate_model(model, model["train_end"], len(prices), 1, 8.929)
    lag_two = evaluate_model(model, model["train_end"], len(prices), 2, 8.929)
    assert lag_one["wr"] == 1.0
    assert lag_two["wr"] == 0.0
