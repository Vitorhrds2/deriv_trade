# BRIEFING — 2026-11-10T18:35:00Z

## Mission
Investigate R2 (Q* Optimal Sizing), R3 (Route prioritization and DeepBook Vault protection), and R5 (Preflight simulation, gas validation, live bot runner) for Sui DeepBook <-> Cetus/Turbos arbitrage bot.

## 🔒 My Identity
- Archetype: teamwork_explorer
- Roles: explorer, investigator, analyst
- Working directory: /Users/vitorhrds/Documents/Github/hypothesis
- State folder: /Users/vitorhrds/Documents/Github/hypothesis/.agents/teamwork/teamwork_explorer_survey_3
- Original parent: 760ce50e-d120-477a-bddb-8fc4f4fa33d2
- Milestone: Investigation R2, R3, R5

## 🔒 Key Constraints
- Read-only investigation — do NOT implement
- Do NOT modify any source code or data files
- Output full findings in handoff.md in own working directory
- Communicate via send_message to parent orchestrator
- Preserve existing 85+ tests in trading-engine/tests

## Current Parent
- Conversation ID: 760ce50e-d120-477a-bddb-8fc4f4fa33d2
- Updated: 2026-11-10T18:35:00Z

## Investigation State
- **Explored paths**:
  - `trading-engine/venues/sui_deepbook_venue.py` (PTB builder, GraphQL client, simulation, live broadcast)
  - `trading-engine/venues/sui_scaling_engine.py` (capital scaling, tranche sizing, safety floors)
  - `trading-engine/venues/sui_bot_runner.py` (scan loop, spread polling, preflight check, signal handlers)
  - `trading-engine/venues/sui_ptb_validator.py` (preflight health, 8-step PTB structure verification)
  - `trading-engine/h86_sui/node_modules/@mysten/deepbook-v3` (`pool.ts`, `vault.ts`, `errors.ts`, `deepbook.ts`)
  - Live Sui Mainnet GraphQL queries against Cetus CLMM pools and DeepBook V3 pools
  - Full test suite via `trading-engine/.venv/bin/pytest` (515 passed in 22.51s)
- **Key findings**:
  - **R2 (Q* Optimal Sizing)**: Current sizing relies on fixed discrete tiers ($1k/$5k/$10k) and DeepBook book depth, completely omitting Cetus CLMM price impact. Derived analytical optimal borrow volume $Q^* = \frac{1}{2}(\Delta P - \text{fees}) L \sqrt{P_0}$, which maximizes net profit and absorbs 50% of net spread into price impact. Established dynamic clamping ($100 - $150 USDC on thin pairs like DEEP/USDC, up to $4,000 USD on deep pairs like DEEP/SUI).
  - **R3 (Route Prioritization & Vault Protection)**: DEEP/SUI has $L \approx 9.84 \times 10^{14}$ (4,095x deeper than DEEP/USDC's $2.40 \times 10^{11}$) and 0 bps DeepBook taker fee, warranting top priority. Reproduced `EInsufficientVaultBalance` (abort code 2) when borrowing exceeds pool quote vault balance. Demonstrated live querying of `0xdee9::pool::vault_balances` via GraphQL `simulateTransaction`, revealing CETUS/SUI quote vault holds only 135.80 SUI.
  - **R5 (Preflight Simulation & Live Runner)**: Verified 0-gas Move VM preflight simulation via `simulateTransaction` Base64 BCS, $5.419$ SUI gas runway (2,709 aborts), safety floors (1.5 SUI warning, 0.5 SUI stop), and live execution activation requirements (`DRY_RUN_MODE=false`, `SUI_PRIVATE_KEY`).
- **Unexplored areas**: None within R2, R3, R5 scope.

## Key Decisions Made
- Completed rigorous 5-component handoff report in `handoff.md`.
- Formulated analytical formulas and dynamic clamping bounds for implementers.
- Demonstrated programmatic method to inspect DeepBook vault balances on-chain.

## Artifact Index
- /Users/vitorhrds/Documents/Github/hypothesis/.agents/teamwork/teamwork_explorer_survey_3/DISPATCH.md — Received dispatch instructions
- /Users/vitorhrds/Documents/Github/hypothesis/.agents/teamwork/teamwork_explorer_survey_3/BRIEFING.md — Persistent situational awareness
- /Users/vitorhrds/Documents/Github/hypothesis/.agents/teamwork/teamwork_explorer_survey_3/progress.md — Heartbeat and progress tracking
- /Users/vitorhrds/Documents/Github/hypothesis/.agents/teamwork/teamwork_explorer_survey_3/handoff.md — Self-contained handoff report for R2, R3, R5
