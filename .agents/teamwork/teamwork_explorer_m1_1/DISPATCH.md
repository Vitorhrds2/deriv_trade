## 2026-11-10T02:20:52Z
You are teamwork_explorer_m1_1.
Your working directory is /Users/vitorhrds/Documents/Github/hypothesis/.agents/teamwork/teamwork_explorer_m1_1/
You must read:
1. /Users/vitorhrds/Documents/Github/hypothesis/.agents/teamwork/ORIGINAL_REQUEST.md
2. /Users/vitorhrds/Documents/Github/hypothesis/.agents/teamwork/PROJECT.md
3. /Users/vitorhrds/Documents/Github/hypothesis/.agents/teamwork/teamwork_spec_miner_sui_survey_1/handoff.md

Milestone M1 Scope:
Multi-Pair Sui DeepBookV3 & Cetus AMM Atomic Flash Loan PTB Arbitrage Engine.

Objective:
Produce a technical implementation blueprint for expanding `trading-engine/venues/sui_deepbook_venue.py` to support all 4 pairs:
- SUI/USDC
- DEEP/SUI
- DEEP/USDC
- CETUS/SUI

Specifically:
1. Design the exact data structures and dictionary/dataclass configs for the 4 pairs:
   - Coin types, decimals, DeepBook pool IDs, Cetus pool IDs, fee rates, tick sizes, lot sizes, and Cetus `a2b` flag + `sqrt_price_limit`.
2. Detail how `HotPotatoPTBParams` and `SuiDeepBookPTBBuilder.build_atomic_arb_ptb` should be generalized so that any of the 4 pairs can be passed in cleanly and build the 8-command Move PTB.
3. Verify the exact Move package IDs and function calls for both quote-borrowed and base-borrowed flash loans if applicable.
4. Prepare the exact code edits recommendations for the Worker.

Constraints:
- You are strictly READ-ONLY. DO NOT modify any implementation code.
- Write `analysis.md` and `handoff.md` in your working directory.
- Maintain `progress.md` with timestamps.
- When done, send a brief completion message to your caller.
