import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import patch

import iv_anomaly_oos_runner as runner


class RunnerTests(unittest.TestCase):
    def args(self, max_positions=10, max_entries=2):
        return SimpleNamespace(
            threshold_iv=3.0,
            reversion_iv=1.0,
            position_usd=100.0,
            max_positions=max_positions,
            max_entries_per_cycle=max_entries,
            max_hold_hours=168.0,
        )

    def option(self, instrument="BTC-30DEC26-100000-C", iv=20.0, bid=0.11, ask=0.12):
        return {
            "currency": "BTC",
            "instrument": instrument,
            "type": "C",
            "strike": 100000.0,
            "expiry_str": "30DEC26",
            "expiry_date": datetime(2026, 12, 30, tzinfo=timezone.utc),
            "iv": iv,
            "bid": bid,
            "ask": ask,
            "mid": (bid + ask) / 2,
            "underlying_price": 100.0,
            "spread_pct": (ask - bid) / ((ask + bid) / 2) * 100,
            "oi": 100.0,
            "volume": 10.0,
            "min_trade_amount": 0.1,
        }

    def market(self, options=None):
        options = options or []
        return {
            "BTC": {"all": {item["instrument"]: item for item in options}, "liquid": options, "surface": {}},
            "ETH": {"all": {}, "liquid": [], "surface": {}},
        }

    def test_settlement_uses_exit_bid_and_both_side_fees(self):
        now = datetime(2026, 7, 12, tzinfo=timezone.utc)
        trade = {
            "entry_time": (now - timedelta(hours=1)).isoformat(),
            "entry_price_crypto": 0.10,
            "entry_underlying": 100.0,
            "quantity": 10.0,
        }
        option = self.option(bid=0.11, ask=0.13)
        runner.settle_trade(trade, option, 20.0, now, "reversion")
        self.assertEqual(trade["exit_price_crypto"], 0.11)
        self.assertAlmostEqual(trade["entry_value_usd"], 100.0)
        self.assertAlmostEqual(trade["exit_value_usd"], 110.0)
        self.assertAlmostEqual(trade["fees_usd"], 0.6)
        self.assertAlmostEqual(trade["pnl_usd"], 9.4)

    def test_option_fee_is_capped_at_twelve_point_five_percent_of_premium(self):
        self.assertAlmostEqual(runner.option_fee_usd(0.001, 100.0, 10.0), 0.125)
        self.assertAlmostEqual(runner.option_fee_usd(0.10, 100.0, 10.0), 0.3)

    def test_global_position_limit_is_enforced(self):
        now = datetime(2026, 7, 12, tzinfo=timezone.utc)
        existing = {
            "currency": "BTC",
            "instrument": "EXISTING",
            "entry_time": now.isoformat(),
            "status": "open",
        }
        state = {"trades": [existing], "cycles": 0}
        option = self.option()
        with patch.object(runner, "option_fair_iv", return_value=25.0):
            result = runner.run_cycle(state, self.args(max_positions=1), now=now, market=self.market([option]))
        self.assertEqual(result["entered"], [])
        self.assertEqual(len(state["trades"]), 1)

    def test_duplicate_instrument_is_not_reentered(self):
        now = datetime(2026, 7, 12, tzinfo=timezone.utc)
        option = self.option()
        existing = {
            "currency": "BTC",
            "instrument": option["instrument"],
            "entry_time": now.isoformat(),
            "status": "open",
        }
        state = {"trades": [existing], "cycles": 0}
        with patch.object(runner, "option_fair_iv", return_value=25.0):
            result = runner.run_cycle(state, self.args(), now=now, market=self.market([option]))
        self.assertEqual(result["candidate_count"], 0)
        self.assertEqual(len(state["trades"]), 1)

    def test_entry_is_normalized_to_position_usd(self):
        now = datetime(2026, 7, 12, tzinfo=timezone.utc)
        option = self.option(iv=20.0, bid=0.09, ask=0.10)
        with patch.object(runner, "compute_vega", return_value=1.0):
            candidate = runner.make_candidate(option, 25.0, 100.0, now)
        self.assertAlmostEqual(candidate["entry_value_usd"], 100.0)
        self.assertEqual(candidate["entry_price_crypto"], option["ask"])

    def test_entry_below_minimum_trade_amount_is_rejected(self):
        now = datetime(2026, 7, 12, tzinfo=timezone.utc)
        option = self.option(iv=20.0, bid=0.09, ask=0.10)
        option["min_trade_amount"] = 20.0
        with patch.object(runner, "compute_vega", return_value=1.0):
            self.assertIsNone(runner.make_candidate(option, 25.0, 100.0, now))

    def test_stats_gate_requires_positive_lower_confidence_bound(self):
        state = {
            "cycles": 30,
            "trades": [
                {
                    "status": "settled",
                    "pnl_pct": 1.0,
                    "pnl_usd": 1.0,
                    "entry_cycle": index,
                    "entry_time": f"cycle-{index}",
                }
                for index in range(30)
            ],
        }
        stats = runner.compute_stats(state, 30, 15)
        self.assertTrue(stats["paper_gate_pass"])
        self.assertGreater(stats["ev_pct_ci95"][0], 0)
        self.assertGreater(stats["cluster_ev_pct_ci95"][0], 0)

    def test_atomic_state_round_trip(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "state.json")
            runner.atomic_write(path, {"paper_only": True})
            self.assertEqual(runner.load_state(path), {"paper_only": True})
            self.assertFalse(os.path.exists(path + ".tmp"))


if __name__ == "__main__":
    unittest.main()
