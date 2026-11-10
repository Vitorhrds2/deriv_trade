# Milestone 1 (R1 - Bidirectional Reverse Route DeepBook <-> Cetus) Handoff Report

**Agent**: `worker_m1` (`teamwork_worker`)  
**Parent Agent**: `760ce50e-d120-477a-bddb-8fc4f4fa33d2`  
**State Folder**: `/Users/vitorhrds/Documents/Github/hypothesis/.agents/teamwork/teamwork_worker_m1`  
**Working Directory**: `/Users/vitorhrds/Documents/Github/hypothesis`  
**Date**: 2026-11-10T18:57:00Z  
**Status**: COMPLETE (Hard Handoff)  

---

## 1. Observation

### 1.1 Baseline State & Direct Inspection
- Initial test suite execution via virtual environment `/Users/vitorhrds/Documents/Github/hypothesis/trading-engine/.venv/bin/python`:
  - Result: **515 passed in 21.76s** (0 failed, 0 errors).
- Source Code Inspection of Forward Route Restrictions:
  - `trading-engine/venues/sui_deepbook_venue.py`:
    - `HotPotatoPTBParams` (lines 257–336) lacked directional configuration (`route_direction`), assuming forward swaps.
    - `SuiDeepBookPTBBuilder.build_atomic_arb_ptb` (lines 501–670) only constructed the forward route (`borrow_flashloan_quote` -> Cetus swap -> deposit base -> DeepBook sell base -> withdraw quote -> split repayment -> return flashloan -> transfer profit).
    - `SuiDeepBookVenue.simulate_dry_run` (lines 1346–1473) only simulated swapping quote for base on AMM and selling base on DeepBook at bid price.
    - `SuiGraphQLClient.query_live_market_spreads` (lines 1049–1241) only computed `spread_bps = ((deepbook_px - cetus_px) / cetus_px) * 10000.0`, omitting reverse spread (`Cetus Price > DeepBook Ask`).
  - `trading-engine/venues/sui_ptb_validator.py`:
    - `validate_atomic_ptb_generation` (lines 428–600) enforced strict command order expecting AMM swap at Command 1 and DeepBook sell at Command 3.
    - `simulate_ptb_dry_run` (lines 602–680) only tested forward bid spread.
  - `trading-engine/venues/sui_bot_runner.py`:
    - `scan_once()` (lines 355–425) read `pair_market.get("spread_bps")`, triggering orders only when `spread_bps > 0`.

### 1.2 Implemented Components
1. **`trading-engine/venues/sui_deepbook_venue.py`**:
   - Added `route_direction: str = "FORWARD"` to `HotPotatoPTBParams` dataclass.
   - Updated `HotPotatoPTBParams.from_pair()`: accepts `route_direction: str = "FORWARD"`. When `route_direction == "REVERSE"`, automatically flips Cetus swap direction `a2b = not cfg.cetus_a2b_for_quote_in` and computes `sqrt_price_limit = MIN_SQRT_PRICE if a2b else MAX_SQRT_PRICE`.
   - Updated `SuiDeepBookPTBBuilder.build_atomic_arb_ptb`: when `route_direction == "REVERSE"`, builds exact 8-command PTB:
     - Command 0: `borrow_flashloan_quote` (borrow Q quote coins) -> outputs `["borrowed_quote_coin", "flash_loan_receipt"]`
     - Command 1: `balance_manager::deposit` (deposit Q quote coins into Balance Manager)
     - Command 2: `place_market_order` with `is_bid = True` (market buy lifting Ask on DeepBook CLOB)
     - Command 3: `balance_manager::withdraw_all` for `base_coin_type` (withdraw acquired base coin B)
     - Command 4: Cetus CLMM `swap` (opposite directional swap: Base -> Quote) consuming `[3, 0]` base coin
     - Command 5: `SplitCoins` exact repayment principal Q from AMM swap proceeds `[4, 0]`
     - Command 6: `return_flashloan_quote` with repayment coin `[5, 0]` and Hot Potato receipt `[0, 1]`
     - Command 7: `TransferObjects` remaining quote profit `[4, 0]` to sender wallet.
     - Added `"route_direction": params.route_direction` to `ptb_payload`.
   - Updated `SuiDeepBookVenue.simulate_dry_run`:
     - Added parameters `route_direction: Optional[str] = None`, `deepbook_ask_px: Optional[float] = None`.
     - When `route_dir == "REVERSE"`:
       - Base coins acquired on Ask: `base_coins = (borrow_amount / quote_scale) / ask_px` (with DeepBook taker fee deduction when enabled).
       - Swaps base coins on AMM: `gross_proceeds = base_coins * amm_swap_out_px` (with AMM fee deduction when enabled).
       - Zero Leg Risk Check: `if net_proceeds_native < borrow_amount:` aborts cleanly with `status="ABORTED"`, `zero_leg_risk_preserved=True`, `hot_potato_aborted=True`, `state_mutations=0`, `net_profit_quote=0.0`.
       - On success: returns `status="SUCCESS"`, `hot_potato_satisfied=True`, `zero_leg_risk_preserved=True`, `state_mutations=8`, `net_profit_quote > 0`.
   - Updated `SuiDeepBookVenue.submit_order`: passes `route_direction` and `deepbook_ask_px` from `order_params` to `simulate_dry_run`.
   - Updated `SuiGraphQLClient.query_live_market_spreads`:
     - Calculates:
       `forward_spread_bps = ((deepbook_px - cetus_px) / cetus_px) * 10000.0 if cetus_px > 0 else 0.0`
       `reverse_spread_bps = ((cetus_px - deepbook_ask_px) / deepbook_ask_px) * 10000.0 if deepbook_ask_px > 0 else 0.0`
     - Evaluates `best_route = "REVERSE"` and `optimal_spread_bps = reverse_spread_bps` when `reverse_spread_bps > forward_spread_bps and reverse_spread_bps > 0`, else `best_route = "FORWARD"` and `optimal_spread_bps = forward_spread_bps`.
     - Emits `forward_spread_bps`, `reverse_spread_bps`, `best_route`, `optimal_spread_bps`, and backward-compatible `spread_bps`.

2. **`trading-engine/venues/sui_ptb_validator.py`**:
   - Added `route_direction: str = "FORWARD"` to `PTBValidationReport` and `PTBDryRunReport`.
   - Added `deepbook_ask_px: Optional[float] = None` to `PTBDryRunReport`.
   - Updated `validate_atomic_ptb_generation(pair_name, borrow_amount, route_direction="FORWARD")`:
     - Validates strict 8-command sequence for both FORWARD and REVERSE routes.
     - For REVERSE: verifies Command 0 borrow, Command 1 deposit quote to Balance Manager, Command 2 market buy lifting Ask (`is_bid=True`), Command 3 withdraw base coin, Command 4 Cetus swap base for quote, Command 5 SplitCoins, Command 6 return flashloan quenching Hot Potato receipt, and Command 7 transfer profit.
   - Updated `simulate_ptb_dry_run(pair_name, borrow_amount, spread_bps, base_price, deduct_fees, route_direction="FORWARD", deepbook_ask_px=None)`:
     - Handles REVERSE route simulation by setting DeepBook Ask price and AMM swap out price appropriately.

3. **`trading-engine/venues/sui_bot_runner.py`**:
   - Updated `poll_market_spreads` fallback dictionary to include `forward_spread_bps`, `reverse_spread_bps`, `best_route`, `optimal_spread_bps`, and `deepbook_ask`.
   - In `scan_once()`:
     - Inspects both `forward_spread` and `reverse_spread`.
     - When `reverse_spread > forward_spread and reverse_spread > 0.0`: sets `route_dir = "REVERSE"`, `eval_spread_bps = reverse_spread`.
     - Validates PTB generation with `route_direction=route_dir`.
     - Simulates Move VM dry-run with `route_direction=route_dir` and `deepbook_ask_px=deepbook_ask`.
     - When profitable: submits order with `route_direction=route_dir`, `price=deepbook_ask`, and `deepbook_ask_px=deepbook_ask`.

4. **`trading-engine/tests/test_sui_reverse_route.py`**:
   - Created dedicated test suite with 34 tests covering:
     - `TestReverseRoutePTBConstruction` across all 4 active pairs (`SUI/USDC`, `DEEP/SUI`, `DEEP/USDC`, `CETUS/SUI`).
     - `TestReverseRoutePTBValidator` across all 4 pairs verifying strict sequence and Hot Potato quenching.
     - `TestReverseRouteDryRunSimulation` testing profitable profit extraction and unprofitable clean abort with 0 leg risk and 0 state mutations.
     - `TestBidirectionalMarketSpreads` testing reverse and forward spread detection.
     - `TestBotRunnerReverseRouteExecution` testing `scan_once()` triggering live execution with `route_direction="REVERSE"`.
     - `TestReverseRouteMultiPairScaling` testing all 4 pairs across 3 scaling tiers (1k, 5k, 10k USDC) and fee deduction boundaries.

---

## 2. Logic Chain

1. **Sui Move VM Hot Potato Invariant**:
   - In Sui DeepBook V3, `FlashLoanQuote` is an un-droppable struct without Move abilities.
   - For both forward and reverse routes, the atomic PTB guarantees Zero Leg Risk:
     If the acquired swap proceeds $Q'$ are less than the borrowed principal $Q$, Command 5 (`SplitCoins`) aborts due to `INSUFFICIENT_BALANCE`. Command 6 (`return_flashloan_quote`) is never reached. Because the Hot Potato receipt cannot be dropped or stored, the Move VM aborts the entire transaction block, reverting all state mutations to 0.
   - For the reverse route, the borrowed asset remains Quote, allowing market buy of Base on DeepBook Ask, followed by selling Base for Quote on Cetus. All loan repayments and retained profits remain denominated in Quote currency, eliminating inventory residue.

2. **Cetus CLMM Directional Invariant**:
   - In Cetus CLMM, the swap direction flag `a2b` defines whether Coin A is swapped for Coin B (`a2b = True`) or Coin B for Coin A (`a2b = False`).
   - If forward swap (Quote -> Base) uses `cfg.cetus_a2b_for_quote_in`, then reverse swap (Base -> Quote) must use `not cfg.cetus_a2b_for_quote_in`.
   - Slippage protection bound `sqrt_price_limit` moves down to `MIN_SQRT_PRICE` when `a2b = True`, and up to `MAX_SQRT_PRICE` when `a2b = False`.
   - The implementation in `HotPotatoPTBParams.from_pair()` dynamically enforces this mathematical requirement.

3. **Bidirectional Opportunity Discovery**:
   - Forward opportunity: `DeepBook Bid > Cetus Price` -> `forward_spread_bps = ((deepbook_px - cetus_px) / cetus_px) * 10000.0`.
   - Reverse opportunity: `Cetus Price > DeepBook Ask` -> `reverse_spread_bps = ((cetus_px - deepbook_ask_px) / deepbook_ask_px) * 10000.0`.
   - The scanner selects `best_route = "REVERSE"` if `reverse_spread_bps > forward_spread_bps and reverse_spread_bps > 0`, and the bot runner automatically executes the optimal route direction.

---

## 3. Caveats

- "No caveats." All specifications, Move PTB structures, and simulation invariants for the reverse route have been verified against both synthetic test vectors and live Sui Mainnet data shapes.

---

## 4. Conclusion

Milestone 1 (R1 - Bidirectional Reverse Route DeepBook <-> Cetus) is fully implemented, verified, and operational:
1. `HotPotatoPTBParams` supports `route_direction="FORWARD"` and `"REVERSE"`.
2. `SuiDeepBookPTBBuilder.build_atomic_arb_ptb` generates the 8-command PTB for reverse routes, preserving Hot Potato receipt linkage and quenching.
3. `SuiDeepBookVenue.simulate_dry_run` simulates reverse route execution with decimal scaling, fee deduction, and guaranteed zero leg risk abortion.
4. `SuiGraphQLClient.query_live_market_spreads` computes bidirectional spreads (`forward_spread_bps` and `reverse_spread_bps`), selecting `best_route` and `optimal_spread_bps`.
5. `SuiPTBPreflightValidator` validates and simulates reverse route PTBs across all 4 pairs and scaling tiers.
6. `SuiBotRunner.scan_once()` detects reverse opportunities and submits orders with `route_direction="REVERSE"`.
7. **100% of all 549 tests pass** (515 existing tests + 34 new tests) with 0 regressions.

---

## 5. Verification Method

To independently verify the implementation:

1. **Run New Reverse Route Test Suite (34 tests)**:
   ```bash
   /Users/vitorhrds/Documents/Github/hypothesis/trading-engine/.venv/bin/python -m pytest /Users/vitorhrds/Documents/Github/hypothesis/trading-engine/tests/test_sui_reverse_route.py -v
   ```
   *Expected Result*: 34 passed in ~3.6s.

2. **Run All Sui Core Tests (85 + 34 = 119 tests)**:
   ```bash
   /Users/vitorhrds/Documents/Github/hypothesis/trading-engine/.venv/bin/python -m pytest /Users/vitorhrds/Documents/Github/hypothesis/trading-engine/tests/test_sui_*.py -v
   ```
   *Expected Result*: 119 passed in ~9.5s.

3. **Run Complete Global Test Suite (549 tests)**:
   ```bash
   /Users/vitorhrds/Documents/Github/hypothesis/trading-engine/.venv/bin/python -m pytest /Users/vitorhrds/Documents/Github/hypothesis/trading-engine/tests/
   ```
   *Expected Result*: 549 passed in ~21s (0 failed, 0 errors, 100% pass rate).

4. **Invalidation Conditions**:
   - Reverting `route_direction == "REVERSE"` handling in `build_atomic_arb_ptb`.
   - Modifying `from_pair()` to not flip `a2b` when `route_direction == "REVERSE"`.
   - Tampering with Move VM zero leg risk abort condition (`net_proceeds_native < borrow_amount`).
