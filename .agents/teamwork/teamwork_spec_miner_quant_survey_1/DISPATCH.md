# Dispatch: Survey 1 — Protocol Specifications & Documentation Audit

## Objective
Thoroughly survey and mine the official specifications, protocol architectures, documentation, APIs, and technical blogs for all 6 target vectors:
1. Hyperliquid (H84): L1 architecture, non-validator node gossip protocol, `split_client_blocks:true`, mempool visibility (70-150ms before finality), toxic flow avoidance, post-only / ALO flags, maker rebates, hardware requirements (CPU/RAM), REST/WS latency benchmarks.
2. Drift Protocol / Velocity Exchange (H85): SWIFT WebSocket API, taker intent preview (100-500ms before on-chain execution), quote asset migration (USDC vs USDT), `@velocity-exchange/sdk` vs `@drift-labs/sdk`, market making rebate, price precision/scale (e.g. 1e6), deduplication & race conditions.
3. Sui DeepBookV3 (H86): Programmable Transaction Blocks (PTB), Hot Potato pattern for atomic execution without flash loan fees/leg risk, liquidity pool types (SUI/USDC, SUI/USDT, DeepBook V3 pools), maker rebate & taker fee tiers, on-chain RPC vs AMMs (Cetus/Kriya).
4. Kalshi FIX / AWS PrivateLink (H87): CFTC-regulated prediction markets, FIX protocol (specifications, tags, session management), AWS PrivateLink direct connect vs public REST/WS, latency profile, microstructure (order book dynamics, contract pricing 0-100 cents), KYC requirements and regulatory restrictions.
5. dYdX v4 (CometBFT / L3 orderbook): dYdX Chain architecture, off-chain validator in-memory orderbook matching, block-level consensus, L3 market data feed (WebSocket/gRPC), sub-second finality, maker rebates and taker fees.
6. GMX v2 & Tier-2 CEXs (MEXC / Gate.io): Chainlink Low-Latency Data Streams on GMX v2, oracle frontrunning / latency arbitrage dynamics vs CEX index updates, Tier-2 CEX API latencies, maker/taker fee friction, withdrawal/deposit latency.

## Inputs
- Authoritative User Request: `/Users/vitorhrds/Documents/Github/hypothesis/.agents/teamwork/ORIGINAL_REQUEST.md`
- Use web search (`search_web`), URL reading (`read_url_content`), and developer docs tools to verify official sources with up-to-date timestamps.

## Output Requirements
- Write your comprehensive audit report to:
  `/Users/vitorhrds/Documents/Github/hypothesis/.agents/teamwork/teamwork_spec_miner_quant_survey_1/protocol_specs_audit.md`
- Write your handoff report following the standard Handoff Protocol to:
  `/Users/vitorhrds/Documents/Github/hypothesis/.agents/teamwork/teamwork_spec_miner_quant_survey_1/handoff.md`
- Update `progress.md` with timestamps for liveness.

## 2026-11-03T04:24:09Z
You are teamwork_spec_miner_quant_survey_1.
Your working directory is: /Users/vitorhrds/Documents/Github/hypothesis/.agents/teamwork/teamwork_spec_miner_quant_survey_1
Read your task dispatch at /Users/vitorhrds/Documents/Github/hypothesis/.agents/teamwork/teamwork_spec_miner_quant_survey_1/DISPATCH.md
Read the authoritative user request at: /Users/vitorhrds/Documents/Github/hypothesis/.agents/teamwork/ORIGINAL_REQUEST.md

Task:
Perform a deep technical specification audit across official documentation, APIs, and protocol architectures for the 6 target vectors:
1. Hyperliquid (H84): L1 architecture, non-validator node gossip protocol, `split_client_blocks:true`, mempool visibility (70-150ms before finality), toxic flow avoidance, post-only / ALO flags, maker rebates, hardware requirements (CPU/RAM), REST/WS latency benchmarks.
2. Drift Protocol / Velocity Exchange (H85): SWIFT WebSocket API, taker intent preview (100-500ms before on-chain execution), quote asset migration (USDC vs USDT), `@velocity-exchange/sdk` vs `@drift-labs/sdk`, market making rebate, price precision/scale (e.g. 1e6), deduplication & race conditions.
3. Sui DeepBookV3 (H86): Programmable Transaction Blocks (PTB), Hot Potato pattern for atomic execution without flash loan fees/leg risk, liquidity pool types (SUI/USDC, SUI/USDT, DeepBook V3 pools), maker rebate & taker fee tiers, on-chain RPC vs AMMs (Cetus/Kriya).
4. Kalshi FIX / AWS PrivateLink (H87): CFTC-regulated prediction markets, FIX protocol (specifications, tags, session management), AWS PrivateLink direct connect vs public REST/WS, latency profile, microstructure (order book dynamics, contract pricing 0-100 cents), KYC requirements and regulatory restrictions.
5. dYdX v4 (CometBFT / L3 orderbook): dYdX Chain architecture, off-chain validator in-memory orderbook matching, block-level consensus, L3 market data feed (WebSocket/gRPC), sub-second finality, maker rebates and taker fees.
6. GMX v2 & Tier-2 CEXs (MEXC / Gate.io): Chainlink Low-Latency Data Streams on GMX v2, oracle frontrunning / latency arbitrage dynamics vs CEX index updates, Tier-2 CEX API latencies, maker/taker fee friction, withdrawal/deposit latency.

Use web search and URL reading to verify the latest official documentation, GitHub repos, and timestamped API specs.
Write your full findings to:
/Users/vitorhrds/Documents/Github/hypothesis/.agents/teamwork/teamwork_spec_miner_quant_survey_1/protocol_specs_audit.md
Write your handoff report to:
/Users/vitorhrds/Documents/Github/hypothesis/.agents/teamwork/teamwork_spec_miner_quant_survey_1/handoff.md
When finished, send a message to the orchestrator with your summary and file path.
