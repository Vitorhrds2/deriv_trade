## 2026-11-10T03:44:01Z
You are teamwork_worker_m4_deployment.
Your working directory is /Users/vitorhrds/Documents/Github/hypothesis/.agents/teamwork/teamwork_worker_m4_deployment/

MANDATORY: You must read:
1. /Users/vitorhrds/Documents/Github/hypothesis/.agents/teamwork/ORIGINAL_REQUEST.md
2. /Users/vitorhrds/Documents/Github/hypothesis/.agents/teamwork/PROJECT.md
3. /Users/vitorhrds/Documents/Github/hypothesis/.agents/teamwork/teamwork_worker_m3/handoff.md
4. /Users/vitorhrds/.gemini/config/plugins/railway/skills/use-railway/SKILL.md

MANDATORY INTEGRITY WARNING:
DO NOT CHEAT. All implementations must be genuine. DO NOT hardcode test results, create dummy/facade implementations, or circumvent the intended task. A teamwork_auditor will independently verify your work. Integrity violations WILL be detected and your work WILL be rejected.

Exclusive Write Ownership:
You own and may ONLY edit or create these files:
- `trading-engine/Dockerfile`
- `trading-engine/venues/sui_health_server.py`
- `trading-engine/venues/sui_bot_runner.py`
- `trading-engine/tests/test_sui_production_deployment.py`
- `.agents/teamwork/teamwork_worker_m4_deployment/*`

Milestone M4 Tasks (Requirement R3 - Continuous Production Deployment on Railway):
1. Implement `trading-engine/venues/sui_health_server.py`:
   - Lightweight async HTTP server (using `aiohttp.web` or `asyncio.start_server`) serving `GET /health` on port `$PORT` (default 8080).
   - Returns 200 OK with JSON payload containing:
     - `status`: "HEALTHY" | "DEGRADED" | "CRITICAL"
     - `uptime_seconds`: float
     - `current_tier`: "TIER_1" (1k) | "TIER_2" (5k) | "TIER_3" (10k)
     - `borrow_amount_usdc`: int
     - `sui_gas_balance`: float (actual verified 5.419 SUI)
     - `active_pairs`: ["SUI/USDC", "DEEP/SUI", "DEEP/USDC", "CETUS/SUI"]
     - `region`: "europe-west3" (Frankfurt)
     - `consecutive_aborts`: int
     - `timestamp`: float
2. Implement `trading-engine/venues/sui_bot_runner.py`:
   - Production runtime orchestrator for continuous execution:
     - Pre-flight check via `SuiPTBPreflightValidator.validate_preflight_health()` on startup.
     - Spawns background `sui_health_server` concurrently.
     - Continuous arbitrage scanning loop across the 4 pairs:
       - Checks `DynamicCapitalScalingEngine.can_trade()`.
       - Respects 1.5 SUI warning floor (throttled interval) and 0.5 SUI critical floor (halt execution).
       - Performs dry-run Move VM simulation on detected spread before live on-chain PTB submission.
     - Graceful signal handling (`SIGINT`, `SIGTERM`) with clean shutdown and session closure.
     - Configurable entirely via environment variables (zero hardcoded secrets).
3. Implement `trading-engine/Dockerfile`:
   - Containerized deployment for Railway:
     - Base image: `python:3.11-slim`
     - Non-root user `trader` for security.
     - Installs dependencies from `trading-engine/requirements.txt` (or pyproject.toml).
     - Environment: `PYTHONUNBUFFERED=1`, `PORT=8080`.
     - Entry point: `python venues/sui_bot_runner.py` (or `-m venues.sui_bot_runner`).
4. Implement `trading-engine/tests/test_sui_production_deployment.py`:
   - Unit and integration tests for `sui_health_server.py` (`GET /health` schema, latency, error states).
   - Tests for `sui_bot_runner.py` (configuration parsing from env vars, preflight initialization, graceful shutdown signal handling).
   - Dockerfile validation tests (verifying non-root user, CMD entrypoint, ENV settings).
5. Railway Infrastructure Provisioning & Configuration:
   - Use Railway MCP tools (`call_mcp_tool` on `railway_mcp`) or Railway CLI to provision/configure:
     - Workspace: `c1c15805-fdc5-47b4-b2b1-bb1fb5f36349`.
     - Project: `sui-arbitrage-engine`.
     - Service: `sui-deepbook-cetus-bot`.
     - Set Restart Policy: `ALWAYS`.
     - Set Region: Frankfurt (`europe-west3`).
     - Configure environment variables via `set-variables`:
       * `SUI_GRAPHQL_URL=https://graphql.mainnet.sui.io/graphql`
       * `OPERATOR_ADDRESS=0x5621a8e7199680512ee829565b96febea2587e534fd69b33f04004298d7e5ce9`
       * `INITIAL_BORROW_AMOUNT=1000000000`
       * `PORT=8080`
       * `LOG_LEVEL=INFO`
       * `PYTHONUNBUFFERED=1`
       * `DEEPBOOK_BALANCE_MANAGER_ID=0x0000000000000000000000000000000000000000000000000000000000000001`
       * Template for `SUI_PRIVATE_KEY` (MUST NEVER be logged or written to git/disk).
6. Verification:
   - Run tests:
     `PYTHONPATH=trading-engine trading-engine/.venv/bin/pytest -v trading-engine/tests/test_sui_production_deployment.py`
     `PYTHONPATH=trading-engine trading-engine/.venv/bin/pytest -v trading-engine/tests/test_sui_programmatic_verification.py trading-engine/tests/test_sui_scaling_engine.py trading-engine/tests/test_sui_deepbook_multipair.py`
   - All tests must pass cleanly.
   - Write comprehensive `handoff.md` and send completion message.
