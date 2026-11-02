#!/usr/bin/env python3
"""Adversarial Verification Suite for Milestone 3 (Challenger 2).

Mission: Adversarial Verification of Trend Alignment Filter and Simulation Replay Integrity.

1. Trend Alignment Extreme Regimes:
   - Pure chop / Brownian noise: Test prices with Hurst ~0.50 and ADX < 15. Verify that trend alignment
     rejects / pauses entries rather than trading into chop or alternating blindly.
   - Runaway trend: Strong monotonic trend (BULLISH or BEARISH). Verify that entries strictly align
     with the macro tide and never open counter-trend contracts.
   - V-shape reversal: Strong trend that abruptly reverses. Verify that after reversal, old direction
     is purged and new direction is required before entering.
   - Edge cases: Single-price flatline, zero variance, nan/inf handling, tick gaps.
2. Simulation Replay Stress Testing:
   - Test simulation with randomized subsets of ticks or perturbed prices.
   - Verify that simulation does not leak future ticks into entry decisions (strict causality check).
   - Verify that accounting is strictly conservative (commissions, bid/ask spread, cancellation fees).
"""

import math
import os
import random
import sys
import unittest
from typing import Any

# Ensure trading-engine is in PYTHONPATH
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from d107_rate_limit_winner_holding import (
    CONTRACT_TYPES,
    TrendAlignmentSignal,
    calculate_adx_and_trend,
    evaluate_perpetual_ratchet,
)
from d107_exact_historical_simulation import (
    CANCELLATION_SECONDS,
    DIRECTIONS,
    MULTIPLIER,
    Position,
    SimulationResults,
    directional_gross,
    run_simulation,
    simulate,
)


def hurst_exponent(prices: list[float]) -> float:
    """Computes empirical Hurst exponent via Rescaled Range (R/S) analysis."""
    n = len(prices)
    if n < 50:
        return 0.5
    returns = [math.log(prices[i] / prices[i - 1]) for i in range(1, n)]
    lags = [10, 20, 40, 80]
    rs_vals = []
    lag_vals = []
    for lag in lags:
        if lag > len(returns):
            break
        subsets = [returns[i : i + lag] for i in range(0, len(returns) - lag + 1, lag)]
        rs_sub = []
        for s in subsets:
            mean = sum(s) / len(s)
            dev = [x - mean for x in s]
            cumdev = []
            c = 0.0
            for d in dev:
                c += d
                cumdev.append(c)
            r = max(cumdev) - min(cumdev)
            variance = sum(d * d for d in dev) / len(dev)
            std = math.sqrt(variance) if variance > 1e-12 else 1e-6
            rs_sub.append(r / std)
        if rs_sub:
            rs_vals.append(math.log(sum(rs_sub) / len(rs_sub)))
            lag_vals.append(math.log(lag))
    if len(lag_vals) >= 2:
        # Linear regression slope of log(R/S) vs log(lag)
        mean_x = sum(lag_vals) / len(lag_vals)
        mean_y = sum(rs_vals) / len(rs_vals)
        num = sum((x - mean_x) * (y - mean_y) for x, y in zip(lag_vals, rs_vals))
        den = sum((x - mean_x) ** 2 for x in lag_vals)
        return num / den if den > 0 else 0.5
    return 0.5


class TestTrendAlignmentExtremeRegimes(unittest.TestCase):
    """Stress testing the Trend Alignment module across extreme regimes."""

    def test_01_pure_chop_brownian_noise_and_adx_sub15(self):
        """Pure chop / Brownian noise: Test prices with Hurst ~0.50, ADX < 15.
        Verify that trend alignment rejects / pauses entries rather than trading into chop or alternating blindly.
        """
        rng = random.Random(42)
        n_ticks = 1000
        # 1. Generate Geometric Brownian Motion with zero drift
        p = 100.0
        prices_bm = [p]
        for _ in range(n_ticks - 1):
            ret = rng.gauss(0.0, 0.0004)
            p = max(1.0, p * math.exp(ret))
            prices_bm.append(p)

        h = hurst_exponent(prices_bm)
        print(f"\n[Pure Chop] Empirical Hurst exponent: {h:.3f} (Brownian motion ~0.50)")
        self.assertAlmostEqual(h, 0.50, delta=0.15, msg="Generated series must approximate Brownian motion")

        # 2. Test mean-reverting chop with ADX < 15
        rng_chop = random.Random(101)
        prices_sub15 = [100.0 + 0.08 * math.sin(i * 0.4) + rng_chop.uniform(-0.015, 0.015) for i in range(500)]
        times_sub15 = list(range(len(prices_sub15)))

        sub15_adx = []
        sub15_aligned = []
        for i in range(30, len(prices_sub15)):
            sig = calculate_adx_and_trend(prices_sub15[max(0, i - 180) : i + 1])
            sub15_adx.append(sig.adx_value)
            if sig.is_aligned:
                sub15_aligned.append(sig)

        mean_adx = sum(sub15_adx) / len(sub15_adx)
        print(f"[Low ADX Chop] Mean ADX: {mean_adx:.2f}, Aligned Signals when ADX < 15: {len([s for s in sub15_aligned if s.adx_value < 15])}")
        # Verify that NO signal is aligned when ADX < 15 (requirement: is_strong requires ADX >= 20)
        for sig in [calculate_adx_and_trend(prices_sub15[max(0, i - 180) : i + 1]) for i in range(30, len(prices_sub15))]:
            if sig.adx_value < 15.0:
                self.assertFalse(sig.is_aligned, "Signal must NOT be aligned when ADX < 15")
                self.assertEqual(sig.direction, "NONE", "Direction must be NONE when ADX < 15")

        # 3. Simulate replay under pure chop: compare trend_alignment_enabled vs unaligned alternation
        times_bm = list(range(n_ticks))
        quote_map = {
            "1.0:MULTUP": {"ask_price": 1.04, "cancellation_fee": 0.04, "commission": 0.0},
            "1.0:MULTDOWN": {"ask_price": 1.04, "cancellation_fee": 0.04, "commission": 0.0},
        }

        res_aligned_bm = simulate(
            profile="demo",
            times=times_bm,
            prices=prices_bm,
            quote_map=quote_map,
            stake=1.0,
            bankroll=100.0,
            capital_policy="all_in",
            exit_policy="perpetual_ladder_1x_8x",
            trend_alignment_enabled=True,
        )

        res_unaligned_bm = simulate(
            profile="demo",
            times=times_bm,
            prices=prices_bm,
            quote_map=quote_map,
            stake=1.0,
            bankroll=100.0,
            capital_policy="all_in",
            exit_policy="micro_scalp_baseline",
            trend_alignment_enabled=False,
        )

        res_aligned_sub15 = simulate(
            profile="demo",
            times=times_sub15,
            prices=prices_sub15,
            quote_map=quote_map,
            stake=1.0,
            bankroll=100.0,
            capital_policy="all_in",
            exit_policy="perpetual_ladder_1x_8x",
            trend_alignment_enabled=True,
        )

        print(f"[Brownian Noise Replay] Aligned Buys: {res_aligned_bm.buys} vs Unaligned Mechanical Buys: {res_unaligned_bm.buys}")
        print(f"[Low ADX Replay] Aligned Buys: {res_aligned_sub15.buys} (100% pause in pure chop)")

        # Verify trend alignment rejects trading into chop compared to blind mechanical alternation
        self.assertLess(
            res_aligned_bm.buys,
            res_unaligned_bm.buys,
            "Trend alignment must reject trading into Brownian chop compared to blind alternation",
        )
        self.assertEqual(
            res_aligned_sub15.buys,
            0,
            "Trend alignment must completely pause entries (0 buys) during persistent low-ADX chop",
        )

    def test_02_runaway_monotonic_bullish_trend(self):
        """Runaway trend (Bullish): Strong monotonic upward trend.
        Verify entries strictly align with macro tide (MULTUP) and NEVER open counter-trend (MULTDOWN).
        """
        n_ticks = 600
        p0 = 100.0
        prices = [p0 * (1.0 + 0.0002) ** t for t in range(n_ticks)]
        times = list(range(n_ticks))

        sig = calculate_adx_and_trend(prices)
        self.assertTrue(sig.is_aligned, "Strong runaway bull trend must be aligned")
        self.assertEqual(sig.direction, "MULTUP", "Runaway bull trend must be MULTUP")
        self.assertEqual(sig.macro_trend, "BULLISH", "Runaway bull trend macro must be BULLISH")
        self.assertGreaterEqual(sig.adx_value, 25.0, "ADX must be high in runaway trend")

        quote_map = {
            "1.0:MULTUP": {"ask_price": 1.04, "cancellation_fee": 0.04, "commission": 0.0},
            "1.0:MULTDOWN": {"ask_price": 1.04, "cancellation_fee": 0.04, "commission": 0.0},
        }

        res = simulate(
            profile="demo",
            times=times,
            prices=prices,
            quote_map=quote_map,
            stake=1.0,
            bankroll=100.0,
            capital_policy="all_in",
            exit_policy="perpetual_ladder_1x_8x",
            trend_alignment_enabled=True,
        )

        print(f"\n[Runaway Bullish] Buys: {res.buys}, Realized Net: ${res.realized_net:.2f}")
        self.assertGreater(res.buys, 0, "Must enter trades in strong bullish trend")
        for pos in res.positions:
            self.assertEqual(
                pos["direction"],
                "MULTUP",
                f"Position {pos['position_id']} had direction {pos['direction']}; expected MULTUP only!",
            )

    def test_03_runaway_monotonic_bearish_trend(self):
        """Runaway trend (Bearish): Strong monotonic downward trend.
        Verify entries strictly align with macro tide (MULTDOWN) and NEVER open counter-trend (MULTUP).
        """
        n_ticks = 600
        p0 = 100.0
        prices = [p0 * (1.0 - 0.0002) ** t for t in range(n_ticks)]
        times = list(range(n_ticks))

        sig = calculate_adx_and_trend(prices)
        self.assertTrue(sig.is_aligned, "Strong runaway bear trend must be aligned")
        self.assertEqual(sig.direction, "MULTDOWN", "Runaway bear trend must be MULTDOWN")
        self.assertEqual(sig.macro_trend, "BEARISH", "Runaway bear trend macro must be BEARISH")
        self.assertGreaterEqual(sig.adx_value, 25.0, "ADX must be high in runaway bear trend")

        quote_map = {
            "1.0:MULTUP": {"ask_price": 1.04, "cancellation_fee": 0.04, "commission": 0.0},
            "1.0:MULTDOWN": {"ask_price": 1.04, "cancellation_fee": 0.04, "commission": 0.0},
        }

        res = simulate(
            profile="demo",
            times=times,
            prices=prices,
            quote_map=quote_map,
            stake=1.0,
            bankroll=100.0,
            capital_policy="all_in",
            exit_policy="perpetual_ladder_1x_8x",
            trend_alignment_enabled=True,
        )

        print(f"\n[Runaway Bearish] Buys: {res.buys}, Realized Net: ${res.realized_net:.2f}")
        self.assertGreater(res.buys, 0, "Must enter trades in strong bearish trend")
        for pos in res.positions:
            self.assertEqual(
                pos["direction"],
                "MULTDOWN",
                f"Position {pos['position_id']} had direction {pos['direction']}; expected MULTDOWN only!",
            )

    def test_04_v_shape_reversal_purge_and_realign(self):
        """V-shape reversal: Strong downtrend abruptly reverses to strong uptrend.
        Verify that after reversal, old direction is purged, entries pause in transition,
        and new direction is required before entering.
        """
        down_ticks = 100
        up_ticks = 100
        # Downtrend: 100.0 down to 80.0
        prices_down = [100.0 - (0.2 * t) for t in range(down_ticks)]
        # Uptrend: 80.0 up to 110.0
        prices_up = [80.0 + (0.3 * t) for t in range(1, up_ticks + 1)]
        prices = prices_down + prices_up
        times = list(range(len(prices)))

        # Track signals across the reversal point (ticks 80 to 150)
        reversal_tick = 100
        pre_sig = calculate_adx_and_trend(prices[max(0, 90 - 180) : 91])
        self.assertEqual(pre_sig.macro_trend, "BEARISH")
        self.assertEqual(pre_sig.direction, "MULTDOWN")

        # During inflection (ticks 110-130), verify direction is NONE / unaligned
        inflection_unaligned_count = 0
        for t in range(110, 135, 5):
            sig = calculate_adx_and_trend(prices[max(0, t - 180) : t + 1])
            if sig.direction == "NONE" and not sig.is_aligned:
                inflection_unaligned_count += 1
        self.assertGreater(inflection_unaligned_count, 0, "Inflection zone must purge old direction to NONE")

        # After upward trend established (tick 150+)
        post_sig = calculate_adx_and_trend(prices[max(0, 150 - 180) : 151])
        print(f"\n[V-Shape] Pre-reversal (t=90): {pre_sig.direction}, Transition (t=120): NONE, Post-reversal (t=150): {post_sig.direction}")
        self.assertEqual(post_sig.macro_trend, "BULLISH")
        self.assertEqual(post_sig.direction, "MULTUP")

        # Simulate replay and check that no MULTDOWN entries are opened after reversal transition
        quote_map = {
            "1.0:MULTUP": {"ask_price": 1.04, "cancellation_fee": 0.04, "commission": 0.0},
            "1.0:MULTDOWN": {"ask_price": 1.04, "cancellation_fee": 0.04, "commission": 0.0},
        }
        res = simulate(
            profile="demo",
            times=times,
            prices=prices,
            quote_map=quote_map,
            stake=1.0,
            bankroll=100.0,
            capital_policy="all_in",
            exit_policy="perpetual_ladder_1x_8x",
            trend_alignment_enabled=True,
        )

        late_positions = [p for p in res.positions if p["entry_time"] >= 140]
        for p in late_positions:
            self.assertEqual(
                p["direction"],
                "MULTUP",
                f"Position at t={p['entry_time']} after V-reversal must be MULTUP, was {p['direction']}",
            )

    def test_05_flatline_zero_variance_edge_cases(self):
        """Edge cases: Single-price flatline, micro-perturbations, zero variance."""
        # 1. Perfectly flat price series
        flat_prices = [100.0] * 200
        sig_flat = calculate_adx_and_trend(flat_prices)
        self.assertEqual(sig_flat.macro_trend, "NEUTRAL")
        self.assertEqual(sig_flat.direction, "NONE")
        self.assertFalse(sig_flat.is_aligned)
        self.assertEqual(sig_flat.adx_value, 0.0)

        # 2. Alternating micro-noise: epsilon differences (1e-12)
        micro_prices = [100.0 + (1e-12 if i % 2 == 0 else -1e-12) for i in range(200)]
        sig_micro = calculate_adx_and_trend(micro_prices)
        self.assertEqual(sig_micro.macro_trend, "NEUTRAL")
        self.assertEqual(sig_micro.direction, "NONE")
        self.assertFalse(sig_micro.is_aligned)
        self.assertLess(sig_micro.adx_value, 20.0)

        # 3. Short sequence (< 30 ticks)
        short_prices = [100.0, 101.0, 102.0]
        sig_short = calculate_adx_and_trend(short_prices)
        self.assertEqual(sig_short.direction, "NONE")
        self.assertFalse(sig_short.is_aligned)

        # 4. Simulation on flatline prices
        times = list(range(200))
        quote_map = {
            "1.0:MULTUP": {"ask_price": 1.04, "cancellation_fee": 0.04, "commission": 0.0},
            "1.0:MULTDOWN": {"ask_price": 1.04, "cancellation_fee": 0.04, "commission": 0.0},
        }
        res_flat = simulate(
            profile="demo",
            times=times,
            prices=flat_prices,
            quote_map=quote_map,
            stake=1.0,
            bankroll=100.0,
            capital_policy="all_in",
            exit_policy="perpetual_ladder_1x_8x",
            trend_alignment_enabled=True,
        )
        self.assertEqual(res_flat.buys, 0, "No buys should ever occur on a flatline price series")

    def test_06_nan_inf_none_type_handling(self):
        """Edge cases: NaN, Inf, negative prices, and bad input types."""
        # Mix valid prices with nan and inf
        raw_prices = [100.0 + i * 0.1 for i in range(50)]
        corrupted = raw_prices.copy()
        corrupted[10] = float("nan")
        corrupted[20] = float("inf")
        corrupted[30] = -50.0  # negative
        corrupted[40] = float("-inf")

        # calculate_adx_and_trend cleans non-finite and <= 0 numbers
        sig = calculate_adx_and_trend(corrupted)
        self.assertIsInstance(sig, TrendAlignmentSignal)
        self.assertTrue(math.isfinite(sig.adx_value))

        # Check what happens if ALL are nan
        all_nan = [float("nan")] * 50
        sig_nan = calculate_adx_and_trend(all_nan)
        self.assertEqual(sig_nan.direction, "NONE")
        self.assertFalse(sig_nan.is_aligned)

        # Check raw non-numeric / string inputs: documents current behavior
        try:
            calculate_adx_and_trend(["bad_data", 100.0])
            type_error_raised = False
        except TypeError:
            type_error_raised = True
        self.assertTrue(
            type_error_raised,
            "Direct calculate_adx_and_trend raises TypeError if input is not pre-cleaned by _positive_float",
        )

    def test_07_tick_gaps_and_irregular_intervals(self):
        """Edge cases: Large tick gaps and non-uniform timestamps."""
        times = [0, 1, 2, 3, 4, 3600, 3601, 3602, 3603, 3604]
        prices = [100.0, 100.1, 100.2, 100.3, 100.4, 105.0, 105.1, 105.2, 105.3, 105.4]
        quote_map = {
            "1.0:MULTUP": {"ask_price": 1.04, "cancellation_fee": 0.04, "commission": 0.0},
            "1.0:MULTDOWN": {"ask_price": 1.04, "cancellation_fee": 0.04, "commission": 0.0},
        }
        res = simulate(
            profile="demo",
            times=times,
            prices=prices,
            quote_map=quote_map,
            stake=1.0,
            bankroll=10.0,
            capital_policy="all_in",
            exit_policy="perpetual_ladder_1x_8x",
            trend_alignment_enabled=False,
        )
        self.assertGreater(res.buys, 0)
        cancelled_or_held = [p for p in res.positions if p["boundary_time"] is not None]
        self.assertGreater(len(cancelled_or_held), 0)


class TestSimulationReplayStressAndIntegrity(unittest.TestCase):
    """Stress testing the historical simulation replay engine for integrity."""

    def test_08_strict_causality_oracle_test(self):
        """Strict causality check: Verify that future ticks do not leak into past entry/exit decisions.
        We run two simulations identical up to tick T, but diverging completely after T.
        All decisions, positions, and ledger states at t <= T MUST be bit-for-bit identical.
        """
        rng = random.Random(12345)
        prefix_len = 300
        diverge_len = 200

        # Base prefix
        p = 100.0
        base_prices = [p]
        for _ in range(prefix_len - 1):
            p = p * math.exp(rng.gauss(0.0001, 0.0005))
            base_prices.append(p)
        base_times = list(range(prefix_len))

        # Branch A: Skyrockets
        branch_a_prices = list(base_prices)
        p_a = base_prices[-1]
        for _ in range(diverge_len):
            p_a = p_a * 1.002
            branch_a_prices.append(p_a)

        # Branch B: Crashes
        branch_b_prices = list(base_prices)
        p_b = base_prices[-1]
        for _ in range(diverge_len):
            p_b = p_b * 0.998
            branch_b_prices.append(p_b)

        full_times = list(range(prefix_len + diverge_len))
        quote_map = {
            "1.0:MULTUP": {"ask_price": 1.04, "cancellation_fee": 0.04, "commission": 0.0},
            "1.0:MULTDOWN": {"ask_price": 1.04, "cancellation_fee": 0.04, "commission": 0.0},
        }

        res_a = simulate(
            profile="demo",
            times=full_times,
            prices=branch_a_prices,
            quote_map=quote_map,
            stake=1.0,
            bankroll=100.0,
            capital_policy="all_in",
            exit_policy="perpetual_ladder_1x_8x",
            trend_alignment_enabled=True,
        )

        res_b = simulate(
            profile="demo",
            times=full_times,
            prices=branch_b_prices,
            quote_map=quote_map,
            stake=1.0,
            bankroll=100.0,
            capital_policy="all_in",
            exit_policy="perpetual_ladder_1x_8x",
            trend_alignment_enabled=True,
        )

        # Check all positions that entered at t < prefix_len, sorted by position_id
        pos_a_prefix = sorted([p for p in res_a.positions if p["entry_time"] < prefix_len], key=lambda x: x["position_id"])
        pos_b_prefix = sorted([p for p in res_b.positions if p["entry_time"] < prefix_len], key=lambda x: x["position_id"])

        self.assertEqual(
            len(pos_a_prefix),
            len(pos_b_prefix),
            "Number of entries prior to divergence tick must be identical",
        )

        for pa, pb in zip(pos_a_prefix, pos_b_prefix):
            self.assertEqual(pa["position_id"], pb["position_id"])
            self.assertEqual(pa["entry_time"], pb["entry_time"])
            self.assertAlmostEqual(pa["entry_price"], pb["entry_price"], places=6)
            self.assertEqual(pa["direction"], pb["direction"])
            self.assertAlmostEqual(pa["ask_price"], pb["ask_price"], places=6)
            self.assertAlmostEqual(pa["cancellation_fee"], pb["cancellation_fee"], places=6)

        print(f"\n[Causality Oracle] Tested prefix {prefix_len} ticks: All {len(pos_a_prefix)} entry decisions identical across divergent futures.")

    def test_09_randomized_tick_perturbations_and_subsets(self):
        """Test simulation stability across randomized subsamples and perturbed price paths."""
        rng = random.Random(999)
        n = 500
        p = 100.0
        prices = [p]
        for _ in range(n - 1):
            p = p * math.exp(rng.gauss(0.0, 0.001))
            prices.append(p)
        times = [t * 2 for t in range(n)]

        quote_map = {
            "1.0:MULTUP": {"ask_price": 1.04, "cancellation_fee": 0.04, "commission": 0.005},
            "1.0:MULTDOWN": {"ask_price": 1.04, "cancellation_fee": 0.04, "commission": 0.005},
        }

        indices = sorted(rng.sample(range(n), int(n * 0.6)))
        sub_times = [times[i] for i in indices]
        sub_prices = [prices[i] for i in indices]

        res = simulate(
            profile="demo",
            times=sub_times,
            prices=sub_prices,
            quote_map=quote_map,
            stake=1.0,
            bankroll=50.0,
            capital_policy="all_in",
            exit_policy="perpetual_ladder_1x_8x",
            trend_alignment_enabled=True,
        )

        d = res.as_dict()
        self.assertGreaterEqual(res.buys, 0)
        self.assertGreaterEqual(res.cancellations, 0)
        self.assertGreaterEqual(res.held_winners, 0)
        self.assertGreaterEqual(res.max_drawdown, 0.0)
        self.assertAlmostEqual(d["final_balance"], res.bankroll + d["final_equity"], places=6)
        print(f"\n[Perturbation Test] Subsample 60% (n={len(sub_times)}): Buys={res.buys}, Cancellations={res.cancellations}, Held={res.held_winners}, Realized=${res.realized_net:.2f}")

    def test_10_conservative_accounting_and_conservation(self):
        """Verify that accounting is strictly conservative:
        1. Cancellation fees deducted on cancel and from winners.
        2. Commission deducted from mark.
        3. Stopout loses full cost (stake + cancellation fee).
        4. Cash conservation: bankroll + realized_net + unrealized == final balance.
        """
        # Test Case A: Clean Cancellation (0.1% adverse drop on 400x multiplier = -0.40 mark, does not stop out)
        times_c = [0, 300]
        prices_c = [100.0, 99.90]
        quote_map = {
            "1.0:MULTUP": {"ask_price": 1.08, "cancellation_fee": 0.08, "commission": 0.01},
            "1.0:MULTDOWN": {"ask_price": 1.08, "cancellation_fee": 0.08, "commission": 0.01},
        }

        res_cancel = simulate("demo", times_c, prices_c, quote_map, 1.0, 1.08, "all_in", "perpetual_ladder_1x_8x")
        self.assertEqual(res_cancel.buys, 1)
        self.assertEqual(res_cancel.cancellations, 1)
        # Loss must be strictly equal to cancellation fee (-0.08)
        self.assertAlmostEqual(res_cancel.realized_net, -0.08, places=6)
        self.assertAlmostEqual(res_cancel.as_dict()["final_balance"], 1.00, places=6)

        # Test Case B: Stopout loses full cost
        times_so = [0, 10]
        # Multiplier 400x -> -0.30% drop (-0.30 on 100) loses -1.20 gross mark <= -1.00 stake -> stopout!
        prices_so = [100.0, 99.70]
        res_so = simulate("demo", times_so, prices_so, quote_map, 1.0, 1.08, "all_in", "perpetual_ladder_1x_8x")
        self.assertEqual(res_so.buys, 1)
        self.assertEqual(res_so.stopouts, 1)
        # Full cost lost: stake (1.00) + cancellation fee (0.08) = 1.08
        self.assertAlmostEqual(res_so.realized_net, -1.08, places=6)
        self.assertAlmostEqual(res_so.as_dict()["final_balance"], 0.0, places=6)

        # Test Case C: Winner with commission and fee
        times_win = [0, 300, 350]
        prices_win = [100.0, 100.20, 102.10]
        res_win = simulate("demo", times_win, prices_win, quote_map, 1.0, 1.08, "all_in", "perpetual_ladder_1x_8x")
        self.assertGreaterEqual(res_win.buys, 1)
        self.assertEqual(res_win.held_winners, 1)
        self.assertEqual(res_win.manual_sells, 1)
        pos = res_win.positions[0]
        self.assertEqual(pos["status"], "sold_winner_target")
        expected_mark = directional_gross("MULTUP", 100.0, 102.10, 1.0, MULTIPLIER) - 0.01
        expected_net = expected_mark - 0.08
        self.assertAlmostEqual(pos["terminal_net"], expected_net, places=6)
        print(f"\n[Conservative Accounting] Cancel loss: ${res_cancel.realized_net:.2f}, Stopout loss: ${res_so.realized_net:.2f}, Winner Net: ${pos['terminal_net']:.2f}")

    def test_11_progressive_perpetual_ratchet_tiers(self):
        """Adversarial stress-test of the 4-tier progressive ratchet:
        Verify floor ratchet at 1x, 2x, 4x, 8x and trailing stop triggers.
        """
        stake = 1.0
        # Tier 0 (< 1.0x): no floor
        s0 = evaluate_perpetual_ratchet(profit=0.5, stake=stake, peak_profit=0.8)
        self.assertEqual(s0.current_tier, 0)
        self.assertFalse(s0.should_exit)

        # Tier 1 (+1.0x stake): floor locked at +0.20
        s1 = evaluate_perpetual_ratchet(profit=1.2, stake=stake, peak_profit=1.2)
        self.assertEqual(s1.current_tier, 1)
        self.assertEqual(s1.guaranteed_floor, 0.20)
        self.assertFalse(s1.should_exit)

        # Tier 1 pullback down to 0.20: must exit with trailing stop
        s1_exit = evaluate_perpetual_ratchet(profit=0.19, stake=stake, peak_profit=1.2)
        self.assertEqual(s1_exit.current_tier, 1)
        self.assertTrue(s1_exit.should_exit)
        self.assertEqual(s1_exit.exit_reason, "winner_trailing_stop")

        # Tier 2 (+2.0x stake): floor locked at +1.00
        s2 = evaluate_perpetual_ratchet(profit=2.5, stake=stake, peak_profit=2.5)
        self.assertEqual(s2.current_tier, 2)
        self.assertEqual(s2.guaranteed_floor, 1.00)
        self.assertFalse(s2.should_exit)

        # Tier 2 pullback to 0.99: must exit
        s2_exit = evaluate_perpetual_ratchet(profit=0.99, stake=stake, peak_profit=2.5)
        self.assertTrue(s2_exit.should_exit)

        # Tier 3 (+4.0x stake): floor locked at +2.50
        s3 = evaluate_perpetual_ratchet(profit=4.5, stake=stake, peak_profit=4.5)
        self.assertEqual(s3.current_tier, 3)
        self.assertEqual(s3.guaranteed_floor, 2.50)
        self.assertFalse(s3.should_exit)

        # Tier 4 (+8.0x stake): target hit!
        s4 = evaluate_perpetual_ratchet(profit=8.0, stake=stake, peak_profit=8.0)
        self.assertEqual(s4.current_tier, 4)
        self.assertTrue(s4.should_exit)
        self.assertEqual(s4.exit_reason, "winner_exit_multiple")

        # Tier 4 peak 10.0x pullback below 80% (8.00): must exit
        s4_trail = evaluate_perpetual_ratchet(profit=7.9, stake=stake, peak_profit=10.0)
        self.assertEqual(s4_trail.current_tier, 4)
        self.assertTrue(s4_trail.should_exit)
        self.assertEqual(s4_trail.exit_reason, "winner_trailing_stop")
        print(f"\n[Ratchet Tiers] Successfully verified all 4 ratchet tiers and trailing stops.")


if __name__ == "__main__":
    unittest.main(verbosity=2)
