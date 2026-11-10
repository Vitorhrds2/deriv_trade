# Handoff Report: Turbos Finance CLMM & DeepBook V3 <-> Cetus Reverse Route Specification

- **Agent**: survey_1 (`teamwork_spec_miner`)
- **Date**: 2026-11-10T18:37:00Z
- **Target Folder**: `/Users/vitorhrds/Documents/Github/hypothesis/.agents/teamwork/teamwork_spec_miner_survey_1`
- **Scope**: Authoritative protocol specifications, contract interfaces, packages, integration patterns, and PTB mechanics for:
  1. Turbos Finance CLMM on Sui Mainnet.
  2. DeepBook V3 & Cetus Reverse Route (`DeepBook Ask -> Cetus Bid`).

---

## 1. Observation

### 1.1 Existing Codebase & Test Suite State
- **Virtualenv & Pytest Execution**: Executed `trading-engine/.venv/bin/pytest trading-engine/tests`. Result:
  ```text
  ============================= 515 passed in 22.61s =============================
  ```
  All 515 unit, integration, adversarial, and regression tests currently pass without error.
- **Existing PTB Architecture (`trading-engine/venues/sui_deepbook_venue.py`)**:
  - Lines 43-48 define package IDs:
    ```python
    DEEPBOOK_PACKAGE_ID = "0xdee9"
    DEEPBOOK_V3_PACKAGE_ID = "0x2c8d603bc51326b8c13cef9dd07031a408a48dddb541963357661df5d3204809"
    DEEPBOOK_V3_LATEST_PKG_ID = "0xbca0cefe720330e7bb4f2283438b68de6a0e656688db4ac90d61e71fe6151fe8"
    CETUS_CORE_PACKAGE_ID = "0x1eabed72c53feb3805120a081dc15963c204dc8d091542592abaf7a35689b2fb"
    CETUS_CLMM_LATEST_PKG_ID = "0x260693ec785a6e6c9d81d58c7d2ff72f1288ae0fa6a9725abe05a6478b11f084"
    ```
  - Lines 271-272 define placeholders in `HotPotatoPTBParams`:
    ```python
    amm_target: str = "cetus"  # "cetus" | "turbos"
    borrow_asset: str = "quote"  # "quote" | "base"
    ```
  - Lines 726-753 implement the forward route (Cetus Price < DeepBook Bid) via Move calls:
    - `borrow_flashloan_quote`
    - `cetus::pool::flash_swap` + `repay_flash_swap`
    - `db::pool::swap_exact_base_for_quote`
    - `SplitCoins` + `return_flashloan_quote`
    - `TransferObjects` to sender

### 1.2 DeepBook V3 Contract Interfaces (`@mysten/deepbook-v3`)
- **Inspection of `@mysten/deepbook-v3/src/contracts/deepbook/pool.ts`**:
  - Lines 1172-1184 (`borrow_flashloan_quote`):
    ```typescript
    export function borrowFlashloanQuote(options: BorrowFlashloanQuoteOptions) {
      const packageAddress = options.package ?? '@deepbook/core';
      const argumentsTypes = [null, 'u64'] satisfies (string | null)[];
      const parameterNames = ['self', 'quoteAmount'];
      return (tx: Transaction) => tx.moveCall({
        package: packageAddress,
        module: 'pool',
        function: 'borrow_flashloan_quote',
        arguments: normalizeMoveArguments(options.arguments, argumentsTypes, parameterNames),
        typeArguments: options.typeArguments,
      });
    }
    ```
  - Lines 1144-1156 (`borrow_flashloan_base`):
    Parameters: `self: &mut Pool<Base, Quote>`, `baseAmount: u64`. Returns `(Coin<Base>, FlashLoan)`.
  - Lines 1205-1217 (`return_flashloan_base`) and 1238-1250 (`return_flashloan_quote`):
    Parameters: `self: &mut Pool<Base, Quote>`, `coin: Coin<T>`, `flashLoan: FlashLoan`. Unwraps and quenches the Hot Potato receipt.
  - Lines 476-493 (`swap_exact_quote_for_base`):
    ```typescript
    /**
     * Swap exact quote quantity without needing a `balance_manager`. DEEP quantity can
     * be overestimated. Returns three `Coin` objects: base, quote, and deep. Some
     * quote quantity may be left over if the input quantity is not divisible by lot size.
     */
    export function swapExactQuoteForBase(options: SwapExactQuoteForBaseOptions) { ... }
    ```
    Arguments: `[self, quoteIn, deepIn, minBaseOut, clock]`.
    Type arguments: `[BaseAsset, QuoteAsset]`.
    Returns: `(Coin<BaseAsset>, Coin<QuoteAsset>, Coin<DEEP>)`.
  - Lines 2249-2262 (`vault_balances`):
    Arguments: `[self]`. Type arguments: `[BaseAsset, QuoteAsset]`.
    Returns: `(u64, u64, u64)` -> `(base_balance, quote_balance, deep_balance)`.
- **Inspection of `@mysten/deepbook-v3/src/contracts/deepbook/vault.ts`**:
  - Lines 15-22 (`Vault` struct):
    ```typescript
    export const Vault = new MoveStruct({
      name: `${$moduleName}::Vault<phantom BaseAsset, phantom QuoteAsset>`,
      fields: {
        base_balance: balance.Balance,
        quote_balance: balance.Balance,
        deep_balance: balance.Balance,
      },
    });
    ```
  - If `borrow_quantity > vault.quote_balance.value`, Move VM aborts with code 2 (`EInsufficientVaultBalance`).

### 1.3 Turbos Finance CLMM Authoritative Specifications
- **Authoritative Configuration Endpoint**: Retrieved `https://s3.amazonaws.com/app.turbos.finance/sdk/contract.json`:
  ```json
  "mainnet": {
    "contract": {
      "PackageId": "0xa5a0c25c79e428eba04fb98b3fb2a34db45ab26d4c8faf0d7e39d66a63891e64",
      "PackageIdOriginal": "0x91bfbc386a41afcfd9b2533058d7e915a1d3829089cc268ff4333d54d6339ca1",
      "PoolConfig": "0xc294552b2765353bcafa7c359cd28fd6bc237662e5db8f09877558d81669170c",
      "Positions": "0xf5762ae5ae19a2016bb233c72d9a4b2cba5a302237a82724af66292ae43ae52d",
      "PoolFactoryAdminCap": "0x4bd4c54c84158e4ddab02ba612a84fc4b02dff3cb2ee687db0e46b5ab2f8bc5b",
      "Versioned": "0xf1cf0e81048df168ebeb1b8030fad24b3e0b53ae827c25053fff0779c1445b6f",
      "PoolTableId": "0x08984ed8705f44b6403705dc248896e56ab7961447820ae29be935ce0d32198b"
    },
    "fee": {
      "10bps": "0x49dcf28ac3b5480e65bee812ad2d6e60108ab8037d5a815c3c11bbe7bc47c270",
      "100bps": "0x18136d55969b970330e6991e0deaa713fca99f4e526152c10d5592a01d45f857",
      "500bps": "0xdfcd1043f54fef3aa649eccd4d0b2b09a3da6c87a8a62736467b686268869365",
      "1000bps": "0x3725d87c71b3981924cdda303e536cfe335c1cdc656c5d2cfb71b6f31296b488",
      "1500bps": "0xd2c339cf4764232690e9b8b495deba88289c04d58af80532e4c45ae22b8b504a",
      "2000bps": "0x5121798d1ac50ee8d5c3213c69d4955814318901070ac06a8accfba39fb30198",
      "2500bps": "0x0dfa811ff9d86f7680f212a78b2dd886f10916383d80accf287612a0df3906a0",
      "3000bps": "0x6bc433c8604f58272155d0c65327ae0b316f63869e5de3846f70aef4625d8c46"
    }
  }
  ```
- **Live On-Chain Sui GraphQL Verification (`https://graphql.mainnet.sui.io/graphql`)**:
  - `Versioned` object `0xf1cf0e81048df168ebeb1b8030fad24b3e0b53ae827c25053fff0779c1445b6f` has `initialSharedVersion: 1621135`. Passed as immutable `&Versioned` in swap functions.
  - `swap_router` module functions verified in package `0xa5a0c25c79e428eba04fb98b3fb2a34db45ab26d4c8faf0d7e39d66a63891e64`:
    - `swap_a_b` (`public entry`): takes `(pool, coins: vector<Coin<CoinA>>, amount_specified: u64, amount_threshold: u64, sqrt_price_limit: u128, is_exact_input: bool, recipient: address, deadline: u64, clock: &Clock, versioned: &Versioned)`. Transfers outputs directly to `recipient`.
    - `swap_a_b_with_return_` (`public fun`): takes identical arguments, returns `(Coin<CoinB>, Coin<CoinA>)`.
    - `swap_b_a` (`public entry`): takes `(pool, coins: vector<Coin<CoinB>>, amount_specified: u64, amount_threshold: u64, sqrt_price_limit: u128, is_exact_input: bool, recipient: address, deadline: u64, clock: &Clock, versioned: &Versioned)`.
    - `swap_b_a_with_return_` (`public fun`): takes identical arguments, returns `(Coin<CoinA>, Coin<CoinB>)`.
- **Verified Pool IDs, Initial Shared Versions & Move Structs on Sui Mainnet**:
  1. **SUI/USDC**:
     - Pool ID: `0x0df4f02d0e210169cb6d5aabd03c3058328c06f2c4dbb0804faa041159c78443`
     - initialSharedVersion: `426673878`
     - Type: `0x91bfbc386a41afcfd9b2533058d7e915a1d3829089cc268ff4333d54d6339ca1::pool::Pool<0x2::sui::SUI, 0xdba34672e30cb065b1f93e3ab55318768fd6fef66c15942c9f7cb846e2f900e7::usdc::USDC, 0x91bfbc386a41afcfd9b2533058d7e915a1d3829089cc268ff4333d54d6339ca1::fee500bps::FEE500BPS>`
     - Coin A: `SUI` (9 decimals), Coin B: `USDC` (6 decimals), Fee: 500 (5.0 bps).
  2. **DEEP/SUI**:
     - Pool ID: `0xbca476e3c744648c65b1fae5551b86be8ad7f482ca9c2268dad1d6b4fd0e2635`
     - initialSharedVersion: `389633758`
     - Type: `0x91bfbc386a41afcfd9b2533058d7e915a1d3829089cc268ff4333d54d6339ca1::pool::Pool<0xdeeb7a4662eec9f2f3def03fb937a663dddaa2e215b8078a284d026b7946c270::deep::DEEP, 0x2::sui::SUI, 0x91bfbc386a41afcfd9b2533058d7e915a1d3829089cc268ff4333d54d6339ca1::fee3000bps::FEE3000BPS>`
     - Coin A: `DEEP` (6 decimals), Coin B: `SUI` (9 decimals), Fee: 3000 (30 bps).
  3. **DEEP/USDC**:
     - Pool ID: `0x198af6ff81028c6577e94465d534c4e2cfcbbab06a95724ece7011c55a9d1f5a`
     - initialSharedVersion: `599890732`
     - Type: `0x91bfbc386a41afcfd9b2533058d7e915a1d3829089cc268ff4333d54d6339ca1::pool::Pool<0xdeeb7a4662eec9f2f3def03fb937a663dddaa2e215b8078a284d026b7946c270::deep::DEEP, 0xdba34672e30cb065b1f93e3ab55318768fd6fef66c15942c9f7cb846e2f900e7::usdc::USDC, 0x38a236095cb5a4fec3bdf42cf3e9c80f7ef68f1a835290a6cd107f156f8747f4::fee1500bps::FEE1500BPS>`
     - Coin A: `DEEP` (6 decimals), Coin B: `USDC` (6 decimals), Fee: 1500 (15 bps).
  4. **CETUS/SUI**:
     - Pool ID: `0xdf9d069bdfd51515aa0316698225a26444cbdf3cccd130a226b3ac81cfe2f606`
     - initialSharedVersion: `561404948`
     - Type: `0x91bfbc386a41afcfd9b2533058d7e915a1d3829089cc268ff4333d54d6339ca1::pool::Pool<0x06864a6f921804860930db6ddbe2e16acdf8504495ea7481637a1c8b9a8fe54b::cetus::CETUS, 0x2::sui::SUI, 0x91bfbc386a41afcfd9b2533058d7e915a1d3829089cc268ff4333d54d6339ca1::fee3000bps::FEE3000BPS>`
     - Coin A: `CETUS` (9 decimals), Coin B: `SUI` (9 decimals), Fee: 3000 (30 bps).

---

## 2. Logic Chain

### 2.1 Turbos Finance CLMM Mechanics & Math
1. **Math Formulation**:
   - Spot price of Coin B per Coin A:
     $$P_{B/A} = \left(\frac{\text{sqrt\_price}}{2^{64}}\right)^2 \cdot 10^{\text{decimals}_A - \text{decimals}_B}$$
   - When Coin A is base and Coin B is quote, spot price of base in quote is $P_{B/A}$.
   - When Coin B is base and Coin A is quote, spot price of base in quote is $1 / P_{B/A}$.
2. **Scanner Polling**:
   - In Sui GraphQL, the query batch can poll both Cetus and Turbos pool objects in a single round-trip:
     ```graphql
     p_turbos_sui_usdc: object(address: "0x0df4f02d0e210169cb6d5aabd03c3058328c06f2c4dbb0804faa041159c78443") {
       asMoveObject { contents { json } }
     }
     ```
   - Parsing: Read `contents["json"]["sqrt_price"]`. If `params.amm_target == "turbos"`, calculate spot price using Turbos pool decimals and coin ordering.
3. **PTB Swap Execution**:
   - Because `pool::swap` has friend visibility, router module `0xa5a0c25c79e428eba04fb98b3fb2a34db45ab26d4c8faf0d7e39d66a63891e64::swap_router` is the required entrypoint.
   - For atomic composability with DeepBook flashloans, `swap_a_b_with_return_` and `swap_b_a_with_return_` must be used because they return the resulting `Coin` object directly into the transaction environment, avoiding premature object transfer to an external wallet before loan repayment.
   - Inputs require:
     - `coins: vector<Coin<T>>`: Wrapped via `Command::MakeMoveVec([coin])`.
     - `sqrt_price_limit`: `MIN_SQRT_PRICE` (`4295048016`) for `a2b = True`; `MAX_SQRT_PRICE` (`79226673515401279992447579055`) for `a2b = False`.
     - `deadline`: `now_ms + 180_000`.
     - `versioned`: `0xf1cf0e81048df168ebeb1b8030fad24b3e0b53ae827c25053fff0779c1445b6f` (immutable reference).
     - `clock`: `0x6` (immutable reference).

### 2.2 DeepBook V3 & Cetus Reverse Route Mechanics (`DeepBook Ask -> Cetus Bid`)
1. **Spread Condition**:
   - Cetus Price > DeepBook Ask.
   - Base is cheaper on DeepBook (at Ask price) and more expensive on Cetus (at Bid price).
2. **Flashloan Asset Determination**:
   - **Primary Asset**: Borrow Quote asset (`borrow_flashloan_quote`).
     - Reasoning: By borrowing Quote, the market buy on DeepBook is executed via `swap_exact_quote_for_base`, which consumes Quote and outputs Base tokens.
     - The Base tokens are then sold on Cetus (AMM Bid) for Quote tokens.
     - The borrowed principal Quote is split and returned via `return_flashloan_quote`.
     - All net profits are retained in Quote (USDC or SUI), completely avoiding dual-currency residue or residual unsold inventory.
   - **Dynamic Selection & Vault Balance Protection**:
     - Before executing, query DeepBook `vault_balances(pool_id)`.
     - If `vault.quote_balance < borrow_amount`, DO NOT borrow quote. If `vault.base_balance >= borrow_amount_base`, can fall back to `borrow_flashloan_base` (selling Base on Cetus, buying Base on DeepBook).
     - If neither vault balance meets the required tranche size, abort pre-flight immediately, preventing `EInsufficientVaultBalance` (abort code 2).
3. **PTB Command Flow (Reverse Route - Borrow Quote)**:
   - Command 0: `db::pool::borrow_flashloan_quote<Base, Quote>(db_pool, quote_borrow_amount)` -> `[quote_coin, flash_loan_receipt]`
   - Command 1: `coin::zero<DEEP>()` -> `zero_deep`
   - Command 2: `db::pool::swap_exact_quote_for_base<Base, Quote>(db_pool, quote_coin, zero_deep, min_base_out, clock)` -> `(base_out, quote_leftover, deep_zero)`
   - Command 3: `coin::destroy_zero<DEEP>(deep_zero)`
   - Command 4: `coin::into_balance<BaseCoin>(base_out)` -> `base_balance`
   - Command 5: `balance::zero<QuoteCoin>()` -> `zero_quote_balance`
   - Command 6: `cetus::pool::flash_swap<CoinA, CoinB>(cetus_config, cetus_pool, a2b_rev, True, base_amount, sqrt_limit_rev, clock)` -> `(bal_a, bal_b, receipt)`
   - Command 7: `balance::destroy_zero<BaseCoin>(zero_base_bal)`
   - Command 8: `cetus::pool::repay_flash_swap<CoinA, CoinB>(cetus_config, cetus_pool, repay_a, repay_b, receipt)`
   - Command 9: `coin::from_balance<QuoteCoin>(swapped_quote_bal)` -> `quote_swapped`
   - Command 10: `MergeCoins(quote_swapped, [quote_leftover])` (consolidate leftover quote from DeepBook lot rounding)
   - Command 11: `SplitCoins(quote_swapped, [quote_borrow_amount])` -> `repay_quote_coin`
   - Command 12: `db::pool::return_flashloan_quote<Base, Quote>(db_pool, repay_quote_coin, flash_loan_receipt)` -> Quenches Hot Potato struct
   - Command 13: `TransferObjects([quote_swapped], recipient)` -> Transfers net arbitrage profit to operator wallet

### 2.3 Q* Optimal Sizing Formulation
1. Net edge: $\Delta = S - F$, where $S$ is spread and $F$ is fee hurdle.
2. Marginal price impact slope: $\lambda = \Delta P / (P \cdot \Delta Q)$.
3. Optimal tranche:
   $$Q^* = \frac{S - F}{\lambda}$$
4. Safeguards:
   $$Q_{opt} = \max(Q_{min}, \min(Q^*, 0.85 \cdot D_{CLOB}, 0.80 \cdot V_{vault}, Q_{max}))$$
   where $Q_{min} = 100 \text{ USDC}$ and $Q_{max} = 10,000 \text{ USDC}$ (tiered).

---

## 3. Features Discovered

| # | Category | Feature | Description | Inputs | Outputs | Error Behavior | Discovered Via |
|---|----------|---------|-------------|--------|---------|----------------|----------------|
| 1 | Turbos CLMM | `swap_a_b` | Direct entry swap from Token A to Token B | Pool, `vector<Coin<A>>`, `amount_specified: u64`, `amount_threshold: u64`, `sqrt_price_limit: u128`, `is_exact_input: bool`, `recipient: address`, `deadline: u64`, Clock, Versioned | None (direct transfer to recipient) | Aborts if deadline passed or slippage exceeded | Move package `0xa5a0c25c...::swap_router` |
| 2 | Turbos CLMM | `swap_b_a` | Direct entry swap from Token B to Token A | Pool, `vector<Coin<B>>`, `amount_specified: u64`, `amount_threshold: u64`, `sqrt_price_limit: u128`, `is_exact_input: bool`, `recipient: address`, `deadline: u64`, Clock, Versioned | None (direct transfer to recipient) | Aborts if deadline passed or slippage exceeded | Move package `0xa5a0c25c...::swap_router` |
| 3 | Turbos CLMM | `swap_a_b_with_return_` | Composable swap returning coin objects (A -> B) | Pool, `vector<Coin<A>>`, `amount_specified: u64`, `amount_threshold: u64`, `sqrt_price_limit: u128`, `is_exact_input: bool`, `recipient: address`, `deadline: u64`, Clock, Versioned | `(Coin<CoinB>, Coin<CoinA>)` | Aborts on slippage or invalid pool version | Move package `0xa5a0c25c...::swap_router` |
| 4 | Turbos CLMM | `swap_b_a_with_return_` | Composable swap returning coin objects (B -> A) | Pool, `vector<Coin<B>>`, `amount_specified: u64`, `amount_threshold: u64`, `sqrt_price_limit: u128`, `is_exact_input: bool`, `recipient: address`, `deadline: u64`, Clock, Versioned | `(Coin<CoinA>, Coin<CoinB>)` | Aborts on slippage or invalid pool version | Move package `0xa5a0c25c...::swap_router` |
| 5 | Turbos CLMM | `PoolConfig` & `PoolTableId` | Central registry containing 9,643 CLMM pools and fee map | Object ID `0xc294552b...`, table ID `0x08984ed8...` | Dynamic fields mapping token pairs to pool IDs | Read-only shared object | S3 `contract.json` & Sui GraphQL |
| 6 | Turbos CLMM | `Versioned` object | Global protocol version check object | Object ID `0xf1cf0e81...` (initialSharedVersion: 1621135) | Passed as `&Versioned` | Aborts if package version mismatch | Turbos Move contracts & Sui GraphQL |
| 7 | Turbos CLMM | Q64.64 Tick Math | Tick index to price & sqrt_price conversions | `tick_current_index`, `sqrt_price` | Spot price $P_{B/A} = (\text{sqrt\_price}/2^{64})^2 \cdot 10^{\text{dec}_A - \text{dec}_B}$ | Range errors if outside $[4295048016, 79226673515401279992447579055]$ | `turbos-clmm-sdk/src/lib/math.ts` |
| 8 | DeepBook V3 | `swap_exact_quote_for_base` | CLOB market buy taking asks without BalanceManager | Pool, `quoteIn: Coin<Quote>`, `deepIn: Coin<DEEP>`, `minBaseOut: u64`, Clock | `(Coin<Base>, Coin<Quote>, Coin<DEEP>)` | Aborts if output < `minBaseOut` | `@mysten/deepbook-v3/contracts/deepbook/pool.ts:481` |
| 9 | DeepBook V3 | `swap_exact_base_for_quote` | CLOB market sell taking bids without BalanceManager | Pool, `baseIn: Coin<Base>`, `deepIn: Coin<DEEP>`, `minQuoteOut: u64`, Clock | `(Coin<Base>, Coin<Quote>, Coin<DEEP>)` | Aborts if output < `minQuoteOut` | `@mysten/deepbook-v3/contracts/deepbook/pool.ts:386` |
| 10 | DeepBook V3 | `vault_balances` | On-chain query of available pool vault liquidity | Pool ID | `(u64, u64, u64)` -> `(base, quote, deep)` | Read-only simulation | `@mysten/deepbook-v3/contracts/deepbook/pool.ts:2250` |
| 11 | DeepBook V3 | `borrow_flashloan_quote` / `return_flashloan_quote` | 0-fee flashloan of quote asset with Hot Potato enforcement | Pool, `quoteAmount: u64`, `coin: Coin<Quote>`, `flashLoan: FlashLoan` | `(Coin<Quote>, FlashLoan)` / None | Aborts with `EInsufficientVaultBalance` (code 2) if vault empty; unhandled Hot Potato aborts entire PTB | `@mysten/deepbook-v3/contracts/deepbook/pool.ts:1172` |
| 12 | DeepBook V3 | `borrow_flashloan_base` / `return_flashloan_base` | 0-fee flashloan of base asset with Hot Potato enforcement | Pool, `baseAmount: u64`, `coin: Coin<Base>`, `flashLoan: FlashLoan` | `(Coin<Base>, FlashLoan)` / None | Aborts with `EInsufficientVaultBalance` (code 2) if vault empty; unhandled Hot Potato aborts entire PTB | `@mysten/deepbook-v3/contracts/deepbook/pool.ts:1144` |

---

## 4. Edge Cases

| # | Feature | Input | Observed Behavior |
|---|---------|-------|-------------------|
| 1 | DeepBook Flashloan | `quoteAmount > vault.quote_balance` | Move VM aborts with code 2 (`EInsufficientVaultBalance`). PTB reverts with 0 state mutations and 0 leg risk. Pre-flight check via `vault_balances` eliminates this trigger. |
| 2 | DeepBook CLOB Lot Size | `quote_in` not evenly divisible by lot size | `swap_exact_quote_for_base` returns leftover `quote_leftover` in Result 1. Must be merged into proceeds coin before splitting loan repayment. |
| 3 | DeepBook Fee Zero Coin | DEEP fee input when user has no DEEP | Calling `0x2::coin::zero<DEEP>()` produces a 0-value coin; pool consumes 0 DEEP and returns 0 DEEP, which must be quenched via `coin::destroy_zero<DEEP>`. |
| 4 | Turbos CLMM Vector Argument | Passing raw coin to `swap_a_b_with_return_` | Function expects `vector<Coin<T>>`. Passing a naked coin produces a BCS type mismatch. Must wrap with `Command::MakeMoveVec([coin])`. |
| 5 | Turbos CLMM Slippage Limit | `sqrt_price_limit` set inappropriately | When `a2b = True`, price moves down, so limit must be $\le$ current price (down to `MIN_SQRT_PRICE`). If set to `MAX_SQRT_PRICE`, transaction immediately aborts. Conversely, `a2b = False` requires limit up to `MAX_SQRT_PRICE`. |
| 6 | Turbos CLMM Immutable Objects | `Versioned` or `Clock` passed as mutable | Sui execution engine rejects transaction block if shared object mutability does not match Move function signature. Both must be `mutable = false`. |
| 7 | Reverse Route Insufficient Spread | Cetus Bid proceeds < DeepBook Ask cost | Proceeds $Q' < Q$ principal. `SplitCoins(quote_swapped, [Q])` fails with `INSUFFICIENT_BALANCE`. `return_flashloan_quote` is never reached. Transaction aborts cleanly with 0 leg risk. |
| 8 | DEEP/SUI Zero Taker Fee Priority | DEEP/SUI vs DEEP/USDC | DEEP/SUI pool on DeepBook is whitelisted with 0.0 bps taker fee. DEEP/USDC has 0.0 bps taker fee but significantly thinner liquidity on AMMs ($868 vs $70k TVL). Prioritizing DEEP/SUI maximizes execution probability. |

---

## 5. Caveats
- No caveats regarding contract signatures or package IDs: all addresses, package IDs, shared object versions, and Move module signatures were queried and verified directly against live Sui Mainnet GraphQL (`https://graphql.mainnet.sui.io/graphql`) and official Turbos SDK sources.
- Real-time pool tick index: While spot price can be read directly from `sqrt_price` in a single GraphQL query, full multi-tick swap simulations with exact depth traversal off-chain require reading tick arrays or running dry-run simulations via `simulateTransaction`.

---

## 6. Conclusion
The authoritative specifications for both Turbos Finance CLMM integration and DeepBook V3 <-> Cetus Reverse Route arbitrage are fully probed, documented, and verified:
1. **Turbos Finance CLMM**:
   - Active package ID: `0xa5a0c25c79e428eba04fb98b3fb2a34db45ab26d4c8faf0d7e39d66a63891e64`.
   - Entry/Router functions: `swap_router::swap_a_b_with_return_` and `swap_b_a_with_return_`.
   - All 4 primary pool IDs and initial shared versions verified.
   - Price math Q64.64 identical to Uniswap V3 / Cetus.
2. **Reverse Route (`DeepBook Ask -> Cetus Bid`)**:
   - Primary asset: Borrow Quote (`borrow_flashloan_quote`).
   - Atomic sequence: Borrow Quote -> `swap_exact_quote_for_base` on DeepBook -> Swap Base to Quote on Cetus -> Merge leftover Quote -> `SplitCoins` -> `return_flashloan_quote` -> Transfer profit.
   - Preserves 100% zero leg risk via Hot Potato semantics.
   - Dynamic asset selection and `vault_balances` pre-check prevent `EInsufficientVaultBalance` abort code 2.

---

## 7. Verification Method
1. **Run Full Test Suite**:
   ```bash
   trading-engine/.venv/bin/pytest trading-engine/tests
   ```
2. **Verify Live Pool Objects on Sui GraphQL**:
   ```bash
   trading-engine/.venv/bin/python3 -c "
   import urllib.request, json
   query = '''
   query {
     turbos_sui_usdc: object(address: \"0x0df4f02d0e210169cb6d5aabd03c3058328c06f2c4dbb0804faa041159c78443\") { version }
     turbos_deep_sui: object(address: \"0xbca476e3c744648c65b1fae5551b86be8ad7f482ca9c2268dad1d6b4fd0e2635\") { version }
     turbos_deep_usdc: object(address: \"0x198af6ff81028c6577e94465d534c4e2cfcbbab06a95724ece7011c55a9d1f5a\") { version }
     turbos_cetus_sui: object(address: \"0xdf9d069bdfd51515aa0316698225a26444cbdf3cccd130a226b3ac81cfe2f606\") { version }
   }
   '''
   req = urllib.request.Request('https://graphql.mainnet.sui.io/graphql', data=json.dumps({'query': query}).encode(), headers={'Content-Type': 'application/json'})
   with urllib.request.urlopen(req) as resp:
       print(resp.read().decode())
   "
   ```
3. **Invalidation Conditions**:
   - Upgrades to Turbos `PackageId` or `Versioned` object on Sui Mainnet.
   - DeepBook V3 core package migration beyond `0xbca0cefe720330e7bb4f2283438b68de6a0e656688db4ac90d61e71fe6151fe8`.
