# Original User Request

## Approved Task Prompt — 2026-11-02T08:31:00Z

Restore D107's core premise of capturing 1x-8x daily perpetual gains by investigating recent micro-scalping regressions, studying the accidental perpetual runner turnaround (contract #19127889519) and historical May trades (from 4 months ago), curating active Deriv bots operating against trends, and redesigning position opening/closing logic based on proven perpetual success cases.

Working directory: /Users/vitorhrds/Documents/Github/hypothesis/trading-engine
Integrity mode: development

## Requirements

### R1. Historical Trade & Perpetual Turnaround Study
Analyze historical trades from 4 months ago (`trading-engine/historico_trades_maio.csv`) and the accidental perpetual runner case (contract #19127889519) where an API error allowed an unmanaged position to run to +155% profit (+1.55 USD), identifying the exact market regimes, entry criteria, and holding dynamics that differentiate true 1x-8x perpetual runners from premature micro-profits (+0.15 to +0.23 USD in Trials #256-#316).

### R2. Deriv Bot Curation & Trend Alignment
Perform an in-depth curation of bots running on Deriv to diagnose and resolve why individual positions appear to trade against prevailing market tides and trends, ensuring entry filters align with directional momentum.

### R3. Redesign Opening and Closing Execution
Redesign D107 opening and closing logic in `trading-engine/d107_rate_limit_winner_holding.py` so that winning positions with strong trend momentum are allowed to transition past the 5-minute cancellation window into perpetual runners targeting 1x-8x stake returns, eliminating premature micro-profit exits inside the cancellation window.

### R4. Simulation & Empirical Validation
Validate the redesigned strategy using historical simulation and tick replay (`trading-engine/d107_exact_historical_simulation.py` and historical datasets), verifying that the new logic captures high-gain perpetual runs without regression into premature micro-scalping.

### R5. Learning Proposal Artifact
Persist all findings, comparative metrics, and the finalized strategy architecture into a `learning_proposal.md` artifact (with `RequestFeedback=true`) for user review and tracking.

## Acceptance Criteria

### Historical Analysis & Regimes
- [ ] Quantitative comparative analysis documents the entry conditions, trend indicators, and holding duration separating 1x-8x perpetual winners from the 17 premature micro-profit exits (+0.15 to +0.23 USD) observed in Trials #256-#316.
- [ ] Contract #19127889519 turnaround behavior and historical May trade patterns are documented with reproducible metrics.

### Bot Curation & Trend Alignment
- [ ] Active Deriv bot configurations and trend filters are audited, identifying specific mechanisms causing counter-trend trades.

### Strategy Implementation
- [ ] `trading-engine/d107_rate_limit_winner_holding.py` is updated so that qualified positions cross the 5-minute cancellation window to run as perpetuals targeting 1x-8x returns instead of exiting for micro-profits.

### Verification & Backtesting
- [ ] Redesigned logic is validated against historical simulation and tick data, demonstrating higher expected return per trade and successful retention of perpetual winners compared to the baseline trailing stop logic.

### Learning Proposal
- [ ] `learning_proposal.md` artifact is created with `RequestFeedback=true` summarizing the investigation, code modifications, simulation results, and operational guidelines.
