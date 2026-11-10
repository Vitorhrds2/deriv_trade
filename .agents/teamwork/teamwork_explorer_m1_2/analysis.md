# Technical Implementation Blueprint: Sui GraphQL RPC Client & Multi-Pair Market Data Architecture (Milestone M1)

**Working Directory:** `/Users/vitorhrds/Documents/Github/hypothesis/.agents/teamwork/teamwork_explorer_m1_2/`  
**Date:** 2026-11-10T02:33:00Z  
**Status:** Complete Technical Blueprint for Worker Implementation  

---

## 1. Executive Summary

Public Sui fullnodes (`https://fullnode.mainnet.sui.io`) have completely deprecated JSON-RPC, returning verbatim error `{"jsonrpc":"2.0","error":{"code":-32601,"message":"Method not found. JSON-RPC on public fullnodes has been deprecated. Please migrate to gRPC or GraphQL endpoints..."}}`.

This document establishes the production-grade technical specification for Milestone M1:
1. **`SuiGraphQLClient`**: High-performance asynchronous GraphQL client interfacing `https://graphql.mainnet.sui.io/graphql` (configurable via `SUI_GRAPHQL_URL`).
2. **Atomic Dual-Coin Balance Tracking**: Resolves operator wallet (`0x5621a8e7199680512ee829565b96febea2587e534fd69b33f04004298d7e5ce9`) SUI gas (5,419,245,048 MIST = 5.4192 SUI) and Circle Native USDC balances in a single sub-200ms query.
3. **Multi-Pair DeepBookV3 & Cetus AMM Pricing**: Live state extraction and mathematical price conversion across all 4 production pairs (`SUI/USDC`, `DEEP/SUI`, `DEEP/USDC`, `CETUS/SUI`).
4. **Pool ID Verification & Bug Fix**: Resolved the verified mainnet DeepBook V3 CETUS/SUI pool ID (`0xcf8d0d98dd3c2ceaf40845f5260c620fa62b3a15380bc100053aecd6df8e5e7c`), correcting the truncated ID in previous drafts.
5. **Dry-Run & Simulation via GraphQL**: Replaces legacy `dryRunTransactionBlock` with the official GraphQL `simulateTransaction(transaction: JSON!, doGasSelection: Boolean)` API.

---

## 2. On-Chain Introspection & Evidence Matrix

### 2.1 Legacy JSON-RPC Deprecation Evidence
```bash
curl -s -X POST https://fullnode.mainnet.sui.io -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"suix_getBalance","params":["0x5621a8e7199680512ee829565b96febea2587e534fd69b33f04004298d7e5ce9"]}'
```
**Verbatim Output:**
```json
{"jsonrpc":"2.0","error":{"code":-32601,"message":"Method not found. JSON-RPC on public fullnodes has been deprecated. Please migrate to gRPC or GraphQL endpoints. See https://docs.sui.io/develop/accessing-data/json-rpc-migration for more information."},"id":null}
```

### 2.2 DeepBook V3 Package & Registry Introspection
- **Package ID**: `0x2c8d603bc51326b8c13cef9dd07031a408a48dddb541963357661df5d3204809` (Note: `0xdee9` is legacy DeepBook V2).
- **Registry Shared Object**: `0xaf16199a2dff736e9f07a845f23c5da6df6f756eddb631aed9d24a93efc4549d`.
- **Cetus Global Config**: `0xdaa46292632c3c4d8f31f23ea0f9b36a28ff3677e9684980e4438403a67a3d8f`.

### 2.3 Verified Production 4-Pair Parameters
| Pair | DeepBook V3 Pool ID | Cetus CLMM Pool ID | Base Coin Type & Decimals | Quote Coin Type & Decimals | Cetus Swap Direction (`a2b`) | Price Formula |
|---|---|---|---|---|---|---|
| **SUI/USDC** | `0xe05dafb5133bcffb8d59f4e12465dc0e9faeaa05e3e342a08fe135800e3e4407` | `0x51e883ba7c0b566a26cbc8a94cd33eb0abd418a77cc1e60ad22fd9b1f29cd2ab` | `0x2::sui::SUI` (9) | `0xdba34672e30cb065b1f93e3ab55318768fd6fef66c15942c9f7cb846e2f900e7::usdc::USDC` (6) | `True` (USDC->SUI) | $P_{USDC/SUI} = 1.0 / ( (sp / 2^{64})^2 \times 10^{-3} )$ |
| **DEEP/SUI** | `0xb663828d6217467c8a1838a03793da896cbe745b150ebd57d82f814ca579fc22` | `0xd978d331772a5b90d5a4781e1232d18afd12019d0c35db79e3674beeda8f9126` | `0xdeeb7a4662eec9f2f3def03fb937a663dddaa2e215b8078a284d026b7946c270::deep::DEEP` (6) | `0x2::sui::SUI` (9) | `False` (SUI->DEEP) | $P_{SUI/DEEP} = (sp / 2^{64})^2 \times 10^{-3}$ |
| **DEEP/USDC** | `0xf948981b806057580f91622417534f491da5f61aeaf33d0ed8e69fd5691c95ce` | `0xa2f4e24dc234cf024bae1bd5b1275ab5bdc7c28dd1ec84dd98c2d012bbd315f0` | `0xdeeb7a4662eec9f2f3def03fb937a663dddaa2e215b8078a284d026b7946c270::deep::DEEP` (6) | `0xdba34672e30cb065b1f93e3ab55318768fd6fef66c15942c9f7cb846e2f900e7::usdc::USDC` (6) | `False` (USDC->DEEP) | $P_{USDC/DEEP} = (sp / 2^{64})^2 \times 1.0$ |
| **CETUS/SUI** | `0xcf8d0d98dd3c2ceaf40845f5260c620fa62b3a15380bc100053aecd6df8e5e7c` | `0x2e041f3fd93646dcc877f783c1f2b7fa62d30271bdef1f21ef002cebf857bded` | `0x06864a6f921804860930db6ddbe2e16acdf8504495ea7481637a1c8b9a8fe54b::cetus::CETUS` (9) | `0x2::sui::SUI` (9) | `False` (SUI->CETUS) | $P_{SUI/CETUS} = (sp / 2^{64})^2 \times 1.0$ |

---

## 3. Architecture of `SuiGraphQLClient`

### 3.1 Design Goals
1. **Asynchronous & Non-Blocking**: Built on `httpx.AsyncClient` with standard `urllib.request` fallback for testing/synchronous contexts.
2. **Atomic Batch Queries**: Queries all 4 pair pools and wallet balances in a single HTTP request roundtrip (~200–300ms total latency).
3. **Resilient Network Handling**: Exponential backoff (100ms, 200ms, 400ms) with jitter, connection pooling (max keepalive connections = 20), and 10-second timeout.
4. **Zero-Gas Simulation**: Executes `simulateTransaction` on Sui GraphQL for PTB dry runs, eliminating deprecated JSON-RPC `dryRunTransactionBlock`.

### 3.2 Key GraphQL Queries

#### 3.2.1 Atomic Dual-Balance Query
```graphql
query GetBalances($address: SuiAddress!) {
  address(address: $address) {
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

#### 3.2.2 Multi-Pair Market Snapshot Query
```graphql
query GetMultiPairMarketSnapshot(
  $wallet: SuiAddress!,
  $cetusSuiUsdc: SuiAddress!,
  $cetusDeepSui: SuiAddress!,
  $cetusDeepUsdc: SuiAddress!,
  $cetusCetusSui: SuiAddress!,
  $deepbookSuiUsdc: SuiAddress!,
  $deepbookDeepSui: SuiAddress!,
  $deepbookDeepUsdc: SuiAddress!,
  $deepbookCetusSui: SuiAddress!
) {
  wallet: address(address: $wallet) {
    sui: balance(coinType: "0x2::sui::SUI") { totalBalance }
    usdc: balance(coinType: "0xdba34672e30cb065b1f93e3ab55318768fd6fef66c15942c9f7cb846e2f900e7::usdc::USDC") { totalBalance }
  }
  cetusSuiUsdc: object(address: $cetusSuiUsdc) { asMoveObject { contents { json } } }
  cetusDeepSui: object(address: $cetusDeepSui) { asMoveObject { contents { json } } }
  cetusDeepUsdc: object(address: $cetusDeepUsdc) { asMoveObject { contents { json } } }
  cetusCetusSui: object(address: $cetusCetusSui) { asMoveObject { contents { json } } }
  deepbookSuiUsdc: object(address: $deepbookSuiUsdc) { asMoveObject { contents { json } } }
  deepbookDeepSui: object(address: $deepbookDeepSui) { asMoveObject { contents { json } } }
  deepbookDeepUsdc: object(address: $deepbookDeepUsdc) { asMoveObject { contents { json } } }
  deepbookCetusSui: object(address: $deepbookCetusSui) { asMoveObject { contents { json } } }
}
```

#### 3.2.3 Simulation Query
```graphql
query SimulatePTB($tx: JSON!, $doGasSelection: Boolean) {
  simulateTransaction(transaction: $tx, doGasSelection: $doGasSelection) {
    effects {
      status
      gasEffects {
        gasSummary {
          computationCost
          storageCost
          storageRebate
        }
      }
    }
    outputs
  }
}
```

---

## 4. Multi-Pair Polling & Market Data Dispatching (`subscribe_market_data`)

### 4.1 Internal Polling Loop Workflow
1. When `connect()` is awaited, a background task `_poll_market_data_loop` is spawned.
2. Every `POLL_INTERVAL_SEC` (default: 1.0s, configurable via env `SUI_POLL_INTERVAL`):
   - Invokes `SuiGraphQLClient.get_market_snapshot()`.
   - Parses `current_sqrt_price` for each of the 4 Cetus pools and computes the AMM price $P_{\text{amm}}$.
   - Extracts or models the DeepBook best bid $P_{\text{bid}}$ and best ask $P_{\text{ask}}$.
   - Calculates the directional arbitrage spread in basis points:
     $$\text{spread\_bps} = \frac{P_{\text{bid}} - P_{\text{amm\_ask}}}{P_{\text{amm\_ask}}} \times 10,000$$
   - Generates a `MarketUpdate` instance for each pair and triggers all callbacks subscribed via `subscribe_market_data(symbol, callback)`.
   - Caches wallet balances in `_cached_balances` for `get_wallet_balances()`.

### 4.2 Data Models
```python
@dataclass
class MarketUpdate:
    venue: str               # "sui_deepbook"
    symbol: str              # "SUI/USDC", "DEEP/SUI", "DEEP/USDC", "CETUS/SUI"
    bid_px: float            # DeepBook best bid price
    bid_sz: float            # DeepBook available bid size
    ask_px: float            # DeepBook best ask price
    ask_sz: float            # DeepBook available ask size
    timestamp_ns: int        # Hardware timestamp in nanoseconds
    raw: Optional[Dict[str, Any]] = None  # {cetus_price, spread_bps, liquidity, fee_rate, pool_id}
```

---

## 5. Worker Implementation Specification

The implementer (Worker) must modify `trading-engine/venues/sui_deepbook_venue.py` according to the following design:

### 5.1 Component Overview
```
trading-engine/venues/sui_deepbook_venue.py
├── PairConfig / PAIRS_REGISTRY (Definitions of 4 pairs, pool IDs, decimals)
├── SuiGraphQLClient (Async GraphQL client with execute, dual_balance, snapshot, simulate)
├── HotPotatoPTBParams (Updated with pair_name, pool IDs, fee structures)
├── SuiDeepBookPTBBuilder (Updated with DeepBook V3 package 0x2c8d..., 4 pairs support)
└── SuiDeepBookVenue (UnifiedVenue implementation with live connect, polling, order submission)
```

### 5.2 Exact Code Skeleton for Implementer
```python
class SuiGraphQLClient:
    def __init__(self, endpoint: Optional[str] = None):
        self.endpoint = endpoint or os.getenv("SUI_GRAPHQL_URL", SUI_GRAPHQL_MAINNET)
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(10.0, connect=5.0),
                limits=httpx.Limits(max_keepalive_connections=20, max_connections=50)
            )
        return self._client

    async def execute(self, query: str, variables: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        client = await self._get_client()
        payload = {"query": query, "variables": variables or {}}
        for attempt in range(3):
            try:
                resp = await client.post(self.endpoint, json=payload, headers={"Content-Type": "application/json"})
                resp.raise_for_status()
                data = resp.json()
                if "errors" in data and not data.get("data"):
                    raise RuntimeError(f"GraphQL Errors: {data['errors']}")
                return data
            except Exception as e:
                if attempt == 2:
                    raise
                await asyncio.sleep(0.1 * (2 ** attempt))

    async def get_wallet_balances(self, address: str) -> Dict[str, float]:
        query = """...""" # Dual balance query
        res = await self.execute(query, {"address": address})
        sui_mist = int(res["data"]["address"]["sui"]["totalBalance"])
        usdc_raw = int(res["data"]["address"]["usdc"]["totalBalance"])
        return {
            "sui_mist": sui_mist,
            "sui": sui_mist / 1e9,
            "usdc_raw": usdc_raw,
            "usdc": usdc_raw / 1e6
        }

    async def get_market_snapshot(self, wallet_address: str) -> Dict[str, Any]:
        # Single batch query for all 4 pairs and wallet balances
        ...
```

---

## 6. Verification and Validation Guidelines

1. **Verify Dual Balance**: Address `0x5621a8e7199680512ee829565b96febea2587e534fd69b33f04004298d7e5ce9` returns `totalBalance: 5419245048` for SUI and `0` for USDC.
2. **Verify 4-Pair Object Resolution**: Batch GraphQL query returns valid `asMoveObject.contents.json` for all 8 pool objects (`4 Cetus + 4 DeepBook`).
3. **Verify SUI Price Consistency**: Cetus SUI/USDC `sqrt_price` converted via $P_{USDC/SUI} = 1.0 / ( (sp / 2^{64})^2 \times 10^{-3} )$ returns a spot price within expected mainnet range (~$0.80–$0.90 USDC).
4. **Verify Zero Legacy Fullnode Calls**: Confirm `grep -rn "fullnode.mainnet.sui.io" trading-engine/` returns zero active usages in `sui_deepbook_venue.py`.
