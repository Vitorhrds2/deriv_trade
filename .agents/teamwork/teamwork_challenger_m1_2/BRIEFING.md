# BRIEFING — 2026-11-10T02:57:00Z

## Mission
Milestone M1 Adversarial Verification: PTB Structural Invariants, Serialization, and GraphQL Resilience (`trading-engine/venues/sui_deepbook_venue.py`).

## 🔒 My Identity
- Archetype: empirical challenger
- Roles: critic, specialist
- Working directory: /Users/vitorhrds/Documents/Github/hypothesis/.agents/teamwork/teamwork_challenger_m1_2/
- Original parent: bb8c036e-693a-4192-a9f6-25494af55dae
- Milestone: M1
- Instance: 2 of 2 (teamwork_challenger_m1_2)

## 🔒 Key Constraints
- Review-only — do NOT modify implementation code
- Run verification code directly (empirical challenge)
- Do NOT trust worker claims or logs
- .agents/teamwork/ must contain only metadata — no source or test files
- Communicate via send_message to bb8c036e-693a-4192-a9f6-25494af55dae

## Current Parent
- Conversation ID: bb8c036e-693a-4192-a9f6-25494af55dae
- Updated: not yet

## Review Scope
- **Files to review**: `trading-engine/venues/sui_deepbook_venue.py`, `trading-engine/tests/test_adversarial_challenger_2.py`
- **Interface contracts**: `.agents/teamwork/ORIGINAL_REQUEST.md`, `.agents/teamwork/PROJECT.md`
- **Review criteria**: PTB structural invariants, serialization, GraphQL resilience under faults, backward compatibility

## Key Decisions Made
- Added `TestSuiM1ChallengerStructuralInvariantsAndResilience` in `trading-engine/tests/test_adversarial_challenger_2.py` containing 18 rigorous adversarial tests.
- Tested all 12 combinations of 4 pairs and 3 tiers (1k, 5k, 10k) verifying all 8 commands, positional arguments, and Hot Potato links.
- Tested GraphQL client resilience against HTTP 500, network timeouts, malformed JSON, and empty responses.
- Verified 100% backward compatibility of zero-argument `HotPotatoPTBParams()` calls.
- Rendered explicit verdict: APPROVE.

## Artifact Index
- `.agents/teamwork/teamwork_challenger_m1_2/BRIEFING.md` — persistent context
- `.agents/teamwork/teamwork_challenger_m1_2/DISPATCH.md` — dispatch history
- `.agents/teamwork/teamwork_challenger_m1_2/progress.md` — progress heartbeat
- `.agents/teamwork/teamwork_challenger_m1_2/analysis.md` — detailed challenge analysis
- `.agents/teamwork/teamwork_challenger_m1_2/handoff.md` — 5-component handoff report

## Attack Surface
- **Hypotheses tested**:
  - PTB command index alignment breaks when scaling borrow amounts across pairs: REJECTED (all 12 combinations passed).
  - Calling PTB builder without arguments alters legacy PTB output: REJECTED (100% identical).
  - GraphQL 500 or timeout causes unhandled process crash: REJECTED (clean exceptions raised).
  - Empty wallet balance response causes unhandled parsing exception: REJECTED (parsed cleanly to 0).
- **Vulnerabilities found**:
  - `addr_data.get("sui", {}).get(...)` raises `AttributeError` if `sui` is `None` in GraphQL response (Finding 1).
  - `_sync_exec` fallback does not validate `"errors" in data` before returning (Finding 2).
- **Untested angles**:
  - Live on-chain PTB execution against Sui Mainnet RPC validator nodes (requires active funded wallet and live BalanceManager).

## Loaded Skills
None requested in dispatch.
