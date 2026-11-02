from dataclasses import asdict, dataclass, replace
import hashlib
from typing import Callable

from stats_utils import wilson_ci


CALL = "CALL"
PUT = "PUT"


@dataclass(frozen=True)
class Candle:
    epoch: int
    open: float
    high: float
    low: float
    close: float


@dataclass(frozen=True)
class StrategySpec:
    name: str
    duration_minutes: int
    primary: bool
    description: str


@dataclass(frozen=True)
class Trade:
    strategy: str
    symbol: str
    signal_epoch: int
    entry_epoch: int
    exit_epoch: int
    direction: str
    entry_price: float
    exit_price: float
    payout: float
    won: bool


STRATEGIES = (
    StrategySpec(
        "mtf_strict_15m",
        15,
        True,
        "4h, 1h e 5m na mesma direcao; vela de 1m confirma; contrato de 15m",
    ),
    StrategySpec(
        "mtf_majority_15m",
        15,
        False,
        "maioria entre 4h, 1h e 5m; vela de 1m confirma; contrato de 15m",
    ),
    StrategySpec(
        "sr_touch_15m",
        15,
        False,
        "toque na maxima/minima previa de 60m; reversao contraria por 15m",
    ),
    StrategySpec(
        "sr_rejection_15m",
        15,
        False,
        "toque na maxima/minima previa de 60m com candle de rejeicao; reversao por 15m",
    ),
    StrategySpec(
        "indicator_consensus_5m",
        5,
        False,
        "ADX>=25 e consenso 3/4 entre EMA, MACD, RSI e media de 20; contrato de 5m",
    ),
    StrategySpec(
        "indicator_consensus_10m",
        10,
        False,
        "ADX>=25 e consenso 3/4 entre EMA, MACD, RSI e media de 20; contrato de 10m",
    ),
    StrategySpec(
        "multifactor_score_5m",
        5,
        False,
        "Multi-factor scoring: RSI(14)+BB(20,2)+ROC(5)+direction reversal+local max/min; score>=6; contrato de 5m",
    ),
    StrategySpec(
        "multifactor_score_10m",
        10,
        False,
        "Multi-factor scoring: RSI(14)+BB(20,2)+ROC(5)+direction reversal+local max/min; score>=6; contrato de 10m",
    ),
)


def candles_from_dicts(records):
    unique = {}
    for record in records:
        candle = Candle(
            epoch=int(record["epoch"]),
            open=float(record["open"]),
            high=float(record["high"]),
            low=float(record["low"]),
            close=float(record["close"]),
        )
        unique[candle.epoch] = candle
    return [unique[epoch] for epoch in sorted(unique)]


def candles_to_dicts(candles):
    return [asdict(candle) for candle in candles]


def _sign(value):
    if value > 0:
        return 1
    if value < 0:
        return -1
    return 0


def _ema(values, period):
    if not values:
        return []
    alpha = 2.0 / (period + 1)
    output = [float(values[0])]
    for value in values[1:]:
        output.append(alpha * value + (1 - alpha) * output[-1])
    return output


def _rolling_sma(values, period):
    output = [None] * len(values)
    running = 0.0
    for index, value in enumerate(values):
        running += value
        if index >= period:
            running -= values[index - period]
        if index >= period - 1:
            output[index] = running / period
    return output


def _rolling_rsi(values, period=14):
    output = [None] * len(values)
    gains = [0.0] * len(values)
    losses = [0.0] * len(values)
    for index in range(1, len(values)):
        change = values[index] - values[index - 1]
        gains[index] = max(change, 0.0)
        losses[index] = max(-change, 0.0)
    gain_sum = 0.0
    loss_sum = 0.0
    for index in range(1, len(values)):
        gain_sum += gains[index]
        loss_sum += losses[index]
        if index > period:
            gain_sum -= gains[index - period]
            loss_sum -= losses[index - period]
        if index >= period:
            if loss_sum == 0:
                output[index] = 100.0 if gain_sum > 0 else 50.0
            else:
                relative_strength = gain_sum / loss_sum
                output[index] = 100.0 - 100.0 / (1.0 + relative_strength)
    return output


def _rolling_adx(candles, period=14):
    count = len(candles)
    true_ranges = [0.0] * count
    plus_dm = [0.0] * count
    minus_dm = [0.0] * count
    for index in range(1, count):
        current = candles[index]
        previous = candles[index - 1]
        true_ranges[index] = max(
            current.high - current.low,
            abs(current.high - previous.close),
            abs(current.low - previous.close),
        )
        up_move = current.high - previous.high
        down_move = previous.low - current.low
        plus_dm[index] = up_move if up_move > down_move and up_move > 0 else 0.0
        minus_dm[index] = down_move if down_move > up_move and down_move > 0 else 0.0
    dx = [None] * count
    tr_sum = 0.0
    plus_sum = 0.0
    minus_sum = 0.0
    for index in range(1, count):
        tr_sum += true_ranges[index]
        plus_sum += plus_dm[index]
        minus_sum += minus_dm[index]
        if index > period:
            tr_sum -= true_ranges[index - period]
            plus_sum -= plus_dm[index - period]
            minus_sum -= minus_dm[index - period]
        if index >= period and tr_sum > 0:
            plus_di = 100.0 * plus_sum / tr_sum
            minus_di = 100.0 * minus_sum / tr_sum
            denominator = plus_di + minus_di
            dx[index] = 100.0 * abs(plus_di - minus_di) / denominator if denominator else 0.0
    output = [None] * count
    window = []
    for index, value in enumerate(dx):
        if value is not None:
            window.append(value)
        if len(window) > period:
            window.pop(0)
        if len(window) == period:
            output[index] = sum(window) / period
    return output


def _rolling_std(values, period):
    output = [None] * len(values)
    for index in range(period - 1, len(values)):
        window = values[index - period + 1:index + 1]
        mean = sum(window) / period
        variance = sum((value - mean) ** 2 for value in window) / period
        output[index] = variance ** 0.5
    return output


def _rolling_roc(values, period=5):
    output = [None] * len(values)
    for index in range(period, len(values)):
        prev = values[index - period]
        if prev != 0:
            output[index] = (values[index] - prev) / prev
        else:
            output[index] = 0.0
    return output


def build_context(candles):
    closes = [candle.close for candle in candles]
    ema12 = _ema(closes, 12)
    ema26 = _ema(closes, 26)
    macd = [fast - slow for fast, slow in zip(ema12, ema26)]
    macd_signal = _ema(macd, 9)
    sma20 = _rolling_sma(closes, 20)
    std20 = _rolling_std(closes, 20)
    bb_upper = [s + 2 * sd if s is not None and sd is not None else None for s, sd in zip(sma20, std20)]
    bb_lower = [s - 2 * sd if s is not None and sd is not None else None for s, sd in zip(sma20, std20)]
    return {
        "ema12": ema12,
        "ema26": ema26,
        "macd_hist": [value - signal for value, signal in zip(macd, macd_signal)],
        "rsi14": _rolling_rsi(closes, 14),
        "sma20": sma20,
        "adx14": _rolling_adx(candles, 14),
        "bb_upper": bb_upper,
        "bb_lower": bb_lower,
        "roc5": _rolling_roc(closes, 5),
    }


def _mtf_strict(candles, index, context):
    if index < 240:
        return None
    directions = [_sign(candles[index].close - candles[index - window].close) for window in (240, 60, 5)]
    execution = _sign(candles[index].close - candles[index].open)
    if directions[0] and len(set(directions)) == 1 and execution == directions[0]:
        return CALL if execution > 0 else PUT
    return None


def _mtf_majority(candles, index, context):
    if index < 240:
        return None
    directions = [_sign(candles[index].close - candles[index - window].close) for window in (240, 60, 5)]
    balance = sum(directions)
    majority = 1 if balance >= 2 else -1 if balance <= -2 else 0
    execution = _sign(candles[index].close - candles[index].open)
    if majority and execution == majority:
        return CALL if majority > 0 else PUT
    return None


def _sr_touch(candles, index, context):
    if index < 60:
        return None
    prior = candles[index - 60:index]
    resistance = max(candle.high for candle in prior)
    support = min(candle.low for candle in prior)
    candle = candles[index]
    upper_touch = candle.high >= resistance
    lower_touch = candle.low <= support
    body = _sign(candle.close - candle.open)
    if upper_touch and not lower_touch and body > 0:
        return PUT
    if lower_touch and not upper_touch and body < 0:
        return CALL
    return None


def _sr_rejection(candles, index, context):
    if index < 60:
        return None
    prior = candles[index - 60:index]
    resistance = max(candle.high for candle in prior)
    support = min(candle.low for candle in prior)
    candle = candles[index]
    upper_touch = candle.high >= resistance
    lower_touch = candle.low <= support
    body = _sign(candle.close - candle.open)
    if upper_touch and not lower_touch and body < 0:
        return PUT
    if lower_touch and not upper_touch and body > 0:
        return CALL
    return None


def _indicator_consensus(candles, index, context):
    if index < 40:
        return None
    required = (context["rsi14"][index], context["sma20"][index], context["adx14"][index])
    if any(value is None for value in required) or context["adx14"][index] < 25.0:
        return None
    up_votes = sum((
        context["ema12"][index] > context["ema26"][index],
        context["macd_hist"][index] > 0,
        context["rsi14"][index] > 50.0,
        candles[index].close > context["sma20"][index],
    ))
    if up_votes >= 3:
        return CALL
    if up_votes <= 1:
        return PUT
    return None


def _multifactor_score(candles, index, context):
    if index < 25:
        return None
    rsi = context["rsi14"][index]
    bb_upper = context["bb_upper"][index]
    bb_lower = context["bb_lower"][index]
    sma = context["sma20"][index]
    roc = context["roc5"][index]
    if any(value is None for value in (rsi, bb_upper, bb_lower, sma, roc)):
        return None
    close = candles[index].close
    bb_width = bb_upper - bb_lower
    if bb_width <= 0:
        return None
    upper_70 = sma + 0.7 * (bb_upper - sma)
    lower_70 = sma - 0.7 * (sma - bb_lower)
    fall_score = 0
    rise_score = 0
    if rsi > 78:
        fall_score += 3
    elif rsi > 70:
        fall_score += 2
    if rsi < 22:
        rise_score += 3
    elif rsi < 30:
        rise_score += 2
    if close >= bb_upper:
        fall_score += 3
    elif close >= upper_70:
        fall_score += 1
    if close <= bb_lower:
        rise_score += 3
    elif close <= lower_70:
        rise_score += 1
    if roc < -0.02:
        fall_score += 2
    if roc > 0.02:
        rise_score += 2
    if index >= 2:
        prev_dir = _sign(candles[index - 1].close - candles[index - 2].close)
        curr_dir = _sign(close - candles[index - 1].close)
        if prev_dir > 0 and curr_dir < 0:
            fall_score += 2
        if prev_dir < 0 and curr_dir > 0:
            rise_score += 2
    if index >= 20:
        local_max = max(candles[index - 20].close, candles[index].close)
        local_min = min(candles[index - 20].close, candles[index].close)
        for candle in candles[index - 19:index]:
            local_max = max(local_max, candle.close)
            local_min = min(local_min, candle.close)
        if close >= local_max:
            fall_score += 1
        if close <= local_min:
            rise_score += 1
    if fall_score >= 6 and fall_score > rise_score:
        return PUT
    if rise_score >= 6 and rise_score > fall_score:
        return CALL
    return None


SIGNAL_FUNCTIONS: dict[str, Callable] = {
    "mtf_strict_15m": _mtf_strict,
    "mtf_majority_15m": _mtf_majority,
    "sr_touch_15m": _sr_touch,
    "sr_rejection_15m": _sr_rejection,
    "indicator_consensus_5m": _indicator_consensus,
    "indicator_consensus_10m": _indicator_consensus,
    "multifactor_score_5m": _multifactor_score,
    "multifactor_score_10m": _multifactor_score,
}


def _won(direction, entry_price, exit_price):
    return exit_price > entry_price if direction == CALL else exit_price < entry_price


def backtest_strategy(candles, symbol, spec, payout=1.96):
    context = build_context(candles)
    signal_function = SIGNAL_FUNCTIONS[spec.name]
    trades = []
    next_entry_index = 0
    for signal_index in range(len(candles)):
        entry_index = signal_index + 1
        exit_index = entry_index + spec.duration_minutes
        if exit_index >= len(candles) or entry_index < next_entry_index:
            continue
        direction = signal_function(candles, signal_index, context)
        if direction is None:
            continue
        entry = candles[entry_index]
        exit_candle = candles[exit_index]
        interval = candles[signal_index:exit_index + 1]
        if any(right.epoch - left.epoch != 60 for left, right in zip(interval, interval[1:])):
            continue
        trade = Trade(
            strategy=spec.name,
            symbol=symbol,
            signal_epoch=candles[signal_index].epoch,
            entry_epoch=entry.epoch,
            exit_epoch=exit_candle.epoch,
            direction=direction,
            entry_price=entry.open,
            exit_price=exit_candle.open,
            payout=float(payout),
            won=_won(direction, entry.open, exit_candle.open),
        )
        trades.append(trade)
        next_entry_index = exit_index
    return trades


def _maximum_loss_streak(trades):
    maximum = 0
    current = 0
    for trade in trades:
        if trade.won:
            current = 0
        else:
            current += 1
            maximum = max(maximum, current)
    return maximum


def summarize_trades(trades, minimum_n=100):
    count = len(trades)
    if not count:
        return {
            "n": 0,
            "wins": 0,
            "win_rate": 0.0,
            "win_rate_ci95": [0.0, 0.0],
            "ev_per_stake": 0.0,
            "ev_ci95": [0.0, 0.0],
            "break_even_win_rate": 0.0,
            "max_loss_streak": 0,
            "verdict": "insufficient",
        }
    profits = [(trade.payout - 1.0) if trade.won else -1.0 for trade in trades]
    wins = sum(trade.won for trade in trades)
    wr_low, wr_high = wilson_ci(wins, count)
    ev = sum(profits) / count
    average_payout = sum(trade.payout for trade in trades) / count
    ev_low = wr_low * average_payout - 1.0
    ev_high = wr_high * average_payout - 1.0
    if count >= minimum_n and ev_low > 0:
        verdict = "confirmed"
    elif count >= minimum_n and ev_high < 0:
        verdict = "refuted"
    else:
        verdict = "inconclusive"
    return {
        "n": count,
        "wins": wins,
        "win_rate": wins / count,
        "win_rate_ci95": [wr_low, wr_high],
        "ev_per_stake": ev,
        "ev_ci95": [ev_low, ev_high],
        "break_even_win_rate": 1.0 / average_payout,
        "max_loss_streak": _maximum_loss_streak(trades),
        "verdict": verdict,
    }


def invert_trades(trades):
    output = []
    for trade in trades:
        direction = PUT if trade.direction == CALL else CALL
        output.append(replace(trade, direction=direction, won=_won(direction, trade.entry_price, trade.exit_price)))
    return output


def randomize_trades(trades, seed=20260713):
    output = []
    for trade in trades:
        digest = hashlib.sha256(
            f"{seed}:{trade.strategy}:{trade.symbol}:{trade.entry_epoch}".encode("utf-8")
        ).digest()
        direction = CALL if int.from_bytes(digest[:8], "big") % 2 == 0 else PUT
        output.append(replace(trade, direction=direction, won=_won(direction, trade.entry_price, trade.exit_price)))
    return output


def simulate_bankroll(trades, multiplier, initial_bankroll=100.0, base_stake=1.0):
    bankroll = float(initial_bankroll)
    peak = bankroll
    max_drawdown = 0.0
    loss_level = 0
    peak_stake = 0.0
    executed = 0
    ruined = False
    for trade in trades:
        stake = base_stake * (multiplier ** loss_level)
        peak_stake = max(peak_stake, stake)
        if stake > bankroll:
            ruined = True
            break
        executed += 1
        if trade.won:
            bankroll += stake * (trade.payout - 1.0)
            loss_level = 0
        else:
            bankroll -= stake
            loss_level += 1
        peak = max(peak, bankroll)
        if peak > 0:
            max_drawdown = max(max_drawdown, (peak - bankroll) / peak)
        if bankroll <= 0:
            ruined = True
            break
    return {
        "initial_bankroll": initial_bankroll,
        "base_stake": base_stake,
        "multiplier": multiplier,
        "trades_executed": executed,
        "final_bankroll": bankroll,
        "return_pct": (bankroll / initial_bankroll - 1.0) * 100.0,
        "max_drawdown_pct": max_drawdown * 100.0,
        "peak_stake": peak_stake,
        "ruined": ruined,
    }


def build_strategy_report(trades, oos_start_epoch, seed=20260713):
    in_sample = [trade for trade in trades if trade.entry_epoch < oos_start_epoch]
    out_of_sample = [trade for trade in trades if trade.entry_epoch >= oos_start_epoch]
    return {
        "all": summarize_trades(trades),
        "in_sample": summarize_trades(in_sample),
        "out_of_sample": summarize_trades(out_of_sample),
        "controls_oos": {
            "anti_signal": summarize_trades(invert_trades(out_of_sample)),
            "random_direction": summarize_trades(randomize_trades(out_of_sample, seed=seed)),
        },
        "bankroll_oos": {
            "flat_1pct": simulate_bankroll(out_of_sample, multiplier=1.0),
            "martingale_2x": simulate_bankroll(out_of_sample, multiplier=2.0),
        },
        "trades": [asdict(trade) for trade in trades],
    }


def pooled_report(reports, strategy_name, split="out_of_sample", seed=20260713):
    trades = []
    for symbol_report in reports.values():
        strategy_report = symbol_report["strategies"][strategy_name]
        cutoff = symbol_report["data"]["oos_start_epoch"]
        strategy_trades = [Trade(**record) for record in strategy_report["trades"]]
        if split == "out_of_sample":
            strategy_trades = [trade for trade in strategy_trades if trade.entry_epoch >= cutoff]
        elif split == "in_sample":
            strategy_trades = [trade for trade in strategy_trades if trade.entry_epoch < cutoff]
        trades.extend(strategy_trades)
    trades.sort(key=lambda trade: (trade.entry_epoch, trade.symbol))
    return {
        "observed": summarize_trades(trades),
        "anti_signal": summarize_trades(invert_trades(trades)),
        "random_direction": summarize_trades(randomize_trades(trades, seed=seed)),
        "bankroll": {
            "flat_1pct": simulate_bankroll(trades, multiplier=1.0),
            "martingale_2x": simulate_bankroll(trades, multiplier=2.0),
        },
    }
