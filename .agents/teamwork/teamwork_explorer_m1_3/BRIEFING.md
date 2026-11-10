# BRIEFING — 2026-11-10T02:29:00Z

## Mission
Produce a technical blueprint for multi-pair mathematical simulation, dry-run execution, and unit test harness for sui_deepbook_venue.py across SUI/USDC, DEEP/SUI, DEEP/USDC, and CETUS/SUI.

## 🔒 My Identity
- Archetype: explorer
- Roles: [explorer, synthesis, investigation]
- Working directory: /Users/vitorhrds/Documents/Github/hypothesis/.agents/teamwork/teamwork_explorer_m1_3
- Original parent: bb8c036e-693a-4192-a9f6-25494af55dae
- Milestone: M1

## 🔒 Key Constraints
- Read-only investigation — do NOT implement
- Only write to /Users/vitorhrds/Documents/Github/hypothesis/.agents/teamwork/teamwork_explorer_m1_3/
- Produce technical blueprint for multi-pair dry-run simulation, math verification, and test harness in trading-engine/venues/sui_deepbook_venue.py and trading-engine/tests/

## Current Parent
- Conversation ID: bb8c036e-693a-4192-a9f6-25494af55dae
- Updated: 2026-11-10T02:21:11Z

## Investigation State
- **Explored paths**:
  - `trading-engine/venues/sui_deepbook_venue.py` (lines 1–418)
  - `trading-engine/tests/test_venues_unit.py` (lines 349–435)
  - `trading-engine/tests/test_adversarial_challenger_2.py` (lines 70–225)
  - `.agents/teamwork/ORIGINAL_REQUEST.md`, `PROJECT.md`
  - `.agents/teamwork/teamwork_spec_miner_sui_survey_1/handoff.md`
  - `.agents/teamwork/teamwork_explorer_sui_survey_2/handoff.md`
- **Key findings**:
  - `simulate_dry_run` previously hardcoded $10^6$ scaling, lacked fee deduction, and supported only SUI/USDC.
  - Multi-pair parameters derived and validated: SUI (9 dec), USDC (6 dec), DEEP (6 dec), CETUS (9 dec).
  - DeepBook fees: 10 bps for SUI/USDC and CETUS/SUI; 0 bps (whitelisted) for DEEP/SUI and DEEP/USDC.
  - Cetus fees: 0.05% tier (5 bps) or 0.25% tier (25 bps).
  - Compound fee hurdles: ~15 bps (SUI/USDC), ~5 bps (DEEP/SUI, DEEP/USDC), ~35 bps (CETUS/SUI).
  - Bytecode zero leg risk: when net proceeds < loan principal, SplitCoins aborts with InsufficientBalance, quenching fails, 0 state mutations commit.
- **Unexplored areas**: None for M1 simulation blueprint.

## Key Decisions Made
- Designed `SUPPORTED_PAIRS` registry covering all 4 pairs with exact decimals, fees, pool IDs, and `a2b` flags.
- Generalized `simulate_dry_run` with `deduct_fees: bool = True` default and full decimal normalization.
- Designed 13-test suite in `trading-engine/tests/test_sui_deepbook_multipair.py`.
- Formulated exact updates for `test_adversarial_challenger_2.py` to maintain 100% green tests.

## Artifact Index
- `.agents/teamwork/teamwork_explorer_m1_3/DISPATCH.md` — Incoming task dispatch record
- `.agents/teamwork/teamwork_explorer_m1_3/analysis.md` — Comprehensive technical blueprint and code specifications
- `.agents/teamwork/teamwork_explorer_m1_3/handoff.md` — 5-component handoff report for Worker
- `.agents/teamwork/teamwork_explorer_m1_3/progress.md` — Activity and liveness tracking
