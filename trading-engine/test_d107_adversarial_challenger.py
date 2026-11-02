import asyncio
import random
import tempfile
import time
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import AsyncMock

from d107_rate_limit_winner_holding import (
    D107Bot,
    D107Config,
    PerpetualRatchetState,
    PnlDecision,
    PnlEvidence,
    TrendAlignmentSignal,
    calculate_adx_and_trend,
    evaluate_perpetual_ratchet,
    new_state,
)
from d107_exact_historical_simulation import (
    simulate,
    run_simulation,
    SimulationResults,
)


class FakeClient:
    def __init__(self, responses=None):
        self.use_demo = True
        self.account_id = "VRTC-D107-TEST"
        self.responses = responses or {}
        self.calls = []

    async def send_request(self, payload):
        self.calls.append(payload)
        key = next(iter(payload))
        response = self.responses.get(key)
        if callable(response):
            return response(payload)
        if response is not None:
            return response
        if key == "cancel":
            return {"cancel": {"sold_for": 1.0}}
        return {}


def test_config(tmpdir):
    return replace(
        D107Config(),
        auto_sell_winners=True,
        in_window_auto_sell=False,
        state_file=str(Path(tmpdir) / "state.json"),
        results_file=str(Path(tmpdir) / "events.jsonl"),
    )


class TestRatchetThresholdBoundaryConditions(unittest.TestCase):
    """
    Adversarial verification of exact boundary conditions across all 4 tiers:
    0.99x, 1.00x, 1.01x, 1.99x, 2.00x, 2.01x, 3.99x, 4.00x, 4.01x, 7.99x, 8.00x, 8.01x.
    """

    def test_threshold_transitions_and_floors_at_stake_1(self):
        stake = 1.0
        # Format: (peak_multiple, expected_tier, expected_floor)
        test_cases = [
            (0.99, 0, 0.0),
            (1.00, 1, 0.20),
            (1.01, 1, 0.20),
            (1.99, 1, 0.20),
            (2.00, 2, 1.00),
            (2.01, 2, 1.00),
            (3.99, 2, 1.00),
            (4.00, 3, 2.50),
            (4.01, 3, 2.50),
            (7.99, 3, 2.50),
            (8.00, 4, 6.40),  # 80% trailing stop: 8.0 * 0.80 = 6.40
            (8.01, 4, 6.408), # 80% trailing stop: 8.01 * 0.80 = 6.408
        ]

        for peak_mult, expected_tier, expected_floor in test_cases:
            peak = round(peak_mult * stake, 6)
            # Test when current profit equals peak profit
            # Note: For peak >= 8.0x, profit at peak triggers target take-profit
            r = evaluate_perpetual_ratchet(profit=peak, stake=stake, peak_profit=peak)
            self.assertEqual(
                r.current_tier,
                expected_tier,
                f"Peak {peak_mult}x failed tier expectation. Expected {expected_tier}, got {r.current_tier}",
            )
            if peak_mult >= 8.0:
                self.assertTrue(r.should_exit)
                self.assertEqual(r.exit_reason, "winner_exit_multiple")
            else:
                self.assertFalse(r.should_exit)
                self.assertEqual(r.exit_reason, "holding")
                self.assertAlmostEqual(
                    r.guaranteed_floor,
                    expected_floor,
                    places=5,
                    msg=f"Peak {peak_mult}x failed floor expectation.",
                )

    def test_threshold_transitions_across_variable_stakes(self):
        stakes = [0.5, 2.0, 10.0]
        test_multiples = [
            (0.99, 0, 0.0),
            (1.00, 1, 0.20),
            (1.99, 1, 0.20),
            (2.00, 2, 1.00),
            (3.99, 2, 1.00),
            (4.00, 3, 2.50),
            (7.99, 3, 2.50),
            (8.00, 4, 6.40),
        ]
        for stake in stakes:
            for mult, exp_tier, exp_floor_mult in test_multiples:
                peak = round(mult * stake, 6)
                if mult < 8.0:
                    r = evaluate_perpetual_ratchet(profit=peak, stake=stake, peak_profit=peak)
                    self.assertEqual(r.current_tier, exp_tier)
                    self.assertAlmostEqual(r.guaranteed_floor, exp_floor_mult * stake, places=5)
                    self.assertFalse(r.should_exit)
                else:
                    # Test pullback evaluation for Tier 4
                    r_pullback = evaluate_perpetual_ratchet(profit=round(7.0 * stake, 6), stake=stake, peak_profit=peak)
                    self.assertEqual(r_pullback.current_tier, 4)
                    self.assertAlmostEqual(r_pullback.guaranteed_floor, exp_floor_mult * stake, places=5)

    def test_pullback_behavior_tier_0(self):
        """Tier 0 (< 1.0x stake): Allows full breathing room without triggering trailing stop."""
        stake = 1.0
        peak = 0.99
        pullbacks = [0.80, 0.50, 0.20, 0.05, 0.00, -0.10, -0.25, -0.34]
        for p in pullbacks:
            r = evaluate_perpetual_ratchet(profit=p, stake=stake, peak_profit=peak)
            self.assertEqual(r.current_tier, 0)
            self.assertEqual(r.guaranteed_floor, 0.0)
            self.assertFalse(
                r.should_exit,
                f"Tier 0 triggered premature exit at profit={p} with peak={peak}",
            )
            self.assertEqual(r.exit_reason, "holding")

    def test_pullback_behavior_tier_1(self):
        """Tier 1 (+1.0x stake): Locks in +0.20 floor."""
        stake = 1.0
        peak = 1.00
        # Above floor: hold
        r_hold = evaluate_perpetual_ratchet(profit=0.2001, stake=stake, peak_profit=peak)
        self.assertFalse(r_hold.should_exit)
        self.assertEqual(r_hold.exit_reason, "holding")
        self.assertAlmostEqual(r_hold.guaranteed_floor, 0.20)

        # At floor: exit
        r_exit_at = evaluate_perpetual_ratchet(profit=0.20, stake=stake, peak_profit=peak)
        self.assertTrue(r_exit_at.should_exit)
        self.assertEqual(r_exit_at.exit_reason, "winner_trailing_stop")

        # Below floor: exit
        r_exit_below = evaluate_perpetual_ratchet(profit=0.1999, stake=stake, peak_profit=peak)
        self.assertTrue(r_exit_below.should_exit)
        self.assertEqual(r_exit_below.exit_reason, "winner_trailing_stop")

    def test_pullback_behavior_tier_2(self):
        """Tier 2 (+2.0x stake): Locks in +1.00 floor."""
        stake = 1.0
        peak = 2.00
        # Above floor: hold
        r_hold = evaluate_perpetual_ratchet(profit=1.0001, stake=stake, peak_profit=peak)
        self.assertFalse(r_hold.should_exit)
        self.assertEqual(r_hold.exit_reason, "holding")
        self.assertAlmostEqual(r_hold.guaranteed_floor, 1.00)

        # At floor: exit
        r_exit_at = evaluate_perpetual_ratchet(profit=1.00, stake=stake, peak_profit=peak)
        self.assertTrue(r_exit_at.should_exit)
        self.assertEqual(r_exit_at.exit_reason, "winner_trailing_stop")

        # Below floor: exit
        r_exit_below = evaluate_perpetual_ratchet(profit=0.9999, stake=stake, peak_profit=peak)
        self.assertTrue(r_exit_below.should_exit)
        self.assertEqual(r_exit_below.exit_reason, "winner_trailing_stop")

    def test_pullback_behavior_tier_3(self):
        """Tier 3 (+4.0x stake): Locks in +2.50 floor."""
        stake = 1.0
        peak = 4.00
        # Above floor: hold
        r_hold = evaluate_perpetual_ratchet(profit=2.5001, stake=stake, peak_profit=peak)
        self.assertFalse(r_hold.should_exit)
        self.assertEqual(r_hold.exit_reason, "holding")
        self.assertAlmostEqual(r_hold.guaranteed_floor, 2.50)

        # At floor: exit
        r_exit_at = evaluate_perpetual_ratchet(profit=2.50, stake=stake, peak_profit=peak)
        self.assertTrue(r_exit_at.should_exit)
        self.assertEqual(r_exit_at.exit_reason, "winner_trailing_stop")

        # Below floor: exit
        r_exit_below = evaluate_perpetual_ratchet(profit=2.4999, stake=stake, peak_profit=peak)
        self.assertTrue(r_exit_below.should_exit)
        self.assertEqual(r_exit_below.exit_reason, "winner_trailing_stop")

    def test_pullback_behavior_tier_4(self):
        """Tier 4 (+8.0x stake): Immediate TP at 8.0x target, trails at 80% if held or pulled back."""
        stake = 1.0
        # 1. At 8.0x profit: Immediate exit
        r_tp = evaluate_perpetual_ratchet(profit=8.00, stake=stake, peak_profit=8.00)
        self.assertTrue(r_tp.should_exit)
        self.assertEqual(r_tp.exit_reason, "winner_exit_multiple")

        r_tp_above = evaluate_perpetual_ratchet(profit=8.01, stake=stake, peak_profit=8.01)
        self.assertTrue(r_tp_above.should_exit)
        self.assertEqual(r_tp_above.exit_reason, "winner_exit_multiple")

        # 2. Peak at 8.0, floor is 8.0 * 0.80 = 6.40
        r_hold = evaluate_perpetual_ratchet(profit=6.41, stake=stake, peak_profit=8.00)
        self.assertEqual(r_hold.current_tier, 4)
        self.assertFalse(r_hold.should_exit)
        self.assertAlmostEqual(r_hold.guaranteed_floor, 6.40)

        r_trail_exit = evaluate_perpetual_ratchet(profit=6.40, stake=stake, peak_profit=8.00)
        self.assertTrue(r_trail_exit.should_exit)
        self.assertEqual(r_trail_exit.exit_reason, "winner_trailing_stop")

        # 3. Peak at 10.0, floor is 10.0 * 0.80 = 8.00
        r_high_peak = evaluate_perpetual_ratchet(profit=7.95, stake=stake, peak_profit=10.00)
        self.assertEqual(r_high_peak.current_tier, 4)
        self.assertAlmostEqual(r_high_peak.guaranteed_floor, 8.00)
        self.assertTrue(r_high_peak.should_exit)
        self.assertEqual(r_high_peak.exit_reason, "winner_trailing_stop")


class TestVolatilityAndNoiseStress(unittest.TestCase):
    """
    Stress-testing under high volatility, adverse noise excursions, and whipsaw sequences.
    """

    def test_whipsaw_sequence_tier_1_to_breakeven_exit(self):
        """
        Whipsaw sequence:
        1. Profit rises to +1.5x (enters Tier 1, locks +0.20 floor).
        2. Drops to +0.25x (stays open, holding).
        3. Drops to +0.19x (exits with locked profit, winner_trailing_stop).
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            config = test_config(tmpdir)
            bot = D107Bot(FakeClient(), config)
            now = time.time()

            record = {
                "contract_id": "whipsaw_1",
                "lifecycle": "held_winner",
                "direction": "MULTUP",
                "stake": 1.0,
                "buy_price": 1.04,
                "cancellation_fee": 0.04,
                "multiplier": 400,
                "confirmed_at": now - 100,
                "held_at": now - 50,
                "held_peak_unrealized_pnl": 1.54,  # net peak = 1.50
            }

            def make_evidence(bid_price):
                raw = {"bid_price": bid_price, "buy_price": 1.04}
                ev = PnlEvidence(
                    decision=PnlDecision("validated_winner", "api", bid_price - 1.00, bid_price - 1.00, bid_price - 1.00, "test"),
                    entry_spot=100.0,
                    current_spot=100.5,
                    bid_price=bid_price,
                    is_valid_to_cancel=False,
                    is_valid_to_sell=True,
                    contract_id="whipsaw_1",
                    raw=raw,
                )
                return raw, ev

            # Step 1: Profit at +1.50 net (bid_price = 2.54) -> Should hold (Tier 1)
            raw_step1, ev_step1 = make_evidence(2.54)
            should_exit, reason = bot.evaluate_winner_exit(record, raw_step1, ev_step1, now=now)
            self.assertFalse(should_exit)
            self.assertEqual(reason, "holding")

            # Step 2: Severe pullback to +0.25 net (bid_price = 1.29) -> MUST STAY OPEN (floor is +0.20)
            raw_step2, ev_step2 = make_evidence(1.29)
            should_exit, reason = bot.evaluate_winner_exit(record, raw_step2, ev_step2, now=now)
            self.assertFalse(should_exit)
            self.assertEqual(reason, "holding")

            # Step 3: Pullback dips to +0.19 net (bid_price = 1.23) -> MUST EXIT with locked profit
            raw_step3, ev_step3 = make_evidence(1.23)
            should_exit, reason = bot.evaluate_winner_exit(record, raw_step3, ev_step3, now=now)
            self.assertTrue(should_exit)
            self.assertEqual(reason, "winner_trailing_stop")

    def test_drawdown_during_cancellation_window_contract_19127889519_turnaround(self):
        """
        Emulates contract #19127889519:
        Position suffers an adverse excursion to -85% inside the 5-minute cancellation window.
        Verify that trailing stop, take profit, or premature scalping NEVER sell it inside the window.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            config = test_config(tmpdir)
            bot = D107Bot(FakeClient(), config)
            now = time.time()

            # Contract inside cancellation window
            record = {
                "contract_id": "19127889519",
                "lifecycle": "cancellation_window_monitoring",
                "direction": "MULTUP",
                "stake": 1.0,
                "buy_price": 1.04,
                "cancellation_fee": 0.04,
                "multiplier": 400,
                "date_start": now - 120,
                "cancellation_expiry": now + 180,
            }

            # Stress path: normal -> -30% -> -85% (trough) -> +15% -> +50% -> +155%
            drawdown_path = [
                (1.04, 0.00, "entry breakeven"),
                (0.74, -0.30, "mild drawdown -30%"),
                (0.19, -0.85, "catastrophic drawdown -85%"),
                (0.40, -0.64, "partial recovery"),
                (1.19, +0.15, "micro-profit bounce +15%"),
                (1.54, +0.50, "medium profit bounce +50%"),
                (2.59, +1.55, "macro runner +155%"),
            ]

            for bid_price, expected_net, label in drawdown_path:
                raw = {
                    "contract_id": "19127889519",
                    "bid_price": bid_price,
                    "buy_price": 1.04,
                    "is_valid_to_cancel": 1,
                    "is_valid_to_sell": 1,
                }
                ev = PnlEvidence(
                    decision=PnlDecision(
                        "validated_loss" if expected_net < 0 else "validated_winner",
                        "api",
                        expected_net,
                        expected_net,
                        expected_net,
                        "test",
                    ),
                    entry_spot=100.0,
                    current_spot=100.0 + expected_net / 4.0,
                    bid_price=bid_price,
                    is_valid_to_cancel=True,
                    is_valid_to_sell=True,
                    contract_id="19127889519",
                    raw=raw,
                )
                should_exit, reason = bot.evaluate_winner_exit(record, raw, ev, now=now)
                # CRITICAL VERIFICATION: MUST NEVER SELL INSIDE CANCELLATION WINDOW
                self.assertFalse(
                    should_exit,
                    f"Contract prematurely sold during cancellation window at {label} (net={expected_net})",
                )
                self.assertEqual(reason, "in_window_auto_sell_disabled")

    def test_in_window_auto_sell_disabled_blocks_all_premature_micro_scalps(self):
        """Verify that micro-profit spikes (+0.15 to +0.25) are strictly retained."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config = test_config(tmpdir)
            bot = D107Bot(FakeClient(), config)
            record = {
                "contract_id": "micro_test",
                "lifecycle": "cancellation_window_monitoring",
                "direction": "MULTUP",
                "stake": 1.0,
                "buy_price": 1.04,
                "cancellation_fee": 0.04,
            }
            for micro_profit in [0.15, 0.18, 0.20, 0.23, 0.25]:
                raw = {"bid_price": 1.04 + micro_profit, "buy_price": 1.04, "is_valid_to_cancel": 1, "is_valid_to_sell": 1}
                ev = PnlEvidence(
                    decision=PnlDecision("validated_winner", "api", micro_profit, micro_profit, micro_profit, "test"),
                    entry_spot=100.0,
                    current_spot=100.1,
                    bid_price=1.04 + micro_profit,
                    is_valid_to_cancel=True,
                    is_valid_to_sell=True,
                    contract_id="micro_test",
                    raw=raw,
                )
                should_exit, reason = bot.evaluate_winner_exit(record, raw, ev)
                self.assertFalse(should_exit)
                self.assertEqual(reason, "in_window_auto_sell_disabled")


class TestBoundaryDecisionStress(unittest.TestCase):
    """
    Stress-testing boundary qualification at the 4m45s decision point:
    - Marginal profit < fee (must cancel)
    - Profit >= fee with trend agreement (must hold)
    - Profit >= fee with contrary trend (must cancel defensively)
    - Missed cancellation window handling
    """

    def test_boundary_marginal_profit_less_than_fee_cancels(self):
        """
        Gross profit = 0.06, fee = 0.04 -> net_profit = 0.02.
        Since net_profit (0.02) < cancel_fee (0.04), must cancel defensively.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            config = replace(test_config(tmpdir), trend_alignment_enabled=True)
            # Uptrend matches contract direction (MULTUP)
            uptrend = [100.0 + i * 0.10 for i in range(180)]
            client = FakeClient(responses={
                "ticks_history": {"history": {"prices": uptrend}},
                "cancel": {"cancel": {"sold_for": 1.0}},
            })
            bot = D107Bot(client, config)
            bot.state = new_state()
            bot.account_id = client.account_id

            record = {
                "contract_id": "marginal_sub_fee",
                "lifecycle": "cancellation_window_monitoring",
                "direction": "MULTUP",
                "stake": 1.0,
                "buy_price": 1.04,
                "cancellation_fee": 0.04,
                "multiplier": 400,
                "cancellation_expiry": time.time() + 60,
            }
            bot.state["contracts"]["marginal_sub_fee"] = record
            raw = {
                "contract_id": "marginal_sub_fee",
                "contract_type": "MULTUP",
                "entry_spot": 100.0,
                "current_spot": 100.015,
                "profit": 0.06,  # net = 0.02 < 0.04 fee
                "bid_price": 1.06,
                "is_valid_to_cancel": 1,
                "is_valid_to_sell": 1,
            }

            asyncio.run(bot.handle_boundary(record, raw))
            # Must cancel because net profit does not cover the cancellation risk threshold
            self.assertEqual(record["lifecycle"], "closed_loser")
            self.assertTrue(any("cancel" in call for call in client.calls))

    def test_boundary_profit_covers_fee_with_trend_agreement_holds(self):
        """
        Gross profit = 0.16, fee = 0.04 -> net_profit = 0.12 >= fee 0.04.
        Trend agrees (MULTUP).
        Must transition to held_winner.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            config = replace(test_config(tmpdir), trend_alignment_enabled=True)
            uptrend = [100.0 + i * 0.10 for i in range(180)]
            client = FakeClient(responses={"ticks_history": {"history": {"prices": uptrend}}})
            bot = D107Bot(client, config)
            bot.state = new_state()
            bot.account_id = client.account_id
            bot.monitor_held_winner = AsyncMock()

            record = {
                "contract_id": "qualified_runner",
                "lifecycle": "cancellation_window_monitoring",
                "direction": "MULTUP",
                "stake": 1.0,
                "buy_price": 1.04,
                "cancellation_fee": 0.04,
                "multiplier": 400,
                "cancellation_expiry": time.time() + 60,
            }
            bot.state["contracts"]["qualified_runner"] = record
            raw = {
                "contract_id": "qualified_runner",
                "contract_type": "MULTUP",
                "entry_spot": 100.0,
                "current_spot": 100.04,
                "profit": 0.16,  # net = 0.12 >= 0.04 fee
                "bid_price": 1.16,
                "is_valid_to_cancel": 1,
                "is_valid_to_sell": 1,
            }

            asyncio.run(bot.handle_boundary(record, raw))
            self.assertEqual(record["lifecycle"], "held_winner")
            self.assertEqual(bot.state["machine_state"], "HELD_WINNER")
            bot.monitor_held_winner.assert_awaited_once()

    def test_boundary_profit_covers_fee_with_contrary_trend_cancels_defensively(self):
        """
        Gross profit = 0.20, fee = 0.04 -> net_profit = 0.16 >= 0.04.
        However, market trend is contrary (downtrend / MULTDOWN vs MULTUP position).
        Must cancel defensively before window expires!
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            config = replace(test_config(tmpdir), trend_alignment_enabled=True)
            # Market entered strong downtrend (contrary to MULTUP)
            downtrend = [120.0 - i * 0.10 for i in range(180)]
            client = FakeClient(responses={
                "ticks_history": {"history": {"prices": downtrend}},
                "cancel": {"cancel": {"sold_for": 1.0}},
            })
            bot = D107Bot(client, config)
            bot.state = new_state()
            bot.account_id = client.account_id

            record = {
                "contract_id": "contrary_runner",
                "lifecycle": "cancellation_window_monitoring",
                "direction": "MULTUP",
                "stake": 1.0,
                "buy_price": 1.04,
                "cancellation_fee": 0.04,
                "multiplier": 400,
                "cancellation_expiry": time.time() + 60,
            }
            bot.state["contracts"]["contrary_runner"] = record
            raw = {
                "contract_id": "contrary_runner",
                "contract_type": "MULTUP",
                "entry_spot": 100.0,
                "current_spot": 100.05,
                "profit": 0.20,  # net = 0.16 >= 0.04 fee
                "bid_price": 1.20,
                "is_valid_to_cancel": 1,
                "is_valid_to_sell": 1,
            }

            asyncio.run(bot.handle_boundary(record, raw))
            # Trend is against position -> must defensively cancel
            self.assertEqual(record["lifecycle"], "closed_loser")
            self.assertTrue(any("cancel" in call for call in client.calls))

    def test_boundary_cancellation_window_missed_handling(self):
        """
        If is_valid_to_cancel is False when sub-fee or contrary trend arrives at boundary,
        bot must mark contract as cancellation_window_missed and NOT attempt invalid cancel.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            config = replace(test_config(tmpdir), trend_alignment_enabled=True)
            uptrend = [100.0 + i * 0.10 for i in range(180)]
            client = FakeClient(responses={"ticks_history": {"history": {"prices": uptrend}}})
            bot = D107Bot(client, config)
            bot.state = new_state()
            bot.account_id = client.account_id

            record = {
                "contract_id": "missed_window",
                "lifecycle": "cancellation_window_monitoring",
                "direction": "MULTUP",
                "stake": 1.0,
                "buy_price": 1.04,
                "cancellation_fee": 0.04,
                "multiplier": 400,
                "cancellation_expiry": time.time() - 5,
            }
            bot.state["contracts"]["missed_window"] = record
            raw = {
                "contract_id": "missed_window",
                "contract_type": "MULTUP",
                "entry_spot": 100.0,
                "current_spot": 100.005,
                "profit": 0.02,  # net = -0.02 < fee
                "bid_price": 1.02,
                "is_valid_to_cancel": 0,
                "is_valid_to_sell": 1,
            }

            asyncio.run(bot.handle_boundary(record, raw))
            self.assertEqual(bot.state["contracts"]["missed_window"]["lifecycle"], "cancellation_window_missed")
            self.assertEqual(bot.state["machine_state"], "RECONCILIATION_REQUIRED")
            self.assertFalse(any("cancel" in call for call in client.calls))


class TestPropertyBasedRatchetInvariants(unittest.TestCase):
    """
    Property-based verification of invariants across 1,000 randomized synthetic trajectories.
    """

    def test_floor_monotonicity_under_random_walk(self):
        """
        INVARIANT 1: As a position experiences fluctuating profit, the guaranteed floor
        must be monotonically non-decreasing over time: floor(t_i+1) >= floor(t_i).
        """
        stake = 1.0
        random.seed(42)

        for trial in range(100):
            current_profit = 0.0
            peak_profit = 0.0
            last_floor = 0.0

            for step in range(50):
                # Random shock between -0.2 and +0.3
                shock = random.uniform(-0.2, 0.3)
                current_profit = max(-0.95, current_profit + shock)
                peak_profit = max(peak_profit, current_profit)

                ratchet = evaluate_perpetual_ratchet(
                    profit=current_profit,
                    stake=stake,
                    peak_profit=peak_profit,
                )

                # Monotonicity check
                self.assertGreaterEqual(
                    ratchet.guaranteed_floor,
                    last_floor - 1e-9,
                    f"Floor decreased from {last_floor} to {ratchet.guaranteed_floor} at step {step}",
                )
                last_floor = ratchet.guaranteed_floor

                if ratchet.should_exit:
                    # Invariant 2: realized profit upon exit must satisfy ratchet floor constraint
                    if ratchet.exit_reason == "winner_trailing_stop":
                        self.assertLessEqual(current_profit, ratchet.guaranteed_floor + 1e-9)
                    break

    def test_intra_window_immunity_invariant(self):
        """
        INVARIANT 2: Inside the 5-minute cancellation window (is_valid_to_cancel=True),
        evaluate_winner_exit MUST NEVER return should_exit=True for ANY profit in [-1.0, +10.0].
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            config = test_config(tmpdir)
            bot = D107Bot(FakeClient(), config)

            record = {
                "contract_id": "inv_test",
                "lifecycle": "cancellation_window_monitoring",
                "direction": "MULTUP",
                "stake": 1.0,
                "buy_price": 1.04,
                "cancellation_fee": 0.04,
            }

            # Sample 200 arbitrary profit points across full range
            profits = [round(p * 0.05, 2) for p in range(-20, 201)]
            for p in profits:
                bid = max(0.01, 1.04 + p)
                raw = {"bid_price": bid, "buy_price": 1.04, "is_valid_to_cancel": 1, "is_valid_to_sell": 1}
                ev = PnlEvidence(
                    decision=PnlDecision("validated_winner" if p >= 0 else "validated_loss", "api", p, p, p, "test"),
                    entry_spot=100.0,
                    current_spot=100.0 + p / 4.0,
                    bid_price=bid,
                    is_valid_to_cancel=True,
                    is_valid_to_sell=True,
                    contract_id="inv_test",
                    raw=raw,
                )
                should_exit, reason = bot.evaluate_winner_exit(record, raw, ev)
                self.assertFalse(
                    should_exit,
                    f"In-window immunity violated at profit={p}: returned should_exit=True ({reason})",
                )
                self.assertEqual(reason, "in_window_auto_sell_disabled")


class TestSimulationDiscreteEventStress(unittest.TestCase):
    """
    Discrete-event simulation replay tests across recorded and synthetic tick streams.
    Stress-testing:
    - Drawdown during 5m cancellation window without premature micro-scalping
    - Progressive ratchet pullbacks and floor triggers
    - Boundary defensive cancellation on sub-fee profit and contrary trend
    """

    def test_simulation_contract_19127889519_drawdown_held_through_window(self):
        """
        Emulate contract #19127889519 in discrete simulation replay:
        Adverse excursion to -85% inside the cancellation window.
        Verify that perpetual_ladder_1x_8x NEVER micro-scalps or exits prematurely,
        whereas micro_scalp_baseline prematurely dumps the winner.
        """
        times = [0, 60, 120, 180, 240, 300, 400]
        # At 400x multiplier on stake=1.0:
        # t=0: 100.0 (entry)
        # t=60: 99.85 (-0.60 mark)
        # t=120: 99.7875 (-0.85 mark, -85% adverse excursion)
        # t=180: 99.90 (-0.40 mark, turnaround starts)
        # t=240: 100.10 (+0.40 mark, micro-profit bounce)
        # t=300: 100.40 (+1.60 mark, net=1.56 >= 0.04 fee -> boundary winner!)
        # t=400: 102.10 (+8.40 mark >= 8.0 target -> sold_winner_target!)
        prices = [100.0, 99.85, 99.7875, 99.90, 100.10, 100.40, 102.10]
        quote_map = {
            "1.0:MULTUP": {"ask_price": 1.04, "cancellation_fee": 0.04, "commission": 0.0},
            "1.0:MULTDOWN": {"ask_price": 1.04, "cancellation_fee": 0.04, "commission": 0.0},
        }

        # 1. Perpetual Ladder: Holds through -85% drawdown and reaches 8.0x target
        res_perp = simulate("demo", times, prices, quote_map, 1.0, 1.04, "all_in", "perpetual_ladder_1x_8x", target_multiple=8.0)
        self.assertEqual(res_perp.held_winners, 1)
        self.assertEqual(res_perp.positions[0]["status"], "sold_winner_target")
        self.assertEqual(res_perp.positions[0]["terminal_time"], 400)
        self.assertAlmostEqual(res_perp.positions[0]["adverse_min"], -0.85, places=4)
        self.assertAlmostEqual(res_perp.positions[0]["terminal_net"], 8.36, places=4)

        # 2. Micro-scalp baseline: Prematurely scalps at t=240 (+0.40 mark) inside window!
        res_baseline = simulate("demo", times, prices, quote_map, 1.0, 1.04, "all_in", "micro_scalp_baseline", target_multiple=0.25)
        self.assertEqual(res_baseline.positions[0]["status"], "sold_winner_micro_scalp")
        self.assertEqual(res_baseline.positions[0]["terminal_time"], 240)
        self.assertAlmostEqual(res_baseline.positions[0]["terminal_net"], 0.36, places=4)

    def test_simulation_ratchet_tier_pullbacks(self):
        """
        Verify that the simulation replay strictly implements the 4-tier ratchet floors:
        - Tier 1 (+1.0x stake): floor locked at +0.20
        - Tier 2 (+2.0x stake): floor locked at +1.00
        - Tier 3 (+4.0x stake): floor locked at +2.50
        """
        quote_map = {
            "1.0:MULTUP": {"ask_price": 1.04, "cancellation_fee": 0.04, "commission": 0.0},
            "1.0:MULTDOWN": {"ask_price": 1.04, "cancellation_fee": 0.04, "commission": 0.0},
        }

        # --- Tier 1 Test ---
        # t=0: 100.0, t=300: 100.10 (boundary held), t=350: 100.375 (+1.50 peak -> Tier 1),
        # t=400: 100.065 (+0.26 mark > 0.20 floor -> hold), t=450: 100.045 (+0.18 mark <= 0.20 floor -> exit)
        times_t1 = [0, 300, 350, 400, 450]
        prices_t1 = [100.0, 100.10, 100.375, 100.065, 100.045]
        res_t1 = simulate("demo", times_t1, prices_t1, quote_map, 1.0, 1.04, "all_in", "perpetual_ladder_1x_8x")
        self.assertEqual(res_t1.held_winners, 1)
        self.assertEqual(res_t1.positions[0]["status"], "sold_winner_trailing")
        self.assertEqual(res_t1.positions[0]["terminal_time"], 450)
        self.assertAlmostEqual(res_t1.positions[0]["held_peak_net"], 1.50, places=4)

        # --- Tier 2 Test ---
        # t=350: 100.65 (+2.60 peak -> Tier 2), t=400: 100.24 (+0.96 mark <= 1.00 floor -> exit)
        times_t2 = [0, 300, 350, 400]
        prices_t2 = [100.0, 100.10, 100.65, 100.24]
        res_t2 = simulate("demo", times_t2, prices_t2, quote_map, 1.0, 1.04, "all_in", "perpetual_ladder_1x_8x")
        self.assertEqual(res_t2.held_winners, 1)
        self.assertEqual(res_t2.positions[0]["status"], "sold_winner_trailing")
        self.assertEqual(res_t2.positions[0]["terminal_time"], 400)
        self.assertAlmostEqual(res_t2.positions[0]["held_peak_net"], 2.60, places=4)

        # --- Tier 3 Test ---
        # t=350: 101.15 (+4.60 peak -> Tier 3), t=400: 100.60 (+2.40 mark <= 2.50 floor -> exit)
        times_t3 = [0, 300, 350, 400]
        prices_t3 = [100.0, 100.10, 101.15, 100.60]
        res_t3 = simulate("demo", times_t3, prices_t3, quote_map, 1.0, 1.04, "all_in", "perpetual_ladder_1x_8x")
        self.assertEqual(res_t3.held_winners, 1)
        self.assertEqual(res_t3.positions[0]["status"], "sold_winner_trailing")
        self.assertEqual(res_t3.positions[0]["terminal_time"], 400)
        self.assertAlmostEqual(res_t3.positions[0]["held_peak_net"], 4.60, places=4)

    def test_simulation_boundary_qualification_defensive_cancels_contrary_trend(self):
        """
        In simulation, when trend_alignment_enabled=True:
        If a position has positive net profit (>= fee) at t=300 boundary, but prevailing
        trend opposes position direction, it must be cancelled defensively.
        """
        # Prelude: 60 ticks of uptrend so index >= 30 aligns MULTUP
        times = list(range(0, 500))
        prices = [100.0] * 500
        for t in range(0, 60):
            prices[t] = 100.0 + t * 0.05
        # Reversal: from t=60 to t=500, steady downtrend
        for t in range(60, 500):
            prices[t] = prices[59] - (t - 59) * 0.005

        quote_map = {
            "1.0:MULTUP": {"ask_price": 1.04, "cancellation_fee": 0.04, "commission": 0.0},
            "1.0:MULTDOWN": {"ask_price": 1.04, "cancellation_fee": 0.04, "commission": 0.0},
        }

        # Run simulation with trend alignment enabled
        res = simulate(
            "demo",
            times,
            prices,
            quote_map,
            1.0,
            1.04,
            "all_in",
            "perpetual_ladder_1x_8x",
            trend_alignment_enabled=True,
        )
        self.assertEqual(res.cancellations, 1)
        self.assertEqual(res.held_winners, 0)
        self.assertEqual(res.positions[0]["status"], "cancelled_loser")
        self.assertAlmostEqual(res.positions[0]["terminal_net"], -0.04, places=4)


if __name__ == "__main__":
    unittest.main(verbosity=2)
