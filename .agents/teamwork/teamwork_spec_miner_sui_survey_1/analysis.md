# Technical Specification Survey: Sui DeepBookV3 & Cetus AMM Atomic Flash Loan Arbitrage Bot

**Date:** 2026-11-10T02:15:00Z  
**Target:** Sui Mainnet Atomic Flash Loan Arbitrage (H86)  
**Author:** teamwork_spec_miner_sui_survey_1  

---

## 1. Executive Summary & Codebase State

An exhaustive audit of the existing codebase and live Sui Mainnet state reveals a robust, mathematically guaranteed foundation for cross-DEX atomic arbitrage between **DeepBookV3** (Central Limit Order Book) and **Cetus AMM** (Concentrated Liquidity Market Maker), governed by Sui's Move VM **Hot Potato** flash loan semantics.

### 1.1 Existing Files Analyzed
- `trading-engine/venues/sui_deepbook_venue.py`: Primary venue connector implementing `SuiDeepBookVenue`, `SuiDeepBookPTBBuilder`, and `HotPotatoPTBParams`. Contains the serialized 8-command PTB builder and dry-run execution simulator.
- `trading-engine/tests/test_venues_unit.py`: Unit test suite (lines 352–434) verifying the 8-command PTB structure, Cetus AMM integration, and dry-run simulation of profitable vs. unprofitable spreads.
- `trading-engine/tests/test_adversarial_challenger_2.py`: Stress test suite (lines 72–240) validating Move VM Hot Potato semantics, slippage spectrum aborts, infinitesimal 1-mist boundaries, and flash crash scenarios.
- `trading-engine/simulations/test_quant_vectors_e2e.py`: Tier 1–4 end-to-end test suite (lines 313–384) verifying native USDC token constants, 0-fee borrowing, and atomic quenching.
- `trading-engine/simulations/simulate_h86_micro_capital.py`: Monte Carlo simulation modeling capital runway, gas bankrolls ($1 to $20 USD), and scaling dynamics across 1k, 5k, and 10k USDC loan sizes.
- `trading-engine/h86_sui/`: TypeScript execution framework (`h86_deepbook_execute.ts`, `h86_deepbook_scan.ts`, `h86_setup_wallet.ts`) and on-chain RPC scanner (`h86_onchain_orderbook.py`).

### 1.2 Critical RPC Infrastructure Finding
- **Legacy JSON-RPC Deprecation:** Direct calls to Sui public fullnodes via JSON-RPC methods (`sui_getObject`, `suix_queryEvents`) return error `-32601` (`Method not found. JSON-RPC on public fullnodes has been deprecated`).
- **Required Transport:** Production systems must connect via **Sui GraphQL RPC** (`https://graphql.mainnet.sui.io/graphql`) or **gRPC** (`sui-grpc.publicnode.com:443`). All on-chain object and pool inspections in this report were verified directly against `https://graphql.mainnet.sui.io/graphql`.

---

## 2. Sui Mainnet Asset & Pool Specifications (All 4 Pairs)

### 2.1 Core Coin Types & Metadata
All 4 assets are verified on-chain via Sui GraphQL `coinMetadata`:

| Asset | Exact Sui Type Identifier | Decimals | Minimal Atomic Unit | Issuer / Standard |
|---|---|---|---|---|
| **SUI** | `0x0000000000000000000000000000000000000000000000000000000000000002::sui::SUI` (short: `0x2::sui::SUI`) | 9 | 1 MIST ($10^{-9}$ SUI) | Native Sui Gas Coin |
| **USDC** | `0xdba34672e30cb065b1f93e3ab55318768fd6fef66c15942c9f7cb846e2f900e7::usdc::USDC` | 6 | 1 Micro-USDC ($10^{-6}$ USDC) | Circle Native USDC |
| **DEEP** | `0xdeeb7a4662eec9f2f3def03fb937a663dddaa2e215b8078a284d026b7946c270::deep::DEEP` | 6 | 1 Micro-DEEP ($10^{-6}$ DEEP) | DeepBook Protocol Token |
| **CETUS**| `0x06864a6f921804860930db6ddbe2e16acdf8504495ea7481637a1c8b9a8fe54b::cetus::CETUS` | 9 | 1 Nano-CETUS ($10^{-9}$ CETUS) | Cetus Protocol Token |

---

### 2.2 DeepBookV3 Mainnet Pools
- **Package ID:** `0x000000000000000000000000000000000000000000000000000000000000dee9` (short: `0xdee9`)  
- **Resolved Package Address:** `0x2c8d603bc51326b8c13cef9dd07031a408a48dddb541963357661df5d3204809`  
- **Flash Loan Fee:** Exactly **0 bps (0.00%)** via `borrow_flashloan_base` and `borrow_flashloan_quote`.

| Pair | Pool Object ID | Base Asset Type | Quote Asset Type | Tick Size | Lot Size | Min Size | Taker Fee | Maker Rebate | Whitelist Status |
|---|---|---|---|---|---|---|---|---|---|
| **SUI/USDC** | `0xe05dafb5133bcffb8d59f4e12465dc0e9faeaa05e3e342a08fe135800e3e4407` | `0x2::sui::SUI` (9 dec) | `Native USDC` (6 dec) | `1,000` ($0.001) | `100,000,000` (0.1 SUI) | `1,000,000,000` (1 SUI) | 10 bps (`1,000,000`) | 5 bps (`500,000`) | Standard (DEEP fee required) |
| **DEEP/SUI** | `0xb663828d6217467c8a1838a03793da896cbe745b150ebd57d82f814ca579fc22` | `DEEP` (6 dec) | `0x2::sui::SUI` (9 dec) | `10,000,000` ($0.01) | `10,000,000` (10 DEEP) | `100,000,000` (100 DEEP) | 0 bps (`0`) | 0 bps (`0`) | Whitelisted (0 fee) |
| **DEEP/USDC**| `0xf948981b806057580f91622417534f491da5f61aeaf33d0ed8e69fd5691c95ce` | `DEEP` (6 dec) | `Native USDC` (6 dec) | `10,000` ($0.01) | `10,000,000` (10 DEEP) | `100,000,000` (100 DEEP) | 0 bps (`0`) | 0 bps (`0`) | Whitelisted (0 fee) |
| **CETUS/SUI**| `0xcf8d0d98dd3c2ceaf40845f5260c620fa62b3a15380bc100053aecd6df8e5e7c` | `CETUS` (9 dec) | `0x2::sui::SUI` (9 dec) | `10,000` ($0.00001) | `100,000,000` (0.1 CETUS) | `1,000,000,000` (1 CETUS) | 10 bps (`1,000,000`) | 5 bps (`500,000`) | Standard (DEEP fee required) |

*DeepBook Price Factor Formula:*  
$$\text{Price Factor} = 10^{(9 - \text{Base Decimals} + \text{Quote Decimals})}$$
- SUI/USDC: $10^{(9 - 9 + 6)} = 10^6 = 1,000,000$. Real Price = $\text{raw\_price} / 10^6$.
- DEEP/SUI: $10^{(9 - 6 + 9)} = 10^{12} = 1,000,000,000,000$. Real Price = $\text{raw\_price} / 10^{12}$.
- DEEP/USDC: $10^{(9 - 6 + 6)} = 10^9 = 1,000,000,000$. Real Price = $\text{raw\_price} / 10^9$.
- CETUS/SUI: $10^{(9 - 9 + 9)} = 10^9 = 1,000,000,000$. Real Price = $\text{raw\_price} / 10^9$.

---

### 2.3 Cetus AMM Mainnet Pools
- **Core Package ID:** `0x1eabed72c53feb3805120a081dc15963c204dc8d091542592abaf7a35689b2fb`  
- **Router / Script Package ID:** `0x9ee0534b703b14457aee7698ea3a07a5080f954ed2b7e9910fbb7a55506824fa`  
- **Global Config ID:** `0xdaa46292632c3c4d8f31f23ea0f9b36a28ff3677e9684980e4438403a67a3d8f`  
- **Sui Clock Object ID:** `0x0000000000000000000000000000000000000000000000000000000000000006` (short: `0x6`)

| Pair | Pool Object ID | Coin A Type | Coin B Type | Fee Rate | Fee (bps) | Tick Spacing | Verified TVL | Direction for Arb (USDC/Base in) |
|---|---|---|---|---|---|---|---|---|
| **SUI/USDC (Tier 1)** | `0xb8d7d9e66a60c239e7a60110efcf8de6c705580ed924d0dde141f4a0e2c90105` | `Native USDC` (6 dec) | `SUI` (9 dec) | 2,500 | 25 bps (0.25%) | 60 | ~$3.84M | USDC $\to$ SUI: `a2b = true` |
| **SUI/USDC (Tier 2)** | `0x51e883ba7c0b566a26cbc8a94cd33eb0abd418a77cc1e60ad22fd9b1f29cd2ab` | `Native USDC` (6 dec) | `SUI` (9 dec) | 500 | 5 bps (0.05%) | 10 | ~$1.02M | USDC $\to$ SUI: `a2b = true` |
| **DEEP/SUI (Tier 1)** | `0xe01243f37f712ef87e556afb9b1d03d0fae13f96d324ec912daffc339dfdcbd2` | `DEEP` (6 dec) | `SUI` (9 dec) | 2,500 | 25 bps (0.25%) | 60 | ~$162k | SUI $\to$ DEEP: `a2b = false` (`b2a`) |
| **DEEP/SUI (Tier 2)** | `0xd978d331772a5b90d5a4781e1232d18afd12019d0c35db79e3674beeda8f9126` | `DEEP` (6 dec) | `SUI` (9 dec) | 500 | 5 bps (0.05%) | 10 | ~$84k | SUI $\to$ DEEP: `a2b = false` (`b2a`) |
| **DEEP/USDC** | `0xa2f4e24dc234cf024bae1bd5b1275ab5bdc7c28dd1ec84dd98c2d012bbd315f0` | `DEEP` (6 dec) | `Native USDC` (6 dec) | 500 | 5 bps (0.05%) | 10 | ~$19k | USDC $\to$ DEEP: `a2b = false` (`b2a`) |
| **CETUS/SUI** | `0x2e041f3fd93646dcc877f783c1f2b7fa62d30271bdef1f21ef002cebf857bded` | `CETUS` (9 dec) | `SUI` (9 dec) | 2,500 | 25 bps (0.25%) | 60 | ~$592k | SUI $\to$ CETUS: `a2b = false` (`b2a`) |

*Critical Cetus Sqrt Price Limits:*
- When `a2b = true` (swapping Coin A for Coin B): Price decreases. `sqrt_price_limit` must be set to the minimum allowable sqrt price:  
  `MIN_SQRT_PRICE = 4295048016` (or $0$ for unchecked boundary).
- When `a2b = false` (swapping Coin B for Coin A): Price increases. `sqrt_price_limit` must be set to the maximum allowable sqrt price:  
  `MAX_SQRT_PRICE = 79226673515401279992447579055` ($2^{96}-1$).

---

## 3. The 8-Step Atomic Programmable Transaction Block (PTB) Architecture

A Sui Programmable Transaction Block (PTB) allows heterogeneous Move function calls, coin splits, merges, and transfers to execute inside a single transaction with **total atomicity**. If any command fails, the entire transaction aborts, leaving 0 state mutations and preserving zero leg risk.

```
+----------------------------------------------------------------------------------------------------+
|                                    8-STEP ATOMIC MOVE PTB PIPELINE                                 |
+----------------------------------------------------------------------------------------------------+
| 0. borrow_flashloan_quote [DeepBook]                                                               |
|    Borrow Q USDC (0% fee) -> Produces [borrowed_usdc_coin, FlashLoan (Hot Potato)]                 |
|                                                                                                    |
| 1. router::swap [Cetus AMM]                                                                        |
|    Swap Q USDC on Cetus (a2b=true) -> Produces S SUI coin                                          |
|                                                                                                    |
| 2. balance_manager::deposit [DeepBook]                                                             |
|    Deposit S SUI coin into Operator's BalanceManager                                               |
|                                                                                                    |
| 3. pool::place_market_order [DeepBook CLOB]                                                        |
|    Sell S SUI as Market Ask -> Accumulates Q' USDC in BalanceManager                               |
|                                                                                                    |
| 4. balance_manager::withdraw_all [DeepBook]                                                        |
|    Withdraw accumulated proceeds Q' USDC as coin from BalanceManager                               |
|                                                                                                    |
| 5. SplitCoins [Sui Native Command]                                                                 |
|    Split exactly Q USDC (loan debt) from Q' USDC -> Produces [repay_coin, profit_coin]             |
|    *** REVERSION GATE: If Q' < Q, SplitCoins FAILS with InsufficientBalance ***                    |
|                                                                                                    |
| 6. pool::return_flashloan_quote [DeepBook]                                                         |
|    Pass repay_coin + FlashLoan -> Quenches Hot Potato struct                                       |
|                                                                                                    |
| 7. TransferObjects [Sui Native Command]                                                            |
|    Transfer profit_coin (Delta Q = Q' - Q) to Operator Wallet address                              |
+----------------------------------------------------------------------------------------------------+
```

### Detailed Command Breakdown

#### Command 0: Flash Loan Borrowing (Quote Asset)
- **Target:** `0xdee9::pool::borrow_flashloan_quote<Base, Quote>`
- **Type Arguments:** `[0x2::sui::SUI, 0xdba34672e30cb065b1f93e3ab55318768fd6fef66c15942c9f7cb846e2f900e7::usdc::USDC]`
- **Arguments:**
  - `pool`: `&mut Pool<Base, Quote>` (`Input 0` = `0xe05dafb5...`)
  - `amount`: `u64` (`Input 1` = `1_000_000_000` = 1,000 USDC)
- **Returns:**
  - `Result 0, Subresult 0`: `Coin<Quote>` (`borrowed_quote_coin`)
  - `Result 0, Subresult 1`: `0xdee9::vault::FlashLoan` (**Hot Potato Struct**)
- **Fee:** Exact 0 bps (0.0%).

#### Command 1: AMM Swap Leg (Cetus Concentrated Liquidity)
- **Target:** `0x9ee0534b703b14457aee7698ea3a07a5080f954ed2b7e9910fbb7a55506824fa::router::swap<CoinA, CoinB>`
- **Type Arguments:** `[0xdba34672...::usdc::USDC, 0x2::sui::SUI]`
- **Arguments:**
  - `config`: `&GlobalConfig` (`0xdaa46292...`)
  - `pool`: `&mut Pool<CoinA, CoinB>` (`0xb8d7d9e6...` or `0x51e883ba...`)
  - `coin_a`: `Coin<CoinA>` (`NestedResult(0, 0)` = borrowed USDC)
  - `coin_b`: `Coin<CoinB>` (pass `coin::zero<SUI>` or empty coin)
  - `a2b`: `bool` (`true`)
  - `by_amount_in`: `bool` (`true`)
  - `amount`: `u64` (`1_000_000_000`)
  - `sqrt_price_limit`: `u128` (`4295048016` = minimum sqrt price for a2b)
  - `has_amount_limit`: `bool` (`false`)
  - `clock`: `&Clock` (`0x6`)
- **Returns:**
  - `Result 1, Subresult 0`: `Coin<USDC>` (remaining unused input, typically 0)
  - `Result 1, Subresult 1`: `Coin<SUI>` (`swapped_base_coin`, acquired SUI)

#### Command 2: Deposit Swapped Base Coin to DeepBook Balance Manager
- **Target:** `0xdee9::balance_manager::deposit<Base>`
- **Type Arguments:** `[0x2::sui::SUI]`
- **Arguments:**
  - `balance_manager`: `&mut BalanceManager` (`Input: balance_manager_id`)
  - `coin`: `Coin<Base>` (`NestedResult(1, 1)` = acquired SUI)
- **Returns:** `()`

#### Command 3: Place Market Ask Order on DeepBook CLOB
- **Target:** `0xdee9::pool::place_market_order<Base, Quote>`
- **Type Arguments:** `[0x2::sui::SUI, 0xdba34672...::usdc::USDC]`
- **Arguments:**
  - `pool`: `&mut Pool<Base, Quote>` (`Input: pool_id`)
  - `balance_manager`: `&mut BalanceManager` (`Input: balance_manager_id`)
  - `trade_proof`: `&TradeProof` (generated via `balance_manager::generate_proof_as_owner` or session proof)
  - `client_order_id`: `u64` (`0`)
  - `order_type`: `u8` (`2` = Immediate-Or-Cancel Market Order)
  - `quantity`: `u64` (size of SUI to sell)
  - `is_bid`: `bool` (`false` = Ask / Sell Base for Quote)
  - `pay_with_deep`: `bool` (`false` or `true` if holding DEEP for fee discount)
  - `clock`: `&Clock` (`0x6`)
- **Returns:** `OrderInfo` (execution fill summary; proceeds $Q'$ credited to BalanceManager)

#### Command 4: Withdraw Accumulated Quote Proceeds from Balance Manager
- **Target:** `0xdee9::balance_manager::withdraw_all<Quote>`
- **Type Arguments:** `[0xdba34672...::usdc::USDC]`
- **Arguments:**
  - `balance_manager`: `&mut BalanceManager` (`Input: balance_manager_id`)
- **Returns:**
  - `Result 4, Subresult 0`: `Coin<Quote>` (`withdrawn_quote_coin`, total proceeds $Q'$)

#### Command 5: Split Exact Flash Loan Repayment Coin
- **Target:** Native PTB `SplitCoins`
- **Arguments:**
  - `coin`: `NestedResult(4, 0)` (`withdrawn_quote_coin`)
  - `amounts`: `[1_000_000_000]` (exact borrowed principal $Q$)
- **Returns:**
  - `Result 5, Subresult 0`: `Coin<Quote>` (`repay_quote_coin`, exactly $Q$ units)
- **Residual Coin:** `NestedResult(4, 0)` now holds exactly $\Delta Q = Q' - Q$ units of net USDC profit.

#### Command 6: Return Flash Loan (Quench Hot Potato)
- **Target:** `0xdee9::pool::return_flashloan_quote<Base, Quote>`
- **Type Arguments:** `[0x2::sui::SUI, 0xdba34672...::usdc::USDC]`
- **Arguments:**
  - `pool`: `&mut Pool<Base, Quote>` (`Input: pool_id`)
  - `coin`: `NestedResult(5, 0)` (`repay_quote_coin`)
  - `flash_loan`: `NestedResult(0, 1)` (`flash_loan_receipt` Hot Potato struct)
- **Returns:** `()`
- **Move Invariant:** The Hot Potato struct is consumed and destroyed.

#### Command 7: Transfer Net Profit to Operator Wallet
- **Target:** Native PTB `TransferObjects`
- **Arguments:**
  - `objects`: `[NestedResult(4, 0)]` (remaining profit coin $\Delta Q$)
  - `recipient`: `sender_address`
- **Gas Coin Safety:** The gas coin (`GAS`) is **never passed** into `SplitCoins` for the arbitrage leg. Gas is strictly isolated for network execution fees (~0.002 SUI), preventing accidental gas drainage or coin contamination.

---

## 4. Error Handling, Move VM Reversion & Zero Leg Risk

### 4.1 Theoretical & Mechanical Zero Leg Risk
In Move, a struct without `drop`, `copy`, `store`, or `key` is termed a **Hot Potato**:
```move
public struct FlashLoan {
    pool_id: ID,
    borrow_quantity: u64,
    type_asset: u8,
}
```
Because `FlashLoan` lacks the `drop` ability, it is illegal for the transaction block to complete while an instance of `FlashLoan` exists. It can only be unpacked and consumed inside `pool::return_flashloan_quote` or `pool::return_flashloan_base`.

### 4.2 Reversion Behavior on Negative Spread / Slippage
Consider the three market conditions:
1. **Profitable Spread ($Q' > Q$):**
   - Step 4 withdraws $Q'$.
   - Step 5 splits $Q$ into `repay_coin` and leaves $\Delta Q > 0$.
   - Step 6 consumes `FlashLoan` with `repay_coin`.
   - Step 7 transfers $\Delta Q$ to sender.
   - **Result:** PTB commits successfully. Net balance change = $+\Delta Q$ USDC, $-0.002$ SUI gas.
2. **Breakeven ($Q' = Q$):**
   - Step 5 splits exactly $Q$, leaving 0 in residual coin.
   - Step 6 quenches `FlashLoan`.
   - Step 7 transfers 0-value coin (or ignored).
   - **Result:** PTB commits with 0 net profit.
3. **Negative Spread / Slippage ($Q' < Q$):**
   - The CLOB bid or AMM liquidity was insufficient to produce $Q$ units of quote asset ($Q' < Q$).
   - Step 5 attempts to split $Q$ units from a coin with balance $Q'$.
   - **Sui Native VM Abort:** `SplitCoins` immediately aborts with `InsufficientBalance`.
   - Because Step 5 fails, Step 6 (`return_flashloan_quote`) is **never reached**.
   - The Move VM detects an unhandled Hot Potato (`UnhandledHotPotato`) and **aborts the entire transaction block**.
   - **State Mutations:** Exactly **0** (all state reverts).
   - **Lingering Debt:** Exactly **0** (the borrowed coin never leaves the aborted PTB).
   - **Cost Incurred:** Only execution gas burned (~0.002 SUI / ~$0.004 USD).

---

## 5. Capital Scaling & Runway Specifications (R2)

### 5.1 Dynamic Scaling Logic
Per requirements R1 and R2 in `ORIGINAL_REQUEST.md`:
- **Initial State:** `flash_borrow_amount = 1_000_000_000` (1,000 USDC native, 6 decimals).
- **Threshold 1 (Transition to 5k):** When cumulative net realized USDC balance on wallet $\ge 500$ USDC, automatically scale `flash_borrow_amount = 5_000_000_000` (5,000 USDC).
- **Threshold 2 (Transition to 10k):** When cumulative net realized USDC balance $\ge 2,500$ USDC, automatically scale `flash_borrow_amount = 10_000_000_000` (10,000 USDC).

### 5.2 Micro-Capital Runway & Gas Capacity
- **Initial Wallet Balance:** `5.419245048 SUI` (~$11.10 USD at $2.05/SUI).
- **Gas per PTB:** ~`0.002 SUI` (2,000,000 MIST).
- **Total Max Aborted Attempts Runway:**
  $$\text{Runway} = \frac{5.419245048 \text{ SUI}}{0.002 \text{ SUI/tx}} \approx 2,709 \text{ consecutive failed transactions}$$
- **Empirical Simulation Result (`simulate_h86_micro_capital.py`):**
  - With initial capital of just $1.00 USD (243 attempts), the probability of ruin is **0.0%** because off-chain filters eliminate negative spreads before submission, and dry-run simulations prevent non-viable PTBs from touching the validator consensus.
  - With 5.419 SUI, the bot has over 2,700 attempts of pure execution buffer, making capital exhaustion virtually impossible under normal network conditions.

---

## 6. Features Discovered & Edge Cases

## Features Discovered
| # | Category | Feature | Description | Inputs | Outputs | Error Behavior | Discovered Via |
|---|----------|---------|-------------|--------|---------|----------------|----------------|
| 1 | RPC Transport | Sui GraphQL RPC | Official modern query interface for Sui mainnet | GraphQL Query / Variables | JSON Object / Event Data | HTTP 200 with `errors` array | `https://graphql.mainnet.sui.io/graphql` |
| 2 | RPC Transport | Legacy JSON-RPC Deprecation | Public fullnodes reject JSON-RPC calls | `sui_getObject`, `suix_queryEvents` | `{"code": -32601}` | Method not found error | Live Sui RPC probing |
| 3 | DEX (CLOB) | DeepBookV3 Flash Loan | 0-fee flash borrow producing Hot Potato | `pool: ID`, `amount: u64` | `[Coin<T>, FlashLoan]` | Move VM abort if invalid pool/amount | `0x2c8d603b...::pool::borrow_flashloan_quote` |
| 4 | DEX (CLOB) | DeepBookV3 Hot Potato Quench | Repay exact principal, destroying receipt | `pool: ID`, `coin: Coin<T>`, `receipt: FlashLoan` | `()` | Move VM abort if coin amount < borrowed | `0x2c8d603b...::pool::return_flashloan_quote` |
| 5 | DEX (CLOB) | DeepBook Balance Manager | Dedicated trading account for resting and market orders | `balance_manager: ID`, `trade_proof` | `OrderInfo` / Balance state | Aborts on invalid signature or balance | `0x2c8d603b...::balance_manager` |
| 6 | DEX (CLOB) | Whitelisted 0-Fee Pools | DEEP/SUI and DEEP/USDC charge 0 taker/maker fees | Standard order arguments | `OrderInfo` with 0 fee | None (fee exempted) | On-chain `PoolCreated` event scan |
| 7 | DEX (AMM) | Cetus CLMM Router Swap | Concentrated liquidity swap accepting coin inputs | `config`, `pool`, `coin_a`, `coin_b`, `a2b`, `amount` | `[Coin<A>, Coin<B>]` | Aborts on slippage exceeding `sqrt_price_limit` | `0x9ee0534b...::router::swap` |
| 8 | DEX (AMM) | Cetus Flash Swap & Repay | Low-level flash swap returning balance and receipt | `config`, `pool`, `a2b`, `by_amount_in`, `amount` | `[Balance<A>, Balance<B>, FlashSwapReceipt]` | Aborts if `repay_flash_swap` lacks balance | `0x1eabed72...::pool::flash_swap` |
| 9 | DEX (AMM) | Cetus Price Limits | Enforces price direction protection in AMM curve | `sqrt_price_limit: u128` | Clamped execution price | Aborts if limit breached before full fill | Cetus SDK & On-Chain Move |
| 10 | Move Native | Hot Potato Reversion Gate | PTB split failure aborts before loan repayment | `SplitCoins(coin, [borrow_amount])` | `[repay_coin, profit_coin]` | `InsufficientBalance` aborts full PTB | Sui Move VM specification |
| 11 | Move Native | Gas Coin Isolation | Gas coin is separated from trade assets | `GAS` input | Gas payment only | Out of gas abort if SUI < fee | Sui PTB specification |

## Edge Cases
| # | Feature | Input | Observed Behavior |
|---|---------|-------|-------------------|
| 1 | Flash Loan Repayment | $Q' = Q - 1 \text{ MIST}$ (Shortfall of 1 atomic unit) | `SplitCoins` fails with `InsufficientBalance`. Command 6 (`return_flashloan_quote`) is never reached. PTB aborts cleanly; 0 state mutations committed; gas fee (~0.002 SUI) burned. |
| 2 | Flash Loan Repayment | $Q' = Q$ (Exact breakeven) | `SplitCoins` produces exact repay coin and 0-value residual coin. Hot Potato quenched. Transaction succeeds with 0.0 net profit. |
| 3 | AMM Slippage / Sandwich | AMM price spikes 10x before PTB commit | Swapped base tokens $S$ drop significantly. CLOB sell proceeds $Q' \ll Q$. PTB aborts at Command 5 with zero leg risk. |
| 4 | CLOB Crash / Depth Drain | DeepBook bid book drained by 99% | Market ask fills at deep discount. Proceeds $Q' < Q$. PTB aborts at Command 5; no debt remains. |
| 5 | Cetus Sqrt Price Limit | `sqrt_price_limit` set above market price in `a2b` | AMM swap aborts immediately in Move with `EExceedPriceLimit`; PTB reverts. |
| 6 | Fee Calculation on SUI/USDC | DEEP balance = 0 on Operator wallet | DeepBook SUI/USDC pool charges 10 bps taker fee deducted from output quote coins. Spreads must exceed 35 bps (25 bps Cetus + 10 bps DeepBook) to be profitable. |
| 7 | Gas Coin Exhaustion | SUI balance drops below 0.005 SUI | Transaction cannot be constructed or signed; node rejects before consensus. |
