# Test Infrastructure Architecture & Methodology (Milestone M4)

## 1. Executive Summary & Architecture Overview

The Quantitative Market Microstructure Test Suite (`trading-engine/simulations/test_quant_vectors_e2e.py`) establishes an enterprise-grade, requirement-driven, 4-tier testing framework. It rigorously validates the end-to-end operational readiness, cryptographic integrity, low-latency execution semantics, and mathematical edge across all six target market microstructure vectors:

1. **Hyperliquid (H84)**: L1 mempool gossip preview (`split_client_blocks: true`), cryptographic EIP-712 typed data signing, Post-Only / ALO (`tif: "Alo"`) enforcement, and 70–150ms toxic flow deflection.
2. **Velocity Exchange / Drift SWIFT (H85)**: Sub-second taker intent WebSocket streaming, live Dutch auction curve $P(t) = P_{\text{start}} + \frac{t}{D}(P_{\text{end}} - P_{\text{start}})$, 0.25 bps maker rebate capture (`placeAndMakeSignedMsgPerpOrder`), Ed25519 authentication, and LRU deduplication.
3. **Sui DeepBookV3 (H86)**: Move Programmable Transaction Blocks (PTB) with 8 atomic commands, 0.0% fee Hot Potato flash loans (`FlashLoan` struct with 0 abilities), AMM swap integration (Cetus/Turbos), and zero leg risk via VM reversion.
4. **Kalshi FIX (H87)**: FIXT.1.1 transport and FIX50SP2 application profile, strict CFTC Rule 38 compliance (strict omission of Tag 50 on Logon `35=A`), Ed25519 Tag 96 authentication, binary contract order lifecycle ($0.01–$0.99), and High-Fidelity Mock Server.
5. **dYdX v4 CometBFT / MemCLOB**: In-memory validator orderbook matching, real-time L2 and L3 discrete order maintainers, zero-gas Short-Term Orders (STO) with deterministic nonces, and institutional fee/rebate tier resolution (Tier 6+ maker rebate of 0.7 bps).
6. **GMX v2 Data Streams & Tier-2 CEXs**: Chainlink Low-Latency pull oracle verification, 2-step `acceptablePrice` slippage barriers, dynamic pool depth and price impact modeling ($I = \text{base\_fee} + \text{impact} \cdot \frac{\text{size}}{\text{pool}}$), Tier-2 CEX (MEXC / Gate.io) WebSocket ticker parsing, and lead-lag signal detection.

---

## 2. 4-Tier Test Suite Methodology

The test suite is structured hierarchically across 4 orthogonal tiers to ensure both isolated correctness and emergent system resilience:

```
+-----------------------------------------------------------------------------------+
|                            Tier 4: Real-World Scenarios                           |
|       (End-to-End Multi-Step Lifecycle, Toxic Deflection, Tri-Arb, Latency Arb)   |
+-----------------------------------------------------------------------------------+
                                         ^
                                         |
+-----------------------------------------------------------------------------------+
|                     Tier 3: Cross-Feature Combinations & Pairwise                 |
|   (Mempool Defense + ALO, SWIFT + CEX Hedge, Flash Loan + AMM, FIX + CEX Shock)   |
+-----------------------------------------------------------------------------------+
                                         ^
                                         |
+-----------------------------------------------------------------------------------+
|                      Tier 2: Boundary & Corner Cases                              |
| (Zero Size, Max Precision, Negative Spreads, VM Reverts, Tag 50 Rejection, etc.)  |
+-----------------------------------------------------------------------------------+
                                         ^
                                         |
+-----------------------------------------------------------------------------------+
|                        Tier 1: Feature Coverage (Happy Path)                      |
|       (H84, H85, H86, H87, dYdX v4, GMX/CEX Component Isolation >=5 tests/vector)  |
+-----------------------------------------------------------------------------------+
```

### Tier 1: Feature Coverage (>=5 tests per vector, >=30 tests total)
Isolates each protocol connector and verifies fundamental capabilities:
- **H84**: Payload construction, ALO flag settings, EIP-712 typed signing, `l2Book` parsing (`levels[0]=bids`, `levels[1]=asks`), and EIP-712 order cancellation.
- **H85**: SWIFT intent parsing, Dutch auction curve calculations, 0.25 bps rebate instruction building, LRU message deduplication, and Ed25519 challenge auth.
- **H86**: Native USDC pool targeting, 8-step Move PTB construction, 0% flash loan borrow, Cetus AMM swap leg, and Hot Potato repayment.
- **H87**: SOH-delimited FIX serialization, checksum & body length calculation, Tag 96 Ed25519 logon, NewOrderSingle (35=D) with Tag 50, and OrderCancelRequest (35=F).
- **dYdX v4**: L2 orderbook snapshot parsing, L3 order maintainer, zero-gas short-term order placement, maker rebate tier resolution, and zero-gas cancellation.
- **GMX v2 & CEXs**: Chainlink Data Streams pull oracle verification, dynamic price impact calculation, MEXC ticker parsing, Gate.io ticker parsing, and lead-lag signal detection.

### Tier 2: Boundary & Corner Cases (>=5 tests per vector, >=30 tests total)
Evaluates behavior under extreme inputs, network anomalies, and protocol constraints:
- **H84**: Zero size limits, negative prices, empty order books, spread crossing with ALO auto-cancellation, and non-toxic mempool filtering.
- **H85**: Zero duration auctions, post-duration clamping ($P(t) = P_{\text{end}}$), pre-start clamping ($P(t) = P_{\text{start}}$), extreme oracle spread toxic rejection (>50 bps), and LRU cache eviction boundaries.
- **H86**: Zero borrow amount, negative spread triggering Move VM abort, AMM slippage limit exceedance, custom token types, and 0 state mutations on abort.
- **H87**: Strict rejection of Tag 50 on Logon (35=A), corrupted checksum detection, out-of-range binary contract prices (<$0.01 or >$0.99), rapid reconnect concurrency control, and cancellation of unknown ClOrdIDs.
- **dYdX v4**: Client ID / nonce collisions, expired short-term orders (`goodTilBlock`), empty bid/ask L2 updates, non-existent order cancellations, and invalid price/size bounds.
- **GMX v2 & CEXs**: Zero pool depth fallback, extreme order size price impact explosion, stale oracle feeds, missing feeds during lead-lag evaluation, and adverse price moves violating `acceptablePrice`.

### Tier 3: Cross-Feature & Pairwise Combinations (>=10 tests total)
Verifies multi-venue synchronicity, concurrent operations, and atomic cross-market reactions:
- H84 mempool toxic sweep trigger driving resting ALO cancellation.
- Velocity SWIFT taker order event triggering synthetic hedge on CEX.
- Sui DeepBook flash loan coupled with AMM swap and atomic repayment cycle.
- Kalshi FIX order placement paired with mock execution report and fill state tracking.
- Tier-1 CEX price jump triggering GMX pull oracle order execution and Tier-2 synthetic hedge.
- Hyperliquid ALO maker quote defense coordinated with dYdX v4 quote updates.
- Velocity SWIFT auction price tracking driving dynamic updates on dYdX L3 book.
- GMX lead-lag signal detector triggering Sui DeepBook atomic arbitrage simulation.
- Kalshi prediction market price discovery paired with CEX volatility spike event.
- Cross-venue fee and rebate arbitrage comparing maker rebates across venues.
- Multi-venue simultaneous disconnection and task cleanup.

### Tier 4: Real-World Scenarios (>=6 tests total)
Simulates end-to-end production trading strategies and market microstructures:
1. **Scenario 1 — Hyperliquid Tokyo Market Making & Toxic Flow Avoidance**:
   Passive maker quote deployment, receipt of pre-consensus toxic market sweep from Tokyo node gossip, and defensive cancellation within the 70–150ms window before block commit.
2. **Scenario 2 — High-Frequency Drift SWIFT Intent Capture & Rebate Collection**:
   Streaming taker intent on SOL-PERP, computing live Dutch auction price $P(t)$, verifying reference oracle safety, executing maker fill earning 0.25 bps rebate, and deduplicating subsequent taker retries.
3. **Scenario 3 — Sui DeepBookV3 Atomic Triangular Arbitrage with Zero Leg Risk**:
   Execution of 8-step PTB under both profitable conditions (net profit transferred to operator, Hot Potato consumed) and unprofitable conditions (clean VM abort, 0 state mutations, 0 leg risk, only ~0.002 SUI gas burned).
4. **Scenario 4 — Kalshi FIX Prediction Market Liquidity Provision & Execution**:
   Live TCP socket connection to mock FIX engine, Ed25519 Tag 96 logon, binary contract quote submission, execution report processing against retail flow, and cancel-on-disconnect.
5. **Scenario 5 — dYdX v4 Sub-Second Market Making Loop**:
   L2 snapshot ingestion, L3 orderbook maintainer seeding, zero-gas STO placement capturing institutional rebate, rapid quote adjustments, and zero-gas cancellation.
6. **Scenario 6 — Cross-Venue Latency Arbitrage (Gate.io/MEXC to GMX v2)**:
   Detection of lead-lag divergence across CEX spot and GMX pull oracle, submission of GMX v2 order respecting `acceptablePrice`, and opening of synthetic delta-neutral hedge.
7. **Scenario 7 — System Resilience & Fault Tolerance**:
   Handling of simulated transport dropouts, invalid FIX frames, corrupted orderbook feeds, and automatic session recovery across all active connectors.

---

## 3. Mock & Emulation Architecture

To enable complete deterministic execution without external KYC barriers (e.g. CFTC Rule 38 on Kalshi) or expensive live node infrastructure ($2,700/mo Tokyo node on Hyperliquid), the framework integrates two high-fidelity emulators:

### 1. Kalshi FIX Mock Server (`trading-engine/mocks/kalshi_fix_mock.py`)
- In-memory TCP server supporting standard FIXT.1.1 and FIX50SP2 frames.
- Implements strict SOH (`\x01`) delimited Tag=Value wire protocol with checksum (Tag 10) validation.
- Enforces CFTC regulatory compliance: rejects any Logon (35=A) containing Tag 50 with an immediate Logout (35=5).
- In-memory binary contract matching engine supporting price-time priority between $0.01 and $0.99.

### 2. Hyperliquid Mempool Tokyo Gossip Emulator (`trading-engine/mocks/hyperliquid_mempool_mock.py`)
- Emulates non-validator L1 nodes operating with `split_client_blocks: true`.
- Emits pre-consensus uncommitted transactions with configurable lead times (70–150ms).
- Simulates toxic flow sweeps that allow measuring maker defensive reaction latencies (Tokyo <5ms vs US-East ~150ms).

---

## 4. Test Environment & Execution Commands

### Prerequisites
- Python 3.11+ / 3.13+ in `trading-engine/.venv`
- `pytest` with `pytest-asyncio` plugin installed

### Running the Entire E2E Test Suite
```bash
trading-engine/.venv/bin/pytest trading-engine/simulations/test_quant_vectors_e2e.py -v
```

### Running by Tier
```bash
# Tier 1: Feature Coverage
trading-engine/.venv/bin/pytest trading-engine/simulations/test_quant_vectors_e2e.py -k "tier1" -v

# Tier 2: Boundary & Corner Cases
trading-engine/.venv/bin/pytest trading-engine/simulations/test_quant_vectors_e2e.py -k "tier2" -v

# Tier 3: Cross-Feature Combinations
trading-engine/.venv/bin/pytest trading-engine/simulations/test_quant_vectors_e2e.py -k "tier3" -v

# Tier 4: Real-World Scenarios
trading-engine/.venv/bin/pytest trading-engine/simulations/test_quant_vectors_e2e.py -k "tier4" -v
```

### Running by Microstructure Vector
```bash
# Hyperliquid H84
trading-engine/.venv/bin/pytest trading-engine/simulations/test_quant_vectors_e2e.py -k "h84" -v

# Velocity SWIFT H85
trading-engine/.venv/bin/pytest trading-engine/simulations/test_quant_vectors_e2e.py -k "h85" -v

# Sui DeepBookV3 H86
trading-engine/.venv/bin/pytest trading-engine/simulations/test_quant_vectors_e2e.py -k "h86" -v

# Kalshi FIX H87
trading-engine/.venv/bin/pytest trading-engine/simulations/test_quant_vectors_e2e.py -k "h87" -v

# dYdX v4
trading-engine/.venv/bin/pytest trading-engine/simulations/test_quant_vectors_e2e.py -k "dydx" -v

# GMX v2 & CEXs
trading-engine/.venv/bin/pytest trading-engine/simulations/test_quant_vectors_e2e.py -k "gmx" -v
```

---

## 5. Integrity & Quality Standards

- **Zero Facade Testing**: No mock or test contains trivial assertions (`assert True`) or hardcoded dummy results. Every test exercises real classes, executes real cryptographic algorithms (Ed25519, EIP-712/Keccak-256), parses real wire-protocol frames, and validates genuine execution flows.
- **Deterministic Independence**: All tests are fully self-contained, managing their own lifecycle, initializing isolated state, and closing sockets and asynchronous event loops cleanly upon completion.
- **Strict Typing & Error Handling**: Comprehensive typing conforming to Python `typing` annotations and rigorous assertion of expected edge-case exception types and error status codes.
