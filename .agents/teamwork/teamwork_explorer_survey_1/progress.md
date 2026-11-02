# Progress — teamwork_explorer_survey_1

Last visited: 2026-11-02T08:45:00Z

## Status
- [x] Initialized workspace and state files (DISPATCH.md, BRIEFING.md, progress.md)
- [x] Inspected `trading-engine/historico_trades_maio.csv` (2,914 trades, 1-tick dual-direction straddle on JD100, 77 dual wins @ +$190.62)
- [x] Discovered smoking gun for contract `#19127889519` (Accidental Perpetual Runner):
  - Deriv API returned `InternalServerError` during `buy_submitted` at 03:29:55Z.
  - Position was orphaned as `legacy_external` and bypassed `in_window_trailing_stop`.
  - Survived adverse excursion of -85% (-$0.85 USD) at 04:19:50Z without hitting stop-out.
  - Caught macro trend on 1HZ75V MULTDOWN from 1329.34 down to 1306.71, peaking at +1.65 USD (+155% net profit), held for >4 hours across 239 portfolio snapshots.
- [x] Isolated exact mechanism for Trials #256-#316 premature exits:
  - 17 trades prematurely closed by `in_window_trailing_stop` at +0.15 to +0.23 USD (mean +$0.18, mean holding 199s).
  - Feature `in_window_auto_sell` with `in_window_trailing_stop_pct = 0.30` sniped winning positions inside the 5-minute cancellation window on standard tick noise, preventing them from ever becoming perpetual runners.
- [x] Generated detailed quantitative comparative metrics table across 1x-8x perpetual runners vs premature micro-profit exits vs May trades.
- [x] Synthesized findings into final `handoff.md` following the 5-Component Handoff Protocol.
- [x] Sent completion message to parent orchestrator.
