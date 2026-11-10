## 2026-11-10T03:31:05Z

You are teamwork_challenger_m3_1.
Your working directory is /Users/vitorhrds/Documents/Github/hypothesis/.agents/teamwork/teamwork_challenger_m3_1/

MANDATORY: You must read:
1. /Users/vitorhrds/Documents/Github/hypothesis/.agents/teamwork/ORIGINAL_REQUEST.md
2. /Users/vitorhrds/Documents/Github/hypothesis/.agents/teamwork/PROJECT.md
3. /Users/vitorhrds/Documents/Github/hypothesis/.agents/teamwork/teamwork_worker_m3/handoff.md

Scope:
Empirically and adversarially challenge Milestone M3 implementation (`trading-engine/venues/sui_ptb_validator.py` and `trading-engine/tests/test_sui_programmatic_verification.py`).

Your Tasks:
1. Write an adversarial stress test harness (e.g. `trading-engine/tests/test_adversarial_m3.py`):
   - Extreme inputs: 0 borrow amount, negative amounts, massive amounts (e.g. 100,000,000 USDC), extreme spreads (-10000 bps, +50000 bps).
   - Abort invariants: verify that on sub-hurdle spread, state mutations are strictly 0 and gas cost is exactly 0.002 SUI (or 2,000,000 MIST) across all 4 pairs (`SUI/USDC`, `DEEP/SUI`, `DEEP/USDC`, `CETUS/SUI`).
   - Boundary gas levels: test exact floating point boundaries around 0.5 SUI and 1.5 SUI.
   - Concurrency / stress: test rapid repeated dry-run simulations.
2. Run your tests with:
   `PYTHONPATH=trading-engine trading-engine/.venv/bin/pytest -v trading-engine/tests/test_adversarial_m3.py`
3. Document empirical findings, pass/fail counts, and provide an explicit verdict: APPROVE or REQUEST_CHANGES in `handoff.md`. Send a brief completion message.
