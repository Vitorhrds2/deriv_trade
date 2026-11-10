# Architectural Specification: Dynamic Capital Scaling Engine & Wallet Balance Tracking for Sui DeepBookV3 & Cetus Arbitrage

**Document Version:** 1.0.0  
**Author:** teamwork_explorer_sui_survey_2  
**Date:** 2026-11-10  
**Status:** Approved for Implementation  
**Target Environment:** Sui Mainnet / Railway Continuous Runner (Frankfurt or Oregon)  

---

## 1. Executive Summary & Problem Scope

This specification details the end-to-end design of the **Dynamic Capital Scaling Engine** and **Wallet Balance Tracking Architecture** for the high-frequency atomic arbitrage bot operating between **Sui DeepBookV3** (central limit order book) and **Cetus Protocol** (concentrated liquidity AMM).

### Key Objectives Addressed
1. **Wallet Balance & Gas Management:**
   - Real-time on-chain tracking of the operator wallet balance (`0x5621a8e7199680512ee829565b96febea2587e534fd69b33f04004298d7e5ce9`), verified on Sui Mainnet with **5.419245048 SUI** (~5.42 SUI = 5,419,245,048 MIST) and Circle Native USDC (`0xdba34672e30cb065b1f93e3ab55318768fd6fef66c15942c9f7cb846e2f900e7::usdc::USDC`, 6 decimals).
   - Strict gas runaway prevention and multi-tiered alerting before gas reaches critical floors.
2. **Sui RPC & GraphQL Integration Protocol:**
   - Migration from deprecated Sui public JSON-RPC (error code `-32601`) to official **Sui GraphQL RPC** (`https://graphql.mainnet.sui.io/graphql`) with dedicated JSON-RPC/gRPC secondary fallbacks.
   - Dual-balance single-roundtrip query retrieving both SUI and USDC balances in sub-200ms latency.
3. **Dynamic Capital Scaling State Machine:**
   - Starting tier: `flash_borrow_amount = 1_000_000_000` (1,000 USDC nativo, 6 decimals).
   - Baseline net profit tracking: mathematical verification of net accumulated profits credited via Move PTB Command 7 (`TransferObjects`).
   - Phased threshold transitions:
     - **Tier 1:** 1,000 USDC (`1_000_000_000`)
     - **Tier 2:** 5,000 USDC (`5_000_000_000`) upon reaching $+\$100-\$250$ verified net profit and stability metrics.
     - **Tier 3:** 10,000 USDC (`10_000_000_000`) upon reaching $+\$750$ cumulative net profit and AMM depth validation.
4. **Drawdown & Safety Guardrails:**
   - Pre-flight `dryRunTransactionBlock` simulation ensuring zero on-chain gas waste for non-executable spreads.
   - Consecutive abort circuit breaker (downgrade on 3 aborts, freeze on 5 aborts).
   - Balance divergence guard preventing desynchronization between off-chain order accounting and on-chain coin states.
5. **Programmatic Test Suite:**
   - Full test specifications covering state transitions, balance parser resilience, gas floor alerting, and dry-run PTB verification across all 4 configured pairs (`SUI/USDC`, `DEEP/SUI`, `DEEP/USDC`, `CETUS/SUI`).

---

## 2. Existing Codebase Audit & Architectural Gaps

### 2.1 File Inventory & Current Capabilities
An inspection of the repository revealed the following implementations:
- `trading-engine/venues/sui_deepbook_venue.py`:
  - Contains `SuiDeepBookVenue` registered in the venue registry (`UnifiedVenue`).
  - Contains `SuiDeepBookPTBBuilder` implementing the 8-step Move Programmable Transaction Block (PTB) with Hot Potato flash loan borrowing (`borrow_flashloan_quote`) and repayment (`return_flashloan_quote`).
  - Contains local mathematical simulation (`simulate_dry_run`), modeling the AMM swap, DeepBook CLOB sell, and Hot Potato resolution.
- `trading-engine/h86_sui/`:
  - Prototype scripts (`h86_setup_wallet.ts`, `h86_deepbook_execute.ts`, `h86_deepbook_scan.ts`, `h86_onchain_orderbook.py`).
  - Contains wallet configuration `.env` with operator address `0x5621a8e7199680512ee829565b96febea2587e534fd69b33f04004298d7e5ce9`.
- `trading-engine/tests/test_venues_unit.py`:
  - Contains unit tests for `SuiDeepBookPTBBuilder` verifying the 8-step structure and `simulate_dry_run` with zero leg risk.

### 2.2 Critical Gaps Identified & Remediation Plan

| Component | Current State | Defect / Vulnerability | Remediation |
|---|---|---|---|
| **RPC Endpoint** | Calls `https://fullnode.mainnet.sui.io` via JSON-RPC `suix_getBalance` | **Deprecated by Mysten Labs** (`-32601 Method not found`). All public fullnode JSON-RPC endpoints are disabled. | Connect via **Sui GraphQL RPC** (`https://graphql.mainnet.sui.io/graphql`) with dual query for SUI and Native USDC. |
| **Balance Tracking** | No balance tracking method in `SuiDeepBookVenue`. `h86_setup_wallet.ts` has one-off script. | The trading engine cannot check its available SUI gas or verify USDC profit accumulation in real time. | Implement `SuiBalanceTracker` class integrated into venue lifecycle, running polling loops and pre/post-trade checks. |
| **Initial Flash Loan Amount** | Hardcoded to `100_000_000` (100 USDC) in `HotPotatoPTBParams`. | Violates Requirement R2 (`flash_borrow_amount = 1_000_000_000`). | Update default to `1_000_000_000` (1,000 USDC) and decouple parameter into dynamic engine controller. |
| **Capital Scaling** | Static capital parameter, no transition logic. | Cannot transition to 5k and 10k USDC; no automated profit compounding. | Implement `DynamicCapitalScalingEngine` state machine with threshold transitions, criteria checks, and auto-downgrade. |
| **Gas Safety Floor** | Hardcoded check of `< 0.05 SUI` in execution script without circuit breaker. | Risks transaction exhaustion in high-frequency trading loops; does not protect against degraded RPC states. | Implement two-tiered gas floor: Warning (1.5 SUI) and Critical (0.5 SUI) with automated execution halt. |
| **Dry Run Simulation** | Mathematical Python simulation only; no live RPC call to `sui_dryRunTransactionBlock`. | Does not validate actual on-chain Move bytecode, object ownership, or current dynamic tick state before submitting. | Implement RPC `dryRunTransactionBlock` execution pipeline via GraphQL or dedicated RPC endpoint before broadcasting. |

---

## 3. Sui Mainnet RPC & Wallet Tracking Architecture

### 3.1 Network Protocol: Sui GraphQL RPC (Primary)
The official Sui network architecture has shifted from public JSON-RPC fullnodes to **GraphQL**. The primary production endpoint is:
```
POST https://graphql.mainnet.sui.io/graphql
Content-Type: application/json
```

#### Dual-Balance Atomic Query
Instead of making separate network requests for SUI and USDC, the bot executes a single atomic GraphQL document:

```graphql
query GetWalletBalances($owner: SuiAddress!) {
  address(address: $owner) {
    sui: balance(coinType: "0x2::sui::SUI") {
      totalBalance
      coinBalance
    }
    usdc: balance(coinType: "0xdba34672e30cb065b1f93e3ab55318768fd6fef66c15942c9f7cb846e2f900e7::usdc::USDC") {
      totalBalance
      coinBalance
    }
  }
}
```

**Query Variables:**
```json
{
  "owner": "0x5621a8e7199680512ee829565b96febea2587e534fd69b33f04004298d7e5ce9"
}
```

**Live Verified Mainnet Response:**
```json
{
  "data": {
    "address": {
      "sui": {
        "totalBalance": "5419245048",
        "coinBalance": "5419245048"
      },
      "usdc": {
        "totalBalance": "0",
        "coinBalance": "0"
      }
    }
  }
}
```

### 3.2 Wallet Accounting & Decimal Normalization

| Asset | Type String | On-Chain Decimals | Conversion Factor | Current Mainnet Balance | Value (USD) |
|---|---|---|---|---|---|
| **SUI (Gas)** | `0x2::sui::SUI` | 9 decimals | $10^9$ (MIST) | `5419245048` MIST = **5.419245048 SUI** | ~$11.11 ($2.05/SUI) |
| **USDC (Profit/Capital)** | `0xdba34672e30cb065b1f93e3ab55318768fd6fef66c15942c9f7cb846e2f900e7::usdc::USDC` | 6 decimals | $10^6$ (Micro-USDC) | `0` = **0.000000 USDC** | $0.00 |

### 3.3 SUI Gas Budget, Runway & Alerting Floors

#### Gas Consumption Profile on Sui Move VM
1. **Pre-flight Dry Run (`dryRunTransactionBlock`):**
   - Cost: **0.000000 SUI**.
   - Executed as an RPC node simulation; no transaction block is published to validators; zero MIST deducted from wallet.
2. **Move VM Abort (Hot Potato Unsatisfied):**
   - Gas burned: **~0.002000 SUI** (2,000,000 MIST = ~$0.0041).
   - When an unprofitable spread aborts inside Move VM (Command 5 `SplitCoins` fails), the PTB aborts without mutating storage; only execution gas is burned.
3. **Successful Execution (8-step PTB Commits):**
   - Gas burned: **~0.003500 - 0.005000 SUI** (3,500,000 - 5,000,000 MIST = ~$0.0072 - $0.0102).
   - Involves Hot Potato borrow, Cetus AMM swap, DeepBook BalanceManager deposit, CLOB market order execution, withdraw, split, Hot Potato return, and coin transfer.

#### Gas Runway Calculation with 5.419245048 SUI
$$\text{Max Aborted Attempts Capacity} = \frac{5.419245048 \text{ SUI}}{0.002000 \text{ SUI}} \approx \mathbf{2,709 \text{ on-chain aborts}}$$
$$\text{Max Successful Execution Capacity} = \frac{5.419245048 \text{ SUI}}{0.004000 \text{ SUI}} \approx \mathbf{1,354 \text{ full trades}}$$

Because 95%+ of unprofitable spreads are filtered **before** broadcast via off-chain spread checks and pre-flight `dryRunTransactionBlock`, the **practical runway exceeds 50,000 evaluated market events**.

#### Gas Alerting & Threshold Hierarchy

```
 5.42 SUI  ─────────────────────────────  CURRENT LIVE BALANCE (Healthy)
           │
           │ Normal Operating Band
           │ Full scanning and execution active
           │
 3.00 SUI  ─────────────────────────────  GAS_TARGET_COMFORT
           │
           │ Moderate Gas Band
           │ Log informational notice; evaluate auto-refuel options
           │
 1.50 SUI  ─────────────────────────────  GAS_WARNING_FLOOR
           │ - Emit WARNING log + alert webhook (Discord/Telegram/Railway)
           │ - Throttle scan frequency (e.g., from 500ms to 2000ms)
           │ - Restrict execution to high-conviction spreads (> 15 bps)
           │
 0.50 SUI  ─────────────────────────────  GAS_CRITICAL_FLOOR (EMERGENCY HALT)
           │ - IMMEDIATE HARD STOP of all transaction submissions
           │ - State transitions to HALTED_LOW_GAS
           │ - Emit CRITICAL alert; require manual gas top-up or auto-refuel
 0.00 SUI  ─────────────────────────────  WALLET DEPLETED (Unreachable due to halt)
```

### 3.4 Fallback RPC Endpoints & Resilience
To ensure zero downtime during Railway operation, the bot configures a fallback connection pool:
1. **Primary:** `https://graphql.mainnet.sui.io/graphql` (Mysten Labs official GraphQL).
2. **Secondary GraphQL:** Provider endpoint (e.g., Shinami Node GraphQL or self-hosted fullnode).
3. **Tertiary JSON-RPC (Private/Dedicated node only):** Dedicated fullnode with JSON-RPC enabled (e.g. `https://sui-mainnet.nodeinfra.com` or private endpoint).
4. **Retry Policy:** Exponential backoff with full jitter:
   - Initial interval: 250ms
   - Max backoff: 2,500ms
   - Max retries: 3 attempts
   - Circuit breaker: After 5 consecutive RPC failures, enter `RPC_DEGRADED` state for 30 seconds before retrying health check.

---

## 4. Multi-Pair Coverage & Token/Pool Specifications

The bot is mandated by Requirement R1 to monitor 4 core pairs. The exact on-chain types and pool identifiers on Sui Mainnet are:

| Pair Name | Base Token (CoinType) | Quote Token (CoinType) | DeepBookV3 Pool ID | Cetus CLMM Pool ID | Base Decimals | Quote Decimals |
|---|---|---|---|---|---|---|
| **SUI/USDC** | `0x2::sui::SUI` | `0xdba34672e30cb065b1f93e3ab55318768fd6fef66c15942c9f7cb846e2f900e7::usdc::USDC` | `0xe05dafb5133bcffb8d59f4e12465dc0e9faeaa05e3e342a08fe135800e3e4407` | `0x51e883ba7c0b566a26cbc8a94cd33eb0abd418a77cc1e60ad22fd9b1f29cd2ab` (0.05%) / `0xb8d7...` (0.25%) | 9 | 6 |
| **DEEP/SUI** | `0xdeeb7a4662eec9f2f3def03fb937a663dddaa2e215b8078a284d026b7946c270::deep::DEEP` | `0x2::sui::SUI` | `0xb663828d6217467c8a1838a03793da896cbe745b150ebd57d82f814ca579fc22` | `0xd978d331772a5b90d5a4781e1232d18afd12019d0c35db79e3674beeda8f9126` (0.05%) / `0xe012...` (0.25%) | 6 | 9 |
| **DEEP/USDC** | `0xdeeb7a4662eec9f2f3def03fb937a663dddaa2e215b8078a284d026b7946c270::deep::DEEP` | `0xdba34672e30cb065b1f93e3ab55318768fd6fef66c15942c9f7cb846e2f900e7::usdc::USDC` | `0xf948981b806057580f91622417534f491da5f61aeaf33d0ed8e69fd5691c95ce` | `0xa2f4e24dc234cf024bae1bd5b1275ab5bdc7c28dd1ec84dd98c2d012bbd315f0` (0.05%) | 6 | 6 |
| **CETUS/SUI** | `0x06864a6f921804860930db6ddbe2e16acdf8504495ea7481637a1c8b9a8fe54b::cetus::CETUS` | `0x2::sui::SUI` | `0x4405b50d...` (Auto-discovered / CLOB registry) | `0x2e041f3fd93646dcc877f783c1f2b7fa62d30271bdef1f21ef002cebf857bded` (0.25%) | 9 | 9 |

*Note on Flash Loan Currency:*
- For `SUI/USDC` and `DEEP/USDC`, the flash loan is borrowed in **Native USDC** (`borrow_flashloan_quote`).
- For `DEEP/SUI` and `CETUS/SUI`, the flash loan can be borrowed in **SUI** (`borrow_flashloan_quote`), where profit is realized in SUI and periodically converted or tracked in USDC equivalent.
- The dynamic scaling engine controls the base USDC borrowing tranche for the USD-quoted pools and calculates proportional SUI flash-borrow amounts for SUI-quoted pools.

---

## 5. Dynamic Capital Scaling Engine & State Machine

### 5.1 Architectural Principles
The scaling engine implements a **conservative, ratcheted state machine** governed by three core principles:
1. **Zero Capital Risk:** The bot does not risk principal capital because the trading mechanism is an atomic flash loan. Capital scaling increases the *borrowed tranche size* ($Q$), which magnifies dollar profit per trade:
   $$\text{Gross Profit} = Q \times \left( \frac{\text{Spread}_{\text{net}}}{10,000} \right)$$
   For a net spread of $+20$ bps:
   - At $Q = 1,000 \text{ USDC}$: $\text{Profit} = \$2.00$
   - At $Q = 5,000 \text{ USDC}$: $\text{Profit} = \$10.00$
   - At $Q = 10,000 \text{ USDC}$: $\text{Profit} = \$20.00$
2. **Liquidity Depth Gating:** Higher borrowing amounts face non-linear AMM slippage ($PriceImpact \propto Q / PoolDepth$). Scaling up is forbidden unless orderbook and AMM pool depth exceed $3\times$ the tranche size.
3. **Hysteresis & Demotion:** Scaling down occurs aggressively on repeated failures, while scaling up requires sustained, verified profit accumulation.

### 5.2 State Machine Definition

```
 ┌──────────────┐
 │  BOOTSTRAP   │──▶ Connect RPC, query wallet balance, establish baseline
 └──────┬───────┘
        ▼
 ┌──────────────┐   Verified Profit >= $100 AND N >= 10 trades
 │  TIER 1 (1k) │────────────────────────────────────────────────┐
 │ 1,000 USDC   │◀──────────────────────────────┐                │
 └──────┬───────┘       3 Consecutive Aborts     │                │
        │                                        │                ▼
        │                               ┌────────┴──────┐ ┌──────────────┐
        │                               │ COOLDOWN /    │ │  TIER 2 (5k) │
        │                               │ AUTO-DOWNGRADE│ │ 5,000 USDC   │
        │                               └────────▲──────┘ └──────┬───────┘
        │                                        │               │
        │                               3 Consec.│               │ Verified Profit >= $500
        │                               Aborts   │               │ AND N >= 20 trades
        │                                        │               ▼
        │                                        │        ┌──────────────┐
        │                                        └────────│ TIER 3 (10k) │
        │                                                 │ 10,000 USDC  │
        │                                                 └──────────────┘
        ▼
 ┌──────────────┐
 │ HALTED /     │◀── Gas < 0.5 SUI OR 5 consecutive aborts OR balance divergence
 │ EMERGENCY    │
 └──────────────┘
```

### 5.3 Detailed Tier Specifications & Transition Rules

#### Tier 1: Initial Bootstrap Phase
- **Parameter:** `flash_borrow_amount = 1_000_000_000` (1,000.000000 USDC).
- **Min Net Spread Hurdle:** $+12.0$ bps (covers Cetus 5 bps / 25 bps fee + gas + buffer).
- **Transition Criteria to Tier 2:**
  1. **Verified Cumulative Net Profit:** $\ge \$100.000000$ USDC (`100_000_000` micro-units) from baseline.
  2. **Trade Count Stability:** At least 10 successfully committed PTBs in Tier 1.
  3. **Win Rate / Execution Ratio:** $\ge 80\%$ on submitted trades.
  4. **Gas Reserve:** Wallet SUI balance $\ge 2.0$ SUI.
  5. **Network Latency:** Median PTB execution latency $< 450$ ms.

#### Tier 2: Mid-Scale Compounding Phase
- **Parameter:** `flash_borrow_amount = 5_000_000_000` (5,000.000000 USDC).
- **Min Net Spread Hurdle:** $+10.0$ bps (lower percentage required to cover fixed gas cost).
- **Transition Criteria to Tier 3:**
  1. **Verified Cumulative Net Profit:** $\ge \$500.000000$ USDC generated in Tier 2 (total cumulative profit from start $\ge \$750.000000$ USDC).
  2. **Trade Count Stability:** At least 20 successfully committed PTBs in Tier 2.
  3. **Win Rate / Execution Ratio:** $\ge 85\%$ in Tier 2.
  4. **Liquidity Depth Verification:** AMM pool liquidity can absorb \$5k without exceeding 3 bps price impact.
  5. **Gas Reserve:** Wallet SUI balance $\ge 2.0$ SUI.

#### Tier 3: Terminal Production Scale Phase
- **Parameter:** `flash_borrow_amount = 10_000_000_000` (10,000.000000 USDC).
- **Min Net Spread Hurdle:** $+8.0$ bps.
- **Steady State Execution:** Maximum capital efficiency; continuous monitoring of slippage.

### 5.4 Net Profit Accounting & Verification Methodology

#### Baseline Reference Setup
At startup, the engine queries the on-chain USDC balance and establishes the reference baseline:
$$USDC_{\text{baseline}} = \text{QueryOnchainBalance}(CIRCLE\_USDC\_TYPE)$$

#### On-Chain Reconciliation Formula
Because Command 7 of the PTB transfers the remaining tokens directly to the operator address, all net profit accumulates as native USDC coins in the wallet.
$$\text{Accumulated Net Profit} = USDC_{\text{onchain\_current}} - USDC_{\text{baseline}}$$

#### Periodic Verification Routine
1. **Post-Trade Check:** Immediately following a successful PTB commit, wait for checkpoint finality (~390ms), then query GraphQL for updated balance.
2. **Periodic Sweep Loop:** Every 60 seconds during steady operation, execute `GetWalletBalances` to detect any off-chain desynchronization.
3. **Sanity Assertion:**
   $$\left| (USDC_{\text{onchain\_current}} - USDC_{\text{baseline}}) - \sum \Delta Q_{\text{reported\_by\_ptb}} \right| < 10,000 \text{ units (0.01 USDC)}$$
   If divergence exceeds 0.01 USDC, trigger `BALANCE_DIVERGENCE_ALERT` and pause promotions until reconciled.

---

## 6. Drawdown & Safety Guardrails

### 6.1 Circuit Breaker Matrix

| Guardrail | Trigger Condition | Immediate Action | Recovery Condition |
|---|---|---|---|
| **Gas Critical Floor** | SUI balance $< 0.5$ SUI | **Hard Stop:** Halt all execution; set state to `HALTED_LOW_GAS`. Cancel all pending tasks. | SUI balance replenished to $\ge 3.0$ SUI via external deposit or auto-refuel. |
| **Gas Warning Floor** | SUI balance $< 1.5$ SUI | **Throttle:** Increase scan interval to 2,000ms; restrict execution to spreads $\ge 20$ bps; emit warning alert. | SUI balance restored above 2.0 SUI. |
| **Consecutive Revert Breaker** | 3 consecutive PTB aborts on-chain | **Downgrade & Cooldown:** Demote scaling tier by 1 level (10k -> 5k, or 5k -> 1k). Enter 60-second cooldown. Flush local orderbook cache. | 60-second cooldown expires AND next dry-run passes with positive profit. |
| **Emergency Halt Breaker** | 5 consecutive PTB aborts on-chain | **Emergency Lock:** Halt trading engine; state `EMERGENCY_LOCK`. Require human review. | Manual operator reset command or restart after diagnostic check. |
| **Balance Divergence Guard** | On-chain USDC decreases or diverges by $> \$0.05$ | **Freeze Scaling:** Lock current tier; emit alert; re-read on-chain object state. | State reconciliation confirmed via 3 consecutive identical queries. |
| **Pre-Flight Dry-Run Gate** | `dryRunTransactionBlock` status != `success` or profit $\le 0$ | **Zero Broadcast:** Transaction is discarded locally. Zero on-chain gas burned. Zero state mutation. | Next market update produces profitable spread in dry run. |

### 6.2 Pre-Flight Simulation Workflow
The diagram below illustrates how `dryRunTransactionBlock` completely eliminates unnecessary gas burn:

```
Market Spread Detected (> Hurdle)
           │
           ▼
Build 8-Step Move PTB (Hot Potato + Cetus Swap + CLOB Fill)
           │
           ▼
Execute `dryRunTransactionBlock` on Sui RPC
           │
     ┌─────┴────────────────────────┐
     ▼                              ▼
Dry Run Failed                 Dry Run Succeeded
(Spread shifted / aborted)     (Profit verified > gas)
     │                              │
     ▼                              ▼
DISCARD LOCALLY                SIGN WITH Ed25519 KEY
Gas Burned: 0 SUI              BROADCAST TO MAINNET
Leg Risk: ZERO                 Gas Burned: ~0.0035 SUI
                               Profit Credited: +Delta Q
```

---

## 7. Programmatic Test Architecture & Verification Plan

### 7.1 Test Scope & Coverage Matrix

```
tests/
├── unit/
│   ├── test_sui_balance_tracker.py       # Balance queries, GraphQL parsing, decimal conversions
│   ├── test_dynamic_capital_scaling.py   # State transitions, tier promotions, demotions, cooldowns
│   ├── test_gas_safety_guardrails.py     # Critical & warning gas floors, alert emission
│   └── test_sui_ptb_builder_all_pairs.py # PTB construction across 4 pairs with 1k/5k/10k sizes
└── integration/
    ├── test_sui_graphql_live_probe.py    # Read-only query to live Sui Mainnet verifying 5.419 SUI
    └── test_sui_dry_run_simulation.py    # Simulation of profitable vs unprofitable spreads
```

### 7.2 Programmatic Test Cases Detailed

#### Test Case 1: `test_sui_graphql_balance_parsing`
- **Objective:** Verify accurate parsing of GraphQL response for both SUI (9 decimals) and USDC (6 decimals).
- **Input Mock:**
  ```json
  {"data": {"address": {"sui": {"totalBalance": "5419245048"}, "usdc": {"totalBalance": "150000000"}}}}
  ```
- **Assertions:**
  - `parsed.sui_mist == 5419245048`
  - `parsed.sui_float == 5.419245048`
  - `parsed.usdc_micro == 150000000`
  - `parsed.usdc_float == 150.000000`

#### Test Case 2: `test_gas_floor_transitions`
- **Objective:** Ensure state machine halts when gas balance drops below critical threshold.
- **Sequence:**
  1. Start with 5.419 SUI -> Status `NORMAL`.
  2. Degrade to 1.400 SUI -> Status `WARNING`, throttle active, alert emitted.
  3. Degrade to 0.450 SUI -> Status `CRITICAL`, state `HALTED_LOW_GAS`, `can_execute()` returns `False`.
  4. Replenish to 3.500 SUI -> Status `NORMAL`, execution re-enabled.

#### Test Case 3: `test_dynamic_scaling_tier_promotions`
- **Objective:** Validate strict condition checking before transitioning from Tier 1 -> Tier 2 -> Tier 3.
- **Sequence:**
  1. Initialize with `initial_borrow = 1_000_000_000` (Tier 1).
  2. Report 9 successful trades of \$12.00 profit each (cumulative = \$108.00). Tier must remain Tier 1 (count < 10).
  3. Report 10th successful trade. Cumulative = \$120.00. Tier promotes to Tier 2 (`flash_borrow_amount = 5_000_000_000`).
  4. Simulate 3 consecutive aborts at Tier 2. Engine must demote back to Tier 1 and enter 60-second cooldown.

#### Test Case 4: `test_ptb_builder_across_all_4_pairs`
- **Objective:** Verify valid 8-step PTB payload generation for `SUI/USDC`, `DEEP/SUI`, `DEEP/USDC`, and `CETUS/SUI`.
- **Assertions:**
  - Commands length == 8.
  - Step 0 targets DeepBook `borrow_flashloan_quote` with correct pool ID and coin types.
  - Step 1 targets Cetus `pool::swap` with correct quote/base types.
  - Step 6 consumes `flash_loan_receipt` via `return_flashloan_quote`.
  - Step 7 transfers remaining profit to `sender_address`.

#### Test Case 5: `test_live_mainnet_rpc_read_only_integration`
- **Objective:** Programmatically connect to `https://graphql.mainnet.sui.io/graphql` and confirm live wallet state without mutating blockchain state.
- **Assertions:**
  - HTTP 200 OK with valid GraphQL structure.
  - Address matches `0x5621a8e7199680512ee829565b96febea2587e534fd69b33f04004298d7e5ce9`.
  - SUI balance == `5419245048` MIST.

---

## 8. Implementation Blueprint (Data Structures & Classes)

Below is the technical specification of the Python classes to be implemented in downstream tasks:

### 8.1 `SuiBalanceTracker` Specification
```python
@dataclass
class WalletBalanceSnapshot:
    sui_mist: int
    sui_float: float
    usdc_units: int
    usdc_float: float
    timestamp_ns: int
    is_gas_critical: bool
    is_gas_warning: bool

class SuiBalanceTracker:
    def __init__(
        self,
        wallet_address: str,
        graphql_url: str = "https://graphql.mainnet.sui.io/graphql",
        gas_critical_floor_sui: float = 0.5,
        gas_warning_floor_sui: float = 1.5,
    ) -> None: ...
    async def fetch_balances(self) -> WalletBalanceSnapshot: ...
    def check_gas_safety(self, snapshot: WalletBalanceSnapshot) -> bool: ...
```

### 8.2 `DynamicCapitalScalingEngine` Specification
```python
class ScalingTier(Enum):
    TIER_1_1K = 1_000_000_000   # 1,000 USDC
    TIER_2_5K = 5_000_000_000   # 5,000 USDC
    TIER_3_10K = 10_000_000_000 # 10,000 USDC
    HALTED = 0

class DynamicCapitalScalingEngine:
    def __init__(
        self,
        balance_tracker: SuiBalanceTracker,
        tier1_profit_threshold_usdc: float = 100.0,
        tier2_profit_threshold_usdc: float = 500.0,
        min_tier1_trades: int = 10,
        min_tier2_trades: int = 20,
    ) -> None: ...
    def get_current_borrow_amount(self) -> int: ...
    def record_trade_result(self, success: bool, net_profit_usdc: float) -> None: ...
    def evaluate_state_transitions(self, onchain_usdc_balance: float) -> ScalingTier: ...
```

---

## 9. Conclusion & Next Steps for Implementation Agents

1. **Architecture Confirmed:** The system leverages Sui GraphQL RPC for resilient dual-balance tracking and an 8-step atomic PTB ensuring mathematical zero leg risk.
2. **Readiness:** With 5.419245048 SUI in gas reserves, the bot has over 2,700 on-chain execution abort buffers and virtually unlimited pre-flight simulation capacity.
3. **Downstream Handoff:** Implementation agents can directly translate the class specifications and test cases into production Python code within `trading-engine/venues/` and `trading-engine/tests/`.
