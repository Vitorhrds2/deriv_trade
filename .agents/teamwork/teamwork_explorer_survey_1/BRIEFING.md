# BRIEFING — 2026-11-02T08:44:00Z

## Mission
Investigate Requirement R1 (Historical Trade & Perpetual Turnaround Study): analyze May historical trades, accidental perpetual runner #19127889519 (+155% profit), and Trials #256-#316 (17 premature micro-profit exits).

## 🔒 My Identity
- Archetype: teamwork_explorer
- Roles: explorer, analyst, investigator
- Working directory: /Users/vitorhrds/Documents/Github/hypothesis/.agents/teamwork/teamwork_explorer_survey_1
- Original parent: b88574b4-e7fe-4def-af10-a3a9d9c2bf6d
- Milestone: Survey & Investigation (Requirement R1)

## 🔒 Key Constraints
- Read-only investigation — do NOT implement or modify source/data files
- Write findings only to `/Users/vitorhrds/Documents/Github/hypothesis/.agents/teamwork/teamwork_explorer_survey_1/handoff.md`
- Maintain `progress.md` with timestamps

## Current Parent
- Conversation ID: b88574b4-e7fe-4def-af10-a3a9d9c2bf6d
- Updated: 2026-11-02T08:44:00Z

## Investigation State
- **Explored paths**:
  - `trading-engine/historico_trades_maio.csv` (May 2026 real account trades)
  - `trading-engine/d107_rate_limit_winner_holding_results.jsonl` (317 trials log)
  - `trading-engine/d107_rate_limit_winner_holding_state.json` (316 contracts state)
  - `trading-engine/d107_rate_limit_winner_holding.py` (D107 bot execution code)
  - `trading-engine/ai_regime_supervisor.py` & `market_regime_policy.json` (Regime logic)
  - `docs/d107_exact_7d_simulation.summary.md` (Simulation context)
- **Key findings**:
  1. Contract `#19127889519` entered at 03:29:55Z on 1HZ75V MULTDOWN at 1329.34. Deriv API returned `InternalServerError` during `buy_submitted`. Bot orphaned it as `legacy_external`. It survived an 85% adverse excursion (-$0.85 at 04:19:50Z) and went on a massive run to +$1.65 (+155% net) as spot dropped to 1306.71 over 4+ hours (14,669s).
  2. Trials #256-#316 contained 61 trades: 35 cancelled losers (-$3.50), 17 premature micro-profit exits (+0.15 to +0.23, avg +$0.18, totaling +$3.05), 5 winner_trailing_stop, 3 capital preservation exits, 1 unresolved loss. Total net profit was only +$0.16.
  3. The 17 premature exits were caused by `in_window_auto_sell` with `in_window_trailing_stop_pct = 0.30` and `in_window_min_profit_to_trail = 0.25`. This cut winners prematurely inside the 5-minute cancellation window on normal tick volatility, completely blocking any transition into the 1x-8x perpetual holding logic.
  4. May historical trades were a 1-tick dual-direction straddle on JD100 (Jump 100 Index), profiting from 77 "dual win" ties (+190.62% per win) rather than perpetual momentum.
- **Unexplored areas**: None for R1. All acceptance criteria and scope requirements investigated.

## Key Decisions Made
- Documented full comparative metrics and root cause mechanisms in `handoff.md`.

## Artifact Index
- `DISPATCH.md` — Record of task dispatch
- `BRIEFING.md` — Persistent agent state
- `progress.md` — Liveness and execution progress tracker
- `handoff.md` — Final structured report
