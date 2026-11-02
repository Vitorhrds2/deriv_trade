import asyncio
import json
import tempfile
import time
import unittest
from datetime import datetime
from dataclasses import replace
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

from d107_rate_limit_winner_holding import (
    AppendOnlyEventLog,
    AtomicStateStore,
    D107Bot,
    D107Config,
    PerpetualRatchetState,
    PnlDecision,
    PnlEvidence,
    TrendAlignmentSignal,
    calculate_adx_and_trend,
    classify_pnl,
    classify_portfolio_contracts,
    cancellation_decision_timestamp,
    cancellation_retry_allowed,
    evaluate_market_trend,
    evaluate_new_buy_guardrails,
    evaluate_perpetual_ratchet,
    new_state,
    pnl_evidence_from_contract,
    reconstruct_directional_pnl,
    validate_proposal,
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
        state_file=str(Path(tmpdir) / "state.json"),
        results_file=str(Path(tmpdir) / "events.jsonl"),
    )


class TestD107PureLogic(unittest.TestCase):
    def test_directional_reconstruction(self):
        self.assertAlmostEqual(reconstruct_directional_pnl("MULTUP", 100, 101, 1, 400), 4.0)
        self.assertAlmostEqual(reconstruct_directional_pnl("MULTDOWN", 100, 99, 1, 400), 4.0)
        self.assertAlmostEqual(reconstruct_directional_pnl("MULTUP", 100, 99, 1, 400), -4.0)
        self.assertIsNone(reconstruct_directional_pnl("CALL", 100, 101, 1, 400))

    def test_missing_and_zero_api_profit_can_use_reconstruction(self):
        metadata = {
            "contract_id": "1",
            "contract_type": "MULTDOWN",
            "stake": 1.0,
            "multiplier": 400,
        }
        evidence = pnl_evidence_from_contract(
            {
                "contract_id": "1",
                "profit": 0,
                "bid_price": 1.2,
                "is_valid_to_cancel": 1,
                "is_valid_to_sell": 1,
            },
            metadata,
            fallback_entry_spot=100,
            fallback_current_spot=99,
        )
        self.assertEqual(evidence.decision.classification, "validated_winner")
        self.assertEqual(evidence.decision.pnl_source, "reconstructed")

        missing = pnl_evidence_from_contract(
            {
                "contract_id": "1",
                "bid_price": 0.7,
                "is_valid_to_cancel": 1,
                "is_valid_to_sell": 1,
            },
            metadata,
            fallback_entry_spot=100,
            fallback_current_spot=101,
        )
        self.assertEqual(missing.decision.classification, "validated_loss")
        self.assertEqual(missing.decision.pnl_source, "reconstructed")

    def test_contradictory_pnl_is_unresolved(self):
        decision = classify_pnl(5.0, -4.0, api_coherent=True)
        self.assertEqual(decision.classification, "unresolved")
        self.assertEqual(decision.pnl_source, "unknown")

    def test_sparse_positive_api_without_reconstruction_is_not_a_winner(self):
        decision = classify_pnl(5.0, None, api_coherent=False)
        self.assertEqual(decision.classification, "unresolved")
        self.assertEqual(decision.pnl_source, "unknown")

    def test_neutral_is_not_a_winner(self):
        decision = classify_pnl(0.0, 0.0, api_coherent=True)
        self.assertEqual(decision.classification, "neutral")
        self.assertEqual(decision.pnl_source, "neutral")

    def test_boundary_deadline(self):
        self.assertEqual(cancellation_decision_timestamp(300, 15), 285)
        self.assertTrue(cancellation_retry_allowed(299.0, 300.0, 0.5))
        self.assertFalse(cancellation_retry_allowed(300.0, 300.0, 0.5))
        self.assertFalse(cancellation_retry_allowed(301.0, 300.0, 0.0))

    def test_guardrails_include_external_exposure_and_fees(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            config = test_config(tmpdir)
            allowed, reason = evaluate_new_buy_guardrails(
                balance=100,
                open_count=2,
                deployed_capital=19,
                next_buy_cost=1,
                realized_pnl=0,
                cancellation_fees=0,
                config=config,
            )
            self.assertTrue(allowed)
            self.assertEqual(reason, "ok")

            blocked, reason = evaluate_new_buy_guardrails(
                balance=100,
                open_count=10,
                deployed_capital=0,
                next_buy_cost=1,
                realized_pnl=0,
                cancellation_fees=0,
                config=config,
            )
            self.assertFalse(blocked)
            self.assertEqual(reason, "max_open_positions")

            blocked, reason = evaluate_new_buy_guardrails(
                balance=100,
                open_count=2,
                deployed_capital=19,
                next_buy_cost=1.1,
                realized_pnl=0,
                cancellation_fees=0,
                config=config,
            )
            self.assertFalse(blocked)
            self.assertEqual(reason, "max_deployed_capital")

            blocked, reason = evaluate_new_buy_guardrails(
                balance=100,
                open_count=2,
                deployed_capital=0,
                next_buy_cost=1,
                realized_pnl=0,
                cancellation_fees=10,
                config=config,
            )
            self.assertFalse(blocked)
            self.assertEqual(reason, "session_loss_stop")

    def test_proposal_validation_locks_parameters(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            config = test_config(tmpdir)
            now = time.time()
            proposal = {
                "id": "proposal-1",
                "ask_price": 1.44,
                "amount": 1.0,
                "date_start": now,
                "contract_type": "MULTUP",
                "underlying": "1HZ10V",
                "multiplier": 400,
                "shortcode": f"MULTUP_1HZ10V_1.00_400_{int(now)}_0_5m_0.00_N1_0",
                "cancellation": {
                    "ask_price": 0.44,
                    "date_expiry": now + 300,
                    "duration": 5,
                    "duration_unit": "m",
                },
            }
            validated = validate_proposal(proposal, config, "MULTUP", now=now)
            self.assertEqual(validated.proposal_id, "proposal-1")
            self.assertEqual(validated.cancellation_fee, 0.44)

            invalid = dict(proposal, underlying="1HZ100V")
            with self.assertRaises(ValueError):
                validate_proposal(invalid, config, "MULTUP", now=now)

    def test_portfolio_matching_separates_other_symbols(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            config = test_config(tmpdir)
            matching, unknown = classify_portfolio_contracts(
                [
                    {
                        "contract_id": "d107",
                        "contract_type": "MULTUP",
                        "underlying_symbol": "1HZ10V",
                        "multiplier": 400,
                        "buy_price": 1.44,
                    },
                    {
                        "contract_id": "other",
                        "contract_type": "MULTDOWN",
                        "underlying_symbol": "1HZ100V",
                        "multiplier": 400,
                        "buy_price": 1.44,
                    },
                ],
                config,
            )
            self.assertEqual([item["contract_id"] for item in matching], ["d107"])
            self.assertEqual(unknown, [])

    def test_config_rejects_locked_values(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            config = test_config(tmpdir)
            with self.assertRaises(ValueError):
                replace(config, symbol="INVALID_SYMBOL").validate()
            with self.assertRaises(ValueError):
                replace(config, multiplier=999).validate()
            with self.assertRaises(ValueError):
                replace(config, stake=10.01).validate()
            with self.assertRaises(ValueError):
                replace(config, boundary_buffer_seconds=300).validate()

    def test_compact_observation_logging_is_configurable(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            env = {
                "D107_RESULTS_FILE": str(Path(tmpdir) / "events.jsonl"),
                "D107_STATE_FILE": str(Path(tmpdir) / "state.json"),
                "D107_OBSERVATION_LOG_SECONDS": "300",
                "D107_MIN_FREE_BYTES": "104857600",
                "D107_LOG_RAW_OBSERVATIONS": "0",
            }
            config = D107Config.from_env(env)
            self.assertEqual(config.observation_log_seconds, 300.0)
            self.assertEqual(config.min_free_bytes, 104857600)
            self.assertFalse(config.log_raw_observations)


class TestD107PersistenceAndAccount(unittest.TestCase):
    def test_atomic_state_preserves_alternation(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = str(Path(tmpdir) / "state.json")
            store = AtomicStateStore(path)
            state = new_state()
            state["last_confirmed_direction"] = "MULTUP"
            state["next_direction"] = "MULTDOWN"
            state["confirmed_buys"] = 1
            store.save(state)
            restored = store.load()
            self.assertEqual(restored["next_direction"], "MULTDOWN")
            self.assertEqual(restored["confirmed_buys"], 1)

    def test_event_log_redacts_credentials(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "events.jsonl"
            AppendOnlyEventLog(str(path)).append(
                "test",
                api_token="pat_super_secret",
                nested={"authorization": "secret-value"},
            )
            text = path.read_text()
            self.assertNotIn("pat_super_secret", text)
            self.assertNotIn("secret-value", text)
            self.assertIn("<redacted>", text)

    def test_demo_identity_is_required(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            config = test_config(tmpdir)
            client = FakeClient()
            bot = D107Bot(client, config)
            bot.verify_demo_account()
            self.assertEqual(bot.account_id, client.account_id)
            client.use_demo = False
            with self.assertRaises(ValueError):
                bot.verify_demo_account()

    def test_automated_winner_sale_is_disabled_by_default(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            bot = D107Bot(FakeClient(), test_config(tmpdir))
            self.assertFalse(bot.config.auto_sell_winners)
            self.assertEqual(bot.config.winner_exit_multiple, 8.0)


class TestD107CancellationStateMachine(unittest.TestCase):
    def test_target_multiple_sell_is_explicit_and_logged(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            config = replace(test_config(tmpdir), auto_sell_winners=True, winner_exit_multiple=3.0)
            client = FakeClient(responses={"sell": {"sell": {"sold_for": 3.12}}})
            bot = D107Bot(
                client,
                config,
                state_store=AtomicStateStore(config.state_file),
                event_log=AppendOnlyEventLog(config.results_file),
            )
            bot.state = new_state()
            bot.account_id = client.account_id
            record = {
                "contract_id": "winner",
                "lifecycle": "held_winner",
                "direction": "MULTUP",
                "stake": 1.0,
                "buy_price": 1.04,
                "cancellation_expiry": time.time() - 1,
            }
            bot.state["contracts"]["winner"] = record
            evidence = PnlEvidence(
                decision=PnlDecision("validated_winner", "api", 2.08, 2.08, 2.1, "test"),
                entry_spot=100.0,
                current_spot=102.5,
                bid_price=3.12,
                is_valid_to_cancel=False,
                is_valid_to_sell=True,
                contract_id="winner",
                raw={"bid_price": 3.12, "buy_price": 1.04},
            )
            self.assertTrue(
                bot.should_auto_sell_winner(
                    record,
                    {"bid_price": 3.12, "buy_price": 1.04},
                    evidence,
                )
            )
            asyncio.run(bot.sell_winner(record, evidence))
            self.assertEqual(record["lifecycle"], "closed_target")
            self.assertEqual(record["realized_pnl"], 2.08)
            self.assertEqual(client.calls, [{"sell": "winner", "price": 0}])

    def test_validated_loser_uses_cancel_only(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            config = test_config(tmpdir)
            client = FakeClient()
            bot = D107Bot(
                client,
                config,
                state_store=AtomicStateStore(config.state_file),
                event_log=AppendOnlyEventLog(config.results_file),
            )
            bot.state = new_state()
            bot.account_id = client.account_id
            record = {
                "contract_id": "1",
                "lifecycle": "cancellation_window_monitoring",
                "direction": "MULTDOWN",
                "stake": 1.0,
                "buy_price": 1.44,
                "cancellation_fee": 0.44,
                "cancellation_expiry": time.time() + 30,
            }
            bot.state["contracts"]["1"] = record
            evidence = PnlEvidence(
                decision=PnlDecision("validated_loss", "reconstructed", -4.0, None, -4.0, "test"),
                entry_spot=100.0,
                current_spot=101.0,
                bid_price=0.5,
                is_valid_to_cancel=True,
                is_valid_to_sell=False,
                contract_id="1",
                raw={},
            )
            asyncio.run(bot.cancel_loser(record, evidence))
            self.assertEqual(record["lifecycle"], "closed_loser")
            self.assertEqual(client.calls, [{"cancel": 1}])
            self.assertNotIn("sell", [next(iter(call)) for call in client.calls])

    def test_unresolved_loss_is_sold_after_cancellation_window(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            config = test_config(tmpdir)
            client = FakeClient(responses={"sell": {"sell": {"sold_for": 0.70}}})
            bot = D107Bot(
                client,
                config,
                state_store=AtomicStateStore(config.state_file),
                event_log=AppendOnlyEventLog(config.results_file),
            )
            bot.state = new_state()
            bot.account_id = client.account_id
            record = {
                "contract_id": "unresolved-loss",
                "lifecycle": "unresolved",
                "direction": "MULTUP",
                "stake": 1.0,
                "buy_price": 1.04,
            }
            bot.state["contracts"][record["contract_id"]] = record
            bot.state["unresolved_contracts"] = [record["contract_id"]]
            bot.state["stop_reason"] = "reconciliation_required"
            evidence = PnlEvidence(
                decision=PnlDecision("validated_loss", "api", -0.34, -0.34, -0.34, "test"),
                entry_spot=100.0,
                current_spot=99.9,
                bid_price=0.70,
                is_valid_to_cancel=False,
                is_valid_to_sell=True,
                contract_id=record["contract_id"],
                raw={},
            )
            self.assertTrue(asyncio.run(bot.sell_unresolved_loss(record, evidence)))
            self.assertEqual(record["lifecycle"], "closed_unresolved_loss")
            self.assertAlmostEqual(record["realized_pnl"], -0.34)
            self.assertEqual(bot.state["unresolved_contracts"], [])
            self.assertIsNone(bot.state["stop_reason"])
            self.assertEqual(client.calls, [{"sell": "unresolved-loss", "price": 0}])


class TestD107RuntimeSafety(unittest.TestCase):
    def test_sparse_contract_uses_tick_history_fallback(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            purchase_time = int(time.time())
            client = FakeClient(
                responses={
                    "ticks_history": {
                        "history": {"prices": [100.0], "times": [purchase_time]},
                    },
                    "ticks": {"tick": {"quote": 99.0}},
                }
            )
            config = test_config(tmpdir)
            bot = D107Bot(client, config)
            record = {
                "contract_id": "sparse",
                "direction": "MULTDOWN",
                "stake": 1.0,
                "multiplier": 400,
                "purchase_time": purchase_time,
            }
            evidence = asyncio.run(
                bot.collect_evidence(
                    record,
                    {
                        "contract_id": "sparse",
                        "contract_type": "MULTDOWN",
                        "profit": 0,
                        "bid_price": 1.0,
                        "is_valid_to_cancel": 1,
                        "is_valid_to_sell": 1,
                    },
                )
            )
            self.assertEqual(evidence.decision.classification, "validated_winner")
            self.assertEqual(evidence.decision.pnl_source, "reconstructed")
            self.assertEqual([next(iter(call)) for call in client.calls], ["ticks_history", "ticks"])

    def test_winner_boundary_holds_without_any_close_request(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            client = FakeClient()
            config = test_config(tmpdir)
            bot = D107Bot(client, config)
            bot.state = new_state()
            bot.account_id = client.account_id
            bot.monitor_held_winner = AsyncMock()
            record = {
                "contract_id": "winner",
                "lifecycle": "cancellation_window_monitoring",
                "direction": "MULTUP",
                "stake": 1.0,
                "multiplier": 400,
                "cancellation_expiry": time.time() + 300,
            }
            bot.state["contracts"]["winner"] = record
            asyncio.run(
                bot.handle_boundary(
                    record,
                    {
                        "contract_id": "winner",
                        "contract_type": "MULTUP",
                        "entry_spot": 100,
                        "current_spot": 101,
                        "profit": 4,
                        "bid_price": 5,
                        "is_valid_to_cancel": 1,
                        "is_valid_to_sell": 1,
                    },
                )
            )
            self.assertEqual(record["lifecycle"], "held_winner")
            self.assertEqual(client.calls, [])
            bot.monitor_held_winner.assert_awaited_once()

    def test_rate_limit_cancel_retries_are_bounded_and_stop_buys(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            client = FakeClient(
                responses={
                    "cancel": {"error": {"code": "RateLimit", "message": "rate limit"}},
                }
            )
            config = test_config(tmpdir)
            bot = D107Bot(
                client,
                config,
                state_store=AtomicStateStore(config.state_file),
                event_log=AppendOnlyEventLog(config.results_file),
            )
            bot.state = new_state()
            bot.account_id = client.account_id
            record = {
                "contract_id": "loser",
                "lifecycle": "cancellation_window_monitoring",
                "direction": "MULTDOWN",
                "stake": 1.0,
                "buy_price": 1.44,
                "cancellation_fee": 0.44,
                "cancellation_expiry": time.time() + 10,
            }
            bot.state["contracts"]["loser"] = record
            evidence = PnlEvidence(
                decision=PnlDecision("validated_loss", "reconstructed", -4.0, None, -4.0, "test"),
                entry_spot=100.0,
                current_spot=101.0,
                bid_price=0.5,
                is_valid_to_cancel=True,
                is_valid_to_sell=False,
                contract_id="loser",
                raw={},
            )
            asyncio.run(bot.cancel_loser(record, evidence))
            self.assertEqual(len([call for call in client.calls if "cancel" in call]), 3)
            self.assertEqual(record["lifecycle"], "cancel_failed")
            self.assertFalse(bot.state["new_buys_enabled"])
            self.assertNotIn("sell", [next(iter(call)) for call in client.calls])

    def test_buy_timeout_leaves_pending_state_and_prevents_duplicate(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            now = time.time()
            def proposal(_payload):
                return {
                    "proposal": {
                        "id": "p-timeout",
                        "ask_price": 1.44,
                        "amount": 1.0,
                        "date_start": now,
                        "contract_type": "MULTUP",
                        "underlying": "1HZ10V",
                        "multiplier": 400,
                        "shortcode": f"MULTUP_1HZ10V_1.00_400_{int(now)}_0_5m_0.00_N1_0",
                        "cancellation": {
                            "ask_price": 0.44,
                            "date_expiry": now + 300,
                            "duration": 5,
                            "duration_unit": "m",
                        },
                    }
                }
            def timeout(_payload):
                raise asyncio.TimeoutError()
            client = FakeClient(
                responses={
                    "balance": {"balance": {"balance": 100}},
                    "portfolio": {"portfolio": {"contracts": []}},
                    "proposal": proposal,
                    "buy": timeout,
                }
            )
            config = test_config(tmpdir)
            bot = D107Bot(
                client,
                config,
                state_store=AtomicStateStore(config.state_file),
                event_log=AppendOnlyEventLog(config.results_file),
            )
            bot.state = new_state()
            bot.state["new_buys_enabled"] = True
            asyncio.run(bot.try_buy())
            first_buy_count = len([call for call in client.calls if "buy" in call])
            self.assertEqual(first_buy_count, 1)
            self.assertFalse(bot.state["new_buys_enabled"])
            self.assertTrue(bot.state["pending_buy"])
            asyncio.run(bot.try_buy())
            self.assertEqual(len([call for call in client.calls if "buy" in call]), first_buy_count)

    def test_external_positions_are_counted_before_enabling_buys(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            positions = [
                {
                    "contract_id": str(index),
                    "contract_type": "MULTUP",
                    "underlying_symbol": "1HZ10V",
                    "multiplier": 400,
                    "buy_price": 1.44,
                }
                for index in range(10)
            ]
            client = FakeClient(
                responses={
                    "balance": {"balance": {"balance": 100}},
                    "portfolio": {"portfolio": {"contracts": positions}},
                }
            )
            config = test_config(tmpdir)
            bot = D107Bot(client, config)
            asyncio.run(bot.preflight())
            self.assertEqual(len(bot.portfolio_positions), 10)
            self.assertFalse(bot.state["new_buys_enabled"])
            self.assertEqual(bot.state["stop_reason"], "max_open_positions")
            self.assertEqual(bot.state["contracts"], {})

    def test_continuous_releases_position_cap_after_capacity_returns(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            positions = [
                {
                    "contract_id": str(index),
                    "contract_type": "MULTUP",
                    "underlying_symbol": "1HZ10V",
                    "multiplier": 400,
                    "buy_price": 1.04,
                }
                for index in range(10)
            ]
            client = FakeClient(
                responses={
                    "balance": {"balance": {"balance": 100}},
                    "portfolio": {"portfolio": {"contracts": positions}},
                }
            )
            config = replace(test_config(tmpdir), mode="continuous")
            bot = D107Bot(client, config)
            asyncio.run(bot.preflight())
            self.assertFalse(bot.state["new_buys_enabled"])
            self.assertEqual(bot.state["stop_reason"], "max_open_positions")

            client.responses["portfolio"] = {"portfolio": {"contracts": []}}
            asyncio.run(bot.write_portfolio_snapshot())
            self.assertTrue(bot.state["new_buys_enabled"])
            self.assertIsNone(bot.state["stop_reason"])

    def test_continuous_releases_stale_disabled_gate_without_reason(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            config = replace(test_config(tmpdir), mode="continuous")
            bot = D107Bot(FakeClient(), config)
            bot.state = new_state()
            bot.state["new_buys_enabled"] = False
            bot.state["stop_reason"] = None
            bot.state["deployed_capital"] = 0.0
            bot.portfolio_positions = []
            bot.refresh_continuous_buy_gate(100.0)
            self.assertTrue(bot.state["new_buys_enabled"])
            self.assertIsNone(bot.state["stop_reason"])

    def test_continuous_releases_snapshot_failure_after_healthy_snapshot(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            client = FakeClient(
                responses={
                    "balance": {"balance": {"balance": 100}},
                    "portfolio": {"portfolio": {"contracts": []}},
                }
            )
            config = replace(test_config(tmpdir), mode="continuous")
            bot = D107Bot(client, config)
            bot.state = new_state()
            bot.state["stop_reason"] = "portfolio_snapshot_failure"
            bot.state["new_buys_enabled"] = False
            bot.state_store.save(bot.state)
            asyncio.run(bot.preflight())
            self.assertTrue(bot.state["new_buys_enabled"])
            self.assertIsNone(bot.state["stop_reason"])

    def test_continuous_does_not_release_session_loss_stop(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            client = FakeClient(
                responses={
                    "balance": {"balance": {"balance": 100}},
                    "portfolio": {"portfolio": {"contracts": []}},
                }
            )
            config = replace(test_config(tmpdir), mode="continuous")
            bot = D107Bot(client, config)
            bot.state = new_state()
            bot.state["stop_reason"] = "session_loss_stop"
            bot.state["session_realized_pnl"] = -10
            bot.state["new_buys_enabled"] = False
            bot.state_store.save(bot.state)
            asyncio.run(bot.preflight())
            self.assertFalse(bot.state["new_buys_enabled"])
            self.assertEqual(bot.state["stop_reason"], "session_loss_stop")

    def test_restart_reconciles_and_restarts_held_winner_monitor(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            config = test_config(tmpdir)
            store = AtomicStateStore(config.state_file)
            state = new_state()
            state["contracts"]["winner"] = {
                "contract_id": "winner",
                "owner": "d107_created",
                "lifecycle": "held_winner",
                "direction": "MULTUP",
                "stake": 1.0,
                "buy_price": 1.44,
                "multiplier": 400,
                "cancellation_expiry": time.time() + 300,
            }
            store.save(state)
            client = FakeClient(
                responses={
                    "balance": {"balance": {"balance": 100}},
                    "portfolio": {
                        "portfolio": {
                            "contracts": [
                                {
                                    "contract_id": "winner",
                                    "contract_type": "MULTUP",
                                    "underlying_symbol": "1HZ10V",
                                    "multiplier": 400,
                                    "buy_price": 1.44,
                                }
                            ]
                        }
                    },
                }
            )
            bot = D107Bot(
                client,
                config,
                state_store=store,
                event_log=AppendOnlyEventLog(config.results_file),
            )
            bot.start_monitor = MagicMock()
            asyncio.run(bot.preflight())
            bot.start_monitor.assert_called_once_with("winner")
            self.assertTrue(bot.state["new_buys_enabled"])

    def test_restart_reconciles_terminal_external_close(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            config = test_config(tmpdir)
            store = AtomicStateStore(config.state_file)
            state = new_state()
            state["stop_reason"] = "reconciliation_required"
            state["unresolved_contracts"] = ["closed"]
            state["contracts"]["closed"] = {
                "contract_id": "closed",
                "owner": "d107_created",
                "lifecycle": "held_winner",
                "direction": "MULTUP",
                "stake": 1.0,
                "buy_price": 1.04,
                "multiplier": 400,
                "cancellation_expiry": time.time() + 300,
            }
            store.save(state)
            client = FakeClient(
                responses={
                    "balance": {"balance": {"balance": 100}},
                    "portfolio": {"portfolio": {"contracts": []}},
                    "proposal_open_contract": {
                        "proposal_open_contract": {
                            "contract_id": "closed",
                            "status": "sold",
                            "is_sold": 1,
                            "is_expired": 0,
                            "sell_price": 0.97,
                        }
                    },
                }
            )
            bot = D107Bot(
                client,
                config,
                state_store=store,
                event_log=AppendOnlyEventLog(config.results_file),
            )
            asyncio.run(bot.preflight())
            self.assertEqual(bot.state["contracts"]["closed"]["lifecycle"], "closed_external")
            self.assertEqual(bot.state["unresolved_contracts"], [])
            self.assertTrue(bot.state["new_buys_enabled"])
            self.assertEqual(bot.state["stop_reason"], None)

    def test_restart_reconciles_open_unresolved_contract_as_winner(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            config = test_config(tmpdir)
            store = AtomicStateStore(config.state_file)
            state = new_state()
            state["stop_reason"] = "API profit contradicts independent reconstruction"
            state["unresolved_contracts"] = ["open"]
            state["contracts"]["open"] = {
                "contract_id": "open",
                "owner": "d107_created",
                "lifecycle": "unresolved",
                "direction": "MULTUP",
                "stake": 1.0,
                "buy_price": 1.04,
                "multiplier": 400,
                "cancellation_expiry": time.time() + 300,
                "purchase_time": int(time.time()) - 30,
            }
            store.save(state)
            client = FakeClient(
                responses={
                    "balance": {"balance": {"balance": 100}},
                    "portfolio": {
                        "portfolio": {
                            "contracts": [
                                {
                                    "contract_id": "open",
                                    "contract_type": "MULTUP",
                                    "underlying_symbol": "1HZ10V",
                                    "multiplier": 400,
                                    "buy_price": 1.04,
                                }
                            ]
                        }
                    },
                    "proposal_open_contract": {
                        "proposal_open_contract": {
                            "contract_id": "open",
                            "contract_type": "MULTUP",
                            "entry_spot": 100,
                            "current_spot": 101,
                            "profit": 4,
                            "bid_price": 5,
                            "is_valid_to_cancel": 0,
                            "is_valid_to_sell": 1,
                            "status": "open",
                        }
                    },
                }
            )
            bot = D107Bot(
                client,
                config,
                state_store=store,
                event_log=AppendOnlyEventLog(config.results_file),
            )
            bot.start_monitor = MagicMock()
            asyncio.run(bot.preflight())
            self.assertEqual(bot.state["contracts"]["open"]["lifecycle"], "held_winner")
            self.assertEqual(bot.state["unresolved_contracts"], [])
            self.assertTrue(bot.state["new_buys_enabled"])
            bot.start_monitor.assert_called_once_with("open")

    def test_unclassifiable_multiplier_stops_new_buys(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            config = test_config(tmpdir)
            client = FakeClient()
            bot = D107Bot(client, config)
            ok = asyncio.run(
                bot.reconcile_portfolio(
                    [
                        {
                            "contract_id": "unknown",
                            "contract_type": "MULTUP",
                            "underlying_symbol": "1HZ10V",
                            "buy_price": 1.44,
                        }
                    ],
                    strict=False,
                )
            )
            self.assertFalse(ok)
            self.assertFalse(bot.state["new_buys_enabled"])
            self.assertEqual(bot.state["stop_reason"], "reconciliation_required")

    def test_winner_trailing_stop_exit(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            config = replace(test_config(tmpdir), auto_sell_winners=True)
            client = FakeClient()
            bot = D107Bot(client, config)
            fake_now = datetime.fromisoformat("2026-10-30T10:02:00+00:00").timestamp()
            record = {
                "contract_id": "winner-ts",
                "buy_price": 1.0,
                "stake": 1.0,
                "cancellation_fee": 0.0,
                "peak_unrealized_pnl": 1.20,
                "held_at": "2026-10-30T10:00:00+00:00",
            }
            # Profit was 1.20 (Tier 1 locks in +0.20 floor), now dropped to 0.18 (<= +0.20 floor)
            raw = {"bid_price": 1.18, "buy_price": 1.0}
            evidence = PnlEvidence(
                decision=PnlDecision("validated_winner", "api", 0.18, 0.18, 0.18, "test"),
                entry_spot=100.0,
                current_spot=100.18,
                bid_price=1.18,
                is_valid_to_cancel=False,
                is_valid_to_sell=True,
                contract_id="winner-ts",
                raw=raw,
            )
            should_sell, reason = bot.evaluate_winner_exit(record, raw, evidence, now=fake_now)
            self.assertTrue(should_sell)
            self.assertEqual(reason, "winner_trailing_stop")

    def test_winner_capital_preservation_exit(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            config = replace(test_config(tmpdir), auto_sell_winners=True, winner_capital_preservation_loss=0.10)
            client = FakeClient()
            bot = D107Bot(client, config)
            # Held for 60 seconds, now negative by -0.15
            record = {
                "contract_id": "winner-cp",
                "buy_price": 1.0,
                "peak_unrealized_pnl": 0.05,
                "held_at": "2026-10-30T10:00:00+00:00",
            }
            raw = {"bid_price": 0.85, "buy_price": 1.0}
            evidence = PnlEvidence(
                decision=PnlDecision("validated_loss", "api", -0.15, -0.15, -0.15, "test"),
                entry_spot=100.0,
                current_spot=99.85,
                bid_price=0.85,
                is_valid_to_cancel=False,
                is_valid_to_sell=True,
                contract_id="winner-cp",
                raw=raw,
            )
            fake_now = datetime.fromisoformat("2026-10-30T10:01:10+00:00").timestamp()
            should_sell, reason = bot.evaluate_winner_exit(record, raw, evidence, now=fake_now)
            self.assertTrue(should_sell)
            self.assertEqual(reason, "winner_capital_preservation")

    def test_winner_time_stop_exit(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            config = replace(test_config(tmpdir), auto_sell_winners=True, winner_max_hold_seconds=600.0)
            client = FakeClient()
            bot = D107Bot(client, config)
            record = {
                "contract_id": "winner-time",
                "buy_price": 1.0,
                "peak_unrealized_pnl": 0.10,
                "held_at": "2026-10-30T10:00:00+00:00",
            }
            raw = {"bid_price": 1.05, "buy_price": 1.0}
            evidence = PnlEvidence(
                decision=PnlDecision("validated_winner", "api", 0.05, 0.05, 0.05, "test"),
                entry_spot=100.0,
                current_spot=100.05,
                bid_price=1.05,
                is_valid_to_cancel=False,
                is_valid_to_sell=True,
                contract_id="winner-time",
                raw=raw,
            )
            fake_now = datetime.fromisoformat("2026-10-30T10:11:00+00:00").timestamp()
            should_sell, reason = bot.evaluate_winner_exit(record, raw, evidence, now=fake_now)
            self.assertTrue(should_sell)
            self.assertEqual(reason, "winner_time_stop")

    def test_open_contract_uses_push_stream_cache(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            config = test_config(tmpdir)
            client = FakeClient()
            client.contract_streams = {
                12345: {"contract_id": 12345, "bid_price": 1.5, "profit": 0.46, "status": "open"}
            }
            client.contract_stream_times = {
                12345: time.monotonic()
            }
            bot = D107Bot(client, config)
            # Call open_contract, should return cached contract with 0 calls to send_request
            contract = asyncio.run(bot.open_contract("12345"))
            self.assertEqual(contract["contract_id"], 12345)
            self.assertEqual(contract["profit"], 0.46)
            self.assertEqual(client.calls, [])

    def test_parse_shortcode_with_underscore_symbols(self):
        from d107_rate_limit_winner_holding import parse_shortcode
        res = parse_shortcode("MULTUP_R_100_1.00_100_1793404413_4947004799_5m_0.00_N1_0")
        self.assertEqual(res["symbol"], "R_100")
        self.assertEqual(res["contract_type"], "MULTUP")
        self.assertEqual(res["stake"], 1.0)
        self.assertEqual(res["multiplier"], 100)
        self.assertEqual(res["purchase_time"], 1793404413)

        res2 = parse_shortcode("MULTDOWN_1HZ100V_1.00_100_1793404413_4947004799_5m_0.00_N1_0")
        self.assertEqual(res2["symbol"], "1HZ100V")
        self.assertEqual(res2["multiplier"], 100)

    def test_trailing_stop_breakeven_floor(self):
        import os
        with tempfile.TemporaryDirectory() as tmpdir:
            config = replace(
                test_config(tmpdir),
                auto_sell_winners=True,
            )
            client = FakeClient()
            bot = D107Bot(client, config)

            record = {
                "contract_id": "999",
                "buy_price": 1.10,
                "stake": 1.00,
                "cancellation_fee": 0.10,
                "peak_unrealized_pnl": 1.30,  # +1.20 net pnl (Tier 1 floor locks in at +0.20 net)
                "held_at": "2026-10-30T10:00:00+00:00",
            }
            # Caso 1: Bid está em 1.35 (net_pnl = +0.25 > 0.20). O trailing stop ainda não foi acionado.
            raw_holding = {"bid_price": 1.35, "buy_price": 1.10}
            ev_holding = PnlEvidence(
                decision=PnlDecision("validated_winner", "api", 0.35, 0.35, 0.35, "test"),
                entry_spot=100.0,
                current_spot=100.0,
                bid_price=1.35,
                is_valid_to_cancel=False,
                is_valid_to_sell=True,
                contract_id="999",
                raw=raw_holding,
            )
            fake_now = datetime.fromisoformat("2026-10-30T10:02:00+00:00").timestamp()
            should_sell, reason = bot.evaluate_winner_exit(record, raw_holding, ev_holding, now=fake_now)
            self.assertFalse(should_sell)
            self.assertEqual(reason, "holding")

            # Caso 2: Bid recua para 1.25 (net_pnl = +0.15 <= 0.20 floor). Atinge o trailing threshold com piso de breakeven!
            raw_be = {"bid_price": 1.25, "buy_price": 1.10}
            ev_be = PnlEvidence(
                decision=PnlDecision("validated_winner", "api", 0.25, 0.25, 0.25, "test"),
                entry_spot=100.0,
                current_spot=100.0,
                bid_price=1.25,
                is_valid_to_cancel=False,
                is_valid_to_sell=True,
                contract_id="999",
                raw=raw_be,
            )
            should_sell_be, reason_be = bot.evaluate_winner_exit(record, raw_be, ev_be, now=fake_now)
            self.assertTrue(should_sell_be)
            self.assertEqual(reason_be, "winner_trailing_stop")

    def test_market_regime_supervisor_filter(self):
        import os
        import json
        with tempfile.TemporaryDirectory() as tmpdir:
            policy_file = os.path.join(tmpdir, "policy.json")
            config = replace(
                test_config(tmpdir),
                check_regime_supervisor=True,
                symbol="R_100",
                min_regime_hurst=0.48,
                regime_policy_file=policy_file,
            )

            client = FakeClient()
            bot = D107Bot(client, config)

            # Test low hurst (chop)
            with open(policy_file, "w") as f:
                json.dump({
                    "epoch": time.time(),
                    "deriv_metrics": {
                        "R_100": {"hurst": 0.42, "recommended_strategy": "RSI_MEAN_REVERSION"}
                    }
                }, f)
            ok, reason = bot.evaluate_market_regime()
            self.assertFalse(ok)
            self.assertIn("hurst_too_low", reason)

            # Test healthy momentum hurst
            with open(policy_file, "w") as f:
                json.dump({
                    "epoch": time.time(),
                    "deriv_metrics": {
                        "R_100": {"hurst": 0.58, "recommended_strategy": "MOMENTUM_BREAKOUT"}
                    }
                }, f)
            ok, reason = bot.evaluate_market_regime()
            self.assertTrue(ok)
            self.assertIn("regime_ok", reason)

    def test_held_peak_unrealized_pnl_reset(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            config = replace(
                test_config(tmpdir),
                auto_sell_winners=True,
            )
            client = FakeClient()
            bot = D107Bot(client, config)

            # Record with high peak in 5m window (1.35) but freshly transitioned to held_winner (held_peak = 0.05)
            record = {
                "contract_id": "888",
                "buy_price": 1.10,
                "stake": 1.00,
                "cancellation_fee": 0.10,
                "peak_unrealized_pnl": 1.35,
                "held_peak_unrealized_pnl": 0.05,
                "held_at": "2026-10-30T10:00:00+00:00",
            }
            # Current bid 1.05 (net_pnl = -0.05). If it used peak_unrealized_pnl=1.35, it would see Tier 1 floor (+0.20) and sell.
            # But with held_peak=0.05 (< 1.0x stake Tier 0), it must HOLD and not sell!
            raw = {"bid_price": 1.05, "buy_price": 1.10}
            ev = PnlEvidence(
                decision=PnlDecision("validated_winner", "api", 0.05, 0.05, 0.05, "test"),
                entry_spot=100.0,
                current_spot=100.0,
                bid_price=1.05,
                is_valid_to_cancel=False,
                is_valid_to_sell=True,
                contract_id="888",
                raw=raw,
            )
            fake_now = datetime.fromisoformat("2026-10-30T10:00:10+00:00").timestamp()
            should_sell, reason = bot.evaluate_winner_exit(record, raw, ev, now=fake_now)
            self.assertFalse(should_sell)
            self.assertEqual(reason, "holding")

            # Now, simulate that the perpetual rallied: held_peak reached 1.30 (+1.20 net, activating Tier 1 +0.20 floor)
            record["held_peak_unrealized_pnl"] = 1.30
            # Then bid dropped back to 1.25 (net_pnl = +0.15 <= +0.20 floor) -> triggers winner_trailing_stop!
            raw_exit = {"bid_price": 1.25, "buy_price": 1.10}
            ev_exit = PnlEvidence(
                decision=PnlDecision("validated_winner", "api", 0.25, 0.25, 0.25, "test"),
                entry_spot=100.0,
                current_spot=100.0,
                bid_price=1.25,
                is_valid_to_cancel=False,
                is_valid_to_sell=True,
                contract_id="888",
                raw=raw_exit,
            )
            should_sell_exit, reason_exit = bot.evaluate_winner_exit(record, raw_exit, ev_exit, now=fake_now)
            self.assertTrue(should_sell_exit)
            self.assertEqual(reason_exit, "winner_trailing_stop")

    def test_allowed_symbols_includes_1hz75v_and_r75(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            cfg_75v = replace(test_config(tmpdir), symbol="1HZ75V")
            cfg_75v.validate()
            self.assertEqual(cfg_75v.symbol, "1HZ75V")

            cfg_r75 = replace(test_config(tmpdir), symbol="R_75")
            cfg_r75.validate()
            self.assertEqual(cfg_r75.symbol, "R_75")

    def test_in_window_early_take_profit(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            config = replace(
                test_config(tmpdir),
                symbol="1HZ75V",
                auto_sell_winners=True,
                in_window_auto_sell=False,
                in_window_take_profit=0.20,
            )
            client = FakeClient()
            bot = D107Bot(client, config)

            record = {
                "contract_id": "777",
                "buy_price": 1.08,
                "stake": 1.00,
                "cancellation_fee": 0.08,
                "peak_unrealized_pnl": 0.22,
            }
            raw = {"bid_price": 1.30, "buy_price": 1.08}
            ev = PnlEvidence(
                decision=PnlDecision("validated_winner", "api", 0.22, 0.22, 0.22, "test"),
                entry_spot=100.0,
                current_spot=100.22,
                bid_price=1.30,
                is_valid_to_cancel=True,
                is_valid_to_sell=True,
                contract_id="777",
                raw=raw,
            )
            should_sell, reason = bot.evaluate_winner_exit(record, raw, ev)
            self.assertFalse(should_sell)
            self.assertEqual(reason, "in_window_auto_sell_disabled")

    def test_in_window_early_trailing_stop(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            config = replace(
                test_config(tmpdir),
                symbol="1HZ75V",
                auto_sell_winners=True,
                in_window_auto_sell=True,
                in_window_take_profit=0.30,
                in_window_trailing_stop_pct=0.35,
                in_window_min_profit_to_trail=0.15,
            )
            client = FakeClient()
            bot = D107Bot(client, config)

            # Contract rallied to +$0.25 net / +$0.33 gross (bid=1.33, buy=1.08, stake=1.00)
            record = {
                "contract_id": "778",
                "buy_price": 1.08,
                "stake": 1.00,
                "cancellation_fee": 0.08,
                "peak_unrealized_pnl": 0.33,
            }
            raw = {"bid_price": 1.20, "buy_price": 1.08}
            ev = PnlEvidence(
                decision=PnlDecision("validated_winner", "api", 0.20, 0.20, 0.20, "test"),
                entry_spot=100.0,
                current_spot=100.20,
                bid_price=1.20,
                is_valid_to_cancel=True,
                is_valid_to_sell=True,
                contract_id="778",
                raw=raw,
            )
            # Under abolished in-window micro-scalping, contract is NOT sold inside cancellation window
            should_sell, reason = bot.evaluate_winner_exit(record, raw, ev)
            self.assertFalse(should_sell)
            self.assertEqual(reason, "cancellation_window_monitoring")

    def test_four_tier_progressive_perpetual_ratchet(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            config = replace(test_config(tmpdir), auto_sell_winners=True, winner_exit_multiple=8.0)
            self.assertFalse(config.in_window_auto_sell)
            self.assertEqual(config.winner_min_profit_to_trail, 1.0)
            self.assertEqual(config.winner_capital_preservation_loss, 0.35)
            bot = D107Bot(FakeClient(), config)
            fake_now = datetime.fromisoformat("2026-10-30T10:02:00+00:00").timestamp()

            # Tier 0 (< 1.0x stake): peak_net_pnl = +$0.80 (< $1.00), dipped to -$0.25 net -> pure perpetual hold!
            rec_t0 = {
                "contract_id": "t0",
                "buy_price": 1.10,
                "stake": 1.00,
                "cancellation_fee": 0.10,
                "held_peak_unrealized_pnl": 0.90,  # +0.80 net
                "held_at": "2026-10-30T10:00:00+00:00",
            }
            raw_t0 = {"bid_price": 0.85, "buy_price": 1.10}
            ev_t0 = PnlEvidence(
                decision=PnlDecision("validated_loss", "api", -0.15, -0.15, -0.15, "test"),
                entry_spot=100.0,
                current_spot=99.85,
                bid_price=0.85,
                is_valid_to_cancel=False,
                is_valid_to_sell=True,
                contract_id="t0",
                raw=raw_t0,
            )
            self.assertEqual(bot.evaluate_winner_exit(rec_t0, raw_t0, ev_t0, now=fake_now), (False, "holding"))

            # Tier 1 (+1.0x stake / +$1.00): peak_net_pnl = +$1.20 -> locks in breakeven floor at +0.20 * stake
            rec_t1 = dict(rec_t0, contract_id="t1", held_peak_unrealized_pnl=1.30)  # +1.20 net
            raw_t1_hold = {"bid_price": 1.35, "buy_price": 1.10}  # +0.25 net > 0.20 floor
            ev_t1_hold = replace(ev_t0, bid_price=1.35, raw=raw_t1_hold)
            self.assertEqual(bot.evaluate_winner_exit(rec_t1, raw_t1_hold, ev_t1_hold, now=fake_now), (False, "holding"))
            raw_t1_sell = {"bid_price": 1.28, "buy_price": 1.10}  # +0.18 net <= 0.20 floor
            ev_t1_sell = replace(ev_t0, bid_price=1.28, raw=raw_t1_sell)
            self.assertEqual(
                bot.evaluate_winner_exit(rec_t1, raw_t1_sell, ev_t1_sell, now=fake_now),
                (True, "winner_trailing_stop"),
            )

            # Tier 2 (+2.0x stake / +$2.00): peak_net_pnl = +$2.50 -> ratchets guaranteed floor to +1.00 * stake
            rec_t2 = dict(rec_t0, contract_id="t2", held_peak_unrealized_pnl=2.60)  # +2.50 net
            raw_t2_hold = {"bid_price": 2.25, "buy_price": 1.10}  # +1.15 net > 1.00 floor
            ev_t2_hold = replace(ev_t0, bid_price=2.25, raw=raw_t2_hold)
            self.assertEqual(bot.evaluate_winner_exit(rec_t2, raw_t2_hold, ev_t2_hold, now=fake_now), (False, "holding"))
            raw_t2_sell = {"bid_price": 2.05, "buy_price": 1.10}  # +0.95 net <= 1.00 floor
            ev_t2_sell = replace(ev_t0, bid_price=2.05, raw=raw_t2_sell)
            self.assertEqual(
                bot.evaluate_winner_exit(rec_t2, raw_t2_sell, ev_t2_sell, now=fake_now),
                (True, "winner_trailing_stop"),
            )

            # Tier 3 (+4.0x stake / +$4.00): peak_net_pnl = +$4.50 -> ratchets guaranteed floor to +2.50 * stake
            rec_t3 = dict(rec_t0, contract_id="t3", held_peak_unrealized_pnl=4.60)  # +4.50 net
            raw_t3_hold = {"bid_price": 3.75, "buy_price": 1.10}  # +2.65 net > 2.50 floor
            ev_t3_hold = replace(ev_t0, bid_price=3.75, raw=raw_t3_hold)
            self.assertEqual(bot.evaluate_winner_exit(rec_t3, raw_t3_hold, ev_t3_hold, now=fake_now), (False, "holding"))
            raw_t3_sell = {"bid_price": 3.55, "buy_price": 1.10}  # +2.45 net <= 2.50 floor
            ev_t3_sell = replace(ev_t0, bid_price=3.55, raw=raw_t3_sell)
            self.assertEqual(
                bot.evaluate_winner_exit(rec_t3, raw_t3_sell, ev_t3_sell, now=fake_now),
                (True, "winner_trailing_stop"),
            )

            # Tier 4 (+8.0x stake / +$8.00): Target take-profit / 80% trailing stop
            rec_t4 = dict(rec_t0, contract_id="t4", held_peak_unrealized_pnl=8.60)  # +8.50 net
            raw_t4_tp = {"bid_price": 9.10, "buy_price": 1.10}  # +8.00 net >= 8.0x target
            ev_t4_tp = replace(ev_t0, bid_price=9.10, raw=raw_t4_tp)
            self.assertEqual(
                bot.evaluate_winner_exit(rec_t4, raw_t4_tp, ev_t4_tp, now=fake_now),
                (True, "winner_exit_multiple"),
            )
            # 80% trailing stop on peak +8.50 -> floor = 8.50 * 0.80 = 6.80
            raw_t4_hold = {"bid_price": 8.00, "buy_price": 1.10}  # +6.90 net > 6.80 floor
            ev_t4_hold = replace(ev_t0, bid_price=8.00, raw=raw_t4_hold)
            self.assertEqual(bot.evaluate_winner_exit(rec_t4, raw_t4_hold, ev_t4_hold, now=fake_now), (False, "holding"))
            raw_t4_trail = {"bid_price": 7.80, "buy_price": 1.10}  # +6.70 net <= 6.80 floor
            ev_t4_trail = replace(ev_t0, bid_price=7.80, raw=raw_t4_trail)
            self.assertEqual(
                bot.evaluate_winner_exit(rec_t4, raw_t4_trail, ev_t4_trail, now=fake_now),
                (True, "winner_trailing_stop"),
            )

    def test_boundary_cancels_marginal_winner_below_cancel_fee(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            client = FakeClient()
            config = test_config(tmpdir)
            bot = D107Bot(client, config)
            bot.state = new_state()
            bot.account_id = client.account_id
            record = {
                "contract_id": "marginal",
                "lifecycle": "cancellation_window_monitoring",
                "direction": "MULTUP",
                "stake": 1.0,
                "buy_price": 1.44,
                "cancellation_fee": 0.44,
                "multiplier": 400,
                "cancellation_expiry": time.time() + 60,
            }
            bot.state["contracts"]["marginal"] = record
            # Gross profit +0.20 < 0.44 cancellation_fee (net_pnl = -0.24 < 0) -> must cancel!
            asyncio.run(
                bot.handle_boundary(
                    record,
                    {
                        "contract_id": "marginal",
                        "contract_type": "MULTUP",
                        "entry_spot": 100.0,
                        "current_spot": 100.05,
                        "profit": 0.20,
                        "bid_price": 1.20,
                        "is_valid_to_cancel": 1,
                        "is_valid_to_sell": 1,
                    },
                )
            )
            self.assertEqual(record["lifecycle"], "closed_loser")
            self.assertTrue(any("cancel" in call for call in client.calls))

            # Marginal winner below cancel_fee arriving after cancellation validity ended must NOT become held_winner
            record_missed = {
                "contract_id": "marginal-missed",
                "lifecycle": "cancellation_window_monitoring",
                "direction": "MULTUP",
                "stake": 1.0,
                "buy_price": 1.44,
                "cancellation_fee": 0.44,
                "multiplier": 400,
                "cancellation_expiry": time.time() - 5,
            }
            bot.state["contracts"]["marginal-missed"] = record_missed
            asyncio.run(
                bot.handle_boundary(
                    record_missed,
                    {
                        "contract_id": "marginal-missed",
                        "contract_type": "MULTUP",
                        "entry_spot": 100.0,
                        "current_spot": 100.05,
                        "profit": 0.20,
                        "bid_price": 1.20,
                        "is_valid_to_cancel": 0,
                        "is_valid_to_sell": 1,
                    },
                )
            )
            self.assertEqual(record_missed["lifecycle"], "cancellation_window_missed")

    def test_in_window_parabolic_take_profit_when_auto_sell_disabled(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            config = replace(
                test_config(tmpdir),
                symbol="1HZ75V",
                auto_sell_winners=True,
                in_window_auto_sell=False,
                in_window_take_profit=1.20,
            )
            bot = D107Bot(FakeClient(), config)
            record = {
                "contract_id": "parabolic",
                "buy_price": 1.08,
                "stake": 1.00,
                "cancellation_fee": 0.08,
                "peak_unrealized_pnl": 0.60,
            }
            # Sub-parabolic (+0.52 net) while in_window_auto_sell=False -> disabled
            raw_sub = {"bid_price": 1.60, "buy_price": 1.08}
            ev_sub = PnlEvidence(
                decision=PnlDecision("validated_winner", "api", 0.60, 0.60, 0.60, "test"),
                entry_spot=100.0,
                current_spot=100.60,
                bid_price=1.60,
                is_valid_to_cancel=True,
                is_valid_to_sell=True,
                contract_id="parabolic",
                raw=raw_sub,
            )
            self.assertEqual(
                bot.evaluate_winner_exit(record, raw_sub, ev_sub),
                (False, "in_window_auto_sell_disabled"),
            )

            # In-window scalp exits are abolished: positions are held to cross cancellation boundary
            raw_spike = {"bid_price": 2.40, "buy_price": 1.08}
            ev_spike = replace(ev_sub, bid_price=2.40, raw=raw_spike)
            self.assertEqual(
                bot.evaluate_winner_exit(record, raw_spike, ev_spike),
                (False, "in_window_auto_sell_disabled"),
            )

    def test_regime_direction_and_anti_exhaustion_micro_trend(self):
        import json
        import os

        with tempfile.TemporaryDirectory() as tmpdir:
            policy_file = os.path.join(tmpdir, "policy.json")
            with open(policy_file, "w") as f:
                json.dump(
                    {
                        "epoch": time.time(),
                        "deriv_primary_asset": "R_75",
                        "deriv_metrics": {
                            "1HZ75V": {
                                "hurst": 0.54,
                                "recommended_strategy": "UNCONDITIONAL_VOLATILITY_EXPANSION",
                                "recommended_direction": "MULTDOWN",
                            }
                        },
                    },
                    f,
                )
            config = replace(
                test_config(tmpdir),
                symbol="1HZ75V",
                regime_policy_file=policy_file,
                dynamic_asset_rotation=False,
            )
            client = FakeClient()
            bot = D107Bot(client, config)
            rec_sym, rec_dir = bot.get_regime_recommendations("1HZ75V")
            self.assertEqual(rec_sym, "R_75")
            self.assertEqual(rec_dir, "MULTDOWN")

            # Steady 180-tick uptrend -> MULTUP
            steady_prices = [100.0 + i * 0.01 for i in range(180)]
            client.responses["ticks_history"] = {"history": {"prices": steady_prices}}
            self.assertEqual(asyncio.run(bot.detect_realtime_micro_trend("1HZ75V")), "MULTUP")

            # Exhaustion spike in last 10 ticks (170 flat ticks then vertical jump) -> None
            exhaustion_prices = [100.0] * 170 + [100.0 + (i + 1) * 0.15 for i in range(10)]
            client.responses["ticks_history"] = {"history": {"prices": exhaustion_prices}}
            self.assertIsNone(asyncio.run(bot.detect_realtime_micro_trend("1HZ75V")))

    def test_buy_error_reconciles_and_adopts_orphan_contract(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            now = time.time()
            portfolio_calls = 0

            def portfolio_resp(_payload):
                nonlocal portfolio_calls
                portfolio_calls += 1
                # First call (pre-buy) is empty; second call (after InternalServerError) has the new contract!
                if portfolio_calls == 1:
                    return {"portfolio": {"contracts": []}}
                return {
                    "portfolio": {
                        "contracts": [
                            {
                                "contract_id": 19127889519,
                                "contract_type": "MULTUP",
                                "underlying_symbol": "1HZ10V",
                                "multiplier": 400,
                                "buy_price": 1.44,
                                "shortcode": f"MULTUP_1HZ10V_1.00_400_{int(now)}_0_5m_0.00_N1_0",
                            }
                        ]
                    }
                }

            client = FakeClient(
                responses={
                    "balance": {"balance": {"balance": 100.0}},
                    "portfolio": portfolio_resp,
                    "proposal": {
                        "proposal": {
                            "id": "prop-err",
                            "ask_price": 1.44,
                            "amount": 1.0,
                            "date_start": now,
                            "contract_type": "MULTUP",
                            "underlying": "1HZ10V",
                            "multiplier": 400,
                            "shortcode": f"MULTUP_1HZ10V_1.00_400_{int(now)}_0_5m_0.00_N1_0",
                            "cancellation": {
                                "ask_price": 0.44,
                                "date_expiry": now + 300,
                                "duration": 5,
                                "duration_unit": "m",
                            },
                        }
                    },
                    "buy": {
                        "error": {
                            "code": "InternalServerError",
                            "message": "Sorry, an error occurred while processing your request.",
                        }
                    },
                }
            )
            config = test_config(tmpdir)
            bot = D107Bot(client, config)
            bot.state = new_state()
            bot.state["new_buys_enabled"] = True
            bot.start_monitor = MagicMock()
            asyncio.run(bot.try_buy())
            self.assertIn("19127889519", bot.state["contracts"])
            adopted = bot.state["contracts"]["19127889519"]
            self.assertEqual(adopted["owner"], "d107_created")
            self.assertEqual(adopted["lifecycle"], "cancellation_window_monitoring")
            self.assertTrue(adopted["adopted_after_buy_error"])
            self.assertIsNone(bot.state["pending_buy"])
            bot.start_monitor.assert_called_once_with("19127889519")

            # Also test ambiguous TimeoutError on buy when portfolio shows the newly opened contract
            timeout_portfolio_calls = 0

            def timeout_portfolio_resp(_payload):
                nonlocal timeout_portfolio_calls
                timeout_portfolio_calls += 1
                if timeout_portfolio_calls == 1:
                    return {"portfolio": {"contracts": []}}
                return {
                    "portfolio": {
                        "contracts": [
                            {
                                "contract_id": 19127889520,
                                "contract_type": "MULTDOWN",
                                "underlying_symbol": "1HZ10V",
                                "multiplier": 400,
                                "buy_price": 1.44,
                                "shortcode": f"MULTDOWN_1HZ10V_1.00_400_{int(now)}_0_5m_0.00_N1_0",
                            }
                        ]
                    }
                }

            def raise_timeout(_payload):
                raise asyncio.TimeoutError()

            client_to = FakeClient(
                responses={
                    "balance": {"balance": {"balance": 100.0}},
                    "portfolio": timeout_portfolio_resp,
                    "proposal": {
                        "proposal": {
                            "id": "prop-to",
                            "ask_price": 1.44,
                            "amount": 1.0,
                            "date_start": now,
                            "contract_type": "MULTDOWN",
                            "underlying": "1HZ10V",
                            "multiplier": 400,
                            "shortcode": f"MULTDOWN_1HZ10V_1.00_400_{int(now)}_0_5m_0.00_N1_0",
                            "cancellation": {
                                "ask_price": 0.44,
                                "date_expiry": now + 300,
                                "duration": 5,
                                "duration_unit": "m",
                            },
                        }
                    },
                    "buy": raise_timeout,
                }
            )
            bot_to = D107Bot(client_to, config)
            bot_to.state = new_state()
            bot_to.state["next_direction"] = "MULTDOWN"
            bot_to.state["new_buys_enabled"] = True
            bot_to.start_monitor = MagicMock()
            asyncio.run(bot_to.try_buy())
            self.assertIn("19127889520", bot_to.state["contracts"])
            adopted_to = bot_to.state["contracts"]["19127889520"]
            self.assertEqual(adopted_to["owner"], "d107_created")
            self.assertEqual(adopted_to["lifecycle"], "cancellation_window_monitoring")
            self.assertIsNone(bot_to.state["pending_buy"])
            self.assertTrue(bot_to.state["new_buys_enabled"])
            bot_to.start_monitor.assert_called_once_with("19127889520")

    def test_dynamic_asset_rotation_proposal_and_portfolio(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            config = replace(
                test_config(tmpdir),
                symbol="R_100",
                dynamic_asset_rotation=True,
            )
            client = FakeClient()
            bot = D107Bot(client, config)

            # Proposal on 1HZ75V
            proposal_payload = {
                "id": "prop_75",
                "ask_price": 1.08,
                "amount": 1.00,
                "date_start": 1000.0,
                "underlying_symbol": "1HZ75V",
                "multiplier": 400,
                "contract_type": "MULTUP",
                "cancellation": {
                    "ask_price": 0.08,
                    "date_expiry": 1300.0,
                },
            }
            prop = validate_proposal(proposal_payload, config, "MULTUP", expected_symbol="1HZ75V", now=1100.0)
            self.assertEqual(prop.symbol, "1HZ75V")
            self.assertEqual(prop.cancellation_fee, 0.08)

            # Portfolio classification with 1HZ75V and 1HZ10V positions
            portfolio = [
                {
                    "contract_id": 9991,
                    "contract_type": "MULTUP",
                    "underlying_symbol": "1HZ75V",
                    "multiplier": 400,
                    "buy_price": 1.08,
                },
                {
                    "contract_id": 9992,
                    "contract_type": "MULTDOWN",
                    "underlying_symbol": "1HZ10V",
                    "multiplier": 400,
                    "buy_price": 1.44,
                },
            ]
            matching, unknown = classify_portfolio_contracts(portfolio, config)
            self.assertEqual(len(matching), 2)
            self.assertEqual(len(unknown), 0)


class TestD107Milestone3PerpetualAndTrend(unittest.TestCase):
    def test_perpetual_ratchet_standalone_all_tiers(self):
        stake = 1.0

        # Tier 0 (< 1.0x stake): No trailing stop. Guaranteed floor = 0.0, holding
        r0 = evaluate_perpetual_ratchet(profit=0.50, stake=stake, peak_profit=0.80)
        self.assertEqual(r0.current_tier, 0)
        self.assertFalse(r0.should_exit)
        self.assertEqual(r0.exit_reason, "holding")
        self.assertEqual(r0.guaranteed_floor, 0.0)

        # Tier 1 (+1.0x stake): floor locked at +0.20 * stake
        r1_hold = evaluate_perpetual_ratchet(profit=0.30, stake=stake, peak_profit=1.20)
        self.assertEqual(r1_hold.current_tier, 1)
        self.assertFalse(r1_hold.should_exit)
        self.assertAlmostEqual(r1_hold.guaranteed_floor, 0.20)

        r1_exit = evaluate_perpetual_ratchet(profit=0.18, stake=stake, peak_profit=1.20)
        self.assertEqual(r1_exit.current_tier, 1)
        self.assertTrue(r1_exit.should_exit)
        self.assertEqual(r1_exit.exit_reason, "winner_trailing_stop")

        # Tier 2 (+2.0x stake): floor ratcheted to +1.00 * stake
        r2_hold = evaluate_perpetual_ratchet(profit=1.50, stake=stake, peak_profit=2.50)
        self.assertEqual(r2_hold.current_tier, 2)
        self.assertFalse(r2_hold.should_exit)
        self.assertAlmostEqual(r2_hold.guaranteed_floor, 1.00)

        r2_exit = evaluate_perpetual_ratchet(profit=0.95, stake=stake, peak_profit=2.50)
        self.assertEqual(r2_exit.current_tier, 2)
        self.assertTrue(r2_exit.should_exit)
        self.assertEqual(r2_exit.exit_reason, "winner_trailing_stop")

        # Tier 3 (+4.0x stake): floor ratcheted to +2.50 * stake
        r3_hold = evaluate_perpetual_ratchet(profit=3.00, stake=stake, peak_profit=4.50)
        self.assertEqual(r3_hold.current_tier, 3)
        self.assertFalse(r3_hold.should_exit)
        self.assertAlmostEqual(r3_hold.guaranteed_floor, 2.50)

        r3_exit = evaluate_perpetual_ratchet(profit=2.40, stake=stake, peak_profit=4.50)
        self.assertEqual(r3_exit.current_tier, 3)
        self.assertTrue(r3_exit.should_exit)
        self.assertEqual(r3_exit.exit_reason, "winner_trailing_stop")

        # Tier 4 (+8.0x stake): Target take-profit / 80% trailing stop
        r4_tp = evaluate_perpetual_ratchet(profit=8.05, stake=stake, peak_profit=8.05)
        self.assertEqual(r4_tp.current_tier, 4)
        self.assertTrue(r4_tp.should_exit)
        self.assertEqual(r4_tp.exit_reason, "winner_exit_multiple")

        # Tier 4: Peak at 8.0, floor = max(2.50, 8.0 * 0.80) = 6.40
        r4_trail_hold = evaluate_perpetual_ratchet(profit=6.50, stake=stake, peak_profit=8.0)
        self.assertEqual(r4_trail_hold.current_tier, 4)
        self.assertFalse(r4_trail_hold.should_exit)
        self.assertAlmostEqual(r4_trail_hold.guaranteed_floor, 6.40)

        r4_trail_exit = evaluate_perpetual_ratchet(profit=6.30, stake=stake, peak_profit=8.0)
        self.assertEqual(r4_trail_exit.current_tier, 4)
        self.assertTrue(r4_trail_exit.should_exit)
        self.assertEqual(r4_trail_exit.exit_reason, "winner_trailing_stop")

    def test_trend_alignment_adx_and_ema_calculation(self):
        # Sustained monotonic uptrend: 180 prices climbing from 100 to 118
        uptrend = [100.0 + i * 0.10 for i in range(180)]
        sig_up = calculate_adx_and_trend(uptrend)
        self.assertEqual(sig_up.direction, "MULTUP")
        self.assertEqual(sig_up.macro_trend, "BULLISH")
        self.assertTrue(sig_up.is_aligned)
        self.assertGreaterEqual(sig_up.adx_value, 20.0)
        self.assertGreater(sig_up.confidence, 0.4)

        # Sustained monotonic downtrend: 180 prices falling from 120 to 102
        downtrend = [120.0 - i * 0.10 for i in range(180)]
        sig_down = calculate_adx_and_trend(downtrend)
        self.assertEqual(sig_down.direction, "MULTDOWN")
        self.assertEqual(sig_down.macro_trend, "BEARISH")
        self.assertTrue(sig_down.is_aligned)
        self.assertGreaterEqual(sig_down.adx_value, 20.0)
        self.assertGreater(sig_down.confidence, 0.4)

        # Flat/choppy oscillation: prices bouncing between 100.0 and 100.02
        chop = [100.0 + (0.02 if i % 2 == 0 else -0.02) for i in range(180)]
        sig_chop = calculate_adx_and_trend(chop)
        self.assertEqual(sig_chop.direction, "NONE")
        self.assertFalse(sig_chop.is_aligned)

    def test_trend_alignment_gating_pauses_when_unaligned(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            config = replace(test_config(tmpdir), trend_alignment_enabled=True)
            # Chop prices -> unaligned trend
            chop = [100.0 + (0.01 if i % 2 == 0 else -0.01) for i in range(180)]
            client = FakeClient(responses={"ticks_history": {"history": {"prices": chop}}})
            bot = D107Bot(client, config)
            bot.state["new_buys_enabled"] = True
            bot.state["next_direction"] = "MULTUP"
            client.account_id = "VRTC-D107-TEST"
            client.responses["portfolio"] = {"portfolio": {"contracts": []}}
            client.responses["balance"] = {"balance": {"balance": 1000.0}}

            asyncio.run(bot.try_buy())
            # Should have paused and emitted trend_alignment_pause without purchasing
            self.assertFalse(any("buy" in call for call in client.calls))
            lines = [json.loads(line) for line in Path(config.results_file).read_text().splitlines() if line.strip()]
            events = [e for e in lines if e.get("event") == "trend_alignment_pause"]
            self.assertEqual(len(events), 1)
            self.assertEqual(events[0]["reason"], "no_aligned_trend")

    def test_trend_alignment_preserves_trend_direction_in_buy_confirmed(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            now = time.time()
            config = replace(test_config(tmpdir), trend_alignment_enabled=True)
            uptrend = [100.0 + i * 0.10 for i in range(180)]
            client = FakeClient(responses={
                "ticks_history": {"history": {"prices": uptrend}},
                "portfolio": {"portfolio": {"contracts": []}},
                "balance": {"balance": {"balance": 1000.0}},
                "proposal": {
                    "proposal": {
                        "id": "prop_align",
                        "ask_price": 1.04,
                        "amount": 1.0,
                        "contract_type": "MULTUP",
                        "underlying": "1HZ10V",
                        "multiplier": 400,
                        "shortcode": f"MULTUP_1HZ10V_1.00_400_{int(now)}_0_5m_0.00_N1_0",
                        "date_start": now,
                        "spot": 118.0,
                        "cancellation": {
                            "ask_price": 0.04,
                            "date_expiry": now + 300,
                            "duration": 5,
                            "duration_unit": "m",
                        },
                    }
                },
                "buy": {"buy": {"contract_id": "c_align", "buy_price": 1.04}},
            })
            bot = D107Bot(client, config)
            bot.state["new_buys_enabled"] = True
            bot.account_id = client.account_id
            asyncio.run(bot.try_buy())

            # Verified buy went through in trend direction (MULTUP)
            self.assertIn("c_align", bot.state["contracts"])
            self.assertEqual(bot.state["contracts"]["c_align"]["direction"], "MULTUP")
            # Trend alignment must NOT mechanically alternate to MULTDOWN!
            self.assertEqual(bot.state["next_direction"], "MULTUP")

    def test_boundary_qualification_defensively_cancels_when_contrary_trend(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            config = replace(test_config(tmpdir), trend_alignment_enabled=True)
            # Market entered strong downtrend (120 -> 102)
            downtrend = [120.0 - i * 0.10 for i in range(180)]
            client = FakeClient(responses={
                "ticks_history": {"history": {"prices": downtrend}},
                "cancel": {"cancel": {"sold_for": 1.0}},
            })
            bot = D107Bot(client, config)
            bot.state = new_state()
            bot.account_id = client.account_id

            # Position is MULTUP, has net_profit (+0.12 >= 0.04 fee) but market trend is MULTDOWN
            record = {
                "contract_id": "contrary",
                "lifecycle": "cancellation_window_monitoring",
                "direction": "MULTUP",
                "stake": 1.0,
                "buy_price": 1.04,
                "cancellation_fee": 0.04,
                "multiplier": 400,
                "cancellation_expiry": time.time() + 60,
            }
            bot.state["contracts"]["contrary"] = record
            raw = {
                "contract_id": "contrary",
                "contract_type": "MULTUP",
                "entry_spot": 100.0,
                "current_spot": 100.04,
                "profit": 0.16,  # net = 0.12 >= 0.04 fee
                "bid_price": 1.16,
                "is_valid_to_cancel": 1,
                "is_valid_to_sell": 1,
            }
            asyncio.run(bot.handle_boundary(record, raw))
            # Because trend momentum is contrary (MULTDOWN vs MULTUP), it cancels defensively!
            self.assertEqual(record["lifecycle"], "closed_loser")
            self.assertTrue(any("cancel" in call for call in client.calls))

    def test_boundary_qualification_transitions_to_held_winner_when_qualified(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            config = replace(test_config(tmpdir), trend_alignment_enabled=True)
            # Market is in strong uptrend (100 -> 118)
            uptrend = [100.0 + i * 0.10 for i in range(180)]
            client = FakeClient(responses={
                "ticks_history": {"history": {"prices": uptrend}},
            })
            bot = D107Bot(client, config)
            bot.state = new_state()
            bot.account_id = client.account_id
            bot.monitor_held_winner = AsyncMock()

            # Position is MULTUP, net_profit (+0.16 >= 0.04 fee), and trend agrees (MULTUP)
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
                "current_spot": 100.05,
                "profit": 0.20,  # net = 0.16 >= 0.04 fee
                "bid_price": 1.20,
                "is_valid_to_cancel": 1,
                "is_valid_to_sell": 1,
            }
            asyncio.run(bot.handle_boundary(record, raw))
            # Fully qualified -> transitions to held_winner!
            self.assertEqual(record["lifecycle"], "held_winner")
            self.assertEqual(bot.state["machine_state"], "HELD_WINNER")
            bot.monitor_held_winner.assert_awaited_once()


if __name__ == "__main__":
    unittest.main(verbosity=2)
