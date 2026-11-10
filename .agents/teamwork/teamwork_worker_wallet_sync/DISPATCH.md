## 2026-11-10T04:12:25Z

You are the Sui Production Wallet & Railway Sync Worker.

MANDATORY FIRST STEP:
Read `/Users/vitorhrds/Documents/Github/hypothesis/.agents/teamwork/ORIGINAL_REQUEST.md` and `/Users/vitorhrds/Documents/Github/hypothesis/.agents/teamwork/PROJECT.md` before starting work.

Working Directory: `/Users/vitorhrds/Documents/Github/hypothesis/.agents/teamwork/teamwork_worker_wallet_sync/`

MANDATORY INTEGRITY WARNING:
DO NOT CHEAT. All implementations must be genuine. DO NOT hardcode test results, create dummy/facade implementations, or circumvent the intended task. A teamwork_auditor will independently verify your work. Integrity violations WILL be detected and your work WILL be rejected.

CRITICAL SECURITY CONSTRAINT:
NEVER print, log, display in terminal, or write private keys / secrets to any git repository, markdown handoff, or file. Handle private keys strictly in-memory when passing them to Railway MCP tools. Mask all sensitive keys (e.g. `suiprivkey...` -> `[REDACTED_SUI_PRIVATE_KEY]`) in reports and messages.

Your Mission:
The user has directed:
"Os valores da carteira com SUI está em /Users/vitorhrds/Documents/Github/hypothesis/trading-engine/h86_sui/.env e as definições das chaves detalhadas estão em /Users/vitorhrds/Documents/Github/hypothesis/trading-engine/h86_sui/.env.example, verifique e suba no serviço sui-deepbook-arb-bot do railway"

Detailed Steps:
1. Inspect `/Users/vitorhrds/Documents/Github/hypothesis/trading-engine/h86_sui/.env.example` to understand all configuration variables and key definitions.
2. Read `/Users/vitorhrds/Documents/Github/hypothesis/trading-engine/h86_sui/.env` (which contains the real credentials for the wallet with 5.419245048 SUI).
3. Connect to Railway using Railway MCP:
   - Identify project `sui-arbitrage-engine` (`0b2dfdc6-81f4-4da4-af48-4f566be655d4`) in workspace `c1c15805-fdc5-47b4-b2b1-bb1fb5f36349`.
   - Inspect existing services using `list-services`.
   - If the service is named `sui-deepbook-cetus-bot` (`8ec93921-cafb-417a-9c98-9d8be72d1344`), update its name to `sui-deepbook-arb-bot` (or create/maintain service alias so it is identified as `sui-deepbook-arb-bot`) using `update-service`.
   - Set the environment variables from `/Users/vitorhrds/Documents/Github/hypothesis/trading-engine/h86_sui/.env` into the service using Railway MCP `set-variables`. Ensure all required variables (`SUI_PRIVATE_KEY`, `OPERATOR_ADDRESS` / `SUI_WALLET_ADDRESS`, `DEEPBOOK_BALANCE_MANAGER_ID`, `SUI_GRAPHQL_URL`, `INITIAL_BORROW_AMOUNT`, `PORT`, `PYTHONUNBUFFERED`, `REGION`, etc.) are populated.
4. Verify code compatibility in `trading-engine/venues/sui_bot_runner.py` and `trading-engine/venues/sui_deepbook_venue.py`:
   - Ensure the config parser seamlessly handles aliases (e.g., if `.env` uses `SUI_WALLET_ADDRESS` or `OPERATOR_ADDRESS`, `SUI_PRIVATE_KEY` or `SUI_SECRET_KEY`, `DEEPBOOK_BALANCE_MANAGER_ID` or `BALANCE_MANAGER_ID`). If any alias is missing, update `SuiBotConfig.from_env()` so it reads both variants seamlessly.
5. Verify via Railway MCP `list-variables` that the variables are in place and non-empty (confirming variable names and that value is present without echoing raw secret in output).
6. Run the production deployment test suite:
   `PYTHONPATH=trading-engine trading-engine/.venv/bin/pytest -v trading-engine/tests/test_sui_production_deployment.py`
   to ensure all tests remain 100% passing.
7. Write your handoff report to `/Users/vitorhrds/Documents/Github/hypothesis/.agents/teamwork/teamwork_worker_wallet_sync/handoff.md` and send a message when done.
