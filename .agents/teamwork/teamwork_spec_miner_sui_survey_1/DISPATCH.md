## 2026-11-10T02:01:56Z
You are teamwork_spec_miner_sui_survey_1.
Your working directory is /Users/vitorhrds/Documents/Github/hypothesis/.agents/teamwork/teamwork_spec_miner_sui_survey_1/
You must read /Users/vitorhrds/Documents/Github/hypothesis/.agents/teamwork/ORIGINAL_REQUEST.md before starting work.

Objective:
Investigate and extract the exact technical specifications and existing codebase state for the Sui DeepBookV3 and Cetus AMM atomic flash loan arbitrage bot.
Specifically:
1. Examine `trading-engine/venues/sui_deepbook_venue.py` and any related Sui code/tests in the repository.
2. Document the exact Sui Mainnet pool IDs, Coin Types (native USDC `0xdba34672e30cb065b1f93e3ab55318768fd6fef66c15942c9f7cb846e2f900e7::usdc::USDC`, SUI `0x2::sui::SUI`, DEEP, CETUS), decimals, and tick sizes for all 4 pairs:
   - SUI/USDC
   - DEEP/SUI
   - DEEP/USDC
   - CETUS/SUI
3. Detail the exact 8-step atomic PTB (Programmable Transaction Block) structure in Move:
   - DeepBookV3 Hot Potato flash loan borrowing (0 bps fee)
   - Cetus AMM swap interfaces (pools, sqrt_price_limit, a2b vs b2a)
   - DeepBookV3 trading/swap interfaces
   - Hot Potato loan repayment / quenching
   - Profit extraction and safe gas coin handling
4. Detail error handling, VM reversion behavior on negative spread, and zero leg risk guarantees.

Constraints:
- You are strictly READ-ONLY. DO NOT modify or create any implementation code files.
- Deliver your detailed report in `analysis.md` and `handoff.md` in your working directory `/Users/vitorhrds/Documents/Github/hypothesis/.agents/teamwork/teamwork_spec_miner_sui_survey_1/`.
- Maintain heartbeat in `progress.md` with timestamps.
- When finished, send a brief completion message to your caller.


## 2026-11-10T02:12:59Z
**Context**: Sui DeepBookV3 and Cetus AMM Spec Survey
**Content**: Checking in on progress. Have you completed the inspection of `trading-engine/venues/sui_deepbook_venue.py`, pool IDs, and the 8-step Move PTB structure?
**Action**: Please update progress.md and let me know your status or if you need any assistance.
