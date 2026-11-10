# BRIEFING — 2026-11-10T02:02:00Z

## Mission
Investigate and extract exact technical specifications and existing codebase state for the Sui DeepBookV3 and Cetus AMM atomic flash loan arbitrage bot.

## 🔒 My Identity
- Archetype: Specification Miner
- Roles: Technical Investigator, Move PTB & Sui DEX Specification Extractor
- Working directory: /Users/vitorhrds/Documents/Github/hypothesis/.agents/teamwork/teamwork_spec_miner_sui_survey_1
- Original parent: bb8c036e-693a-4192-a9f6-25494af55dae
- Milestone: Sui Survey & Technical Specification Extraction

## 🔒 Key Constraints
- Strictly READ-ONLY. DO NOT modify or create any implementation code files.
- Deliver detailed report in `analysis.md` and `handoff.md` in working directory.
- Maintain heartbeat in `progress.md` with timestamps.
- Prioritize authoritative sources over LLM prior knowledge.
- Document exact Mainnet pool IDs, Coin Types, decimals, tick sizes for all 4 pairs: SUI/USDC, DEEP/SUI, DEEP/USDC, CETUS/SUI.
- Detail the exact 8-step atomic PTB structure in Move (DeepBookV3 Hot Potato loan, Cetus swap, DeepBook swap/quench, profit extraction, gas coin handling).
- Detail error handling, VM reversion behavior on negative spread, and zero leg risk guarantees.

## Current Parent
- Conversation ID: bb8c036e-693a-4192-a9f6-25494af55dae
- Updated: 2026-11-10T02:18:00Z

## Task Summary
- **What to build**: Specification discovery report (analysis.md & handoff.md) detailing Sui DeepBookV3 and Cetus AMM flash loan arbitrage bot mechanics, pool IDs, coin types, Move PTB commands, error behaviors.
- **Success criteria**: Comprehensive analysis.md and handoff.md covering all 4 required areas with verifiable code references and exact Move PTB step breakdown.
- **Interface contracts**: Move PTB commands on Sui SDK / pysui / custom PTB builder, DeepBookV3 & Cetus AMM contracts on Sui Mainnet.
- **Code layout**: Existing code in `trading-engine/venues/sui_deepbook_venue.py` and related files. Output strictly in `.agents/teamwork/teamwork_spec_miner_sui_survey_1/`.

## Key Decisions Made
- Initial investigation checked existing files in `trading-engine/venues/sui_deepbook_venue.py`, tests, simulations, and TypeScript scripts.
- Verified deprecation of legacy JSON-RPC (-32601) and confirmed migration to official Sui GraphQL RPC (`https://graphql.mainnet.sui.io/graphql`).
- Verified all 4 trading pairs on-chain via GraphQL (pool IDs, coin types, decimals, tick sizes, fee tiers).
- Verified exact Move function signatures for DeepBookV3 and Cetus CLMM router on mainnet.
- Validated all 20 test suite cases across `test_venues_unit.py`, `test_adversarial_challenger_2.py`, and `test_quant_vectors_e2e.py` (100% pass rate).

## Artifact Index
- `.agents/teamwork/teamwork_spec_miner_sui_survey_1/DISPATCH.md` — Dispatch prompt and check-in history
- `.agents/teamwork/teamwork_spec_miner_sui_survey_1/BRIEFING.md` — Situational awareness
- `.agents/teamwork/teamwork_spec_miner_sui_survey_1/progress.md` — Liveness heartbeat (completed)
- `.agents/teamwork/teamwork_spec_miner_sui_survey_1/analysis.md` — Comprehensive technical specification
- `.agents/teamwork/teamwork_spec_miner_sui_survey_1/handoff.md` — 5-component self-contained handoff report
