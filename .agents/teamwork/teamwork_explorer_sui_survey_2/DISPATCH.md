## 2026-11-10T02:02:07Z
Sender: bb8c036e-693a-4192-a9f6-25494af55dae
Content:
You are teamwork_explorer_sui_survey_2.
Your working directory is /Users/vitorhrds/Documents/Github/hypothesis/.agents/teamwork/teamwork_explorer_sui_survey_2/
You must read /Users/vitorhrds/Documents/Github/hypothesis/.agents/teamwork/ORIGINAL_REQUEST.md before starting work.

Objective:
Investigate and design the dynamic capital scaling engine and wallet balance tracking architecture for the Sui DeepBookV3 & Cetus arbitrage bot.
Specifically:
1. Examine existing wallet and balance checking code in the repository (e.g. `trading-engine/venues/sui_deepbook_venue.py`, RPC clients, etc.).
2. Detail how the bot will connect to Sui Mainnet RPC (via GraphQL and/or JSON-RPC) to query:
   - SUI balance (wallet has 5.419245048 SUI) for gas management and alerting if gas drops below safe floor.
   - Native USDC balance (`0xdba34672e30cb065b1f93e3ab55318768fd6fef66c15942c9f7cb846e2f900e7::usdc::USDC`, 6 decimals).
3. Specify the dynamic scaling logic:
   - Initial `flash_borrow_amount = 1_000_000_000` (1,000 USDC nativo).
   - Baseline net profit tracking: how accumulated net profit is calculated and verified periodically.
   - Threshold transitions: when accumulated profit triggers transition from 1,000 USDC to 5,000 USDC (`5_000_000_000`), and subsequently to 10,000 USDC (`10_000_000_000`).
   - Drawdown / safety guardrails: what happens if a dry run or execution consumes unexpected gas or if balances diverge.
4. Detail the programmatic test approach for validating the scaling state machine and balance check routines.

Constraints:
- You are strictly READ-ONLY. DO NOT modify or create any implementation code files.
- Deliver your detailed report in `analysis.md` and `handoff.md` in your working directory `/Users/vitorhrds/Documents/Github/hypothesis/.agents/teamwork/teamwork_explorer_sui_survey_2/`.
- Maintain heartbeat in `progress.md` with timestamps.
- When finished, send a brief completion message to your caller.
