# Dispatch: E2E Test Suite Writer — Milestone M4 (Dual Track Test Suite & TEST_READY.md)

## Objective
Design and implement the comprehensive 4-Tier requirement-driven E2E test suite in `trading-engine/simulations/test_quant_vectors_e2e.py` and publish `TEST_INFRA.md` and `TEST_READY.md` at the project root:

### 1. Test Methodology (4 Tiers across all 6 vectors: H84, H85, H86, H87, dYdX v4, GMX/CEX):
- **Tier 1 — Feature Coverage (>=5 tests per vector, >=30 tests total)**:
  - Happy-path verification of each venue connector in isolation:
    - H84: Order construction, ALO flag, EIP-712 signature generation, WS l2Book parsing.
    - H85: SWIFT message parsing, live Dutch auction curve calculation $P(t)$, 0.25 bps maker rebate order construction, deduplication LRU cache.
    - H86: Native USDC pool ID targeting, 8-step Move PTB construction, flash loan borrowing and repayment coin creation.
    - H87: FIX message serialization, checksum calculation, Tag 96 Ed25519 logon, order entry and cancel messages.
    - dYdX v4: L2 orderbook updates, L3 orderbook maintainer, zero-gas short-term order creation, fee tier resolution.
    - GMX v2 & CEXs: Chainlink Data Streams pull oracle verification, price impact fee calculation, MEXC & Gate.io bookTicker parsing, lead-lag signal detector.
- **Tier 2 — Boundary & Corner Cases (>=5 tests per vector, >=30 tests total)**:
  - Extreme values and limit conditions:
    - H84: Zero size, negative price, max price precision, invalid signature handling, empty order book.
    - H85: Auction duration = 0, elapsed time > duration ($P(t) = P_{\text{end}}$), elapsed time < 0 ($P(t) = P_{\text{start}}$), extreme price spread (>5000 bps) toxic rejection.
    - H86: Borrow amount = 0, repay amount < borrow amount (Hot Potato violation), slippage tolerance exceeded in AMM leg, invalid pool addresses.
    - H87: Strict rejection of Tag 50 on Logon (35=A), invalid checksum handling, binary contract prices outside [1, 99] cents, rapid connection disconnect/reconnect.
    - dYdX v4: Nonce collisions, expired short-term orders, empty orderbook bids/asks, order cancel for non-existent order.
    - GMX v2 & CEXs: Negative or zero open interest, massive order size relative to pool depth (extreme price impact fee), stale oracle reports (>60s), CEX price disconnect.
- **Tier 3 — Cross-Feature & Pairwise Combinations (>=10 tests)**:
  - Multi-venue interactions and joint workflows:
    - H84 mempool toxic sweep trigger paired with resting ALO order cancellation.
    - Velocity SWIFT taker order event driving simultaneous hedge on Binance/Coinbase.
    - Sui DeepBook flash loan coupled with Cetus AMM swap and atomic repayment cycle.
    - Kalshi FIX order placement paired with mock execution report and fill state tracking.
    - Tier-1 CEX price jump triggering GMX pull oracle order execution and Tier-2 synthetic hedge.
- **Tier 4 — Real-World Application Scenarios (>=6 tests)**:
  - Realistic multi-step end-to-end operational scenarios:
    1. Full Hyperliquid Tokyo market making cycle with toxic flow deflection.
    2. High-frequency Drift SWIFT taker intent capture and rebate collection on SOL-PERP.
    3. Complete atomic triangular arbitrage on Sui with zero leg risk (dry-run pass vs unprofitable dry-run abort).
    4. Kalshi FIX prediction market liquidity provision and execution against simulated retail flow.
    5. dYdX v4 sub-second market making loop with zero-gas quote updates.
    6. Cross-venue latency arbitrage between Gate.io/MEXC and GMX v2 with synthetic delta-neutral position hold.

### 2. Deliverables:
- `TEST_INFRA.md`: Published at project root documenting test architecture, methodology, and tier coverage breakdown.
- `trading-engine/simulations/test_quant_vectors_e2e.py`: Full pytest test suite. Run via `trading-engine/.venv/bin/pytest trading-engine/simulations/test_quant_vectors_e2e.py -v`.
- `TEST_READY.md`: Published at project root signaling the completion of the E2E test suite with full test count and passing status.
- `handoff.md`: In your working directory summarizing test design, execution metrics, and commands.

## Inputs
- Authoritative User Request: `/Users/vitorhrds/Documents/Github/hypothesis/.agents/teamwork/ORIGINAL_REQUEST.md`
- Blueprint: `/Users/vitorhrds/Documents/Github/hypothesis/.agents/teamwork/PROJECT.md`
- Master Technical Report: `/Users/vitorhrds/Documents/Github/hypothesis/docs/technical_audit_quant_intelligence.md`
- Venue Connectors: `/Users/vitorhrds/Documents/Github/hypothesis/trading-engine/venues/`
- Mock Infrastructure: `/Users/vitorhrds/Documents/Github/hypothesis/trading-engine/mocks/`

## Mandatory Integrity Warning
DO NOT CHEAT. All implementations must be genuine. DO NOT hardcode test results, create dummy/facade implementations, or circumvent the intended task. A teamwork_auditor will independently verify your work. Integrity violations WILL be detected and your work WILL be rejected.


## 2026-11-03T05:17:47Z
Sender: 784b07d9-8c51-454a-ae17-d0ee1ce5f483
Content: You are teamwork_test_writer_m4.
Your working directory is: /Users/vitorhrds/Documents/Github/hypothesis/.agents/teamwork/teamwork_test_writer_m4
Read your task dispatch at /Users/vitorhrds/Documents/Github/hypothesis/.agents/teamwork/teamwork_test_writer_m4/DISPATCH.md
Read the authoritative user request at: /Users/vitorhrds/Documents/Github/hypothesis/.agents/teamwork/ORIGINAL_REQUEST.md
Read PROJECT.md at: /Users/vitorhrds/Documents/Github/hypothesis/.agents/teamwork/PROJECT.md

MANDATORY INTEGRITY WARNING:
DO NOT CHEAT. All implementations must be genuine. DO NOT hardcode test results, create dummy/facade implementations, or circumvent the intended task. A teamwork_auditor will independently verify your work. Integrity violations WILL be detected and your work WILL be rejected.

Your Tasks:
1. Create `TEST_INFRA.md` at project root outlining the 4-tier methodology, feature coverage, and architecture.
2. Implement the 4-Tier E2E test suite in `trading-engine/simulations/test_quant_vectors_e2e.py` covering:
   - Tier 1: Feature Coverage (>=5 tests per vector, >=30 tests total across H84, H85, H86, H87, dYdX v4, GMX/CEX).
   - Tier 2: Boundary & Corner Cases (>=5 tests per vector, >=30 tests total).
   - Tier 3: Cross-Feature Combinations (>=10 tests).
   - Tier 4: Real-World Scenarios (>=6 tests).
   Total test cases: >=76 tests!
3. Execute the test suite using `trading-engine/.venv/bin/pytest trading-engine/simulations/test_quant_vectors_e2e.py -v` and ensure 100% pass rate.
4. Publish `TEST_READY.md` at project root with full summary table and runner commands.
5. Write your handoff report to `/Users/vitorhrds/Documents/Github/hypothesis/.agents/teamwork/teamwork_test_writer_m4/handoff.md` and send a message when complete.
