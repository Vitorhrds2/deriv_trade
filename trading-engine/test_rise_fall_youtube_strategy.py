import unittest
from dataclasses import replace

from rise_fall_youtube_strategy import (
    CALL,
    PUT,
    Candle,
    SIGNAL_FUNCTIONS,
    STRATEGIES,
    Trade,
    backtest_strategy,
    build_context,
    candles_from_dicts,
    invert_trades,
    randomize_trades,
    simulate_bankroll,
    summarize_trades,
)


def make_trend_candles(count=600, direction=1, start=100.0):
    candles = []
    price = start
    for index in range(count):
        open_price = price
        close_price = open_price + direction * 0.5
        high = max(open_price, close_price) + 0.1
        low = min(open_price, close_price) - 0.1
        candles.append(Candle(1_700_000_000 + index * 60, open_price, high, low, close_price))
        price = close_price
    return candles


def make_trade(won, epoch, direction=CALL, payout=1.96):
    entry = 100.0
    exit_price = 101.0 if (won and direction == CALL) or (not won and direction == PUT) else 99.0
    return Trade(
        strategy="test",
        symbol="TEST",
        signal_epoch=epoch - 60,
        entry_epoch=epoch,
        exit_epoch=epoch + 60,
        direction=direction,
        entry_price=entry,
        exit_price=exit_price,
        payout=payout,
        won=won,
    )


class TestCandleNormalization(unittest.TestCase):
    def test_sorts_and_deduplicates_by_epoch(self):
        records = [
            {"epoch": 120, "open": 2, "high": 3, "low": 1, "close": 2.5},
            {"epoch": 60, "open": 1, "high": 2, "low": 0, "close": 1.5},
            {"epoch": 120, "open": 4, "high": 5, "low": 3, "close": 4.5},
        ]
        candles = candles_from_dicts(records)
        self.assertEqual([candle.epoch for candle in candles], [60, 120])
        self.assertEqual(candles[-1].open, 4.0)


class TestSignals(unittest.TestCase):
    def test_strict_mtf_follows_rising_market(self):
        candles = make_trend_candles()
        signal = SIGNAL_FUNCTIONS["mtf_strict_15m"](candles, 240, build_context(candles))
        self.assertEqual(signal, CALL)

    def test_strict_mtf_follows_falling_market(self):
        candles = make_trend_candles(direction=-1)
        signal = SIGNAL_FUNCTIONS["mtf_strict_15m"](candles, 240, build_context(candles))
        self.assertEqual(signal, PUT)

    def test_signal_does_not_use_future_candles(self):
        candles = make_trend_candles()
        before = SIGNAL_FUNCTIONS["mtf_strict_15m"](candles, 240, build_context(candles))
        changed = candles[:241] + make_trend_candles(count=len(candles) - 241, direction=-1, start=20.0)
        changed = [replace(candle, epoch=candles[index].epoch) for index, candle in enumerate(changed)]
        after = SIGNAL_FUNCTIONS["mtf_strict_15m"](changed, 240, build_context(changed))
        self.assertEqual(before, after)

    def test_support_resistance_touch_is_contrarian(self):
        candles = [Candle(1_700_000_000 + index * 60, 100, 101, 99, 100) for index in range(60)]
        candles.append(Candle(1_700_003_600, 100, 102, 99.5, 101.5))
        signal = SIGNAL_FUNCTIONS["sr_touch_15m"](candles, 60, build_context(candles))
        self.assertEqual(signal, PUT)

    def test_support_resistance_rejection_requires_reversal_candle(self):
        candles = [Candle(1_700_000_000 + index * 60, 100, 101, 99, 100) for index in range(60)]
        candles.append(Candle(1_700_003_600, 101.5, 102, 99.5, 100))
        signal = SIGNAL_FUNCTIONS["sr_rejection_15m"](candles, 60, build_context(candles))
        self.assertEqual(signal, PUT)


class TestReplay(unittest.TestCase):
    def test_entry_is_next_open_and_positions_do_not_overlap(self):
        candles = make_trend_candles()
        spec = next(spec for spec in STRATEGIES if spec.name == "mtf_strict_15m")
        trades = backtest_strategy(candles, "TEST", spec, payout=1.96)
        self.assertGreater(len(trades), 1)
        first = trades[0]
        self.assertEqual(first.entry_epoch, first.signal_epoch + 60)
        self.assertEqual(first.exit_epoch, first.entry_epoch + 15 * 60)
        for previous, current in zip(trades, trades[1:]):
            self.assertGreaterEqual(current.entry_epoch, previous.exit_epoch)
        self.assertTrue(all(trade.won for trade in trades))

    def test_gap_invalidates_trade(self):
        candles = make_trend_candles()
        candles[250] = replace(candles[250], epoch=candles[250].epoch + 30)
        spec = next(spec for spec in STRATEGIES if spec.name == "mtf_strict_15m")
        trades = backtest_strategy(candles, "TEST", spec, payout=1.96)
        self.assertTrue(all(trade.exit_epoch - trade.entry_epoch == 15 * 60 for trade in trades))


class TestStatisticsAndRisk(unittest.TestCase):
    def test_summary_uses_payout_and_break_even(self):
        trades = [make_trade(index < 700, 1_700_000_000 + index * 60, payout=2.0) for index in range(1000)]
        summary = summarize_trades(trades)
        self.assertAlmostEqual(summary["win_rate"], 0.7)
        self.assertAlmostEqual(summary["ev_per_stake"], 0.4)
        self.assertAlmostEqual(summary["break_even_win_rate"], 0.5)
        self.assertEqual(summary["verdict"], "confirmed")

    def test_inverted_signal_recomputes_outcome(self):
        trades = [make_trade(True, 1_700_000_000), make_trade(False, 1_700_000_060)]
        inverted = invert_trades(trades)
        self.assertEqual([trade.won for trade in inverted], [False, True])
        self.assertEqual([trade.direction for trade in inverted], [PUT, PUT])

    def test_random_control_is_deterministic(self):
        trades = [make_trade(True, 1_700_000_000 + index * 60) for index in range(20)]
        first = randomize_trades(trades, seed=42)
        second = randomize_trades(trades, seed=42)
        self.assertEqual(first, second)

    def test_martingale_ruins_bankroll_on_loss_streak(self):
        losses = [make_trade(False, 1_700_000_000 + index * 60) for index in range(7)]
        result = simulate_bankroll(losses, multiplier=2.0, initial_bankroll=100.0, base_stake=1.0)
        self.assertTrue(result["ruined"])
        self.assertEqual(result["trades_executed"], 6)
        self.assertEqual(result["final_bankroll"], 37.0)
        self.assertEqual(result["peak_stake"], 64.0)

    def test_flat_stake_survives_same_loss_streak(self):
        losses = [make_trade(False, 1_700_000_000 + index * 60) for index in range(7)]
        result = simulate_bankroll(losses, multiplier=1.0, initial_bankroll=100.0, base_stake=1.0)
        self.assertFalse(result["ruined"])
        self.assertEqual(result["final_bankroll"], 93.0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
