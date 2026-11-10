## 2026-11-10T18:21:33Z
You are survey_1 (teamwork_spec_miner).
Your state folder is: /Users/vitorhrds/Documents/Github/hypothesis/.agents/teamwork/teamwork_spec_miner_survey_1
Working directory: /Users/vitorhrds/Documents/Github/hypothesis

You MUST read /Users/vitorhrds/Documents/Github/hypothesis/.agents/teamwork/ORIGINAL_REQUEST.md before starting.

Your task:
Investigate authoritative protocol specifications, contract interfaces, packages, and integration patterns for:
1. Turbos Finance CLMM on Sui Mainnet:
   - Package IDs, pool structures, router / swap entry functions, tick math, quote calculation mechanics.
   - Exact PTB swap commands (e.g., `swap_a_b`, `swap_b_a`, coin splitting, recipient, slippage parameters, version/clock/fee objects).
   - How to poll continuous real-time quotes in scanner (`params.amm_target = "turbos"`).
   - Known pool IDs for key pairs (DEEP/SUI, DEEP/USDC, SUI/USDC, CETUS/SUI).
2. DeepBook V3 & Cetus Reverse Route (DeepBook Ask -> Cetus Bid):
   - Exact mechanics when Cetus Price > DeepBook Ask: flashloan asset determination (borrow quote vs base), market buy on DeepBook (Ask), swap on Cetus (Bid), repay flashloan within the same PTB.
   - Interface contracts and coin object flow in the PTB.

Deliver a comprehensive specification report in:
`/Users/vitorhrds/Documents/Github/hypothesis/.agents/teamwork/teamwork_spec_miner_survey_1/handoff.md`
Follow the Handoff Protocol (Observation, Logic Chain, Caveats, Conclusion, Verification Method).
When finished, send a message to your parent with the report summary.
