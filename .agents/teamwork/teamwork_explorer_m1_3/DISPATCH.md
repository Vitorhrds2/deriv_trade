## 2026-11-10T02:21:11Z
You are teamwork_explorer_m1_3.
Your working directory is /Users/vitorhrds/Documents/Github/hypothesis/.agents/teamwork/teamwork_explorer_m1_3/
You must read:
1. /Users/vitorhrds/Documents/Github/hypothesis/.agents/teamwork/ORIGINAL_REQUEST.md
2. /Users/vitorhrds/Documents/Github/hypothesis/.agents/teamwork/PROJECT.md
3. /Users/vitorhrds/Documents/Github/hypothesis/.agents/teamwork/teamwork_spec_miner_sui_survey_1/handoff.md
4. /Users/vitorhrds/Documents/Github/hypothesis/.agents/teamwork/teamwork_explorer_sui_survey_2/handoff.md

Milestone M1 Scope:
Multi-Pair Dry-Run Simulation, Math Verification, and Test Harness.

Objective:
Produce a technical blueprint for the mathematical simulation and dry-run execution methods in `trading-engine/venues/sui_deepbook_venue.py` for all 4 pairs:
Specifically:
1. Generalize `SuiDeepBookVenue.simulate_dry_run(ptb, deepbook_bid_px, amm_swap_out_px)` to handle:
   - SUI/USDC, DEEP/SUI, DEEP/USDC, CETUS/SUI with correct decimal scaling (SUI: 9, USDC: 6, DEEP: 6, CETUS: 9).
   - Accurate fee deduction per pair (DeepBook: 10 bps for SUI/USDC and CETUS/SUI, 0 bps for DEEP/SUI and DEEP/USDC; Cetus: 0.05% or 0.25% fee tier).
   - Zero leg risk verification: confirming that if net proceeds < loan principal, `status == "ABORTED"` with zero leg risk preserved.
2. Outline the exact unit tests to be added/updated in `trading-engine/tests/` to test all 4 pairs.
3. Provide the test execution commands and expected outputs for the Worker.

Constraints:
- You are strictly READ-ONLY. DO NOT modify any implementation code.
- Write `analysis.md` and `handoff.md` in your working directory.
- Maintain `progress.md` with timestamps.
- When done, send a brief completion message to your caller.
