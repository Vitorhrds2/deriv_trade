# BRIEFING — 2026-11-03T05:15:00Z

## Mission
Build and thoroughly test production-grade, genuine end-to-end execution connectors for all 6 quantitative market microstructure vectors in `trading-engine/venues/`: base/registry updates, Hyperliquid (H84), Velocity SWIFT (H85), Sui DeepBookV3 (H86), Kalshi FIX (H87), dYdX v4, and GMX v2 / CEXs.

## 🔒 My Identity
- Archetype: teamwork_worker
- Roles: implementer, qa, specialist
- Working directory: /Users/vitorhrds/Documents/Github/hypothesis/.agents/teamwork/teamwork_worker_m3_connectors
- Original parent: 784b07d9-8c51-454a-ae17-d0ee1ce5f483
- Milestone: M3 (End-to-End Execution Software & Venue Connectors)

## 🔒 Key Constraints
- DO NOT CHEAT. All implementations must be genuine.
- DO NOT hardcode test results, expected outputs, or create dummy/facade implementations.
- Every implementation must maintain real state and produce real behavior.
- Use `trading-engine/.venv/bin/pytest` for testing.
- Write handoff report to `handoff.md` with 5 components (Observation, Logic Chain, Caveats, Conclusion, Verification Method).
- Coordinate via `send_message` with caller `784b07d9-8c51-454a-ae17-d0ee1ce5f483`.

## Current Parent
- Conversation ID: 784b07d9-8c51-454a-ae17-d0ee1ce5f483
- Updated: 2026-11-03T05:01:11Z

## Task Summary
- **What to build**:
  1. `trading-engine/venues/base.py` & `registry.py` contract updates (`MarketUpdate`, `OrderExecutionResult`, `UnifiedVenue`, registry lookup).
  2. `trading-engine/venues/hyperliquid_venue.py` (H84): REST, WS l2Book parsing fix (`levels[0]` bids, `levels[1]` asks), EIP-712 signing, Post-Only/ALO flag, mempool toxic flow cancel integration.
  3. `trading-engine/venues/velocity_swift_venue.py` (H85): SWIFT WS, Ed25519 challenge auth, running Dutch auction curve P(t), 0.25 bps maker rebate order construction, message deduplication, and toxic flow gating.
  4. `trading-engine/venues/sui_deepbook_venue.py` (H86): GraphQL RPC client, Circle native USDC pool, Move PTB builder for DeepBookV3 flash loan (0 bps fee) + AMM leg swap (Cetus/Turbos) + return_flashloan Hot Potato repayment, and dryRun simulation.
  5. `trading-engine/venues/kalshi_fix_venue.py` (H87): FIXT.1.1/FIX50SP2 client, Tag 96 Ed25519 auth, KalshiNR / KalshiMD session routing, connection to Demo TLS gateway or local mock server.
  6. `trading-engine/venues/dydx_v4_venue.py`: Indexer WS L2/L3 orderbook maintainer, sub-second settlement, and zero-gas order placement.
  7. `trading-engine/venues/gmx_cex_venue.py`: Chainlink Data Streams pull oracle modeling with dynamic price impact fees, MEXC/Gate.io WS feeds, and synthetic delta-neutral execution.
  8. `trading-engine/tests/test_venues_unit.py`: Comprehensive unit tests for all 6 venues, execution mechanisms, and mechanical protections.
- **Success criteria**: 100% passing tests in `trading-engine/tests/test_venues_unit.py`, zero fake/hardcoded implementations, robust error handling and genuine state.
- **Interface contracts**: `PROJECT.md § Interface Contracts`
- **Code layout**: `PROJECT.md § Code Layout`

## Key Decisions Made
- Architecture conforms strictly to `UnifiedVenue` base class while maintaining backward compatibility for existing `PriceFeedVenue` and `ExecutionVenue` subclasses.
- All connectors implement real protocol serialization, state machines, math models, and network/simulation interfaces.
- Post-mortems 5.1, 5.2, and 5.3 were fully resolved in the new connectors and verified by unit tests.

## Artifact Index
- `.agents/teamwork/teamwork_worker_m3_connectors/DISPATCH.md` — Worker assignment and task record
- `.agents/teamwork/teamwork_worker_m3_connectors/progress.md` — Liveness heartbeat and progress tracking
- `.agents/teamwork/teamwork_worker_m3_connectors/handoff.md` — Final handoff report
- `trading-engine/venues/base.py` — UnifiedVenue, MarketUpdate, OrderExecutionResult contracts
- `trading-engine/venues/registry.py` — Auto-registration decorator & lookup
- `trading-engine/venues/hyperliquid_venue.py` — H84 connector
- `trading-engine/venues/velocity_swift_venue.py` — H85 connector
- `trading-engine/venues/sui_deepbook_venue.py` — H86 connector
- `trading-engine/venues/kalshi_fix_venue.py` — H87 connector
- `trading-engine/venues/dydx_v4_venue.py` — dYdX v4 connector
- `trading-engine/venues/gmx_cex_venue.py` — GMX v2 & CEXs connector
- `trading-engine/tests/test_venues_unit.py` — Comprehensive unit test suite (12/12 passing)

## Change Tracker
- **Files modified**:
  - `trading-engine/venues/base.py`: Added MarketUpdate, OrderExecutionResult, UnifiedVenue.
  - `trading-engine/venues/registry.py`: Allowed UnifiedVenue and Any class in registry.
  - `trading-engine/venues/__init__.py`: Exported new venues and contracts.
  - `trading-engine/venues/hyperliquid_venue.py`: Built H84 connector.
  - `trading-engine/venues/velocity_swift_venue.py`: Built H85 connector.
  - `trading-engine/venues/sui_deepbook_venue.py`: Built H86 connector.
  - `trading-engine/venues/kalshi_fix_venue.py`: Built H87 connector.
  - `trading-engine/venues/dydx_v4_venue.py`: Built dYdX v4 connector.
  - `trading-engine/venues/gmx_cex_venue.py`: Built GMX v2 & CEXs connector.
  - `trading-engine/tests/test_venues_unit.py`: Built 12 comprehensive unit test cases.
- **Build status**: PASS (24/24 tests passing across test_venues_unit.py and test_mocks_unit.py)
- **Pending issues**: None

## Quality Status
- **Build/test result**: 100% pass (24/24 unit tests)
- **Lint status**: Clean (py_compile passed with 0 errors)
- **Tests added/modified**: 12 new comprehensive test cases in `test_venues_unit.py`

## Loaded Skills
- None requested in dispatch
