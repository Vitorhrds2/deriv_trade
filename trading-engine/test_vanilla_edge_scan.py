import numpy as np

from vanilla_edge_scan import bootstrap_mean_ci, monte_carlo_payout


def test_zero_return_pool_has_exact_call_payoff():
    values = monte_carlo_payout([0.0], 100, 105.0, 100.0, True, 2500, np.random.default_rng(7))
    assert values == [5.0] * 2500


def test_zero_return_pool_has_exact_put_payoff():
    values = monte_carlo_payout([0.0], 100, 95.0, 100.0, False, 2500, np.random.default_rng(7))
    assert values == [5.0] * 2500


def test_vectorized_bootstrap_is_seeded_and_exact_for_constant_values():
    first = bootstrap_mean_ci([3.5] * 5000, n_boot=1000, seed=9)
    second = bootstrap_mean_ci([3.5] * 5000, n_boot=1000, seed=9)
    assert first == second == (3.5, 3.5, 3.5)


def test_vectorized_sampler_is_seeded_and_nonnegative():
    first = monte_carlo_payout([-1.0, 1.0], 30, 100.0, 100.0, True, 5000, np.random.default_rng(11))
    second = monte_carlo_payout([-1.0, 1.0], 30, 100.0, 100.0, True, 5000, np.random.default_rng(11))
    assert first == second
    assert len(first) == 5000
    assert min(first) >= 0.0
