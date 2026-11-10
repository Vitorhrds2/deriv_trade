# BRIEFING — 2026-11-10T02:27:00Z

## Mission
Produce a technical implementation blueprint for expanding `trading-engine/venues/sui_deepbook_venue.py` to support all 4 pairs: SUI/USDC, DEEP/SUI, DEEP/USDC, CETUS/SUI.

## 🔒 My Identity
- Archetype: explorer
- Roles: investigation, synthesis
- Working directory: /Users/vitorhrds/Documents/Github/hypothesis/.agents/teamwork/teamwork_explorer_m1_1/
- Original parent: bb8c036e-693a-4192-a9f6-25494af55dae
- Milestone: M1

## 🔒 Key Constraints
- Read-only investigation — do NOT implement
- Scope limited to M1 blueprint for expanding `trading-engine/venues/sui_deepbook_venue.py` to 4 pairs (SUI/USDC, DEEP/SUI, DEEP/USDC, CETUS/SUI)
- Write analysis.md and handoff.md in own working directory

## Current Parent
- Conversation ID: bb8c036e-693a-4192-a9f6-25494af55dae
- Updated: 2026-11-10T02:21:00Z

## Investigation State
- **Explored paths**:
  - `ORIGINAL_REQUEST.md`, `PROJECT.md`, `teamwork_spec_miner_sui_survey_1/handoff.md`, `teamwork_spec_miner_sui_survey_1/analysis.md`
  - `trading-engine/venues/sui_deepbook_venue.py`
  - `trading-engine/tests/test_venues_unit.py` and `trading-engine/tests/test_adversarial_challenger_2.py`
  - Live Sui GraphQL RPC queries for all 4 DeepBook and Cetus pools
- **Key findings**:
  - Coin ordering in Cetus is fixed: SUI/USDC is `Pool<USDC, SUI>`, DEEP/SUI is `Pool<DEEP, SUI>`, DEEP/USDC is `Pool<DEEP, USDC>`, CETUS/SUI is `Pool<CETUS, SUI>`.
  - For Quote-borrowed flash loans: SUI/USDC requires `a2b = True`; DEEP/SUI, DEEP/USDC, and CETUS/SUI require `a2b = False`.
  - `sqrt_price_limit` is `4295048016` (MIN) for `a2b = True`, and `79226673515401279992447579055` (MAX) for `a2b = False`.
  - Base-borrowed flash loan variant is also formally verified using `borrow_flashloan_base` and `return_flashloan_base`.
  - Full code design formulated: `PairConfig` dataclass, `SUI_PAIRS_CONFIG` dictionary, generalized `HotPotatoPTBParams`, generalized `build_atomic_arb_ptb`, multi-pair dry-run simulation, and GraphQL pool state reader.
- **Unexplored areas**: None. Ready for analysis and handoff synthesis.

## Key Decisions Made
- Structured the blueprint to be 100% backward-compatible with existing tests (`test_venues_unit.py`, `test_adversarial_challenger_2.py`).
- Retained Command 1 argument structure matching existing test assertions while allowing parameterized pool IDs, a2b, and sqrt_price_limit.
- Designed `PairConfig` with full metadata (coin types, decimals, pool IDs, fee rates, tick/lot sizes, price factors).

## Artifact Index
- DISPATCH.md — Task dispatch
- BRIEFING.md — Persistent context & state
- progress.md — Liveness heartbeat
- analysis.md — Technical implementation blueprint
- handoff.md — 5-component handoff report
