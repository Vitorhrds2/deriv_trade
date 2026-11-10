# Dispatch: Worker — Milestone M3 (End-to-End Execution Software & Venue Connectors)

## Objective
Build and test production-grade, end-to-end execution connectors for all 6 quantitative microstructure vectors in `trading-engine/venues/`:

1. **`trading-engine/venues/base.py` & `registry.py`**:
   - Ensure the Unified Venue interfaces (`PriceFeedVenue`, `ExecutionVenue`, `MarketUpdate`, `OrderExecutionResult`) are fully updated per `PROJECT.md § Interface Contracts`.

2. **`trading-engine/venues/hyperliquid_venue.py` (Vetor H84)**:
   - Full connector implementing:
     - Public REST and WebSocket subscription to `l2Book` (correctly parsing `levels[0]` as bids and `levels[1]` as asks, fixing the historical bug).
     - EIP-712 structured data signing for order placement (`place_order`) and cancellation (`cancel_order`).
     - Explicit Post-Only / ALO (`order_type: {"limit": {"tif": "Alo"}}`) flags ensuring zero taker fees.
     - Integration with `trading-engine/mocks/hyperliquid_mempool_mock.py` or local gossip stream for toxic flow avoidance (auto-cancel within lead-time window).
     - Testnet and mainnet endpoint routing.

3. **`trading-engine/venues/velocity_swift_venue.py` (Vetor H85)**:
   - Full connector implementing:
     - SWIFT WebSocket client (`wss://swift.velocity.exchange/ws?pubkey=...`) handling Ed25519 challenge authentication.
     - Live Dutch auction curve calculation $P(t) = P_{\text{start}} + \frac{t}{D}(P_{\text{end}} - P_{\text{start}})$ fixing the historical 2000 bps price artifact.
     - 0.25 bps maker rebate order construction (`placeAndMakeSignedMsgPerpOrder`).
     - Message deduplication (tracking `order_id` in LRU cache to prevent double-fills and race conditions).
     - Toxic flow gating against Coinbase / Binance reference oracle.

4. **`trading-engine/venues/sui_deepbook_venue.py` (Vetor H86)**:
   - Full connector implementing:
     - Sui GraphQL RPC client (`https://graphql.mainnet.sui.io/graphql` & testnet).
     - Real active Circle native USDC pool targeting (`0xe05dafb5133bcffb8d59f4e12465dc0e9faeaa05e3e342a08fe135800e3e4407`).
     - Move Programmable Transaction Block (PTB) builder for atomic Hot Potato flash loan:
       1. Borrow quote/base coin via flash loan (`borrow_flashloan_quote` with 0 bps fee).
       2. Place market order on DeepBookV3 pool.
       3. Swap acquired coin on AMM leg (Cetus / Turbos) back to flash loan coin (fixing the historical missing AMM leg bug).
       4. Return flash loan coin (`return_flashloan_quote`), satisfying Hot Potato.
       5. Profit remains in transaction context.
     - Dry-run simulation via GraphQL/RPC (`sui_dryRunTransactionBlock`) verifying zero leg risk (transaction aborts cleanly if spread is unprofitable).

5. **`trading-engine/venues/kalshi_fix_venue.py` (Vetor H87)**:
   - Full connector implementing:
     - FIXT.1.1 / FIX50SP2 client handling raw TCP and TLS connections.
     - TargetCompID routing: `KalshiNR` (trading) and `KalshiMD` (market data).
     - Tag 96 Ed25519 / RSA signature authentication on Logon (`35=A`), omitting Tag 50 to avoid CFTC disconnects.
     - Order entry (`35=D`), cancel (`35=F`), and execution report (`35=8`) processing for binary contracts (0-100 cents).
     - Seamless switching between Demo TLS Gateway (`fix.demo.kalshi.co:8228`) and local `KalshiFixMockServer`.

6. **`trading-engine/venues/dydx_v4_venue.py` (dYdX v4 L3)**:
   - Full connector implementing:
     - dYdX v4 Indexer REST & WebSocket client (`wss://indexer.dydx.trade/v4/ws`).
     - Real-time L2 and order-by-order L3 orderbook maintenance.
     - Short-term order submission with deterministic nonces and zero gas cost.
     - Sub-second execution confirmation handling.

7. **`trading-engine/venues/gmx_cex_venue.py` (GMX v2 & Tier-2 CEXs)**:
   - Full connector implementing:
     - Chainlink Low-Latency Data Streams pull oracle modeling (evaluating signed price reports and `acceptablePrice` slippage bounds).
     - WebSocket price feeds for Tier-2 CEXs (MEXC Spot `wbs.mexc.com/ws`, Gate.io Spot `api.gateio.ws/ws/v4/`).
     - Dynamic price impact fee calculation ($I = f(\Delta \text{OI}, \text{PoolSize})$).
     - Lead-lag signal detection between Tier-1 CEX, Tier-2 CEX, and GMX v2.
     - Synthetic delta-neutral hedging execution logic (avoiding physical withdrawal batching delays).

## Testing & Verification Requirements
- Write comprehensive unit tests in `trading-engine/tests/test_venues_unit.py` testing each venue connector:
  - Connection/disconnection.
  - Market data stream parsing.
  - Order construction and execution logic.
  - Specific mechanical protections (PTB atomic reversal, Post-Only ALO, SWIFT deduplication, Dutch auction pricing, FIX Tag 96).
- Run `pytest trading-engine/tests/test_venues_unit.py -v` using the virtual environment (`trading-engine/.venv/bin/pytest`).
- Document all test results in `handoff.md`.

## Mandatory Integrity Warning
DO NOT CHEAT. All implementations must be genuine. DO NOT hardcode test results, create dummy/facade implementations, or circumvent the intended task. A teamwork_auditor will independently verify your work. Integrity violations WILL be detected and your work WILL be rejected.


## 2026-11-03T05:01:11Z
You are teamwork_worker_m3_connectors.
Your working directory is: /Users/vitorhrds/Documents/Github/hypothesis/.agents/teamwork/teamwork_worker_m3_connectors
Read your task dispatch at /Users/vitorhrds/Documents/Github/hypothesis/.agents/teamwork/teamwork_worker_m3_connectors/DISPATCH.md
Read the authoritative user request at: /Users/vitorhrds/Documents/Github/hypothesis/.agents/teamwork/ORIGINAL_REQUEST.md
Read PROJECT.md at: /Users/vitorhrds/Documents/Github/hypothesis/.agents/teamwork/PROJECT.md
Read master audit report at: /Users/vitorhrds/Documents/Github/hypothesis/docs/technical_audit_quant_intelligence.md

MANDATORY INTEGRITY WARNING:
DO NOT CHEAT. All implementations must be genuine. DO NOT hardcode test results, create dummy/facade implementations, or circumvent the intended task. A teamwork_auditor will independently verify your work. Integrity violations WILL be detected and your work WILL be rejected.

Your Tasks for Milestone M3:
1. Update `trading-engine/venues/base.py` and `registry.py` per PROJECT.md contracts.
2. Build `trading-engine/venues/hyperliquid_venue.py` (H84): REST, WS l2Book parsing fix, EIP-712 signing, Post-Only/ALO flag, mempool toxic flow cancel integration.
3. Build `trading-engine/venues/velocity_swift_venue.py` (H85): SWIFT WS, Ed25519 challenge auth, running Dutch auction curve P(t), 0.25 bps maker rebate order construction, message deduplication, and toxic flow gating.
4. Build `trading-engine/venues/sui_deepbook_venue.py` (H86): GraphQL RPC client, Circle native USDC pool (0xe05dafb5...), Move PTB builder for DeepBookV3 flash loan (0 bps fee) + AMM leg swap (Cetus/Turbos) + return_flashloan Hot Potato repayment, and dryRun simulation.
5. Build `trading-engine/venues/kalshi_fix_venue.py` (H87): FIXT.1.1/FIX50SP2 client, Tag 96 Ed25519 auth, KalshiNR / KalshiMD session routing, connection to Demo TLS gateway or local mock server.
6. Build `trading-engine/venues/dydx_v4_venue.py` (dYdX v4): Indexer WS L2/L3 orderbook maintainer, sub-second settlement, and zero-gas order placement.
7. Build `trading-engine/venues/gmx_cex_venue.py` (GMX v2 & CEXs): Chainlink Data Streams pull oracle modeling with dynamic price impact fees, MEXC/Gate.io WS feeds, and synthetic delta-neutral execution.
8. Build comprehensive unit tests in `trading-engine/tests/test_venues_unit.py` testing all 6 venues, execution mechanisms, and mechanical protections. Run tests via `trading-engine/.venv/bin/pytest trading-engine/tests/test_venues_unit.py -v` and ensure 100% pass.

Write your handoff report to:
/Users/vitorhrds/Documents/Github/hypothesis/.agents/teamwork/teamwork_worker_m3_connectors/handoff.md
Send a message to the orchestrator when complete.
