## 2026-11-10T04:17:18Z
sender=bb8c036e-693a-4192-a9f6-25494af55dae priority=MESSAGE_PRIORITY_HIGH
content=You are the M5 Adversarial Challenger for the Sui DeepBookV3 & Cetus Arbitrage Bot.

MANDATORY FIRST STEP:
Read `/Users/vitorhrds/Documents/Github/hypothesis/.agents/teamwork/ORIGINAL_REQUEST.md` and `/Users/vitorhrds/Documents/Github/hypothesis/.agents/teamwork/PROJECT.md` before starting work.

Working Directory: `/Users/vitorhrds/Documents/Github/hypothesis/.agents/teamwork/teamwork_challenger_m5_1/`

Context:
Worker M5 has delivered full regression verification (458/458 repo tests green, 148/148 Sui tests green) and authored the production runbook in `/Users/vitorhrds/Documents/Github/hypothesis/docs/sui_production_runbook.md`.

Your Adversarial Mission (Tier 5):
1. Run and challenge the full multi-milestone Sui verification suite:
   `PYTHONPATH=trading-engine trading-engine/.venv/bin/pytest -v trading-engine/tests/test_sui_deepbook_multipair.py trading-engine/tests/test_sui_scaling_engine.py trading-engine/tests/test_sui_programmatic_verification.py trading-engine/tests/test_sui_production_deployment.py trading-engine/tests/test_adversarial_m3.py trading-engine/tests/test_adversarial_m4_deployment.py`
2. Challenge the system invariants:
   - Zero Leg Risk Invariant: Verify that under any negative arbitrage spread, fee slippage, or insufficient swap return, the Move PTB will fail at `SplitCoins` / `return_flashloan_quote` without repaying debt and cleanly abort with 0 state changes.
   - Gas Depletion Protection: Verify that when gas drops to 0.5 SUI, the bot strictly refuses to fire PTBs, preventing wallet depletion.
   - Capital Scaling Monotonicity & Cooldown: Verify that scaling up requires both net profit AND trade count hurdles, and that 3 consecutive aborts trigger immediate downgrade and 5-minute cooldown.
   - Runbook Integrity: Verify that commands, configuration variables, and healthcheck paths in `docs/sui_production_runbook.md` match actual implementation.
3. Write your handoff report to:
   `/Users/vitorhrds/Documents/Github/hypothesis/.agents/teamwork/teamwork_challenger_m5_1/handoff.md` with an explicit verdict: APPROVE or REQUEST_CHANGES.
4. Notify me via `send_message` when done.
