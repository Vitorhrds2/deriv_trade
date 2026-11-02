import json
import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

import early_sell_status_monitor as monitor


NOW = datetime(2026, 7, 12, 12, 10, tzinfo=timezone.utc)


class StatusMonitorTests(unittest.TestCase):
    def write(self, root, relative, value):
        path = Path(root) / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(value, encoding="utf-8")
        os.utime(path, (NOW.timestamp(), NOW.timestamp()))
        return path

    def fixtures(self, root):
        campaign = Path(root) / "campaign"
        ab_dir = Path(root) / "ab"
        oos = Path(root) / "oos.json"
        self.write(campaign, "manifest.txt", "target_valid_sessions=4\ncommand=python early_sell_test.py --trials 20\n")
        self.write(campaign, "status.tsv", "attempt\tvalid_session\tstatus\n1\t1\tVALID\n")
        log = "Conta: DOT92167553 -> OK DEMO\n" + "\n".join(
            f"[{index}] profit_hold=$+1.0000" for index in range(3)
        ) + "\n[3] sample=0 bid=$1\n"
        self.write(campaign, "attempt_02.log", log)
        self.write(ab_dir, "manifest.txt", "pairs=20\naccount=DOT92167553 demo-only\n")
        self.write(oos.parent, oos.name, json.dumps({
            "observed_utc": NOW.isoformat(),
            "health": "HEALTHY",
            "paper_only": True,
            "decision": "NOT_VALIDATED",
            "signals": [],
        }))
        return campaign, ab_dir, oos

    def probe(self, repeat=True, ab=True):
        def value(fragment, excludes=()):
            if fragment == "repeat_campaign.sh":
                return [101] if repeat else []
            return [202] if ab else []
        return value

    def test_running_repeat_and_waiting_ab_are_healthy(self):
        with tempfile.TemporaryDirectory() as root:
            campaign, ab_dir, oos = self.fixtures(root)
            snapshot = monitor.build_snapshot(campaign, ab_dir, oos, NOW, self.probe())
        self.assertEqual(snapshot["health"], "HEALTHY")
        self.assertTrue(snapshot["demo_paper_only"])
        self.assertEqual(snapshot["pipeline_stage"], "repeat")
        self.assertEqual(snapshot["campaign"]["valid_sessions"], 1)
        self.assertEqual(snapshot["campaign"]["completed_trials_current_attempt"], 3)
        self.assertEqual(snapshot["campaign"]["active_trial"], 3)
        self.assertEqual(snapshot["paired_ab"]["stage"], "waiting")

    def test_complete_repeat_and_running_ab_report_live_stats(self):
        with tempfile.TemporaryDirectory() as root:
            campaign, ab_dir, oos = self.fixtures(root)
            with open(campaign / "manifest.txt", "a", encoding="utf-8") as handle:
                handle.write("valid_sessions=4\nattempts=4\n")
            self.write(ab_dir, "run.log", "account validated=True\n")
            with open(ab_dir / "manifest.txt", "a", encoding="utf-8") as handle:
                handle.write("started_utc=2026-07-12T12:00:00Z\n")
            self.write(ab_dir, "stats.json", json.dumps({
                "updated_utc": NOW.isoformat(),
                "attempts": 5,
                "valid_pairs": 5,
                "target_pairs": 20,
                "decision": "NOT_VALIDATED",
                "treatment_ev_ci95": [-1, 1, 3],
                "control_ev_ci95": [-2, 0, 2],
                "paired_diff_ci95": [-1, 1, 4],
            }))
            snapshot = monitor.build_snapshot(campaign, ab_dir, oos, NOW, self.probe())
        self.assertEqual(snapshot["health"], "HEALTHY")
        self.assertEqual(snapshot["pipeline_stage"], "paired_ab")
        self.assertEqual(snapshot["paired_ab"]["stage"], "running")
        self.assertEqual(snapshot["paired_ab"]["valid_pairs"], 5)

    def test_waiter_transition_after_repeat_is_healthy(self):
        with tempfile.TemporaryDirectory() as root:
            campaign, ab_dir, oos = self.fixtures(root)
            with open(campaign / "manifest.txt", "a", encoding="utf-8") as handle:
                handle.write("valid_sessions=4\n")
            snapshot = monitor.build_snapshot(campaign, ab_dir, oos, NOW, self.probe())
        self.assertEqual(snapshot["health"], "HEALTHY")
        self.assertEqual(snapshot["pipeline_stage"], "paired_ab")
        self.assertEqual(snapshot["paired_ab"]["stage"], "starting")

    def test_completed_ab_surfaces_gate_and_decision(self):
        with tempfile.TemporaryDirectory() as root:
            campaign, ab_dir, oos = self.fixtures(root)
            with open(campaign / "manifest.txt", "a", encoding="utf-8") as handle:
                handle.write("valid_sessions=4\n")
            self.write(ab_dir, "stats.json", json.dumps({
                "updated_utc": NOW.isoformat(),
                "valid_pairs": 20,
                "target_pairs": 20,
                "demo_gate_pass": True,
                "decision": "DEMO_SIGNAL",
                "treatment_total_pnl": 25.0,
                "control_total_pnl": -5.0,
            }))
            snapshot = monitor.build_snapshot(campaign, ab_dir, oos, NOW, self.probe(repeat=False, ab=False))
        self.assertEqual(snapshot["pipeline_stage"], "complete")
        self.assertEqual(snapshot["paired_ab"]["stage"], "complete")
        self.assertEqual(snapshot["paired_ab"]["decision"], "DEMO_SIGNAL")
        self.assertTrue(snapshot["paired_ab"]["demo_gate_pass"])

    def test_missing_waiter_degrades_snapshot(self):
        with tempfile.TemporaryDirectory() as root:
            campaign, ab_dir, oos = self.fixtures(root)
            snapshot = monitor.build_snapshot(campaign, ab_dir, oos, NOW, self.probe(ab=False))
        self.assertEqual(snapshot["health"], "DEGRADED")
        self.assertEqual(snapshot["paired_ab"]["stage"], "missing_waiter")

    def test_stale_campaign_log_degrades_snapshot(self):
        with tempfile.TemporaryDirectory() as root:
            campaign, ab_dir, oos = self.fixtures(root)
            stale = (NOW - timedelta(minutes=25)).timestamp()
            os.utime(campaign / "attempt_02.log", (stale, stale))
            snapshot = monitor.build_snapshot(campaign, ab_dir, oos, NOW, self.probe())
        self.assertEqual(snapshot["health"], "DEGRADED")
        self.assertFalse(snapshot["campaign"]["fresh"])

    def test_atomic_current_and_append_only_history(self):
        with tempfile.TemporaryDirectory() as root:
            campaign, ab_dir, oos = self.fixtures(root)
            snapshot = monitor.build_snapshot(campaign, ab_dir, oos, NOW, self.probe())
            current = Path(root) / "state/current.json"
            history = Path(root) / "state/history.jsonl"
            monitor.atomic_write(current, snapshot)
            monitor.append_jsonl(history, snapshot)
            monitor.append_jsonl(history, snapshot)
            self.assertEqual(json.loads(current.read_text(encoding="utf-8"))["health"], "HEALTHY")
            self.assertEqual(len(history.read_text(encoding="utf-8").splitlines()), 2)
            self.assertFalse(any(Path(root).rglob("*.tmp")))


if __name__ == "__main__":
    unittest.main()
