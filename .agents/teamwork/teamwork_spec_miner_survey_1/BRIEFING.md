# BRIEFING — 2026-11-10T18:35:00Z

## Mission
Investigate authoritative protocol specifications, contract interfaces, packages, and integration patterns for Turbos Finance CLMM on Sui Mainnet and DeepBook V3 & Cetus Reverse Route (DeepBook Ask -> Cetus Bid).

## 🔒 My Identity
- Archetype: teamwork_spec_miner
- Roles: survey_1 (Teamwork specialist / specification miner)
- Working directory: /Users/vitorhrds/Documents/Github/hypothesis
- State folder: /Users/vitorhrds/Documents/Github/hypothesis/.agents/teamwork/teamwork_spec_miner_survey_1
- Original parent: 760ce50e-d120-477a-bddb-8fc4f4fa33d2
- Milestone: specification mining

## 🔒 Key Constraints
- Read-only: discover and document features by probing authoritative specification; do NOT implement anything.
- Probe ALL discovered features thoroughly, capturing inputs, outputs, error behaviors, edge cases.
- Follow Handoff Protocol: write handoff.md with Observation, Logic Chain, Caveats, Conclusion, Verification Method.
- Preserve zero leg risk, Move VM Hot Potato semantics.

## Current Parent
- Conversation ID: 760ce50e-d120-477a-bddb-8fc4f4fa33d2
- Updated: 2026-11-10T18:35:00Z

## Task Summary
- **What to build**: Specification report for Turbos Finance CLMM and DeepBook V3 <-> Cetus Reverse Route arbitrage.
- **Success criteria**: Detailed, verified specifications with package IDs, entry points, tick math, quote calculation mechanics, PTB commands, reverse route flashloan asset determination, coin flow, and pool IDs.
- **Interface contracts**: /Users/vitorhrds/Documents/Github/hypothesis/.agents/teamwork/ORIGINAL_REQUEST.md
- **Code layout**: trading-engine/

## Key Decisions Made
- Extracted and verified authoritative Turbos CLMM contracts from Turbos S3 endpoint and unpacked `turbos-clmm-sdk`.
- Queried live Sui Mainnet GraphQL for Turbos packages, `swap_router` functions, pool objects, and initial shared versions.
- Probed DeepBook V3 flash loan and swap contracts (`@mysten/deepbook-v3`), discovering `swap_exact_quote_for_base`, `vault_balances`, and reverse route PTB flow.

## Artifact Index
- .agents/teamwork/teamwork_spec_miner_survey_1/handoff.md — Final specification report
- .agents/teamwork/teamwork_spec_miner_survey_1/progress.md — Progress and liveness log
