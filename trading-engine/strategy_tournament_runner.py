import argparse
import asyncio
import json
import logging
import math
import os
import statistics
import time
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

from deriv_client import DerivClient


MODEL_SPECS = [
    {
        "id": "reversal_2tick_cooldown30",
        "kind": "reversal",
        "streak": 2,
        "min_move": 0.0,
        "cooldown_seconds": 30,
        "symbol": "1HZ100V",
        "duration_ticks": 1,
        "stake": 1.0,
        "rationale": "Pivot from failed 2-tick trend-follow: fade the same local pattern.",
    },
    {
        "id": "reversal_3tick_minmove020",
        "kind": "reversal",
        "streak": 3,
        "min_move": 0.20,
        "cooldown_seconds": 35,
        "symbol": "1HZ100V",
        "duration_ticks": 1,
        "stake": 1.0,
        "rationale": "Require stronger local overextension before fading.",
    },
    {
        "id": "mean_revert_5tick_dev025",
        "kind": "mean_revert",
        "window": 5,
        "min_move": 0.25,
        "cooldown_seconds": 35,
        "symbol": "1HZ100V",
        "duration_ticks": 1,
        "stake": 1.0,
        "rationale": "Trade back toward a short tick mean, avoiding pure two-tick noise.",
    },
    {
        "id": "trend_3tick_minmove030",
        "kind": "trend",
        "streak": 3,
        "min_move": 0.30,
        "cooldown_seconds": 40,
        "symbol": "1HZ100V",
        "duration_ticks": 1,
        "stake": 1.0,
        "rationale": "Only follow stronger moves; avoids the failed weak 2-tick trend model.",
    },
    {
        "id": "reversal_2tick_R100",
        "kind": "reversal",
        "streak": 2,
        "min_move": 0.0,
        "cooldown_seconds": 35,
        "symbol": "R_100",
        "duration_ticks": 1,
        "stake": 1.0,
        "rationale": "Same fade hypothesis on classic R_100 instead of 1HZ100V.",
    },
    {
        "id": "reversal_4tick_minmove040",
        "kind": "reversal",
        "streak": 4,
        "min_move": 0.40,
        "cooldown_seconds": 45,
        "symbol": "1HZ100V",
        "duration_ticks": 1,
        "stake": 1.0,
        "rationale": "Require a larger four-tick overextension before fading.",
    },
    {
        "id": "mean_revert_7tick_dev035",
        "kind": "mean_revert",
        "window": 7,
        "min_move": 0.35,
        "cooldown_seconds": 45,
        "symbol": "1HZ100V",
        "duration_ticks": 1,
        "stake": 1.0,
        "rationale": "Longer short-horizon mean-reversion window after weak two/three-tick fades.",
    },
    {
        "id": "trend_4tick_minmove050",
        "kind": "trend",
        "streak": 4,
        "min_move": 0.50,
        "cooldown_seconds": 50,
        "symbol": "1HZ100V",
        "duration_ticks": 1,
        "stake": 1.0,
        "rationale": "Follow only stronger four-tick directional bursts.",
    },
    {
        "id": "reversal_3tick_minmove020_R100",
        "kind": "reversal",
        "streak": 3,
        "min_move": 0.20,
        "cooldown_seconds": 45,
        "symbol": "R_100",
        "duration_ticks": 1,
        "stake": 1.0,
        "rationale": "Port the strongest early 1HZ100V reversal gate candidate to classic R_100.",
    },
    {
        "id": "mean_revert_5tick_dev020_R100",
        "kind": "mean_revert",
        "window": 5,
        "min_move": 0.20,
        "cooldown_seconds": 45,
        "symbol": "R_100",
        "duration_ticks": 1,
        "stake": 1.0,
        "rationale": "Lower-threshold short mean reversion on R_100 for cross-symbol comparison.",
    },
    {
        "id": "reversal_3tick_minmove020_1HZ10V",
        "kind": "reversal",
        "streak": 3,
        "min_move": 0.20,
        "cooldown_seconds": 45,
        "symbol": "1HZ10V",
        "duration_ticks": 1,
        "stake": 1.0,
        "rationale": "Same three-tick fade on 1HZ10V to test symbol sensitivity.",
    },
    {
        "id": "trend_3tick_minmove020_1HZ10V",
        "kind": "trend",
        "streak": 3,
        "min_move": 0.20,
        "cooldown_seconds": 45,
        "symbol": "1HZ10V",
        "duration_ticks": 1,
        "stake": 1.0,
        "rationale": "Moderate trend-follow candidate on 1HZ10V.",
    },
]

DISCOVERY_MODEL_SPECS = [
    {
        "id": "reversal_3tick_minmove015_1HZ10V",
        "kind": "reversal",
        "streak": 3,
        "min_move": 0.15,
        "cooldown_seconds": 35,
        "symbol": "1HZ10V",
        "duration_ticks": 1,
        "stake": 1.0,
        "rationale": "Looser version of the 100-trade winner to test whether signal frequency can rise without killing EV.",
    },
    {
        "id": "reversal_3tick_minmove025_1HZ10V",
        "kind": "reversal",
        "streak": 3,
        "min_move": 0.25,
        "cooldown_seconds": 45,
        "symbol": "1HZ10V",
        "duration_ticks": 1,
        "stake": 1.0,
        "rationale": "Tighter version of the 100-trade winner to test whether larger local overextension improves quality.",
    },
    {
        "id": "reversal_4tick_minmove020_1HZ10V",
        "kind": "reversal",
        "streak": 4,
        "min_move": 0.20,
        "cooldown_seconds": 45,
        "symbol": "1HZ10V",
        "duration_ticks": 1,
        "stake": 1.0,
        "rationale": "Longer overextension on the same winning symbol.",
    },
    {
        "id": "mean_revert_4tick_dev015_1HZ10V",
        "kind": "mean_revert",
        "window": 4,
        "min_move": 0.15,
        "cooldown_seconds": 35,
        "symbol": "1HZ10V",
        "duration_ticks": 1,
        "stake": 1.0,
        "rationale": "Mean-reversion neighbor around the winning short-horizon fade.",
    },
    {
        "id": "reversal_3tick_minmove020_1HZ25V",
        "kind": "reversal",
        "streak": 3,
        "min_move": 0.20,
        "cooldown_seconds": 45,
        "symbol": "1HZ25V",
        "duration_ticks": 1,
        "stake": 1.0,
        "rationale": "Port the winning rule to Volatility 25 (1s) for symbol sensitivity.",
    },
    {
        "id": "reversal_3tick_minmove030_1HZ25V",
        "kind": "reversal",
        "streak": 3,
        "min_move": 0.30,
        "cooldown_seconds": 45,
        "symbol": "1HZ25V",
        "duration_ticks": 1,
        "stake": 1.0,
        "rationale": "Higher threshold Volatility 25 (1s) fade after local overextension.",
    },
    {
        "id": "mean_revert_5tick_dev025_1HZ25V",
        "kind": "mean_revert",
        "window": 5,
        "min_move": 0.25,
        "cooldown_seconds": 45,
        "symbol": "1HZ25V",
        "duration_ticks": 1,
        "stake": 1.0,
        "rationale": "Short mean-reversion variant on Volatility 25 (1s).",
    },
    {
        "id": "reversal_3tick_minmove030_1HZ50V",
        "kind": "reversal",
        "streak": 3,
        "min_move": 0.30,
        "cooldown_seconds": 45,
        "symbol": "1HZ50V",
        "duration_ticks": 1,
        "stake": 1.0,
        "rationale": "Port the fade family to Volatility 50 (1s), scaled to a larger move threshold.",
    },
    {
        "id": "reversal_4tick_minmove040_1HZ50V",
        "kind": "reversal",
        "streak": 4,
        "min_move": 0.40,
        "cooldown_seconds": 50,
        "symbol": "1HZ50V",
        "duration_ticks": 1,
        "stake": 1.0,
        "rationale": "Stricter four-tick fade on Volatility 50 (1s).",
    },
    {
        "id": "reversal_3tick_minmove040_1HZ75V",
        "kind": "reversal",
        "streak": 3,
        "min_move": 0.40,
        "cooldown_seconds": 45,
        "symbol": "1HZ75V",
        "duration_ticks": 1,
        "stake": 1.0,
        "rationale": "Higher-volatility neighbor test on Volatility 75 (1s).",
    },
    {
        "id": "trend_3tick_minmove020_1HZ10V_discovery",
        "kind": "trend",
        "streak": 3,
        "min_move": 0.20,
        "cooldown_seconds": 45,
        "symbol": "1HZ10V",
        "duration_ticks": 1,
        "stake": 1.0,
        "rationale": "Control arm against the winning reversal on the same symbol and threshold.",
    },
    {
        "id": "reversal_3tick_minmove018_1HZ10V_w2",
        "kind": "reversal",
        "streak": 3,
        "min_move": 0.18,
        "cooldown_seconds": 40,
        "symbol": "1HZ10V",
        "duration_ticks": 1,
        "stake": 1.0,
        "rationale": "Wave 2 near-neighbor of the champion: slightly looser than 0.20 while keeping a cooldown buffer.",
    },
    {
        "id": "reversal_3tick_minmove022_1HZ10V_w2",
        "kind": "reversal",
        "streak": 3,
        "min_move": 0.22,
        "cooldown_seconds": 45,
        "symbol": "1HZ10V",
        "duration_ticks": 1,
        "stake": 1.0,
        "rationale": "Wave 2 near-neighbor of the champion: slightly tighter than 0.20 to test quality over frequency.",
    },
    {
        "id": "reversal_3tick_minmove020_cd30_1HZ10V_w2",
        "kind": "reversal",
        "streak": 3,
        "min_move": 0.20,
        "cooldown_seconds": 30,
        "symbol": "1HZ10V",
        "duration_ticks": 1,
        "stake": 1.0,
        "rationale": "Champion rule with shorter cooldown to test whether higher throughput keeps positive EV.",
    },
    {
        "id": "reversal_3tick_minmove020_cd60_1HZ10V_w2",
        "kind": "reversal",
        "streak": 3,
        "min_move": 0.20,
        "cooldown_seconds": 60,
        "symbol": "1HZ10V",
        "duration_ticks": 1,
        "stake": 1.0,
        "rationale": "Champion rule with longer cooldown to test whether spacing improves trade quality.",
    },
    {
        "id": "reversal_4tick_minmove025_1HZ10V_w2",
        "kind": "reversal",
        "streak": 4,
        "min_move": 0.25,
        "cooldown_seconds": 50,
        "symbol": "1HZ10V",
        "duration_ticks": 1,
        "stake": 1.0,
        "rationale": "Stricter same-symbol fade requiring four aligned ticks and a larger displacement.",
    },
    {
        "id": "mean_revert_6tick_dev020_1HZ10V_w2",
        "kind": "mean_revert",
        "window": 6,
        "min_move": 0.20,
        "cooldown_seconds": 45,
        "symbol": "1HZ10V",
        "duration_ticks": 1,
        "stake": 1.0,
        "rationale": "Longer mean-reversion neighbor on the champion symbol after the 4/5 tick variants failed.",
    },
    {
        "id": "reversal_3tick_minmove025_1HZ25V_w2",
        "kind": "reversal",
        "streak": 3,
        "min_move": 0.25,
        "cooldown_seconds": 45,
        "symbol": "1HZ25V",
        "duration_ticks": 1,
        "stake": 1.0,
        "rationale": "Middle threshold on 1HZ25V between the previously tested 0.20 and 0.30 variants.",
    },
    {
        "id": "reversal_4tick_minmove030_1HZ25V_w2",
        "kind": "reversal",
        "streak": 4,
        "min_move": 0.30,
        "cooldown_seconds": 50,
        "symbol": "1HZ25V",
        "duration_ticks": 1,
        "stake": 1.0,
        "rationale": "Four-tick overextension on 1HZ25V to separate noise from stronger local exhaustion.",
    },
    {
        "id": "mean_revert_6tick_dev030_1HZ25V_w2",
        "kind": "mean_revert",
        "window": 6,
        "min_move": 0.30,
        "cooldown_seconds": 50,
        "symbol": "1HZ25V",
        "duration_ticks": 1,
        "stake": 1.0,
        "rationale": "Longer short-horizon mean reversion on 1HZ25V after the first pass produced a post-100 failure.",
    },
    {
        "id": "reversal_3tick_minmove035_1HZ50V_w2",
        "kind": "reversal",
        "streak": 3,
        "min_move": 0.35,
        "cooldown_seconds": 45,
        "symbol": "1HZ50V",
        "duration_ticks": 1,
        "stake": 1.0,
        "rationale": "Middle threshold on 1HZ50V between the failed 0.30 and stricter 0.40 four-tick variant.",
    },
    {
        "id": "mean_revert_6tick_dev040_1HZ50V_w2",
        "kind": "mean_revert",
        "window": 6,
        "min_move": 0.40,
        "cooldown_seconds": 50,
        "symbol": "1HZ50V",
        "duration_ticks": 1,
        "stake": 1.0,
        "rationale": "Mean-reversion counterpart on 1HZ50V with a larger displacement filter.",
    },
    {
        "id": "reversal_4tick_minmove050_1HZ75V_w2",
        "kind": "reversal",
        "streak": 4,
        "min_move": 0.50,
        "cooldown_seconds": 55,
        "symbol": "1HZ75V",
        "duration_ticks": 1,
        "stake": 1.0,
        "rationale": "Stricter Volatility 75 (1s) overextension test after the first 3-tick variant failed.",
    },
    {
        "id": "reversal_3tick_minmove060_1HZ100V_w2",
        "kind": "reversal",
        "streak": 3,
        "min_move": 0.60,
        "cooldown_seconds": 55,
        "symbol": "1HZ100V",
        "duration_ticks": 1,
        "stake": 1.0,
        "rationale": "Scaled high-volatility revisit of the original synthetic family using a stricter displacement gate.",
    },
    {
        "id": "mean_revert_8tick_dev060_1HZ100V_w2",
        "kind": "mean_revert",
        "window": 8,
        "min_move": 0.60,
        "cooldown_seconds": 60,
        "symbol": "1HZ100V",
        "duration_ticks": 1,
        "stake": 1.0,
        "rationale": "Longer mean-reversion test on 1HZ100V with a high displacement filter to avoid weak noise.",
    },
    {
        "id": "reversal_3tick_minmove016_1HZ10V_w3",
        "kind": "reversal",
        "streak": 3,
        "min_move": 0.16,
        "cooldown_seconds": 40,
        "symbol": "1HZ10V",
        "duration_ticks": 1,
        "stake": 1.0,
        "rationale": "Wave 3: lower-than-champion threshold requested by user, testing whether more frequent entries keep positive EV.",
    },
    {
        "id": "reversal_3tick_minmove018_CALLonly_1HZ10V_w3",
        "kind": "reversal",
        "streak": 3,
        "min_move": 0.18,
        "cooldown_seconds": 40,
        "symbol": "1HZ10V",
        "duration_ticks": 1,
        "stake": 1.0,
        "allowed_contract_types": ["CALL"],
        "rationale": "Wave 3 direction filter: only take CALL side of the near-champion lower-threshold reversal.",
    },
    {
        "id": "reversal_3tick_minmove018_PUTonly_1HZ10V_w3",
        "kind": "reversal",
        "streak": 3,
        "min_move": 0.18,
        "cooldown_seconds": 40,
        "symbol": "1HZ10V",
        "duration_ticks": 1,
        "stake": 1.0,
        "allowed_contract_types": ["PUT"],
        "rationale": "Wave 3 direction filter: only take PUT side of the near-champion lower-threshold reversal.",
    },
    {
        "id": "reversal_3tick_minmove020_stake15_1HZ10V_w3",
        "kind": "reversal",
        "streak": 3,
        "min_move": 0.20,
        "cooldown_seconds": 45,
        "symbol": "1HZ10V",
        "duration_ticks": 1,
        "stake": 1.0,
        "stake_multiplier": 1.5,
        "rationale": "Wave 3 stake test: champion rule at 1.5x the discovery default stake, still demo-only.",
    },
    {
        "id": "reversal_3tick_minmove020_guard_1HZ10V_w3",
        "kind": "reversal",
        "streak": 3,
        "min_move": 0.20,
        "cooldown_seconds": 35,
        "symbol": "1HZ10V",
        "duration_ticks": 1,
        "stake": 1.0,
        "block_guard": {"window": 8, "max_loss": -12.0, "max_gain": 28.0, "pause_seconds": 180},
        "rationale": "Wave 3 block-regime guard: pause after clearly bad or hot 8-trade blocks to reduce block alternation.",
    },
    {
        "id": "reversal_3tick_minmove018_guard_CALLonly_1HZ10V_w3",
        "kind": "reversal",
        "streak": 3,
        "min_move": 0.18,
        "cooldown_seconds": 35,
        "symbol": "1HZ10V",
        "duration_ticks": 1,
        "stake": 1.0,
        "allowed_contract_types": ["CALL"],
        "block_guard": {"window": 8, "max_loss": -12.0, "max_gain": 28.0, "pause_seconds": 180},
        "rationale": "Wave 3 combined rule: lower threshold, CALL-only direction filter, and block-regime pause.",
    },
    {
        "id": "reversal_3tick_minmove018_guard_PUTonly_1HZ10V_w3",
        "kind": "reversal",
        "streak": 3,
        "min_move": 0.18,
        "cooldown_seconds": 35,
        "symbol": "1HZ10V",
        "duration_ticks": 1,
        "stake": 1.0,
        "allowed_contract_types": ["PUT"],
        "block_guard": {"window": 8, "max_loss": -12.0, "max_gain": 28.0, "pause_seconds": 180},
        "rationale": "Wave 3 combined rule: lower threshold, PUT-only direction filter, and block-regime pause.",
    },
    {
        "id": "adaptive_agent_tick_research_1HZ10V_w3",
        "kind": "adaptive_agent",
        "symbol": "1HZ10V",
        "duration_ticks": 1,
        "cooldown_seconds": 30,
        "stake": 1.0,
        "score_window": 40,
        "min_paper_samples": 12,
        "min_rule_score": 0.0,
        "block_guard": {"window": 10, "max_loss": -15.0, "max_gain": 35.0, "pause_seconds": 180},
        "rules": [
            {"id": "rev3_016", "kind": "reversal", "streak": 3, "min_move": 0.16},
            {"id": "rev3_020", "kind": "reversal", "streak": 3, "min_move": 0.20},
            {"id": "rev4_025", "kind": "reversal", "streak": 4, "min_move": 0.25},
            {"id": "mr5_018", "kind": "mean_revert", "window": 5, "min_move": 0.18},
            {"id": "mr6_020", "kind": "mean_revert", "window": 6, "min_move": 0.20},
            {"id": "trend3_020", "kind": "trend", "streak": 3, "min_move": 0.20},
        ],
        "rationale": "Wave 3 agentic model: continuously paper-scores explicit sub-rules and trades only the currently best positive-scoring rule.",
    },
    {
        "id": "reversal_3tick_minmove020_guard_v2_1HZ10V_w4",
        "kind": "reversal",
        "streak": 3,
        "min_move": 0.20,
        "cooldown_seconds": 35,
        "symbol": "1HZ10V",
        "duration_ticks": 1,
        "stake": 1.0,
        "block_guard": {"window": 5, "max_loss": -10.0, "max_gain": 25.0, "pause_seconds": 300},
        "loss_streak_pause": {"losses": 2, "pause_seconds": 420, "phases": ["gate30", "target100"]},
        "rationale": "Wave 4: stricter version of the best failed guard model, pausing faster after loss clusters or overheated five-trade blocks.",
    },
    {
        "id": "reversal_3tick_minmove020_guard_lock_1HZ10V_w4",
        "kind": "reversal",
        "streak": 3,
        "min_move": 0.20,
        "cooldown_seconds": 35,
        "symbol": "1HZ10V",
        "duration_ticks": 1,
        "stake": 1.0,
        "block_guard": {"window": 8, "max_loss": -12.0, "max_gain": 28.0, "pause_seconds": 300},
        "target100_trailing_pause": {"drawdown_from_peak": 25.0, "pause_seconds": 900, "min_trades": 30},
        "rationale": "Wave 4: preserve the Wave 3 gate30 profit by pausing target100 after a large peak-to-trough retrace.",
    },
    {
        "id": "reversal_3tick_minmove020_guard_2losspause_1HZ10V_w4",
        "kind": "reversal",
        "streak": 3,
        "min_move": 0.20,
        "cooldown_seconds": 35,
        "symbol": "1HZ10V",
        "duration_ticks": 1,
        "stake": 1.0,
        "loss_streak_pause": {"losses": 2, "pause_seconds": 600, "phases": ["gate30", "target100"]},
        "rationale": "Wave 4: isolate whether a simple two-loss pause can avoid the drawdown block that killed the best Wave 3 lead.",
    },
    {
        "id": "adaptive_agent_tick_research_v2_1HZ10V_w4",
        "kind": "adaptive_agent",
        "symbol": "1HZ10V",
        "duration_ticks": 1,
        "cooldown_seconds": 40,
        "stake": 1.0,
        "score_window": 80,
        "min_paper_samples": 40,
        "min_rule_score": 12.0,
        "block_guard": {"window": 6, "max_loss": -10.0, "max_gain": 22.0, "pause_seconds": 420},
        "loss_streak_pause": {"losses": 2, "pause_seconds": 900, "phases": ["gate30", "target100"]},
        "rules": [
            {"id": "rev3_020", "kind": "reversal", "streak": 3, "min_move": 0.20},
            {"id": "rev4_025", "kind": "reversal", "streak": 4, "min_move": 0.25},
            {"id": "mr5_020", "kind": "mean_revert", "window": 5, "min_move": 0.20},
            {"id": "mr6_025", "kind": "mean_revert", "window": 6, "min_move": 0.25},
        ],
        "rationale": "Wave 4: agentic selector with stricter paper probation after Wave 3 paper-score/live mismatch.",
    },
    {
        "id": "adaptive_agent_consistency_pnl500_v3_1HZ10V",
        "kind": "adaptive_agent",
        "symbol": "1HZ10V",
        "duration_ticks": 1,
        "cooldown_seconds": 35,
        "stake": 1.0,
        "score_window": 80,
        "min_paper_samples": 40,
        "min_rule_score": 2.0,
        "agent_status_log_seconds": 30,
        "block_guard": {"window": 8, "max_loss": -22.0, "max_gain": 45.0, "pause_seconds": 300},
        "loss_streak_pause": {"losses": 2, "pause_seconds": 600, "phases": ["gate30", "target100", "post100"]},
        "target100_trailing_pause": {
            "drawdown_from_peak": 35.0,
            "pause_seconds": 900,
            "min_trades": 30,
            "phases": ["target100", "post100"],
        },
        "rules": [
            {"id": "rev3_018_call", "kind": "reversal", "streak": 3, "min_move": 0.18, "allowed_contract_types": ["CALL"]},
            {"id": "rev3_018_put", "kind": "reversal", "streak": 3, "min_move": 0.18, "allowed_contract_types": ["PUT"]},
            {"id": "rev3_020_call", "kind": "reversal", "streak": 3, "min_move": 0.20, "allowed_contract_types": ["CALL"]},
            {"id": "rev3_020_put", "kind": "reversal", "streak": 3, "min_move": 0.20, "allowed_contract_types": ["PUT"]},
            {"id": "rev3_022", "kind": "reversal", "streak": 3, "min_move": 0.22},
            {"id": "rev4_025", "kind": "reversal", "streak": 4, "min_move": 0.25},
            {"id": "mr5_020_call", "kind": "mean_revert", "window": 5, "min_move": 0.20, "allowed_contract_types": ["CALL"]},
            {"id": "mr5_020_put", "kind": "mean_revert", "window": 5, "min_move": 0.20, "allowed_contract_types": ["PUT"]},
            {"id": "mr6_025", "kind": "mean_revert", "window": 6, "min_move": 0.25},
            {"id": "trend3_020", "kind": "trend", "streak": 3, "min_move": 0.20},
        ],
        "rationale": "Agentic PnL500 campaign: reuse champion-neighbor reversal, sub-0.20 threshold, direction filters, trend control, and rolling paper-score selection for sustained demo PnL.",
    },
    {
        "id": "adaptive_agent_consistency_pnl500_v4_guarded_1HZ10V",
        "kind": "adaptive_agent",
        "symbol": "1HZ10V",
        "duration_ticks": 1,
        "cooldown_seconds": 45,
        "stake": 1.0,
        "score_window": 120,
        "min_paper_samples": 80,
        "min_rule_score": 6.0,
        "agent_status_log_seconds": 30,
        "block_guard": {"window": 4, "max_loss": -12.0, "max_gain": 28.0, "pause_seconds": 600},
        "loss_streak_pause": {"losses": 2, "pause_seconds": 900, "phases": ["gate30", "target100", "post100"]},
        "agent_rule_live_guard": {"losses": 1, "pause_seconds": 1800, "window": 3, "max_loss": -1.0},
        "target100_trailing_pause": {
            "drawdown_from_peak": 25.0,
            "pause_seconds": 1200,
            "min_trades": 30,
            "phases": ["target100", "post100"],
        },
        "rules": [
            {"id": "rev3_018_call", "kind": "reversal", "streak": 3, "min_move": 0.18, "allowed_contract_types": ["CALL"]},
            {"id": "rev3_018_put", "kind": "reversal", "streak": 3, "min_move": 0.18, "allowed_contract_types": ["PUT"]},
            {"id": "rev3_020_call", "kind": "reversal", "streak": 3, "min_move": 0.20, "allowed_contract_types": ["CALL"]},
            {"id": "rev3_020_put", "kind": "reversal", "streak": 3, "min_move": 0.20, "allowed_contract_types": ["PUT"]},
            {"id": "rev3_022", "kind": "reversal", "streak": 3, "min_move": 0.22},
            {"id": "rev4_025", "kind": "reversal", "streak": 4, "min_move": 0.25},
            {"id": "mr5_020_put", "kind": "mean_revert", "window": 5, "min_move": 0.20, "allowed_contract_types": ["PUT"]},
            {"id": "mr6_025", "kind": "mean_revert", "window": 6, "min_move": 0.25},
        ],
        "rationale": "Agentic PnL500 v4: tighten paper gate and quarantine any sub-rule after live loss to reduce paper/live mismatch seen in v3.",
    },
    {
        "id": "adaptive_agent_consistency_pnl500_v5_reversal_only_1HZ10V",
        "kind": "adaptive_agent",
        "symbol": "1HZ10V",
        "duration_ticks": 1,
        "cooldown_seconds": 50,
        "stake": 1.0,
        "score_window": 180,
        "min_paper_samples": 120,
        "min_rule_score": 8.0,
        "agent_status_log_seconds": 30,
        "block_guard": {"window": 3, "max_loss": -12.0, "max_gain": 24.0, "pause_seconds": 1200},
        "loss_streak_pause": {"losses": 2, "pause_seconds": 1800, "phases": ["gate30", "target100", "post100"]},
        "agent_rule_live_guard": {"losses": 1, "pause_seconds": 7200, "window": 3, "max_loss": -1.0},
        "target100_trailing_pause": {
            "drawdown_from_peak": 20.0,
            "pause_seconds": 1800,
            "min_trades": 30,
            "phases": ["target100", "post100"],
        },
        "rules": [
            {"id": "rev3_018_call", "kind": "reversal", "streak": 3, "min_move": 0.18, "allowed_contract_types": ["CALL"]},
            {"id": "rev3_018_put", "kind": "reversal", "streak": 3, "min_move": 0.18, "allowed_contract_types": ["PUT"]},
            {"id": "rev3_020_call", "kind": "reversal", "streak": 3, "min_move": 0.20, "allowed_contract_types": ["CALL"]},
            {"id": "rev3_020_put", "kind": "reversal", "streak": 3, "min_move": 0.20, "allowed_contract_types": ["PUT"]},
            {"id": "rev3_022_call", "kind": "reversal", "streak": 3, "min_move": 0.22, "allowed_contract_types": ["CALL"]},
            {"id": "rev3_022_put", "kind": "reversal", "streak": 3, "min_move": 0.22, "allowed_contract_types": ["PUT"]},
            {"id": "rev4_025_call", "kind": "reversal", "streak": 4, "min_move": 0.25, "allowed_contract_types": ["CALL"]},
            {"id": "rev4_025_put", "kind": "reversal", "streak": 4, "min_move": 0.25, "allowed_contract_types": ["PUT"]},
        ],
        "rationale": "Agentic PnL500 v5 fallback: restrict the agent to the champion reversal lineage after v3/v4 mean-reversion sub-rules showed paper/live mismatch.",
    },
    {
        "id": "adaptive_agent_consensus_pnl500_v6_reversal_cluster_1HZ10V",
        "kind": "adaptive_agent",
        "symbol": "1HZ10V",
        "duration_ticks": 1,
        "cooldown_seconds": 55,
        "stake": 1.0,
        "score_window": 240,
        "min_paper_samples": 160,
        "min_rule_score": 4.0,
        "min_consensus_rules": 2,
        "min_consensus_score": 16.0,
        "consensus_key": "contract_type",
        "agent_status_log_seconds": 30,
        "block_guard": {"window": 3, "max_loss": -12.0, "max_gain": 24.0, "pause_seconds": 1800},
        "loss_streak_pause": {"losses": 2, "pause_seconds": 3600, "phases": ["gate30", "target100", "post100"]},
        "agent_rule_live_guard": {"losses": 1, "pause_seconds": 10800, "window": 3, "max_loss": -1.0},
        "target100_trailing_pause": {
            "drawdown_from_peak": 18.0,
            "pause_seconds": 2400,
            "min_trades": 30,
            "phases": ["target100", "post100"],
        },
        "rules": [
            {"id": "rev3_018_call", "kind": "reversal", "streak": 3, "min_move": 0.18, "allowed_contract_types": ["CALL"]},
            {"id": "rev3_020_call", "kind": "reversal", "streak": 3, "min_move": 0.20, "allowed_contract_types": ["CALL"]},
            {"id": "rev3_022_call", "kind": "reversal", "streak": 3, "min_move": 0.22, "allowed_contract_types": ["CALL"]},
            {"id": "rev4_025_call", "kind": "reversal", "streak": 4, "min_move": 0.25, "allowed_contract_types": ["CALL"]},
            {"id": "rev3_018_put", "kind": "reversal", "streak": 3, "min_move": 0.18, "allowed_contract_types": ["PUT"]},
            {"id": "rev3_020_put", "kind": "reversal", "streak": 3, "min_move": 0.20, "allowed_contract_types": ["PUT"]},
            {"id": "rev3_022_put", "kind": "reversal", "streak": 3, "min_move": 0.22, "allowed_contract_types": ["PUT"]},
            {"id": "rev4_025_put", "kind": "reversal", "streak": 4, "min_move": 0.25, "allowed_contract_types": ["PUT"]},
        ],
        "rationale": "Agentic PnL500 v6 fallback: require a same-direction cluster of reversal sub-rules before trading, so one isolated high paper score cannot walk the model through fragile live rules.",
    },
    {
        "id": "adaptive_agent_consensus_pnl500_v7_momentum_mirror_1HZ10V",
        "kind": "adaptive_agent",
        "symbol": "1HZ10V",
        "duration_ticks": 1,
        "cooldown_seconds": 55,
        "stake": 1.0,
        "score_window": 240,
        "min_paper_samples": 160,
        "min_rule_score": 4.0,
        "min_consensus_rules": 2,
        "min_consensus_score": 16.0,
        "consensus_key": "contract_type",
        "agent_status_log_seconds": 30,
        "block_guard": {"window": 3, "max_loss": -12.0, "max_gain": 24.0, "pause_seconds": 1800},
        "loss_streak_pause": {"losses": 2, "pause_seconds": 3600, "phases": ["gate30", "target100", "post100"]},
        "agent_rule_live_guard": {"losses": 1, "pause_seconds": 10800, "window": 3, "max_loss": -1.0},
        "target100_trailing_pause": {
            "drawdown_from_peak": 18.0,
            "pause_seconds": 2400,
            "min_trades": 30,
            "phases": ["target100", "post100"],
        },
        "rules": [
            {"id": "trend3_018_call", "kind": "trend", "streak": 3, "min_move": 0.18, "allowed_contract_types": ["CALL"]},
            {"id": "trend3_020_call", "kind": "trend", "streak": 3, "min_move": 0.20, "allowed_contract_types": ["CALL"]},
            {"id": "trend3_022_call", "kind": "trend", "streak": 3, "min_move": 0.22, "allowed_contract_types": ["CALL"]},
            {"id": "trend4_025_call", "kind": "trend", "streak": 4, "min_move": 0.25, "allowed_contract_types": ["CALL"]},
            {"id": "trend3_018_put", "kind": "trend", "streak": 3, "min_move": 0.18, "allowed_contract_types": ["PUT"]},
            {"id": "trend3_020_put", "kind": "trend", "streak": 3, "min_move": 0.20, "allowed_contract_types": ["PUT"]},
            {"id": "trend3_022_put", "kind": "trend", "streak": 3, "min_move": 0.22, "allowed_contract_types": ["PUT"]},
            {"id": "trend4_025_put", "kind": "trend", "streak": 4, "min_move": 0.25, "allowed_contract_types": ["PUT"]},
        ],
        "rationale": "Agentic PnL500 v7 fallback: if reversal consensus stays negative after enough paper samples, test the momentum mirror with the same consensus gate instead of loosening isolated reversal entries.",
    },
    {
        "id": "adaptive_agent_crossfamily_pnl500_v8_regime_switch_1HZ10V",
        "kind": "adaptive_agent",
        "symbol": "1HZ10V",
        "duration_ticks": 1,
        "cooldown_seconds": 60,
        "stake": 1.0,
        "score_window": 300,
        "min_paper_samples": 160,
        "min_rule_score": 2.0,
        "min_consensus_rules": 2,
        "min_consensus_score": 12.0,
        "min_consensus_families": 2,
        "consensus_key": "contract_type",
        "consensus_family_key": "rule_family",
        "agent_status_log_seconds": 30,
        "block_guard": {"window": 3, "max_loss": -12.0, "max_gain": 24.0, "pause_seconds": 2400},
        "loss_streak_pause": {"losses": 2, "pause_seconds": 3600, "phases": ["gate30", "target100", "post100"]},
        "agent_rule_live_guard": {"losses": 1, "pause_seconds": 10800, "window": 3, "max_loss": -1.0},
        "target100_trailing_pause": {
            "drawdown_from_peak": 18.0,
            "pause_seconds": 2400,
            "min_trades": 30,
            "phases": ["target100", "post100"],
        },
        "rules": [
            {"id": "rev3_016_call", "kind": "reversal", "family": "reversal", "streak": 3, "min_move": 0.16, "allowed_contract_types": ["CALL"]},
            {"id": "rev3_016_put", "kind": "reversal", "family": "reversal", "streak": 3, "min_move": 0.16, "allowed_contract_types": ["PUT"]},
            {"id": "rev3_020_call", "kind": "reversal", "family": "reversal", "streak": 3, "min_move": 0.20, "allowed_contract_types": ["CALL"]},
            {"id": "rev3_020_put", "kind": "reversal", "family": "reversal", "streak": 3, "min_move": 0.20, "allowed_contract_types": ["PUT"]},
            {"id": "mr4_016_call", "kind": "mean_revert", "family": "mean_revert", "window": 4, "min_move": 0.16, "allowed_contract_types": ["CALL"]},
            {"id": "mr4_016_put", "kind": "mean_revert", "family": "mean_revert", "window": 4, "min_move": 0.16, "allowed_contract_types": ["PUT"]},
            {"id": "mr6_020_call", "kind": "mean_revert", "family": "mean_revert", "window": 6, "min_move": 0.20, "allowed_contract_types": ["CALL"]},
            {"id": "mr6_020_put", "kind": "mean_revert", "family": "mean_revert", "window": 6, "min_move": 0.20, "allowed_contract_types": ["PUT"]},
            {"id": "trend3_018_call", "kind": "trend", "family": "momentum", "streak": 3, "min_move": 0.18, "allowed_contract_types": ["CALL"]},
            {"id": "trend3_018_put", "kind": "trend", "family": "momentum", "streak": 3, "min_move": 0.18, "allowed_contract_types": ["PUT"]},
            {"id": "trend4_025_call", "kind": "trend", "family": "momentum", "streak": 4, "min_move": 0.25, "allowed_contract_types": ["CALL"]},
            {"id": "trend4_025_put", "kind": "trend", "family": "momentum", "streak": 4, "min_move": 0.25, "allowed_contract_types": ["PUT"]},
        ],
        "rationale": "Agentic PnL500 v8 fallback: dynamically score reversal, mean-reversion, and momentum families, then trade only when at least two families agree on the same direction, reducing the positive/negative block alternation seen in prior live runs.",
    },
    {
        "id": "adaptive_agent_crossfamily_memory_pnl500_v9_1HZ10V",
        "kind": "adaptive_agent",
        "symbol": "1HZ10V",
        "duration_ticks": 1,
        "cooldown_seconds": 60,
        "stake": 1.0,
        "score_window": 300,
        "min_paper_samples": 160,
        "min_rule_score": 2.0,
        "min_consensus_rules": 2,
        "min_consensus_score": 12.0,
        "min_consensus_families": 2,
        "consensus_key": "contract_type",
        "consensus_family_key": "rule_family",
        "consensus_memory_seconds": 300,
        "agent_status_log_seconds": 30,
        "block_guard": {"window": 3, "max_loss": -12.0, "max_gain": 24.0, "pause_seconds": 2400},
        "loss_streak_pause": {"losses": 2, "pause_seconds": 3600, "phases": ["gate30", "target100", "post100"]},
        "agent_rule_live_guard": {"losses": 1, "pause_seconds": 10800, "window": 3, "max_loss": -1.0},
        "target100_trailing_pause": {
            "drawdown_from_peak": 18.0,
            "pause_seconds": 2400,
            "min_trades": 30,
            "phases": ["target100", "post100"],
        },
        "rules": [
            {"id": "rev3_016_call", "kind": "reversal", "family": "reversal", "streak": 3, "min_move": 0.16, "allowed_contract_types": ["CALL"]},
            {"id": "rev3_016_put", "kind": "reversal", "family": "reversal", "streak": 3, "min_move": 0.16, "allowed_contract_types": ["PUT"]},
            {"id": "rev3_020_call", "kind": "reversal", "family": "reversal", "streak": 3, "min_move": 0.20, "allowed_contract_types": ["CALL"]},
            {"id": "rev3_020_put", "kind": "reversal", "family": "reversal", "streak": 3, "min_move": 0.20, "allowed_contract_types": ["PUT"]},
            {"id": "mr4_016_call", "kind": "mean_revert", "family": "mean_revert", "window": 4, "min_move": 0.16, "allowed_contract_types": ["CALL"]},
            {"id": "mr4_016_put", "kind": "mean_revert", "family": "mean_revert", "window": 4, "min_move": 0.16, "allowed_contract_types": ["PUT"]},
            {"id": "mr6_020_call", "kind": "mean_revert", "family": "mean_revert", "window": 6, "min_move": 0.20, "allowed_contract_types": ["CALL"]},
            {"id": "mr6_020_put", "kind": "mean_revert", "family": "mean_revert", "window": 6, "min_move": 0.20, "allowed_contract_types": ["PUT"]},
            {"id": "trend3_018_call", "kind": "trend", "family": "momentum", "streak": 3, "min_move": 0.18, "allowed_contract_types": ["CALL"]},
            {"id": "trend3_018_put", "kind": "trend", "family": "momentum", "streak": 3, "min_move": 0.18, "allowed_contract_types": ["PUT"]},
            {"id": "trend4_025_call", "kind": "trend", "family": "momentum", "streak": 4, "min_move": 0.25, "allowed_contract_types": ["CALL"]},
            {"id": "trend4_025_put", "kind": "trend", "family": "momentum", "streak": 4, "min_move": 0.25, "allowed_contract_types": ["PUT"]},
        ],
        "rationale": "Agentic PnL500 v9 fallback: keep v8 cross-family safeguards, but let a recent eligible family vote confirm a current eligible rule for a few minutes, so valid regime agreement is not lost solely because families do not emit on the same tick.",
    },
]


def select_model_specs(model_set):
    if model_set == "discovery":
        return DISCOVERY_MODEL_SPECS
    if model_set == "all":
        return MODEL_SPECS + DISCOVERY_MODEL_SPECS
    return MODEL_SPECS


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def configure_logging(log_path):
    logger = logging.getLogger("STRATEGY_TOURNAMENT")
    logger.setLevel(logging.INFO)
    logger.handlers.clear()
    formatter = logging.Formatter("%(asctime)s - STRATEGY_TOURNAMENT:%(levelname)s:%(message)s")
    file_handler = logging.FileHandler(log_path, encoding="utf-8")
    file_handler.setFormatter(formatter)
    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    logger.addHandler(stream_handler)
    return logger


def load_jsonl(path):
    rows = []
    path = Path(path)
    if not path.exists():
        return rows
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if line.strip():
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return rows


def percentile(values, q):
    if not values:
        return "n/a"
    ordered = sorted(values)
    index = min(len(ordered) - 1, math.ceil(q * len(ordered)) - 1)
    return ordered[index]


def empty_model_state(spec, status="pending"):
    return {
        "id": spec["id"],
        "kind": spec["kind"],
        "status": status,
        "phase": "gate30",
        "symbol": spec["symbol"],
        "stake": spec["stake"],
        "duration_ticks": spec["duration_ticks"],
        "cooldown_seconds": spec["cooldown_seconds"],
        "rationale": spec["rationale"],
        "trades": 0,
        "wins": 0,
        "losses": 0,
        "rejects": 0,
        "errors": 0,
        "pnl": 0.0,
        "peak_pnl": 0.0,
        "max_drawdown": 0.0,
        "latencies_ms": [],
        "recent_profits": [],
        "blocked_until_ts": 0.0,
        "blocked_reason": None,
        "last_agent_rule": None,
        "last_agent_status": None,
        "rule_live_stats": {},
        "promoted_at": None,
        "pivot_reason": None,
        "started_at": None,
        "stopped_at": None,
    }


class StrategyTournament:
    def __init__(self, args, logger):
        self.args = args
        self.logger = logger
        self.client = None
        self.model_specs = select_model_specs(args.model_set)
        self.apply_rotation_model_filter()
        self.ticks_by_symbol = {spec["symbol"]: [] for spec in self.model_specs}
        self.adaptive_agents = {}
        self.last_trade_at = 0.0
        self.in_trade = False
        self.done = asyncio.Event()
        self.state_path = Path(args.state_json)
        self.events_path = Path(args.events_jsonl)
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self.events_path.parent.mkdir(parents=True, exist_ok=True)
        self.state = self.load_or_init_state()

    def rotation_model_ids(self):
        return [value.strip() for value in self.args.rotation_model_ids.split(",") if value.strip()]

    def rotation_enabled(self):
        return bool(self.rotation_model_ids())

    def apply_rotation_model_filter(self):
        ids = self.rotation_model_ids()
        if not ids:
            return
        specs_by_id = {spec["id"]: spec for spec in self.model_specs}
        missing = [model_id for model_id in ids if model_id not in specs_by_id]
        if missing:
            raise RuntimeError(f"rotation model id(s) not found in selected model set: {', '.join(missing)}")
        self.model_specs = [specs_by_id[model_id] for model_id in ids]

    def rotation_state_template(self):
        return {
            "enabled": self.rotation_enabled(),
            "model_ids": self.rotation_model_ids(),
            "global_trades": 0,
            "global_pnl": 0.0,
            "global_peak_pnl": 0.0,
            "global_max_drawdown": 0.0,
            "target_trades": self.args.global_target_trades,
            "target_pnl": self.args.global_target_pnl,
            "hard_drawdown_stop": self.args.global_hard_drawdown_stop,
            "peak_drop_trigger": self.args.rotation_peak_drop,
            "recent_window": self.args.rotation_recent_window,
            "recent_loss_trigger": self.args.rotation_recent_loss,
            "min_trades": self.args.rotation_min_trades,
            "model_cooldown_seconds": self.args.rotation_model_cooldown_seconds,
            "switches": [],
        }

    def load_or_init_state(self):
        if self.state_path.exists() and not self.args.reset:
            state = json.loads(self.state_path.read_text(encoding="utf-8"))
            self.reconcile_model_specs(state)
            self.refresh_runtime_state(state)
            if self.args.start_model_id:
                self.prepare_priority_start(state, self.args.start_model_id)
            if self.args.continue_model_id:
                self.prepare_model_continuation(state, self.args.continue_model_id)
            self.write_state(state)
            return state

        models = [empty_model_state(spec) for spec in self.model_specs]
        state = {
            "goal": (
                "PnL +500 em ate 1000 trades com rotacao sequencial de modelos"
                if self.rotation_enabled()
                else "PnL positivo apos 100 trades, com gate positivo em 30 trades"
            ),
            "model_set": self.args.model_set,
            "status": "collecting",
            "job_id": self.args.job_id,
            "started_at": utc_now(),
            "updated_at": utc_now(),
            "real_money_allowed": False,
            "gate_trades": self.args.gate_trades,
            "target_trades": self.args.target_trades,
            "healthy_drawdown_30": self.args.healthy_drawdown_30,
            "healthy_drawdown_100": self.args.healthy_drawdown_100,
            "hard_drawdown_stop": self.args.hard_drawdown_stop,
            "target_pnl": self.args.target_pnl,
            "post_target_stake": self.args.post_target_stake,
            "post_target_max_trades": self.args.post_target_max_trades,
            "post_target_kill_loss": self.args.post_target_kill_loss,
            "stake_override": self.args.stake_override,
            "current_model_index": 0,
            "models": models,
            "champions": [],
            "backlog": [],
            "last_event": None,
            "runtime": {
                "pid": os.getpid(),
                "log_path": str(Path(self.args.log_path).resolve()),
                "events_jsonl": str(self.events_path.resolve()),
                "state_json": str(self.state_path.resolve()),
                "app_id_env": self.args.app_id_env,
                "api_token_env": self.args.api_token_env,
            },
        }
        if self.rotation_enabled():
            state["rotation"] = self.rotation_state_template()
        if self.args.seed_failed_ledger:
            self.seed_failed_trend_model(state, Path(self.args.seed_failed_ledger))
        if self.args.start_model_id:
            self.prepare_priority_start(state, self.args.start_model_id)
        if self.args.continue_model_id:
            raise RuntimeError("--continue-model-id requires an existing state file")
        self.write_state(state)
        return state

    def refresh_runtime_state(self, state):
        state["job_id"] = self.args.job_id
        state["model_set"] = self.args.model_set
        state["gate_trades"] = self.args.gate_trades
        state["target_trades"] = self.args.target_trades
        state["healthy_drawdown_30"] = self.args.healthy_drawdown_30
        state["healthy_drawdown_100"] = self.args.healthy_drawdown_100
        state["hard_drawdown_stop"] = self.args.hard_drawdown_stop
        state["target_pnl"] = self.args.target_pnl
        state["post_target_stake"] = self.args.post_target_stake
        state["post_target_max_trades"] = self.args.post_target_max_trades
        state["post_target_kill_loss"] = self.args.post_target_kill_loss
        state["stake_override"] = self.args.stake_override
        if self.rotation_enabled():
            rotation = state.setdefault("rotation", self.rotation_state_template())
            rotation.update(
                {
                    "enabled": True,
                    "model_ids": self.rotation_model_ids(),
                    "target_trades": self.args.global_target_trades,
                    "target_pnl": self.args.global_target_pnl,
                    "hard_drawdown_stop": self.args.global_hard_drawdown_stop,
                    "peak_drop_trigger": self.args.rotation_peak_drop,
                    "recent_window": self.args.rotation_recent_window,
                    "recent_loss_trigger": self.args.rotation_recent_loss,
                    "min_trades": self.args.rotation_min_trades,
                    "model_cooldown_seconds": self.args.rotation_model_cooldown_seconds,
                }
            )
        state.setdefault("runtime", {}).update(
            {
                "pid": os.getpid(),
                "log_path": str(Path(self.args.log_path).resolve()),
                "events_jsonl": str(self.events_path.resolve()),
                "state_json": str(self.state_path.resolve()),
                "loaded_existing_state_at": utc_now(),
                "app_id_env": self.args.app_id_env,
                "api_token_env": self.args.api_token_env,
            }
        )

    def prepare_model_continuation(self, state, model_id):
        models = state.get("models", [])
        for index, model in enumerate(models):
            if model.get("id") != model_id:
                continue

            if model.get("status") == "backlog" and not self.args.allow_backlog_continuation:
                raise RuntimeError(f"refusing to continue backlogged model without --allow-backlog-continuation: {model_id}")

            state["current_model_index"] = index
            state["status"] = "collecting_continuation"
            model["phase"] = "target100"
            model["status"] = "collecting_target100"
            model["stopped_at"] = None
            model["pivot_reason"] = None
            state.setdefault("runtime", {}).update(
                {
                    "continuation_model_id": model_id,
                    "continuation_started_at": utc_now(),
                    "continued_from_trades": model.get("trades", 0),
                    "continued_from_pnl": model.get("pnl", 0.0),
                }
            )
            return

        raise RuntimeError(f"model not found for continuation: {model_id}")

    def prepare_priority_start(self, state, model_id):
        if self.args.continue_model_id:
            raise RuntimeError("--start-model-id cannot be combined with --continue-model-id")
        models = state.get("models", [])
        target_index = next((index for index, model in enumerate(models) if model.get("id") == model_id), None)
        if target_index is None:
            raise RuntimeError(f"model not found for priority start: {model_id}")

        current_index = int(state.get("current_model_index", 0))
        for index in range(current_index, target_index):
            model = models[index]
            if model.get("status") == "backlog":
                continue
            model["status"] = "backlog"
            model["pivot_reason"] = "priority_skipped_for_requested_wave3"
            model["stopped_at"] = utc_now()
            state.setdefault("backlog", []).append(
                {
                    "model_id": model["id"],
                    "reason": model["pivot_reason"],
                    "trades": model.get("trades", 0),
                    "pnl": model.get("pnl", 0.0),
                }
            )

        target = models[target_index]
        if target.get("status") == "backlog" and not self.args.allow_backlog_continuation:
            raise RuntimeError(f"refusing to start backlogged model without --allow-backlog-continuation: {model_id}")
        if target.get("status") == "backlog":
            target["status"] = "pending"
            target["pivot_reason"] = None
            target["stopped_at"] = None
        state["current_model_index"] = target_index
        state["status"] = "collecting_priority_start"
        state.setdefault("runtime", {}).update(
            {
                "priority_start_model_id": model_id,
                "priority_started_at": utc_now(),
                "priority_skipped_from_index": current_index,
                "priority_skipped_to_index": target_index,
            }
        )

    def reconcile_model_specs(self, state):
        existing_ids = {model["id"] for model in state.get("models", [])}
        old_len = len(state.get("models", []))
        appended = []
        for spec in self.model_specs:
            if spec["id"] not in existing_ids:
                state.setdefault("models", []).append(empty_model_state(spec))
                appended.append(spec["id"])
        if appended:
            state.setdefault("runtime", {})["reconciled_model_specs_at"] = utc_now()
            state["runtime"]["reconciled_model_specs"] = appended
            if state.get("current_model_index", 0) >= old_len and state.get("status") != "goal_candidate_found":
                state["current_model_index"] = old_len
                state["status"] = "collecting"

    def seed_failed_trend_model(self, state, ledger_path):
        rows = load_jsonl(ledger_path)
        settled = [row for row in rows if row.get("event") == "settled"]
        if not settled:
            return
        pnl = float(settled[-1].get("pnl", sum(float(row.get("profit", 0)) for row in settled)))
        wins = sum(1 for row in settled if float(row.get("profit", 0)) > 0)
        losses = sum(1 for row in settled if float(row.get("profit", 0)) < 0)
        seeded = empty_model_state(
            {
                "id": "trend_2tick_cooldown30_JOB003_seed",
                "kind": "trend",
                "symbol": "1HZ100V",
                "stake": 1.0,
                "duration_ticks": 1,
                "cooldown_seconds": 30,
                "rationale": "Seeded from JOB-20260702-003; failed 30-trade positive-PnL gate.",
            },
            status="backlog",
        )
        seeded.update(
            {
                "trades": len(settled),
                "wins": wins,
                "losses": losses,
                "pnl": round(pnl, 4),
                "pivot_reason": "failed_gate30_seed_pnl_nonpositive",
                "stopped_at": utc_now(),
            }
        )
        state["models"].insert(0, seeded)
        state["backlog"].append(
            {
                "model_id": seeded["id"],
                "reason": seeded["pivot_reason"],
                "trades": seeded["trades"],
                "pnl": seeded["pnl"],
                "source": str(ledger_path),
            }
        )
        state["current_model_index"] = 1

    def write_state(self, state=None):
        target = state if state is not None else self.state
        target["updated_at"] = utc_now()
        self.state_path.write_text(json.dumps(target, indent=2, sort_keys=True), encoding="utf-8")

    def log_event(self, event, **fields):
        row = {"ts": utc_now(), "event": event, "job_id": self.args.job_id, **fields}
        with self.events_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, sort_keys=True) + "\n")
        self.state["last_event"] = row
        self.write_state()

    def current_model(self):
        idx = self.state["current_model_index"]
        if idx >= len(self.state["models"]):
            return None
        return self.state["models"][idx]

    def current_spec(self):
        model = self.current_model()
        if not model:
            return None
        return next((spec for spec in self.model_specs if spec["id"] == model["id"]), None)

    def start_current_model(self):
        model = self.current_model()
        if not model:
            self.state["status"] = "exhausted_models"
            self.write_state()
            self.done.set()
            return None
        if model["status"] == "pending":
            model["status"] = "collecting_rotation" if self.rotation_enabled() else "collecting_gate30"
            model["phase"] = "rotation" if self.rotation_enabled() else "gate30"
            model["started_at"] = utc_now()
            self.logger.info("MODEL_START id=%s phase=%s rationale=%s", model["id"], model["phase"], model["rationale"])
            self.log_event("model_start", model_id=model["id"], phase=model["phase"], rationale=model["rationale"])
        self.write_state()
        return model

    def pivot_current_model(self, reason):
        model = self.current_model()
        if not model:
            return
        if self.args.stop_on_pivot:
            model["status"] = reason
            model["pivot_reason"] = reason
            model["stopped_at"] = utc_now()
            self.state["status"] = reason
            self.logger.warning(
                "STOP_ON_PIVOT model=%s reason=%s trades=%s pnl=%.2f",
                model["id"],
                reason,
                model["trades"],
                model["pnl"],
            )
            self.log_event("stop_on_pivot", model_id=model["id"], reason=reason, trades=model["trades"], pnl=model["pnl"])
            self.done.set()
            return
        model["status"] = "backlog"
        model["pivot_reason"] = reason
        model["stopped_at"] = utc_now()
        self.state["backlog"].append(
            {"model_id": model["id"], "reason": reason, "trades": model["trades"], "pnl": model["pnl"]}
        )
        self.logger.warning("PIVOT model=%s reason=%s trades=%s pnl=%.2f", model["id"], reason, model["trades"], model["pnl"])
        self.log_event("pivot", model_id=model["id"], reason=reason, trades=model["trades"], pnl=model["pnl"])
        self.state["current_model_index"] += 1
        self.start_current_model()

    def rotate_current_model(self, reason):
        model = self.current_model()
        if not model:
            return

        now_ts = time.time()
        cooldown = max(0.0, float(self.args.rotation_model_cooldown_seconds))
        model["status"] = "rotation_cooldown"
        model["rotation_last_reason"] = reason
        model["rotation_cooldown_until_ts"] = now_ts + cooldown
        model["rotation_stopped_at"] = utc_now()

        rotation = self.state.setdefault("rotation", self.rotation_state_template())
        rotation.setdefault("switches", []).append(
            {
                "ts": utc_now(),
                "from_model_id": model["id"],
                "reason": reason,
                "trades": model["trades"],
                "pnl": model["pnl"],
                "peak_pnl": model["peak_pnl"],
                "global_trades": rotation.get("global_trades", 0),
                "global_pnl": rotation.get("global_pnl", 0.0),
            }
        )
        self.logger.warning(
            "ROTATE_OUT model=%s reason=%s trades=%s pnl=%.2f peak=%.2f",
            model["id"],
            reason,
            model["trades"],
            model["pnl"],
            model["peak_pnl"],
        )
        self.log_event(
            "rotation_switch_out",
            model_id=model["id"],
            reason=reason,
            trades=model["trades"],
            pnl=model["pnl"],
            peak_pnl=model["peak_pnl"],
        )

        models = self.state.get("models", [])
        if not models:
            self.state["status"] = "exhausted_rotation_models"
            self.done.set()
            return

        current_index = int(self.state.get("current_model_index", 0))
        next_index = None
        for offset in range(1, len(models) + 1):
            candidate_index = (current_index + offset) % len(models)
            candidate = models[candidate_index]
            if float(candidate.get("rotation_cooldown_until_ts", 0.0)) <= now_ts:
                next_index = candidate_index
                break

        if next_index is None:
            next_index = (current_index + 1) % len(models)

        next_model = models[next_index]
        self.state["current_model_index"] = next_index
        self.state["status"] = "collecting_rotation"
        next_model["status"] = "collecting_rotation"
        next_model["phase"] = "rotation"
        next_model.setdefault("started_at", utc_now())
        next_model["rotation_resumed_at"] = utc_now()
        self.logger.info("ROTATE_IN model=%s trades=%s pnl=%.2f", next_model["id"], next_model["trades"], next_model["pnl"])
        self.log_event(
            "rotation_switch_in",
            model_id=next_model["id"],
            trades=next_model["trades"],
            pnl=next_model["pnl"],
            prior_reason=reason,
        )
        self.write_state()

    def update_rotation_after_settlement(self, model, profit):
        rotation = self.state.setdefault("rotation", self.rotation_state_template())
        rotation["global_trades"] = int(rotation.get("global_trades", 0)) + 1
        rotation["global_pnl"] = round(float(rotation.get("global_pnl", 0.0)) + float(profit), 4)
        rotation["global_peak_pnl"] = max(float(rotation.get("global_peak_pnl", 0.0)), rotation["global_pnl"])
        global_dd = round(rotation["global_pnl"] - rotation["global_peak_pnl"], 4)
        rotation["global_max_drawdown"] = min(float(rotation.get("global_max_drawdown", 0.0)), global_dd)
        self.write_state()

        if self.args.global_target_pnl > 0 and rotation["global_pnl"] >= self.args.global_target_pnl:
            model["status"] = "rotation_target_pnl_reached"
            model["stopped_at"] = utc_now()
            self.state["status"] = "rotation_target_pnl_reached"
            self.log_event(
                "rotation_target_pnl_reached",
                model_id=model["id"],
                global_trades=rotation["global_trades"],
                global_pnl=rotation["global_pnl"],
                target_pnl=self.args.global_target_pnl,
            )
            self.done.set()
            return True

        if self.args.global_target_trades > 0 and rotation["global_trades"] >= self.args.global_target_trades:
            model["status"] = "rotation_target_trades_reached"
            model["stopped_at"] = utc_now()
            self.state["status"] = "rotation_target_trades_reached"
            self.log_event(
                "rotation_target_trades_reached",
                model_id=model["id"],
                global_trades=rotation["global_trades"],
                global_pnl=rotation["global_pnl"],
                target_trades=self.args.global_target_trades,
            )
            self.done.set()
            return True

        if self.args.global_hard_drawdown_stop > 0 and abs(rotation["global_max_drawdown"]) >= abs(self.args.global_hard_drawdown_stop):
            model["status"] = "rotation_global_drawdown_stop"
            model["stopped_at"] = utc_now()
            self.state["status"] = "rotation_global_drawdown_stop"
            self.log_event(
                "rotation_global_drawdown_stop",
                model_id=model["id"],
                global_trades=rotation["global_trades"],
                global_pnl=rotation["global_pnl"],
                global_max_drawdown=rotation["global_max_drawdown"],
                stop=self.args.global_hard_drawdown_stop,
            )
            self.done.set()
            return True

        if model["trades"] < self.args.rotation_min_trades:
            return False

        giveback = round(float(model["pnl"]) - float(model["peak_pnl"]), 4)
        if self.args.rotation_peak_drop > 0 and giveback <= -abs(self.args.rotation_peak_drop):
            self.rotate_current_model(f"rotation_peak_giveback_{abs(self.args.rotation_peak_drop):.2f}")
            return True

        window = int(self.args.rotation_recent_window)
        recent = model.get("recent_profits", [])
        if window > 0 and len(recent) >= window:
            recent_pnl = round(sum(float(value) for value in recent[-window:]), 4)
            if self.args.rotation_recent_loss > 0 and recent_pnl <= -abs(self.args.rotation_recent_loss):
                self.rotate_current_model(f"rotation_recent_loss_{window}_{abs(self.args.rotation_recent_loss):.2f}")
                return True

        return False

    def promote_current_model(self):
        model = self.current_model()
        if not model:
            return
        model["phase"] = "target100"
        model["status"] = "collecting_target100"
        model["promoted_at"] = utc_now()
        self.state["champions"].append({"model_id": model["id"], "promoted_at": model["promoted_at"], "pnl_at_30": model["pnl"]})
        self.logger.info("PROMOTE model=%s pnl_at_30=%.2f", model["id"], model["pnl"])
        self.log_event("promote_to_100", model_id=model["id"], pnl=model["pnl"], trades=model["trades"])
        self.write_state()

    def pass_healthy_drawdown(self, model):
        limit = self.args.healthy_drawdown_30 if model["phase"] == "gate30" else self.args.healthy_drawdown_100
        return abs(model["max_drawdown"]) <= abs(limit)

    def stake_for_model(self, model, spec):
        if self.args.stake_override > 0:
            base = float(self.args.stake_override)
        elif model.get("phase") == "post100" and self.args.post_target_stake > 0:
            base = float(self.args.post_target_stake)
        else:
            base = float(spec.get("stake", 1.0))
        return round(base * float(spec.get("stake_multiplier", 1.0)), 2)

    def max_possible_pnl_at_trade_count(self, model, target_trades):
        spec = self.current_spec()
        stake = self.stake_for_model(model, spec) if spec else 1.0
        remaining = max(0, target_trades - model["trades"])
        max_win_profit = stake * float(self.args.max_win_return_ratio)
        return round(model["pnl"] + remaining * max_win_profit, 4)

    def check_gate30_early_failure(self, model):
        if model["phase"] != "gate30" or model["trades"] >= self.args.gate_trades:
            return False
        if not self.pass_healthy_drawdown(model):
            self.pivot_current_model("failed_gate30_drawdown_early")
            return True
        if self.max_possible_pnl_at_trade_count(model, self.args.gate_trades) <= 0:
            self.pivot_current_model("failed_gate30_pnl_recovery_impossible")
            return True
        return False

    def check_target100_early_failure(self, model):
        if model["phase"] != "target100" or model["trades"] >= self.args.target_trades:
            return False
        if not self.pass_healthy_drawdown(model):
            self.pivot_current_model("failed_100_drawdown_early")
            return True
        if self.max_possible_pnl_at_trade_count(model, self.args.target_trades) <= 0:
            self.pivot_current_model("failed_100_pnl_recovery_impossible")
            return True
        return False

    def update_after_settlement(self, model, profit, signal=None):
        model["trades"] += 1
        if profit > 0:
            model["wins"] += 1
        elif profit < 0:
            model["losses"] += 1
        model["pnl"] = round(model["pnl"] + profit, 4)
        model["peak_pnl"] = max(model["peak_pnl"], model["pnl"])
        dd = model["pnl"] - model["peak_pnl"]
        model["max_drawdown"] = min(model["max_drawdown"], round(dd, 4))
        recent = model.setdefault("recent_profits", [])
        recent.append(round(profit, 4))
        model["recent_profits"] = recent[-100:]
        self.update_agent_rule_live_stats_after_settlement(model, profit, signal)
        self.apply_block_guard_after_settlement(model)
        self.apply_loss_streak_pause_after_settlement(model)
        self.apply_target100_trailing_pause_after_settlement(model)
        self.write_state()

        if self.rotation_enabled():
            self.update_rotation_after_settlement(model, profit)
            return

        if model["pnl"] <= -abs(self.args.model_kill_loss):
            self.pivot_current_model("model_kill_loss")
            return
        if self.args.hard_drawdown_stop > 0 and abs(model["max_drawdown"]) >= abs(self.args.hard_drawdown_stop):
            self.pivot_current_model("hard_drawdown_stop")
            return

        if self.args.target_pnl > 0 and model["pnl"] >= self.args.target_pnl:
            model["status"] = "target_pnl_reached"
            model["stopped_at"] = utc_now()
            self.state["status"] = "target_pnl_reached"
            self.log_event("target_pnl_reached", model_id=model["id"], trades=model["trades"], pnl=model["pnl"], target_pnl=self.args.target_pnl)
            self.done.set()
            return

        if model["phase"] == "post100":
            start_pnl = float(model.get("post_target_start_pnl", model["pnl"]))
            if self.args.post_target_kill_loss > 0 and model["pnl"] - start_pnl <= -abs(self.args.post_target_kill_loss):
                self.pivot_current_model("post100_kill_loss")
                return
            if self.args.post_target_max_trades > 0 and model["trades"] >= self.args.post_target_max_trades:
                model["status"] = "post100_complete"
                model["stopped_at"] = utc_now()
                self.state["status"] = "post100_complete"
                self.log_event("post100_complete", model_id=model["id"], trades=model["trades"], pnl=model["pnl"])
                self.done.set()
                return

        if self.check_gate30_early_failure(model) or self.check_target100_early_failure(model):
            return

        if model["phase"] == "gate30" and model["trades"] >= self.args.gate_trades:
            if model["pnl"] > 0 and self.pass_healthy_drawdown(model):
                self.promote_current_model()
            else:
                reason = "failed_gate30_pnl_nonpositive" if model["pnl"] <= 0 else "failed_gate30_drawdown"
                self.pivot_current_model(reason)
        elif model["phase"] == "target100" and model["trades"] >= self.args.target_trades:
            if model["pnl"] > 0 and self.pass_healthy_drawdown(model):
                if self.args.post_target_stake > 0:
                    model["phase"] = "post100"
                    model["status"] = "collecting_post100"
                    model["post_target_started_at"] = utc_now()
                    model["post_target_start_pnl"] = model["pnl"]
                    model["post_target_stake"] = float(self.args.post_target_stake)
                    self.state["status"] = "collecting_post100"
                    self.log_event(
                        "promote_post100_stake",
                        model_id=model["id"],
                        trades=model["trades"],
                        pnl=model["pnl"],
                        stake=float(self.args.post_target_stake),
                    )
                else:
                    model["status"] = "passed_100"
                    model["stopped_at"] = utc_now()
                    self.state["status"] = "goal_candidate_found"
                    self.log_event("passed_100", model_id=model["id"], trades=model["trades"], pnl=model["pnl"])
                    self.done.set()
            else:
                reason = "failed_100_pnl_nonpositive" if model["pnl"] <= 0 else "failed_100_drawdown"
                self.pivot_current_model(reason)

    def apply_block_guard_after_settlement(self, model):
        spec = self.current_spec()
        guard = spec.get("block_guard") if spec else None
        if not guard:
            return
        recent = model.get("recent_profits", [])
        window = int(guard.get("window", 0))
        if window <= 0 or len(recent) < window:
            return
        block_pnl = round(sum(recent[-window:]), 4)
        pause_seconds = float(guard.get("pause_seconds", 0))
        if pause_seconds <= 0:
            return
        if "max_loss" in guard and block_pnl <= float(guard["max_loss"]):
            model["blocked_until_ts"] = time.time() + pause_seconds
            model["blocked_reason"] = f"recent_loss_block_{window}_pnl_{block_pnl}"
            self.log_event(
                "block_guard_pause",
                model_id=model["id"],
                reason=model["blocked_reason"],
                recent_window=window,
                recent_pnl=block_pnl,
                pause_seconds=pause_seconds,
            )
        elif (
            not self.args.disable_gain_block
            and not self.rotation_enabled()
            and "max_gain" in guard
            and block_pnl >= float(guard["max_gain"])
        ):
            model["blocked_until_ts"] = time.time() + pause_seconds
            model["blocked_reason"] = f"recent_gain_block_{window}_pnl_{block_pnl}"
            self.log_event(
                "block_guard_pause",
                model_id=model["id"],
                reason=model["blocked_reason"],
                recent_window=window,
                recent_pnl=block_pnl,
                pause_seconds=pause_seconds,
            )

    def apply_loss_streak_pause_after_settlement(self, model):
        spec = self.current_spec()
        guard = spec.get("loss_streak_pause") if spec else None
        if not guard:
            return
        phases = guard.get("phases")
        if phases and model.get("phase") not in set(phases):
            return
        recent = model.get("recent_profits", [])
        required_losses = int(guard.get("losses", 0))
        pause_seconds = float(guard.get("pause_seconds", 0))
        if required_losses <= 0 or pause_seconds <= 0 or len(recent) < required_losses:
            return
        tail = recent[-required_losses:]
        if not all(float(value) < 0 for value in tail):
            return
        model["blocked_until_ts"] = time.time() + pause_seconds
        model["blocked_reason"] = f"loss_streak_{required_losses}"
        self.log_event(
            "loss_streak_pause",
            model_id=model["id"],
            reason=model["blocked_reason"],
            losses=required_losses,
            pause_seconds=pause_seconds,
        )

    def apply_target100_trailing_pause_after_settlement(self, model):
        spec = self.current_spec()
        guard = spec.get("target100_trailing_pause") if spec else None
        if not guard:
            return
        phases = set(guard.get("phases", ["target100"]))
        if model.get("phase") not in phases:
            return
        min_trades = int(guard.get("min_trades", self.args.gate_trades))
        if model.get("trades", 0) < min_trades:
            return
        trigger = abs(float(guard.get("drawdown_from_peak", 0)))
        pause_seconds = float(guard.get("pause_seconds", 0))
        if trigger <= 0 or pause_seconds <= 0:
            return
        retrace = round(float(model["pnl"]) - float(model["peak_pnl"]), 4)
        if retrace > -trigger:
            return
        model["blocked_until_ts"] = time.time() + pause_seconds
        model["blocked_reason"] = f"target100_peak_retrace_{abs(retrace)}"
        self.log_event(
            "target100_trailing_pause",
            model_id=model["id"],
            reason=model["blocked_reason"],
            retrace=retrace,
            peak_pnl=model["peak_pnl"],
            pnl=model["pnl"],
            pause_seconds=pause_seconds,
        )

    def signal_from_rule(self, ticks, rule):
        if rule["kind"] in ("trend", "reversal"):
            needed = int(rule["streak"]) + 1
            if len(ticks) < needed:
                return None
            recent = ticks[-needed:]
            deltas = [recent[i]["quote"] - recent[i - 1]["quote"] for i in range(1, len(recent))]
            if all(delta > 0 for delta in deltas):
                direction = "UP"
            elif all(delta < 0 for delta in deltas):
                direction = "DOWN"
            else:
                return None
            move = recent[-1]["quote"] - recent[0]["quote"]
            if abs(move) < rule.get("min_move", 0.0):
                return None
            if rule["kind"] == "reversal":
                direction = "DOWN" if direction == "UP" else "UP"
            signal = {
                "direction": direction,
                "contract_type": "CALL" if direction == "UP" else "PUT",
                "move": round(move, 5),
                "from_quote": recent[0]["quote"],
                "to_quote": recent[-1]["quote"],
            }
            return self.finalize_rule_signal(rule, signal)

        if rule["kind"] == "mean_revert":
            window = int(rule["window"])
            if len(ticks) < window:
                return None
            recent = ticks[-window:]
            mean_quote = statistics.mean(item["quote"] for item in recent[:-1])
            last_quote = recent[-1]["quote"]
            diff = last_quote - mean_quote
            if abs(diff) < rule["min_move"]:
                return None
            direction = "DOWN" if diff > 0 else "UP"
            signal = {
                "direction": direction,
                "contract_type": "CALL" if direction == "UP" else "PUT",
                "move": round(diff, 5),
                "from_quote": round(mean_quote, 5),
                "to_quote": last_quote,
            }
            return self.finalize_rule_signal(rule, signal)
        return None

    def finalize_rule_signal(self, rule, signal):
        signal["rule_kind"] = rule.get("kind")
        signal["rule_family"] = rule.get("family", rule.get("kind"))
        return self.apply_rule_contract_filter(rule, signal)

    def apply_rule_contract_filter(self, rule, signal):
        allowed_contracts = rule.get("allowed_contract_types")
        if allowed_contracts and signal.get("contract_type") not in set(allowed_contracts):
            return None
        return signal

    def apply_signal_filters(self, model, spec, signal):
        if not signal:
            return None
        allowed_contracts = spec.get("allowed_contract_types")
        if allowed_contracts and signal.get("contract_type") not in set(allowed_contracts):
            return None
        blocked_until = float(model.get("blocked_until_ts", 0.0) or 0.0)
        if blocked_until > time.time():
            return None
        return signal

    def adaptive_state(self, model):
        return self.adaptive_agents.setdefault(
            model["id"],
            {
                "pending": [],
                "scores": {},
                "history": {},
                "consensus_memory": {},
                "last_tick_seen_at": 0.0,
                "last_logged_rule": None,
                "last_status_logged_at": 0.0,
            },
        )

    def adaptive_signal_for_model(self, model, spec):
        ticks = self.ticks_by_symbol[spec["symbol"]]
        agent = self.adaptive_state(model)
        if ticks:
            current_seen_at = ticks[-1]["seen_at"]
            if agent["last_tick_seen_at"] != current_seen_at:
                self.update_adaptive_paper(agent, spec, ticks)
                agent["last_tick_seen_at"] = current_seen_at

        emitted = []
        for rule in spec.get("rules", []):
            signal = self.signal_from_rule(ticks, rule)
            if signal:
                rule_id = rule["id"]
                history = agent["history"].get(rule_id, [])
                score = round(sum(history[-int(spec.get("score_window", 40)):]), 4)
                emitted.append((score, len(history), rule_id, signal))

        min_samples = int(spec.get("min_paper_samples", 0))
        min_score = float(spec.get("min_rule_score", -999999))
        eligible = [
            item
            for item in emitted
            if item[1] >= min_samples and item[0] >= min_score and not self.is_agent_rule_blocked(model, item[2])
        ]
        self.refresh_agent_consensus_memory(agent, spec, eligible)
        self.record_agent_status(model, spec, agent, emitted, eligible)
        if float(model.get("blocked_until_ts", 0.0) or 0.0) > time.time():
            return None
        if not emitted:
            return None

        if not eligible and spec.get("allow_exploration_before_min_samples", False):
            eligible = emitted
        if not eligible:
            return None

        current_rule_ids = {item[2] for item in eligible}
        consensus_pool = self.agent_consensus_pool(agent, spec, eligible)
        consensus_eligible = self.apply_agent_consensus_filter(model, spec, consensus_pool)
        eligible = [item for item in consensus_eligible if item[2] in current_rule_ids]
        if not eligible:
            return None

        score, samples, rule_id, signal = max(eligible, key=lambda item: (item[0], item[1], item[2]))
        signal["agent_rule_id"] = rule_id
        signal["agent_rule_score"] = score
        signal["agent_rule_samples"] = samples
        model["last_agent_rule"] = {"rule_id": rule_id, "score": score, "samples": samples, "ts": utc_now()}
        if agent.get("last_logged_rule") != rule_id:
            self.log_event("agent_rule_selected", model_id=model["id"], rule_id=rule_id, score=score, samples=samples)
            agent["last_logged_rule"] = rule_id
        return signal

    def record_agent_status(self, model, spec, agent, emitted, eligible):
        score_window = int(spec.get("score_window", 40))
        rules = []
        live_stats = model.get("rule_live_stats", {})
        for rule in spec.get("rules", []):
            rule_id = rule["id"]
            history = agent.get("history", {}).get(rule_id, [])
            rule_live = live_stats.get(rule_id, {})
            rules.append(
                {
                    "rule_id": rule_id,
                    "rule_kind": rule.get("kind"),
                    "rule_family": rule.get("family", rule.get("kind")),
                    "samples": len(history),
                    "score": round(sum(history[-score_window:]), 4),
                    "lifetime_score": round(sum(history), 4),
                    "currently_emitted": any(item[2] == rule_id for item in emitted),
                    "eligible": any(item[2] == rule_id for item in eligible),
                    "live_blocked": self.is_agent_rule_blocked(model, rule_id),
                    "live_stats": rule_live,
                }
            )

        best = max(rules, key=lambda item: (item["score"], item["samples"], item["rule_id"])) if rules else None
        status = {
            "ts": utc_now(),
            "score_window": score_window,
            "min_paper_samples": int(spec.get("min_paper_samples", 0)),
            "min_rule_score": float(spec.get("min_rule_score", -999999)),
            "global_blocked": float(model.get("blocked_until_ts", 0.0) or 0.0) > time.time(),
            "global_blocked_reason": model.get("blocked_reason"),
            "emitted_count": len(emitted),
            "eligible_count": len(eligible),
            "best_rule": best,
            "rules": rules,
            "consensus_memory": self.active_agent_consensus_memory(agent, spec),
        }
        model["last_agent_status"] = status

        log_seconds = float(spec.get("agent_status_log_seconds", 60.0))
        now = time.time()
        if now - float(agent.get("last_status_logged_at", 0.0) or 0.0) >= log_seconds:
            self.log_event(
                "agent_status",
                model_id=model["id"],
                emitted_count=status["emitted_count"],
                eligible_count=status["eligible_count"],
                min_paper_samples=status["min_paper_samples"],
                min_rule_score=status["min_rule_score"],
                best_rule=best,
                rules=rules,
                consensus_memory=status["consensus_memory"],
            )
            agent["last_status_logged_at"] = now

    def refresh_agent_consensus_memory(self, agent, spec, eligible):
        ttl = float(spec.get("consensus_memory_seconds", 0.0) or 0.0)
        if ttl <= 0:
            return
        now = time.time()
        memory = agent.setdefault("consensus_memory", {})
        for rule_id in list(memory):
            if float(memory[rule_id].get("expires_at", 0.0) or 0.0) <= now:
                del memory[rule_id]
        for score, samples, rule_id, signal in eligible:
            memory_signal = dict(signal)
            memory_signal["agent_vote_source"] = "memory"
            memory[rule_id] = {
                "score": float(score),
                "samples": int(samples),
                "rule_id": rule_id,
                "signal": memory_signal,
                "recorded_at": now,
                "expires_at": now + ttl,
            }

    def active_agent_consensus_memory(self, agent, spec):
        ttl = float(spec.get("consensus_memory_seconds", 0.0) or 0.0)
        if ttl <= 0:
            return []
        now = time.time()
        active = []
        for rule_id, row in sorted(agent.get("consensus_memory", {}).items()):
            expires_at = float(row.get("expires_at", 0.0) or 0.0)
            if expires_at <= now:
                continue
            signal = row.get("signal", {})
            active.append(
                {
                    "rule_id": rule_id,
                    "rule_family": signal.get("rule_family"),
                    "contract_type": signal.get("contract_type"),
                    "score": round(float(row.get("score", 0.0) or 0.0), 4),
                    "samples": int(row.get("samples", 0) or 0),
                    "age_seconds": round(now - float(row.get("recorded_at", now) or now), 1),
                    "ttl_remaining_seconds": round(expires_at - now, 1),
                }
            )
        return active

    def agent_consensus_pool(self, agent, spec, eligible):
        ttl = float(spec.get("consensus_memory_seconds", 0.0) or 0.0)
        if ttl <= 0:
            return eligible
        now = time.time()
        current_rule_ids = {item[2] for item in eligible}
        pool = []
        for score, samples, rule_id, signal in eligible:
            current_signal = dict(signal)
            current_signal["agent_vote_source"] = "current"
            pool.append((score, samples, rule_id, current_signal))
        for rule_id, row in sorted(agent.get("consensus_memory", {}).items()):
            if rule_id in current_rule_ids:
                continue
            if float(row.get("expires_at", 0.0) or 0.0) <= now:
                continue
            memory_signal = dict(row.get("signal", {}))
            memory_signal["agent_vote_source"] = "memory"
            memory_signal["agent_vote_age_seconds"] = round(now - float(row.get("recorded_at", now) or now), 3)
            pool.append((float(row.get("score", 0.0) or 0.0), int(row.get("samples", 0) or 0), rule_id, memory_signal))
        return pool

    def apply_agent_consensus_filter(self, model, spec, eligible):
        min_rules = int(spec.get("min_consensus_rules", 0) or 0)
        min_score = float(spec.get("min_consensus_score", 0.0) or 0.0)
        min_families = int(spec.get("min_consensus_families", 0) or 0)
        if min_rules <= 1 and min_score <= 0 and min_families <= 1:
            return eligible

        key_name = spec.get("consensus_key", "contract_type")
        family_key = spec.get("consensus_family_key", "rule_family")
        grouped = {}
        for item in eligible:
            score, samples, rule_id, signal = item
            key = signal.get(key_name) or signal.get("contract_type")
            grouped.setdefault(key, []).append(item)

        accepted_groups = []
        for key, items in grouped.items():
            group_score = round(sum(float(item[0]) for item in items), 4)
            families = sorted(
                {
                    str(item[3].get(family_key) or item[3].get("rule_kind") or "unknown")
                    for item in items
                }
            )
            if min_rules > 1 and len(items) < min_rules:
                continue
            if min_score > 0 and group_score < min_score:
                continue
            if min_families > 1 and len(families) < min_families:
                continue
            accepted_groups.append((group_score, len(items), len(families), key, families, items))

        if not accepted_groups:
            return []

        group_score, _, _, group_key, families, items = max(accepted_groups, key=lambda item: (item[0], item[1], item[2], item[3]))
        for score, samples, rule_id, signal in items:
            signal["agent_consensus_key"] = group_key
            signal["agent_consensus_rules"] = len(items)
            signal["agent_consensus_score"] = group_score
            signal["agent_consensus_families"] = families
        model["last_agent_consensus"] = {
            "key": group_key,
            "rules": len(items),
            "score": group_score,
            "families": families,
            "ts": utc_now(),
        }
        return items

    def is_agent_rule_blocked(self, model, rule_id):
        stats = model.get("rule_live_stats", {}).get(rule_id, {})
        return float(stats.get("blocked_until_ts", 0.0) or 0.0) > time.time()

    def update_agent_rule_live_stats_after_settlement(self, model, profit, signal):
        rule_id = (signal or {}).get("agent_rule_id")
        if not rule_id:
            return
        stats = model.setdefault("rule_live_stats", {}).setdefault(
            rule_id,
            {
                "trades": 0,
                "wins": 0,
                "losses": 0,
                "pnl": 0.0,
                "loss_streak": 0,
                "recent_profits": [],
                "blocked_until_ts": 0.0,
                "blocked_reason": None,
            },
        )
        stats["trades"] += 1
        stats["pnl"] = round(float(stats.get("pnl", 0.0)) + profit, 4)
        stats.setdefault("recent_profits", []).append(round(profit, 4))
        stats["recent_profits"] = stats["recent_profits"][-20:]
        if profit > 0:
            stats["wins"] += 1
            stats["loss_streak"] = 0
        elif profit < 0:
            stats["losses"] += 1
            stats["loss_streak"] = int(stats.get("loss_streak", 0)) + 1

        spec = self.current_spec()
        guard = spec.get("agent_rule_live_guard") if spec else None
        if not guard:
            return
        pause_seconds = float(guard.get("pause_seconds", 0))
        if pause_seconds <= 0:
            return

        reason = None
        required_losses = int(guard.get("losses", 0))
        if required_losses > 0 and int(stats.get("loss_streak", 0)) >= required_losses:
            reason = f"rule_loss_streak_{required_losses}"
        window = int(guard.get("window", 0))
        if not reason and window > 0 and len(stats.get("recent_profits", [])) >= window:
            block_pnl = round(sum(stats["recent_profits"][-window:]), 4)
            if block_pnl <= float(guard.get("max_loss", -999999)):
                reason = f"rule_recent_loss_{window}_pnl_{block_pnl}"
        if not reason:
            return

        stats["blocked_until_ts"] = time.time() + pause_seconds
        stats["blocked_reason"] = reason
        self.log_event(
            "agent_rule_quarantine",
            model_id=model["id"],
            rule_id=rule_id,
            reason=reason,
            pause_seconds=pause_seconds,
            rule_trades=stats["trades"],
            rule_pnl=stats["pnl"],
        )

    def update_adaptive_paper(self, agent, spec, ticks):
        if len(ticks) < 2:
            return
        previous_quote = ticks[-2]["quote"]
        current_quote = ticks[-1]["quote"]
        pending = agent.get("pending", [])
        for item in pending:
            direction = item["direction"]
            if direction == "UP":
                outcome = 0.92 if current_quote > previous_quote else -1.0
            else:
                outcome = 0.92 if current_quote < previous_quote else -1.0
            rule_id = item["rule_id"]
            history = agent.setdefault("history", {}).setdefault(rule_id, [])
            history.append(outcome)
            agent["history"][rule_id] = history[-200:]
            agent.setdefault("scores", {})[rule_id] = round(sum(agent["history"][rule_id]), 4)

        new_pending = []
        for rule in spec.get("rules", []):
            signal = self.signal_from_rule(ticks, rule)
            if signal:
                new_pending.append({"rule_id": rule["id"], "direction": signal["direction"]})
        agent["pending"] = new_pending

    def signal_for_model(self, model, spec):
        ticks = self.ticks_by_symbol[spec["symbol"]]
        if spec["kind"] == "adaptive_agent":
            return self.apply_signal_filters(model, spec, self.adaptive_signal_for_model(model, spec))

        if spec["kind"] in ("trend", "reversal"):
            return self.apply_signal_filters(model, spec, self.signal_from_rule(ticks, spec))

        if spec["kind"] == "mean_revert":
            return self.apply_signal_filters(model, spec, self.signal_from_rule(ticks, spec))
        return None

    async def on_tick(self, message):
        tick = message.get("tick", {})
        symbol = tick.get("symbol")
        if not symbol:
            symbol = self.current_model()["symbol"] if self.current_model() else "unknown"
        quote = float(tick.get("quote"))
        ticks = self.ticks_by_symbol.setdefault(symbol, [])
        ticks.append({"quote": quote, "epoch": tick.get("epoch"), "seen_at": time.time()})
        self.ticks_by_symbol[symbol] = ticks[-50:]

        model = self.current_model()
        spec = self.current_spec()
        if not model or not spec or symbol != spec["symbol"]:
            return
        self.logger.info("TICK model=%s symbol=%s quote=%.5f trades=%s pnl=%.2f", model["id"], symbol, quote, model["trades"], model["pnl"])
        if spec["kind"] == "adaptive_agent":
            self.adaptive_signal_for_model(model, spec)
        if self.in_trade:
            return
        if time.time() - self.last_trade_at < spec["cooldown_seconds"]:
            return
        signal = self.signal_for_model(model, spec)
        if not signal:
            return
        self.in_trade = True
        asyncio.create_task(self.execute_trade(model["id"], spec, signal))

    async def execute_trade(self, model_id, spec, signal):
        start = time.time()
        model = self.current_model()
        if not model or model["id"] != model_id:
            self.in_trade = False
            return
        trade_no = model["trades"] + 1
        stake = self.stake_for_model(model, spec)
        self.last_trade_at = time.time()
        self.logger.info("SIGNAL model=%s trade=%s contract=%s stake=%.2f move=%.5f", model_id, trade_no, signal["contract_type"], stake, signal["move"])
        self.log_event("signal", model_id=model_id, trade_no=trade_no, phase=model["phase"], stake=stake, **signal)
        try:
            response = await self.client.buy_direct(
                contract_type=signal["contract_type"],
                stake=stake,
                symbol=spec["symbol"],
                duration=spec["duration_ticks"],
                duration_unit="t",
            )
            latency_ms = round((time.time() - start) * 1000, 3)
            if "error" in response:
                model["rejects"] += 1
                self.log_event("reject", model_id=model_id, trade_no=trade_no, latency_ms=latency_ms, error=response["error"])
                self.logger.warning("REJECT model=%s trade=%s error=%s", model_id, trade_no, response["error"])
                return
            contract_id = response["buy"]["contract_id"]
            model["latencies_ms"].append(latency_ms)
            self.log_event("buy", model_id=model_id, trade_no=trade_no, contract_id=contract_id, latency_ms=latency_ms, buy_price=float(response["buy"]["buy_price"]), stake=stake, **signal)
            self.logger.info("BUY model=%s trade=%s contract_id=%s latency_ms=%.1f", model_id, trade_no, contract_id, latency_ms)
            await self.wait_settlement(model_id, trade_no, contract_id, signal)
        except Exception as exc:
            model["errors"] += 1
            self.logger.exception("ERROR model=%s trade=%s %s", model_id, trade_no, exc)
            self.log_event("error", model_id=model_id, trade_no=trade_no, error=str(exc))
        finally:
            self.in_trade = False
            self.write_state()

    async def wait_settlement(self, model_id, trade_no, contract_id, signal):
        deadline = time.time() + self.args.settlement_timeout_seconds
        while time.time() < deadline:
            response = await self.client.send_request({"proposal_open_contract": 1, "contract_id": contract_id})
            contract = response.get("proposal_open_contract", {})
            if contract.get("is_sold"):
                profit = float(contract.get("profit", 0.0))
                model = next(item for item in self.state["models"] if item["id"] == model_id)
                self.update_after_settlement(model, profit, signal)
                self.log_event("settled", model_id=model_id, trade_no=trade_no, contract_id=contract_id, profit=profit, pnl=model["pnl"], trades=model["trades"], **signal)
                self.logger.info("SETTLED model=%s trade=%s profit=%.2f pnl=%.2f trades=%s", model_id, trade_no, profit, model["pnl"], model["trades"])
                return
            await asyncio.sleep(self.args.poll_seconds)
        model = next(item for item in self.state["models"] if item["id"] == model_id)
        model["errors"] += 1
        self.log_event("settlement_timeout", model_id=model_id, trade_no=trade_no, contract_id=contract_id)

    async def connect(self):
        load_dotenv(".env", override=True)
        app_id = os.getenv(self.args.app_id_env)
        api_token = os.getenv(self.args.api_token_env)
        if not app_id:
            raise RuntimeError(f"missing app id env var: {self.args.app_id_env}")
        if not api_token:
            raise RuntimeError(f"missing api token env var: {self.args.api_token_env}")
        self.client = DerivClient(app_id=app_id, api_token=api_token, use_demo=True)
        for attempt in range(1, self.args.auth_retries + 1):
            try:
                await self.client.connect()
                account_id = str(self.client.account_id or "")
                if not account_id.startswith("DOT"):
                    raise RuntimeError(f"non-demo account blocked: {account_id[:3]}")
                self.log_event("demo_authenticated", account_id_prefix=account_id[:3], api_token_env=self.args.api_token_env)
                return
            except Exception as exc:
                self.log_event("auth_retry", attempt=attempt, error=str(exc))
                if attempt >= self.args.auth_retries:
                    raise
                await asyncio.sleep(min(2 * attempt, 20))

    async def run(self):
        await self.connect()
        if self.args.continue_model_id:
            model = self.current_model()
            self.log_event(
                "continue_model",
                model_id=self.args.continue_model_id,
                from_trades=model.get("trades", 0) if model else 0,
                from_pnl=model.get("pnl", 0.0) if model else 0.0,
                target_trades=self.args.target_trades,
            )
        model = self.start_current_model()
        if model:
            self.check_gate30_early_failure(model) or self.check_target100_early_failure(model)
        symbols = sorted({spec["symbol"] for spec in self.model_specs})
        for symbol in symbols:
            await self.client.subscribe_ticks(symbol, self.on_tick)
            await asyncio.sleep(0.25)
        try:
            await asyncio.wait_for(self.done.wait(), timeout=self.args.max_runtime_seconds)
        except asyncio.TimeoutError:
            self.state["status"] = "stopped_runtime_timeout"
            self.log_event("runtime_timeout", seconds=self.args.max_runtime_seconds)
        finally:
            self.write_state()
            await self.client.disconnect()


def parse_args():
    parser = argparse.ArgumentParser(description="Deriv demo model tournament with 30->100 trade gates.")
    parser.add_argument("--job-id", default="JOB-20260702-META100")
    parser.add_argument("--state-json", default="strategy_tournament_state.json")
    parser.add_argument("--events-jsonl", default="strategy_tournament_events.jsonl")
    parser.add_argument("--log-path", default="strategy_tournament.log")
    parser.add_argument("--reset", action="store_true")
    parser.add_argument("--seed-failed-ledger", default="")
    parser.add_argument("--gate-trades", type=int, default=30)
    parser.add_argument("--target-trades", type=int, default=100)
    parser.add_argument("--target-pnl", type=float, default=0.0)
    parser.add_argument("--healthy-drawdown-30", type=float, default=12.0)
    parser.add_argument("--healthy-drawdown-100", type=float, default=20.0)
    parser.add_argument("--hard-drawdown-stop", type=float, default=0.0)
    parser.add_argument("--model-kill-loss", type=float, default=14.0)
    parser.add_argument("--max-win-return-ratio", type=float, default=0.92)
    parser.add_argument("--max-runtime-seconds", type=float, default=21600)
    parser.add_argument("--poll-seconds", type=float, default=0.25)
    parser.add_argument("--settlement-timeout-seconds", type=float, default=25)
    parser.add_argument("--auth-retries", type=int, default=8)
    parser.add_argument("--continue-model-id", default="")
    parser.add_argument("--start-model-id", default="")
    parser.add_argument("--allow-backlog-continuation", action="store_true")
    parser.add_argument("--model-set", choices=["default", "discovery", "all"], default="default")
    parser.add_argument("--app-id-env", default="DERIV_APP_ID")
    parser.add_argument("--api-token-env", default="DERIV_API_TOKEN")
    parser.add_argument("--post-target-stake", type=float, default=0.0)
    parser.add_argument("--post-target-max-trades", type=int, default=0)
    parser.add_argument("--post-target-kill-loss", type=float, default=50.0)
    parser.add_argument("--stake-override", type=float, default=0.0)
    parser.add_argument("--rotation-model-ids", default="")
    parser.add_argument("--rotation-peak-drop", type=float, default=0.0)
    parser.add_argument("--rotation-recent-window", type=int, default=0)
    parser.add_argument("--rotation-recent-loss", type=float, default=0.0)
    parser.add_argument("--rotation-min-trades", type=int, default=0)
    parser.add_argument("--rotation-model-cooldown-seconds", type=float, default=0.0)
    parser.add_argument("--global-target-trades", type=int, default=0)
    parser.add_argument("--global-target-pnl", type=float, default=0.0)
    parser.add_argument("--global-hard-drawdown-stop", type=float, default=0.0)
    parser.add_argument("--stop-on-pivot", action="store_true")
    parser.add_argument("--disable-gain-block", action="store_true")
    return parser.parse_args()


def main():
    args = parse_args()
    logger = configure_logging(args.log_path)
    runner = StrategyTournament(args, logger)
    asyncio.run(runner.run())


if __name__ == "__main__":
    main()
