# BRIEFING — 2026-11-03T04:26:00Z

## Mission
Perform a deep technical specification audit across official documentation, APIs, and protocol architectures for 6 target vectors (Hyperliquid, Drift/Velocity SWIFT, Sui DeepBookV3, Kalshi FIX/PrivateLink, dYdX v4 CometBFT/L3, GMX v2 Data Streams & Tier-2 CEXs).

## 🔒 My Identity
- Archetype: teamwork_spec_miner
- Roles: Specification Miner, Quant Infrastructure Auditor
- Working directory: /Users/vitorhrds/Documents/Github/hypothesis/.agents/teamwork/teamwork_spec_miner_quant_survey_1
- Original parent: 784b07d9-8c51-454a-ae17-d0ee1ce5f483
- Milestone: Survey 1 — Protocol Specifications & Documentation Audit

## 🔒 Key Constraints
- Read-only miner: do NOT implement runtime code or bots in this turn, discover and document features by probing authoritative specifications.
- Must cover all 6 target vectors in exhaustive technical depth.
- Authoritative sources prioritized: official documentation, GitHub repositories, API specifications, and timestamped protocol specs.
- Provide structured output in `protocol_specs_audit.md` and standard 5-component handoff in `handoff.md`.
- Keep heartbeat updated in `progress.md`.

## Current Parent
- Conversation ID: 784b07d9-8c51-454a-ae17-d0ee1ce5f483
- Updated: 2026-11-03T04:26:00Z

## Task Summary
- **What to build**: Full technical specification audit report across 6 target vectors with detailed architecture, API endpoints, message schemas, latency metrics, fee schedules, edge cases, and hardware requirements.
- **Success criteria**: Comprehensive `protocol_specs_audit.md` covering all 6 vectors with features discovered table, edge cases table, and authoritative references, plus `handoff.md`.
- **Interface contracts**: `/Users/vitorhrds/Documents/Github/hypothesis/.agents/teamwork/ORIGINAL_REQUEST.md` and `DISPATCH.md`.
- **Code layout**: Metadata and reports strictly in `.agents/teamwork/teamwork_spec_miner_quant_survey_1/`.

## Key Decisions Made
- Audit systematically parsed official docs, GitHub source codes, and API specifications for each vector:
  1. Hyperliquid: Confirmed `split_client_blocks:true` mempool streaming (70-150ms lead time) to `mempool_txs/{date}`; co-location in Tokyo mandatory; Tier 0 retail maker fee is +1.5 bps.
  2. Velocity / Drift SWIFT: Identified that previous "2000 bps toxic deviation" was an auction pricing bug evaluating $P_{\text{end}}$ instead of $P(t)$; verified flat 0.25 bps maker rebate and USDT quote asset.
  3. Sui DeepBookV3: Uncovered that previous "illiquid pool" conclusion was an artifact of testing deprecated Wormhole test pools and dummy coin strings; verified real Circle USDC pool (`0xe05dafb5...`) and 0 bps Hot Potato flash loans; noted Sui JSON-RPC deprecation to gRPC/GraphQL.
  4. Kalshi FIX / PrivateLink: Documented FIXT.1.1/FIX50SP2, `KalshiNR` session, Tag 96 Ed25519 logon, and AWS PrivateLink VPC endpoint specs; designed mock testing strategy for CFTC KYC bypass.
  5. dYdX v4: Documented Cosmos SDK memCLOB (in-memory book), zero-gas order matching, full node L3 streaming, and tiered rebates.
  6. GMX v2 & Tier-2 CEXs: Documented Chainlink pull oracles preventing latency frontrunning; documented Gate.io WebSocket v4 and MEXC 0% spot maker; identified CEX cold-wallet delays requiring synthetic delta-neutral execution.

## Artifact Index
- `protocol_specs_audit.md` — Detailed protocol specification audit
- `handoff.md` — 5-component handoff report
- `progress.md` — Heartbeat and activity log
