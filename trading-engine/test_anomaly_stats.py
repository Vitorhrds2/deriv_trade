"""Testes offline das primitivas estatisticas do monitor de anomalias.

Sem rede e sem dependencias externas. Rode com:
    python test_anomaly_stats.py
ou, se tiver pytest:
    pytest test_anomaly_stats.py -q
"""
import math
import random

from anomaly_stats import (
    CHI2_CRIT_DF9,
    autocorr_lag1,
    chi_square_uniform,
    digit_z_scores,
    ev_bounds,
    ev_per_unit,
    implied_prob,
    runs_test_z,
    spike_timing_z,
    wilson_interval,
)


def test_wilson_contains_phat_and_orders():
    lo, hi = wilson_interval(50, 100)
    assert 0.0 <= lo < 0.5 < hi <= 1.0
    # IC encolhe com mais amostras.
    lo_small, hi_small = wilson_interval(5, 10)
    lo_big, hi_big = wilson_interval(500, 1000)
    assert (hi_big - lo_big) < (hi_small - lo_small)


def test_wilson_edges():
    assert wilson_interval(0, 0) == (0.0, 1.0)
    lo, hi = wilson_interval(0, 100)
    assert lo == 0.0 and hi < 0.1


def test_chi_square_uniform_zero_when_flat():
    assert chi_square_uniform([100] * 10) == 0.0


def test_chi_square_detects_skew():
    skewed = [50, 50, 50, 50, 50, 50, 50, 50, 50, 550]
    assert chi_square_uniform(skewed) > CHI2_CRIT_DF9[0.001]


def test_digit_z_scores_flag_outlier():
    counts = [100] * 10
    counts[7] = 40  # digito 7 suprimido
    z = digit_z_scores(counts)
    assert z[7] < -3.0
    assert abs(z[0]) < 3.0


def test_runs_test_directions():
    # Alternancia perfeita = MUITAS corridas = reversao -> z grande POSITIVO.
    alt = [i % 2 for i in range(200)]
    assert runs_test_z(alt) > 3.0
    # Streaks longas = POUCAS corridas = tendencia -> z grande NEGATIVO.
    streaks = [0] * 100 + [1] * 100
    assert runs_test_z(streaks) < -3.0
    # Serie aleatoria justa fica perto de 0.
    rng = random.Random(12345)
    rand = [rng.randrange(2) for _ in range(2000)]
    assert abs(runs_test_z(rand)) < 3.0


def test_spike_timing_z():
    # Gaps na media do spec -> z pequeno (cadencia normal).
    assert abs(spike_timing_z([1000] * 50, 1000)) < 1.0
    # Gaps sistematicamente na metade -> spikes acelerados -> z bem negativo.
    assert spike_timing_z([500] * 50, 1000) < -3.0
    # Gaps ao dobro -> spikes atrasados -> z bem positivo.
    assert spike_timing_z([2000] * 50, 1000) > 3.0
    # Amostra insuficiente ou spec invalido -> 0.
    assert spike_timing_z([1000], 1000) == 0.0
    assert spike_timing_z([1000] * 50, 0) == 0.0


def test_autocorr_lag1_bounds():
    assert abs(autocorr_lag1([1, 2, 1, 2, 1, 2]) + 1.0) < 0.2
    assert autocorr_lag1([5]) == 0.0


def test_implied_and_ev():
    assert abs(implied_prob(2.0) - 0.5) < 1e-12
    # Jogo justo 50/50 com payout 2.0 => EV 0.
    assert abs(ev_per_unit(0.5, 2.0)) < 1e-12
    # Casa pagando 0.95 liquido num 50/50 => EV negativo.
    assert ev_per_unit(0.5, 1.95) < 0


def test_ev_bounds_propagation():
    lo, hi = ev_bounds(0.50, 0.55, 2.10)
    assert lo < hi
    # ev_lo > 0 significa "+EV mesmo no pior caso do IC".
    assert lo == ev_per_unit(0.50, 2.10)


def _run_all():
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failed = 0
    for fn in fns:
        try:
            fn()
            print(f"  PASS {fn.__name__}")
        except AssertionError as e:
            failed += 1
            print(f"  FAIL {fn.__name__}: {e}")
    print(f"\n{len(fns) - failed}/{len(fns)} testes passaram.")
    return failed


if __name__ == "__main__":
    raise SystemExit(1 if _run_all() else 0)
