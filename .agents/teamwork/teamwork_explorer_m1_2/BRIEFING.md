# BRIEFING — 2026-11-10T02:35:00Z

## Mission
Produce a technical implementation blueprint for integrating Sui GraphQL RPC into `trading-engine/venues/sui_deepbook_venue.py` for Milestone M1 (multi-pair pricing polling, dual-balance query, pool state extraction, eliminating legacy fullnode JSON-RPC).

## 🔒 My Identity
- Archetype: explorer
- Roles: investigator, architect, synthesizer
- Working directory: /Users/vitorhrds/Documents/Github/hypothesis/.agents/teamwork/teamwork_explorer_m1_2/
- Original parent: bb8c036e-693a-4192-a9f6-25494af55dae
- Milestone: M1 - Sui GraphQL RPC Client Integration and Multi-Pair Orderbook / Pricing Polling

## 🔒 Key Constraints
- Read-only investigation — do NOT implement / modify project code
- Target file for blueprint: trading-engine/venues/sui_deepbook_venue.py (and related modules)
- Design SuiGraphQLClient class (urllib.request / httpx / aiohttp)
- Endpoint: https://graphql.mainnet.sui.io/graphql (configurable via SUI_GRAPHQL_URL)
- Atomic dual-balance query for SUI and native USDC
- Dynamic object fetching for DeepBook pools and Cetus pool states
- Async subscribe_market_data and pricing snapshot methods for 4 target pairs
- Replace legacy JSON-RPC calls (avoiding -32601 Method Not Found)
- Output analysis.md and handoff.md in working directory
- Communicate completion via send_message to caller

## Current Parent
- Conversation ID: bb8c036e-693a-4192-a9f6-25494af55dae
- Updated: 2026-11-10T02:30:00Z

## Investigation State
- **Explored paths**:
  - `trading-engine/venues/sui_deepbook_venue.py`
  - `trading-engine/venues/base.py`
  - `trading-engine/h86_sui_deepbook_flashloan_arb_scan.py`
  - `trading-engine/h86_sui/h86_onchain_orderbook.py`
  - Sui GraphQL RPC (`https://graphql.mainnet.sui.io/graphql`) schema introspection
- **Key findings**:
  - Legacy fullnode JSON-RPC fails with `-32601 Method not found`.
  - Operator wallet `0x5621a8e7199680512ee829565b96febea2587e534fd69b33f04004298d7e5ce9` verified live with 5,419,245,048 MIST (5.4192 SUI) and 0 USDC via atomic GraphQL query.
  - DeepBook V3 package ID on mainnet is `0x2c8d603bc51326b8c13cef9dd07031a408a48dddb541963357661df5d3204809` (not `0xdee9` which is V2).
  - DeepBook V3 Registry shared object is `0xaf16199a2dff736e9f07a845f23c5da6df6f756eddb631aed9d24a93efc4549d`.
  - Identified and verified all 4 pairs:
    1. SUI/USDC: DeepBook `0xe05dafb5...`, Cetus `0x51e883ba...`
    2. DEEP/SUI: DeepBook `0xb663828d...`, Cetus `0xd978d331...`
    3. DEEP/USDC: DeepBook `0xf948981b...`, Cetus `0xa2f4e24d...`
    4. CETUS/SUI: DeepBook `0xcf8d0d98dd3c2ceaf40845f5260c620fa62b3a15380bc100053aecd6df8e5e7c`, Cetus `0x2e041f3f...`
  - Cetus spot pricing mathematically validated via fixed-point Q64.64 `current_sqrt_price`.
  - Sui GraphQL `simulateTransaction` completely replaces `dryRunTransactionBlock`.
- **Unexplored areas**:
  - Worker implementation of `trading-engine/venues/sui_deepbook_venue.py` (delegated to Worker in next turn).

## Key Decisions Made
- Replaced individual pool queries with a single batch GraphQL document querying all 8 pools + wallet in <300ms.
- Standardized on `httpx.AsyncClient` with connection pooling and configurable `SUI_GRAPHQL_URL`.
- Corrected CETUS/SUI DeepBook pool ID to `0xcf8d0d98dd3c2ceaf40845f5260c620fa62b3a15380bc100053aecd6df8e5e7c`.
- Designed background polling loop for `subscribe_market_data` dispatching `MarketUpdate` dataclass events.

## Artifact Index
- `/Users/vitorhrds/Documents/Github/hypothesis/.agents/teamwork/teamwork_explorer_m1_2/DISPATCH.md` — Incoming message log
- `/Users/vitorhrds/Documents/Github/hypothesis/.agents/teamwork/teamwork_explorer_m1_2/BRIEFING.md` — Persistent context & state
- `/Users/vitorhrds/Documents/Github/hypothesis/.agents/teamwork/teamwork_explorer_m1_2/progress.md` — Liveness heartbeat & progress
- `/Users/vitorhrds/Documents/Github/hypothesis/.agents/teamwork/teamwork_explorer_m1_2/analysis.md` — Full technical implementation blueprint
- `/Users/vitorhrds/Documents/Github/hypothesis/.agents/teamwork/teamwork_explorer_m1_2/handoff.md` — 5-component hard handoff report
