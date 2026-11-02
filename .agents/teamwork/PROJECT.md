# Project: D107 Perpetual Winner Holding Strategy Restoration

## Architecture
- **Execution Engine (`trading-engine/d107_rate_limit_winner_holding.py`)**:
  - Broker Interface: Deriv WebSocket API (`proposal`, `buy`, `sell`, `cancel`, `proposal_open_contract`).
  - Pre-Buy Guardrails: Cash balance check, max open positions, capital deployment ceiling (20%), session loss stop (50%).
  - Trend Alignment Gating: Macro Tide (M15/M5 EMA20 vs EMA50 / Linear Regression) + Trend Momentum (M1 ADX > 25 & +DI/-DI). Eliminates blind mechanical alternation (`self.state["next_direction"] = alternation_after`).
  - 5-Minute Deal Cancellation Window: Asymmetric protection option. Losing trades cancelled at 4m45s boundary for fixed fee (-$0.08 to -$0.11).
  - Intra-Window Winner Retention: `in_window_auto_sell` disabled. In-window trailing stops and micro-profit take-profits removed, preventing premature scalp exits (+0.15 to +0.23 USD) on tick noise.
  - Perpetual Runner Ratchet (`held_winner`): 4-Tier progressive ratchet (Tier 0: breathing room < 1x; Tier 1: +1x stake locks breakeven floor +0.20; Tier 2: +2x stake ratchets to +1.00; Tier 3: +4x stake ratchets to +2.50; Tier 4: +8x stake take-profit / 80% trailing stop).
  - State & Audit: `AtomicStateStore` (`d107_rate_limit_winner_holding_state.json`) + `AppendOnlyEventLog` (`d107_rate_limit_winner_holding_results.jsonl`).
- **Simulation Engine (`trading-engine/d107_exact_historical_simulation.py`)**:
  - Discrete-event historical replay on recorded tick streams (`d107_simulation_1hz10v_ticks.json`).
  - Realistic quote profiles, bid/ask spreads, boundary cancellation fees, mark-to-market valuations, and execution slippage.
  - Scenario comparison: Micro-Scalp Baseline vs Perpetual Ladder 1x-8x.
- **Reporting & Learning Proposal (`learning_proposal.md`)**:
  - Comprehensive research synthesis, comparative ledger metrics, architecture specifications, simulation outcomes, and operational runbook.

## Feature Inventory
| # | Feature | Description | Milestone | Source |
|---|---------|-------------|-----------|--------|
| 1 | Historical Trade Comparative Analysis | Comparative analysis of 2,914 May trades, contract #19127889519 unmanaged runner, and Trials #256-#316 (17 premature exits) | M1 | ORIGINAL_REQUEST §R1 |
| 2 | Accidental Runner (#19127889519) Turnaround Study | Document InternalServerError orphan event, -85% adverse excursion, and 4-hour +155% macro run | M1 | ORIGINAL_REQUEST §R1 |
| 3 | Deriv Bot Curation & Counter-Trend Diagnosis | Audit all active Deriv bots in `trading-engine/`, isolate mechanisms causing counter-trend trades | M2 | ORIGINAL_REQUEST §R2 |
| 4 | Multi-Timeframe Trend Alignment Filter | Design & implement M15 tide + M5 trend + M1 ADX momentum entry filter to replace blind alternation | M2, M3 | ORIGINAL_REQUEST §R2 |
| 5 | Abolish In-Window Micro-Scalping Exits | Disable `in_window_auto_sell` and remove intra-window trailing stop in `evaluate_winner_exit` | M3 | ORIGINAL_REQUEST §R3 |
| 6 | 4-Tier Progressive Perpetual Ratchet | Implement Tiers 0-4 ratchet (1x, 2x, 4x, 8x returns) for held perpetual winners past cancellation window | M3 | ORIGINAL_REQUEST §R3 |
| 7 | Directional Boundary Qualification | Enhance 4m45s boundary gate to verify net profit >= cancellation fee AND trend alignment | M3 | ORIGINAL_REQUEST §R3 |
| 8 | Perpetual Simulation Scenarios & Replay | Add `perpetual_ladder_1x_8x` scenario to `d107_exact_historical_simulation.py` and run replay on tick dataset | M3 | ORIGINAL_REQUEST §R4 |
| 9 | Statistical Return & Runner Retention Verification | Validate higher $\mathbb{E}[\text{PnL}]$ per trade and retention of multi-bagger runners vs -$0.97 micro-scalp baseline | M3, M4 | ORIGINAL_REQUEST §R4 |
| 10 | E2E 4-Tier Test Suite & Test Infra | Build opaque-box E2E test harness covering Tiers 1-4 (>=11*N tests), generate `TEST_READY.md` | M4 | Project Pattern Dual Track |
| 11 | Adversarial Coverage Hardening (Tier 5) | White-box adversarial testing by Challenger identifying edge cases and verifying robustness | M4 | Project Pattern Phase 2 |
| 12 | Learning Proposal Artifact Generation | Persist findings, comparative metrics, architecture, and runbook into `learning_proposal.md` with `RequestFeedback=true` | M5 | ORIGINAL_REQUEST §R5 |

## Milestones
| # | Name | Scope | Dependencies | Status |
|---|------|-------|-------------|--------|
| M1 | Historical Trade & Perpetual Turnaround Study | Research artifact documenting regimes, contract #19127889519, Trials #256-#316 | Survey completed | DONE |
| M2 | Deriv Bot Curation & Trend Alignment Audit | Audit active bots, formalize Trend Alignment Matrix & ADX gating rules | Survey completed | DONE |
| M3 | Strategy Implementation & Historical Simulation | Redesign `d107_rate_limit_winner_holding.py` & `d107_exact_historical_simulation.py`, run unit tests & replay | M1, M2 | DONE |
| M4 | E2E Verification, Adversarial Testing & Integrity Audit | 2 Reviewers, 2 Challengers, 1 Forensic Auditor gate verification | M3 | DONE |
| M5 | Learning Proposal Artifact & User Delivery | Persist all deliverables into `learning_proposal.md` with RequestFeedback=true | M1, M2, M3, M4 | DONE |

## Interface Contracts
### Trend Alignment Module ↔ D107 Execution Engine
```python
class TrendAlignmentSignal:
    direction: str  # "MULTUP", "MULTDOWN", or "NONE"
    macro_trend: str  # "BULLISH", "BEARISH", "NEUTRAL"
    adx_value: float  # Current ADX on M1/M5
    is_aligned: bool  # True if macro + momentum agree
    confidence: float  # 0.0 to 1.0

def evaluate_market_trend(symbol: str, client: DerivClient) -> TrendAlignmentSignal:
    ...
```

### D107 Execution Engine ↔ Perpetual Runner Ratchet
```python
class PerpetualRatchetState:
    peak_profit: float
    current_tier: int  # 0, 1, 2, 3, 4
    guaranteed_floor: float  # Min profit to lock in
    take_profit_target: float  # 8.0 * stake
    should_exit: bool
    exit_reason: str

def evaluate_perpetual_ratchet(profit: float, stake: float, peak_profit: float) -> PerpetualRatchetState:
    ...
```

### Simulation Engine ↔ Historical Replay
```python
def run_simulation(
    ticks: List[Dict[str, Any]],
    exit_scenario: str,  # "micro_scalp_baseline" vs "perpetual_ladder_1x_8x"
    trend_alignment_enabled: bool,
    stake: float = 1.0,
    multiplier: int = 100
) -> SimulationResults:
    ...
```

## Code Layout
- `trading-engine/d107_rate_limit_winner_holding.py`: Core live/paper execution engine
- `trading-engine/test_d107_rate_limit_winner_holding.py`: Unit test suite for D107 engine (54 tests)
- `trading-engine/d107_exact_historical_simulation.py`: Historical tick simulation and backtest harness
- `trading-engine/test_d107_exact_historical_simulation.py`: Unit tests for simulation replay (12 tests)
- `trading-engine/test_d107_adversarial_challenger.py`: Adversarial test suite (19 tests)
- `trading-engine/stress_test_challenger_2.py`: Stress test suite (11 tests)
- `trading-engine/d107_validation_report.py`: Multi-horizon performance and risk report generator (9 tests)
- `trading-engine/historico_trades_maio.csv`: Historical May trade dataset
- `trading-engine/d107_rate_limit_winner_holding_results.jsonl`: Event audit ledger (Trials #256-#316, etc.)
- `trading-engine/d107_simulation_1hz10v_ticks.json`: 24-hour historical tick dataset
- `learning_proposal.md`: Deliverable artifact at project root
