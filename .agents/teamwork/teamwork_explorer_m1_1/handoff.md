# Handoff Report: Milestone M1 — Multi-Pair Sui DeepBookV3 & Cetus AMM Atomic Flash Loan PTB Arbitrage Engine Blueprint

**Agent:** `teamwork_explorer_m1_1`  
**Working Directory:** `/Users/vitorhrds/Documents/Github/hypothesis/.agents/teamwork/teamwork_explorer_m1_1/`  
**Recipient / Caller:** `bb8c036e-693a-4192-a9f6-25494af55dae`  
**Milestone:** M1 — Multi-Pair Arbitrage Engine Blueprint  
**Date:** 2026-11-10T02:30:00Z  

---

## 1. Observation

1. **Existing Codebase State (`trading-engine/venues/sui_deepbook_venue.py`):**
   - Lines 35–46 currently configure only `SUI_USDC_POOL_ID` (`0xe05dafb5...`) and `DEEP_SUI_POOL_ID` (`0xb663828d...`), omitting `DEEP/USDC` and `CETUS/SUI`.
   - Lines 49–59 (`HotPotatoPTBParams`) hardcode default parameters to `SUI/USDC`.
   - Lines 70–207 (`build_atomic_arb_ptb`) hardcode `CETUS_POOL_SUI_USDC`, `type_arguments: [params.quote_coin_type, params.base_coin_type]`, and `a2b = True`.
   - Lines 276–280 (`simulate_dry_run`) hardcode scaling by `1e6` (USDC decimals), which breaks calculations for SUI-quote pairs (`DEEP/SUI` and `CETUS/SUI` having 9 decimals).

2. **On-Chain Verified Pool Move Types (Sui Mainnet GraphQL `https://graphql.mainnet.sui.io/graphql`):**
   - **DeepBookV3 Pools (`0x2c8d603b...` / `0xdee9`):**
     - `SUI/USDC`: `0x2c8d603b...::pool::Pool<0x2::sui::SUI, 0xdba346...::usdc::USDC>` (`0xe05dafb5...`)
     - `DEEP/SUI`: `0x2c8d603b...::pool::Pool<0xdeeb...::deep::DEEP, 0x2::sui::SUI>` (`0xb663828d...`)
     - `DEEP/USDC`: `0x2c8d603b...::pool::Pool<0xdeeb...::deep::DEEP, 0xdba346...::usdc::USDC>` (`0xf948981b...`)
     - `CETUS/SUI`: `0x2c8d603b...::pool::Pool<0x0686...::cetus::CETUS, 0x2::sui::SUI>` (`0xcf8d0d98...`)
   - **Cetus CLMM Pools (`0x1eabed72...`):**
     - `SUI/USDC`: `0x1eabed72...::pool::Pool<0xdba346...::usdc::USDC, 0x2::sui::SUI>` (`0x51e883ba...` 5 bps; `0xb8d7d9e6...` 25 bps) -> Coin A = USDC, Coin B = SUI.
     - `DEEP/SUI`: `0x1eabed72...::pool::Pool<0xdeeb...::deep::DEEP, 0x2::sui::SUI>` (`0xd978d331...` 5 bps; `0xe01243f3...` 25 bps) -> Coin A = DEEP, Coin B = SUI.
     - `DEEP/USDC`: `0x1eabed72...::pool::Pool<0xdeeb...::deep::DEEP, 0xdba346...::usdc::USDC>` (`0xa2f4e24d...` 5 bps) -> Coin A = DEEP, Coin B = USDC.
     - `CETUS/SUI`: `0x1eabed72...::pool::Pool<0x0686...::cetus::CETUS, 0x2::sui::SUI>` (`0x2e041f3f...` 25 bps) -> Coin A = CETUS, Coin B = SUI.

3. **Current Test Suite Invariants:**
   - `trading-engine/tests/test_venues_unit.py` (2/2 PASSED):
     - Line 366: `assert len(commands) == 8`
     - Line 370: `assert cmd0["function"] == "borrow_flashloan_quote"`
     - Line 376: `assert cmd1["function"] == "swap"`
     - Line 380: `assert cmd6["function"] == "return_flashloan_quote"`
     - Line 384: `assert cmd7["type"] == "TransferObjects"`
   - `trading-engine/tests/test_adversarial_challenger_2.py` (5/5 PASSED):
     - Line 95: `assert commands[0]["outputs"] == ["borrowed_quote_coin", "flash_loan_receipt"]`
     - Line 99: `assert commands[1]["arguments"][2] == {"NestedResult": [0, 0]}`
     - Line 116: `assert commands[6]["arguments"][1] == {"NestedResult": [5, 0]}`
     - Line 117: `assert commands[6]["arguments"][2] == {"NestedResult": [0, 1]}`

---

## 2. Logic Chain

1. **Observation 1 & 2:** DeepBookV3 and Cetus AMM represent coin pairs differently on-chain. In Cetus CLMM, `Pool<CoinA, CoinB>` requires that Move calls pass type arguments matching the pool's declared types:
   - For `SUI/USDC`: Coin A is USDC, Coin B is SUI. Quote (USDC) is Coin A. Buying SUI with USDC moves from Coin A to Coin B, meaning `a2b = True`, and `sqrt_price_limit = 4295048016` (minimum bound).
   - For `DEEP/SUI`: Coin A is DEEP, Coin B is SUI. Quote (SUI) is Coin B. Buying DEEP with SUI moves from Coin B to Coin A, meaning `a2b = False`, and `sqrt_price_limit = 79226673515401279992447579055` (maximum bound).
   - For `DEEP/USDC`: Coin A is DEEP, Coin B is USDC. Quote (USDC) is Coin B. Buying DEEP with USDC moves from Coin B to Coin A, meaning `a2b = False`, and `sqrt_price_limit = 79226673515401279992447579055`.
   - For `CETUS/SUI`: Coin A is CETUS, Coin B is SUI. Quote (SUI) is Coin B. Buying CETUS with SUI moves from Coin B to Coin A, meaning `a2b = False`, and `sqrt_price_limit = 79226673515401279992447579055`.
2. **Observation 3:** Existing unit and adversarial tests make explicit assertions on `commands[1]["arguments"][2]` and command names. Any refactor must preserve the exact positional arguments in `commands[1]` while substituting dynamic parameters.
3. **Deduction:** Defining a frozen dataclass `PairConfig` with a static dictionary `SUI_PAIRS_CONFIG` and adding `from_pair()` to `HotPotatoPTBParams` allows any of the 4 pairs to be instantiated with 1 line of code while maintaining 100% backward compatibility with all single-pair tests.
4. **Deduction on Zero Leg Risk:** In all 4 pairs, Command 5 splits exact borrowed principal $Q$ from proceeds $Q'$ using native `SplitCoins`. If $Q' < Q$, `SplitCoins` aborts with `InsufficientBalance`. Command 6 (`return_flashloan_quote`) is never reached, leaving the unconsumed `FlashLoan` Hot Potato. The Move VM automatically aborts the entire transaction block with zero state mutations and zero debt.

---

## 3. Caveats

1. **DeepBook Whitelisted vs Non-Whitelisted Pairs:**
   - `DEEP/SUI` and `DEEP/USDC` are whitelisted (0 bps fee).
   - `SUI/USDC` and `CETUS/SUI` are non-whitelisted (10 bps fee). Unless the operator stakes DEEP tokens in the `BalanceManager` to unlock fee tier reductions, the gross spread must exceed the Cetus fee (5 or 25 bps) + DeepBook taker fee (10 bps) to be net profitable.
2. **Quote Decimals Discrepancy:**
   - `SUI/USDC` and `DEEP/USDC` use USDC as quote (6 decimals, initial borrow = `1_000_000_000` = 1,000 USDC).
   - `DEEP/SUI` and `CETUS/SUI` use SUI as quote (9 decimals, initial borrow = `500_000_000_000` = 500 SUI, equivalent to ~$1,000 USD at $2.00/SUI). The scaling engine in Milestone M2 will track native USDC and convert equivalent SUI thresholds.
3. **Cetus Pool Selection (Fee Tiers):**
   - For `SUI/USDC` and `DEEP/SUI`, the primary pool is the 0.05% fee tier (`500`), which has the lowest taker friction. If liquidity is constrained, the 0.25% tier (`2500`) serves as a viable fallback.

---

## 4. Conclusion

Milestone M1 scope is fully designed, verified on-chain, and documented in `analysis.md`:
1. All 4 target pairs (`SUI/USDC`, `DEEP/SUI`, `DEEP/USDC`, `CETUS/SUI`) have verified pool IDs, coin types, decimals, fee tiers, tick/lot sizes, `a2b` flags, and `sqrt_price_limit` values.
2. `PairConfig` and `SUI_PAIRS_CONFIG` provide a clean static registry for the trading engine.
3. `HotPotatoPTBParams` and `SuiDeepBookPTBBuilder.build_atomic_arb_ptb` are generalized to construct the 8-command PTB for any of the 4 pairs while preserving full backward compatibility.
4. Exact Move package IDs and function signatures for both quote-borrowed and base-borrowed flash loans are documented.
5. Concrete code recommendations and test specifications are prepared for the Worker.

---

## 5. Verification Method

To verify the blueprint findings:

1. **Verify On-Chain Pool IDs and Types via Sui GraphQL:**
   ```bash
   python3 -c "
   import requests
   q = '''query { object(address: \"0xe05dafb5133bcffb8d59f4e12465dc0e9faeaa05e3e342a08fe135800e3e4407\") { asMoveObject { contents { type { repr } } } } }'''
   r = requests.post('https://graphql.mainnet.sui.io/graphql', json={'query': q})
   print(r.json())
   "
   ```
2. **Execute Current Unit Tests (Baseline 2/2 PASSED):**
   ```bash
   trading-engine/.venv/bin/pytest -v trading-engine/tests/test_venues_unit.py -k "sui"
   ```
3. **Execute Adversarial Stress Tests (Baseline 5/5 PASSED):**
   ```bash
   trading-engine/.venv/bin/pytest -v trading-engine/tests/test_adversarial_challenger_2.py -k "sui"
   ```
4. **Inspect Generated Blueprint:**
   View `/Users/vitorhrds/Documents/Github/hypothesis/.agents/teamwork/teamwork_explorer_m1_1/analysis.md`.
