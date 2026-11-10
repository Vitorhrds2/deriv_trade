# Progress — Survey 3: Connectivity, Credentials & KYC Feasibility

Last visited: 2026-11-03T04:39:15Z

## Status
- [x] Initialized workspace and briefing.
- [x] Run comprehensive live network connectivity probes (REST and WebSocket) across all 7 target venues.
  - Hyperliquid: Mainnet/Testnet REST & WS 100% verified (sub-400ms REST, 804ms WS).
  - Drift / Velocity: Legacy drift domains migrated; Velocity SWIFT WS verified with Ed25519 auth challenge over `wss://swift.velocity.exchange/ws?pubkey=...` (814ms).
  - Sui DeepBookV3: Critical discovery — Sui public fullnodes deprecated legacy JSON-RPC (`-32601`); verified active Sui GraphQL RPC (`graphql.mainnet.sui.io` & `graphql.testnet.sui.io`) and official DeepBook V3 mainnet packages and active SUI/USDC pool (`0xe05dafb5...`).
  - Kalshi: Verified migration from `trading-api.kalshi.com` to `api.elections.kalshi.com`; verified TLS handshake to live and demo FIX gateways (`mm.fix.elections.kalshi.com:8228`, `marketdata.fix.elections.kalshi.com:8233`, `fix.demo.kalshi.co:8228`).
  - dYdX v4: Public indexer REST & WS orderbook feeds 100% verified (sub-100ms L2 orderbook, CometBFT node info active).
  - GMX v2 & CEXs Tier-2: Arbitrum RPC & GMX synthetics API verified; MEXC and Gate.io REST & WS verified.
- [x] Analyzed KYC, CFTC, legal restrictions, and browser accessibility across all platforms.
- [x] Evaluated permissionless testnets vs authenticated credentials and identified `.gitignore` safe storage.
- [x] Defined complete mock/emulation architecture for blocked venues (Kalshi CFTC / AWS PrivateLink / CEX KYC).
- [x] Compiled comprehensive `connectivity_credentials_audit.md`.
- [x] Produced standard 5-component `handoff.md`.
- [x] Sent final report message to orchestrator.
