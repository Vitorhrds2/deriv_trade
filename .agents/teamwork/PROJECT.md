# Project: Sui DeepBook V3, Cetus & Turbos Multi-DEX Atomic Arbitrage Engine

## Architecture Overview
This project enhances the enterprise-grade high-frequency atomic flash loan arbitrage bot operating across Sui DeepBook V3 (Central Limit Order Book), Cetus Protocol (Concentrated Liquidity AMM), and Turbos Finance (CLMM) in production.

### Core Architectural Pillars
1. **Bidirectional Flash Loan Arbitrage (R1)**:
   - Forward Route: Borrow Quote -> AMM Swap Quote for Base -> DeepBook CLOB Market Sell Base -> Split Repayment -> Quench Hot Potato -> Extract Profit.
   - Reverse Route: Borrow Quote -> DeepBook CLOB Market Buy Base at Ask -> AMM Swap Base for Quote -> Split Repayment -> Quench Hot Potato -> Extract Profit.
   - Enforces Move VM Zero Leg Risk bytecode guarantee: If swap proceeds < borrow principal, `SplitCoins` aborts, leaving Hot Potato unquenched and atomically reverting all state mutations.

2. **Analytical Q* Optimal Sizing & Dynamic Tranches (R2)**:
   - Replaces static orderbook-only sizing with analytical closed-form optimal borrow sizing:
     $$Q^* = \frac{1}{2} (\Delta P - \text{fees}) \cdot L \sqrt{P_0}$$
   - Dynamic tranche bounds adapted to pool liquidity (e.g., $100 - $150 USDC for thin pools like DEEP/USDC with $L \approx 2.40 \times 10^{11}$, scaling up to $1,000+ USDC for deep pools like DEEP/SUI with $L \approx 9.84 \times 10^{14}$).
   - Precludes preflight Move VM slippage and repayment aborts while maximizing net realized profit.

3. **Route Prioritization & DeepBook Vault Balance Protection (R3)**:
   - Prioritizes DEEP/SUI (massive liquidity $L \approx 9.84 \times 10^{14}$ and whitelisted 0 bps DeepBook taker fee) over DEEP/USDC.
   - Programmatic pre-flight query of `0xdee9::pool::vault_balances` to verify available vault cash balance, ensuring $Q \le 0.90 \times \text{vault\_balance}$ and eliminating Move abort code 2 (`EInsufficientVaultBalance`).

4. **Multi-DEX CLMM Support with Turbos Finance (R4)**:
   - Full integration with Turbos Finance CLMM: Package `0xa5a0c25c79e428eba04fb98b3fb2a34db45ab26d4c8faf0d7e39d66a63891e64`, Versioned `0xf1cf0e81048df168ebeb1b8030fad24b3e0b53ae827c25053fff0779c1445b6f`, PoolConfig `0xc294552b2765353bcafa7c359cd28fd6bc237662e5db8f09877558d81669170c`, Clock `0x6`.
   - Continuous real-time quote polling in scanner (`params.amm_target = "turbos"`).
   - Atomic PTB construction and execution via Turbos router (`swap_a_b_with_return_` / `swap_b_a_with_return_`).

5. **Hot Potato Integrity & Live Bot Runner (R5)**:
   - Strict 100% pass rate preservation across all 515+ existing tests in `trading-engine/tests/`.
   - Dry-run preflight simulation and gas safety runway (5.419 SUI, 1.5 SUI warning, 0.5 SUI stop).
   - Operational bot runner ready for live execution.

---

## Feature Inventory
| # | Feature | Description | Milestone | Source |
|---|---------|-------------|-----------|--------|
| 1 | Bidirectional Reverse Route Scanner (R1) | Computes `reverse_spread_bps = ((cetus_px - deepbook_ask_px) / deepbook_ask_px) * 10000.0` alongside forward spread | M1 | ORIGINAL_REQUEST §R1 |
| 2 | Reverse Route Atomic PTB Builder (R1) | Constructs 8-command PTB: Borrow Quote -> DeepBook Market Buy Ask -> Cetus Swap Base to Quote -> Split Repayment -> Quench Hot Potato | M1 | ORIGINAL_REQUEST §R1 |
| 3 | Reverse Route Dry-Run Simulator (R1) | Extends `simulate_dry_run` and preflight validator to simulate reverse route execution and verify clean aborts | M1 | ORIGINAL_REQUEST §R1 |
| 4 | Analytical Q* Optimal Sizing Engine (R2) | Implements $Q^* = \frac{1}{2} (\Delta P - \text{fees}) \cdot L \sqrt{P_0}$ dynamically adapted to Cetus pool liquidity slope | M2 | ORIGINAL_REQUEST §R2 |
| 5 | Dynamic Tranche Bounding & Slippage Protection (R2) | Enforces pool-specific tranche bounds ($100 - $150 USDC on DEEP/USDC) passing Move VM without slippage aborts | M2 | ORIGINAL_REQUEST §R2 |
| 6 | Pair Route Prioritization Engine (R3) | Evaluates and prioritizes DEEP/SUI (deepest liquidity, 0 bps fee) over DEEP/USDC in scanner opportunity selection | M2 | ORIGINAL_REQUEST §R3 |
| 7 | DeepBook Vault Balance Protection (R3) | Queries `0xdee9::pool::vault_balances` pre-flight via GraphQL to enforce $Q \le 0.90 \times \text{vault\_balance}$, preventing abort code 2 | M2 | ORIGINAL_REQUEST §R3 |
| 8 | Turbos Finance CLMM Registry & Objects (R4) | Verified package IDs, shared objects (`Versioned`, `PoolConfig`, `Clock`), and pool IDs for SUI/USDC, DEEP/SUI, DEEP/USDC, CETUS/SUI | M3 | ORIGINAL_REQUEST §R4 |
| 9 | Turbos Finance Real-Time Quote Scanner (R4) | Extends `SuiGraphQLClient` to query Turbos pool `sqrt_price` dynamically for `amm_target = "turbos"` | M3 | ORIGINAL_REQUEST §R4 |
| 10 | Turbos Finance Atomic PTB Builder & Executor (R4) | Implements atomic PTB execution for DeepBook <-> Turbos in both forward and reverse directions with Hot Potato quenching | M3 | ORIGINAL_REQUEST §R4 |
| 11 | Comprehensive Test Suite & Zero-Regression Verification (R5) | 100% pass rate maintained on all 515+ tests, plus dedicated unit & integration tests for R1-R4 | M4 | ORIGINAL_REQUEST §R5 |
| 12 | Preflight Simulation & Gas Runway Validation (R5) | Validates GraphQL `simulateTransaction` and operator gas runway (5.419 SUI, 1.5 warning, 0.5 hard stop) | M4 | ORIGINAL_REQUEST §R5 |
| 13 | Bot Runner Live Deployment Configuration (R5) | Configures live execution mode (`DRY_RUN_MODE=false`) with health server and structured execution telemetry | M4 | ORIGINAL_REQUEST §R5 |

---

## Milestones
| # | Name | Scope | Dependencies | Status |
|---|------|-------|-------------|--------|
| M1 | Bidirectional Reverse Route (DeepBook <-> Cetus) | Features 1, 2, 3 (R1): Reverse spread scanning, reverse atomic PTB construction, reverse dry-run simulation | Survey | DONE (549/549 tests passing) |
| M2 | Q* Optimal Sizing & DeepBook Vault Protection | Features 4, 5, 6, 7 (R2, R3): Q* analytical sizing, dynamic tranches, DEEP/SUI prioritization, vault balance pre-flight check | M1 | DONE (568/568 tests passing) |
| M3 | Multi-DEX Integration with Turbos Finance CLMM | Features 8, 9, 10 (R4): Turbos pool registry, real-time quote polling in scanner, Turbos PTB builder & executor | M1, M2 | DONE (583/583 tests passing) |
| M4 | E2E Verification, Hot Potato Integrity & Live Deploy | Features 11, 12, 13 (R5): Full test suite execution (515+ tests), preflight validation, challenger stress testing, forensic audit, live bot runner configuration | M1, M2, M3 | DONE (677/677 tests passing, Gate PASS) |

---

## Interface Contracts

### 1. Reverse Route Contracts (`venues/sui_deepbook_venue.py`)
- `HotPotatoPTBParams`:
  ```python
  route_direction: str = "FORWARD"  # "FORWARD" (Cetus Buy -> DB Sell) | "REVERSE" (DB Buy -> Cetus Sell)
  ```
- `SuiDeepBookPTBBuilder.build_atomic_arb_ptb`:
  - When `route_direction == "REVERSE"`:
    - Command 0: `0xdee9::pool::borrow_flashloan_quote` -> `(quote_coin, receipt)`
    - Command 1: `balance_manager::deposit` quote_coin
    - Command 2: `pool::place_market_order(is_bid=True)` or `swap_exact_quote_for_base` -> lifts Ask
    - Command 3: `balance_manager::withdraw_all<Base>` -> base_coin
    - Command 4: AMM swap Base for Quote (`cetus_clmm` or `turbos_clmm`)
    - Command 5: `SplitCoins` exact repayment quote principal from swap proceeds
    - Command 6: `0xdee9::pool::return_flashloan_quote(pool, repay_coin, receipt)`
    - Command 7: `TransferObjects` profit quote coin to sender.
- `SuiGraphQLClient.query_live_market_spreads`:
  - Emits: `forward_spread_bps`, `reverse_spread_bps`, `best_route` (`"FORWARD"` | `"REVERSE"`), `optimal_spread_bps`.

### 2. Analytical Q* Sizing & Vault Protection (`venues/sui_scaling_engine.py`)
- `calculate_optimal_borrow_q_star(spread_bps: float, liquidity: float, sqrt_price: int, fee_bps: float, min_tranche: int, max_tranche: int, vault_balance: int) -> int`
- `check_deepbook_vault_balance(pool_id: str, client: SuiGraphQLClient) -> Dict[str, int]`
  - Returns `{"base_balance": int, "quote_balance": int, "deep_balance": int}`
  - Enforces `borrow_amount <= 0.90 * vault_balance["quote_balance"]`.

### 3. Turbos Finance CLMM Contracts (`venues/sui_deepbook_venue.py`)
- Turbos Constants:
  - `TURBOS_PACKAGE_ID = "0xa5a0c25c79e428eba04fb98b3fb2a34db45ab26d4c8faf0d7e39d66a63891e64"`
  - `TURBOS_VERSIONED_ID = "0xf1cf0e81048df168ebeb1b8030fad24b3e0b53ae827c25053fff0779c1445b6f"`
  - `TURBOS_POOL_CONFIG_ID = "0xc294552b2765353bcafa7c359cd28fd6bc237662e5db8f09877558d81669170c"`
- Pool Mapping:
  - `SUI/USDC`: `0x0df4f02d0e210169cb6d5aabd03c3058328c06f2c4dbb0804faa041159c78443`
  - `DEEP/SUI`: `0xbca476e3c744648c65b1fae5551b86be8ad7f482ca9c2268dad1d6b4fd0e2635`
  - `DEEP/USDC`: `0x198af6ff81028c6577e94465d534c4e2cfcbbab06a95724ece7011c55a9d1f5a`
  - `CETUS/SUI`: `0xdf9d069bdfd51515aa0316698225a26444cbdf3cccd130a226b3ac81cfe2f606`

---

## Code Layout
- `trading-engine/venues/sui_deepbook_venue.py` — PTB Builder, GraphQL Client, Venue connector, Turbos & Cetus protocols
- `trading-engine/venues/sui_scaling_engine.py` — Q* Optimal Sizing, Vault check, capital scaling, route prioritization
- `trading-engine/venues/sui_bot_runner.py` — Bot runner, main scan loop, route execution
- `trading-engine/venues/sui_ptb_validator.py` — Preflight validator, PTB generation and dry-run validation
- `trading-engine/tests/` — Test suites (all existing 515 tests + new tests)
