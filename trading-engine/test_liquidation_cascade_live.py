import json
import os
import tempfile
import unittest

import liquidation_cascade_live as runner


class ParseTests(unittest.TestCase):
    def test_parses_force_order(self):
        message = json.dumps({
            "stream": "btcusdt@forceOrder",
            "data": {
                "e": "forceOrder",
                "E": 1000,
                "o": {"s": "BTCUSDT", "S": "SELL", "ap": "100", "z": "2"},
            },
        })
        event = runner.parse_liquidation(message)
        self.assertEqual(event["direction"], "SHORT")
        self.assertEqual(event["notional_usd"], 200.0)

    def test_ignores_non_liquidation_messages(self):
        self.assertIsNone(runner.parse_liquidation(json.dumps({"data": {"e": "markPriceUpdate"}})))


class CascadeTests(unittest.TestCase):
    def events(self):
        return [
            {
                "event_ms": timestamp,
                "symbol": "BTCUSDT",
                "direction": "SHORT",
                "notional_usd": 1000.0,
            }
            for timestamp in (1000, 5000, 9000)
        ]

    def test_detects_three_events_inside_window(self):
        events = self.events()
        event = {**events[-1], "event_utc": "1970-01-01T00:00:09+00:00"}
        cascade = runner.detect_cascade(events, event, [], 10, 3, 30, 2000)
        self.assertIsNotNone(cascade)
        self.assertEqual(cascade["liquidation_count"], 3)
        self.assertEqual(cascade["liquidation_notional_usd"], 3000.0)

    def test_cooldown_blocks_duplicate_cascade(self):
        events = self.events()
        event = {**events[-1], "event_utc": "1970-01-01T00:00:09+00:00"}
        existing = [{"symbol": "BTCUSDT", "direction": "SHORT", "trigger_ms": 8000}]
        self.assertIsNone(runner.detect_cascade(events, event, existing, 10, 3, 30, 0))

    def test_notional_guardrail_is_enforced(self):
        events = self.events()
        event = {**events[-1], "event_utc": "1970-01-01T00:00:09+00:00"}
        self.assertIsNone(runner.detect_cascade(events, event, [], 10, 3, 30, 4000))


class PnlTests(unittest.TestCase):
    def test_long_uses_ask_to_bid_and_fees(self):
        pnl = runner.paper_pnl("LONG", {"bid": 99, "ask": 100}, {"bid": 101, "ask": 102}, 0.04)
        self.assertEqual(pnl["entry_price"], 100)
        self.assertEqual(pnl["exit_price"], 101)
        self.assertAlmostEqual(pnl["net_pnl_pct"], 0.92)

    def test_short_uses_bid_to_ask_and_fees(self):
        pnl = runner.paper_pnl("SHORT", {"bid": 100, "ask": 101}, {"bid": 98, "ask": 99}, 0.04)
        self.assertEqual(pnl["entry_price"], 100)
        self.assertEqual(pnl["exit_price"], 99)
        self.assertAlmostEqual(pnl["net_pnl_pct"], 0.92)

    def test_settles_each_horizon_once(self):
        state = {
            "liquidations_seen": 3,
            "cascades": [{
                "cascade_id": "x",
                "trigger_ms": 1000,
                "symbol": "BTCUSDT",
                "direction": "LONG",
                "entry_book": {"bid": 99, "ask": 100},
                "resolved_horizons_s": [],
            }],
            "results": [],
        }
        book = lambda symbol: {"bid": 101, "ask": 102, "observed_ms": 31_000}
        first = runner.settle_due(state, 31_000, (30, 60), 0.04, book)
        second = runner.settle_due(state, 31_000, (30, 60), 0.04, book)
        self.assertEqual(len(first), 1)
        self.assertEqual(second, [])
        self.assertEqual(state["cascades"][0]["resolved_horizons_s"], [30])

    def test_late_horizon_is_marked_missed_without_book_lookup(self):
        state = {
            "liquidations_seen": 3,
            "cascades": [{
                "cascade_id": "x",
                "trigger_ms": 1000,
                "symbol": "BTCUSDT",
                "direction": "LONG",
                "entry_book": {"bid": 99, "ask": 100},
                "resolved_horizons_s": [],
            }],
            "results": [],
        }
        calls = []
        result = runner.settle_due(
            state,
            41_000,
            (30,),
            0.04,
            lambda symbol: calls.append(symbol),
            max_delay_s=5,
        )
        self.assertEqual(result[0]["status"], "missed")
        self.assertEqual(calls, [])
        stats = runner.compute_stats(state, (30,), 1)
        self.assertEqual(stats["horizons"]["30"]["n"], 0)
        self.assertEqual(stats["missed_results"], 1)

    def test_stats_gate_uses_ev_lower_bound(self):
        state = {
            "liquidations_seen": 30,
            "cascades": [{} for _ in range(30)],
            "results": [{"horizon_s": 30, "net_pnl_pct": 1.0} for _ in range(30)],
        }
        stats = runner.compute_stats(state, (30,), 30)
        self.assertEqual(stats["decision"], "PAPER_SIGNAL")
        self.assertGreater(stats["horizons"]["30"]["ev_pct_ci95"][0], 0)


class PersistenceTests(unittest.TestCase):
    def test_atomic_state_round_trip(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "state.json")
            runner.atomic_write(path, {"paper_only": True})
            with open(path, encoding="utf-8") as handle:
                self.assertTrue(json.load(handle)["paper_only"])
            self.assertFalse(os.path.exists(path + ".tmp"))


if __name__ == "__main__":
    unittest.main()
