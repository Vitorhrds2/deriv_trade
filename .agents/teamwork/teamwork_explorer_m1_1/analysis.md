# Technical Implementation Blueprint: Multi-Pair Sui DeepBookV3 & Cetus AMM Atomic Flash Loan PTB Arbitrage Engine

**Agent:** `teamwork_explorer_m1_1`  
**Working Directory:** `/Users/vitorhrds/Documents/Github/hypothesis/.agents/teamwork/teamwork_explorer_m1_1/`  
**Milestone:** M1 — Multi-Pair Arbitrage Engine Blueprint  
**Date:** 2026-11-10T02:28:00Z  

---

## 1. Executive Summary & Objective

The objective of Milestone M1 is to expand the existing single-pair connector in `trading-engine/venues/sui_deepbook_venue.py` into a robust, high-frequency multi-pair atomic arbitrage engine supporting all 4 target trading pairs on Sui Mainnet:
1. **SUI/USDC**
2. **DEEP/SUI**
3. **DEEP/USDC**
4. **CETUS/SUI**

Arbitrage execution relies on Sui's native **Hot Potato** flash loan semantics (0.0 bps fee from DeepBookV3) combined with an 8-command Programmable Transaction Block (PTB). By quenching the Hot Potato receipt only after extracting proceeds and splitting the principal repayment, the Move VM mathematically guarantees **zero leg risk**: any unprofitable execution reverts atomically with zero lingering debt and zero state mutations, consuming only nominal gas (~0.002 SUI / ~$0.004 USD).

This blueprint provides:
- The exact verified on-chain configuration dictionaries and dataclasses for all 4 pairs.
- Generalization of `HotPotatoPTBParams` and `SuiDeepBookPTBBuilder.build_atomic_arb_ptb`.
- Exact Move package IDs and function calls for both quote-borrowed and base-borrowed flash loans.
- Precise code edit recommendations for the implementation Worker.
- Specification for `trading-engine/tests/test_sui_deepbook_multipair.py`.

---

## 2. On-Chain Asset & Pool Configurations (All 4 Pairs)

### 2.1 Core Coin Types & Metadata

Every coin type was queried and verified on Sui Mainnet via GraphQL:

```python
# Fully qualified Move type identifiers
SUI_COIN_TYPE = "0x0000000000000000000000000000000000000000000000000000000000000002::sui::SUI"  # Short: "0x2::sui::SUI"
CIRCLE_USDC_TYPE = "0xdba34672e30cb065b1f93e3ab55318768fd6fef66c15942c9f7cb846e2f900e7::usdc::USDC"
DEEP_COIN_TYPE = "0xdeeb7a4662eec9f2f3def03fb937a663dddaa2e215b8078a284d026b7946c270::deep::DEEP"
CETUS_COIN_TYPE = "0x06864a6f921804860930db6ddbe2e16acdf8504495ea7481637a1c8b9a8fe54b::cetus::CETUS"
```

| Asset | Move Type Identifier | Decimals | Minimal Atomic Unit | Issuer / Standard |
|---|---|---|---|---|
| **SUI** | `0x2::sui::SUI` | 9 | 1 MIST ($10^{-9}$ SUI) | Native Sui Gas Coin |
| **USDC** | `0xdba34672...::usdc::USDC` | 6 | 1 Micro-USDC ($10^{-6}$ USDC) | Circle Native USDC |
| **DEEP** | `0xdeeb7a46...::deep::DEEP` | 6 | 1 Micro-DEEP ($10^{-6}$ DEEP) | DeepBook Protocol Token |
| **CETUS**| `0x06864a6f...::cetus::CETUS` | 9 | 1 Nano-CETUS ($10^{-9}$ CETUS) | Cetus Protocol Token |

---

### 2.2 DeepBookV3 Pool Specifications

- **Package ID:** `0xdee9` (Mainnet resolved: `0x2c8d603bc51326b8c13cef9dd07031a408a48dddb541963357661df5d3204809`)
- **Flash Loan Fee:** Exactly **0.0 bps** (`borrow_flashloan_quote` and `borrow_flashloan_base`)
- **Price Factor Formula:** $\text{Price Factor} = 10^{(9 - \text{Base Decimals} + \text{Quote Decimals})}$

| Pair | Pool Object ID | Base Asset | Quote Asset | Tick Size | Lot Size | Min Size | Taker Fee | Whitelisted | Price Factor |
|---|---|---|---|---|---|---|---|---|---|
| **SUI/USDC** | `0xe05dafb5133bcffb8d59f4e12465dc0e9faeaa05e3e342a08fe135800e3e4407` | SUI (9) | USDC (6) | 1,000 ($0.001) | 100,000,000 (0.1 SUI) | 1,000,000,000 (1 SUI) | 10 bps | False | $10^6$ |
| **DEEP/SUI** | `0xb663828d6217467c8a1838a03793da896cbe745b150ebd57d82f814ca579fc22` | DEEP (6) | SUI (9) | 10,000,000 ($0.01) | 10,000,000 (10 DEEP) | 100,000,000 (100 DEEP) | 0 bps | True | $10^{12}$ |
| **DEEP/USDC**| `0xf948981b806057580f91622417534f491da5f61aeaf33d0ed8e69fd5691c95ce` | DEEP (6) | USDC (6) | 10,000 ($0.01) | 10,000,000 (10 DEEP) | 100,000,000 (100 DEEP) | 0 bps | True | $10^9$ |
| **CETUS/SUI**| `0xcf8d0d98dd3c2ceaf40845f5260c620fa62b3a15380bc100053aecd6df8e5e7c` | CETUS (9) | SUI (9) | 10,000 ($0.00001)| 100,000,000 (0.1 CETUS) | 1,000,000,000 (1 CETUS) | 10 bps | False | $10^9$ |

---

### 2.3 Cetus AMM Pool Specifications & Asset Ordering

- **Cetus Core Package ID:** `0x1eabed72c53feb3805120a081dc15963c204dc8d091542592abaf7a35689b2fb`
- **Cetus Global Config:** `0xdaa46292632c3c4d8f31f23ea0f9b36a28ff3677e9684980e4438403a67a3d8f`
- **Sui Clock Object:** `0x0000000000000000000000000000000000000000000000000000000000000006` (`0x6`)
- **Sqrt Price Limits:**
  - `MIN_SQRT_PRICE = 4295048016` (used when `a2b = True`, price decreases)
  - `MAX_SQRT_PRICE = 79226673515401279992447579055` (used when `a2b = False`, price increases)

**Critical On-Chain Ordering Insight:**
In Cetus, the Move type `Pool<CoinA, CoinB>` is immutable. When calling `cetus_clmm::pool::swap<CoinA, CoinB>`, type arguments MUST be passed in the exact order `[CoinA, CoinB]`:

| Pair | Cetus Pool ID | Fee Rate (bps) | Coin A Type | Coin B Type | Quote Asset in Arb | Cetus Swap Direction for Quote $\to$ Base | `a2b` Flag | `sqrt_price_limit` |
|---|---|---|---|---|---|---|---|---|
| **SUI/USDC** | `0x51e883ba7c0b566a26cbc8a94cd33eb0abd418a77cc1e60ad22fd9b1f29cd2ab` | 500 (5 bps) | USDC | SUI | USDC (Coin A) | USDC $\to$ SUI | **`True`** | `4295048016` |
| **SUI/USDC (Alt)** | `0xb8d7d9e66a60c239e7a60110efcf8de6c705580ed924d0dde141f4a0e2c90105` | 2500 (25 bps) | USDC | SUI | USDC (Coin A) | USDC $\to$ SUI | **`True`** | `4295048016` |
| **DEEP/SUI** | `0xd978d331772a5b90d5a4781e1232d18afd12019d0c35db79e3674beeda8f9126` | 500 (5 bps) | DEEP | SUI | SUI (Coin B) | SUI $\to$ DEEP | **`False`** | `79226673515401279992447579055` |
| **DEEP/SUI (Alt)** | `0xe01243f37f712ef87e556afb9b1d03d0fae13f96d324ec912daffc339dfdcbd2` | 2500 (25 bps) | DEEP | SUI | SUI (Coin B) | SUI $\to$ DEEP | **`False`** | `79226673515401279992447579055` |
| **DEEP/USDC** | `0xa2f4e24dc234cf024bae1bd5b1275ab5bdc7c28dd1ec84dd98c2d012bbd315f0` | 500 (5 bps) | DEEP | USDC | USDC (Coin B) | USDC $\to$ DEEP | **`False`** | `79226673515401279992447579055` |
| **CETUS/SUI** | `0x2e041f3fd93646dcc877f783c1f2b7fa62d30271bdef1f21ef002cebf857bded` | 2500 (25 bps) | CETUS | SUI | SUI (Coin B) | SUI $\to$ CETUS | **`False`** | `79226673515401279992447579055` |

---

### 2.4 Data Structure Design: `PairConfig` & Registry

```python
from dataclasses import dataclass
from typing import Dict

@dataclass(frozen=True)
class PairConfig:
    """Static configuration parameters for a Sui DeepBookV3 and Cetus AMM trading pair."""
    pair_name: str
    base_symbol: str
    quote_symbol: str
    base_coin_type: str
    quote_coin_type: str
    base_decimals: int
    quote_decimals: int
    deepbook_pool_id: str
    cetus_pool_id: str
    cetus_coin_a_type: str
    cetus_coin_b_type: str
    cetus_a2b_for_quote_in: bool
    cetus_sqrt_price_limit_quote_in: int
    deepbook_tick_size: int
    deepbook_lot_size: int
    deepbook_min_size: int
    deepbook_taker_fee_bps: float
    deepbook_whitelisted: bool
    cetus_fee_bps: float
    default_borrow_amount: int
    price_factor: int


# Global static registry for all 4 pairs
SUI_PAIRS_CONFIG: Dict[str, PairConfig] = {
    "SUI/USDC": PairConfig(
        pair_name="SUI/USDC",
        base_symbol="SUI",
        quote_symbol="USDC",
        base_coin_type=SUI_COIN_TYPE,
        quote_coin_type=CIRCLE_USDC_TYPE,
        base_decimals=9,
        quote_decimals=6,
        deepbook_pool_id=SUI_USDC_POOL_ID,
        cetus_pool_id="0x51e883ba7c0b566a26cbc8a94cd33eb0abd418a77cc1e60ad22fd9b1f29cd2ab",  # 0.05%
        cetus_coin_a_type=CIRCLE_USDC_TYPE,
        cetus_coin_b_type=SUI_COIN_TYPE,
        cetus_a2b_for_quote_in=True,
        cetus_sqrt_price_limit_quote_in=4295048016,
        deepbook_tick_size=1_000,
        deepbook_lot_size=100_000_000,
        deepbook_min_size=1_000_000_000,
        deepbook_taker_fee_bps=10.0,
        deepbook_whitelisted=False,
        cetus_fee_bps=5.0,
        default_borrow_amount=1_000_000_000,  # 1,000 USDC
        price_factor=1_000_000,
    ),
    "DEEP/SUI": PairConfig(
        pair_name="DEEP/SUI",
        base_symbol="DEEP",
        quote_symbol="SUI",
        base_coin_type=DEEP_COIN_TYPE,
        quote_coin_type=SUI_COIN_TYPE,
        base_decimals=6,
        quote_decimals=9,
        deepbook_pool_id=DEEP_SUI_POOL_ID,
        cetus_pool_id="0xd978d331772a5b90d5a4781e1232d18afd12019d0c35db79e3674beeda8f9126",  # 0.05%
        cetus_coin_a_type=DEEP_COIN_TYPE,
        cetus_coin_b_type=SUI_COIN_TYPE,
        cetus_a2b_for_quote_in=False,
        cetus_sqrt_price_limit_quote_in=79226673515401279992447579055,
        deepbook_tick_size=10_000_000,
        deepbook_lot_size=10_000_000,
        deepbook_min_size=100_000_000,
        deepbook_taker_fee_bps=0.0,
        deepbook_whitelisted=True,
        cetus_fee_bps=5.0,
        default_borrow_amount=500_000_000_000,  # 500 SUI (~$1,000 at $2.00/SUI)
        price_factor=1_000_000_000_000,
    ),
    "DEEP/USDC": PairConfig(
        pair_name="DEEP/USDC",
        base_symbol="DEEP",
        quote_symbol="USDC",
        base_coin_type=DEEP_COIN_TYPE,
        quote_coin_type=CIRCLE_USDC_TYPE,
        base_decimals=6,
        quote_decimals=6,
        deepbook_pool_id="0xf948981b806057580f91622417534f491da5f61aeaf33d0ed8e69fd5691c95ce",
        cetus_pool_id="0xa2f4e24dc234cf024bae1bd5b1275ab5bdc7c28dd1ec84dd98c2d012bbd315f0",  # 0.05%
        cetus_coin_a_type=DEEP_COIN_TYPE,
        cetus_coin_b_type=CIRCLE_USDC_TYPE,
        cetus_a2b_for_quote_in=False,
        cetus_sqrt_price_limit_quote_in=79226673515401279992447579055,
        deepbook_tick_size=10_000,
        deepbook_lot_size=10_000_000,
        deepbook_min_size=100_000_000,
        deepbook_taker_fee_bps=0.0,
        deepbook_whitelisted=True,
        cetus_fee_bps=5.0,
        default_borrow_amount=1_000_000_000,  # 1,000 USDC
        price_factor=1_000_000_000,
    ),
    "CETUS/SUI": PairConfig(
        pair_name="CETUS/SUI",
        base_symbol="CETUS",
        quote_symbol="SUI",
        base_coin_type=CETUS_COIN_TYPE,
        quote_coin_type=SUI_COIN_TYPE,
        base_decimals=9,
        quote_decimals=9,
        deepbook_pool_id="0xcf8d0d98dd3c2ceaf40845f5260c620fa62b3a15380bc100053aecd6df8e5e7c",
        cetus_pool_id="0x2e041f3fd93646dcc877f783c1f2b7fa62d30271bdef1f21ef002cebf857bded",  # 0.25%
        cetus_coin_a_type=CETUS_COIN_TYPE,
        cetus_coin_b_type=SUI_COIN_TYPE,
        cetus_a2b_for_quote_in=False,
        cetus_sqrt_price_limit_quote_in=79226673515401279992447579055,
        deepbook_tick_size=10_000,
        deepbook_lot_size=100_000_000,
        deepbook_min_size=1_000_000_000,
        deepbook_taker_fee_bps=10.0,
        deepbook_whitelisted=False,
        cetus_fee_bps=25.0,
        default_borrow_amount=500_000_000_000,  # 500 SUI (~$1,000 at $2.00/SUI)
        price_factor=1_000_000_000,
    ),
}
```

---

## 3. Generalization of `HotPotatoPTBParams` & `SuiDeepBookPTBBuilder`

### 3.1 Generalized `HotPotatoPTBParams` Dataclass

To maintain **100% backward compatibility** with all existing tests while fully enabling any of the 4 pairs, `HotPotatoPTBParams` provides sensible default values matching `SUI/USDC` and includes a factory classmethod `from_pair()`:

```python
@dataclass
class HotPotatoPTBParams:
    """Parameters for constructing an atomic DeepBookV3 Hot Potato arbitrage PTB across any pair."""
    pair_name: str = "SUI/USDC"
    pool_id: str = SUI_USDC_POOL_ID
    cetus_pool_id: str = CETUS_POOL_SUI_USDC
    base_coin_type: str = SUI_COIN_TYPE
    quote_coin_type: str = CIRCLE_USDC_TYPE
    cetus_coin_a_type: str = CIRCLE_USDC_TYPE
    cetus_coin_b_type: str = SUI_COIN_TYPE
    flash_borrow_amount: int = 1_000_000_000   # 1,000 USDC default
    min_repay_amount: int = 1_000_000_000      # 0 bps fee: exact principal repayment
    a2b: bool = True                           # Cetus swap direction (Quote -> Base)
    sqrt_price_limit: int = 4295048016         # MIN_SQRT_PRICE for a2b=True
    amm_target: str = "cetus"                  # "cetus" | "turbos"
    borrow_asset: str = "quote"                # "quote" | "base"
    balance_manager_id: str = "0x0000000000000000000000000000000000000000000000000000000000000001"
    sender_address: str = "0x5621a8e7199680512ee829565b96febea2587e534fd69b33f04004298d7e5ce9"

    @classmethod
    def from_pair(
        cls,
        pair_name: str,
        flash_borrow_amount: Optional[int] = None,
        balance_manager_id: Optional[str] = None,
        sender_address: Optional[str] = None,
        cetus_pool_id: Optional[str] = None,
        borrow_asset: str = "quote",
    ) -> HotPotatoPTBParams:
        """Constructs params automatically configured from the global pair registry."""
        if pair_name not in SUI_PAIRS_CONFIG:
            raise ValueError(f"Unknown pair: {pair_name}. Supported: {list(SUI_PAIRS_CONFIG.keys())}")
        
        cfg = SUI_PAIRS_CONFIG[pair_name]
        borrow_amt = flash_borrow_amount if flash_borrow_amount is not None else cfg.default_borrow_amount
        cetus_pid = cetus_pool_id or cfg.cetus_pool_id
        
        # When borrowing Quote to buy Base on Cetus:
        if borrow_asset == "quote":
            a2b = cfg.cetus_a2b_for_quote_in
            sqrt_limit = cfg.cetus_sqrt_price_limit_quote_in
        else: # borrowing Base to sell on Cetus: direction flips
            a2b = not cfg.cetus_a2b_for_quote_in
            sqrt_limit = 79226673515401279992447579055 if a2b else 4295048016

        return cls(
            pair_name=pair_name,
            pool_id=cfg.deepbook_pool_id,
            cetus_pool_id=cetus_pid,
            base_coin_type=cfg.base_coin_type,
            quote_coin_type=cfg.quote_coin_type,
            cetus_coin_a_type=cfg.cetus_coin_a_type,
            cetus_coin_b_type=cfg.cetus_coin_b_type,
            flash_borrow_amount=borrow_amt,
            min_repay_amount=borrow_amt,
            a2b=a2b,
            sqrt_price_limit=sqrt_limit,
            amm_target="cetus",
            borrow_asset=borrow_asset,
            balance_manager_id=balance_manager_id or "0x0000000000000000000000000000000000000000000000000000000000000001",
            sender_address=sender_address or "0x5621a8e7199680512ee829565b96febea2587e534fd69b33f04004298d7e5ce9",
        )
```

---

### 3.2 The Generalized 8-Command Move PTB Execution Pipeline

The 8-command PTB pipeline executes in a single transaction block. The sequence is detailed below:

```
+----------------------------------------------------------------------------------------------------+
|                               8-COMMAND ATOMIC MOVE PTB PIPELINE                                   |
+----------------------------------------------------------------------------------------------------+
| Command 0: 0xdee9::pool::borrow_flashloan_quote                                                    |
|            TypeArgs: [Base, Quote]                                                                 |
|            Returns:  [borrowed_quote_coin, flash_loan_receipt (Hot Potato)]                        |
|                                                                                                    |
| Command 1: cetus_clmm::pool::swap                                                                  |
|            TypeArgs: [CoinA, CoinB] (Strictly Cetus Pool order)                                    |
|            Args:     [Config, CetusPool, borrowed_coin (NestedResult 0,0), a2b, exact_in, amount,  |
|                       sqrt_price_limit]                                                            |
|            Returns:  [swapped_base_coin]                                                           |
|                                                                                                    |
| Command 2: 0xdee9::balance_manager::deposit                                                        |
|            TypeArgs: [Base]                                                                        |
|            Args:     [balance_manager_id, swapped_base_coin (NestedResult 1,0)]                    |
|                                                                                                    |
| Command 3: 0xdee9::pool::place_market_order                                                        |
|            TypeArgs: [Base, Quote]                                                                 |
|            Args:     [pool_id, balance_manager_id, client_order_id=0, order_type=2, is_bid=False]   |
|            Action:   Sells swapped base tokens on DeepBook CLOB; credits quote proceeds Q' to BM   |
|                                                                                                    |
| Command 4: 0xdee9::balance_manager::withdraw_all                                                   |
|            TypeArgs: [Quote]                                                                       |
|            Args:     [balance_manager_id]                                                          |
|            Returns:  [withdrawn_quote_coin (proceeds Q')]                                          |
|                                                                                                    |
| Command 5: SplitCoins (Sui Native Command)                                                         |
|            Coin:     withdrawn_quote_coin (NestedResult 4,0)                                       |
|            Amounts:  [min_repay_amount Q]                                                          |
|            Returns:  [repay_quote_coin]                                                            |
|            *** REVERSION GATE: If Q' < Q, SplitCoins ABORTS with InsufficientBalance! ***          |
|                                                                                                    |
| Command 6: 0xdee9::pool::return_flashloan_quote                                                    |
|            TypeArgs: [Base, Quote]                                                                 |
|            Args:     [pool_id, repay_quote_coin (NestedResult 5,0), receipt (NestedResult 0,1)]     |
|            Action:   Quenches Hot Potato struct; clears Move ability invariant                     |
|                                                                                                    |
| Command 7: TransferObjects (Sui Native Command)                                                    |
|            Objects:  [residual_profit_coin (NestedResult 4,0)]                                     |
|            Recipient: sender_address                                                               |
+----------------------------------------------------------------------------------------------------+
```

---

## 4. Move Package IDs & Function Signatures

### 4.1 DeepBookV3 Flash Loan Functions (`0xdee9::pool`)

#### Quote-Borrowed Flash Loan:
```move
// 1. Borrow quote tokens at 0.0 bps fee
public fun borrow_flashloan_quote<Base, Quote>(
    pool: &mut Pool<Base, Quote>,
    amount: u64,
    ctx: &mut TxContext
): (Coin<Quote>, FlashLoan)

// 2. Return quote tokens, destroying Hot Potato receipt
public fun return_flashloan_quote<Base, Quote>(
    pool: &mut Pool<Base, Quote>,
    coin: Coin<Quote>,
    loan: FlashLoan
)
```

#### Base-Borrowed Flash Loan:
```move
// 1. Borrow base tokens at 0.0 bps fee
public fun borrow_flashloan_base<Base, Quote>(
    pool: &mut Pool<Base, Quote>,
    amount: u64,
    ctx: &mut TxContext
): (Coin<Base>, FlashLoan)

// 2. Return base tokens, destroying Hot Potato receipt
public fun return_flashloan_base<Base, Quote>(
    pool: &mut Pool<Base, Quote>,
    coin: Coin<Base>,
    loan: FlashLoan
)
```

**Hot Potato Move Definition:**
```move
public struct FlashLoan {
    pool_id: ID,
    borrow_quantity: u64,
    type_asset: u8,
}
```
*Because `FlashLoan` has **no abilities** (`drop`, `copy`, `store`, `key`), the Move VM mandates that every constructed `FlashLoan` MUST be consumed before transaction completion. If Command 5 fails due to insufficient balance, Command 6 is never reached, and the VM aborts the entire transaction block without committing any state changes.*

---

### 4.2 DeepBookV3 BalanceManager Functions (`0xdee9::balance_manager`)

```move
public fun deposit<T>(
    balance_manager: &mut BalanceManager,
    coin: Coin<T>
)

public fun withdraw_all<T>(
    balance_manager: &mut BalanceManager
): Coin<T>

public fun withdraw<T>(
    balance_manager: &mut BalanceManager,
    amount: u64,
    ctx: &mut TxContext
): Coin<T>
```

---

### 4.3 Cetus CLMM Swap Function (`cetus_clmm::pool::swap`)

- **Package:** `0x1eabed72c53feb3805120a081dc15963c204dc8d091542592abaf7a35689b2fb` (aliased as `"cetus_clmm"`)
- **Module:** `pool`
- **Function:** `swap`
- **Type Arguments:** `[CoinA, CoinB]` (Must match Cetus pool creation order)
- **Signature:**
```move
public fun swap<CoinA, CoinB>(
    config: &GlobalConfig,
    pool: &mut Pool<CoinA, CoinB>,
    coin_in: Coin<InputCoin>,
    a2b: bool,
    by_amount_in: bool,
    amount: u64,
    sqrt_price_limit: u128,
    has_amount_limit: bool,
    clock: &Clock,
    ctx: &mut TxContext
): (Coin<CoinA>, Coin<CoinB>)
```

---

## 5. Precise Code Modification Recommendations for Worker

The worker will update `trading-engine/venues/sui_deepbook_venue.py`. Below are the exact before/after implementations required:

### 5.1 Constants and Configuration Dictionary Addition

**Target:** `trading-engine/venues/sui_deepbook_venue.py` (lines 35–46)

```python
# --- BEFORE ---
DEEPBOOK_PACKAGE_ID = "0xdee9"
CIRCLE_USDC_TYPE = "0xdba34672e30cb065b1f93e3ab55318768fd6fef66c15942c9f7cb846e2f900e7::usdc::USDC"
SUI_COIN_TYPE = "0x2::sui::SUI"
DEEP_COIN_TYPE = "0xdeeb7a4662eec9f2f3def03fb937a663dddaa2e215b8078a284d026b7946c270::deep::DEEP"

# Active high-liquidity pools
SUI_USDC_POOL_ID = "0xe05dafb5133bcffb8d59f4e12465dc0e9faeaa05e3e342a08fe135800e3e4407"
DEEP_SUI_POOL_ID = "0xb663828d6217467c8a1838a03793da896cbe745b150ebd57d82f814ca579fc22"

CETUS_GLOBAL_CONFIG_ID = "0xdaa46292632c3c4d8f31f23ea0f9b36a28ff3677e9684980e4438403a67a3d8f"
CETUS_POOL_SUI_USDC = "0xcf994611fd4c48e277d3424d8be4910cfab579488e0e64c8d5fe55dbb320875e"
```

```python
# --- AFTER ---
DEEPBOOK_PACKAGE_ID = "0xdee9"
CIRCLE_USDC_TYPE = "0xdba34672e30cb065b1f93e3ab55318768fd6fef66c15942c9f7cb846e2f900e7::usdc::USDC"
SUI_COIN_TYPE = "0x0000000000000000000000000000000000000000000000000000000000000002::sui::SUI"
SUI_COIN_SHORT_TYPE = "0x2::sui::SUI"
DEEP_COIN_TYPE = "0xdeeb7a4662eec9f2f3def03fb937a663dddaa2e215b8078a284d026b7946c270::deep::DEEP"
CETUS_COIN_TYPE = "0x06864a6f921804860930db6ddbe2e16acdf8504495ea7481637a1c8b9a8fe54b::cetus::CETUS"

# Cetus Protocols & Bounds
CETUS_GLOBAL_CONFIG_ID = "0xdaa46292632c3c4d8f31f23ea0f9b36a28ff3677e9684980e4438403a67a3d8f"
CETUS_CORE_PACKAGE_ID = "0x1eabed72c53feb3805120a081dc15963c204dc8d091542592abaf7a35689b2fb"
SUI_CLOCK_OBJECT_ID = "0x0000000000000000000000000000000000000000000000000000000000000006"
MIN_SQRT_PRICE = 4295048016
MAX_SQRT_PRICE = 79226673515401279992447579055

# Active high-liquidity DeepBookV3 Pools
SUI_USDC_POOL_ID = "0xe05dafb5133bcffb8d59f4e12465dc0e9faeaa05e3e342a08fe135800e3e4407"
DEEP_SUI_POOL_ID = "0xb663828d6217467c8a1838a03793da896cbe745b150ebd57d82f814ca579fc22"
DEEP_USDC_POOL_ID = "0xf948981b806057580f91622417534f491da5f61aeaf33d0ed8e69fd5691c95ce"
CETUS_SUI_POOL_ID = "0xcf8d0d98dd3c2ceaf40845f5260c620fa62b3a15380bc100053aecd6df8e5e7c"

# Active Cetus Pools
CETUS_POOL_SUI_USDC = "0x51e883ba7c0b566a26cbc8a94cd33eb0abd418a77cc1e60ad22fd9b1f29cd2ab"  # 0.05%
CETUS_POOL_SUI_USDC_25 = "0xb8d7d9e66a60c239e7a60110efcf8de6c705580ed924d0dde141f4a0e2c90105"  # 0.25%
CETUS_POOL_DEEP_SUI = "0xd978d331772a5b90d5a4781e1232d18afd12019d0c35db79e3674beeda8f9126"  # 0.05%
CETUS_POOL_DEEP_USDC = "0xa2f4e24dc234cf024bae1bd5b1275ab5bdc7c28dd1ec84dd98c2d012bbd315f0"  # 0.05%
CETUS_POOL_CETUS_SUI = "0x2e041f3fd93646dcc877f783c1f2b7fa62d30271bdef1f21ef002cebf857bded"  # 0.25%


@dataclass(frozen=True)
class PairConfig:
    pair_name: str
    base_symbol: str
    quote_symbol: str
    base_coin_type: str
    quote_coin_type: str
    base_decimals: int
    quote_decimals: int
    deepbook_pool_id: str
    cetus_pool_id: str
    cetus_coin_a_type: str
    cetus_coin_b_type: str
    cetus_a2b_for_quote_in: bool
    cetus_sqrt_price_limit_quote_in: int
    deepbook_tick_size: int
    deepbook_lot_size: int
    deepbook_min_size: int
    deepbook_taker_fee_bps: float
    deepbook_whitelisted: bool
    cetus_fee_bps: float
    default_borrow_amount: int
    price_factor: int


SUI_PAIRS_CONFIG: Dict[str, PairConfig] = {
    "SUI/USDC": PairConfig(
        pair_name="SUI/USDC",
        base_symbol="SUI",
        quote_symbol="USDC",
        base_coin_type=SUI_COIN_SHORT_TYPE,
        quote_coin_type=CIRCLE_USDC_TYPE,
        base_decimals=9,
        quote_decimals=6,
        deepbook_pool_id=SUI_USDC_POOL_ID,
        cetus_pool_id=CETUS_POOL_SUI_USDC,
        cetus_coin_a_type=CIRCLE_USDC_TYPE,
        cetus_coin_b_type=SUI_COIN_SHORT_TYPE,
        cetus_a2b_for_quote_in=True,
        cetus_sqrt_price_limit_quote_in=MIN_SQRT_PRICE,
        deepbook_tick_size=1_000,
        deepbook_lot_size=100_000_000,
        deepbook_min_size=1_000_000_000,
        deepbook_taker_fee_bps=10.0,
        deepbook_whitelisted=False,
        cetus_fee_bps=5.0,
        default_borrow_amount=1_000_000_000,
        price_factor=1_000_000,
    ),
    "DEEP/SUI": PairConfig(
        pair_name="DEEP/SUI",
        base_symbol="DEEP",
        quote_symbol="SUI",
        base_coin_type=DEEP_COIN_TYPE,
        quote_coin_type=SUI_COIN_SHORT_TYPE,
        base_decimals=6,
        quote_decimals=9,
        deepbook_pool_id=DEEP_SUI_POOL_ID,
        cetus_pool_id=CETUS_POOL_DEEP_SUI,
        cetus_coin_a_type=DEEP_COIN_TYPE,
        cetus_coin_b_type=SUI_COIN_SHORT_TYPE,
        cetus_a2b_for_quote_in=False,
        cetus_sqrt_price_limit_quote_in=MAX_SQRT_PRICE,
        deepbook_tick_size=10_000_000,
        deepbook_lot_size=10_000_000,
        deepbook_min_size=100_000_000,
        deepbook_taker_fee_bps=0.0,
        deepbook_whitelisted=True,
        cetus_fee_bps=5.0,
        default_borrow_amount=500_000_000_000,
        price_factor=1_000_000_000_000,
    ),
    "DEEP/USDC": PairConfig(
        pair_name="DEEP/USDC",
        base_symbol="DEEP",
        quote_symbol="USDC",
        base_coin_type=DEEP_COIN_TYPE,
        quote_coin_type=CIRCLE_USDC_TYPE,
        base_decimals=6,
        quote_decimals=6,
        deepbook_pool_id=DEEP_USDC_POOL_ID,
        cetus_pool_id=CETUS_POOL_DEEP_USDC,
        cetus_coin_a_type=DEEP_COIN_TYPE,
        cetus_coin_b_type=CIRCLE_USDC_TYPE,
        cetus_a2b_for_quote_in=False,
        cetus_sqrt_price_limit_quote_in=MAX_SQRT_PRICE,
        deepbook_tick_size=10_000,
        deepbook_lot_size=10_000_000,
        deepbook_min_size=100_000_000,
        deepbook_taker_fee_bps=0.0,
        deepbook_whitelisted=True,
        cetus_fee_bps=5.0,
        default_borrow_amount=1_000_000_000,
        price_factor=1_000_000_000,
    ),
    "CETUS/SUI": PairConfig(
        pair_name="CETUS/SUI",
        base_symbol="CETUS",
        quote_symbol="SUI",
        base_coin_type=CETUS_COIN_TYPE,
        quote_coin_type=SUI_COIN_SHORT_TYPE,
        base_decimals=9,
        quote_decimals=9,
        deepbook_pool_id=CETUS_SUI_POOL_ID,
        cetus_pool_id=CETUS_POOL_CETUS_SUI,
        cetus_coin_a_type=CETUS_COIN_TYPE,
        cetus_coin_b_type=SUI_COIN_SHORT_TYPE,
        cetus_a2b_for_quote_in=False,
        cetus_sqrt_price_limit_quote_in=MAX_SQRT_PRICE,
        deepbook_tick_size=10_000,
        deepbook_lot_size=100_000_000,
        deepbook_min_size=1_000_000_000,
        deepbook_taker_fee_bps=10.0,
        deepbook_whitelisted=False,
        cetus_fee_bps=25.0,
        default_borrow_amount=500_000_000_000,
        price_factor=1_000_000_000,
    ),
}
```

---

### 5.2 `SuiDeepBookPTBBuilder.build_atomic_arb_ptb` Implementation

**Target:** `trading-engine/venues/sui_deepbook_venue.py` (lines 70–207)

```python
    def build_atomic_arb_ptb(self, params: HotPotatoPTBParams) -> Dict[str, Any]:
        """Builds serialized representation of the 8 Move PTB commands across any configured pair."""
        commands: List[Dict[str, Any]] = []

        is_quote_borrow = (params.borrow_asset == "quote")
        borrow_fn = "borrow_flashloan_quote" if is_quote_borrow else "borrow_flashloan_base"
        repay_fn = "return_flashloan_quote" if is_quote_borrow else "return_flashloan_base"
        borrow_out_label = "borrowed_quote_coin" if is_quote_borrow else "borrowed_base_coin"

        # Command 0: Borrow Quote Coin via DeepBook Flash Loan (0.0% fee)
        commands.append({
            "command_index": 0,
            "type": "MoveCall",
            "package": DEEPBOOK_PACKAGE_ID,
            "module": "pool",
            "function": borrow_fn,
            "type_arguments": [params.base_coin_type, params.quote_coin_type],
            "arguments": [
                {"Input": params.pool_id},
                {"Input": params.flash_borrow_amount},
            ],
            "outputs": [borrow_out_label, "flash_loan_receipt"],
            "description": f"Borrow {params.pair_name.split('/')[1] if is_quote_borrow else params.pair_name.split('/')[0]} with 0 bps fee; produce Hot Potato receipt",
        })

        # Command 1: Swap borrowed coin on AMM (Cetus)
        # Type arguments MUST match Cetus pool declaration [CoinA, CoinB]
        cetus_type_args = [params.cetus_coin_a_type, params.cetus_coin_b_type]
        commands.append({
            "command_index": 1,
            "type": "MoveCall",
            "package": "cetus_clmm" if params.amm_target == "cetus" else "turbos_clmm",
            "module": "pool",
            "function": "swap",
            "type_arguments": cetus_type_args,
            "arguments": [
                {"Input": CETUS_GLOBAL_CONFIG_ID},
                {"Input": params.cetus_pool_id},
                {"NestedResult": [0, 0]},  # borrowed coin from Command 0
                {"Input": params.a2b},     # a2b direction
                {"Input": True},           # exact_input
                {"Input": params.flash_borrow_amount},
                {"Input": params.sqrt_price_limit},
            ],
            "outputs": ["swapped_base_coin" if is_quote_borrow else "swapped_quote_coin"],
            "description": f"Swap on Cetus AMM for {params.pair_name}",
        })

        # Command 2: Deposit swapped base coin into DeepBook Balance Manager
        deposit_coin_type = params.base_coin_type if is_quote_borrow else params.quote_coin_type
        commands.append({
            "command_index": 2,
            "type": "MoveCall",
            "package": DEEPBOOK_PACKAGE_ID,
            "module": "balance_manager",
            "function": "deposit",
            "type_arguments": [deposit_coin_type],
            "arguments": [
                {"Input": params.balance_manager_id},
                {"NestedResult": [1, 0]},  # swapped coin from Command 1
            ],
            "outputs": [],
            "description": f"Deposit swapped token to Balance Manager for CLOB settlement",
        })

        # Command 3: Place Market Order on DeepBook CLOB
        # is_bid = False (Sell base for quote) when quote was borrowed
        # is_bid = True (Buy base with quote) when base was borrowed
        commands.append({
            "command_index": 3,
            "type": "MoveCall",
            "package": DEEPBOOK_PACKAGE_ID,
            "module": "pool",
            "function": "place_market_order",
            "type_arguments": [params.base_coin_type, params.quote_coin_type],
            "arguments": [
                {"Input": params.pool_id},
                {"Input": params.balance_manager_id},
                {"Input": 0},  # Client order id
                {"Input": 2},  # Market order type
                {"Input": not is_quote_borrow},  # is_bid = False for Ask, True for Bid
            ],
            "outputs": ["fill_summary"],
            "description": f"Execute market order on DeepBook CLOB ({'Ask' if is_quote_borrow else 'Bid'})",
        })

        # Command 4: Withdraw accumulated proceeds from Balance Manager
        withdraw_coin_type = params.quote_coin_type if is_quote_borrow else params.base_coin_type
        commands.append({
            "command_index": 4,
            "type": "MoveCall",
            "package": DEEPBOOK_PACKAGE_ID,
            "module": "balance_manager",
            "function": "withdraw_all",
            "type_arguments": [withdraw_coin_type],
            "arguments": [
                {"Input": params.balance_manager_id},
            ],
            "outputs": ["withdrawn_proceeds_coin"],
            "description": "Withdraw proceeds Q' from Balance Manager",
        })

        # Command 5: Split coin for exact flash loan repayment
        commands.append({
            "command_index": 5,
            "type": "SplitCoins",
            "coin": {"NestedResult": [4, 0]},  # withdrawn_proceeds_coin
            "amounts": [{"Input": params.min_repay_amount}],
            "outputs": ["repay_coin"],
            "description": "Split exact repayment principal from proceeds",
        })

        # Command 6: Return flash loan coin, satisfying Hot Potato struct
        commands.append({
            "command_index": 6,
            "type": "MoveCall",
            "package": DEEPBOOK_PACKAGE_ID,
            "module": "pool",
            "function": repay_fn,
            "type_arguments": [params.base_coin_type, params.quote_coin_type],
            "arguments": [
                {"Input": params.pool_id},
                {"NestedResult": [5, 0]},  # repay_coin
                {"NestedResult": [0, 1]},  # flash_loan_receipt (Hot Potato)
            ],
            "outputs": [],
            "description": "Consume Hot Potato; repay flash loan at 0% fee",
        })

        # Command 7: Transfer remaining profit coin Delta Q to operator
        commands.append({
            "command_index": 7,
            "type": "TransferObjects",
            "objects": [{"NestedResult": [4, 0]}],  # remaining profit
            "recipient": {"Input": params.sender_address},
            "description": "Transfer net arbitrage profit to sender wallet",
        })

        ptb_payload = {
            "version": 1,
            "pair": params.pair_name,
            "sender": params.sender_address,
            "gas_budget": 50_000_000,  # 0.05 SUI max gas budget
            "gas_price": 1000,
            "commands": commands,
            "is_atomic": True,
            "hot_potato_guarantee": True,
        }
        return ptb_payload
```

---

### 5.3 Multi-Pair Simulation & Execution Enhancement in `SuiDeepBookVenue`

**Target:** `trading-engine/venues/sui_deepbook_venue.py` (`simulate_dry_run` & `submit_order`)

```python
    def simulate_dry_run(
        self,
        ptb: Dict[str, Any],
        deepbook_bid_px: float,
        amm_swap_out_px: float,
        borrow_amount: int = 100_000_000,
        pair_name: str = "SUI/USDC",
    ) -> Dict[str, Any]:
        """Simulates Sui Move VM `sui_dryRunTransactionBlock` execution across any of the 4 pairs."""
        cfg = SUI_PAIRS_CONFIG.get(pair_name, SUI_PAIRS_CONFIG["SUI/USDC"])
        quote_scale = 10 ** cfg.quote_decimals

        # Step 1: Swap Q quote coins for S base coins at AMM price
        base_coins_acquired = (borrow_amount / quote_scale) / amm_swap_out_px

        # Step 4: Sell S base coins on DeepBook at bid price
        proceeds_quote = (base_coins_acquired * deepbook_bid_px) * quote_scale

        gas_cost_sui = 0.002
        gas_used_mist = 2_000_000

        if proceeds_quote < borrow_amount:
            return {
                "status": "ABORTED",
                "error": "MoveAbort(balance_manager::withdraw, INSUFFICIENT_BALANCE_FOR_REPAYMENT)",
                "hot_potato_aborted": True,
                "zero_leg_risk_preserved": True,
                "net_profit_quote": 0.0,
                "gas_used_mist": gas_used_mist,
                "gas_cost_sui": gas_cost_sui,
                "state_mutations": 0,
            }

        net_profit_quote = (proceeds_quote - borrow_amount) / quote_scale
        return {
            "status": "SUCCESS",
            "hot_potato_satisfied": True,
            "zero_leg_risk_preserved": True,
            "borrow_amount_quote": borrow_amount / quote_scale,
            "repaid_amount_quote": borrow_amount / quote_scale,
            "net_profit_quote": net_profit_quote,
            "gas_used_mist": gas_used_mist,
            "gas_cost_sui": gas_cost_sui,
            "state_mutations": 8,
        }
```

---

## 6. Real-Time Sui GraphQL RPC Integration

To replace the deprecated JSON-RPC (-32601), `SuiDeepBookVenue` will include high-efficiency async GraphQL query helpers:

```python
import aiohttp

class SuiGraphQLClient:
    """Async GraphQL client interfacing official Sui endpoints."""
    def __init__(self, endpoint: str = SUI_GRAPHQL_MAINNET):
        self.endpoint = endpoint

    async def get_cetus_pool_spot_price(self, pool_id: str, dec_a: int, dec_b: int) -> float:
        """Queries Cetus pool state and calculates exact spot price."""
        query = f"""
        query {{
          object(address: "{pool_id}") {{
            asMoveObject {{
              contents {{
                json
              }}
            }}
          }}
        }}
        """
        async with aiohttp.ClientSession() as session:
            async with session.post(self.endpoint, json={"query": query}, timeout=5) as resp:
                data = await resp.json()
                contents = data.get("data", {}).get("object", {}).get("asMoveObject", {}).get("contents", {}).get("json", {})
                sqrt_p = int(contents.get("current_sqrt_price", 0))
                p_ratio = (sqrt_p / (2**64)) ** 2
                # Amount of Coin B per Coin A
                real_b_per_a = p_ratio * (10 ** (dec_a - dec_b))
                return real_b_per_a
```

---

## 7. Automated Multi-Pair Test Suite Specification (`test_sui_deepbook_multipair.py`)

A new test file `trading-engine/tests/test_sui_deepbook_multipair.py` will test:
1. `test_multipair_configs_completeness`: Validates that all 4 pairs exist in `SUI_PAIRS_CONFIG` with non-empty pool IDs, valid decimals, and matching price factors.
2. `test_multipair_ptb_builder_all_pairs`: Generates 8-command PTBs for `"SUI/USDC"`, `"DEEP/SUI"`, `"DEEP/USDC"`, and `"CETUS/SUI"`. Verifies:
   - Exactly 8 commands.
   - Command 0 uses `borrow_flashloan_quote` with matching pair types.
   - Command 1 uses correct Cetus pool ID, `[cetus_coin_a, cetus_coin_b]`, and `a2b` boolean (`True` for SUI/USDC, `False` for the rest).
   - Command 6 quenches Hot Potato via `return_flashloan_quote`.
3. `test_multipair_dry_run_simulation_profitable`: Runs profitable simulation across all 4 pairs and asserts `SUCCESS`, positive profit, and 0 lingering debt.
4. `test_multipair_dry_run_simulation_unprofitable_abort`: Runs unprofitable simulation and asserts `ABORTED`, `state_mutations == 0`, and `zero_leg_risk_preserved == True`.
5. `test_base_borrowed_flashloan_variant`: Tests construction of PTBs with `borrow_asset = "base"`.

---

## 8. Summary Checklist for Worker

- [ ] Add `CETUS_COIN_TYPE`, `CETUS_CORE_PACKAGE_ID`, `MIN_SQRT_PRICE`, `MAX_SQRT_PRICE`, and all pool ID constants to `trading-engine/venues/sui_deepbook_venue.py`.
- [ ] Define `PairConfig` and `SUI_PAIRS_CONFIG` dictionary.
- [ ] Update `HotPotatoPTBParams` with multi-pair fields and `from_pair()` factory method.
- [ ] Generalize `SuiDeepBookPTBBuilder.build_atomic_arb_ptb()` to dynamically support pair configurations and `borrow_asset`.
- [ ] Update `simulate_dry_run()` to scale by pair-specific quote decimals.
- [ ] Add `test_sui_deepbook_multipair.py` and ensure 100% test pass rate across existing and new suites.
