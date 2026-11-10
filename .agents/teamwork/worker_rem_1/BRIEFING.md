# BRIEFING — 2026-11-10T05:12:30Z

## Mission
Implement the full production remediation across Tasks 1, 2, and 3: on-chain BalanceManager creation, live price/spread polling in venue & bot runner, container safety guards, full test suite pass, clean git push to feat/research-docs, and Railway deployment configuration and verification.

## 🔒 My Identity
- Archetype: worker
- Roles: implementer, qa, specialist
- Working directory: /Users/vitorhrds/Documents/Github/hypothesis/.agents/teamwork/worker_rem_1/
- Original parent: ae5035fc-25bf-4785-8a7f-6b28349aa17b
- Milestone: production_remediation

## 🔒 Key Constraints
- DO NOT CHEAT. All implementations must be genuine.
- Granularly stage ONLY the 15 clean files: trading-engine/Dockerfile, trading-engine/venues/sui_*.py, trading-engine/venues/__init__.py, trading-engine/venues/base.py, trading-engine/venues/registry.py, trading-engine/tests/test_sui_*.py, docs/sui_production_runbook.md.
- STRICT CHECK: verify `git diff --staged --name-only` does NOT contain any `.env`, `.agents/`, or untracked sensitive files.
- Exclusive write ownership: trading-engine/h86_sui/, venues/sui_deepbook_venue.py, venues/sui_bot_runner.py, venues/__init__.py, Railway service configuration.
- Write report to /Users/vitorhrds/Documents/Github/hypothesis/.agents/teamwork/worker_rem_1/handoff.md and send completion message back.

## Current Parent
- Conversation ID: ae5035fc-25bf-4785-8a7f-6b28349aa17b
- Updated: not yet

## Task Summary
- **What to build**: Real on-chain DeepBook V3 BalanceManager, live price & spread polling in DeepBook venue & bot runner, container safety guard in __init__.py, test suite pass, clean git push, Railway deployment update & verification.
- **Success criteria**:
  1. Shared BalanceManager created on Sui Mainnet, real ID stored in .env and Railway variables.
  2. Live GraphQL market polling implemented in SuiGraphQLClient & SuiBotRunner with 100% test pass.
  3. Clean git commit and push of 15 files to feat/research-docs.
  4. Railway service updated, rebuilt, deployed with status SUCCESS, and live runtime logs confirmed.
- **Interface contracts**: /Users/vitorhrds/Documents/Github/hypothesis/.agents/teamwork/PROJECT.md
- **Code layout**: /Users/vitorhrds/Documents/Github/hypothesis/.agents/teamwork/PROJECT.md

## Key Decisions Made
- [Pending initial review of explorer handoffs]

## Artifact Index
- /Users/vitorhrds/Documents/Github/hypothesis/.agents/teamwork/worker_rem_1/handoff.md — Final handoff report
- /Users/vitorhrds/Documents/Github/hypothesis/.agents/teamwork/worker_rem_1/progress.md — Progress heartbeat

## Change Tracker
- **Files modified**: None yet
- **Build status**: Pending
- **Pending issues**: None

## Quality Status
- **Build/test result**: Pending
- **Lint status**: Clean
- **Tests added/modified**: Pending

## Loaded Skills
- Source: use-railway (/Users/vitorhrds/.gemini/config/plugins/railway/skills/use-railway/SKILL.md)
  Local copy: /Users/vitorhrds/Documents/Github/hypothesis/.agents/teamwork/worker_rem_1/use-railway-skill.md
  Core methodology: Operate Railway infrastructure, service configuration, variables, deployments, and logs via railway_mcp.
