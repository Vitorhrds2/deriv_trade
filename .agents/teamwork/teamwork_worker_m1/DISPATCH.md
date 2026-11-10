## 2026-11-10T18:39:42Z

You are worker_m1 (teamwork_worker).
Your state folder is: /Users/vitorhrds/Documents/Github/hypothesis/.agents/teamwork/teamwork_worker_m1
Working directory: /Users/vitorhrds/Documents/Github/hypothesis

MANDATORY: You MUST read /Users/vitorhrds/Documents/Github/hypothesis/.agents/teamwork/ORIGINAL_REQUEST.md before starting work.
Also read /Users/vitorhrds/Documents/Github/hypothesis/.agents/teamwork/PROJECT.md and the survey handoff reports:
- /Users/vitorhrds/Documents/Github/hypothesis/.agents/teamwork/teamwork_explorer_survey_2/handoff.md (specifically Section 4.2 Blueprint)
- /Users/vitorhrds/Documents/Github/hypothesis/.agents/teamwork/teamwork_spec_miner_survey_1/handoff.md

MANDATORY INTEGRITY WARNING:
DO NOT CHEAT. All implementations must be genuine. DO NOT hardcode test results, create dummy/facade implementations, or circumvent the intended task. A teamwork_auditor will independently verify your work. Integrity violations WILL be detected and your work WILL be rejected.

Your Task: Implement Milestone 1 (R1 - Bidirectional Reverse Route DeepBook <-> Cetus):
1. In `trading-engine/venues/sui_deepbook_venue.py`:
   - Add `route_direction: str = "FORWARD"` to `HotPotatoPTBParams` (`"FORWARD"` | `"REVERSE"`).
   - In `SuiDeepBookPTBBuilder.build_atomic_arb_ptb`: support `route_direction == "REVERSE"`:
     - Command 0: `borrow_flashloan_quote` (borrow Q quote coins)
     - Command 1: Deposit Q into Balance Manager (`balance_manager::deposit`)
     - Command 2: Market buy on DeepBook Ask (`place_market_order` with `is_bid = True` lifting Ask)
     - Command 3: Withdraw acquired base coin B from Balance Manager (`balance_manager::withdraw_all<Base>`)
     - Command 4: AMM swap Base for Quote on Cetus (opposite directional swap: Base -> Quote)
     - Command 5: `SplitCoins` exact repayment principal Q from AMM swap proceeds
     - Command 6: `return_flashloan_quote` with repayment coin and Hot Potato receipt
     - Command 7: `TransferObjects` remaining quote profit to sender wallet.
   - In `SuiDeepBookVenue.simulate_dry_run`: add simulation support for `route_direction == "REVERSE"`:
     - Base coins acquired on Ask: `base_coins = (borrow_amount / quote_scale) / deepbook_ask_px`.
     - Swap base coins on AMM: `gross_proceeds = base_coins * amm_swap_out_px`.
     - Assert zero leg risk: If proceeds < borrow_amount, abort cleanly and guarantee `zero_leg_risk_preserved = True`.
   - In `SuiGraphQLClient.query_live_market_spreads`: calculate both spreads:
     `forward_spread_bps = ((deepbook_px - cetus_px) / cetus_px) * 10000.0`
     `reverse_spread_bps = ((cetus_px - deepbook_ask_px) / deepbook_ask_px) * 10000.0`
     and return `forward_spread_bps`, `reverse_spread_bps`, `best_route`, `optimal_spread_bps`.
2. In `trading-engine/venues/sui_ptb_validator.py`:
   - Update `validate_atomic_ptb_generation` and `simulate_ptb_dry_run` to accept and validate reverse routes.
3. In `trading-engine/venues/sui_bot_runner.py`:
   - In `scan_once()`: check both forward and reverse spreads, set `route_direction = "REVERSE"` when profitable, simulate, and trigger order.
4. In `trading-engine/tests/`:
   - Add unit tests for the reverse route covering PTB construction, validation, dry-run simulation, and zero leg risk abortion when spread is unprofitable.
5. Verification:
   - Run the complete test suite using Python virtual environment:
     `/Users/vitorhrds/Documents/Github/hypothesis/trading-engine/.venv/bin/python -m pytest /Users/vitorhrds/Documents/Github/hypothesis/trading-engine/tests/`
   - Ensure ALL 515 existing tests pass 100% without regression, PLUS all new reverse route tests pass.
6. Deliver a comprehensive handoff report to:
   `/Users/vitorhrds/Documents/Github/hypothesis/.agents/teamwork/teamwork_worker_m1/handoff.md`
   Follow Handoff Protocol (Observation, Logic Chain, Caveats, Conclusion, Verification Method).
   When finished, send a message to your parent with the report summary.
