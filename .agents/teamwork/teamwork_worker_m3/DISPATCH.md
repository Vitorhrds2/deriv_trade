## 2026-11-02T08:48:43Z
You are Milestone 3 Worker (teamwork_worker).
Your working directory is: /Users/vitorhrds/Documents/Github/hypothesis/.agents/teamwork/teamwork_worker_m3

Read the original request at: /Users/vitorhrds/Documents/Github/hypothesis/.agents/teamwork/ORIGINAL_REQUEST.md
Read the project specifications at: /Users/vitorhrds/Documents/Github/hypothesis/.agents/teamwork/PROJECT.md
Read the detailed survey reports at:
- /Users/vitorhrds/Documents/Github/hypothesis/.agents/teamwork/teamwork_explorer_survey_1/handoff.md
- /Users/vitorhrds/Documents/Github/hypothesis/.agents/teamwork/teamwork_explorer_survey_2/handoff.md
- /Users/vitorhrds/Documents/Github/hypothesis/.agents/teamwork/teamwork_explorer_survey_3/handoff.md

MANDATORY INTEGRITY WARNING:
DO NOT CHEAT. All implementations must be genuine. DO NOT hardcode test results, create dummy/facade implementations, or circumvent the intended task. A teamwork_auditor will independently verify your work. Integrity violations WILL be detected and your work WILL be rejected.

Scope & Tasks:
1. Strategy Implementation (`trading-engine/d107_rate_limit_winner_holding.py`):
   - Abolish premature micro-scalping exits: Set `in_window_auto_sell = False` by default. In `evaluate_winner_exit`, if `is_valid_to_cancel` is True, do NOT sell winning positions via intra-window trailing stop or take-profit. The 5-minute cancellation window exists solely as an asymmetric option to filter out losers at the 4m45s boundary while letting strong winners cross into perpetual runners.
   - 4-Tier Progressive Perpetual Ratchet on `held_winner`: Replace premature 0.15 trail with a genuine multi-tier ratchet:
     * Tier 0 (< 1.0x stake): No trailing stop. Breathing room to ride the macro trend.
     * Tier 1 (+1.0x stake / +$1.00): Lock in breakeven floor at +0.20 * stake.
     * Tier 2 (+2.0x stake / +$2.00): Ratchet guaranteed floor to +1.00 * stake.
     * Tier 3 (+4.0x stake / +$4.00): Ratchet guaranteed floor to +2.50 * stake.
     * Tier 4 (+8.0x stake / +$8.00): Target take-profit / 80% trailing stop.
   - Relax capital preservation loss from 0.08 to 0.35 * stake to avoid cutting viable runners on normal noise.
   - Trend Alignment: Replace blind mechanical alternation (`self.state["next_direction"] = alternation_after`) when trend alignment is active. Ensure entries align with prevailing market tides (directional momentum / moving averages / ADX).
   - Boundary Qualification: Ensure positions only transition to `held_winner` at 4m45s if net profit >= cancel fee AND trend momentum supports continuation.

2. Unit Tests (`trading-engine/test_d107_rate_limit_winner_holding.py`):
   - Update tests to reflect the new perpetual holding logic, the 4-tier ratchet, and the retirement of in-window trailing stop micro-scalping.
   - Run `PYTHONPATH=trading-engine python3 -m unittest trading-engine/test_d107_rate_limit_winner_holding.py` and ensure 100% of tests pass.

3. Simulation & Empirical Replay (`trading-engine/d107_exact_historical_simulation.py`):
   - Add/update the perpetual runner scenario (e.g. `perpetual_ladder_1x_8x`) implementing the redesigned 1x-8x ratchet alongside the micro-scalp baseline.
   - Run the simulation replay across `trading-engine/d107_simulation_1hz10v_ticks.json`.
   - Document comparative metrics: expected return per trade (E[PnL]), runner conversion rate, profit factor, and winner retention vs baseline.
   - Run `PYTHONPATH=trading-engine python3 -m unittest trading-engine/test_d107_exact_historical_simulation.py` and verify all tests pass.

Exclusive Write Ownership:
- `trading-engine/d107_rate_limit_winner_holding.py`
- `trading-engine/test_d107_rate_limit_winner_holding.py`
- `trading-engine/d107_exact_historical_simulation.py`
- `trading-engine/test_d107_exact_historical_simulation.py`

Output Requirements:
- Write complete handoff report to `/Users/vitorhrds/Documents/Github/hypothesis/.agents/teamwork/teamwork_worker_m3/handoff.md`.
- Maintain `/Users/vitorhrds/Documents/Github/hypothesis/.agents/teamwork/teamwork_worker_m3/progress.md`.
- Send a completion message to the parent orchestrator when done.


## 2026-11-02T09:04:24Z
[Message from Parent Orchestrator]
**Context**: Milestone 3 Implementation
**Content**: Checking in on status. Please update progress.md with your current step and estimated completion.
**Action**: Report progress on Step 5 / code modifications.
