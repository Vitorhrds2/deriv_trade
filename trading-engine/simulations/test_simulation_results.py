"""Unit & Integration Tests for Discrete-Event Simulation Engine Results (Milestone M5).

Verifies the mathematical rigor, microstructural invariants, and empirical conclusions
produced by `trading-engine/simulations/microstructure_discrete_sim.py`.
"""

from __future__ import annotations

import json
from pathlib import Path
import pytest

from simulations.microstructure_discrete_sim import (
    simulate_hyperliquid_mempool,
    simulate_velocity_swift,
    simulate_sui_deepbook,
    simulate_kalshi_fix,
    simulate_dydx_v4,
    simulate_gmx_cex,
    run_all_simulations,
)

RESULTS_FILE = Path(__file__).resolve().parent / "simulation_results.json"


def test_simulation_execution_and_schema():
    """Validates that all 6 vectors execute and produce schema-compliant results."""
    results = run_all_simulations(output_path=str(RESULTS_FILE), seed=42)

    assert "metadata" in results
    assert results["metadata"]["total_events_simulated"] == 35_000
    assert "scorecard" in results
    assert len(results["scorecard"]) == 6

    expected_vectors = {
        "H84 (Hyperliquid L1)",
        "H85 (Velocity SWIFT)",
        "H86 (Sui DeepBookV3)",
        "H87 (Kalshi FIX)",
        "dYdX v4 (CometBFT)",
        "GMX v2 & CEXs",
    }
    actual_vectors = {entry["vector"] for entry in results["scorecard"]}
    assert actual_vectors == expected_vectors

    for entry in results["scorecard"]:
        assert entry["verdict"] in [
            "COMPROVADA COM EDGE",
            "CONDICIONAL",
            "REFUTADA (Física) / CONDICIONAL (Sintética)",
            "REFUTADA / INVIÁVEL",
        ]
        assert entry["fill_rate_pct"] > 0.0
        assert entry["median_rtt_ms"] >= 0.0
        assert isinstance(entry["ev_pnl_bps"], (int, float))
        assert isinstance(entry["net_pnl_usd"], (int, float))
        assert isinstance(entry["annualized_sharpe"], (int, float))


def test_h84_tokyo_vs_useast_vs_eu_deflection():
    """Empirically proves that Tokyo co-location is mandatory for H84 toxic flow defense."""
    res = simulate_hyperliquid_mempool(num_events=5_000, seed=42)
    locs = res["locations"]

    tokyo = locs["tokyo_colocation"]
    us_east = locs["us_east_virginia"]
    eu = locs["eu_london"]

    # Tokyo must deflect > 98% of toxic sweeps due to sub-5ms RTT
    assert tokyo["deflection_rate_pct"] >= 98.0
    assert tokyo["median_rtt_ms"] < 5.0
    # Institutional Tier 4+ must achieve positive EV in Tokyo
    assert tokyo["institutional_tier4"]["ev_pnl_bps"] > 0.0

    # US-East suffers degraded deflection (< 95%) and swept orders due to 150ms transpacific RTT
    assert us_east["deflection_rate_pct"] < 95.0
    assert us_east["total_deflected"] < tokyo["total_deflected"]
    assert us_east["median_rtt_ms"] >= 120.0

    # EU suffers severely collapsed deflection (< 50%) due to 240ms RTT
    assert eu["deflection_rate_pct"] < 50.0

    # Retail Tier 0 pays +1.5 bps fee, destroying edge even in Tokyo
    assert tokyo["retail_tier0"]["ev_pnl_bps"] <= 0.01


def test_h85_velocity_swift_rebate_and_ev():
    """Validates that Velocity SWIFT captures 0.25 bps maker rebate and positive EV."""
    res = simulate_velocity_swift(num_auctions=3_000, seed=42)

    assert res["maker_rebate_bps"] == 0.25
    assert res["overall_fill_rate_pct"] > 50.0
    assert res["ev_pnl_bps"] > 0.0
    assert res["net_pnl_usd"] > 0.0
    assert res["annualized_sharpe"] > 0.0

    # Low volatility must achieve higher fill rate than high volatility
    low_fill = res["regimes"]["low_volatility"]["fill_rate_pct"]
    high_fill = res["regimes"]["high_volatility"]["fill_rate_pct"]
    assert low_fill > high_fill


def test_h86_sui_deepbook_zero_leg_risk():
    """Validates Move PTB atomic execution and 100% zero-leg-risk preservation."""
    res = simulate_sui_deepbook(num_cycles=3_000, seed=42)

    assert res["zero_leg_risk_rate_pct"] == 100.0
    assert res["successful_executions"] > 0
    assert res["clean_vm_aborts"] > 0
    assert res["successful_executions"] + res["clean_vm_aborts"] == 3_000
    assert res["net_pnl_usd"] > 0.0
    assert res["ev_per_attempt_bps"] > 0.0


def test_h87_kalshi_privatelink_advantage():
    """Validates that AWS PrivateLink provides sub-2ms latency and queue priority over Internet."""
    res = simulate_kalshi_fix(num_orders=3_000, seed=42)

    pl = res["aws_privatelink"]
    pub = res["public_internet"]

    # PrivateLink median RTT < 2ms, Public > 20ms
    assert pl["median_rtt_ms"] < 2.0
    assert pub["median_rtt_ms"] > 20.0

    # PrivateLink deflection rate > 80%, Public < 30%
    assert pl["shock_deflection_rate_pct"] > 80.0
    assert pub["shock_deflection_rate_pct"] < 30.0

    # PrivateLink yields higher fill rate due to top-of-queue priority
    assert pl["fill_rate_pct"] > pub["fill_rate_pct"]
    assert pl["net_pnl_usd"] > pub["net_pnl_usd"]


def test_dydx_v4_fee_inversion_tier6_tier7():
    """Validates that dYdX v4 maker rebates flip unprofitable retail MM into positive EV."""
    res = simulate_dydx_v4(num_quotes=3_000, seed=42)
    tiers = res["tiers"]

    # Tier 1 (+1.0 bps fee) must be unprofitable (negative EV)
    assert tiers["tier_1"]["ev_pnl_bps"] < 0.0

    # Tier 6 (-0.7 bps rebate) and Tier 7 (-1.1 bps rebate) must be profitable
    assert tiers["tier_6"]["ev_pnl_bps"] > 0.0
    assert tiers["tier_7"]["ev_pnl_bps"] > tiers["tier_6"]["ev_pnl_bps"]
    assert tiers["tier_7"]["total_pnl_usd"] > tiers["tier_6"]["total_pnl_usd"]


def test_gmx_cex_physical_refutation_vs_synthetic_edge():
    """Validates that physical arbitrage is refuted by 20-min withdrawal delay, while synthetic has edge."""
    res = simulate_gmx_cex(num_signals=3_000, seed=42)

    syn = res["synthetic_delta_neutral"]
    phys = res["physical_arbitrage"]

    # Synthetic delta-neutral must have positive EV
    assert syn["ev_pnl_bps"] > 0.0
    assert syn["total_pnl_usd"] > 0.0

    # Physical transfer latency ruins consistency
    assert "REFUTADA / INVIÁVEL" in phys["verdict"]
