import unittest

from d107_exact_historical_simulation import (
    CAPITAL_POLICIES,
    EXIT_SCENARIOS,
    MAX_POSITIONS,
    SimulationResults,
    run_simulation,
    simulate,
)


class TestExactHistoricalSimulation(unittest.TestCase):
    def test_deterministic_up_then_down_path(self):
        times = list(range(0, 901))
        prices = [100.0] * len(times)
        for index in range(301, len(prices)):
            prices[index] = 101.0
        quote_map = {
            "1.0:MULTUP": {"ask_price": 1.04, "cancellation_fee": 0.04, "commission": 0.02},
            "1.0:MULTDOWN": {"ask_price": 1.04, "cancellation_fee": 0.04, "commission": 0.02},
        }
        result = simulate("demo", times, prices, quote_map, 1.0, 10.4, "all_in")
        self.assertGreater(result.buys, 0)
        self.assertGreater(result.stopouts, 0)
        self.assertGreaterEqual(result.held_winners, 1)
        self.assertLess(result.realized_net, 0)

    def test_capital_policy_blocks_when_twenty_percent_is_insufficient(self):
        times = list(range(0, 31))
        prices = [100.0] * len(times)
        quote_map = {
            "10.0:MULTUP": {"ask_price": 10.44, "cancellation_fee": 0.44, "commission": 0.15},
            "10.0:MULTDOWN": {"ask_price": 10.44, "cancellation_fee": 0.44, "commission": 0.15},
        }
        result = simulate("demo", times, prices, quote_map, 10.0, 10.4, "20pct")
        self.assertEqual(result.buys, 0)
        self.assertEqual(result.positions, [])

    def test_position_count_is_bounded(self):
        times = list(range(0, 901))
        prices = [100.0] * len(times)
        quote_map = {
            "1.0:MULTUP": {"ask_price": 1.04, "cancellation_fee": 0.04, "commission": 0.02},
            "1.0:MULTDOWN": {"ask_price": 1.04, "cancellation_fee": 0.04, "commission": 0.02},
        }
        result = simulate("demo", times, prices, quote_map, 1.0, 104.0, "all_in")
        self.assertLessEqual(sum(1 for p in result.positions if p["status"] == "open"), MAX_POSITIONS)

    def test_manual_boundary_exit_realizes_winner_and_allows_turnover(self):
        times = list(range(0, 901))
        prices = [100.0] * len(times)
        for index in range(301, len(prices)):
            prices[index] = 101.0
        quote_map = {
            "1.0:MULTUP": {"ask_price": 1.04, "cancellation_fee": 0.04, "commission": 0.02},
            "1.0:MULTDOWN": {"ask_price": 1.04, "cancellation_fee": 0.04, "commission": 0.02},
        }
        result = simulate("demo", times, prices, quote_map, 1.0, 10.4, "all_in", "sell_boundary")
        self.assertGreater(result.manual_sells, 0)
        self.assertEqual(result.exit_policy, "sell_boundary")

    def test_no_randomness_in_policy_constants(self):
        self.assertEqual(CAPITAL_POLICIES, ("all_in", "20pct"))

    def test_deal_cancellation_fee_not_refunded_on_manual_sell_or_stopout(self):
        # Single entry at t=0, boundary at t=300, no subsequent entries (bankroll=1.44 allows 1 buy)
        times = [0, 300]
        # +1% move on 400x = +4.00 gross mark; with 0.00 commission and 0.44 fee, net = +3.56
        prices = [100.0, 101.0]
        quote_map = {
            "1.0:MULTUP": {"ask_price": 1.44, "cancellation_fee": 0.44, "commission": 0.0},
            "1.0:MULTDOWN": {"ask_price": 1.44, "cancellation_fee": 0.44, "commission": 0.0},
        }
        res_sell = simulate("demo", times, prices, quote_map, 1.0, 1.44, "all_in", "sell_boundary")
        self.assertEqual(res_sell.manual_sells, 1)
        self.assertAlmostEqual(res_sell.realized_net, 3.56, places=6)
        self.assertAlmostEqual(res_sell.positions[0]["terminal_net"], 3.56, places=6)

        # Stop-out at t=10 (-0.25% move on 400x = -1.00 gross mark -> stopout loses full cost 1.44)
        times_so = [0, 10]
        prices_so = [100.0, 99.75]
        res_so = simulate("demo", times_so, prices_so, quote_map, 1.0, 1.44, "all_in", "hold")
        self.assertEqual(res_so.buys, 1)
        self.assertEqual(res_so.stopouts, 1)
        self.assertAlmostEqual(res_so.realized_net, -1.44, places=6)
        self.assertAlmostEqual(res_so.as_dict()["final_balance"], 0.0, places=6)

    def test_exit_scenarios_contains_milestone_3_policies(self):
        scenario_names = [name for name, _ in EXIT_SCENARIOS]
        self.assertIn("micro_scalp_baseline", scenario_names)
        self.assertIn("perpetual_ladder_1x_8x", scenario_names)

    def test_micro_scalp_baseline_exits_intra_window(self):
        # Entry at t=0, price rises to 100.10 (+0.40 gross on 400x >= 0.25 target) at t=60 (< 300s window)
        times = [0, 60, 300]
        prices = [100.0, 100.10, 100.10]
        quote_map = {
            "1.0:MULTUP": {"ask_price": 1.04, "cancellation_fee": 0.04, "commission": 0.0},
            "1.0:MULTDOWN": {"ask_price": 1.04, "cancellation_fee": 0.04, "commission": 0.0},
        }
        res = simulate("demo", times, prices, quote_map, 1.0, 10.4, "all_in", "micro_scalp_baseline", target_multiple=0.25)
        self.assertEqual(res.manual_sells, 1)
        self.assertEqual(res.positions[0]["status"], "sold_winner_micro_scalp")
        self.assertEqual(res.positions[0]["terminal_time"], 60)
        # Net = 0.40 - 0.04 = 0.36
        self.assertAlmostEqual(res.realized_net, 0.36, places=6)

    def test_perpetual_ladder_abolishes_intra_window_scalp_and_rides_to_target(self):
        # Same path: price rises to 100.10 (+0.40) at t=60, but perpetual_ladder does NOT scalp!
        # At boundary t=300: net profit 0.36 >= 0.04 fee -> qualifies as held_winner.
        # At t=400: price climbs to 102.10 (+8.40 >= 8.0 target) -> exits as sold_winner_target!
        times = [0, 60, 300, 400]
        prices = [100.0, 100.10, 100.10, 102.10]
        quote_map = {
            "1.0:MULTUP": {"ask_price": 1.04, "cancellation_fee": 0.04, "commission": 0.0},
            "1.0:MULTDOWN": {"ask_price": 1.04, "cancellation_fee": 0.04, "commission": 0.0},
        }
        res = simulate("demo", times, prices, quote_map, 1.0, 10.4, "all_in", "perpetual_ladder_1x_8x", target_multiple=8.0)
        self.assertEqual(res.held_winners, 1)
        self.assertEqual(res.manual_sells, 1)
        self.assertEqual(res.positions[0]["status"], "sold_winner_target")
        self.assertEqual(res.positions[0]["terminal_time"], 400)
        self.assertAlmostEqual(res.positions[0]["terminal_net"], 8.36, places=6)

    def test_perpetual_ladder_cancels_marginal_winner_below_cancel_fee(self):
        # Price at t=300 boundary is 100.01 (+0.04 gross move; net = 0.04 - 0.04 = 0.00 < 0.04 cancel fee)
        # Must cancel defensively!
        times = [0, 300]
        prices = [100.0, 100.01]
        quote_map = {
            "1.0:MULTUP": {"ask_price": 1.04, "cancellation_fee": 0.04, "commission": 0.0},
            "1.0:MULTDOWN": {"ask_price": 1.04, "cancellation_fee": 0.04, "commission": 0.0},
        }
        res = simulate("demo", times, prices, quote_map, 1.0, 10.4, "all_in", "perpetual_ladder_1x_8x")
        self.assertEqual(res.cancellations, 1)
        self.assertEqual(res.held_winners, 0)
        self.assertEqual(res.positions[0]["status"], "cancelled_loser")
        self.assertAlmostEqual(res.realized_net, -0.04, places=6)

    def test_perpetual_ladder_relaxed_capital_preservation_exit(self):
        # Position qualifies at t=300 (price 100.20 -> +0.80 gross).
        # Later at t=400, price drops to 99.90 (-0.40 gross <= -0.35 * stake capital preservation stop).
        times = [0, 300, 400]
        prices = [100.0, 100.20, 99.90]
        quote_map = {
            "1.0:MULTUP": {"ask_price": 1.04, "cancellation_fee": 0.04, "commission": 0.0},
            "1.0:MULTDOWN": {"ask_price": 1.04, "cancellation_fee": 0.04, "commission": 0.0},
        }
        res = simulate("demo", times, prices, quote_map, 1.0, 10.4, "all_in", "perpetual_ladder_1x_8x")
        self.assertEqual(res.held_winners, 1)
        self.assertEqual(res.manual_sells, 1)
        self.assertEqual(res.positions[0]["status"], "sold_winner_capital_preservation")
        self.assertEqual(res.positions[0]["terminal_time"], 400)

    def test_run_simulation_interface_contract(self):
        ticks_list = [
            {"time": 0, "price": 100.0},
            {"time": 300, "price": 100.50},
            {"time": 400, "price": 102.50},
        ]
        res = run_simulation(ticks_list, exit_scenario="perpetual_ladder_1x_8x", stake=1.0)
        self.assertIsInstance(res, SimulationResults)
        d = res.as_dict()
        self.assertIn("expected_net_per_trade", d)
        self.assertIn("profit_factor", d)
        self.assertIn("runners_1x", d)
        self.assertIn("runners_4x", d)
        self.assertIn("runners_8x", d)


if __name__ == "__main__":
    unittest.main(verbosity=2)
