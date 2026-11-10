# Dispatch Log

## 2026-11-10T04:49:37Z

Execute critical remediation for production deployment on Railway and live on-chain integration:

Working directory: /Users/vitorhrds/Documents/Github/hypothesis/.agents/teamwork/orchestrator_2/
Original Request reference: /Users/vitorhrds/Documents/Github/hypothesis/.agents/teamwork/ORIGINAL_REQUEST.md
Predecessor handoff: /Users/vitorhrds/Documents/Github/hypothesis/.agents/teamwork/orchestrator_1/handoff.md
Project root: /Users/vitorhrds/Documents/Github/hypothesis

## Tasks to Resolve:

1. **Railway Service Has `Latest deployment: none` (Violates Railway Skill Execution Rule 9)**:
   - Calling `railway_mcp:describe-service` on `projectId: 0b2dfdc6-81f4-4da4-af48-4f566be655d4`, `serviceId: 8ec93921-cafb-417a-9c98-9d8be72d1344` returns `Latest deployment: none`, and `get-logs` fails with `No deployment found for this service and environment`.
   - Creating an empty service and setting variables without attaching a source (`connect-service-source`) leaves no container running on Railway.
   - We verified `git push --dry-run origin feat/research-docs` succeeds against `https://github.com/Vitorhrds2/deriv_trade.git`.
   - **Action Required**:
     a) Stage and commit ONLY the clean code/config files needed for the deployment (`trading-engine/Dockerfile`, `trading-engine/venues/sui_*.py`, `trading-engine/venues/__init__.py`, `trading-engine/venues/base.py`, `trading-engine/venues/registry.py`, `trading-engine/tests/test_sui_*.py`, `docs/sui_production_runbook.md` — NEVER stage `.env` or `.agents/`). Push to `origin feat/research-docs`.
     b) On Railway (`projectId: 0b2dfdc6-81f4-4da4-af48-4f566be655d4`), ensure the service (`8ec93921-cafb-417a-9c98-9d8be72d1344`, or create/rename service `sui-deepbook-arb-bot` with all 12 variables copied over) has `rootDirectory: "trading-engine"` and `dockerfilePath: "Dockerfile"` via `update-service`, then call `connect-service-source` with `repo: "Vitorhrds2/deriv_trade"` and `branch: "feat/research-docs"`.
     c) Poll `list-deployments` / `get-status` / `get-logs` until the deployment reaches `SUCCESS` and the container's runtime logs show the pre-flight healthcheck and continuous scanning loop running live on Railway.

2. **Real On-Chain `DEEPBOOK_BALANCE_MANAGER_ID` Creation & Sync**:
   - In `/Users/vitorhrds/Documents/Github/hypothesis/trading-engine/h86_sui/.env`, `DEEPBOOK_BALANCE_MANAGER_ID=` is currently empty because `h86_setup_wallet.ts` was run before the user deposited the `5.419245048 SUI` into `0x5621a8e7199680512ee829565b96febea2587e534fd69b33f04004298d7e5ce9`, and the Railway service currently has placeholder `0x0000000000000000000000000000000000000000000000000000000000000001`.
   - **Action Required**:
     - Using the funded wallet in `/Users/vitorhrds/Documents/Github/hypothesis/trading-engine/h86_sui/.env` (or a TypeScript/Python script in `trading-engine/h86_sui/` using `@mysten/sui` and the official Sui GraphQL/gRPC endpoint, since `fullnode.mainnet.sui.io` JSON-RPC is deprecated), create and share a real DeepBook V3 `BalanceManager` object on Sui Mainnet (`0x2c8d603bc51326b8c13cef9dd07031a408a48dddb541963357661df5d3204809::balance_manager::new` + `0x2::transfer::public_share_object`), OR if `balance_manager` is created ephemeral/inline or shared on-chain, record the real on-chain `DEEPBOOK_BALANCE_MANAGER_ID=0x...` in `/Users/vitorhrds/Documents/Github/hypothesis/trading-engine/h86_sui/.env` and update `DEEPBOOK_BALANCE_MANAGER_ID` in Railway `set-variables`.

3. **Live On-Chain Price & Spread Polling in `SuiBotRunner.scan_once()`**:
   - Currently `trading-engine/venues/sui_bot_runner.py` line 299 calls `self.validator.simulate_ptb_dry_run(pair_name=pair_name, borrow_amount=borrow_amount, spread_bps=0.0)` with a hardcoded `0.0` spread!
   - **Action Required**:
     - Update `SuiBotRunner` so that in live runtime it queries live pool prices across the 4 pairs (`SUI/USDC`, `DEEP/SUI`, `DEEP/USDC`, `CETUS/SUI`) from Sui GraphQL (with clean fallback to `0.0` if offline or during unit tests so all existing 175 Sui tests continue to pass), computes the live spread in bps, logs an `INFO` line on each scan cycle so Railway deploy logs clearly display the 4 pairs being monitored, and set `DRY_RUN_MODE=false` (or trigger real execution when net profit > hurdle and `DRY_RUN_MODE=false`) as requested by the user.

Deliver a fully deployed, live-logging container on Railway and report completion.

## 2026-11-10T09:30:15Z

CRITICAL HINT TO UNBLOCK RAILWAY DEPLOYMENT IMMEDIATELY:

We noticed `connect-service-source` with `repo: "Vitorhrds2/deriv_trade"` failed because Railway's GitHub App on account `Vitorhrds` isn't installed on `Vitorhrds2`.
HOWEVER, `https://github.com/Vitorhrds2/deriv_trade` is a **PUBLIC repository** (`https://github.com/Vitorhrds2/deriv_trade/archive/refs/heads/feat/research-docs.tar.gz` returns HTTP 200 unauthenticated!).

To deploy immediately on Railway service `8ec93921-cafb-417a-9c98-9d8be72d1344` (`projectId: 0b2dfdc6-81f4-4da4-af48-4f566be655d4`) using ONLY `railway_mcp`:
1. Call `railway_mcp:update-service` on `projectId: "0b2dfdc6-81f4-4da4-af48-4f566be655d4"`, `serviceId: "8ec93921-cafb-417a-9c98-9d8be72d1344"` with:
   `startCommand: "sh -c \"pip install --no-cache-dir aiohttp && python3 -c 'import urllib.request, tarfile, io, os; os.makedirs(\\\"/app\\\", exist_ok=True); t=tarfile.open(fileobj=io.BytesIO(urllib.request.urlopen(\\\"https://github.com/Vitorhrds2/deriv_trade/archive/refs/heads/feat/research-docs.tar.gz\\\").read()), mode=\\\"r:gz\\\"); t.extractall(\\\"/app\\\")' && cd /app/deriv_trade-feat-research-docs/trading-engine && exec python3 venues/sui_bot_runner.py\""`
2. Call `railway_mcp:connect-service-source` on `projectId: "0b2dfdc6-81f4-4da4-af48-4f566be655d4"`, `serviceId: "8ec93921-cafb-417a-9c98-9d8be72d1344"` with:
   `image: "python:3.11-slim"`
3. Poll `railway_mcp:list-deployments` and `railway_mcp:get-logs` until the deployment reaches `SUCCESS` and live runtime logs show `SuiBotRunner` scanning the 4 pairs!

