import json
import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

import parallel_oos_monitor as monitor


NOW = datetime(2026, 7, 12, 12, 0, tzinfo=timezone.utc)


def active_service(name):
    return {
        "name": name,
        "active": True,
        "active_state": "active",
        "sub_state": "running",
        "restarts": 0,
        "main_pid": 123,
        "result": "success",
    }


class MonitorTests(unittest.TestCase):
    def write_json(self, base, relative, value):
        path = Path(base) / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value), encoding="utf-8")

    def create_fixtures(self, base, updated_utc=None):
        updated = updated_utc or NOW.isoformat()
        self.write_json(base, "d55/state.json", {"paper_only": True})
        self.write_json(base, "d55/stats.json", {
            "updated_utc": updated,
            "cycles": 1,
            "target_cycles": 30,
            "current_exit_net_bps": -20.0,
            "current_exit_net_usd": -2.0,
            "incremental_ev_bps_ci95": [-1.0, 0.0, 1.0],
            "missed_events": 0,
            "paper_gate_pass": False,
            "decision": "NOT_VALIDATED",
        })
        self.write_json(base, "d36/state.json", {"config": {"paper_only": True}})
        self.write_json(base, "d36/stats.json", {
            "updated_utc": updated,
            "cycles": 4,
            "open": 8,
            "settled": 2,
            "target_settled": 30,
            "settled_clusters": 1,
            "target_clusters": 15,
            "total_pnl_pct": 4.0,
            "total_pnl_usd": 4.0,
            "ev_pct_ci95": [-2.0, 2.0, 6.0],
            "cluster_ev_pct_ci95": [-3.0, 2.0, 7.0],
            "paper_gate_pass": False,
            "decision": "NOT_VALIDATED",
        })
        self.write_json(base, "d34/state.json", {"paper_only": True, "config": {"primary_horizon": 30}})
        self.write_json(base, "d34/stats.json", {
            "updated_utc": updated,
            "liquidations_seen": 12,
            "cascades": 3,
            "resolved_results": 8,
            "missed_results": 0,
            "target_per_horizon": 30,
            "primary_horizon_s": 30,
            "passing_horizons_s": [],
            "horizons": {
                "30": {
                    "n": 2,
                    "total_pnl_pct": 0.5,
                    "ev_pct_ci95": [-0.2, 0.25, 0.7],
                    "win_rate": 0.5,
                    "win_rate_wilson_ci95": [0.1, 0.9],
                }
            },
            "paper_gate_pass": False,
            "decision": "NOT_VALIDATED",
        })

    def test_snapshot_consolidates_independent_units(self):
        with tempfile.TemporaryDirectory() as directory:
            self.create_fixtures(directory)
            snapshot = monitor.build_snapshot(directory, NOW, active_service)
        self.assertEqual(snapshot["health"], "HEALTHY")
        self.assertTrue(snapshot["paper_only"])
        self.assertEqual(snapshot["decision"], "NOT_VALIDATED")
        self.assertEqual(snapshot["runners"]["d55"]["progress"]["observations"], 1)
        self.assertEqual(snapshot["runners"]["d36"]["progress"]["open"], 8)
        self.assertEqual(snapshot["runners"]["d34"]["progress"]["liquidations_seen"], 12)
        self.assertAlmostEqual(snapshot["runners"]["d34"]["progress"]["ratio"], 2 / 30)

    def test_stale_stats_and_inactive_service_degrade_health(self):
        with tempfile.TemporaryDirectory() as directory:
            self.create_fixtures(directory, (NOW - timedelta(hours=2)).isoformat())

            def service(name):
                value = active_service(name)
                if name == "d36-oos-paper.service":
                    value["active"] = False
                return value

            snapshot = monitor.build_snapshot(directory, NOW, service)
        self.assertEqual(snapshot["health"], "DEGRADED")
        self.assertFalse(snapshot["runners"]["d55"]["fresh"])
        self.assertIn("service: inativo", snapshot["runners"]["d36"]["errors"])

    def test_missing_state_is_degraded_and_does_not_invent_paper_lock(self):
        with tempfile.TemporaryDirectory() as directory:
            self.create_fixtures(directory)
            os.remove(Path(directory) / "d34/state.json")
            snapshot = monitor.build_snapshot(directory, NOW, active_service)
        self.assertEqual(snapshot["health"], "DEGRADED")
        self.assertFalse(snapshot["paper_only"])
        self.assertFalse(snapshot["runners"]["d34"]["paper_only"])
        self.assertTrue(any(error.startswith("state:") for error in snapshot["runners"]["d34"]["errors"]))

    def test_paper_signal_is_reported_without_mixing_pnl_units(self):
        with tempfile.TemporaryDirectory() as directory:
            self.create_fixtures(directory)
            stats_path = Path(directory) / "d55/stats.json"
            stats = json.loads(stats_path.read_text(encoding="utf-8"))
            stats["paper_gate_pass"] = True
            stats["decision"] = "PAPER_SIGNAL"
            stats_path.write_text(json.dumps(stats), encoding="utf-8")
            snapshot = monitor.build_snapshot(directory, NOW, active_service)
        self.assertEqual(snapshot["decision"], "PAPER_SIGNAL")
        self.assertEqual(snapshot["signals"], ["d55"])
        self.assertIn("current_exit_net_bps", snapshot["runners"]["d55"]["pnl"])
        self.assertNotIn("total_pnl", snapshot)

    def test_stale_gate_is_not_promoted_to_current_signal(self):
        with tempfile.TemporaryDirectory() as directory:
            self.create_fixtures(directory, (NOW - timedelta(hours=2)).isoformat())
            stats_path = Path(directory) / "d55/stats.json"
            stats = json.loads(stats_path.read_text(encoding="utf-8"))
            stats["paper_gate_pass"] = True
            stats["decision"] = "PAPER_SIGNAL"
            stats_path.write_text(json.dumps(stats), encoding="utf-8")
            snapshot = monitor.build_snapshot(directory, NOW, active_service)
        self.assertEqual(snapshot["decision"], "NOT_VALIDATED")
        self.assertEqual(snapshot["signals"], [])

    def test_snapshot_persistence_is_atomic_and_append_only(self):
        with tempfile.TemporaryDirectory() as directory:
            self.create_fixtures(directory)
            snapshot = monitor.build_snapshot(directory, NOW, active_service)
            current = Path(directory) / "monitor/current.json"
            history = Path(directory) / "monitor/history.jsonl"
            monitor.atomic_write(current, snapshot)
            monitor.append_jsonl(history, snapshot)
            monitor.append_jsonl(history, snapshot)
            self.assertEqual(json.loads(current.read_text(encoding="utf-8"))["health"], "HEALTHY")
            self.assertEqual(len(history.read_text(encoding="utf-8").splitlines()), 2)
            self.assertFalse(any(Path(directory).rglob("*.tmp")))


if __name__ == "__main__":
    unittest.main()
