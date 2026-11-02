# Challenger 1 Handoff Report — Adversarial Verification of 4-Tier Perpetual Ratchet & Boundary Qualification

## 1. Observation

1. **Target Modules & Code Inspection**:
   - `trading-engine/d107_rate_limit_winner_holding.py`:
     * Line 866-927: `evaluate_perpetual_ratchet(profit, stake, peak_profit, take_profit_multiple=8.0)` defines 4 progressive tiers: Tier 0 (< 1.0x stake, floor = 0.0, holding), Tier 1 (>= 1.0x stake, floor = 0.20 * stake), Tier 2 (>= 2.0x stake, floor = 1.00 * stake), Tier 3 (>= 4.0x stake, floor = 2.50 * stake), Tier 4 (>= 8.0x stake, target take-profit / 80% trailing stop).
     * Line 2634-2642: `evaluate_winner_exit()` intra-window check: `if evidence.is_valid_to_cancel is True: if not self.config.in_window_auto_sell: return False, "in_window_auto_sell_disabled"`.
     * Line 2415-2443: `handle_boundary()` boundary classification gate: computes `net_profit = round(gross_profit - cancel_fee, 10)`, checks `if net_profit < cancel_fee or not trend_supports: await self.cancel_loser(...)`.
   - `trading-engine/d107_exact_historical_simulation.py`:
     * Line 377-383: Pre-boundary window handling: inside the 300s window, `perpetual_ladder_1x_8x` executes no early micro-scalp sales.
     * Line 390-410: Boundary qualification: `net_profit = mark - position.cancellation_fee`; cancels if `net_profit < position.cancellation_fee or not trend_ok`.
     * Line 440-465: Post-boundary held winner ratchet: implements identical progressive floors (Tier 1: 0.20, Tier 2: 1.00, Tier 3: 2.50, Tier 4: max(2.50, peak * 0.80) / target take-profit at 8.0x).

2. **Empirical Verification Suite Execution**:
   - Created comprehensive adversarial test harness: `trading-engine/test_d107_adversarial_challenger.py` containing 19 stress tests.
   - Command:
     ```bash
     PYTHONPATH=trading-engine python3 -m unittest trading-engine/test_d107_adversarial_challenger.py
     ```
   - Verbatim Output:
     ```
     ...................
     ----------------------------------------------------------------------
     Ran 19 tests in 0.130s

     OK
     ```
   - Full discovery test suite across entire trading engine:
     ```bash
     PYTHONPATH=trading-engine python3 -m unittest discover -s trading-engine -p "test_d107_*.py"
     ```
   - Verbatim Output:
     ```
     Ran 94 tests in 1.742s

     OK
     ```
   - 24-hour historical tick replay (`trading-engine/d107_simulation_1hz10v_ticks.json`):
     ```bash
     PYTHONPATH=trading-engine python3 -c '
     from d107_exact_historical_simulation import run_simulation
     r = run_simulation("trading-engine/d107_simulation_1hz10v_ticks.json", exit_scenario="perpetual_ladder_1x_8x", trend_alignment_enabled=True)
     d = r.as_dict()
     print(f"Buys: {d[\"buys\"]}, Net: ${d[\"realized_net\"]:.2f}, E[PnL]: ${d[\"expected_net_per_trade\"]:.4f}, PF: {d[\"profit_factor\"]:.2f}, Runners >= 1x: {d[\"runners_1x\"]}")
     '
     ```
   - Verbatim Output:
     ```
     Buys: 78, Net: $5.04, E[PnL]: $0.0646, PF: 2.11, Runners >= 1x: 10
     ```

## 2. Logic Chain

1. **Ratchet Threshold Boundary Conditions**:
   - Exact numerical boundaries (`0.99x, 1.00x, 1.01x, 1.99x, 2.00x, 2.01x, 3.99x, 4.00x, 4.01x, 7.99x, 8.00x, 8.01x`) were swept with variable stakes ($0.50, $1.00, $2.00, $10.00).
   - *Tier 0 (< 1.00x)*: Peak at 0.99x assigns `current_tier = 0`, `guaranteed_floor = 0.0`. Pullbacks to 0.80x, 0.50x, 0.20x, 0.0x, and down to -0.34x strictly evaluate to `should_exit = False`, providing full breathing room to ride the developing macro trend without premature trailing stop shakeouts.
   - *Tier 1 ([1.00x, 2.00x))*: Peak at 1.00x, 1.01x, and 1.99x assigns `current_tier = 1`, `guaranteed_floor = 0.20 * stake`. Pullbacks to 0.2001x hold; pullbacks touching or breaching 0.20x trigger exit (`winner_trailing_stop`), locking in +0.20 net profit.
   - *Tier 2 ([2.00x, 4.00x))*: Peak at 2.00x, 2.01x, and 3.99x assigns `current_tier = 2`, `guaranteed_floor = 1.00 * stake`. Pullbacks touching or breaching 1.00x exit, locking in +1.00 net profit.
   - *Tier 3 ([4.00x, 8.00x))*: Peak at 4.00x, 4.01x, and 7.99x assigns `current_tier = 3`, `guaranteed_floor = 2.50 * stake`. Pullbacks touching or breaching 2.50x exit, locking in +2.50 net profit.
   - *Tier 4 (>= 8.00x)*: At profit >= 8.00x, `profit >= tp_target - 1e-9` immediately triggers target exit (`winner_exit_multiple`). If peak profit reached >= 8.00x and price pulls back, it activates an 80% trailing stop (`peak_profit * 0.80`, minimum +2.50 * stake).

2. **Volatility & Adverse Noise Stress Testing**:
   - *Whipsaw sequences*: In `test_whipsaw_sequence_tier_1_to_breakeven_exit`, a position peaking at +1.50x (Tier 1) survived a severe drop to +0.25x (holding open above +0.20 floor) and cleanly exited when dipping to +0.19x, realizing the guaranteed breakeven floor.
   - *Adverse Excursion inside Cancellation Window*: Emulating accidental runner contract #19127889519, where an unmanaged position suffered a -85% adverse drawdown during the 5-minute window before rallying to +155%:
     * `evaluate_winner_exit()` strictly returned `(False, "in_window_auto_sell_disabled")` at every drawdown level (-30%, -50%, -85%) and subsequent bounce (+15%, +50%, +155%).
     * Property-based fuzzing over 200 arbitrary profit points in `[-1.0, +10.0]` confirmed zero leaks (`should_exit` was False 100% of the time during `is_valid_to_cancel = True`).
     * In discrete tick replay (`test_simulation_contract_19127889519_drawdown_held_through_window`), `perpetual_ladder_1x_8x` survived the -85% excursion without stopout or scalp, qualified at boundary, and reached +8.36 net return (`sold_winner_target`), whereas `micro_scalp_baseline` prematurely dumped the contract at +$0.36.

3. **Boundary Decision Stress Testing**:
   - *Marginal profit < fee*: When net profit is below the cancellation fee ($0.02 < $0.04), `handle_boundary` and simulation replay both execute defensive cancellation (`defensive_cancel_marginal_winner` / `cancelled_loser`), avoiding unhedged exposure to weak runners.
   - *Profit >= fee with trend agreement*: When net profit covers fee ($0.12 >= $0.04) and trend agrees (MULTUP), position transitions seamlessly to `held_winner` (`HELD_WINNER` machine state).
   - *Profit >= fee with contrary trend*: When net profit covers fee ($0.16 >= $0.04) but prevailing market trend opposes the contract (BEARISH/MULTDOWN vs MULTUP), position is defensively cancelled before window expiration (`closed_loser`), protecting capital against adverse trend reversal.
   - *Missed window safety*: If cancellation validity expired prior to boundary evaluation (`is_valid_to_cancel = False`), contract is safely marked as `cancellation_window_missed` and halts new buys (`RECONCILIATION_REQUIRED`), preventing invalid API requests.

## 3. Adversarial Review Report

### Challenge Summary
**Overall risk assessment**: LOW

### Challenges Evaluated

#### [Low] Challenge 1: Floor Step Transition Edge Cases
- **Assumption challenged**: Whether floating-point precision issues near tier thresholds (e.g. 0.999999 vs 1.000000) could cause premature tier elevation or missed trailing stops.
- **Attack scenario**: Evaluated `profit` and `peak_profit` at `[threshold - 1e-6, threshold, threshold + 1e-6]` and `profit <= floor + 1e-9`.
- **Empirical result**: Pass. Exact float comparison with `1e-9` epsilon ensures reliable transitions without off-by-one tier skips.
- **Blast radius**: Negligible.

#### [Low] Challenge 2: Intra-Window Premature Exit Regression
- **Assumption challenged**: Whether high volatility spikes or extreme negative excursions inside the 5-minute cancellation window could inadvertently trigger a trailing stop or capital preservation stop.
- **Attack scenario**: Subjected contract to -85% drawdown, +155% turnaround, and rapid random walk oscillations during `is_valid_to_cancel = True`.
- **Empirical result**: Pass. The guard clause `if evidence.is_valid_to_cancel is True: return False, "in_window_auto_sell_disabled"` unconditionally isolates intra-window positions from all post-boundary exit triggers.
- **Blast radius**: None.

#### [Low] Challenge 3: Boundary Contrary-Trend Trap
- **Assumption challenged**: Whether a position showing positive paper profit at 4m45s could be converted to an unhedged perpetual runner into a hostile market trend.
- **Attack scenario**: Simulated contract with +$0.16 net profit arriving at boundary while 180-tick ADX and EMA trend had reversed to contrary direction.
- **Empirical result**: Pass. Both live engine and simulation replay actively query the trend filter and trigger defensive cancellation.
- **Blast radius**: None.

### Stress Test Results Matrix

| # | Stress Scenario | Expected Behavior | Actual Behavior | Result |
|---|-----------------|-------------------|-----------------|:------:|
| 1 | Peak at 0.99x (Tier 0), drop to -0.34x | Full breathing room, no trailing stop | `current_tier=0`, `floor=0.0`, `should_exit=False` | PASS |
| 2 | Peak at 1.00x (Tier 1), drop to 0.2001x | Hold open above floor | `current_tier=1`, `floor=0.20`, `should_exit=False` | PASS |
| 3 | Peak at 1.00x (Tier 1), drop to 0.2000x | Exit via trailing stop | `should_exit=True`, `winner_trailing_stop` | PASS |
| 4 | Peak at 2.00x (Tier 2), drop to 1.0000x | Exit via trailing stop | `should_exit=True`, `winner_trailing_stop` | PASS |
| 5 | Peak at 4.00x (Tier 3), drop to 2.5000x | Exit via trailing stop | `should_exit=True`, `winner_trailing_stop` | PASS |
| 6 | Profit hits 8.00x (Tier 4 target) | Immediate target exit | `should_exit=True`, `winner_exit_multiple` | PASS |
| 7 | Peak at 8.00x, pullback to 6.41x | Hold open above 80% trailing floor | `current_tier=4`, `floor=6.40`, `should_exit=False` | PASS |
| 8 | Peak at 8.00x, pullback to 6.40x | Exit via 80% trailing stop | `should_exit=True`, `winner_trailing_stop` | PASS |
| 9 | Whipsaw +1.5x -> +0.25x -> +0.19x | Hold at +0.25x, exit at +0.19x | Stays open at 0.25x, exits at 0.19x | PASS |
| 10 | Contract #19127889519 -85% intra-window drop | Never sell or stopout inside window | `in_window_auto_sell_disabled` across all levels | PASS |
| 11 | Micro-profit spikes (+0.15 to +0.25) in window | Abolish premature micro-scalps | Stays open, held to boundary | PASS |
| 12 | Boundary: net profit < cancellation fee | Defensively cancel loser | `closed_loser`, cancel request sent | PASS |
| 13 | Boundary: net profit >= fee, trend agrees | Transition to held_winner | `held_winner`, machine_state `HELD_WINNER` | PASS |
| 14 | Boundary: net profit >= fee, contrary trend | Defensively cancel loser | `closed_loser`, cancel request sent | PASS |
| 15 | Boundary: validity ended (`is_valid_to_cancel=0`) | Mark missed window safely | `cancellation_window_missed`, reconciliation | PASS |
| 16 | Random walk floor monotonicity (100 trials) | `floor(t+1) >= floor(t)` | Monotonicity satisfied 100% | PASS |
| 17 | Intra-window 200 arbitrary points fuzzing | 0% premature exit rate | 100% retention rate | PASS |
| 18 | Discrete replay contract #19127889519 (-85% drop) | Reaches 8.0x target ($8.36 net) | Survived, boundary qualified, sold at target | PASS |
| 19 | Discrete replay contrary trend boundary | Defensively cancel at t=300 | Cancelled, realized net -$0.04 | PASS |

### Unchallenged Areas
- Physical network socket timeouts during WebSocket request transmission (covered by Sentinel and Forensic Auditor).

## 4. Caveats
- No caveats regarding code modifications, unit test suite, simulation replay, or interface contracts. All stress tests run synchronously and deterministically.

## 5. Conclusion & Verdict

**Verdict: APPROVE**

The 4-tier progressive perpetual ratchet and directional boundary qualification mechanisms are robust, mathematically sound, and empirically verified. All 19 adversarial stress scenarios passed without exception, confirming:
1. Exact, predictable floor transitions across all tiers (0, 1, 2, 3, 4).
2. Complete elimination of intra-window premature micro-scalping exits, safely preserving contracts through catastrophic excursions like #19127889519's -85% drawdown to capture macro trend turnarounds.
3. Strict boundary qualification that cancels weak runners and contrary-trend traps while allowing qualified runners to capture 1x-8x perpetual gains.

## 6. Verification Method

To independently reproduce and verify all adversarial findings:
1. **Run Challenger 1 Adversarial Test Suite**:
   ```bash
   PYTHONPATH=trading-engine python3 -m unittest trading-engine/test_d107_adversarial_challenger.py
   ```
   *Expected Output*: `Ran 19 tests in ~0.13s - OK`
2. **Run Full D107 Unit & Simulation Test Suite**:
   ```bash
   PYTHONPATH=trading-engine python3 -m unittest discover -s trading-engine -p "test_d107_*.py"
   ```
   *Expected Output*: `Ran 94 tests in ~1.7s - OK`
3. **Run 24-Hour Historical Replay**:
   ```bash
   PYTHONPATH=trading-engine python3 -c '
   from d107_exact_historical_simulation import run_simulation
   r = run_simulation("trading-engine/d107_simulation_1hz10v_ticks.json", exit_scenario="perpetual_ladder_1x_8x", trend_alignment_enabled=True)
   d = r.as_dict()
   print(f"Buys: {d[\"buys\"]}, Net: ${d[\"realized_net\"]:.2f}, E[PnL]: ${d[\"expected_net_per_trade\"]:.4f}, PF: {d[\"profit_factor\"]:.2f}, Runners >= 1x: {d[\"runners_1x\"]}")
   '
   ```
   *Expected Output*: `Buys: 78, Net: $5.04, E[PnL]: $0.0646, PF: 2.11, Runners >= 1x: 10`
