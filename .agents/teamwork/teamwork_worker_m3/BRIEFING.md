# BRIEFING — 2026-11-10T19:37:00Z

## Mission
Implement Milestone 3 (Requirement R4) for the Sui Arbitrage Bot in production: Multi-DEX Integration with Turbos Finance CLMM (continuous quote scanning + atomic PTB execution).

## 🔒 My Identity
- Archetype: teamwork_worker
- Roles: implementer, qa, specialist
- Working directory: /Users/vitorhrds/Documents/Github/hypothesis
- State folder: /Users/vitorhrds/Documents/Github/hypothesis/.agents/teamwork/teamwork_worker_m3
- Original parent: 3cb9f997-972a-4e6e-b964-690ae475cc91
- Milestone: Milestone 3 (Requirement R4)

## 🔒 Key Constraints
- Multi-DEX integration with Turbos Finance CLMM
- Continuous quote scanning & spot price calculation using Q64.64 sqrt_price
- Atomic PTB execution with Hot Potato flashloan quenching (Turbos swap_a_b_with_return_ / swap_b_a_with_return_)
- MakeMoveVec wrapping for coins
- Versioned object and Clock arguments
- Zero Leg Risk verification in simulate_dry_run
- Maintain 100% backward compatibility with DeepBook and Cetus CLMM
- Keep all 568 existing tests passing with 0 regressions, plus comprehensive tests for Turbos

## Current Parent
- Conversation ID: 3cb9f997-972a-4e6e-b964-690ae475cc91
- Updated: not yet

## Task Summary
- **What to build**: Turbos CLMM constants & pool registry, Turbos spot price scanning, Multi-DEX quote scanning & selection, Turbos atomic PTB construction (forward & reverse) with Hot Potato return, validation, bot runner multi-DEX support, unit & integration tests.
- **Success criteria**: All new Turbos tests pass, all 568 existing tests pass, 0 regressions, full integrity compliance.
- **Interface contracts**: PROJECT.md and DISPATCH.md
- **Code layout**: `trading-engine/venues/sui_deepbook_venue.py`, `trading-engine/venues/sui_ptb_validator.py`, `trading-engine/venues/sui_bot_runner.py`, `trading-engine/tests/`

## Change Tracker
- **Files modified**:
  - `trading-engine/venues/sui_deepbook_venue.py`: Added Turbos constants, pool registry, Q64.64 price math, Turbos PTB builder (swap_b_a_with_return_ & swap_a_b_with_return_), multi-DEX quote scanner, and Move VM dry-run simulation.
  - `trading-engine/venues/sui_ptb_validator.py`: Added Turbos PTB validation and dry-run report support.
  - `trading-engine/venues/sui_bot_runner.py`: Added multi-DEX AMM target configuration and scanning/execution integration.
  - `trading-engine/tests/test_sui_turbos_clmm.py`: Created 15 comprehensive unit & integration tests covering all requirements.
- **Build status**: PASS (583 passed in 34.70s, 0 failures, 0 regressions)
- **Pending issues**: None

## Quality Status
- **Build/test result**: PASS (583 / 583 passed)
- **Lint status**: CLEAN (0 syntax errors, 0 runtime exceptions)
- **Tests added/modified**: 15 new tests in `test_sui_turbos_clmm.py`

## Loaded Skills
- None explicitly required

## Key Decisions Made
- Coin orientation on Turbos: Coin A is Base and Coin B is Quote across all 4 verified pools.
- Forward route uses `swap_router::swap_b_a_with_return_` with `sqrt_price_limit=MAX_SQRT_PRICE`.
- Reverse route uses `swap_router::swap_a_b_with_return_` with `sqrt_price_limit=MIN_SQRT_PRICE`.
- Wrapped input coins in `MakeMoveVec` structure.
- Multi-DEX scanner compares net spreads (accounting for DEX fee + taker fee) and automatically routes to the most profitable AMM (`best_amm`).

## Artifact Index
- /Users/vitorhrds/Documents/Github/hypothesis/.agents/teamwork/teamwork_worker_m3/DISPATCH.md — assignment details
- /Users/vitorhrds/Documents/Github/hypothesis/.agents/teamwork/teamwork_worker_m3/BRIEFING.md — working memory
- /Users/vitorhrds/Documents/Github/hypothesis/.agents/teamwork/teamwork_worker_m3/progress.md — liveness heartbeat
- /Users/vitorhrds/Documents/Github/hypothesis/.agents/teamwork/teamwork_worker_m3/handoff.md — milestone completion report
