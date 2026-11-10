# Dispatch: Survey 3 — Connectivity, Credentials & KYC Feasibility

## Objective
Assess connectivity, API endpoints, testnets, credentials, browser accessibility, and KYC / legal restrictions for each target venue:
1. Test/verify public API endpoints and WebSocket connectivity for:
   - Hyperliquid (testnet / mainnet public endpoints: `api.hyperliquid.xyz`, `api.hyperliquid-testnet.xyz`, WebSocket `api.hyperliquid.xyz/ws`)
   - Drift / Velocity Exchange (Solana RPC, SWIFT WS endpoint `wss://master.swift.drift.trade` or Velocity equivalent)
   - Sui DeepBookV3 (Sui public RPC `fullnode.mainnet.sui.io`, testnet, package IDs)
   - Kalshi (Public demo API `demo-api.kalshi.co`, REST endpoints, FIX port/gateway requirements, CFTC KYC constraints, AWS PrivateLink requirements)
   - dYdX v4 (Public indexer endpoints `indexer.dydx.trade`, testnet, WebSocket orderbook feeds)
   - GMX v2 & CEXs Tier-2 (Arbitrum RPC, GMX data streams, MEXC `/api/v3/`, Gate.io `/api/v4/`)
2. Identify credential requirements:
   - Which platforms allow permissionless testnet / paper trading (Hyperliquid testnet wallet, Sui testnet wallet, Drift devnet, Kalshi demo)?
   - Which platforms require KYC, CFTC registration, or paid enterprise cross-connects (Kalshi live, AWS PrivateLink)?
   - Document safe storage locations for credentials within workspace (e.g. `.env.local` / non-committed files).
   - Define the mock/emulation architecture required when live access is blocked by KYC or paid infrastructure.

## Inputs
- Authoritative User Request: `/Users/vitorhrds/Documents/Github/hypothesis/.agents/teamwork/ORIGINAL_REQUEST.md`
- Network testing, curl/python probe capabilities.

## Output Requirements
- Write your comprehensive connectivity and credentials audit report to:
  `/Users/vitorhrds/Documents/Github/hypothesis/.agents/teamwork/teamwork_explorer_quant_survey_3/connectivity_credentials_audit.md`
- Write your handoff report following the standard Handoff Protocol to:
  `/Users/vitorhrds/Documents/Github/hypothesis/.agents/teamwork/teamwork_explorer_quant_survey_3/handoff.md`
- Update `progress.md` with timestamps for liveness.
- Notify the orchestrator via `send_message` with your summary and file path when done.


## 2026-11-03T04:24:32Z
Received from orchestrator (784b07d9-8c51-454a-ae17-d0ee1ce5f483):
Assess connectivity, API endpoints, testnets, credentials, browser accessibility, and KYC / legal restrictions for each target venue:
1. Test/verify public API endpoints and WebSocket connectivity for:
   - Hyperliquid (testnet / mainnet public endpoints: `api.hyperliquid.xyz`, `api.hyperliquid-testnet.xyz`, WebSocket `api.hyperliquid.xyz/ws`)
   - Drift / Velocity Exchange (Solana RPC, SWIFT WS endpoint `wss://master.swift.drift.trade` or Velocity equivalent)
   - Sui DeepBookV3 (Sui public RPC `fullnode.mainnet.sui.io`, testnet, package IDs)
   - Kalshi (Public demo API `demo-api.kalshi.co`, REST endpoints, FIX port/gateway requirements, CFTC KYC constraints, AWS PrivateLink requirements)
   - dYdX v4 (Public indexer endpoints `indexer.dydx.trade`, testnet, WebSocket orderbook feeds)
   - GMX v2 & CEXs Tier-2 (Arbitrum RPC, GMX data streams, MEXC `/api/v3/`, Gate.io `/api/v4/`)
2. Identify credential requirements:
   - Which platforms allow permissionless testnet / paper trading (Hyperliquid testnet wallet, Sui testnet wallet, Drift devnet, Kalshi demo)?
   - Which platforms require KYC, CFTC registration, or paid enterprise cross-connects (Kalshi live, AWS PrivateLink)?
   - Document safe storage locations for credentials within workspace (e.g. `.env.local` / non-committed files).
   - Define the mock/emulation architecture required when live access is blocked by KYC or paid infrastructure.


## 2026-11-03T04:35:32Z
Received from orchestrator (784b07d9-8c51-454a-ae17-d0ee1ce5f483):
**Context**: Survey 3 (Connectivity, Credentials & KYC Feasibility)
**Content**: Heartbeat and safety check. Survey 1 and Survey 2 have generated their audit reports. Please report your current progress on the connectivity probes, KYC/credential analysis, and mock/emulation architecture.
**Action**: Update your progress.md and provide status or complete your audit report.
