# Protocol Specifications & Documentation Audit
**Auditor:** `teamwork_spec_miner_quant_survey_1`  
**Timestamp:** 2026-11-03T04:32:00Z  
**Target Vectors:** Hyperliquid (H84), Drift/Velocity SWIFT (H85), Sui DeepBookV3 (H86), Kalshi FIX/AWS PrivateLink (H87), dYdX v4 (CometBFT/L3), GMX v2 & Tier-2 CEXs (MEXC/Gate.io).

---

## 1. Executive Summary

This specification audit provides an exhaustive, authoritative technical review of six modern quantitative trading protocol architectures. The audit evaluates protocol state machines, consensus engines, network transport layers, message schemas, fee/rebate models, hardware requirements, and order execution dynamics. 

### Critical Insights & Rectifications of Previous Repo Findings:
1. **Hyperliquid (H84)**: Running a non-validator node with `split_client_blocks: true` enables eager streaming of uncommitted mempool transactions directly to disk (`~/hl/data/mempool_txs/{date}`) 70–150ms before block finality. Hardware specs require 16 vCPUs (validator requires 32), 128 GB RAM, and public gossip ports (4001, 4002) in Tokyo (ap-northeast-1). Baseline retail maker fee is +1.5 bps (positive fee); maker rebates require institutional Tier 4+ ($500M+ volume) or VIP contracts.
2. **Velocity Exchange / Drift Protocol (H85)**: Drift Protocol migrated/forked to Velocity Exchange (`@velocity-exchange/sdk@0.6.1`, Program `vELoC1audYbSYVRXn1vPaV8Axoa9oU6BYmNGZZBDZ1P`). The quote asset is native Solana USDT. SWIFT off-chain signed orders (`SignedMsgOrderParams`) carry `auctionStartPrice`, `auctionEndPrice`, and `auctionDuration` (400ms ticks). The prior repo finding of "2000 bps toxic deviation" was a **parsing artifact**: the script evaluated `params.price` (`auctionEndPrice` / limit price) instead of evaluating the active Dutch auction price. Maker rebate is a flat **0.25 bps (0.0025%)** across tiers.
3. **Sui DeepBookV3 (H86)**: DeepBook V3 flash loans utilize Move's "Hot Potato" pattern (zero abilities: no `drop`, `store`, or `copy`) with **0.0% (0 bps) flash loan fee**. The prior repo verdict of "REFUTADA por pool ilíquido" was caused by **querying deprecated Wormhole-bridged USDC (`wUSDC`) test pools and using a fabricated dummy USDC type string**. Active mainnet liquidity resides in the native Circle USDC pool (`0xe05dafb5133bcffb8d59f4e12465dc0e9faeaa05e3e342a08fe135800e3e4407`) and `DEEP_SUI` pool (`0xb663828d6217467c8a1838a03793da896cbe745b150ebd57d82f814ca579fc22`).
4. **Kalshi FIX / AWS PrivateLink (H87)**: CFTC-regulated DCM trading binary contracts (1¢ to 99¢ with $1.00 settlement). FIX connectivity uses **FIXT.1.1 + FIX50SP2** over TLS 1.2+ with target comps `KalshiNR` (non-retransmission, low latency), `KalshiRT`, `KalshiMD`, and `KalshiDC`. Logon (`35=A`) requires Ed25519 or RSA-2048 signing in Tag 96 (`RawData`). AWS PrivateLink provides sub-millisecond dedicated VPC endpoint access in AWS us-east-1 for Premier/Prime institutional accounts. Full KYC is mandatory under CFTC Rule 38; a high-fidelity emulation/mock layer is necessary for automated testing.
5. **dYdX v4 (CometBFT / L3 Orderbook)**: Cosmos SDK standalone appchain utilizing CometBFT consensus with ~0.8s–1.1s instant finality. Order placements and cancellations are **in-memory (memCLOB)** and gossiped peer-to-peer at zero gas. The block proposer executes deterministic matches from RAM. True Level 3 (L3) order-by-order data feeds require local full node gRPC/WebSocket streaming (`websocket-streaming-enabled`). Maker rebates start at Tier 6 (-0.7 bps) and Tier 7 (-1.1 bps).
6. **GMX v2 & Tier-2 CEXs (MEXC / Gate.io)**: GMX v2 eliminates historical push-oracle frontrunning via **Chainlink Low-Latency Data Streams** (pull-based cryptographically signed DON reports). Orders execute in two asynchronous steps (`OrderCreated` -> `ExecuteOrder` by keepers) bounded by `acceptablePrice` slippage limits and dynamic price impact fees. Tier-2 CEXs (MEXC 0% spot maker / 5 bps taker; Gate.io WebSocket v4 cutting latency 30–40%) present structural withdrawal/deposit batching friction (5–30 min delays), demanding synthetic delta-neutral execution over physical capital transfers.

---

## 2. Vector 1: Hyperliquid (H84) Deep Technical Specification

### 2.1 Architecture & Consensus
* **Consensus Engine:** HyperBFT — custom Byzantine Fault Tolerant consensus engine implemented in optimized low-level systems code (Rust/C++), delivering ~200ms block intervals and sub-second deterministic finality.
* **State Transition:** Native L1 purpose-built for financial derivatives. Order cancellation and execution state transitions do not require EVM contract dispatch.
* **Gas Model:** Zero gas fees for order placement, cancel, and modification actions. Rate limits and spam prevention are enforced via proof-of-authority, connection throttling, and account balance weight.

### 2.2 Non-Validator Node Gossip Protocol & `split_client_blocks`
* **Node Binary:** `hl-node` (repository: `hyperliquid-dex/node`).
* **Networking & Ports:** P2P gossip operates on TCP/UDP ports **4001** and **4002**. Both ports **must be publicly reachable** without NAT/firewall blocking; nodes with closed gossip ports are deprioritized by peers.
* **Mempool Visibility Configuration:**
  In `~/override_gossip_config.json`:
  ```json
  {
    "split_client_blocks": true
  }
  ```
* **Streaming Mechanics:**
  When `split_client_blocks: true` is enabled (and supported by intermediary network peers), the node actively bifurcates incoming block data:
  1. It eagerly writes pending, uncommitted transactions to disk at `~/hl/data/mempool_txs/{YYYY-MM-DD}` prior to consensus validation.
  2. It processes the committed block blocks at `~/hl/data/blocks/{YYYY-MM-DD}` upon round finality.
* **Lead Time:** Provides an observable **70ms to 150ms lead time** over standard public WebSocket trade/fill notifications.

### 2.3 Toxic Flow Avoidance Mechanism
* **Adverse Selection Threat:** In automated market making (AMM/CLOB), large aggressive taker orders and on-chain liquidation cascades sweep the book, filling passive limit orders before MMs can react.
* **Mempool Defensive Trigger:**
  1. Monitor file stream / memory-mapped buffer of `~/hl/data/mempool_txs/{date}` via inotify or shared memory ring buffer.
  2. Parse incoming `Order` actions where `is_buy != maker_side` and `sz > threshold_liquidation`.
  3. Emit immediate `cancel` or `cancelByCloid` over local UNIX socket or direct validator RPC connection.
  4. The cancel transaction propagates and arrives in time to be bundled into the same block proposal ahead of or concurrently with the toxic fill, nullifying adverse selection.

### 2.4 Order Flags & Types
* **Add Liquidity Only (ALO / Post-Only):**
  Specified in the `order_type` payload:
  ```json
  {
    "coin": "SOL",
    "is_buy": true,
    "sz": 1.0,
    "limit_px": 145.50,
    "reduce_only": false,
    "order_type": {
      "limit": {
        "tif": "Alo"
      }
    },
    "cloid": "0x0123456789abcdef0123456789abcdef"
  }
  ```
  *Behavior:* If the order crosses the resting spread upon arrival, it is **instantly cancelled** rather than filled as a taker. Zero taker fees paid.
* **Time-in-Force (`tif`):** `Alo` (Post-Only), `Gtc` (Good 'Til Cancel), `Ioc` (Immediate-or-Cancel).
* **Client Order ID (`cloid`):** 128-bit hex string for idempotent order tracking and cancellation without querying exchange order IDs.

### 2.5 Fee Schedule & Maker Rebates
Volume calculated on 14-day rolling window (`Perps Volume + 2 * Spot Volume`):

| Tier | 14-Day Volume | Taker Fee | Maker Fee / Rebate |
| :--- | :--- | :--- | :--- |
| **Tier 0** (Retail) | < $5M | 4.5 bps (0.045%) | **+1.5 bps (0.015%)** |
| **Tier 1** | ≥ $5M | 4.0 bps (0.040%) | **+1.2 bps (0.012%)** |
| **Tier 2** | ≥ $25M | 3.5 bps (0.035%) | **+0.8 bps (0.008%)** |
| **Tier 3** | ≥ $100M | 3.0 bps (0.030%) | **+0.4 bps (0.004%)** |
| **Tier 4** | ≥ $500M | 2.8 bps (0.028%) | **0.0 bps (0.000%)** |
| **Tier 5** | ≥ $2B | 2.6 bps (0.026%) | **0.0 bps (0.000%)** |
| **Tier 6** | ≥ $7B | 2.4 bps (0.024%) | **0.0 bps (0.000%)** |

*Crucial Reality:* Retail makers **pay** 1.5 bps per fill! Negative maker fees (rebates of -0.1 bps or higher) are exclusively reserved for institutional Market Maker Program agreements or specialized liquidity incentives. Staking HYPE offers 5% to 40% fee discounts.

### 2.6 Hardware Requirements & Co-location
* **Operating System:** Ubuntu 24.04 LTS (strictly enforced).
* **Non-Validator Specs:** Minimum 16 vCPUs, 128 GB RAM, 500 GB NVMe SSD.
* **Validator Specs:** Minimum 32 vCPUs, 128 GB RAM, 1 TB NVMe SSD.
* **Network & Co-location:** Core consensus validators are co-located in Tokyo, Japan. Recommended infrastructure: AWS `ap-northeast-1` (Tokyo) or Equinix TY3/TY11. Running in US East (`us-east-2`) introduces ~150ms trans-Pacific base RTT, completely wiping out the 70–150ms gossip edge.

---

## 3. Vector 2: Drift Protocol / Velocity Exchange (H85) Deep Technical Specification

### 3.1 Migration & Ecosystem State
* **Ecosystem Pivot:** Drift Protocol v2's high-performance order flow engine transitioned to **Velocity Exchange** (`velocity.exchange`).
* **Software Packages:**
  * Old package: `@drift-labs/sdk`
  * Active package: `@velocity-exchange/sdk` (active version `0.6.1+`).
* **Solana Program ID:** `vELoC1audYbSYVRXn1vPaV8Axoa9oU6BYmNGZZBDZ1P`.
* **Quote Asset:** Native Solana **USDT** (`Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB`), replacing USDC on mainnet markets.

### 3.2 SWIFT WebSocket Architecture & Taker Intent Preview
* **Endpoint:** `wss://swift.velocity.exchange/ws` (mainnet-beta).
* **Subscriber Class:** `SwiftOrderSubscriber` in `@velocity-exchange/sdk`.
* **Latency Advantage:** Broadcasts cryptographically signed taker order messages **100ms to 500ms before** they land on-chain for JIT auction execution.
* **Payload Structure (`SignedMsgOrderParamsMessage`):**
  ```typescript
  interface SignedMsgOrderParams {
    orderType: OrderType;
    marketIndex: number;
    direction: PositionDirection; // Long = 0, Short = 1
    baseAssetAmount: BN;         // Precision 1e9 (e.g. 1 SOL = 1_000_000_000)
    price: BN;                   // Precision 1e6 (auctionEndPrice / limit price)
    auctionStartPrice: BN;       // Starting price of Dutch auction (1e6)
    auctionEndPrice: BN;         // Final limit price of Dutch auction (1e6)
    auctionDuration: number;     // Duration in 400ms ticks (e.g., 20 = 8.0s)
    maxTs: BN;                   // Expiry unix timestamp
    signature: Buffer;           // 64-byte Ed25519 signature
  }
  ```

### 3.3 Dutch Auction Mechanics & Price Scale Rectification
* **Fixed Precision Scales:**
  * `PRICE_PRECISION`: $10^6$ (`1e6`)
  * `BASE_PRECISION`: $10^9$ (`1e9`)
  * `QUOTE_PRECISION`: $10^6$ (`1e6`)
* **Dutch Auction Price Function:**
  For an order at elapsed time $t \le D$ (where $D = \text{auctionDuration} \times 400\text{ms}$):
  $$P(t) = P_{\text{start}} + \frac{t}{D} \times (P_{\text{end}} - P_{\text{start}})$$
* **Resolution of Prior "2000 bps Toxic Deviation" Bug:**
  In historical tests (`h85_swift_subscriber.ts`), the script inspected `params.price` (which is $P_{\text{end}}$, the extreme limit price of the Dutch auction) and compared it directly to spot oracle price. For example, a taker buying SOL submitted $P_{\text{start}} = \$74.80$ and $P_{\text{end}} = \$60.00$ for a limit sell. The script evaluated the order as a $\$60.00$ instant trade vs $\$75.00$ spot, erroneously marking 100% of orders as "toxic flow". Correct market making requires evaluating $P(t)$ at projected landing slot!

### 3.4 Atomic Execution & On-Chain Instruction
* **Instruction:** `placeAndMakeSignedMsgPerpOrder` (or `getPlaceAndMakeSignedMsgPerpOrderIxs`).
* **Ed25519 Precompile Verification:**
  The Solana transaction must bundle an `Ed25519Program.createInstructionWithPublicKey` instruction verifying the taker's off-chain signature against the serialized message payload.
* **Instruction Index Alignment (`precedingIxs`):**
  The SDK computes the index of the Ed25519 verification instruction relative to the overall transaction instruction array. If adding compute-budget instructions (`ComputeBudgetProgram.setComputeUnitPrice`), they **must be passed as `precedingIxs`** to prevent silent verification failure on-chain.

### 3.5 Maker Rebate & Race Conditions
* **Maker Rebate:** Flat **0.25 bps (0.0025%)** of filled notional across standard volume tiers, paid to maker directly from taker fees.
* **Post-Only Requirement:** Maker order MUST carry `PostOnly` policy to ensure fill occurs as maker and captures the rebate.
* **Deduplication & Jito Auction Wars:**
  All active SWIFT market makers receive identical order packets over the WebSocket. Each maker generates a Solana transaction racing to land first. Only the first transaction processed in the slot succeeds; subsequent attempts revert with `OrderAlreadyFilled`. Makers must implement strict deduplication caches (`Set<orderSignature>`) and utilize Jito Bundles / dynamic priority fees to win the inclusion race without burning excessive compute budget fees on reverts.

---

## 4. Vector 3: Sui DeepBookV3 (H86) Deep Technical Specification

### 4.1 Architecture & Programmable Transaction Blocks (PTB)
* **Core Contract:** DeepBook V3 (`0x000000000000000000000000000000000000000000000000000000000000dee9` / `0xdee9`).
* **Sui JSON-RPC Deprecation Milestone:** Public Sui fullnodes have officially deprecated legacy JSON-RPC (`sui_getObject`, etc. return error `-32601` / `-32000`: *"Sui JSON-RPC endpoint has been deprecated. Please use the gRPC endpoint instead: https://sui-grpc.publicnode.com:443"*). All production integrations must utilize **gRPC** (`@mysten/sui/grpc` or gRPC clients) or **GraphQL** endpoints (`sui-mainnet.mystenlabs.com/graphql`).
* **PTB Execution:** Sui PTBs support up to 1,024 discrete Move operations executed sequentially in a single atomic transaction. Intermediate outputs pass seamlessly between commands without touching permanent global storage.
* **Deterministic Rollback:** If any command in the PTB aborts (e.g., minimum profit check fails or slippage exceeded), the **entire block reverts atomically**, consuming only minimal gas (~0.002 SUI = ~$0.002).

### 4.2 Hot Potato Flash Loan Pattern
* **Move Struct Definition:**
  ```move
  public struct FlashLoan<phantom BaseAsset, phantom QuoteAsset> {
      pool_id: ID,
      borrow_quantity: u64,
      type_asset: u8,
  }
  ```
  *Key Property:* This struct possesses **zero abilities** (no `copy`, no `drop`, no `store`, no `key`).
* **Enforced Execution Invariant:**
  Because the struct cannot be dropped or stored, the transaction verifier requires that it be consumed by the corresponding return function before transaction completion:
  * Borrow: `deepbook::pool::borrow_flashloan_base` or `borrow_flashloan_quote`
  * Return: `deepbook::pool::return_flashloan_base` or `return_flashloan_quote`
* **Flash Loan Fee:** Exactly **0.00% (0 bps)**. DeepBook V3 charges zero fees on uncollateralized flash loans.

### 4.3 Rectification of Mainnet Pools & Coin Types
The previous repository scan (`h86_onchain_orderbook.py`) reported DeepBook V3 as "completely illiquid" because it targeted deprecated Wormhole bridge pools (`wUSDC`) and used a synthetic dummy string for USDC. 

Authoritative addresses from `@mysten/deepbook-v3` (`packages/deepbook-v3/src/utils/constants.ts`):
* **Native Circle USDC Type:** `0xdba34672e30cb065b1f93e3ab55318768fd6fef66c15942c9f7cb846e2f900e7::usdc::USDC`
* **DEEP Governance Token Type:** `0xdeeb7a4662eec9f2f3def03fb937a663dddaa2e215b8078a284d026b7946c270::deep::DEEP`
* **Active Mainnet Pool Addresses:**
  * `SUI_USDC`: `0xe05dafb5133bcffb8d59f4e12465dc0e9faeaa05e3e342a08fe135800e3e4407`
  * `DEEP_SUI`: `0xb663828d6217467c8a1838a03793da896cbe745b150ebd57d82f814ca579fc22`
  * `DEEP_USDC`: `0xf948981b806057580f91622417534f491da5f61aeaf33d0ed8e69fd5691c95ce`
  * `WUSDC_USDC` (Peg Stability): `0xa0b9ebefb38c963fd115f52d71fa64501b79d1adcb5270563f92ce0442376545`
  * `WUSDT_USDC`: `0x4e2ca3988246e1d50b9bf209abb9c1cbfec65bd95afdacc620a36c67bdb8452f`

### 4.4 End-to-End Arbitrage PTB Pipeline
To execute zero-leg-risk cross-venue arbitrage (e.g., DeepBook V3 vs Cetus AMM):
1. `borrow_flashloan_quote`: Borrow $Q$ USDC from DeepBook V3 `SUI_USDC` pool -> yields `[usdc_coin, flash_loan_receipt]`.
2. `cetus::pool::swap`: Swap $Q$ USDC for $S$ SUI on Cetus AMM pool -> yields `sui_coin`.
3. `deepbook::balance_manager::deposit`: Deposit $S$ SUI into Balance Manager.
4. `deepbook::pool::place_market_order`: Sell $S$ SUI for $Q'$ USDC on DeepBook V3 book -> yields balance in Balance Manager.
5. `deepbook::balance_manager::withdraw`: Withdraw $Q'$ USDC.
6. `split_coin`: Split $Q'$ USDC into $Q$ (repayment) and $\Delta Q$ (profit).
7. `return_flashloan_quote`: Pass $Q$ USDC and `flash_loan_receipt` to clear the Hot Potato.
8. `transfer_coin`: Transfer $\Delta Q$ profit to trader wallet.
*Safety Guarantee:* If $Q' < Q$, step 6 fails, the Hot Potato is unconsumed, and the entire PTB reverts at minimal gas.

---

## 5. Vector 4: Kalshi FIX / AWS PrivateLink (H87) Deep Technical Specification

### 5.1 Regulatory Framework & Market Microstructure
* **Regulatory Status:** Designated Contract Market (DCM) regulated by the US Commodity Futures Trading Commission (CFTC) under the Commodity Exchange Act (CEA).
* **Contract Specification:** Binary event contracts settling at exactly **$1.00** (payout on YES outcome) or **$0.00** (NO outcome).
* **Pricing & Spreads:** Priced strictly in whole cents between **$0.01 and $0.99** (1¢ to 99¢). Minimum tick size is **$0.01**. Contract price reflects risk-neutral implied probability.
* **Microstructure:** Fully deterministic central limit order book (CLOB) with price-time priority.

### 5.2 FIX Protocol Specification
* **Transport Standard:** **FIXT.1.1** with Application Version **FIX50SP2** over TLS 1.2 or higher.
* **Session TargetCompIDs:**
  * `KalshiNR`: Order Entry Non-Retransmission (lowest possible latency, non-replaying).
  * `KalshiRT`: Order Entry with Retransmission (standard recovery session).
  * `KalshiMD`: Market Data distribution feed.
  * `KalshiDC`: Drop Copy session (real-time risk and trade audit).
* **SenderCompID:** The trader's API Key ID in **UUID format** (e.g., `a1b2c3d4-e5f6-7890-abcd-ef0123456789`).
* **Logon (`35=A`) Authentication:**
  * Tag `96` (`RawData`): Contains Base64-encoded digital signature of the logon timestamp.
  * Key Types: Ed25519 (recommended for lowest signing latency) or RSA-2048.
  * **Critical Syntax Rule:** Do NOT include `SenderSubID (Tag 50)` on Logon (`35=A`); sending Tag 50 during logon triggers an immediate `Logout (35=5)` disconnect. Tag 50 should only be passed on transactional messages (`35=D`, `35=F`).
  * **Concurrency Limit:** Strictly **one active FIX session per API key**. A secondary connection triggers `35=5 Logout` with text `"already exists"`.

### 5.3 AWS PrivateLink Architecture
* **Network Isolation:** Routes FIX, REST (`external-api.kalshi.com`), and WebSocket (`external-api-ws.kalshi.com`) traffic entirely across the AWS global backbone, bypassing public internet hops, transit providers, and Cloudflare CDN layers.
* **Deployment Region:** AWS **`us-east-1`** (Northern Virginia).
* **Latency Profile:** Sub-millisecond to ~2.5ms RTT from an EC2 instance in us-east-1, compared to 25–65ms over public internet with TLS renegotiation.
* **Access Prerequisites:** Requires **Premier Tier** or **Prime Tier** institutional membership (`institutional@kalshi.com`) and AWS Account ID whitelisting.

### 5.4 KYC & Compliance Restrictions
* **Mandatory Verification:** CFTC compliance mandates full KYC/AML verification (US SSN/EIN, residential verification, bank account linkage). Unverified or anonymous access is strictly blocked.
* **Testing Constraint:** Retail non-US developers cannot access live production order entry. An end-to-end testing pipeline must supply an **in-memory Kalshi FIX mock server** implementing FIXT.1.1/FIX50SP2 state transitions to validate algorithmic code.

---

## 6. Vector 5: dYdX v4 (CometBFT / L3 Orderbook) Deep Technical Specification

### 6.1 Architecture: Cosmos SDK & MemCLOB
* **Consensus Engine:** CometBFT (BFT proof-of-stake engine) providing deterministic single-slot instant finality (~0.8s to 1.1s block times).
* **In-Memory Orderbook (MemCLOB):**
  Unlike typical blockchains where orders are stored in state trees (RocksDB/IAVL), dYdX v4 validator nodes hold the active orderbook **entirely in RAM**.
* **Zero Gas Matching:** Placing, editing, and cancelling limit orders does NOT write to blockchain state and incurs **zero gas fees**.
* **Block Production Loop:**
  1. Orders are submitted to validator RPC and gossiped peer-to-peer across the validator network.
  2. The block proposer matches cross-orders deterministically in its local in-memory orderbook.
  3. The proposer includes matched executions and state updates into the proposed block.
  4. Validators replay and verify proposed matches against their local in-memory state; upon $\ge 2/3$ stake consensus, the block commits.

### 6.2 Level 3 (L3) Market Data Feed
* **L2 vs L3:** Public Indexer WebSockets (`wss://indexer.dydx.trade/v4/ws`) broadcast aggregated Level 2 (market-by-price) snapshots and updates.
* **Direct L3 Stream:** True Level 3 order-by-order telemetry (individual order IDs, order placement, discrete cancellation, partial fills, queue position) is accessible by running a local dYdX full node with `websocket-streaming-enabled` or gRPC streaming enabled on port `9090`.
* **Order Entry Gateway Service (OEGS):** Low-latency routing proxy used by institutional market makers to interface directly with validator mempools.

### 6.3 Fee Structure & Maker Rebate Tiers
Assessed dynamically on rolling 30-day USD trading volume:

| Tier | 30-Day Volume ($) | Taker Fee | Maker Fee / Rebate |
| :--- | :--- | :--- | :--- |
| **Tier 1** | < $1M | 5.0 bps (0.050%) | **+1.0 bps (0.010%)** |
| **Tier 2** | ≥ $1M | 4.5 bps (0.045%) | **+1.0 bps (0.010%)** |
| **Tier 3** | ≥ $5M | 4.0 bps (0.040%) | **+0.5 bps (0.005%)** |
| **Tier 4** | ≥ $25M | 3.5 bps (0.035%) | **0.0 bps (0.000%)** |
| **Tier 5** | ≥ $50M | 3.0 bps (0.030%) | **0.0 bps (0.000%)** |
| **Tier 6** | ≥ $100M | 2.5 bps (0.025%) | **-0.7 bps (-0.007% Rebate)** |
| **Tier 7** | ≥ $200M | 2.5 bps (0.025%) | **-1.1 bps (-0.011% Rebate)** |

Staking DYDX tokens unlocks an additional 5% to 40% net fee discount.

---

## 7. Vector 6: GMX v2 & Tier-2 CEXs (MEXC / Gate.io) Deep Technical Specification

### 7.1 GMX v2 & Chainlink Low-Latency Data Streams
* **Oracle Mechanism:** Replaced legacy push oracles with **Chainlink Data Streams** — pull-based, cryptographically signed price reports from a Decentralized Oracle Network (DON).
* **Two-Step Asynchronous Execution:**
  1. `OrderCreated`: Trader broadcasts order intent to `ExchangeRouter`, committing collateral and slippage boundary `acceptablePrice`.
  2. `ExecuteOrder`: Autonomous keeper bots retrieve the sub-second signed report from Chainlink Data Streams and submit the settlement transaction to `OrderHandler`.
* **Mitigation of Latency Frontrunning:**
  * In GMX v1, 1–3 second oracle delays permitted traders to frontrun CEX price shocks.
  * In GMX v2, the keeper passes a fresh report timestamped to the block. If the price moves past `acceptablePrice`, the order is rejected or cancelled. Dynamic price impact fees penalize any order that widens open interest imbalance.

### 7.2 Tier-2 CEXs: MEXC & Gate.io Specifications
* **MEXC Global:**
  * Endpoints: Spot REST `https://api.mexc.com`, Futures REST `https://contract.mexc.com`.
  * Fees: Standard spot maker is promotional **0.00%**, taker **0.05%** (5 bps). Futures baseline: **0.01%–0.02% maker, 0.06%–0.08% taker**.
  * Connectivity: No public testnet/sandbox available. WebSockets terminate after 30 seconds of inactivity if no channels are subscribed. Limit 30 subscriptions per socket.
* **Gate.io (API v4):**
  * Endpoints: Spot REST `https://api.gateio.ws/api/v4`, Spot WS `wss://api.gateio.ws/ws/v4/`, Futures WS `wss://fx-ws.gateio.ws/v4/ws/usdt`.
  * Latency: WebSocket v4 supports order placement and cancellation, reducing latency by **30% in Spot** and **40% in Futures** compared to REST.
  * Fees: VIP 0 base is 0.20% maker / 0.20% taker. High-tier Market Maker programs offer negative maker fees (rebates). Gate.io enforces an order-to-trade ratio (OTR) to penalize excessive order churn.
* **Capital Velocity & Transfer Latency:**
  Physical cross-venue arbitrage (withdrawing funds from MEXC/Gate.io to on-chain DEXs) suffers from **5 to 30+ minute cold-wallet batching delays**. Effective strategies must operate in a **synthetic delta-neutral regime** (e.g. maintaining pre-funded collateral on both venues and executing offsetting perpetual orders).

---

## 8. Features Discovered

| # | Category | Feature | Description | Inputs | Outputs | Error Behavior | Discovered Via |
|---|----------|---------|-------------|--------|---------|----------------|----------------|
| 1 | Hyperliquid | `split_client_blocks` | Eagerly writes uncommitted mempool transactions to disk 70–150ms before block finality | `~/override_gossip_config.json` | Stream at `~/hl/data/mempool_txs/{date}` | Inoperative if intermediate peers do not enable flag | `hyperliquid-dex/node` source |
| 2 | Hyperliquid | `Alo` Post-Only | Adds liquidity strictly as maker; auto-cancels if order crosses spread | `{"limit": {"tif": "Alo"}}` in order payload | Order resting on L2 book | Immediate cancellation if crossing spread | Hyperliquid Exchange API docs |
| 3 | Hyperliquid | Gossip Ports (4001, 4002) | Direct peer-to-peer protocol ports for node gossip | TCP/UDP ingress on 4001/4002 | Peer discovery and mempool tx exchange | Deprioritization / isolation by P2P network if closed | `hyperliquid-dex/node` specs |
| 4 | Velocity/Drift | SWIFT Feed | Off-chain signed taker order stream delivered 100–500ms before on-chain execution | WebSocket connect to `wss://swift.velocity.exchange/ws` | `SignedMsgOrderParamsMessage` packet | Disconnect / timeout on socket failure | `@velocity-exchange/sdk` docs |
| 5 | Velocity/Drift | `placeAndMakeSignedMsgPerpOrder` | Atomic Solana instruction matching signed taker order with maker fill | Taker order params, Ed25519 signature, maker order params | On-chain matched trade & fill event | Transaction revert if order already filled or invalid signature | `@velocity-exchange/sdk` source |
| 6 | Velocity/Drift | `precedingIxs` parameter | Aligns Ed25519 precompile instruction index when compute budget instructions are prepended | Array of `TransactionInstruction` | Adjusted verification instruction offset | Silent Ed25519 verification failure if omitted | Velocity Protocol SDK docs |
| 7 | Sui DeepBook | Hot Potato Flash Loan | Uncollateralized loan with 0 bps fee requiring same-PTB return | `borrow_flashloan_base` / `borrow_flashloan_quote` | Assets + `FlashLoan` receipt struct | Complete PTB abort if receipt not returned | MystenLabs `deepbookv3` Move code |
| 8 | Sui DeepBook | Native Pool Constants | Official mainnet CLOB pool IDs for Circle USDC and DEEP token pairs | `0xe05dafb5...` (SUI/USDC), `0xb663828d...` (DEEP/SUI) | Real-time orderbook bids and asks | Revert / empty object if querying deprecated Wormhole IDs | `@mysten/deepbook-v3` SDK |
| 9 | Kalshi | FIX Session TargetCompIDs | Dedicated session targets for low-latency non-retransmission, market data, and drop copy | `TargetCompID (56)`: `KalshiNR`, `KalshiRT`, `KalshiMD`, `KalshiDC` | Authenticated FIX session | Session rejection (`35=5 Logout`) if target mismatch | Kalshi FIX API Documentation |
| 10 | Kalshi | Ed25519 FIX Logon Signature | Cryptographic signature in Tag 96 (`RawData`) on Logon (`35=A`) | Timestamp signed by Ed25519/RSA private key | `35=A Logon` response | Disconnect with `35=5 Logout` if signature invalid | Kalshi FIX Protocol Spec |
| 11 | Kalshi | AWS PrivateLink Dedicated Connect | Interface VPC endpoints in AWS us-east-1 for sub-millisecond private routing | Dedicated VPC Endpoint DNS / Port 443 | Private route to FIX/REST/WS gateways | Connection refused if AWS account not whitelisted | Kalshi Infrastructure Docs |
| 12 | dYdX v4 | In-Memory MemCLOB | Off-chain order matching in validator RAM with zero gas fees | P2P gossiped order transactions | Deterministic block execution batch | Transaction discarded if nonce/balance invalid | dYdX v4 Architecture Docs |
| 13 | dYdX v4 | L3 Node Streaming Feed | Order-by-order book stream with individual order IDs from local full node | Full node flag `websocket-streaming-enabled` / gRPC port 9090 | Order additions, cancels, modifications | High memory consumption if unbuffered | dYdX Chain Repository |
| 14 | GMX v2 | Chainlink Data Streams Pull Oracle | Cryptographically signed high-frequency price reports verified on-chain | DON signed price report payload | Validated execution price for `OrderHandler` | Revert if report timestamp exceeds execution window | Chainlink & GMX v2 Docs |
| 15 | GMX v2 | `acceptablePrice` Guard | Slippage barrier set by trader during asynchronous two-step execution | Price limit in `CreateOrder` | Filled position or refund | Order cancelled if market crosses acceptable boundary | GMX v2 ExchangeRouter Spec |
| 16 | Gate.io | WebSocket v4 Trading | Full order management (create, amend, cancel) over persistent WebSocket | Authenticated WS JSON frames | Execution confirmation with 30–40% lower latency | `429` or disconnection on rate limit breach | Gate.io API v4 Developer Guide |

---

## 9. Edge Cases & Protocol Nuances

| # | Feature | Input / Condition | Observed / Documented Behavior |
|---|---------|-------------------|--------------------------------|
| 1 | Hyperliquid `split_client_blocks` | Intermediate peer node running standard config (`split_client_blocks: false`) | Uncommitted mempool streaming silently fails to write to disk. `split_client_blocks` must be enabled across all hops up to validators. |
| 2 | Hyperliquid Order Placement | Trader passes `Alo` flag with price crossing the inside spread | Exchange instantly rejects/cancels the order. No taker fees are incurred, avoiding accidental crossing. |
| 3 | Hyperliquid Retail MM | Retail trader operating MM bot at Tier 0 volume | Every maker fill incurs a **+1.5 bps fee**, resulting in negative net EV unless spread capture exceeds 3.0 bps round-trip. |
| 4 | Velocity SWIFT Auction | Evaluating `params.price` directly against spot oracle | Misinterprets Dutch auction end price ($P_{\text{end}}$) as a 2000 bps price deviation. Math must evaluate $P(t)$ using `auctionStartPrice` and `auctionDuration`. |
| 5 | Velocity SWIFT Verification | Prepending ComputeBudget instructions without setting `precedingIxs` | Ed25519 precompile instruction index mismatch occurs on-chain, causing transaction to fail silently or revert with `InvalidInstructionData`. |
| 6 | Velocity SWIFT Competition | Multiple MMs submit competing fills for the same SWIFT message | Only the first transaction lands in the Solana slot; competing transactions fail on-chain, forfeiting compute priority fees. |
| 7 | Sui DeepBook Flash Loan | Arbitrage swap returns less than borrowed amount | Withdrawing repayment from Balance Manager fails; `return_flashloan` is not reached; Hot Potato is unconsumed; entire PTB reverts at ~0.002 SUI gas. |
| 8 | Sui DeepBook Asset Types | Passing Wormhole USDC (`wUSDC`) instead of native Circle USDC | Targets an illiquid, unmaintained legacy pool with artificial 11,000 bps bid-ask spreads. Real native USDC pool (`0xe05dafb5...`) has tight liquidity. |
| 9 | Kalshi FIX Logon | Sending Tag 50 (`SenderSubID`) in Logon (`35=A`) message | Kalshi gateway immediately rejects connection and sends `35=5 Logout`. Tag 50 must only be passed in transactional messages. |
| 10 | Kalshi FIX Concurrency | Initiating a second FIX session with an already connected API key | Kalshi gateway immediately disconnects the second connection with `35=5 Logout (Text: "already exists")`. |
| 11 | dYdX v4 memCLOB | Block proposer includes invalid or divergent order match | Peer validators replaying matching against local in-memory orderbook detect invalid state and reject the block proposal during CometBFT round. |
| 12 | GMX v2 Execution | Fast CEX price move shifts oracle beyond `acceptablePrice` | Keeper executes `executeOrder`, but contract evaluates current oracle price vs `acceptablePrice`; order is aborted or cancelled without slippage. |
| 13 | Gate.io WebSocket | Algorithmic account submits hundreds of empty order cancels without fills | Gate.io Order-to-Trade Ratio (OTR) monitor flags the account, imposing severe rate limit throttling or IP connection bans. |

---

## 10. Comparative Feasibility & Edge Assessment

| Vector | Edge Hypothesis | Authoritative Feasibility Finding | Implementation Path for End-to-End Software |
| :--- | :--- | :--- | :--- |
| **H84 (Hyperliquid)** | Mempool toxic flow avoidance via non-validator node gossip feed | **Feasible only with Tokyo hardware (16 vCPU, 128GB RAM)**. In US East, network RTT destroys the 70–150ms lead time. At Tier 0, +1.5 bps maker fee requires >3 bps spread capture. | Build local mempool parser module reading `mempool_txs` stream with `Alo` post-only flags. Provide benchmark simulation against Tokyo vs US East latency traces. |
| **H85 (Velocity / Drift)** | Taker intent preview (100–500ms) with 0.25 bps maker rebate | **Confirmed Feasible**. SDK transitioned to `@velocity-exchange/sdk` and USDT quote. Prior "toxic flow" classification was an auction pricing bug. | Implement SWIFT listener with dynamic Dutch auction calculation $P(t)$, Ed25519 precompile alignment (`precedingIxs`), and fast deduplication cache. |
| **H86 (Sui DeepBook)** | Atomic triangular arbitrage with zero leg risk via Hot Potato PTB | **Confirmed Feasible**. Flash loan fee is 0 bps. Prior "illiquid pool" conclusion was caused by targeting deprecated Wormhole `wUSDC` instead of native USDC (`0xe05dafb5...`). | Construct end-to-end PTB assembling DeepBook flash loan borrow -> Cetus AMM swap -> DeepBook CLOB market fill -> flash loan return with atomic rollback. |
| **H87 (Kalshi FIX)** | Sub-millisecond latency prediction arb via FIX & AWS PrivateLink | **Architecturally Feasible, Regulated Gatekeeping**. CFTC KYC required. PrivateLink requires Premier/Prime tier. | Build dual-mode connector: full FIXT.1.1/FIX50SP2 client with Ed25519 authentication, supported by an internal high-fidelity mock engine for unblocked testing. |
| **dYdX v4 (CometBFT)** | High-frequency zero-gas market making via in-memory orderbook | **Confirmed Feasible**. Off-chain in-memory matching; L3 data accessible via full node streaming. Maker rebates require Tier 6+ ($100M+). | Implement Cosmos SDK gRPC/WebSocket client streaming L3 data and submitting signed CLOB order transactions with sub-second finality handling. |
| **GMX v2 / CEXs** | Oracle latency arbitrage vs Tier-2 CEX fast feeds | **Refuted as simple arb; Valid as synthetic hedge**. GMX v2 pull oracles (Chainlink Data Streams) and price impact eliminate stale price exploitation. | Implement synthetic delta-neutral market maker hedging between GMX v2 and Gate.io/MEXC WebSockets, avoiding physical on-chain deposit/withdrawal delays. |

---

## 11. Authoritative References & Timestamped Sources

1. **Hyperliquid Node & Architecture:**
   - Repository: `https://github.com/hyperliquid-dex/node` (Commit specs for Ubuntu 24.04, ports 4001/4002, hardware requirements).
   - Docs: `https://hyperliquid.gitbook.io/hyperliquid-docs` (Fee tiers, ALO post-only, `split_client_blocks` override gossip).
2. **Velocity Exchange / Drift Protocol:**
   - Package: `@velocity-exchange/sdk` (v0.6.1, TypeScript SDK, `SwiftOrderSubscriber`).
   - Program: `vELoC1audYbSYVRXn1vPaV8Axoa9oU6BYmNGZZBDZ1P` (Solana mainnet deployment).
   - Documentation: `https://docs.velocity.exchange` (SWIFT signed-message architecture, Dutch auctions, maker rebates).
3. **Sui DeepBook V3:**
   - Repository: `https://github.com/MystenLabs/deepbookv3` (Move contracts, Hot Potato flash loan implementation).
   - TypeScript SDK: `@mysten/deepbook-v3` in `MystenLabs/ts-sdks` (`packages/deepbook-v3/src/utils/constants.ts`).
   - Addresses: Native USDC `0xdba34672...`, SUI/USDC Pool `0xe05dafb5...`.
4. **Kalshi FIX & Connectivity:**
   - Documentation: `https://kalshi-fix.mintlify.app/` & `https://trading-api.kalshi.com/trade-api/v2/docs` (FIX50SP2, Tag 96 Ed25519 logon, AWS PrivateLink).
   - Regulatory Rules: CFTC DCM Rule 38 filings for event contracts.
5. **dYdX v4 Chain:**
   - Repository: `https://github.com/dydxprotocol/v4-chain` (Cosmos SDK `x/clob`, `x/perpetuals`, in-memory orderbook).
   - Documentation: `https://docs.dydx.exchange` (MemCLOB, full node L3 streaming, fee tiers).
6. **GMX v2 & Tier-2 CEXs:**
   - GMX v2 Docs: `https://gmxio.gitbook.io/gmx/v/v2/` (Chainlink Data Streams, `acceptablePrice`, `OrderCreated` / `ExecuteOrder`).
   - Gate.io API v4: `https://www.gate.io/docs/developers/apiv4/` (WebSocket v4 trading, OTR rate limits).
   - MEXC Developer Hub: `https://mexcdevelop.github.io/apidocs/spot_v3_en/` (REST/WS specs, fee structures).
