# Dispatch for Worker: Full Production Remediation Implementation

## Mission
Implement the full production remediation across Tasks 1, 2, and 3:
1. Create and share real on-chain DeepBook V3 `BalanceManager` on Sui Mainnet using the funded wallet.
2. Implement live on-chain price and spread polling in `trading-engine/venues/sui_deepbook_venue.py` and `trading-engine/venues/sui_bot_runner.py` with fail-safe test fallback, INFO logging, and live execution.
3. Apply `ImportError` guard in `trading-engine/venues/__init__.py`.
4. Run all Sui test suites (175 tests) and verify 100% green.
5. Granularly stage the 15 clean files (NEVER `.env` or `.agents/`), commit, and push to `origin feat/research-docs`.
6. Configure Railway service (`update-service`), connect source (`connect-service-source`), sync variables (`set-variables`), and monitor until deployment reaches `SUCCESS`.
7. Retrieve and verify live container runtime logs via `railway_mcp:get-logs`.

## Mandatory Reading
- `/Users/vitorhrds/Documents/Github/hypothesis/.agents/teamwork/ORIGINAL_REQUEST.md` (MUST read before starting)
- `/Users/vitorhrds/Documents/Github/hypothesis/.agents/teamwork/PROJECT.md`
- `/Users/vitorhrds/Documents/Github/hypothesis/.agents/teamwork/explorer_rem_1/handoff.md` (Task 2 BalanceManager)
- `/Users/vitorhrds/Documents/Github/hypothesis/.agents/teamwork/explorer_rem_2/handoff.md` (Task 3 Price/Spread Polling)
- `/Users/vitorhrds/Documents/Github/hypothesis/.agents/teamwork/explorer_rem_3/handoff.md` (Task 1 Railway Deployment)

## Working Directory
`/Users/vitorhrds/Documents/Github/hypothesis/.agents/teamwork/worker_rem_1/`

## Exclusive Write Ownership
- `trading-engine/h86_sui/` (script copy & execution, `.env` update)
- `trading-engine/venues/sui_deepbook_venue.py`
- `trading-engine/venues/sui_bot_runner.py`
- `trading-engine/venues/__init__.py`
- Railway service configuration & environment variables via `railway_mcp`

## MANDATORY INTEGRITY WARNING
DO NOT CHEAT. All implementations must be genuine. DO NOT hardcode test results, create dummy/facade implementations, or circumvent the intended task. A teamwork_auditor will independently verify your work. Integrity violations WILL be detected and your work WILL be rejected.

Output your comprehensive handoff report to:
`/Users/vitorhrds/Documents/Github/hypothesis/.agents/teamwork/worker_rem_1/handoff.md`
Send a completion message back when done.


## 2026-11-10T05:11:48Z
You are the Production Remediation Worker.
Your working directory is: /Users/vitorhrds/Documents/Github/hypothesis/.agents/teamwork/worker_rem_1/
Read your dispatch instructions in: /Users/vitorhrds/Documents/Github/hypothesis/.agents/teamwork/worker_rem_1/DISPATCH.md
MANDATORY: Read /Users/vitorhrds/Documents/Github/hypothesis/.agents/teamwork/ORIGINAL_REQUEST.md before starting work.
Also read /Users/vitorhrds/Documents/Github/hypothesis/.agents/teamwork/PROJECT.md.

Read the 3 Explorer handoffs for full specifications and diffs:
1. /Users/vitorhrds/Documents/Github/hypothesis/.agents/teamwork/explorer_rem_1/handoff.md
2. /Users/vitorhrds/Documents/Github/hypothesis/.agents/teamwork/explorer_rem_2/handoff.md
3. /Users/vitorhrds/Documents/Github/hypothesis/.agents/teamwork/explorer_rem_3/handoff.md

Your tasks:
1. BalanceManager on Sui Mainnet:
   - Copy `/Users/vitorhrds/Documents/Github/hypothesis/.agents/teamwork/explorer_rem_1/proposed_h86_create_balance_manager.mjs` to `trading-engine/h86_sui/h86_create_balance_manager.mjs`.
   - Run `node h86_create_balance_manager.mjs --execute` using the funded wallet in `trading-engine/h86_sui/.env`.
   - Verify on-chain creation of shared BalanceManager (`0x2c8d603bc51326b8c13cef9dd07031a408a48dddb541963357661df5d3204809::balance_manager::BalanceManager`).
   - Confirm `trading-engine/h86_sui/.env` contains the real `DEEPBOOK_BALANCE_MANAGER_ID=0x...`.

2. Live Price & Spread Polling Implementation:
   - In `trading-engine/venues/sui_deepbook_venue.py`, add `query_live_market_spreads()` to `SuiGraphQLClient`.
   - In `trading-engine/venues/sui_bot_runner.py`, implement `poll_market_spreads()`, update `scan_once()` to use live prices and spreads, format INFO cycle summary logging of all 4 pairs, and implement `DRY_RUN_MODE=false` execution and `scaling_engine.record_trade_success()`.

3. Container Safety & Test Suite:
   - Apply the `ImportError` guard in `trading-engine/venues/__init__.py`.
   - Run full repository test suite:
     `PYTHONPATH=trading-engine trading-engine/.venv/bin/pytest -v trading-engine/tests/`
     Ensure 100% of tests pass.

4. Git Staging & Push:
   - Granularly stage ONLY the 15 clean files:
     `trading-engine/Dockerfile`, `trading-engine/venues/sui_*.py`, `trading-engine/venues/__init__.py`, `trading-engine/venues/base.py`, `trading-engine/venues/registry.py`, `trading-engine/tests/test_sui_*.py`, `docs/sui_production_runbook.md`.
   - STRICT CHECK: verify `git diff --staged --name-only` does NOT contain any `.env`, `.agents/`, or untracked sensitive files.
   - Commit and push to `origin feat/research-docs`.

5. Railway Deployment:
   - Use `railway_mcp:update-service` on `0b2dfdc6-81f4-4da4-af48-4f566be655d4`, `8ec93921-cafb-417a-9c98-9d8be72d1344` to set `rootDirectory: "trading-engine"`, `dockerfilePath: "Dockerfile"`, `healthcheckPath: "/health"`, `restartPolicyType: "ALWAYS"`.
   - Call `railway_mcp:connect-service-source` with `repo: "Vitorhrds2/deriv_trade"`, `branch: "feat/research-docs"`.
   - Call `railway_mcp:set-variables` with `DEEPBOOK_BALANCE_MANAGER_ID` (the real on-chain ID) and `DRY_RUN_MODE: "false"`.
   - Poll `list-deployments` and `get-logs` until deployment reaches `SUCCESS` and live runtime logs show the 4-pair scan loop active.
