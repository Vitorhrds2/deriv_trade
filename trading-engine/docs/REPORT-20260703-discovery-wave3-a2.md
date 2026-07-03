# REPORT-20260703 - Discovery A2 Wave 3

Status: closed_no_challenger_promoted

Job: `JOB-20260703-012-DISCOVERY-A2-W3-PRIORITY`
Account: Deriv demo `_2`
Market: `1HZ10V`
Real money: blocked
Default stake: `$10`
Drawdown gate: `$40`
Dashboard: `http://127.0.0.1:8766`

## Objective

Search for a challenger able to beat the benchmark model
`reversal_3tick_minmove020_1HZ10V` after its 1000-trade demo result. The wave
tested lower threshold, direction filters, increased stake, block-regime guards,
and an adaptive agent that paper-scores sub-rules before live demo execution.

## Benchmark

`reversal_3tick_minmove020_1HZ10V` remains the benchmark:

- 1000 trades, 533 wins / 467 losses
- PnL `+$23.36` at stake `$1`
- EV/trade `+$0.02336`
- ROI `+2.34%`
- max drawdown `-$23.08`
- decision: benchmark / collect_more, not real-money, not stake increase

## Wave 3 Results

| idx | model | phase reached | trades | W/L | WR | PnL | EV/trade | ROI | peak | max DD | decision |
|---:|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| 25 | `reversal_3tick_minmove016_1HZ10V_w3` | gate30 | 24 | 13/11 | 54.17% | +$9.99 | +$0.416 | +4.16% | +$59.99 | -$50.00 | failed_gate30_drawdown_early |
| 26 | `reversal_3tick_minmove018_CALLonly_1HZ10V_w3` | gate30 | 22 | 11/11 | 50.00% | -$8.47 | -$0.385 | -3.85% | +$33.07 | -$41.54 | failed_gate30_drawdown_early |
| 27 | `reversal_3tick_minmove018_PUTonly_1HZ10V_w3` | gate30 | 7 | 2/5 | 28.57% | -$31.54 | -$4.506 | -45.06% | +$18.46 | -$50.00 | failed_gate30_drawdown_early |
| 28 | `reversal_3tick_minmove020_stake15_1HZ10V_w3` | gate30 | 12 | 7/5 | 58.33% | +$21.95 | +$1.829 | +12.19% | +$66.95 | -$45.00 | failed_gate30_drawdown_early |
| 29 | `reversal_3tick_minmove020_guard_1HZ10V_w3` | target100 | 38 | 23/15 | 60.53% | +$62.29 | +$1.639 | +16.39% | +$112.29 | -$50.00 | failed_100_drawdown_early |
| 30 | `reversal_3tick_minmove018_guard_CALLonly_1HZ10V_w3` | gate30 | 12 | 5/7 | 41.67% | -$23.85 | -$1.988 | -19.88% | +$18.46 | -$42.31 | failed_gate30_drawdown_early |
| 31 | `reversal_3tick_minmove018_guard_PUTonly_1HZ10V_w3` | gate30 | 16 | 8/8 | 50.00% | -$6.16 | -$0.385 | -3.85% | +$36.15 | -$42.31 | failed_gate30_drawdown_early |
| 32 | `adaptive_agent_tick_research_1HZ10V_w3` | gate30 | 4 | 0/4 | 0.00% | -$40.00 | -$10.000 | -100.00% | $0.00 | -$40.00 | model_kill_loss |

## Findings

The lower threshold alone did not solve robustness. `minmove016` and `minmove018`
could create positive bursts but crossed the drawdown gate before 30 trades.

Direction filters made the result worse. CALL-only and PUT-only variants both
failed early, with no evidence that one side carried the champion edge.

Increasing stake amplified the same block problem. The stake `$15` model peaked
at `+$66.95`, but failed early drawdown at trade 12.

The block guard was the only meaningful improvement. It passed gate30 with
`+$103.83` after 30 trades and reached `+$112.29` peak, but failed target100 at
trade 38 after a drawdown to `-$50.00`. This makes it a useful research lead,
not a promoted model.

The adaptive agent failed immediately. It selected `mr5_018` from paper scoring
(`score=8.0`, `samples=58`) and then lost four live demo trades in a row. That
is a live warning against trusting the current paper-score rule selector.

## Decision

No challenger beat the benchmark under the required 30 -> 100 gate.

`reversal_3tick_minmove020_guard_1HZ10V_w3` is the best failed candidate and
should seed the next wave, but it cannot be promoted because it failed the
target100 drawdown gate.

## Next Wave

Recommended next candidates:

- `guard_v2`: same champion rule, but with a stricter post-hot-block pause and
  a trailing protection rule after gate30.
- `guard_target100_lock`: after passing gate30, stop or de-risk if peak-to-trough
  exceeds `$25` before 100 trades.
- `guard_two_loss_pause`: pause after two consecutive losses or after a bad
  5-trade block, instead of waiting for full drawdown failure.
- `adaptive_agent_v2`: require live probation for a selected rule before it can
  use full stake; paper-score alone is not enough.

All candidates remain demo-only.
