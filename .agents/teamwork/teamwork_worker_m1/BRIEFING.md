# BRIEFING — 2026-11-10T18:57:00Z

## Mission
Implement Milestone 1 (R1 - Bidirectional Reverse Route DeepBook <-> Cetus): PTB construction, validation, dry-run simulation, market spread calculation, bot runner support, and test suite.

## 🔒 My Identity
- Archetype: teamwork_worker
- Roles: implementer, qa
- Working directory: /Users/vitorhrds/Documents/Github/hypothesis
- State folder: /Users/vitorhrds/Documents/Github/hypothesis/.agents/teamwork/teamwork_worker_m1
- Original parent: 760ce50e-d120-477a-bddb-8fc4f4fa33d2
- Milestone: M1_REVERSE_ROUTE

## 🔒 Key Constraints
- Minimal change principle. Genuine implementation only (no hardcoding, no facades).
- Python virtual environment: `/Users/vitorhrds/Documents/Github/hypothesis/trading-engine/.venv/bin/python`
- All 515 existing tests must pass 100% without regression, plus new reverse route tests.
- Zero leg risk preservation: if reverse route proceeds < borrow_amount, abort cleanly and guarantee `zero_leg_risk_preserved = True`.

## Current Parent
- Conversation ID: 760ce50e-d120-477a-bddb-8fc4f4fa33d2
- Updated: 2026-11-10T18:57:00Z

## Task Summary
- **What to build**: Support `route_direction == "REVERSE"` in SuiDeepBookPTBBuilder, SuiDeepBookVenue.simulate_dry_run, SuiGraphQLClient.query_live_market_spreads, SuiPTBValidator, SuiBotRunner, and tests.
- **Success criteria**: All existing tests pass (515/515), all 34 new reverse route tests pass (34/34), PTB valid, dry-run simulation working for REVERSE, zero leg risk preserved.
- **Interface contracts**: /Users/vitorhrds/Documents/Github/hypothesis/.agents/teamwork/PROJECT.md
- **Code layout**: /Users/vitorhrds/Documents/Github/hypothesis/.agents/teamwork/PROJECT.md

## Key Decisions Made
- `HotPotatoPTBParams`: Added `route_direction: str = "FORWARD"` with "REVERSE" option, dynamically flipping Cetus swap `a2b = not cfg.cetus_a2b_for_quote_in` and `sqrt_price_limit = MIN_SQRT_PRICE if a2b else MAX_SQRT_PRICE`.
- `build_atomic_arb_ptb`: Implemented exact 8-command flow for REVERSE: Command 0 (borrow quote) -> Command 1 (deposit quote to BM) -> Command 2 (place market buy lifting Ask) -> Command 3 (withdraw base from BM) -> Command 4 (Cetus swap base for quote) -> Command 5 (Split repayment quote principal) -> Command 6 (return_flashloan_quote Hot Potato quench) -> Command 7 (TransferObjects remaining quote profit).
- `simulate_dry_run`: Added REVERSE branch acquiring base at Ask and selling base at AMM, with exact zero leg risk abortion if proceeds < borrow_amount.
- `query_live_market_spreads`: Computes both `forward_spread_bps` and `reverse_spread_bps`, assigning `best_route` and `optimal_spread_bps` while preserving `spread_bps` for backward compatibility.
- `sui_ptb_validator.py`: Updated `validate_atomic_ptb_generation` and `simulate_ptb_dry_run` to accept and validate reverse routes.
- `sui_bot_runner.py`: Evaluates bidirectional spreads in `scan_once()`, setting `route_direction = "REVERSE"` when profitable and passing it to validation, simulation, and order submission.
- `tests/test_sui_reverse_route.py`: 34 comprehensive unit and multi-pair invariant tests.

## Artifact Index
- DISPATCH.md — Assignment instructions
- BRIEFING.md — Persistent context
- progress.md — Heartbeat and status
- handoff.md — Final handoff report

## Change Tracker
- **Files modified**:
  - `trading-engine/venues/sui_deepbook_venue.py` — PTB params, builder, dry-run simulator, GraphQL live market spreads
  - `trading-engine/venues/sui_ptb_validator.py` — PTB generation validator and dry-run simulator support for reverse route
  - `trading-engine/venues/sui_bot_runner.py` — Bidirectional spread detection and reverse route execution in scan loop
  - `trading-engine/tests/test_sui_reverse_route.py` — New test suite covering reverse route
- **Build status**: 549/549 tests passing (100% success rate, 0 regressions)
- **Pending issues**: None

## Quality Status
- **Build/test result**: PASS (549 passed in 21.02s)
- **Lint status**: Clean
- **Tests added/modified**: 34 new tests added in `tests/test_sui_reverse_route.py`
