# Dispatch: Survey 2 — Repository Audit & Existing Implementation Mapping

## 2026-11-03T04:24:20Z

### Objective
Conduct a deep technical audit of the local repository to assess what is already implemented, tested, or measured:
1. Inspect `docs/state_of_research.md` (specifically lines 1190-1242 and any related sections on H84-H87, HFT, latency, CEX arb).
2. Inspect existing scripts and data files in `trading-engine/`:
   - `h84_hyperliquid_gossip_feasibility.py` & `.json`
   - `h85_continuous.sh`, `h85_drift/`, `h85_drift_swift_maker_rebate*`
   - `h86_sui/` (`h86_onchain_orderbook.py`, `h86_deepbook_execute.ts`, `h86_deepbook_scan.ts`, etc.)
   - `trading-engine/venues/` (`base.py`, `registry.py`, `jupiter_prediction.py`, etc.)
   - `docs/venue_adapter_design.md`, `docs/phantom_ecosystem_findings.md`, `docs/polymarket_dev_reference.md`
   - `agentic-conversation/` (relay, telegram, bot runners)
3. Map the exact delta: what exists vs what is required for end-to-end execution and empirical simulation of H84, H85, H86, H87, dYdX v4, and GMX v2 / Tier-2 CEXs.

### Inputs
- Authoritative User Request: `/Users/vitorhrds/Documents/Github/hypothesis/.agents/teamwork/ORIGINAL_REQUEST.md`
- Target Codebase paths in `/Users/vitorhrds/Documents/Github/hypothesis/`

### Output Requirements
- Write your comprehensive repository mapping report to:
  `/Users/vitorhrds/Documents/Github/hypothesis/.agents/teamwork/teamwork_explorer_quant_survey_2/repo_audit_mapping.md`
- Write your handoff report following the standard Handoff Protocol to:
  `/Users/vitorhrds/Documents/Github/hypothesis/.agents/teamwork/teamwork_explorer_quant_survey_2/handoff.md`
- Update `progress.md` with timestamps for liveness.
- Notify the orchestrator via `send_message` with your summary and file path when done.
