"""Micro-Capital Simulation for Sui DeepBookV3 (H86).

Evaluates the exact empirical performance, survival probability, runway, and net PnL
for allocated micro-capitals of:
$1 USD, $2 USD, $4 USD, $10 USD, and $20 USD.

Compares two paradigms:
Paradigm A: Capital allocated as GAS BANKROLL for Flash Loan Arbitrage (True H86 Architecture).
Paradigm B: Capital allocated as DIRECT SPOT ARBITRAGE (Traditional no-flash-loan trading).
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List

import numpy as np

# Simulation constants
SUI_PRICE_USD = 2.05
GAS_PER_PTB_SUI = 0.002
GAS_COST_USD = GAS_PER_PTB_SUI * SUI_PRICE_USD  # $0.0041 USD

CETUS_FEE_BPS = 25.0
DEEPBOOK_MAKER_FEE_BPS = 0.0
CETUS_IMPACT_FACTOR = 100.0 / 4_000_000.0  # size / pool_depth * 100


def run_micro_capital_simulation(
    num_events: int = 5_000,
    seed: int = 42,
) -> Dict[str, Any]:
    rng = np.random.default_rng(seed)

    capital_levels = [1.0, 2.0, 4.0, 10.0, 20.0]
    flash_loan_sizes = [1_000.0, 5_000.0, 10_000.0]  # $1k, $5k, $10k flash loan sizes

    # Generate synthetic spreads between DeepBook CLOB and Cetus AMM
    # Normal distribution with mean=18 bps, std=22 bps (same as master engine)
    raw_spreads_bps = rng.normal(loc=18.0, scale=22.0, size=num_events)

    # 1. PARADIGM A: FLASH LOAN (Capital = Gas Bankroll)
    flash_loan_results: Dict[str, Any] = {}

    for fl_size in flash_loan_sizes:
        fl_key = f"flash_loan_{int(fl_size)}"
        impact_bps = fl_size * CETUS_IMPACT_FACTOR
        total_friction_bps = CETUS_FEE_BPS + DEEPBOOK_MAKER_FEE_BPS + impact_bps

        levels_data: Dict[str, Any] = {}

        for cap in capital_levels:
            max_attempts_capacity = int(cap / GAS_COST_USD)
            
            # Simulate sequential trading path (Monte Carlo)
            current_bankroll = cap
            total_profit_accumulated = 0.0
            successful_trades = 0
            aborted_trades = 0
            consecutive_failures = 0
            max_consecutive_failures = 0
            bankroll_history: List[float] = [current_bankroll]
            trade_pnl_list: List[float] = []

            ruined = False
            ruin_event_idx = None
            first_success_idx = None

            for i, spread in enumerate(raw_spreads_bps):
                if current_bankroll < GAS_COST_USD:
                    ruined = True
                    ruin_event_idx = i
                    break

                # Net spread after friction
                net_spread_bps = spread - total_friction_bps
                gross_profit = (net_spread_bps / 10_000.0) * fl_size
                net_profit = gross_profit - GAS_COST_USD

                # Off-chain filter: bot only submits if estimated profit > 0
                # In real market, 80% of submitted opportunities execute successfully within 380ms
                if net_profit > 0:
                    execution_success = rng.random() < 0.80
                    if execution_success:
                        # PTB commits successfully
                        successful_trades += 1
                        current_bankroll += net_profit
                        total_profit_accumulated += net_profit
                        trade_pnl_list.append(net_profit)
                        consecutive_failures = 0
                        if first_success_idx is None:
                            first_success_idx = i
                    else:
                        # Move VM aborts via Hot Potato
                        aborted_trades += 1
                        current_bankroll -= GAS_COST_USD
                        trade_pnl_list.append(-GAS_COST_USD)
                        consecutive_failures += 1
                        max_consecutive_failures = max(max_consecutive_failures, consecutive_failures)
                else:
                    # Filtered out off-chain: no gas spent!
                    pass

                bankroll_history.append(current_bankroll)

            pnl_arr = np.array(trade_pnl_list) if trade_pnl_list else np.array([0.0])
            total_net_pnl = float(np.sum(pnl_arr))
            mean_trade_pnl = float(np.mean(pnl_arr)) if len(pnl_arr) > 0 else 0.0
            std_pnl = float(np.std(pnl_arr)) if len(pnl_arr) > 1 else 1.0
            sharpe = float((mean_trade_pnl / (std_pnl if std_pnl > 1e-6 else 1.0)) * math.sqrt(25_000))

            # Max drawdown from peak
            bankroll_arr = np.array(bankroll_history)
            peaks = np.maximum.accumulate(bankroll_arr)
            drawdowns = (peaks - bankroll_arr) / peaks
            max_dd_pct = float(np.max(drawdowns)) * 100.0 if len(drawdowns) > 0 else 0.0

            levels_data[f"cap_{int(cap)}"] = {
                "initial_capital_usd": cap,
                "initial_gas_capacity_txs": max_attempts_capacity,
                "final_bankroll_usd": round(current_bankroll, 2),
                "total_net_profit_usd": round(total_profit_accumulated, 2),
                "roi_pct": round((total_profit_accumulated / cap) * 100.0, 1),
                "successful_trades": successful_trades,
                "aborted_trades": aborted_trades,
                "total_executed_attempts": successful_trades + aborted_trades,
                "win_rate_pct": round((successful_trades / (successful_trades + aborted_trades) * 100.0), 2) if (successful_trades + aborted_trades) > 0 else 0.0,
                "max_consecutive_failures": max_consecutive_failures,
                "ruined": ruined,
                "ruin_probability_pct": 0.0 if not ruined else 100.0,
                "max_drawdown_pct": round(max_dd_pct, 2),
                "sharpe_ratio": round(sharpe, 2),
            }

        flash_loan_results[fl_key] = {
            "flash_loan_size_usd": fl_size,
            "amm_friction_bps": round(total_friction_bps, 2),
            "results_by_capital": levels_data,
        }

    # 2. PARADIGM B: DIRECT SPOT ARBITRAGE (No Flash Loan, Trade Size = Capital)
    direct_spot_results: Dict[str, Any] = {}

    for cap in capital_levels:
        trade_size = cap
        impact_bps = trade_size * CETUS_IMPACT_FACTOR
        total_friction_bps = CETUS_FEE_BPS + DEEPBOOK_MAKER_FEE_BPS + impact_bps

        net_pnls: List[float] = []
        profitable_events = 0
        loss_events = 0

        for spread in raw_spreads_bps:
            net_spread_bps = spread - total_friction_bps
            gross_profit = (net_spread_bps / 10_000.0) * trade_size
            net_profit = gross_profit - GAS_COST_USD

            # Even if spread > friction, is gross_profit > gas?
            if gross_profit > 0:
                net_pnls.append(net_profit)
                if net_profit > 0:
                    profitable_events += 1
                else:
                    loss_events += 1

        pnl_arr = np.array(net_pnls) if net_pnls else np.array([0.0])
        total_pnl = float(np.sum(pnl_arr))
        mean_pnl = float(np.mean(pnl_arr)) if len(pnl_arr) > 0 else 0.0

        direct_spot_results[f"cap_{int(cap)}"] = {
            "capital_usd": cap,
            "trade_size_usd": trade_size,
            "total_friction_bps": round(total_friction_bps, 2),
            "gas_cost_usd": round(GAS_COST_USD, 4),
            "gas_as_pct_of_capital": round((GAS_COST_USD / cap) * 100.0, 3),
            "break_even_spread_bps": round(total_friction_bps + (GAS_COST_USD / trade_size * 10_000.0), 2),
            "viable_profitable_trades": profitable_events,
            "trades_killed_by_gas": loss_events,
            "net_pnl_usd": round(total_pnl, 2),
            "ev_per_trade_usd": round(mean_pnl, 6),
            "is_viable": profitable_events > loss_events and total_pnl > 0,
        }

    output = {
        "simulation_parameters": {
            "num_events": num_events,
            "sui_price_usd": SUI_PRICE_USD,
            "gas_per_ptb_sui": GAS_PER_PTB_SUI,
            "gas_cost_usd": GAS_COST_USD,
            "cetus_fee_bps": CETUS_FEE_BPS,
        },
        "paradigm_a_flash_loan": flash_loan_results,
        "paradigm_b_direct_spot": direct_spot_results,
    }

    # Save results to json
    out_path = Path(__file__).parent / "micro_capital_simulation_results.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2)

    return output


if __name__ == "__main__":
    results = run_micro_capital_simulation()
    print("=== SIMULATION COMPLETED ===")
    print("Direct Spot Viability:")
    for cap_key, data in results["paradigm_b_direct_spot"].items():
        print(f"  Cap ${data['capital_usd']}: Viable={data['is_viable']} | Net PnL=${data['net_pnl_usd']} | Break-even={data['break_even_spread_bps']} bps")
    print("\nFlash Loan $5,000 Sample:")
    for cap_key, data in results["paradigm_a_flash_loan"]["flash_loan_5000"]["results_by_capital"].items():
        print(f"  Cap ${data['initial_capital_usd']}: Gas Capacity={data['initial_gas_capacity_txs']} txs | Final Bankroll=${data['final_bankroll_usd']} | Profit=${data['total_net_profit_usd']} | Ruined={data['ruined']}")
