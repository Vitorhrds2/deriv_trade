import json
import os
import tempfile
import unittest
from unittest.mock import patch

import hyperliquid_oos_runner as runner


class StateTests(unittest.TestCase):
    def snapshot(self, hl_bid=100.0, hl_ask=100.0, bn_bid=100.0, bn_ask=100.0, observed_ms=1_000_000):
        return {
            "observed_utc": "2026-07-12T00:00:00+00:00",
            "observed_ms": observed_ms,
            "hl_bid": hl_bid,
            "hl_ask": hl_ask,
            "hl_mark": 100.0,
            "hl_funding": 0.0,
            "bn_bid": bn_bid,
            "bn_ask": bn_ask,
        }

    def test_initial_state_charges_one_roundtrip_at_executable_prices(self):
        state = runner.initialize_state(1000.0, self.snapshot(), {"time": 900_000, "rate": 0.0})
        self.assertEqual(state["last_bn_funding_time_ms"], 900_000)
        self.assertEqual(state["current_exit_net_bps"], -runner.ROUNDTRIP_BPS)
        self.assertAlmostEqual(state["current_exit_net_usd"], -1.9)

    def test_spread_and_adverse_move_are_included(self):
        state = runner.initialize_state(
            1000.0,
            self.snapshot(hl_bid=100.0, hl_ask=100.2, bn_bid=99.8, bn_ask=100.0),
            None,
        )
        exit_snapshot = self.snapshot(hl_bid=100.8, hl_ask=101.0, bn_bid=99.0, bn_ask=99.2)
        self.assertAlmostEqual(runner.exit_price_pnl_bps(state, exit_snapshot), -200.0)

    def test_funding_event_is_idempotent(self):
        state = runner.initialize_state(1000.0, self.snapshot(), {"time": 900_000, "rate": 0.0})
        event = {"time": 1_100_000, "rate": 0.0001}
        hl_history = [{"time": 1_000_000, "rate": 0.0002}]
        cycle = runner.settle_funding_event(state, event, hl_history, self.snapshot(observed_ms=1_100_100))
        duplicate = runner.settle_funding_event(state, event, hl_history, self.snapshot(observed_ms=1_100_200))
        self.assertIsNotNone(cycle)
        self.assertIsNone(duplicate)
        self.assertEqual(len(state["cycles"]), 1)
        self.assertAlmostEqual(cycle["funding_pnl_bps"], 1.0)
        self.assertAlmostEqual(cycle["incremental_net_bps"], 1.0)
        self.assertAlmostEqual(state["current_exit_net_bps"], -18.0)

    def test_process_uses_strict_eight_hour_funding_window(self):
        event_time = 8 * 3600 * 1000
        state = runner.initialize_state(1000.0, self.snapshot(), {"time": 1, "rate": 0.0})
        state["last_bn_funding_time_ms"] = 1
        records = [
            {"time": 0, "rate": 0.1},
            {"time": 3600 * 1000, "rate": 0.2},
            {"time": event_time, "rate": 0.3},
            {"time": event_time + 1, "rate": 0.4},
        ]
        with patch.object(runner.time, "time", return_value=event_time / 1000 + 1), patch.object(
            runner, "binance_funding_history", return_value=[{"time": event_time, "rate": 0.0}]
        ), patch.object(runner, "market_snapshot", return_value=self.snapshot(observed_ms=event_time + 1000)), patch.object(
            runner, "hl_funding_history", return_value=records
        ):
            processed = runner.process_once(state, max_observation_delay_s=10)
        self.assertEqual(len(processed), 1)
        self.assertEqual(processed[0]["hl_funding_records"], 2)
        self.assertAlmostEqual(processed[0]["hl_collect_bps"], 5000.0)

    def test_late_event_is_recorded_without_fabricated_pnl(self):
        state = runner.initialize_state(1000.0, self.snapshot(), {"time": 900_000, "rate": 0.0})
        with patch.object(runner.time, "time", return_value=2000.0), patch.object(
            runner, "binance_funding_history", return_value=[{"time": 1_000_000, "rate": 0.0001}]
        ), patch.object(runner, "market_snapshot") as market:
            processed = runner.process_once(state, max_observation_delay_s=10)
        self.assertEqual(processed, [])
        self.assertEqual(len(state["missed_events"]), 1)
        self.assertEqual(state["last_bn_funding_time_ms"], 1_000_000)
        market.assert_not_called()

    def test_atomic_state_round_trip(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "state.json")
            runner.atomic_write(path, {"paper_only": True})
            self.assertEqual(runner.load_state(path), {"paper_only": True})
            self.assertFalse(os.path.exists(path + ".tmp"))
            with open(path, encoding="utf-8") as handle:
                self.assertTrue(json.load(handle)["paper_only"])


class StatsTests(unittest.TestCase):
    def test_gate_requires_positive_cycle_ci_and_total_exit_pnl(self):
        state = {
            "cycles": [{"incremental_net_bps": 1.0} for _ in range(30)],
            "current_exit_net_bps": 11.0,
            "current_exit_net_usd": 1.1,
            "funding_hl_total_bps": 45.0,
            "funding_bn_total_bps": -15.0,
            "missed_events": [],
        }
        stats = runner.compute_stats(state, 30)
        self.assertTrue(stats["paper_gate_pass"])
        self.assertEqual(stats["decision"], "PAPER_SIGNAL")
        self.assertGreater(stats["incremental_ev_bps_ci95"][0], 0)

    def test_gate_fails_with_missed_event(self):
        state = {
            "cycles": [{"incremental_net_bps": 1.0} for _ in range(30)],
            "current_exit_net_bps": 11.0,
            "current_exit_net_usd": 1.1,
            "funding_hl_total_bps": 45.0,
            "funding_bn_total_bps": -15.0,
            "missed_events": [{"funding_time_ms": 1}],
        }
        self.assertFalse(runner.compute_stats(state, 30)["paper_gate_pass"])


if __name__ == "__main__":
    unittest.main()
