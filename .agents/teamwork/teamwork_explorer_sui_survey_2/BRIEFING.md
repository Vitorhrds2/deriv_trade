# BRIEFING — 2026-11-10T02:12:30Z

## Mission
Investigate and design dynamic capital scaling engine & wallet balance tracking architecture for Sui DeepBookV3 & Cetus arbitrage bot.

## 🔒 My Identity
- Archetype: explorer
- Roles: investigator, architect, synthesizer
- Working directory: /Users/vitorhrds/Documents/Github/hypothesis/.agents/teamwork/teamwork_explorer_sui_survey_2/
- Original parent: bb8c036e-693a-4192-a9f6-25494af55dae
- Milestone: Sui DeepBookV3 & Cetus Arbitrage Architecture Survey

## 🔒 Key Constraints
- Read-only investigation — do NOT implement
- Only write within working directory /Users/vitorhrds/Documents/Github/hypothesis/.agents/teamwork/teamwork_explorer_sui_survey_2/
- Deliver findings in analysis.md and handoff.md

## Current Parent
- Conversation ID: bb8c036e-693a-4192-a9f6-25494af55dae
- Updated: 2026-11-10T02:12:30Z

## Investigation State
- **Explored paths**:
  - `trading-engine/venues/sui_deepbook_venue.py`
  - `trading-engine/h86_sui/` (`.env`, `h86_setup_wallet.ts`, `h86_deepbook_execute.ts`, `h86_onchain_orderbook.py`, `package.json`)
  - `trading-engine/tests/test_venues_unit.py`
  - `trading-engine/simulations/simulate_h86_micro_capital.py`
  - `docs/technical_audit_quant_intelligence.md`
  - Live Sui Mainnet RPC (`https://fullnode.mainnet.sui.io` & `https://graphql.mainnet.sui.io/graphql`)
- **Key findings**:
  - Confirmed public JSON-RPC deprecation on `https://fullnode.mainnet.sui.io` (`-32601 Method not found`).
  - Confirmed official Sui GraphQL endpoint `https://graphql.mainnet.sui.io/graphql` live resolution.
  - Operator wallet `0x5621a8e7199680512ee829565b96febea2587e534fd69b33f04004298d7e5ce9` holds exactly `5419245048` MIST (5.419245048 SUI) and 0 USDC.
  - SUI runway: 2,709 on-chain aborts (at 0.002 SUI) or 1,354 successful executions; pre-flight dry runs cost 0 SUI.
  - Defined scaling state machine (1k -> 5k -> 10k USDC) with multi-layered safety guardrails.
  - Detailed token types and pool IDs across the 4 pairs: SUI/USDC, DEEP/SUI, DEEP/USDC, CETUS/SUI.
- **Unexplored areas**: None for this survey scope.

## Key Decisions Made
- Replaced deprecated JSON-RPC with atomic dual-balance Sui GraphQL document.
- Formalized scaling state machine with threshold transitions: Tier 1 (1k) -> Tier 2 (5k) at +$100 profit/10 trades -> Tier 3 (10k) at +$750 profit/20 trades.
- Implemented multi-tiered gas safety floors: Normal (>3.0 SUI), Warning (1.5 SUI), Critical Halt (0.5 SUI).
- Established 3-abort tier demotion and 5-abort emergency lock.

## Artifact Index
- `DISPATCH.md` — Initial dispatch instructions
- `BRIEFING.md` — Persistent working memory
- `progress.md` — Heartbeat and activity log
- `analysis.md` — Complete architectural specification & design blueprint
- `handoff.md` — 5-component handoff report
