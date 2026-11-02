# BRIEFING — 2026-11-02T08:44:50Z

## Mission
Investigate Requirement R2 (Deriv Bot Curation & Trend Alignment): audit active bots in `trading-engine/`, diagnose counter-trend trading mechanisms, and formulate concrete trend-alignment recommendations.

## 🔒 My Identity
- Archetype: teamwork_explorer
- Roles: Explorer, Investigator, Synthesizer
- Working directory: /Users/vitorhrds/Documents/Github/hypothesis/.agents/teamwork/teamwork_explorer_survey_2
- Original parent: b88574b4-e7fe-4def-af10-a3a9d9c2bf6d
- Milestone: Survey & Diagnosis (R2)

## 🔒 Key Constraints
- Read-only investigation — do NOT implement or modify any source code or data files.
- Write full analysis and findings to handoff.md.
- Maintain progress.md with timestamps.
- Coordinate via send_message to parent orchestrator upon completion.

## Current Parent
- Conversation ID: b88574b4-e7fe-4def-af10-a3a9d9c2bf6d
- Updated: not yet

## Investigation State
- **Explored paths**:
  - `trading-engine/d107_rate_limit_winner_holding.py`
  - `trading-engine/ai_regime_supervisor.py`
  - `trading-engine/market_regime_policy.json`
  - `trading-engine/demo_tick_strategy_runner.py`
  - `trading-engine/scalper_bot.py`
  - `trading-engine/microtrader_bot.py`
  - `trading-engine/touch_anomaly_bot.py`
  - `trading-engine/d95_deal_cancellation_live_1hz100v.py`
  - `trading-engine/straddle_multiplier_exploit.py`
  - `trading-engine/forex_imbalance_exploit.py`
  - `trading-engine/d107_rate_limit_winner_holding_results.jsonl`
  - `trading-engine/d107_rate_limit_winner_holding_state.json`
  - `trading-engine/historico_trades_maio.csv`
- **Key findings**:
  1. D107 baseline fundamentally relies on mechanical 50/50 alternation (`alternation_after = "MULTDOWN" if direction == "MULTUP" else "MULTUP"`, line 1895, 1920), which forces exactly 50% of positions to trade counter-trend regardless of macro market direction.
  2. When `trend_alignment_enabled` is active, the live micro-trend detector previously examined only 15 ticks (15s) with a 0.005% threshold, triggering on sub-second Brownian jitter. In the latest revision, when 180-tick anti-exhaustion trips or trend is flat, it falls back to `get_regime_recommendations()`.
  3. In `ai_regime_supervisor.py`, assets with Hurst 0.45-0.55 (like 1HZ75V at Hurst=0.5387) are designated `UNCONDITIONAL_VOLATILITY_EXPANSION`, which causes `get_regime_recommendations()` to return `rec_dir = None`. Downstream D107 then falls back to `self.state.get("next_direction")`, reverting 100% to rigid blind alternation.
  4. Across Trials #256-#316 (61 trades), the direction breakdown was exactly 31 MULTUP vs 30 MULTDOWN. During a persistent downtrend from 1348.35 down to 1329.43, Trials 310 and 312 blindly bought MULTUP into the selloff.
  5. Winning positions in Trials #256-#316 suffered 17 premature micro-profit exits (+0.15 to +0.23 USD) due to `in_window_trailing_stop_pct = 0.30` firing inside the 5-minute cancellation window on tiny Brownian bounces.
  6. Meanwhile, accidental unmanaged runner #19127889519 (held through the 5m cancellation window due to `legacy_external` classification) rode through a 49-minute drawdown (-0.85 USD) and captured the macro multi-hour trend down to 1306.71, yielding +150% (+1.65 USD).
  7. There are ZERO standard higher-timeframe trend filters (ADX, Supertrend, MTF EMA, MACD, ATR) across the codebase.
- **Unexplored areas**: None for R2 scope.

## Key Decisions Made
- Fully documented all 8 Deriv bot scripts.
- Formulated quantitative Multi-Timeframe Alignment Matrix (M15 tide + M5 trend + M1 momentum) and ADX regime filter to replace blind alternation and premature micro-scalping.

## Artifact Index
- DISPATCH.md — Dispatch log from parent
- BRIEFING.md — Persistent working memory
- progress.md — Liveness heartbeat and progress tracking
- audit_trials.py — Empirical audit script for Trials 256-316
- audit_micro_wins.py — Empirical audit script for premature micro-profits
- analyze_runner.py — Detailed lifecycle metrics of runner #19127889519
- handoff.md — Final 5-component handoff report
