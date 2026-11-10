# Adversarial Challenge Report: Challenger 2

**Author**: teamwork_challenger_m4_2 (Empirical Challenger)  
**Date**: 2026-11-03T05:38:00Z  
**Verdict**: **APPROVE**  
**Test Suite**: `trading-engine/tests/test_adversarial_challenger_2.py` (20 passed in 5.00s)

---

## Challenge Summary

**Overall risk assessment**: **LOW**

All mathematical boundaries, mechanical protections, and fee/rebate models across the 4 tested microstructure vectors demonstrated robust, deterministic defense:
1. **Sui DeepBookV3 Hot Potato**: The Move VM PTB cleanly aborts on unprofitable spreads, infinitesimal shortfalls (1 mist), and catastrophic slippage/flash crashes with strictly 0 state mutations, 0 lingering debt, and 0 leg risk.
2. **GMX v2 Dynamic Fee & Slippage Barrier**: Price impact fees scale strictly linearly up to 505 bps ($100M order), cleanly inverting naive high-volume sizing edge. The `acceptablePrice` barrier strictly cancels both BUY and SELL orders violating slippage limits down to the single cent ($0.01).
3. **Velocity SWIFT Dutch Auction Curve**: Handles zero duration ($D=0$) and negative duration ($D<0$) without division-by-zero, clamps extreme negative/future timestamps ($10^{18}$ ms, $2^{63}-1$) strictly to boundary prices, and maintains strict monotonicity across the timeline.
4. **Maker Rebate vs Taker Fee Inversion**: Taker orders across Hyperliquid, dYdX v4, and Velocity SWIFT cannot claim negative maker rebates, strictly incurring positive taker fees. Hyperliquid ALO crossing orders cleanly auto-cancel rather than filling as takers.

---

## Challenges & Stress Scenarios

### [Low Risk] Challenge 1: Sui DeepBookV3 Partial Leg Fill & Debt Accumulation on AMM Slippage

- **Assumption challenged**: The multi-step PTB (flash loan borrow $\to$ Cetus swap $\to$ DeepBook sell $\to$ repay) might suffer partial fills or leave outstanding flash loan debt if AMM liquidity thins or suffers an adversarial sandwich attack.
- **Attack scenario**: An adversarial AMM frontrunner drives up the SUI buy price, causing proceeds $Q'$ to fall short of the borrowed amount $Q$ by varying degrees:
  - Infinitesimal shortfall: $Q' = Q - 1\text{ mist}$ ($0.000001\text{ USDC}$).
  - Severe slippage: 10% to 100% adverse price move.
  - Catastrophic sandwich: 10x AMM price spike ($P_{\text{AMM}} = \$20.00$ vs $P_{\text{CLOB}} = \$2.00$).
  - CLOB crash: DeepBook bid collapses by 99% ($P_{\text{CLOB}} = \$0.02$).
- **Blast radius**: If the VM committed any state before aborting or if the Hot Potato could be dropped, the bot would be left holding depreciated inventory with unpaid flash debt.
- **Empirical Observation**:
  - `commands[0]` outputs `["borrowed_quote_coin", "flash_loan_receipt"]` where `flash_loan_receipt` is a Hot Potato struct with 0 Move abilities.
  - When $Q' < Q$, `SplitCoins` at Command 5 fails with `INSUFFICIENT_BALANCE_FOR_REPAYMENT`.
  - Command 6 (`return_flashloan_quote`) is never reached.
  - Sui Move VM triggers a hard abort, reverting 100% of transaction mutations (`state_mutations == 0`, `hot_potato_aborted == True`, `net_profit_quote == 0.0`).
  - Only transaction gas (~0.002 SUI) is burned. No debt lingers.
- **Mitigation Status**: Fully mitigated at the Move bytecode and VM architecture layer. Deterministic defense confirmed.

### [Low Risk] Challenge 2: GMX v2 Dynamic Price Impact Fee Sizing Inversion

- **Assumption challenged**: Sizing up order size to maximize dollar arbitrage PnL on lead-lag signals might be profitable under naive assumptions.
- **Attack scenario**: Lead-lag latency signal indicates a 12 bps divergence between MEXC Spot and GMX v2. An aggressive algorithm sizes an order up to $1M, $3M, $10M, or $50M in a $10M pool.
- **Blast radius**: The algorithm believes it is capturing a 12 bps edge, but dynamic price impact fees consume the entire edge and cause massive negative net EV on fill.
- **Empirical Observation**:
  - Formula: $\text{fee\_bps} = \text{base\_fee\_bps} + \text{impact\_factor} \times \frac{\text{size\_usd}}{\text{pool\_depth\_usd}}$.
  - Sizing at $30k (10 ETH): Fee is 5.15 bps $\implies$ Net edge = $+6.85\text{ bps}$ (Profitable).
  - Sizing at $3M (1000 ETH): Fee explodes to 20.0 bps $\implies$ Net edge = $-8.00\text{ bps}$ (Severely unprofitable).
  - Sizing at $50M: Fee explodes to 255.0 bps (2.55%).
  - Sizing at $100M: Fee explodes to 505.0 bps (5.05%).
  - Degenerate inputs (pool depth $\le 0$, negative size) fall back safely to `base_fee_bps`.
- **Mitigation Status**: Verified. Sizing algorithms must include dynamic price impact fee accounting prior to order dispatch.

### [Low Risk] Challenge 3: GMX v2 Slippage Ceiling Breach via Chainlink Pull Oracle Jitter

- **Assumption challenged**: Sudden oracle price updates during 2-step execution might execute trades at toxic prices beyond trader tolerance.
- **Attack scenario**: A BUY order is placed committing `acceptablePrice = $3000.00`. Between `OrderCreated` and `ExecuteOrder`, keeper submits a higher price: $3000.01 (+0.01 cent), $3050.00 (+1.67%), or $3500.00 (+16.7%). Similarly for SELL orders committing a floor of $3000.00, oracle drops to $2999.99, $2950.00, or $2200.00.
- **Blast radius**: Adverse execution leading to instantaneous drawdown on fill.
- **Empirical Observation**:
  - `evaluate_chainlink_pull_execution` strictly checks `current_oracle_price <= acceptable_price` for BUY and `current_oracle_price >= acceptable_price` for SELL.
  - Any breach (even by 1 cent) causes immediate cancellation with status `CANCELLED`, order prefix `GMX-ABORT-`, 0 fees, and 0 rebates.
- **Mitigation Status**: Fully mitigated. Barrier check guarantees zero adverse fills.

### [Low Risk] Challenge 4: Velocity SWIFT Dutch Auction Numerical Instability & Clock Skew

- **Assumption challenged**: Extreme timestamps, negative durations, or validator clock desynchronizations could produce ZeroDivisionError, NaN prices, or inverted curve directions.
- **Attack scenario**:
  - Corrupt taker intents with $D = 0$ or $D < 0$.
  - Taker intent arriving with timestamp before auction start (`current_time < start_time`).
  - Historical/negative epoch timestamps ($t = -10,000\text{ ms}$).
  - Astronomical future offsets ($t = t_0 + 10^{12}\text{ ms}$, $t = 2^{63}-1$).
- **Blast radius**: Unhandled Python exception halting the async WebSocket stream, or evaluating prices outside the $[P_{\text{start}}, P_{\text{end}}]$ envelope.
- **Empirical Observation**:
  - $D \le 0$ strictly returns `end_price` immediately without division.
  - $t_{\text{elapsed}}$ uses `max(0, min(duration_ms, current_time - start_time))`, mathematically bounding fraction $\in [0.0, 1.0]$.
  - Monotonicity verified across 1000 millisecond ticks for both BUY (climbing) and SELL (decaying) curves.
- **Mitigation Status**: Fully mitigated.

### [Low Risk] Challenge 5: Maker Rebate Extraction via Taker Flow (Fee Inversion)

- **Assumption challenged**: Taker orders placed without ALO or aggressive crossing orders might erroneously claim negative maker rebates, or cross into maker rebate tiers.
- **Attack scenario**: Submitting non-ALO orders in Hyperliquid and dYdX v4 institutional tiers (Tiers 6 and 7 where maker fees are $-0.7\text{ bps}$ and $-1.1\text{ bps}$).
- **Blast radius**: Simulation or trading engine incorrectly crediting rebates on taker execution, creating phantom PnL.
- **Empirical Observation**:
  - In Hyperliquid, `post_only=False` strictly sets `is_maker=False`, `rebate_bps=0.0`, and applies positive taker fee ($+4.5\text{ bps}$ down to $+2.4\text{ bps}$).
  - When an ALO order crosses the spread, Hyperliquid auto-cancels the order (`status="CANCELLED"`, 0 fees), preventing it from executing as taker.
  - In dYdX v4 Tier 6/7, taker orders (`post_only=False`) strictly pay $+2.5\text{ bps}$ taker fee and receive $0.0\text{ bps}$ rebate.
  - Universal invariant holds across all 7 venue implementations: for any non-maker order, `rebate_bps == 0.0` and `fee_bps >= 0.0`.
- **Mitigation Status**: Fully mitigated.

---

## Stress Test Results

| Test ID | Scenario | Expected Behavior | Actual Behavior | Result |
|---|---|---|---|---|
| **SUI-01** | Move PTB 8-step builder structure | Atomic block with Hot Potato receipt at Cmd 0 & 6 | 8 Move commands, receipt un-droppable | **PASS** |
| **SUI-02** | AMM slippage spectrum ($2.0001 to $4.00) | DryRun aborts, 0 state mutations, 0 profit | Status=ABORTED, mutations=0, profit=0.0 | **PASS** |
| **SUI-03** | OrderExecutionResult on PTB abort | Status=REJECTED, fee=0, rebate=0, order_id=PTB-REVERT- | Status=REJECTED, fee=0, rebate=0 | **PASS** |
| **SUI-04** | Infinitesimal boundary (1 mist shortfall) | Proceeds short by 1 mist aborts with 0 mutations | Status=ABORTED, mutations=0 | **PASS** |
| **SUI-05** | Catastrophic 10x AMM spike & 99% CLOB crash | Clean abort, zero leg risk preserved | Status=ABORTED, mutations=0 | **PASS** |
| **GMX-01** | Price impact fee scaling ($10k to $100M) | Linear scaling: 5.05 bps up to 505 bps | Exact mathematical match across all tiers | **PASS** |
| **GMX-02** | Dynamic fee exceeds lead-lag edge | Sizing at $3M inverts 12 bps edge to -8 bps | Order filled, net edge negative (-8 bps) | **PASS** |
| **GMX-03** | Degenerate inputs (pool $\le 0$, size $\le 0$) | Safe fallback to base fee, no ZeroDivisionError | Returns 5.0 bps base fee | **PASS** |
| **GMX-04** | BUY acceptablePrice ceiling violation (+$0.01) | Immediate cancellation, 0 fee, order=GMX-ABORT- | Status=CANCELLED, fee=0, rebate=0 | **PASS** |
| **GMX-05** | SELL acceptablePrice floor violation (-$0.01) | Immediate cancellation, 0 fee, order=GMX-ABORT- | Status=CANCELLED, fee=0, rebate=0 | **PASS** |
| **SWIFT-01** | Zero & negative duration ($D \le 0$) | Immediate return of end_price, no exception | Returns end_price | **PASS** |
| **SWIFT-02** | Negative timestamps and pre-start arrival | Clamps to start_price or computes valid fraction | Clamps to start_price, exact midpoint on progress | **PASS** |
| **SWIFT-03** | Astronomical future offsets ($10^{18}$ ms, $2^{63}-1$) | Clamps strictly to end_price | Returns end_price | **PASS** |
| **SWIFT-04** | Monotonicity across 1000 timeline ticks | BUY monotonic non-decreasing, SELL non-increasing | Verified strictly monotonic | **PASS** |
| **SWIFT-05** | Toxic flow divergence gating (>50 bps) | Order rejected with 0 rebate | Status=REJECTED, rebate=0.0 | **PASS** |
| **FEE-01** | Hyperliquid taker orders across Tiers 0-6 | Positive taker fee (+4.5 to +2.4 bps), 0 rebate | Verified positive taker fees, 0 rebate | **PASS** |
| **FEE-02** | Hyperliquid ALO crossing spread | Auto-cancel, 0 fee, never fills as taker | Status=CANCELLED, fee=0.0, rebate=0.0 | **PASS** |
| **FEE-03** | dYdX v4 Tier 6/7 maker rebate vs taker fee | Takers pay +2.5 bps, never extract -0.7/-1.1 bps | is_maker=False, fee=2.5 bps, rebate=0.0 | **PASS** |
| **FEE-04** | Velocity SWIFT maker rebate exclusivity | Rebate awarded only on valid maker fill | Valid=0.25 bps rebate, dup/toxic=0.0 rebate | **PASS** |
| **FEE-05** | Universal cross-venue fee inversion invariant | Non-maker orders have rebate==0 and fee>=0 | Invariant holds across all 7 venues | **PASS** |

---

## Unchallenged Areas

- **Validator-Level State Machine Byzantine Attacks**: Byzantine validator collusion in CometBFT or Solana consensus (out of scope for client venue connector testing).
- **Physical Hardware SGX Enclaves**: Intel SGX side-channel memory leaks during cryptographic signing (out of scope for simulation architecture).

---

## Verdict: APPROVE

All 20 adversarial stress tests execute with 100% pass rate. Sui Hot Potato atomic reversion, GMX v2 dynamic fee explosion and slippage ceilings, Velocity SWIFT Dutch auction boundary math, and maker rebate vs taker fee protections are mathematically sound and robustly implemented.
