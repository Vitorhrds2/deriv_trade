import asyncio
import json
import os
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import early_sell_paired_ab as ab


class AnalyzeTests(unittest.TestCase):
    def make_record(self, treatment_profit, control_profit, triggered=True, sold=True):
        treatment = {}
        if triggered:
            treatment["trigger"] = {"ratio": 1.2}
        if sold:
            treatment["exit"] = "sell"
            treatment["slippage"] = 0.0
            treatment["sell_latency_s"] = 0.2
        return {
            "status": "complete",
            "treatment_profit": treatment_profit,
            "control_profit": control_profit,
            "paired_diff": treatment_profit - control_profit,
            "treatment": treatment,
            "buy_response_gap_s": 0.1,
            "entry_spot_gap_abs": 0.0,
            "expiry_gap_s": 0.0,
        }

    def test_gate_passes_only_with_positive_paired_evidence(self):
        records = [self.make_record(2.0, -1.0) for _ in range(20)]
        stats = ab.analyze(records, 20)
        self.assertTrue(stats["demo_gate_pass"])
        self.assertEqual(stats["decision"], "DEMO_SIGNAL")
        self.assertEqual(stats["attempts"], 20)
        self.assertEqual(stats["status_counts"], {"complete": 20})
        self.assertEqual(stats["valid_pairs"], 20)
        self.assertEqual(stats["treatment_win_rate"], 1.0)
        self.assertEqual(stats["control_win_rate"], 0.0)
        self.assertEqual(stats["paired_treatment_better_rate"], 1.0)
        self.assertEqual(stats["treatment_better_pairs"], 20)
        self.assertEqual(stats["control_better_pairs"], 0)
        self.assertEqual(stats["tied_pairs"], 0)
        self.assertEqual(stats["fill_rate"], 1.0)
        self.assertEqual(stats["mean_sell_latency_s"], 0.2)
        self.assertEqual(stats["maximum_buy_response_gap_s"], 0.1)
        self.assertGreater(stats["treatment_win_rate_wilson_ci95"][0], 0)
        self.assertGreater(stats["paired_diff_ci95"][0], 0)

    def test_gate_fails_without_trigger_volume(self):
        records = [self.make_record(2.0, -1.0, triggered=False, sold=False) for _ in range(20)]
        stats = ab.analyze(records, 20)
        self.assertFalse(stats["demo_gate_pass"])
        self.assertEqual(stats["trigger_rate"], 0.0)
        self.assertEqual(stats["fill_rate"], 0.0)

    def test_gate_fails_below_fill_guardrail(self):
        records = [self.make_record(2.0, -1.0, sold=i < 18) for i in range(20)]
        stats = ab.analyze(records, 20)
        self.assertFalse(stats["demo_gate_pass"])
        self.assertEqual(stats["fill_rate"], 0.9)

    def test_gate_fails_when_treatment_ev_is_not_positive(self):
        records = [self.make_record(-0.1, -1.0) for _ in range(20)]
        stats = ab.analyze(records, 20)
        self.assertFalse(stats["demo_gate_pass"])
        self.assertGreater(stats["paired_diff_ci95"][0], 0)
        self.assertLessEqual(stats["treatment_ev_ci95"][0], 0)


class PersistenceTests(unittest.TestCase):
    def test_jsonl_and_atomic_stats_round_trip(self):
        with tempfile.TemporaryDirectory() as directory:
            results = os.path.join(directory, "results.jsonl")
            stats_path = os.path.join(directory, "stats.json")
            ab.append_record(results, {"attempt": 1, "status": "complete"})
            ab.append_record(results, {"attempt": 2, "status": "timeout"})
            self.assertEqual(len(ab.load_records(results)), 2)
            ab.write_stats(stats_path, {"valid_pairs": 1})
            with open(stats_path, encoding="utf-8") as handle:
                self.assertEqual(json.load(handle)["valid_pairs"], 1)
            self.assertFalse(os.path.exists(stats_path + ".tmp"))

    def test_config_mismatch_is_rejected(self):
        with self.assertRaises(ValueError):
            ab.enforce_config([{"config": {"threshold_ratio": 1.3}}], {"threshold_ratio": 1.2})


class RunPairTests(unittest.IsolatedAsyncioTestCase):
    def args(self):
        return SimpleNamespace(
            symbol="1HZ10V",
            contract_type="CALL",
            duration=15,
            stake=10.0,
            threshold=1.2,
            poll=0.0,
            sell_retry=3.0,
            max_buy_response_gap=2.0,
            max_entry_spot_gap=0.0,
            max_expiry_gap=2.0,
            min_trigger_rate=0.25,
            min_fill_rate=0.95,
            seed=72120,
            expected_account="DOT92167553",
        )

    async def test_executes_sell_with_minimum_price_and_realized_pair(self):
        treatment = {
            "contract_id": 101,
            "buy_price": 10.0,
            "entry_spot": 100.0,
            "buy_sent_epoch": 1.0,
            "buy_received_epoch": 1.1,
        }
        control = {
            "contract_id": 202,
            "buy_price": 10.0,
            "entry_spot": 100.0,
            "buy_sent_epoch": 1.01,
            "buy_received_epoch": 1.11,
        }

        async def fake_poc(client, contract_id):
            if contract_id == 101:
                return {
                    "bid_price": 12.4,
                    "is_valid_to_sell": True,
                    "is_sold": False,
                    "entry_spot": 100.0,
                    "date_expiry": 900,
                }
            return {
                "bid_price": 19.23,
                "is_valid_to_sell": False,
                "is_sold": True,
                "profit": 9.23,
                "entry_spot": 100.0,
                "date_expiry": 900,
            }

        sell_request = AsyncMock(return_value={"sell": {"sold_for": 12.2}})
        with patch.object(ab, "wait_for_empty_portfolio", AsyncMock()), patch.object(
            ab, "buy_pair", AsyncMock(return_value=(treatment, control))
        ), patch.object(ab, "poc", side_effect=fake_poc), patch.object(ab, "request", sell_request):
            record = await ab.run_pair(object(), self.args(), 1)

        self.assertEqual(record["status"], "complete")
        self.assertAlmostEqual(record["treatment_profit"], 2.2)
        self.assertAlmostEqual(record["control_profit"], 9.23)
        self.assertAlmostEqual(record["paired_diff"], -7.03)
        self.assertEqual(sell_request.await_args.args[1]["price"], 12.0)
        self.assertAlmostEqual(record["treatment"]["slippage"], -0.2)

    async def test_no_trigger_holds_both_legs(self):
        treatment = {
            "contract_id": 101,
            "buy_price": 10.0,
            "entry_spot": 100.0,
            "buy_sent_epoch": 1.0,
            "buy_received_epoch": 1.1,
        }
        control = {
            "contract_id": 202,
            "buy_price": 10.0,
            "entry_spot": 100.0,
            "buy_sent_epoch": 1.01,
            "buy_received_epoch": 1.11,
        }

        async def fake_poc(client, contract_id):
            profit = -10.0 if contract_id == 101 else 9.23
            return {
                "bid_price": 0,
                "is_valid_to_sell": False,
                "is_sold": True,
                "profit": profit,
                "entry_spot": 100.0,
                "date_expiry": 900,
            }

        sell_request = AsyncMock()
        with patch.object(ab, "wait_for_empty_portfolio", AsyncMock()), patch.object(
            ab, "buy_pair", AsyncMock(return_value=(treatment, control))
        ), patch.object(ab, "poc", side_effect=fake_poc), patch.object(ab, "request", sell_request):
            record = await ab.run_pair(object(), self.args(), 1)

        self.assertEqual(record["status"], "complete")
        self.assertEqual(record["treatment"]["exit"], "expiry")
        self.assertEqual(record["control"]["exit"], "expiry")
        self.assertAlmostEqual(record["paired_diff"], -19.23)
        sell_request.assert_not_awaited()

    async def test_pair_with_large_response_gap_is_excluded(self):
        treatment = {
            "contract_id": 101,
            "buy_price": 10.0,
            "entry_spot": 100.0,
            "buy_sent_epoch": 1.0,
            "buy_received_epoch": 1.1,
        }
        control = {
            "contract_id": 202,
            "buy_price": 10.0,
            "entry_spot": 100.0,
            "buy_sent_epoch": 1.01,
            "buy_received_epoch": 4.1,
        }

        async def fake_poc(client, contract_id):
            profit = 9.23 if contract_id == 101 else -10.0
            return {"is_sold": True, "profit": profit, "entry_spot": 100.0, "date_expiry": 900}

        with patch.object(ab, "wait_for_empty_portfolio", AsyncMock()), patch.object(
            ab, "buy_pair", AsyncMock(return_value=(treatment, control))
        ), patch.object(ab, "poc", side_effect=fake_poc):
            record = await ab.run_pair(object(), self.args(), 1)

        self.assertEqual(record["status"], "invalid_pair_gap")
        self.assertFalse(record["pair_quality_ok"])
        self.assertEqual(ab.analyze([record], 1)["valid_pairs"], 0)


if __name__ == "__main__":
    unittest.main()
