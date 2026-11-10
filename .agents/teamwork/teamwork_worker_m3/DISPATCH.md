## 2026-11-10T19:36:26Z

You are worker_m3 (teamwork_worker). Your mission is to implement Milestone 3 (Requirement R4) for the Sui Arbitrage Bot in production: Multi-DEX Integration with Turbos Finance CLMM (continuous quote scanning + atomic PTB execution).

MANDATORY FIRST STEPS:
1. Read ORIGINAL_REQUEST.md at: /Users/vitorhrds/Documents/Github/hypothesis/.agents/teamwork/ORIGINAL_REQUEST.md
2. Read PROJECT.md at: /Users/vitorhrds/Documents/Github/hypothesis/.agents/teamwork/PROJECT.md
3. Read the Spec Miner Survey 1 findings at: /Users/vitorhrds/Documents/Github/hypothesis/.agents/teamwork/teamwork_spec_miner_survey_1/handoff.md
4. Read the Explorer Survey 2 findings at: /Users/vitorhrds/Documents/Github/hypothesis/.agents/teamwork/teamwork_explorer_survey_2/handoff.md

MANDATORY INTEGRITY WARNING:
DO NOT CHEAT. All implementations must be genuine. DO NOT hardcode test results, create dummy/facade implementations, or circumvent the intended task. A teamwork_auditor will independently verify your work. Integrity violations WILL be detected and your work WILL be rejected.

SCOPE OF IMPLEMENTATION (Milestone 3 - R4):

1. Turbos Protocol Constants & Registry:
   - In `trading-engine/venues/sui_deepbook_venue.py`:
     - Define Turbos Mainnet package & shared object constants:
       ```python
       TURBOS_PACKAGE_ID = "0xa5a0c25c79e428eba04fb98b3fb2a34db45ab26d4c8faf0d7e39d66a63891e64"
       TURBOS_VERSIONED_ID = "0xf1cf0e81048df168ebeb1b8030fad24b3e0b53ae827c25053fff0779c1445b6f"  # initialSharedVersion: 1621135
       TURBOS_POOL_CONFIG_ID = "0xc294552b2765353bcafa7c359cd28fd6bc237662e5db8f09877558d81669170c"
       ```
     - Register verified Turbos Mainnet pools for all 4 pairs:
       - `SUI/USDC`: Pool `0x0df4f02d0e210169cb6d5aabd03c3058328c06f2c4dbb0804faa041159c78443` (Coin A: SUI 9 dec, Coin B: USDC 6 dec, Fee: 5 bps, initSharedVer: 426673878)
       - `DEEP/SUI`: Pool `0xbca476e3c744648c65b1fae5551b86be8ad7f482ca9c2268dad1d6b4fd0e2635` (Coin A: DEEP 6 dec, Coin B: SUI 9 dec, Fee: 30 bps, initSharedVer: 389633758)
       - `DEEP/USDC`: Pool `0x198af6ff81028c6577e94465d534c4e2cfcbbab06a95724ece7011c55a9d1f5a` (Coin A: DEEP 6 dec, Coin B: USDC 6 dec, Fee: 15 bps, initSharedVer: 599890732)
       - `CETUS/SUI`: Pool `0xdf9d069bdfd51515aa0316698225a26444cbdf3cccd130a226b3ac81cfe2f606` (Coin A: CETUS 9 dec, Coin B: SUI 9 dec, Fee: 30 bps, initSharedVer: 561404948)
     - Extend `PairConfig` to include Turbos fields (`turbos_pool_id`, `turbos_fee_bps`, `turbos_a2b`).

2. Continuous Real-Time Quote Scanner for Turbos CLMM:
   - In `SuiGraphQLClient`:
     - Implement `get_turbos_pool_spot_price(pool_id: str, pair_name: str) -> float`.
     - In `query_live_market_spreads`, include Turbos pools in query batches or support `params.amm_target = "turbos"` and multi-DEX comparison.
     - Implement price math using Q64.64 sqrt_price integer decoding:
       P_{B/A} = (sqrt_price / 2^64)^2 * 10^(decimals_A - decimals_B).
     - Calculate both `forward_spread_bps` and `reverse_spread_bps` for Turbos vs DeepBook.
     - Support multi-DEX opportunity selection (comparing Cetus and Turbos net profitability).

3. Atomic PTB Builder & Executor with Hot Potato Quenching:
   - In `SuiDeepBookPTBBuilder.build_atomic_arb_ptb`:
     - When `params.amm_target == "turbos"`:
       Use composable router functions:
       `0xa5a0c25c79e428eba04fb98b3fb2a34db45ab26d4c8faf0d7e39d66a63891e64::swap_router::swap_a_b_with_return_` and `swap_b_a_with_return_`.
       Arguments: `[pool, coins (MakeMoveVec([coin])), amount_specified, amount_threshold, sqrt_price_limit, is_exact_input, recipient, deadline, clock, versioned]`.
       - For FORWARD route (Turbos Buy -> DeepBook Sell):
         Borrow Quote -> Turbos swap Quote for Base -> DeepBook Market Sell Base -> Split Repayment Quote -> Return Flashloan Quench -> Transfer Profit.
       - For REVERSE route (DeepBook Buy -> Turbos Sell):
         Borrow Quote -> DeepBook Market Buy Base -> Turbos swap Base for Quote -> Split Repayment Quote -> Return Flashloan Quench -> Transfer Profit.
   - In `simulate_dry_run`:
     - Support `amm_target == "turbos"` in dry-run execution with Zero Leg Risk verification.
   - In `sui_ptb_validator.py` and `sui_bot_runner.py`:
     - Support Turbos validation and multi-DEX scanning/execution in bot runner.

4. Testing & Verification:
   - Create comprehensive unit & integration tests in `trading-engine/tests/test_sui_turbos_clmm.py`.
   - Test Turbos spot price calculation from sqrt_price for all 4 pairs.
   - Test Turbos PTB construction for both FORWARD and REVERSE routes, verifying MakeMoveVec wrapping, versioned object, clock, and Hot Potato return.
   - Test Turbos dry-run simulation (profit capture and abort on shortfall).
   - Test multi-DEX scanner selecting the best AMM (Cetus vs Turbos).
   - Run the complete test suite:
     `PYTHONPATH=trading-engine trading-engine/.venv/bin/pytest trading-engine/tests -v`
   - Ensure ALL 568 existing tests continue to pass with 0 regressions, plus all new Turbos tests pass.

## 2026-11-10T19:46:57Z

**Context**: Milestone 3 Implementation (Turbos Finance CLMM Multi-DEX)
**Content**: Safety timer fired. Checking on your implementation progress. What is your current status?
**Action**: Report current status and estimated completion.

## 2026-11-10T19:59:37Z

**Context**: Milestone 3 Implementation (Turbos Finance CLMM Multi-DEX)
**Content**: Heartbeat check (iteration 6). Checking in on your implementation progress across PTB builder, quote scanner, and tests. What is your current status?
**Action**: Report current status and estimated completion.
