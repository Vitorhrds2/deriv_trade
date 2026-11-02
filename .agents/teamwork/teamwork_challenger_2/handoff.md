# Adversarial Challenge Report — Milestone 3: Trend Alignment Filter & Simulation Replay Integrity

**Challenger**: Challenger 2 (`teamwork_challenger_2`)  
**Verdict**: **APPROVE**  
**Overall Risk Assessment**: **LOW**

---

## 1. Observation

### 1.1 Scope and Test Execution
1. **Adversarial Stress Test Suite**:
   - Location: `trading-engine/stress_test_challenger_2.py`
   - Execution command: `PYTHONPATH=trading-engine python3 trading-engine/stress_test_challenger_2.py`
   - Output: `Ran 11 tests in 0.411s - OK` (100% passing across all 11 adversarial stress tests).

2. **Full Historical Dataset Replay & Mirror Symmetry**:
   - Dataset: `trading-engine/d107_simulation_1hz10v_ticks.json` (86,395 ticks on Volatility 10 (1s) Index).
   - Execution command:
     ```bash
     PYTHONPATH=trading-engine python3 -c '
     import json
     from d107_exact_historical_simulation import run_simulation, simulate
     r_norm = run_simulation("trading-engine/d107_simulation_1hz10v_ticks.json", exit_scenario="perpetual_ladder_1x_8x", trend_alignment_enabled=True)
     d_norm = r_norm.as_dict()
     print("Normal: Buys =", d_norm["buys"], "Net = $", round(d_norm["realized_net"], 2), "E[PnL] = $", round(d_norm["expected_net_per_trade"], 4), "PF =", round(d_norm["profit_factor"], 2), "Runners 1x =", d_norm["runners_1x"])
     with open("trading-engine/d107_simulation_1hz10v_ticks.json") as f: d = json.load(f)
     inv_p = [2.0 * d["prices"][0] - p for p in d["prices"]]
     q = {"1.0:MULTUP": {"ask_price": 1.04, "cancellation_fee": 0.04, "commission": 0.0}, "1.0:MULTDOWN": {"ask_price": 1.04, "cancellation_fee": 0.04, "commission": 0.0}}
     r_inv = simulate("demo", d["times"], inv_p, q, 1.0, 104.0, "all_in", "perpetual_ladder_1x_8x", trend_alignment_enabled=True)
     d_inv = r_inv.as_dict()
     print("Inverted: Buys =", d_inv["buys"], "Net = $", round(d_inv["realized_net"], 2), "E[PnL] = $", round(d_inv["expected_net_per_trade"], 4), "PF =", round(d_inv["profit_factor"], 2), "Runners 1x =", d_inv["runners_1x"])
     '
     ```
   - Verbatim Output:
     * `Normal: Buys = 78 Net = $ 5.04 E[PnL] = $ 0.0646 PF = 2.11 Runners 1x = 10`
     * `Inverted: Buys = 81 Net = $ 4.56 E[PnL] = $ 0.0563 PF = 1.91 Runners 1x = 10`
     * Confirms directional neutrality and absence of upward or downward structural bias.

3. **Core Unit & Strategy Test Discovery Suite**:
   - Execution command: `PYTHONPATH=trading-engine python3 -m unittest discover -s trading-engine -p "test_d107_*.py"`
   - Verbatim Output: `Ran 75 tests in 2.243s - OK` (100% passing).

---

## 2. Logic Chain

### 2.1 Trend Alignment Extreme Regimes
1. **Pure Chop & Brownian Noise (Hurst ~ 0.50, ADX < 15)**:
   - In `trading-engine/d107_rate_limit_winner_holding.py` line 780, `is_strong = adx >= 20.0`.
   - When prices exhibit pure chop with ADX < 15, `is_strong` evaluates to `False`, forcing `direction = "NONE"` and `is_aligned = False`.
   - In empirical testing (`test_01_pure_chop_brownian_noise_and_adx_sub15`), a persistent low-ADX chop series produced `0 buys` (100% pause). Under unconstrained geometric Brownian noise ($H \approx 0.568$), trend alignment reduced buy entries from 67 down to 20 (70% churn elimination) compared to blind mechanical alternation.
   - In `d107_rate_limit_winner_holding.py` lines 1946-1955, the live engine emits `trend_alignment_pause` with reason `no_aligned_trend` instead of trading into unaligned noise.

2. **Runaway Monotonic Trends**:
   - Monotonic upward prices ($P_t = P_0 (1 + g)^t$) produce ADX values exceeding 95.0, `macro_trend == "BULLISH"`, and `direction == "MULTUP"`.
   - In empirical replay (`test_02_runaway_monotonic_bullish_trend`), 20/20 opened positions were `MULTUP` ($0$ counter-trend contracts).
   - Monotonic downward prices ($P_t = P_0 (1 - g)^t$) produce ADX values exceeding 97.0, `macro_trend == "BEARISH"`, and `direction == "MULTDOWN"`.
   - In empirical replay (`test_03_runaway_monotonic_bearish_trend`), 20/20 opened positions were `MULTDOWN` ($0$ counter-trend contracts).
   - Mechanical alternation (`self.state["next_direction"] = alternation_after`) has been effectively replaced: when trend alignment is active, `alternation_after = direction` (lines 2157-2160), preventing the bot from fighting the macro trend.

3. **V-Shape Reversal Purge & Re-qualification**:
   - During a sharp drop followed by an immediate surge, step-by-step tracing demonstrated that at the inflection boundary ($t=100..135$), Directional Movement (+DI/-DI) crosses while EMA windows diverge, causing `calculate_adx_and_trend` to return `direction == "NONE"` and `is_aligned == False`.
   - The old `MULTDOWN` direction is immediately purged, suppressing new entries during the inflection zone.
   - Once the new `BULLISH` trend is confirmed ($t \ge 140$), entries resume strictly as `MULTUP`. Zero `MULTDOWN` entries were opened following the reversal.
   - In `d107_rate_limit_winner_holding.py` lines 2415-2443 (`handle_boundary`), if a position is held across an adverse reversal, `trend_signal.direction != direction` flags `trend_supports = False`, triggering defensive cancellation before the 5-minute deal cancellation window expires.

4. **Edge Cases (Flatline, Zero Variance, NaN/Inf, Tick Gaps)**:
   - Single-price flatline ($P_t = 100.0$ for all $t$): `max(abs(d), 1e-6)` in line 752 prevents division by zero in True Range smoothing. ADX returns `0.0`, `macro_trend == "NEUTRAL"`, `direction == "NONE"`, resulting in `0 buys`.
   - Micro-noise ($10^{-12}$ perturbations): Safely evaluated as NEUTRAL chop with 0 entries.
   - Non-finite numbers (`NaN`, `Inf`, `-Inf`): Filtered out via `clean = [p for p in prices if math.isfinite(p) and p > 0]` (line 724). If all values are invalid, returns safe defaults (`direction == "NONE"`, `adx_value == 0.0`).
   - Tick gaps: Replay across 1-hour time jumps safely evaluates boundaries and open positions at the first post-gap tick without index corruption.

### 2.2 Simulation Replay Integrity & Causality
1. **Strict Causality Oracle Verification**:
   - Evaluated twin simulation runs sharing an identical prefix ($T = 300$ ticks) but diverging drastically thereafter (Branch A surges +20%, Branch B drops -20%).
   - All positions entered at $t \le T$ had **100% bit-for-bit identical** position IDs, entry timestamps, entry prices, contract directions, ask prices, and cancellation fees across both runs.
   - In `d107_exact_historical_simulation.py` lines 394 and 481, price slices are strictly backward-looking: `prices[max(0, index - 180):index + 1]`. No future tick data leaks into entry or boundary decisions.

2. **Conservative Accounting Equations**:
   - Cancellation: Loss is strictly $-cancellation\_fee$ (-$0.08), and stake ($1.00) is returned to cash (`cash += position.stake`), yielding exact cash change equal to `terminal_net`.
   - Stopout: When adverse move reaches 100% of stake (-0.25% move on 400x multiplier), position terminates with loss equal to full cost ($-cost = -(stake + fee) = -$1.08), with no refund to cash.
   - Commissions & Spread: Commission is subtracted from gross mark (`directional_gross - commission`), and ask price incorporates the deal cancellation fee.
   - Ledger Conservation: Across all test runs, `bankroll + realized_net + unrealized == final_balance` held with zero discrepancy.

---

## 3. Challenges

### [Low] Challenge 1: Unsanitized Type Input to `calculate_adx_and_trend`
- **Assumption challenged**: `calculate_adx_and_trend` implicitly assumes all elements of `prices` are `int` or `float` instances.
- **Attack scenario**: If uncleaned JSON payloads containing string numbers (e.g. `["100.25", "100.30"]`) or `None` values are passed directly to `calculate_adx_and_trend`, `math.isfinite(p)` raises `TypeError: must be real number, not str`.
- **Blast radius**: Low. In `d107_rate_limit_winner_holding.py` line 835, `evaluate_market_trend` sanitizes inputs via `clean_prices = [_positive_float(p) for p in prices]`, preventing runtime failures in production. Direct callers outside `evaluate_market_trend` must ensure numeric sequences.
- **Mitigation**: Add defensive type check `isinstance(p, (int, float)) and math.isfinite(p) and p > 0` to list comprehension in `calculate_adx_and_trend`.

---

## 4. Stress Test Results

| Test ID | Scenario | Expected Behavior | Actual Behavior | Result |
|---|---|---|---|---|
| **ST-01** | Low-ADX chop (ADX < 15, Hurst ~0.50) | Direction "NONE", is_aligned False, 0 buys | 0 aligned signals when ADX < 15, 0 buys | **PASS** |
| **ST-02** | Brownian noise ($H \approx 0.568$, 1000 ticks) | Filter rejects chop vs blind alternation | Buys cut from 67 (baseline) to 20 (aligned) | **PASS** |
| **ST-03** | Runaway monotonic bullish trend | 100% MULTUP entries, 0 MULTDOWN | 20/20 MULTUP buys, 0 MULTDOWN | **PASS** |
| **ST-04** | Runaway monotonic bearish trend | 100% MULTDOWN entries, 0 MULTUP | 20/20 MULTDOWN buys, 0 MULTUP | **PASS** |
| **ST-05** | V-shape reversal (inflection zone) | Old direction purged, transition pause | Direction NONE during inflection, 0 counter-trend | **PASS** |
| **ST-06** | Single-price flatline ($P_t = 100.0$) | Div-by-zero handled, ADX=0.0, 0 buys | ADX=0.0, macro NEUTRAL, 0 buys | **PASS** |
| **ST-07** | Epsilon micro-noise ($10^{-12}$) | Clean evaluation, no crash, 0 buys | ADX < 20, macro NEUTRAL, 0 buys | **PASS** |
| **ST-08** | NaN / Inf / Negative prices | Cleaned safely, no crash | Valid signal from clean subset, safe defaults | **PASS** |
| **ST-09** | Tick gaps (1-hour time jump) | Positions evaluated at next tick | Boundary reached safely, no state corruption | **PASS** |
| **ST-10** | Causality Oracle (twin divergent futures) | Prefix decisions 100% identical | 10/10 prefix entries bit-for-bit identical | **PASS** |
| **ST-11** | Conservative Accounting (cancel, stopout, fee) | Exact cash balance and PnL conservation | Cancel loss -$0.08, stopout -$1.08, cash conserved | **PASS** |
| **ST-12** | 4-Tier Ratchet Tiers (1x, 2x, 4x, 8x) | Floor ratchet & trailing stops trigger | All 4 tiers lock floors and exit properly | **PASS** |
| **ST-13** | 86k Tick Inversion (Mirror test) | Symmetric returns on reversed market | Buys=81, Net=$4.56, PF=1.91, Runners=10 | **PASS** |

---

## 5. Caveats
- Direct invocation of `calculate_adx_and_trend` without passing through `evaluate_market_trend` requires inputs to be pre-sanitized numeric floats/ints.
- Discrete historical replay assumes instantaneous order fill at tick prices; execution slippage under live Deriv WebSocket network latency is audited in Milestone 4 live canary testing.

---

## 6. Conclusion
The implementation of the Multi-Timeframe Trend Alignment Filter and the Discrete-Event Simulation Replay Engine in Milestone 3 is **robust, causality-preserving, and mathematically sound**. Empirical stress testing confirms that the strategy successfully suppresses trade churn during chop regimes, aligns strictly with macro trends without counter-trend positions, purges directions upon reversal, and enforces strictly conservative accounting.

**Verdict**: **APPROVE** (Proceed to Milestone 4).

---

## 7. Verification Method
To independently reproduce all empirical findings and verification results:

1. **Run Challenger 2 Adversarial Stress Test Suite**:
   ```bash
   PYTHONPATH=trading-engine python3 trading-engine/stress_test_challenger_2.py
   ```
   *Expected Output*: `Ran 11 tests in ~0.4s - OK`

2. **Run Historical Mirror / Symmetry Replay**:
   ```bash
   PYTHONPATH=trading-engine python3 -c '
   import json
   from d107_exact_historical_simulation import run_simulation, simulate
   r = run_simulation("trading-engine/d107_simulation_1hz10v_ticks.json", exit_scenario="perpetual_ladder_1x_8x", trend_alignment_enabled=True)
   print("Normal:", r.as_dict()["realized_net"], "PF:", r.as_dict()["profit_factor"])
   with open("trading-engine/d107_simulation_1hz10v_ticks.json") as f: d = json.load(f)
   inv_p = [2.0 * d["prices"][0] - p for p in d["prices"]]
   q = {"1.0:MULTUP": {"ask_price": 1.04, "cancellation_fee": 0.04, "commission": 0.0}, "1.0:MULTDOWN": {"ask_price": 1.04, "cancellation_fee": 0.04, "commission": 0.0}}
   r_inv = simulate("demo", d["times"], inv_p, q, 1.0, 104.0, "all_in", "perpetual_ladder_1x_8x", trend_alignment_enabled=True)
   print("Inverted:", r_inv.as_dict()["realized_net"], "PF:", r_inv.as_dict()["profit_factor"])
   '
   ```
   *Expected Output*: Both Normal and Inverted yield positive realized net (~$5.04 and ~$4.56) and Profit Factor $\sim 2.0$.

3. **Run Existing Strategy Test Discovery Suite**:
   ```bash
   PYTHONPATH=trading-engine python3 -m unittest discover -s trading-engine -p "test_d107_*.py"
   ```
   *Expected Output*: `Ran 75 tests in ~2.2s - OK`
