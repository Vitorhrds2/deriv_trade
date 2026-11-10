# Architectural Audit & Exploration Report: Sui DeepBook V3, Cetus & Turbos Arbitrage Bot

**Author**: `survey_2` (`teamwork_explorer`)  
**Target Repository**: `/Users/vitorhrds/Documents/Github/hypothesis/trading-engine`  
**Date**: 2026-11-10  
**Status**: COMPLETE  

---

## 1. Observation

### 1.1 Existing Test Suite Audit (`trading-engine/tests/`)
- **Execution Command**:
  ```bash
  /Users/vitorhrds/Documents/Github/hypothesis/trading-engine/.venv/bin/python -m pytest /Users/vitorhrds/Documents/Github/hypothesis/trading-engine/tests/ -v
  ```
- **Test Framework**:
  - `pytest 9.2.0`, `pytest-asyncio 1.4.1.post1`, `pluggy 1.7.0` running under Python `3.13.3` in virtual environment `trading-engine/.venv`.
- **Global Test Count & Status**:
  - **515 collected, 515 passed, 0 failed, 0 errors** in `21.35s`.
- **Sui-Specific Test Suite**:
  - Command: `/Users/vitorhrds/Documents/Github/hypothesis/trading-engine/.venv/bin/python -m pytest /Users/vitorhrds/Documents/Github/hypothesis/trading-engine/tests/test_sui_*.py -v`
  - Result: **85 passed in 6.29s** (100% pass rate).
- **Per-File Test Breakdown**:
  | Test File | Category | Test Count | Pass Status |
  |---|---|---|---|
  | `tests/test_sui_deepbook_multipair.py` | Sui Core Multi-Pair Configuration & Dry-Run | 13 | 13/13 PASSED |
  | `tests/test_sui_production_deployment.py` | Sui Health Server & Bot Runner Lifecycle | 14 | 14/14 PASSED |
  | `tests/test_sui_programmatic_verification.py` | Sui Preflight, PTB Validation & Dry-Run Simulation | 31 | 31/31 PASSED |
  | `tests/test_sui_scaling_engine.py` | Capital Scaling Tiers, Gas Safety Floors & Sizing | 27 | 27/27 PASSED |
  | **Sui Subtotal** | **Core Sui Arbitrage Suite** | **85** | **85/85 PASSED** |
  | `tests/test_adversarial_challenger_1.py` | Microstructure & Exchange Concurrency | 15 | 15/15 PASSED |
  | `tests/test_adversarial_challenger_2.py` | Sui Hot Potato Reversion & Multi-Pair Invariants | 38 | 38/38 PASSED |
  | `tests/test_adversarial_m1_challenger.py` | Adversarial Microstructure Suite | 178 | 178/178 PASSED |
  | `tests/test_adversarial_m2_challenger.py` | Adversarial Scaling & Boundary Tests | 55 | 55/55 PASSED |
  | `tests/test_adversarial_m3.py` | Adversarial Preflight & Simulation | 43 | 43/43 PASSED |
  | `tests/test_adversarial_m4_deployment.py` | Adversarial Deployment & Health Server | 24 | 24/24 PASSED |
  | `tests/test_adversarial_m5_challenger.py` | Adversarial Edge Execution | 26 | 26/26 PASSED |
  | `tests/test_adversarial_remediation_challenger.py`| Adversarial Remediation Suite 1 | 11 | 11/11 PASSED |
  | `tests/test_adversarial_remediation_challenger_2.py`| Adversarial Remediation Suite 2 | 16 | 16/16 PASSED |
  | `tests/test_mocks_unit.py` | Microstructure Mock Unit Tests | 12 | 12/12 PASSED |
  | `tests/test_venues_unit.py` | Venue Registry & Protocol Connectors | 12 | 12/12 PASSED |
  | **Grand Total** | **All Tests** | **515** | **515/515 PASSED** |

---

### 1.2 Core Component Architecture & File Inventory
The Sui DeepBook V3 & Cetus Arbitrage system consists of the following modules in `trading-engine/`:

1. **`venues/sui_deepbook_venue.py`** (72,183 bytes, 1,701 lines):
   - Package & Object IDs:
     - `DEEPBOOK_PACKAGE_ID = "0xdee9"` (line 44)
     - `DEEPBOOK_V3_PACKAGE_ID = "0x2c8d603bc51326b8c13cef9dd07031a408a48dddb541963357661df5d3204809"` (line 45)
     - `DEEPBOOK_V3_LATEST_PKG_ID = "0xbca0cefe720330e7bb4f2283438b68de6a0e656688db4ac90d61e71fe6151fe8"` (line 46)
     - `CETUS_CORE_PACKAGE_ID = "0x1eabed72c53feb3805120a081dc15963c204dc8d091542592abaf7a35689b2fb"` (line 47)
     - `CETUS_CLMM_LATEST_PKG_ID = "0x260693ec785a6e6c9d81d58c7d2ff72f1288ae0fa6a9725abe05a6478b11f084"` (line 48)
     - `CETUS_GLOBAL_CONFIG_ID = "0xdaa46292632c3c4d8f31f23ea0f9b36a28ff3677e9684980e4438403a67a3d8f"` (line 58)
     - `SUI_CLOCK_OBJECT_ID = "0x0000000000000000000000000000000000000000000000000000000000000006"` (line 59)
   - Verified Pools (`SUI_PAIRS_CONFIG`, lines 157–250):
     - `SUI/USDC`: DeepBook `0xe05dafb5133bcffb8d59f4e12465dc0e9faeaa05e3e342a08fe135800e3e4407`, Cetus `0x51e883ba7c0b566a26cbc8a94cd33eb0abd418a77cc1e60ad22fd9b1f29cd2ab` (5 bps), `a2b=True`
     - `DEEP/SUI`: DeepBook `0xb663828d6217467c8a1838a03793da896cbe745b150ebd57d82f814ca579fc22`, Cetus `0xd978d331772a5b90d5a4781e1232d18afd12019d0c35db79e3674beeda8f9126` (5 bps), `a2b=False`
     - `DEEP/USDC`: DeepBook `0xf948981b806057580f91622417534f491da5f61aeaf33d0ed8e69fd5691c95ce`, Cetus `0xa2f4e24dc234cf024bae1bd5b1275ab5bdc7c28dd1ec84dd98c2d012bbd315f0` (5 bps), `a2b=False`
     - `CETUS/SUI`: DeepBook `0xcf8d0d98dd3c2ceaf40845f5260c620fa62b3a15380bc100053aecd6df8e5e7c`, Cetus `0x2e041f3fd93646dcc877f783c1f2b7fa62d30271bdef1f21ef002cebf857bded` (25 bps), `a2b=False`
   - Data structures: `PairConfig` (lines 94–154), `HotPotatoPTBParams` (lines 257–336).
   - PTB Builders:
     - `SuiDeepBookPTBBuilder.build_atomic_arb_ptb` (lines 501–670): High-level 8-step PTB serialization using Balance Manager.
     - `SuiDeepBookPTBBuilder.build_atomic_arb_ptb_bcs` (lines 671–778): Pure Move BCS binary transaction serializer.
     - `SuiDeepBookPTBBuilder.sign_transaction_bcs` (lines 779–796): Blake2b-256 intent + Ed25519 signing.
   - GraphQL & Network Client:
     - `SuiGraphQLClient` (lines 798–1241): Implements `get_wallet_balances`, `get_cetus_pool_spot_price`, `get_market_snapshot`, `simulate_transaction_bcs`, `execute_transaction_bcs`, `_fetch_deepbook_indexer_orderbook`, and `query_live_market_spreads`.
   - Unified Venue:
     - `SuiDeepBookVenue` (lines 1244–1701): Inherits `UnifiedVenue`, implements `connect`, `disconnect`, `build_arbitrage_ptb`, `simulate_dry_run`, `submit_order`, and `get_wallet_balances`.

2. **`venues/sui_ptb_validator.py`** (37,576 bytes, 919 lines):
   - `SuiPTBPreflightValidator`:
     - `validate_preflight_health` (lines 289–426): RPC health, gas runway check (1.5 SUI warning, 0.5 SUI critical), pool object accessibility across all 4 pairs, BalanceManager format validation.
     - `validate_atomic_ptb_generation` (lines 428–600): Validates strict 8-command sequence, object references, and Hot Potato links.
     - `simulate_ptb_dry_run` (lines 602–665): Calculates synthetic spread, executes venue Move VM dry-run, asserts 0 state mutations on abort.
     - `simulate_capital_scaling_lifecycle` (lines 667–750): Simulates full promotion from Tier 1 -> Tier 2 -> Tier 3.
     - `simulate_gas_safety_monitoring` (lines 752–800): Stepwise gas drawdown validation.

3. **`venues/sui_scaling_engine.py`** (22,829 bytes, 536 lines):
   - `ScalingTier` (lines 93–104): `TIER_1` ($1,000 / 1e9), `TIER_2` ($5,000 / 5e9), `TIER_3` ($10,000 / 1e10).
   - `DynamicCapitalScalingEngine` (lines 154–450):
     - Promotion logic: Tier 1 -> Tier 2 at $\ge \$100$ profit & $\ge 10$ trades; Tier 2 -> Tier 3 at $\ge \$750$ profit & $\ge 20$ trades.
     - Circuit breakers: 3 aborts -> 1 tier demote + 60s cooldown; 5 aborts -> `EMERGENCY_LOCKED`.
     - Gas floors: Warning at 1.5 SUI, hard stop at 0.5 SUI (`EMERGENCY_LOCKED`).
     - Depth-aware sizing: `get_current_borrow_amount` with `max_depth_quote * 0.85`.
   - `SuiBalanceTracker` (lines 452–536): Wraps `SuiGraphQLClient` for dual SUI/USDC reconciliation.

4. **`venues/sui_bot_runner.py`** (25,321 bytes, 570 lines):
   - `SuiBotConfig` (lines 80–180): Parses environment variables (`SUI_GRAPHQL_URL`, `OPERATOR_ADDRESS`, `DRY_RUN_MODE`, `SUI_PRIVATE_KEY`, etc.).
   - `SuiBotRunner` (lines 182–570):
     - `start`: Starts HTTP `SuiHealthServer`, runs `run_preflight`, starts `_main_loop`.
     - `scan_once` (lines 335–450): Queries `poll_market_spreads()`, executes dynamic depth sizing, validates PTB structure, runs `simulate_ptb_dry_run()`, triggers `submit_order()` when profitable ($\ge \$0.05$ net profit).

5. **`venues/sui_health_server.py`** (9,682 bytes, 256 lines):
   - Standalone `aiohttp.web` microserver exposing `/health`, `/live`, and `/` on `$PORT` (default 8080) for Railway orchestration.

6. **`h86_sui/` Utilities**:
   - `h86_sui/h86_create_balance_manager.mjs`: Node.js script using `@mysten/sui` to create and share a `BalanceManager` on Sui Mainnet.
   - `h86_sui/h86_deepbook_execute.ts`: TypeScript execution script using `@mysten/sui/transactions`.
   - `h86_sui/h86_deepbook_scan.ts`: TypeScript scan script querying DeepBook indexer and Coinbase oracle.

---

### 1.3 Hot Potato Flash Loan Implementation
The existing Hot Potato flash loan borrowing and repayment logic is implemented in two distinct layers:

1. **High-Level PTB Serialization (`SuiDeepBookPTBBuilder.build_atomic_arb_ptb`, lines 501–649)**:
   - **Borrow (Command 0, lines 514–527)**:
     - Target: `0xdee9::pool::borrow_flashloan_quote` (or `borrow_flashloan_base`)
     - Type args: `[params.base_coin_type, params.quote_coin_type]`
     - Arguments: `[params.pool_id, params.flash_borrow_amount]`
     - Outputs: `["borrowed_quote_coin", "flash_loan_receipt"]`
     - Move semantics: `flash_loan_receipt` is an instance of `FlashLoanQuote` / `FlashLoanBase` struct with **0 Move abilities** (no `drop`, no `copy`, no `store`, no `key`).
   - **Split Repayment (Command 5, lines 616–623)**:
     - Primitive: `SplitCoins`
     - Consumes: withdrawn proceeds `[4, 0]`
     - Amount: `[params.min_repay_amount]`
     - Output: `repay_quote_coin`
   - **Repay & Quench (Command 6, lines 626–640)**:
     - Target: `0xdee9::pool::return_flashloan_quote` (or `return_flashloan_base`)
     - Type args: `[params.base_coin_type, params.quote_coin_type]`
     - Arguments: `[params.pool_id, repay_coin [5, 0], flash_loan_receipt [0, 1]]`
     - Move semantics: Consumes the Hot Potato receipt. If Command 5 failed (due to proceeds < principal), Command 6 is never reached, the unconsumed receipt causes the Move VM to abort immediately, reverting all state mutations to 0.

2. **Pure Move BCS Bytecode Builder (`SuiDeepBookPTBBuilder.build_atomic_arb_ptb_bcs`, lines 671–754)**:
   - Command 0: `DEEPBOOK_V3_LATEST_PKG_ID::pool::borrow_flashloan_quote` -> `(quote_coin, flash_loan_receipt)`
   - Command 1–5: Cetus flash swap (`cetus::pool::flash_swap` and `cetus::pool::repay_flash_swap`)
   - Command 8: DeepBook CLOB direct pool swap `swap_exact_base_for_quote`
   - Command 10: `SplitCoins` from quote proceeds `[8, 1]` for `[borrow_amount]`
   - Command 11: `DEEPBOOK_V3_LATEST_PKG_ID::pool::return_flashloan_quote(db_pool, repay_quote_coin [10, 0], flash_loan_receipt [0, 1])`
   - Command 12: `TransferObjects` profit to sender wallet.

---

### 1.4 Code Path Audit for R1 (Bidirectional Reverse Route DeepBook Ask -> Cetus)
Direct observation of current code paths reveals the following restrictions to forward-only execution:

1. **Scanner (`venues/sui_deepbook_venue.py`, lines 1136–1239)**:
   - Line 1144: Parses `best_bid = float(bids[0][0])` and calculates weighted bid depth `deepbook_px`.
   - Line 1174: Parses `parsed_ask = float(asks[0][0])`, assigning `deepbook_ask_px`.
   - Line 1227–1229:
     ```python
     spread_bps = (((deepbook_px - cetus_px) / cetus_px) * 10000.0 if cetus_px > 0 else 0.0)
     ```
   - **Finding**: The scanner calculates only `spread_bps` based on DeepBook Bid vs Cetus Price. It **does NOT** compute `reverse_spread_bps` (i.e. `((cetus_px - deepbook_ask_px) / deepbook_ask_px) * 10000.0`) or emit a reverse opportunity flag.

2. **Bot Runner Loop (`venues/sui_bot_runner.py`, lines 355–420)**:
   - Line 355: `spread_bps = float(pair_market.get("spread_bps", 0.0))`
   - Line 380–384: Passes `spread_bps` to `simulate_ptb_dry_run()`.
   - Line 410–422: Sets `order_params`:
     ```python
     order_params = {
         "symbol": pair_name,
         "side": "BUY",
         "size": borrow_amount,
         "price": dry_run.get("deepbook_bid_px", deepbook_price),
         "amm_price": dry_run.get("amm_swap_out_px", base_price),
         "is_arb_ptb": True,
         ...
     }
     ```
   - **Finding**: The runner only triggers when `spread_bps > 0` (DeepBook Bid > Cetus). When Cetus Price > DeepBook Ask (negative spread in current terms), the opportunity is completely ignored.

3. **PTB Builder (`venues/sui_deepbook_venue.py`, lines 501–670 & 671–754)**:
   - In `build_atomic_arb_ptb`:
     - When `borrow_asset == "quote"`: Command 1 is Cetus swap (Quote -> Base), Command 3 is DeepBook CLOB market order with `is_bid = False` (Base -> Quote).
     - When `borrow_asset == "base"`: Command 1 is Cetus swap (Base -> Quote), Command 3 is DeepBook CLOB market order with `is_bid = True` (Quote -> Base).
     - Neither path executes **DeepBook Buy first -> Cetus Sell second**.
   - In `build_atomic_arb_ptb_bcs` (lines 671–754):
     - Hardcodes forward route only (`borrow_flashloan_quote` -> Cetus `flash_swap` -> DeepBook `swap_exact_base_for_quote`). There is no reverse BCS assembly.

4. **Dry-Run Simulator (`venues/sui_deepbook_venue.py`, lines 1357–1430)**:
   - Step 4 (lines 1406–1418): Always swaps quote on AMM for base: `base_coins = quote_in / amm_swap_out_px`.
   - Step 5 (lines 1420–1428): Always sells base on DeepBook CLOB at `deepbook_bid_px`.
   - Cannot simulate reverse route where base is bought on DeepBook Ask and sold on AMM.

---

### 1.5 Code Path Audit for R4 (Turbos Finance CLMM Integration)
Direct observation reveals:

1. **Current Package Hooks (`venues/sui_deepbook_venue.py`)**:
   - Line 271: `amm_target: str = "cetus" # "cetus" | "turbos"`
   - Line 539: `"package": "cetus_clmm" if params.amm_target == "cetus" else "turbos_clmm"`
   - Line 543–551: Even when `amm_target == "turbos"`, the arguments passed in `build_atomic_arb_ptb` are Cetus-specific:
     `[CETUS_GLOBAL_CONFIG_ID, params.cetus_pool_id, ..., params.sqrt_price_limit]`
2. **Scanner Hook Points**:
   - `SuiGraphQLClient.query_live_market_spreads` (lines 1051–1076) queries only Cetus pool addresses (`CETUS_POOL_SUI_USDC`, `CETUS_POOL_DEEP_SUI`, etc.).
   - There are **no Turbos pool object IDs** or GraphQL query fields defined for Turbos pools.
3. **Turbos Protocol Specifications**:
   - Official Sui Mainnet Package ID: `0x91bfbc386a41afcfd9b2533058d7e915a1d3829089cc268ff4333d54d6339ca1`
   - Modules: `pool::Pool<T0, T1, Fee>` and `swap_router::swap_a_b` / `swap_b_a`.
   - Dynamic fields contain `sqrt_price` (analogous to Cetus `current_sqrt_price`).

---

## 2. Logic Chain

1. **Test Suite Baseline**:
   - Running the test runner in `trading-engine/.venv` executes 515 tests with 0 failures, including 85 Sui-specific tests in `test_sui_*.py` and 38 adversarial tests in `test_adversarial_challenger_2.py`.
   - Therefore, any modifications for R1 and R4 must strictly preserve the execution signatures, backward-compatibility aliases, and parameter shapes that these 85+ tests assert.

2. **Hot Potato Invariant**:
   - DeepBook V3 flash loan receipts are Move structs without abilities (`FlashLoanQuote` and `FlashLoanBase`).
   - The zero leg risk guarantee depends on Move VM bytecode aborting when `SplitCoins` encounters `INSUFFICIENT_BALANCE` prior to the `return_flashloan_*` call.
   - For bidirectional reverse routes (R1) and Turbos routes (R4), this exact structural sequence:
     `[Borrow Flashloan] -> [Leg 1 Execution] -> [Leg 2 Execution] -> [Split Repayment Principal] -> [Return Flashloan (Hot Potato Quench)] -> [Transfer Remaining Profit]`
     must remain inviolate.

3. **Reverse Route Integration Chain (R1)**:
   - When Cetus Price > DeepBook Ask, base tokens are underpriced on DeepBook and overpriced on Cetus.
   - To capture this negative spread:
     - **Path A (Quote Borrow)**:
       1. Borrow Quote coin $Q$ from DeepBook (`borrow_flashloan_quote`).
       2. Buy Base coin $B$ on DeepBook CLOB at Ask price (`place_market_order(is_bid=True)` or `swap_exact_quote_for_base`).
       3. Swap Base coin $B$ on Cetus CLMM for Quote coin $Q'$ (`a2b = False` or opposite directional swap).
       4. Split $Q'$ to extract exact repayment principal $Q$.
       5. Call `return_flashloan_quote` to quench the Hot Potato.
       6. Retain net quote profit $Q' - Q$.
     - **Path B (Base Borrow)**:
       1. Borrow Base coin $B$ from DeepBook (`borrow_flashloan_base`).
       2. Swap Base coin $B$ on Cetus CLMM for Quote coin $Q$.
       3. Buy Base coin $B'$ on DeepBook CLOB using $Q$ at Ask price.
       4. Split $B'$ to extract exact repayment principal $B$.
       5. Call `return_flashloan_base` to quench the Hot Potato.
       6. Retain net base profit $B' - B$.
   - The scanner must calculate both `forward_spread_bps` and `reverse_spread_bps`.
   - The PTB builder must support a `route_direction` or `route_type` parameter (`"FORWARD"` vs `"REVERSE"`).
   - The simulator and validator must simulate and validate both directions.

4. **Multi-DEX Turbos Integration Chain (R4)**:
   - Turbos CLMM pools publish state via Sui shared objects containing `sqrt_price`.
   - Adding Turbos requires:
     1. Static registry of Turbos pool object IDs for `SUI/USDC`, `DEEP/SUI`, `DEEP/USDC`, `CETUS/SUI`.
     2. Scanner query in `SuiGraphQLClient` to fetch Turbos pool states alongside Cetus.
     3. PTB builder support for Turbos package (`0x91bfbc386a41afcfd9b2533058d7e915a1d3829089cc268ff4333d54d6339ca1`), calling `swap_router` or `pool::swap` with Turbos arguments (`pool`, `clock`, `versioned`).
     4. Scanner routing logic that checks both Cetus and Turbos spreads and executes against whichever DEX offers greater net profit.

---

## 3. Caveats

1. **Sui Mainnet Node Rate Limits**:
   - The public endpoint `https://graphql.mainnet.sui.io/graphql` has request throttling. In production, dedicated private RPCs (e.g. Mysten Labs, Blockdaemon, or Triton) should be configured via `SUI_GRAPHQL_URL`.
2. **DeepBook Indexer Dependencies**:
   - Real-time DeepBook orderbook depth relies on `https://deepbook-indexer.mainnet.mystenlabs.com`. If the indexer experiences downtime, fallback to on-chain GraphQL `dynamicFields` orderbook reading is used.
3. **Turbos Finance On-Chain Shared Object Initial Versions**:
   - Like Cetus and DeepBook pools, Turbos shared pool objects require their exact `initialSharedVersion` for offline pure BCS transaction serialization. When querying via GraphQL RPC or high-level PTB, Sui resolves shared object versions automatically.
4. **No Source Modifications Made**:
   - In accordance with the explorer role, no source code in `trading-engine/` was modified during this investigation.

---

## 4. Conclusion & Actionable Blueprints

### 4.1 Test Suite Baseline
- The existing test suite in `trading-engine/tests/` contains **515 total tests**, with **85 Sui-specific tests** in `test_sui_*.py`.
- Current test execution command:
  ```bash
  /Users/vitorhrds/Documents/Github/hypothesis/trading-engine/.venv/bin/python -m pytest /Users/vitorhrds/Documents/Github/hypothesis/trading-engine/tests/
  ```
- **100% of tests are passing**. Zero regression tolerance must be maintained during implementation of R1 through R5.

---

### 4.2 Exact Blueprint for R1 (Bidirectional Reverse Route)

#### File 1: `venues/sui_deepbook_venue.py`
1. **Extend `HotPotatoPTBParams`** (line 257):
   ```python
   route_direction: str = "FORWARD"  # "FORWARD" (Cetus Buy -> DB Bid Sell) | "REVERSE" (DB Ask Buy -> Cetus Sell)
   ```
2. **Update `build_atomic_arb_ptb`** (line 501):
   - When `route_direction == "REVERSE"`:
     - Command 0: `borrow_flashloan_quote` (borrows $Q$ quote coins)
     - Command 1: Deposit $Q$ into Balance Manager (`balance_manager::deposit`)
     - Command 2: Place market buy order on DeepBook (`place_market_order` with `is_bid = True`, lifting Ask)
     - Command 3: Withdraw acquired base coin $B$ from Balance Manager (`balance_manager::withdraw_all<Base>`)
     - Command 4: Swap base coin $B$ on Cetus/Turbos (`a2b` set to opposite direction: Base -> Quote)
     - Command 5: `SplitCoins` exact repayment principal $Q$ from AMM swap proceeds $Q'$
     - Command 6: `return_flashloan_quote` with repayment coin and Hot Potato receipt
     - Command 7: `TransferObjects` remaining quote profit $Q' - Q$ to sender wallet.
3. **Update `simulate_dry_run`** (line 1346):
   - Add branch for `route_direction == "REVERSE"`:
     - Step 1: Base coins acquired on DeepBook Ask: `base_coins = (borrow_amount / quote_scale) / deepbook_ask_px`. Apply DeepBook taker fee if non-zero.
     - Step 2: Swap base coins on AMM: `gross_proceeds = base_coins * amm_swap_out_px`. Apply AMM swap fee.
     - Step 3: Compare `net_proceeds_native` to `borrow_amount`. If proceeds < borrow, abort with `zero_leg_risk_preserved = True`.
4. **Update `query_live_market_spreads`** (line 1049):
   - Calculate both spreads:
     ```python
     forward_spread_bps = ((deepbook_px - cetus_px) / cetus_px) * 10000.0
     reverse_spread_bps = ((cetus_px - deepbook_ask_px) / deepbook_ask_px) * 10000.0 if deepbook_ask_px > 0 else 0.0
     ```
   - Return both `forward_spread_bps`, `reverse_spread_bps`, `best_route` (`"FORWARD"` or `"REVERSE"`), and `optimal_spread_bps`.

#### File 2: `venues/sui_ptb_validator.py`
1. Update `validate_atomic_ptb_generation` to accept `route_direction="FORWARD"` and `"REVERSE"`.
2. Update `simulate_ptb_dry_run` to accept `route_direction` and test negative spread reverse scenarios.

#### File 3: `venues/sui_bot_runner.py`
1. In `scan_once()`:
   - Check both `forward_spread_bps` and `reverse_spread_bps`.
   - If `reverse_spread_bps` is profitable and exceeds fee hurdles, set `route_direction = "REVERSE"`, simulate, and execute.

---

### 4.3 Exact Blueprint for R4 (Turbos Finance CLMM Integration)

#### File 1: `venues/sui_deepbook_venue.py`
1. **Define Turbos Constants**:
   ```python
   TURBOS_PACKAGE_ID = "0x91bfbc386a41afcfd9b2533058d7e915a1d3829089cc268ff4333d54d6339ca1"
   TURBOS_VERSIONED_ID = "0xf1bfaf39f07dc30881915fcf20684074249bc6173c83379878229e64e9a03e6b" # or verified versioned object
   # Active Turbos Mainnet Pools
   TURBOS_POOL_SUI_USDC = "0x5eb2dfcdd013849123d50a57277709d4788a93257d074f66fb315488f0f35068"
   TURBOS_POOL_DEEP_SUI = "0x..." # verified pool
   ```
2. **Extend `PairConfig` & Registry**:
   - Add `turbos_pool_id: Optional[str] = None`
   - Add `turbos_fee_bps: float = 5.0`
   - Add `turbos_a2b: bool = True`
3. **Update `SuiGraphQLClient`**:
   - Add Turbos pool objects to GraphQL batch query in `query_live_market_spreads`.
   - Parse Turbos CLMM spot price from `sqrt_price`.
   - Compare DeepBook orderbook against both Cetus and Turbos, selecting the maximum spread.
4. **Update `SuiDeepBookPTBBuilder.build_atomic_arb_ptb`**:
   - When `amm_target == "turbos"`:
     - Target Move function: `${TURBOS_PACKAGE_ID}::swap_router::swap_a_b` (or `swap_b_a` depending on direction).
     - Pass Turbos pool shared object, borrowed coin, `sqrt_price_limit`, recipient, deadline, clock (`0x6`), versioned object.

---

### 4.4 Exact Blueprint for Vault Balance Protection (R3) & Sizing (R2)
1. **Vault Balance Check**:
   - In `SuiGraphQLClient`: Add query `get_deepbook_vault_balances(pool_id: str) -> Dict[str, int]`.
   - Before executing in `sui_bot_runner.py`: Verify `vault_quote >= borrow_amount` (for quote borrow) or `vault_base >= borrow_amount` (for base borrow).
   - If vault balance is insufficient, abort scan cycle to prevent Move VM abort `EInsufficientVaultBalance` (abort code 2).
2. **Optimal Sizing ($Q^*$)**:
   - Replace static sizing with analytical formula:
     $$Q^* = \frac{\text{Spread}_{\text{net}}}{2 \times \gamma_{\text{AMM}}}$$
     where $\gamma_{\text{AMM}}$ is the pool price impact slope estimated from pool liquidity $L$.

---

## 5. Verification Method

To independently verify all findings and test suite integrity:

1. **Verify Global Test Suite (515 tests)**:
   ```bash
   cd /Users/vitorhrds/Documents/Github/hypothesis
   /Users/vitorhrds/Documents/Github/hypothesis/trading-engine/.venv/bin/python -m pytest /Users/vitorhrds/Documents/Github/hypothesis/trading-engine/tests/
   ```
   *Expected output*: `515 passed in ~21s`.

2. **Verify Sui-Specific Test Suite (85 tests)**:
   ```bash
   cd /Users/vitorhrds/Documents/Github/hypothesis
   /Users/vitorhrds/Documents/Github/hypothesis/trading-engine/.venv/bin/python -m pytest /Users/vitorhrds/Documents/Github/hypothesis/trading-engine/tests/test_sui_*.py -v
   ```
   *Expected output*: `85 passed in ~6s`.

3. **Verify Hot Potato Reversion Adversarial Tests (38 tests)**:
   ```bash
   cd /Users/vitorhrds/Documents/Github/hypothesis
   /Users/vitorhrds/Documents/Github/hypothesis/trading-engine/.venv/bin/python -m pytest /Users/vitorhrds/Documents/Github/hypothesis/trading-engine/tests/test_adversarial_challenger_2.py -v
   ```
   *Expected output*: `38 passed in ~1.5s`.

4. **Verify Inspection Locations**:
   - `trading-engine/venues/sui_deepbook_venue.py`: lines 257–336 (`HotPotatoPTBParams`), lines 501–670 (`build_atomic_arb_ptb`), lines 671–754 (`build_atomic_arb_ptb_bcs`), lines 1049–1241 (`query_live_market_spreads`), lines 1357–1473 (`simulate_dry_run`).
   - `trading-engine/venues/sui_ptb_validator.py`: lines 428–600 (`validate_atomic_ptb_generation`), lines 602–665 (`simulate_ptb_dry_run`).
   - `trading-engine/venues/sui_scaling_engine.py`: lines 93–104 (`ScalingTier`), lines 154–450 (`DynamicCapitalScalingEngine`).
   - `trading-engine/venues/sui_bot_runner.py`: lines 335–450 (`scan_once`).
