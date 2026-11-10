# Dispatch: Challenger 2 — Adversarial Stress Testing (Fee Friction, Atomic Reversion & Slippage)

## Objective
Perform code-executing adversarial verification on mathematical edge, fee friction, and mechanical protections:

1. Design and execute an adversarial test harness (`trading-engine/tests/test_adversarial_challenger_2.py`):
   - Sui DeepBookV3 Hot Potato atomic reversion: Verify that when simulated AMM slippage causes an unprofitable swap, the PTB dryRun strictly fails with `INSUFFICIENT_BALANCE` and leaves zero lingering debt or state corruption.
   - GMX v2 dynamic price impact fee explosion: Verify that huge order sizes incur punitive fees exceeding edge, and acceptablePrice slippage ceiling cleanly cancels orders.
   - Velocity SWIFT Dutch auction pricing at extreme boundary timestamps (negative timestamps, huge future offsets, zero durations).
   - Maker rebate vs taker fee inversion: Verify that orders placed without ALO flag or with taker intent correctly incur positive fees and cannot claim negative fee rebates.
2. Run pytest on your adversarial tests using `trading-engine/.venv/bin/pytest`.
3. Verify that all mechanical protections hold deterministically.
4. Issue a formal verdict: **APPROVE** or **REQUEST_CHANGES**.


## 2026-11-03T05:30:26Z
[Message] timestamp=2026-11-03T05:30:26Z sender=784b07d9-8c51-454a-ae17-d0ee1ce5f483 priority=MESSAGE_PRIORITY_HIGH content=You are teamwork_challenger_m4_2.
Your working directory is: /Users/vitorhrds/Documents/Github/hypothesis/.agents/teamwork/teamwork_challenger_m4_2
Read your task dispatch at /Users/vitorhrds/Documents/Github/hypothesis/.agents/teamwork/teamwork_challenger_m4_2/DISPATCH.md
Read the authoritative user request at: /Users/vitorhrds/Documents/Github/hypothesis/.agents/teamwork/ORIGINAL_REQUEST.md
Read PROJECT.md at: /Users/vitorhrds/Documents/Github/hypothesis/.agents/teamwork/PROJECT.md

Build adversarial stress test harness in `trading-engine/tests/test_adversarial_challenger_2.py`:
- Sui DeepBookV3 Hot Potato atomic reversion on simulated AMM slippage (confirming 0 lingering debt / clean abort).
- GMX v2 dynamic price impact fee explosion and acceptablePrice slippage ceiling cancellation.
- Velocity SWIFT Dutch auction pricing at extreme boundary timestamps (negative, huge future offsets, zero duration).
- Maker rebate vs taker fee inversion verification.
Run tests with `trading-engine/.venv/bin/pytest trading-engine/tests/test_adversarial_challenger_2.py -v`.
Issue formal verdict: APPROVE or REQUEST_CHANGES.
Write report to `/Users/vitorhrds/Documents/Github/hypothesis/.agents/teamwork/teamwork_challenger_m4_2/challenge_report.md` and handoff to `/Users/vitorhrds/Documents/Github/hypothesis/.agents/teamwork/teamwork_challenger_m4_2/handoff.md`. Send a message when complete.
