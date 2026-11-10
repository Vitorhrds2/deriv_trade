# Milestone M2 Code Review & Adversarial Quality Analysis

**Reviewer / Critic:** `teamwork_reviewer_m2_1`  
**Target Milestone:** Milestone M2 — Dynamic Capital Scaling Engine & Sui Balance Tracker  
**Target Files:**
- `trading-engine/venues/sui_scaling_engine.py`
- `trading-engine/tests/test_sui_scaling_engine.py`  
**Verdict:** **APPROVE**  
**Date:** 2026-11-10T03:12:30Z  

---

## 1. Executive Summary

Milestone M2 implements the dynamic capital scaling engine, wallet balance tracker, gas safety floors, and multi-tier circuit breakers governing the Sui DeepBookV3 and Cetus AMM arbitrage bot.

The codebase was reviewed through both a quality review lens (correctness, completeness, conformance to `PROJECT.md` and `ORIGINAL_REQUEST.md`) and an adversarial lens (stress-testing state transitions, edge case handling, race conditions, abort cooldowns, gas starvation, and quote currency asymmetries).

All requirements are fully satisfied:
- Initial baseline flash loan tranche: `1_000_000_000` (1,000 USDC nativo, 6 decimals).
- Tier 1 -> Tier 2 promotion: strictly gated on $\ge \$100.00$ net profit AND $\ge 10$ successful executions.
- Tier 2 -> Tier 3 promotion: strictly gated on $\ge \$750.00$ cumulative net profit AND $\ge 20$ successful executions.
- Gas safety floors: Warning alert at 1.5 SUI and Critical Hard Stop at 0.5 SUI (`STATUS_EMERGENCY_LOCKED`).
- Circuit breakers: 3 consecutive aborts trigger a 1-tier downgrade and 60-second cooldown (`STATUS_COOLING_DOWN`); 5 consecutive aborts trigger an emergency lock requiring manual intervention.
- Multi-currency quote conversion: exact micro-USDC for USDC quote pairs (`SUI/USDC`, `DEEP/USDC`), and dynamically converted MIST for SUI quote pairs (`DEEP/SUI`, `CETUS/SUI`) based on SUI spot price.
- `SuiBalanceTracker`: atomic single-roundtrip query using Sui GraphQL RPC, parsing 9-decimal MIST and 6-decimal USDC with safety checks.
- Zero integrity violations: zero hardcoded mocks in source code, zero facade patterns, zero bypassing of intended requirements.
- Full automated test suite passes: 62/62 relevant tests (24 scaling engine unit tests, 13 DeepBook multi-pair tests, 2 venue unit tests, 23 adversarial challenger tests) executed with zero failures.

---

## 2. Review Dimensions & Detailed Findings

### Dimension 1: Correctness & Requirement Conformance

| Requirement | Implementation in `sui_scaling_engine.py` | Status | Evidence |
|-------------|-------------------------------------------|--------|----------|
| **Initial Parameter 1,000 USDC** | `ScalingTier.TIER_1 = 1_000_000_000`, `flash_borrow_amount` property | VERIFIED | `test_initial_tier_and_parameters` passed |
| **Tier 1 -> Tier 2 ($100 profit, 10 trades)** | Lines 292–312: Dual check on `accumulated_net_profit_usdc >= 100.0` and `successful_trades >= 10` | VERIFIED | `test_tier_1_to_tier_2_transition_on_100_profit_and_10_trades`, `test_non_transition_when_profit_met_but_trades_insufficient`, `test_non_transition_when_trades_met_but_profit_insufficient` passed |
| **Tier 2 -> Tier 3 ($750 profit, 20 trades)** | Lines 313–323: Dual check on `accumulated_net_profit_usdc >= 750.0` and `successful_trades >= 20` | VERIFIED | `test_tier_2_to_tier_3_transition_on_750_cumulative_profit_and_20_trades`, `test_direct_tier_1_to_tier_3_promotion` passed |
| **Gas Warning Floor (1.5 SUI)** | Lines 339–344: Sets `gas_warning = True`, emits warning log, remains `ACTIVE` | VERIFIED | `test_gas_safety_warning_at_1_5_sui` passed |
| **Gas Critical Floor (0.5 SUI)** | Lines 331–338: Halts execution immediately, sets `status = EMERGENCY_LOCKED`, `can_trade() == False` | VERIFIED | `test_gas_safety_critical_hard_stop_at_0_5_sui` passed |
| **3-Abort Demotion & Cooldown** | Lines 270–288: Demotes Tier 3 -> Tier 2 or Tier 2 -> Tier 1, sets `status = COOLING_DOWN` with 60s cooldown | VERIFIED | `test_three_abort_downgrade_and_cooldown_from_tier_2`, `test_three_abort_downgrade_from_tier_3` passed |
| **5-Abort Emergency Lock** | Lines 263–269: Sets `status = EMERGENCY_LOCKED`, `_emergency_locked_due_to_aborts = True` | VERIFIED | `test_five_abort_emergency_lock` passed |
| **SUI-Quote Conversion** | Lines 364–402: Calculates $\text{MIST} = \text{round}\left(\frac{\text{Tier USD}}{\text{Price}} \times 10^9\right)$ | VERIFIED | `test_sui_quote_conversion_deep_sui_and_cetus_sui` passed |
| **GraphQL Balance Tracker** | Lines 425–496: `SuiBalanceTracker` queries GraphQL `get_wallet_balances`, maps MIST and USDC raw units | VERIFIED | `test_sui_balance_tracker_parsing_and_gas_floors`, `test_sui_balance_tracker_updates_scaling_engine` passed |

---

## 3. Adversarial Stress-Testing & Edge Case Analysis

### Challenge 1: Abort Cooldown Auto-Recovery & Race Conditions
- **Scenario:** The engine enters `COOLING_DOWN` after 3 aborts. Does it prematurely trade before 60 seconds? Does it resume if gas was depleted during cooldown?
- **Analysis:** Lines 216–228 (`_check_cooldown_expiry`) evaluate `time.time() >= cooldown_until`. In addition, line 220 re-checks `sui_gas_balance < critical_gas_floor`. If gas fell below 0.5 SUI during cooldown, the status immediately escalates to `EMERGENCY_LOCKED` rather than `ACTIVE`.
- **Outcome:** PASS.

### Challenge 2: Gas Replenishment Bypassing Abort Locks
- **Scenario:** The engine hit 5 consecutive aborts (`EMERGENCY_LOCKED`). An automated wallet balance poll runs and sees SUI balance > 1.5 SUI. Does the balance update accidentally clear the abort emergency lock?
- **Analysis:** In line 347 of `update_from_wallet_balances`:
  ```python
  if self.state.status == STATUS_EMERGENCY_LOCKED and not self._emergency_locked_due_to_aborts:
      self.state.status = STATUS_ACTIVE
  ```
  The boolean `_emergency_locked_due_to_aborts` prevents gas updates from clearing an abort-induced lock. Only an explicit operator call to `unlock_emergency()` can clear it.
- **Outcome:** PASS.

### Challenge 3: Monotonic Profit Ratchet vs. Wallet Fluctuations
- **Scenario:** The operator withdraws accumulated USDC profits from the wallet, reducing the balance below baseline. Does the engine crash or demote tiers?
- **Analysis:** Line 360 checks `if onchain_profit > self.state.accumulated_net_profit_usdc`. If on-chain profit is lower than the recorded accumulated net profit, it does not regress the accumulated profit counter, preserving the high-water mark for tiers while trade-by-trade accounting remains intact.
- **Outcome:** PASS.

### Challenge 4: Precision & Decimal Asymmetry in SUI Quote Conversion
- **Scenario:** `DEEP/SUI` or `CETUS/SUI` borrows SUI (9 decimals) rather than USDC (6 decimals). At fractional spot prices (e.g. $2.1379 SUI), does integer rounding lose significant precision?
- **Analysis:** `sui_mist = int(round(sui_amount * 1_000_000_000))`. The precision is bounded within 1 MIST ($0.000000002), which is completely negligible and Move VM compliant.
- **Outcome:** PASS.

---

## 4. Integrity Audit

- **Hardcoded Results:** None detected. State transitions calculate actual arithmetic against configurable thresholds.
- **Facade Implementations:** None detected. Complete integration with `SuiGraphQLClient` and real GraphQL queries.
- **Shortcuts / Bypasses:** None. All safety constraints, circuit breakers, and state machine states are fully wired.
- **Independent Verification:** Ran pytest across 4 independent test suites on Python 3.13; all passed cleanly.

---

## 5. Review Verdict

**VERDICT: APPROVE**

The work product delivered by `teamwork_worker_m2` is robust, well-architected, and adheres strictly to all project specifications. Milestone M2 is approved for integration.
