import unittest
from datetime import datetime, timedelta, timezone

from d107_validation_report import (
    bankroll_scenarios,
    build_ledger,
    build_report,
    capacity_scenario,
    horizon_value,
)


BASE = datetime(2026, 7, 17, 12, 0, tzinfo=timezone.utc)


def timestamp(hours=0):
    return (BASE + timedelta(hours=hours)).isoformat()


def buy_event(contract_id, direction, hours=0, buy_price=1.04):
    return {
        "event": "buy_confirmed",
        "timestamp": timestamp(hours),
        "action": "buy_confirmed",
        "contract_id": contract_id,
        "direction": direction,
        "contract_type": direction,
        "stake": 1.0,
        "multiplier": 400,
        "buy_price": buy_price,
        "purchase_time": (BASE + timedelta(hours=hours)).timestamp(),
        "cancellation_fee": 0.04,
        "cancellation_expiry": (BASE + timedelta(hours=hours, minutes=5)).timestamp(),
    }


def observation(contract_id, hours, pnl, direction="MULTUP", source="api", entry=100, current=101):
    return {
        "event": "contract_observation",
        "timestamp": timestamp(hours),
        "action": "contract_observation",
        "contract_id": contract_id,
        "direction": direction,
        "classification": "validated_winner" if pnl > 0 else "validated_loss",
        "pnl_source": source,
        "profit_at_action": pnl,
        "api_profit": pnl,
        "reconstructed_profit": pnl,
        "entry_spot": entry,
        "current_spot": current,
    }


class TestD107ValidationReport(unittest.TestCase):
    def test_lifecycle_and_terminal_net_are_reconstructed(self):
        events = [
            buy_event("loser", "MULTUP"),
            observation("loser", 0.1, -0.10),
            {
                "event": "cancel_confirmed",
                "timestamp": timestamp(0.1),
                "action": "cancelled_loser",
                "contract_id": "loser",
                "sold_for": 1.0,
                "cancellation_fee": 0.04,
                "profit_at_action": -0.10,
                "pnl_source": "api",
                "bid_price_at_action": 0.90,
            },
            buy_event("winner", "MULTDOWN", 1),
            observation("winner", 1.1, 0.40, direction="MULTDOWN", entry=100, current=99),
            {
                "event": "held_winner",
                "timestamp": timestamp(1.1),
                "action": "held_winner",
                "contract_id": "winner",
                "direction": "MULTDOWN",
                "classification": "validated_winner",
                "pnl_source": "api",
                "profit_at_action": 0.40,
            },
        ]
        ledger = build_ledger(events)
        self.assertEqual(ledger["loser"].lifecycle, "closed_loser")
        self.assertAlmostEqual(ledger["loser"].terminal_net_pnl, -0.04)
        self.assertEqual(ledger["winner"].lifecycle, "held_winner")
        self.assertAlmostEqual(ledger["winner"].boundary_pnl, 0.40)

    def test_horizon_uses_observation_and_terminal_before_horizon(self):
        events = [
            buy_event("open", "MULTUP"),
            observation("open", 1.1, 0.25),
            buy_event("closed", "MULTUP", 1),
            observation("closed", 1.1, -0.04),
            {
                "event": "cancel_confirmed",
                "timestamp": timestamp(1.1),
                "action": "cancelled_loser",
                "contract_id": "closed",
                "sold_for": 1.0,
                "cancellation_fee": 0.04,
            },
        ]
        ledger = build_ledger(events)
        open_horizon = horizon_value(ledger["open"], 1)
        closed_horizon = horizon_value(ledger["closed"], 6)
        self.assertEqual(open_horizon["status"], "observed")
        self.assertAlmostEqual(open_horizon["value"], 0.25)
        self.assertEqual(closed_horizon["status"], "terminal_before_horizon")
        self.assertAlmostEqual(closed_horizon["value"], -0.04)

    def test_external_manual_close_is_separate_terminal_outcome(self):
        events = [
            buy_event("manual", "MULTDOWN"),
            observation("manual", 1, 0.50, direction="MULTDOWN", entry=100, current=99),
            {
                "event": "manual_reconciliation",
                "timestamp": timestamp(2),
                "action": "manual_reconciliation",
                "contract_id": "manual",
                "lifecycle_before": "held_winner",
                "terminal_status": "sold",
                "external_close_pnl": 0.45,
            },
        ]
        record = build_ledger(events)["manual"]
        self.assertEqual(record.lifecycle, "closed_external")
        self.assertAlmostEqual(record.external_close_pnl, 0.45)

    def test_bankroll_scenarios_are_arithmetic_not_forecasts(self):
        report = bankroll_scenarios(1000, deployed_pct=0.20, rates=(0.01,))
        row = report["scenarios"][0]
        self.assertEqual(row["required_bankroll"], 100000)
        self.assertEqual(row["required_bankroll_at_deployed_pct"], 500000)
        self.assertEqual(report["cumulative_withdrawal_by_period"]["30"], 30000)

    def test_fixed_v0_capacity_formula(self):
        report = capacity_scenario(1000, max_positions=10, stake=1, multiplier=400)
        self.assertAlmostEqual(report["all_positions_same_direction_move_required_for_target"], 0.25)
        self.assertAlmostEqual(report["estimated_max_deployed_at_buy"], 10.4)

    def test_report_marks_small_sample_as_in_progress(self):
        events = [buy_event("one", "MULTUP"), observation("one", 1.1, 0.10)]
        report = build_report(events, {"unresolved_contracts": []})
        self.assertEqual(report["validation_gates"]["operational"]["status"], "IN_PROGRESS")
        self.assertEqual(report["validation_gates"]["economic"]["status"], "IN_PROGRESS")
        self.assertEqual(report["validation_gates"]["wealth_question"]["status"], "NOT_ASSESSABLE")

    def test_manual_external_pnl_is_excluded_from_strategy_report(self):
        events = [
            buy_event("target", "MULTUP"),
            {
                "event": "sell_confirmed",
                "timestamp": timestamp(1),
                "action": "sold_winner_target",
                "contract_id": "target",
                "sold_for": 3.12,
                "buy_price": 1.04,
                "realized_pnl": 2.08,
            },
            buy_event("manual", "MULTDOWN", 2),
            {
                "event": "manual_reconciliation",
                "timestamp": timestamp(3),
                "action": "manual_reconciliation",
                "contract_id": "manual",
                "external_close_pnl": 4.0,
                "terminal_status": "sold",
            },
        ]
        report = build_report(events, {"unresolved_contracts": []})
        self.assertAlmostEqual(report["realized_contract_net"]["sum"], 2.08)
        self.assertAlmostEqual(report["manual_external_closes"]["pnl_excluded_from_strategy"], 4.0)
        self.assertEqual(report["sell_waves"]["total_sells"], 1)

    def test_sell_waves_group_close_events(self):
        events = [
            buy_event("a", "MULTUP"),
            buy_event("b", "MULTDOWN", 0.01),
            {
                "event": "sell_confirmed", "timestamp": timestamp(1),
                "action": "sold_winner_target", "contract_id": "a",
                "sold_for": 3.12, "buy_price": 1.04, "realized_pnl": 2.08,
            },
            {
                "event": "sell_confirmed", "timestamp": timestamp(1),
                "action": "sold_winner_target", "contract_id": "b",
                "sold_for": 3.12, "buy_price": 1.04, "realized_pnl": 2.08,
            },
        ]
        report = build_report(events, {"unresolved_contracts": []})
        self.assertEqual(report["sell_waves"]["count"], 1)
        self.assertEqual(report["sell_waves"]["waves"][0]["count"], 2)

    def test_report_tracks_direction_and_fee_quotes_separately(self):
        events = [buy_event("up", "MULTUP"), buy_event("down", "MULTDOWN", 1)]
        report = build_report(events, {"cancellation_fees": 0.0, "unresolved_contracts": []})
        self.assertEqual(report["by_direction"]["MULTUP"]["buys"], 1)
        self.assertEqual(report["by_direction"]["MULTDOWN"]["buys"], 1)
        self.assertAlmostEqual(report["cancellation_fee_quotes_total"], 0.08)
        self.assertEqual(report["cancellation_fees_on_cancel_actions"], 0.0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
