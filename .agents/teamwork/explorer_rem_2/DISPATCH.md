# Dispatch for Explorer 2: Live Price & Spread Polling Implementation

## Mission
Investigate Task 3: Live On-Chain Price & Spread Polling in `SuiBotRunner.scan_once()`.
Read:
- `/Users/vitorhrds/Documents/Github/hypothesis/.agents/teamwork/ORIGINAL_REQUEST.md` (MANDATORY: read full file before starting)
- `/Users/vitorhrds/Documents/Github/hypothesis/.agents/teamwork/PROJECT.md`
- `trading-engine/venues/sui_bot_runner.py` (specifically `scan_once()` around line 299 where `spread_bps=0.0` is hardcoded)
- `trading-engine/venues/sui_deepbook_venue.py` (specifically `SuiGraphQLClient`, DeepBook & Cetus pool addresses and GraphQL queries)
- `trading-engine/tests/test_sui_production_deployment.py` and other Sui tests to see mock expectations

## Working Directory
`/Users/vitorhrds/Documents/Github/hypothesis/.agents/teamwork/explorer_rem_2/`

## Objective
Analyze:
1. How `SuiBotRunner` currently runs `scan_once()` and why line 299 hardcoded `spread_bps=0.0`.
2. How to query live pool prices or pool states for the 4 pairs (`SUI/USDC`, `DEEP/SUI`, `DEEP/USDC`, `CETUS/SUI`) via `SuiGraphQLClient` or DeepBook/Cetus pool state endpoints.
3. How to compute the live spread in bps between Cetus and DeepBook.
4. How to ensure graceful fallback: if offline, during testing, or if query fails, fallback cleanly to `0.0` so all 175 existing unit tests continue to pass without error.
5. How `scan_once()` should log an `INFO` line on each scan cycle showing the 4 pairs and their monitored prices/spreads.
6. How `DRY_RUN_MODE` is handled (e.g. if `DRY_RUN_MODE=false`, submitting the PTB when spread > hurdle).
7. Provide concrete code diffs and recommendations for the Worker.

Output your report to `/Users/vitorhrds/Documents/Github/hypothesis/.agents/teamwork/explorer_rem_2/handoff.md`.

## 2026-11-10T04:52:59Z
You are Explorer 2 (Price Polling Explorer).
Your working directory is: /Users/vitorhrds/Documents/Github/hypothesis/.agents/teamwork/explorer_rem_2/
Read your dispatch instructions in: /Users/vitorhrds/Documents/Github/hypothesis/.agents/teamwork/explorer_rem_2/DISPATCH.md
MANDATORY: Read /Users/vitorhrds/Documents/Github/hypothesis/.agents/teamwork/ORIGINAL_REQUEST.md before starting work.
Also read /Users/vitorhrds/Documents/Github/hypothesis/.agents/teamwork/PROJECT.md.

Task:
Investigate Task 3: Live On-Chain Price & Spread Polling in `SuiBotRunner.scan_once()`.
Inspect `trading-engine/venues/sui_bot_runner.py` (line 299 hardcoded spread_bps=0.0), `trading-engine/venues/sui_deepbook_venue.py` (GraphQL query client, pool IDs for SUI/USDC, DEEP/SUI, DEEP/USDC, CETUS/SUI).
Design live pool price querying from Sui GraphQL, calculate spread in bps between Cetus and DeepBook, ensure safe fallback to 0.0 when offline or under test mocks so all 175 tests pass, format informative INFO logging for each scan cycle, and handle DRY_RUN_MODE=false execution when spread exceeds hurdle.

Write your report to: /Users/vitorhrds/Documents/Github/hypothesis/.agents/teamwork/explorer_rem_2/handoff.md
Send a completion message back when done.
