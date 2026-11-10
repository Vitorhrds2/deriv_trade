# BRIEFING — 2026-11-10T02:13:35Z

## Mission
Investigate and design the production Railway deployment, latency comparison (Frankfurt vs Oregon), and continuous operational setup for the Sui arbitrage bot.

## 🔒 My Identity
- Archetype: explorer
- Roles: Teamwork explorer (read-only investigation, synthesis, architecture)
- Working directory: /Users/vitorhrds/Documents/Github/hypothesis/.agents/teamwork/teamwork_explorer_railway_survey_3/
- Original parent: bb8c036e-693a-4192-a9f6-25494af55dae
- Milestone: Railway Deployment & Operations Survey

## 🔒 Key Constraints
- Read-only investigation — do NOT implement or provision resources yet
- Ensure private keys, mnemonics, sensitive RPC URLs are ONLY supplied via Railway environment variables
- Zero credentials written to git, disk files, or debug logs
- Deliver analysis.md and handoff.md in working directory
- Maintain progress.md heartbeat

## Current Parent
- Conversation ID: bb8c036e-693a-4192-a9f6-25494af55dae
- Updated: 2026-11-10T02:13:35Z

## Investigation State
- **Explored paths**:
  - Railway MCP: whoami, list-workspaces, list-projects, update-service schema, docs search.
  - Sui Mainnet GraphQL: live balance verification, validator geo-resolution, consensus epoch analysis.
  - Codebase: `trading-engine/venues/sui_deepbook_venue.py`, `h86_sui_deepbook_flashloan_arb_scan.py`, `requirements.txt`.
- **Key findings**:
  - Live wallet balance verified on Sui Mainnet: exactly 5.419245048 SUI.
  - Mysten Labs deprecated public JSON-RPC on fullnodes (`error -32601`). Modern GraphQL (`https://graphql.mainnet.sui.io/graphql`) and gRPC are mandatory.
  - Active Sui Mainnet validator set is 57.1%+ European; Germany has the highest single European density (7 sampled nodes). Frankfurt (`europe-west3`) selected as optimal region.
  - Railway has deprecated `railwayConfigFile` (`railway.toml`) for new services; Dockerfile-based deployment with HTTP healthcheck (`GET /health`) is the recommended path.
- **Unexplored areas**: None for survey phase.

## Key Decisions Made
- Frankfurt (`europe-west3`) recommended over Oregon (`us-west1`).
- Multi-stage `Dockerfile` with embedded HTTP healthcheck server on `$PORT` and `restartPolicyType: ALWAYS`.
- Strict environment variable injection for credentials via Railway KMS.

## Artifact Index
- DISPATCH.md — Initial dispatch message
- BRIEFING.md — Persistent context & memory
- progress.md — Liveness heartbeat & task tracking
- analysis.md — Full architectural report, latency benchmark, and operational specification
- handoff.md — 5-component formal handoff report
