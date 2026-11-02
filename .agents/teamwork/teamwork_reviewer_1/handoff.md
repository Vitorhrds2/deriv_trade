# Review & Adversarial Audit Report — Milestone 3

**VERDICT: APPROVE**

**Reviewer Identity**: `teamwork_reviewer_1` (Roles: Reviewer, Critic)  
**Parent Orchestrator**: `b88574b4-e7fe-4def-af10-a3a9d9c2bf6d`  
**Milestone**: Milestone 3 — D107 Winner Holding Strategy Overhaul & Simulation  
**Target Files**: `trading-engine/d107_rate_limit_winner_holding.py`, `trading-engine/test_d107_rate_limit_winner_holding.py`, `trading-engine/d107_exact_historical_simulation.py`

---

## 1. Observation

1. **Test Suite Execution**:
   - `PYTHONPATH=trading-engine python3 -m unittest trading-engine/test_d107_rate_limit_winner_holding.py`:
     * Ran **54 tests in 1.976s — OK** (100% passing).
   - Full Discovery Suite: `PYTHONPATH=trading-engine python3 -m unittest discover -s trading-engine -p "test_d107_*.py"`:
     * Ran **75 tests in 1.763s — OK** (100% passing).
2. **Empirical Historical Tick Replay**:
   - Command:
     ```python
     from d107_exact_historical_simulation import run_simulation
     r = run_simulation("trading-engine/d107_simulation_1hz10v_ticks.json", exit_scenario="perpetual_ladder_1x_8x", trend_alignment_enabled=True)
     ```
   - Observed metrics:
     * `Buys: 78, Realized Net: $5.04, E[PnL] (realized): $0.0646, E[PnL] (total net): $0.0575, Profit Factor: 2.11, Runners >= 1x: 10, Runners >= 2x: 10`.
     * Validated the claimed +499% boost in expected net return per trade over baseline micro-scalp ($0.0096 $\rightarrow$ $0.0575) and reduction of churn from 2,904 buys to 78 buys.
3. **Source Code Implementation Inspection**:
   - `in_window_auto_sell`: Lines 271, 340-342 of `d107_rate_limit_winner_holding.py` set default to `False`.
   - `evaluate_winner_exit()`: Lines 2634-2642 strictly return `False, "in_window_auto_sell_disabled"` or `False, "cancellation_window_monitoring"` whenever `evidence.is_valid_to_cancel is True`. Intra-window scalp exits are completely abolished.
   - 4-Tier Progressive Perpetual Ratchet (`evaluate_perpetual_ratchet`): Lines 866-927 implement Tiers 0 to 4 with progressive floor ratchet:
     * Tier 0 (< 1.0x stake): No floor (`-inf`), returns `should_exit = False, exit_reason = "holding"`.
     * Tier 1 (+1.0x stake): Floor at `+0.20 * stake`.
     * Tier 2 (+2.0x stake): Floor at `+1.00 * stake`.
     * Tier 3 (+4.0x stake): Floor at `+2.50 * stake`.
     * Tier 4 (+8.0x stake): Target take profit at `8.0 * stake` (`winner_exit_multiple`) or 80% trailing stop (`max(2.50 * stake, peak * 0.80)`).
   - Relaxed capital preservation stop: Lines 2678-2686 enforce `winner_capital_preservation_loss = 0.35 * stake`, applied only when `peak_net_pnl < 1.0 * stake` and `time_held >= 30.0`.
   - Trend Alignment Gating: Lines 707-853 define `TrendAlignmentSignal`, `calculate_adx_and_trend` (Wilder's ADX +DI/-DI + EMA trend), and `evaluate_market_trend`. In `try_buy()` (lines 1930-1956), when unaligned, it emits `trend_alignment_pause` and pauses. In `buy_confirmed()` (lines 2157-2160), it maintains `alternation_after = direction` rather than alternating blindly.
   - Boundary Qualification in `handle_boundary()`: Lines 2400-2459 strictly require `net_profit >= cancel_fee` AND `trend_supports == True` before calling `hold_winner()`; otherwise defensively executes `cancel_loser()`.

---

## 2. Logic Chain

1. **Abolition of In-Window Micro-Scalping Exits**:
   - *Observation*: Lines 2634-2642 in `evaluate_winner_exit` intercept any contract where `evidence.is_valid_to_cancel is True` and return `False`.
   - *Inference*: Inside the 5-minute cancellation window, Deriv guarantees risk asymmetry: downside is capped at the fixed cancellation fee (-$0.04 to -$0.08). Selling early for +$0.15 to +$0.23 forfeits the free option to catch large multi-bagger runners while taking full downside risk. Abolishing in-window selling preserves the option for boundary qualification.
2. **Mathematical Mechanics of the 4-Tier Ratchet**:
   - *Observation*: Monotonic floor progression: `0.0 -> 0.20 -> 1.00 -> 2.50 -> max(2.50, 0.80 * peak)`.
   - *Inference*: In volatile synthetic indices with 400x multipliers, standard percentage trailing stops (e.g. 15%) trigger premature shakeouts on tick noise. By granting breathing room in Tier 0 and locking in coarse-grained stair-step guaranteed floors in Tiers 1-4, runners are given space to develop while accumulated profits are protected once established.
3. **Relaxed Capital Preservation**:
   - *Observation*: `winner_capital_preservation_loss = 0.35` with `time_held >= 30.0` guard for Tier 0.
   - *Inference*: On a 400x multiplier, a price change of 0.02% equates to an 8-cent loss. An 8-cent stop loss (previous value) resulted in 100% shakeout on normal spread fluctuations. Relaxing to 0.35 provides sufficient room for normal price volatility while cutting catastrophic reversals at 35% rather than a complete 100% loss.
4. **Trend Alignment Gating vs Mechanical Alternation**:
   - *Observation*: ADX >= 20 threshold, concordance between +DI/-DI and EMA fast/slow differential, and `try_buy()` pause.
   - *Inference*: Mechanical alternating (`MULTUP` $\rightarrow$ `MULTDOWN`) caused the previous bot to enter counter-trend trades 50% of the time. Filtering for market alignment cuts out 97.3% of choppy, low-probability entries and aligns trades with prevailing market momentum.
5. **Integrity & Absence of Cheat Patterns**:
   - *Observation*: All tests construct synthetic price arrays or mock API payloads dynamically. No hardcoded contract IDs or hardcoded return values exist in `d107_rate_limit_winner_holding.py` or `d107_exact_historical_simulation.py`.
   - *Inference*: The implementation represents genuine business logic and satisfies all integrity requirements.

---

## 3. Caveats

1. **Dead Configuration Branch for `in_window_auto_sell`**:
   - Setting `D107_IN_WINDOW_AUTO_SELL=True` will not restore intra-window scalp exits because `evaluate_winner_exit()` explicitly returns `False, "cancellation_window_monitoring"` inside the window. This is intentional to prevent micro-scalping regressions, but users should be aware that intra-window auto-selling cannot be re-enabled without code changes.
2. **Gross vs Net Take-Profit Target Timing**:
   - Line 2647 checks `bid_price >= buy_price * 8.0` (8x return on gross invested capital), while `evaluate_perpetual_ratchet` checks `profit >= 8.0 * stake` (8x return on stake). Because `buy_price = stake + cancel_fee` ($1.04), line 2647 triggers at `bid_price = $8.32` (approx 7.28x net gain on stake) before ratchet's $9.04. Both achieve the target perpetual exit objective.
3. **Simulation Dataset Scope**:
   - Historical simulation was verified on 24 hours of 1-second ticks on `1HZ10V` (86,395 ticks). Runner retention and frequency on different symbols (`1HZ100V`, `R_100`) will depend on respective asset volatility, though the trend filter dynamically scales via relative percentage price deltas.

---

## 4. Conclusion

The Milestone 3 work product is **VERIFIED AND APPROVED**.
- The 6 required verification criteria have been thoroughly audited and confirmed.
- Zero integrity violations, dummy implementations, or hardcoded shortcuts were found.
- The unit test suite (54 engine tests, 75 discovery tests) passes 100%.
- Simulation replay confirms the expected net return per trade increased by +499% ($0.0096 $\rightarrow$ $0.0575) and profit factor improved to 2.11 with 12.8% of entries achieving $\ge 2.0\text{x}$ stake returns.

---

## 5. Verification Method

To independently reproduce this verification:

1. **Run Strategy Unit Tests**:
   ```bash
   PYTHONPATH=trading-engine python3 -m unittest trading-engine/test_d107_rate_limit_winner_holding.py
   ```
   *Expected*: `Ran 54 tests in ~1.9s - OK`
2. **Run Full D107 Discovery Suite**:
   ```bash
   PYTHONPATH=trading-engine python3 -m unittest discover -s trading-engine -p "test_d107_*.py"
   ```
   *Expected*: `Ran 75 tests in ~1.8s - OK`
3. **Run Historical Simulation Replay**:
   ```bash
   PYTHONPATH=trading-engine python3 -c '
   from d107_exact_historical_simulation import run_simulation
   r = run_simulation("trading-engine/d107_simulation_1hz10v_ticks.json", exit_scenario="perpetual_ladder_1x_8x", trend_alignment_enabled=True)
   d = r.as_dict()
   print("Buys:", d["buys"], "Net:", round(d["realized_net"], 2), "PF:", round(d["profit_factor"], 2), "Runners >= 1x:", d["runners_1x"])
   '
   ```
   *Expected*: `Buys: 78 Net: 5.04 PF: 2.11 Runners >= 1x: 10`

---

## Quality Review Report

**Verdict**: APPROVE

### Findings
- **Minor Finding 1 (Design Nuance)**: `in_window_auto_sell` parameter in `D107Config` is a permanent no-op in `evaluate_winner_exit()`. Both `False` and `True` branches return `False`. Suggestion: Keep as-is or document in config docs that in-window auto-selling is architecturally deprecated.
- **Minor Finding 2 (Target Exit Alignment)**: Gross TP check at line 2647 (`bid_price >= buy_price * 8.0`) evaluates before Net TP in ratchet (`profit >= 8.0 * stake`). At $1.04 buy price, triggers at $8.32 vs $9.04. Suggestion: Document that TP secures 8x on total capital outlay.

### Verified Claims
- Claim: In-window micro-scalping exits abolished $\rightarrow$ Verified via `evaluate_winner_exit` and `test_in_window_early_trailing_stop` $\rightarrow$ PASS
- Claim: 4-Tier Ratchet (Tiers 0-4) implemented $\rightarrow$ Verified via `evaluate_perpetual_ratchet` and standalone/integration tests $\rightarrow$ PASS
- Claim: Relaxed stop loss at 0.35 * stake $\rightarrow$ Verified via `evaluate_winner_exit` line 2684 and unit tests $\rightarrow$ PASS
- Claim: Trend Alignment gating pauses unaligned trades $\rightarrow$ Verified via `calculate_adx_and_trend`, `try_buy()` pause, and test assertions $\rightarrow$ PASS
- Claim: Boundary qualification checks profit >= fee AND trend concordance $\rightarrow$ Verified via `handle_boundary` and test assertions $\rightarrow$ PASS
- Claim: 75/75 tests pass $\rightarrow$ Verified via unittest execution $\rightarrow$ PASS

### Coverage Gaps
- None. All 6 dispatch criteria and project interface contracts were fully inspected and verified.

---

## Adversarial Challenge Report

**Overall Risk Assessment**: LOW

### Challenges

#### Challenge 1 (Low): Floating Point Precision at Tier Boundaries
- *Assumption challenged*: In `evaluate_perpetual_ratchet`, `profit <= floor` could suffer from IEEE-754 precision issues (e.g., `0.20000000000000004` failing to trigger an exit at `0.20`).
- *Attack scenario*: Profit drops to exact floor representation.
- *Stress Test Result*: Inspected line 916: `if current_tier > 0 and profit <= floor + 1e-9:`. Tolerance of `1e-9` prevents precision misses. Evaluated with `profit=1.0000000000000002` vs `floor=1.00`: cleanly triggers exit. $\rightarrow$ PASS.

#### Challenge 2 (Low): Zero/Degenerate Volatility in ADX Calculation
- *Assumption challenged*: A flat price series (zero price movement) could cause zero-division in `dx = 100.0 * abs(plus_di - minus_di) / di_sum`.
- *Attack scenario*: 180 identical price ticks passed to `calculate_adx_and_trend`.
- *Stress Test Result*: Tested in Python with `[100.0] * 180`. Line 752 guards with `tr = [max(abs(d), 1e-6) for d in deltas]`, and line 769 guards with `if di_sum > 0 else 0.0`. Returned `adx = 0.0, is_aligned = False, macro_trend = NEUTRAL` without exception. $\rightarrow$ PASS.

#### Challenge 3 (Low): Network / API Exception in Trend Evaluator
- *Assumption challenged*: Malformed API responses or timeout during `evaluate_market_trend` could crash `try_buy()`.
- *Attack scenario*: DerivClient raises `TimeoutError` or returns malformed payload.
- *Stress Test Result*: Inspected lines 813-846: `try...except Exception: pass`. Cleanly falls back to neutral signal (`is_aligned=False`), which causes `try_buy()` to safely emit `trend_alignment_pause` without placing orders. $\rightarrow$ PASS.

### Stress Test Summary Table
| Scenario | Expected Behavior | Actual Behavior | Result |
|---|---|---|---|
| Tier 0 pullback to -$0.25 net | Hold position (no trailing stop) | `(False, "holding")` | PASS |
| Tier 0 loss exceeding -$0.35 after 30s | Exit on capital preservation | `(True, "winner_capital_preservation")` | PASS |
| Tier 1 peak +$1.20, pullback to +$0.18 | Exit on floor breach (< +$0.20) | `(True, "winner_trailing_stop")` | PASS |
| Tier 2 peak +$2.50, pullback to +$0.95 | Exit on floor breach (< +$1.00) | `(True, "winner_trailing_stop")` | PASS |
| Tier 3 peak +$4.50, pullback to +$2.45 | Exit on floor breach (< +$2.50) | `(True, "winner_trailing_stop")` | PASS |
| Tier 4 peak +$8.50, pullback to +$6.70 | Exit on 80% trail breach (< +$6.80) | `(True, "winner_trailing_stop")` | PASS |
| Boundary net profit < cancel fee | Defensively cancel loser | `cancel_loser` requested | PASS |
| Boundary trend opposes position direction | Defensively cancel loser | `cancel_loser` requested | PASS |
| Choppy price series in `try_buy()` | Pause without placing order | `trend_alignment_pause` emitted | PASS |
| Trending price series in `try_buy()` | Enter in trend direction, retain direction | Buy confirmed, no alternation | PASS |

---

## Integrity Audit Certification

As adversarial critic, I certify that I independently checked for all integrity violation patterns:
- **Hardcoded test results or expected outputs in source**: NONE found.
- **Dummy or facade implementations**: NONE found. Real Wilder's ADX and stateful ratchet logic implemented.
- **Shortcuts bypassing intended task**: NONE found.
- **Fabricated verification outputs or logs**: NONE found. All tests and historical simulations were executed independently and produced identical results to those reported.
- **Self-certifying work without genuine verification**: NONE found.

**Final Recommendation**: Proceed to Milestone 4 / Milestone 5.
