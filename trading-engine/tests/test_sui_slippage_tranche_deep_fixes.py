"""Unit and integration tests for Cetus slippage orientation/factor,
shallow depth vs vault protection logging, multi-tranche simulation fallback,
and DeepBook V3 DEEP token fee payment + live fee detection.
"""

from __future__ import annotations

import logging
import struct
import sys
from pathlib import Path
from typing import Any, Dict, List
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from venues.sui_bot_runner import SuiBotConfig, SuiBotRunner  # noqa: E402
from venues.sui_deepbook_venue import (  # noqa: E402
    SuiDeepBookPTBBuilder,
    SuiDeepBookVenue,
    SuiGraphQLClient,
    b58decode,
)


def _read_uleb128(buf: bytes, offset: int) -> tuple[int, int]:
    val = 0
    shift = 0
    while True:
        b = buf[offset]
        offset += 1
        val |= (b & 0x7F) << shift
        if (b & 0x80) == 0:
            return val, offset
        shift += 7


def _inspect_ptb_bcs(tx_bytes: bytes) -> Dict[str, Any]:
    """Minimal structural parser for BCS TransactionData::V1 commands/inputs."""
    assert tx_bytes[:2] == b"\x00\x00"
    off = 2
    n_inputs, off = _read_uleb128(tx_bytes, off)
    call_arg_tags: List[tuple[int, int | None]] = []
    for _ in range(n_inputs):
        tag = tx_bytes[off]
        off += 1
        if tag == 0:
            ln, off = _read_uleb128(tx_bytes, off)
            off += ln
            call_arg_tags.append((0, None))
        elif tag == 1:
            obj_kind = tx_bytes[off]
            off += 1
            call_arg_tags.append((1, obj_kind))
            if obj_kind == 0:  # ImmOrOwnedObject(ObjectRef)
                off += 32 + 8
                d_ln, off = _read_uleb128(tx_bytes, off)
                off += d_ln
            elif obj_kind == 1:  # SharedObject
                off += 32 + 8 + 1
            else:
                raise AssertionError(f"Unexpected ObjectArg kind: {obj_kind}")
        else:
            raise AssertionError(f"Unexpected CallArg tag: {tag}")

    n_cmds, off = _read_uleb128(tx_bytes, off)
    cmd_tags: List[int] = []
    move_calls: List[tuple[str, str]] = []
    for _ in range(n_cmds):
        ctag = tx_bytes[off]
        off += 1
        cmd_tags.append(ctag)
        if ctag == 0:  # MoveCall
            off += 32  # pkg
            mod_len, off = _read_uleb128(tx_bytes, off)
            mod_name = tx_bytes[off : off + mod_len].decode("utf-8")
            off += mod_len
            fn_len, off = _read_uleb128(tx_bytes, off)
            fn_name = tx_bytes[off : off + fn_len].decode("utf-8")
            off += fn_len
            move_calls.append((mod_name, fn_name))
            # Skip rest of MoveCall by not breaking; exact skip requires TypeTag parser.
            break
    return {
        "n_inputs": n_inputs,
        "call_arg_tags": call_arg_tags,
        "n_cmds": n_cmds,
        "first_cmd_tag": cmd_tags[0] if cmd_tags else None,
        "first_move_call": move_calls[0] if move_calls else None,
    }


def _dummy_gas_coin() -> Dict[str, Any]:
    return {
        "address": "0x" + "11" * 32,
        "version": 123456,
        "digest": "2wStav1wbDi9DrcVXmoU2ASLdmDGnLR76c3PzNAfyjsn",
    }


def _dummy_deep_coin(balance: int = 500_000_000) -> Dict[str, Any]:
    return {
        "address": "0x" + "22" * 32,
        "version": 987654,
        "digest": "5pZ2wV6fY5v8z9hK3pQvN1M4cX8jL2rT6bW9yF3dG1hJ",
        "balance": balance,
    }


def test_cetus_virtual_quote_reserve_orientation_and_average_slippage() -> None:
    """Verifies L / sqrt_p for Quote==CoinA (SUI/USDC) vs L * sqrt_p (DEEP/USDC) and 1.0*Q slippage."""
    # Mainnet SUI/USDC snapshot: L=7.867964e13, sqrt_p=34.414435, Q=$1,000 (1_000_000_000)
    # True virtual USDC reserve = L / sqrt_p ~= 2.2862e12 -> 1000e6 / 2.2862e12 * 10000 ~= 4.374 bps
    slip_sui = SuiBotRunner._compute_amm_slippage_bps(
        pair_name="SUI/USDC",
        borrow_amount=1_000_000_000,
        cetus_liq=78_679_640_450_553,
        cetus_sqrt_p=34.414435,
    )
    assert pytest.approx(slip_sui, rel=1e-3) == (1_000_000_000 / (78_679_640_450_553 / 34.414435)) * 10000.0
    assert 4.3 < slip_sui < 4.45

    # DEEP/USDC has Quote==CoinB -> denom = L * sqrt_p
    slip_deep = SuiBotRunner._compute_amm_slippage_bps(
        pair_name="DEEP/USDC",
        borrow_amount=100_000_000,
        cetus_liq=2.4023e11,
        cetus_sqrt_p=0.0139 ** 0.5,
    )
    expected_deep = (100_000_000 / (2.4023e11 * (0.0139 ** 0.5))) * 10000.0
    assert pytest.approx(slip_deep, rel=1e-6) == expected_deep


@pytest.mark.asyncio
async def test_optimal_q_star_not_self_rejected_by_factor_of_two_slippage() -> None:
    """With 1.0 * Q / denom average slippage, an optimal Q* trade passes hurdle + expected profit."""
    runner = SuiBotRunner(config=SuiBotConfig(port=18110, dry_run_mode=False))
    runner.update_gas_balance(5.0)
    mock_spreads = {
        "SUI/USDC": {
            "cetus_price": 0.90,
            "deepbook_price": 0.9018,
            "deepbook_ask": 0.9020,
            "spread_bps": 20.0,
            "forward_spread_bps": 20.0,
            "reverse_spread_bps": 0.0,
            "cetus_liquidity": 7.8679e13,
            "cetus_sqrt_price": 33.33,
            "bid_depth_quote": 50_000.0,
            "ask_depth_quote": 50_000.0,
        }
    }
    # Spread 20 bps > fee 16 bps => net margin = 4 bps.
    # Clamped SUI/USDC min tranche $1,000 -> slippage = 1e9 / (7.8679e13 / 33.33) * 1e4 = 4.24 bps > 4 bps (skips)
    # Bump spread to 25 bps (> 16 + 4.24 = 20.24 bps) -> executes with net profit after slippage & gas!
    mock_spreads["SUI/USDC"]["spread_bps"] = 25.0
    mock_spreads["SUI/USDC"]["forward_spread_bps"] = 25.0

    mock_fill = MagicMock(status="FILLED", order_id="PTB-QSTAR-OK", size=1_000_000_000)
    with patch.object(runner, "poll_market_spreads", return_value=mock_spreads), \
         patch.object(runner.validator.venue, "submit_order", new_callable=AsyncMock, return_value=mock_fill) as mock_submit:
        results = await runner.scan_once()
        sui_res = next(r for r in results if r["pair"] == "SUI/USDC")
        assert sui_res["amm_slippage_bps"] < 5.0
        assert sui_res["effective_hurdle_bps"] < 21.0
        assert sui_res["is_profitable"] is True
        assert mock_submit.call_count == 1


@pytest.mark.asyncio
async def test_shallow_depth_vs_vault_protection_logs_and_statuses(caplog: pytest.LogCaptureFixture) -> None:
    """Shallow orderbook depth must emit INFO SKIPPED_SHALLOW_DEPTH, not VAULT PROTECTION TRIGGERED."""
    runner = SuiBotRunner(config=SuiBotConfig(port=18111, dry_run_mode=True))
    runner.update_gas_balance(5.0)

    shallow_spreads = {
        "DEEP/SUI": {
            "cetus_price": 0.015,
            "deepbook_price": 0.01515,
            "deepbook_ask": 0.01516,
            "spread_bps": 100.0,
            "forward_spread_bps": 100.0,
            "reverse_spread_bps": 0.0,
            "bid_depth_quote": 5.0,  # 5 SUI * $1 = $5 < $25 min floor -> borrow_amount == 0
            "ask_depth_quote": 5000.0,
        }
    }
    healthy_vault = {"base_balance": 10**14, "quote_balance": 10**14, "deep_balance": 10**12}

    with caplog.at_level(logging.INFO), \
         patch.object(runner, "poll_market_spreads", return_value=shallow_spreads), \
         patch.object(runner.validator.graphql_client, "get_deepbook_vault_balances", new_callable=AsyncMock, return_value=healthy_vault):
        results = await runner.scan_once()
        deep_sui = next(r for r in results if r["pair"] == "DEEP/SUI")
        assert deep_sui["status"] == "SKIPPED_SHALLOW_DEPTH"
        assert deep_sui["execution_status"] == "SKIPPED_SHALLOW_DEPTH"
        assert "Shallow orderbook depth for DEEP/SUI" in caplog.text
        assert "VAULT PROTECTION TRIGGERED for DEEP/SUI" not in caplog.text

    caplog.clear()
    depleted_vault = {"base_balance": 10**14, "quote_balance": 1_000_000_000, "deep_balance": 0}  # 1 SUI (~$2) < $25 floor
    deep_spreads = {
        "DEEP/SUI": {
            **shallow_spreads["DEEP/SUI"],
            "bid_depth_quote": 5000.0,
        }
    }
    with caplog.at_level(logging.WARNING), \
         patch.object(runner, "poll_market_spreads", return_value=deep_spreads), \
         patch.object(runner.validator.graphql_client, "get_deepbook_vault_balances", new_callable=AsyncMock, return_value=depleted_vault):
        results = await runner.scan_once()
        deep_sui = next(r for r in results if r["pair"] == "DEEP/SUI")
        assert deep_sui["status"] == "SKIPPED_VAULT_PROTECTED"
        assert deep_sui["execution_status"] == "SKIPPED_VAULT_PROTECTED"
        assert "VAULT PROTECTION TRIGGERED for DEEP/SUI" in caplog.text


@pytest.mark.asyncio
async def test_submit_order_multi_tranche_simulation_fallback() -> None:
    """submit_order retries simulation at 0.5x when enable_tranche_fallback=True and broadcasts on success."""
    venue = SuiDeepBookVenue(env="mainnet")
    venue.private_key = "suiprivkey1qztestdummyseedvaluethatmatchesbech32prefixonly123456"
    mock_gql = AsyncMock()
    mock_gql.get_gas_coin_and_price.return_value = (_dummy_gas_coin(), 550)
    mock_gql.simulate_transaction_bcs.side_effect = [
        {"data": {"simulateTransaction": {"effects": {"status": "ABORTED", "executionError": {"message": "MoveAbort(pool, 12)"}}}}},
        {"data": {"simulateTransaction": {"effects": {"status": "SUCCESS"}}}},
    ]
    mock_gql.execute_transaction_bcs.return_value = {
        "data": {"executeTransaction": {"effects": {"status": "SUCCESS", "digest": "DIGEST-FALLBACK-05X"}}}
    }
    venue.graphql_client = mock_gql

    base_params = {
        "symbol": "SUI/USDC",
        "side": "BUY",
        "size": 1_000_000_000,
        "price": 1.005,
        "amm_price": 1.000,
        "is_arb_ptb": True,
        "route_direction": "FORWARD",
        "live_onchain": True,
        "enable_tranche_fallback": True,
        "min_borrow_units": 25_000_000,
    }
    with patch.object(venue.ptb_builder, "sign_transaction_bcs", return_value="SIG_B64") as mock_sign:
        res = await venue.submit_order(base_params)
        assert res.status == "FILLED"
        assert res.order_id == "DIGEST-FALLBACK-05X"
        assert res.size == 500_000_000
        assert mock_gql.simulate_transaction_bcs.await_count == 2
        mock_sign.assert_called_once()
        mock_gql.execute_transaction_bcs.assert_awaited_once()

    # All tranches abort -> REJECTED without broadcasting
    mock_gql.reset_mock()
    mock_gql.get_gas_coin_and_price.return_value = (_dummy_gas_coin(), 550)
    mock_gql.simulate_transaction_bcs.side_effect = None
    mock_gql.simulate_transaction_bcs.return_value = {
        "data": {"simulateTransaction": {"effects": {"status": "ABORTED", "executionError": {"message": "Insufficient"}}}}
    }
    res_fail = await venue.submit_order(base_params)
    assert res_fail.status == "REJECTED"
    assert res_fail.order_id.startswith("PTB-SIM-REVERT-")
    assert mock_gql.simulate_transaction_bcs.await_count == 3  # 1.0, 0.5, 0.25
    mock_gql.execute_transaction_bcs.assert_not_awaited()

    # Without enable_tranche_fallback flag -> only 1 simulation call
    mock_gql.reset_mock()
    mock_gql.get_gas_coin_and_price.return_value = (_dummy_gas_coin(), 550)
    no_fallback = {k: v for k, v in base_params.items() if k != "enable_tranche_fallback"}
    res_single = await venue.submit_order(no_fallback)
    assert res_single.status == "REJECTED"
    mock_gql.simulate_transaction_bcs.assert_awaited_once()


def test_bcs_ptb_deep_coin_forward_and_reverse() -> None:
    """Verifies SplitCoins + coin::join<DEEP> BCS structure when deep_coin is supplied, and exact default bytes otherwise."""
    builder = SuiDeepBookPTBBuilder()
    sender = "0x" + "ab" * 32
    gas = _dummy_gas_coin()
    deep_coin = _dummy_deep_coin(balance=100_000_000)

    for direction in ("FORWARD", "REVERSE"):
        raw_default = builder.build_atomic_arb_ptb_bcs(
            pair_name="SUI/USDC",
            borrow_amount=1_000_000_000,
            sender_address=sender,
            gas_coin=gas,
            route_direction=direction,
        )
        raw_explicit_zero = builder.build_atomic_arb_ptb_bcs(
            pair_name="SUI/USDC",
            borrow_amount=1_000_000_000,
            sender_address=sender,
            gas_coin=gas,
            route_direction=direction,
            deep_coin=deep_coin,
            deep_fee_amount=0,
        )
        assert raw_default == raw_explicit_zero

        raw_with_deep = builder.build_atomic_arb_ptb_bcs(
            pair_name="SUI/USDC",
            borrow_amount=1_000_000_000,
            sender_address=sender,
            gas_coin=gas,
            route_direction=direction,
            deep_coin=deep_coin,
            deep_fee_amount=15_800_000,
        )
        info_def = _inspect_ptb_bcs(raw_default)
        info_deep = _inspect_ptb_bcs(raw_with_deep)
        assert info_deep["n_inputs"] == info_def["n_inputs"] + 2  # + owned Coin<DEEP> + pure u64 amount
        assert (1, 0) in info_deep["call_arg_tags"]  # ObjectArg::ImmOrOwnedObject
        assert (1, 0) not in info_def["call_arg_tags"]
        assert b58decode(deep_coin["digest"]) in raw_with_deep

        # In FORWARD, no destroy_zero<DEEP> should be emitted after swap; join must be emitted instead
        if direction == "FORWARD":
            assert b"destroy_zero" in raw_default
            assert b"coin\x0cjoin" not in raw_default
            assert raw_with_deep.count(b"destroy_zero") == 1  # only balance::destroy_zero for Cetus leg
            assert b"\x04coin\x04join" in raw_with_deep
        else:
            assert info_deep["n_cmds"] == info_def["n_cmds"] + 1  # + coin::join<DEEP>
            assert b"\x04coin\x04join" in raw_with_deep


def test_estimate_required_deep_raw_matches_mainnet() -> None:
    """$1,000 SUI/USDC swap at 2.0 bps & deep_per_asset=71.72B requires ~14.34M raw DEEP (+10% buffer)."""
    est = SuiGraphQLClient.estimate_required_deep_raw(
        borrow_amount_quote_raw=1_000_000_000,
        taker_fee_raw=200_000,
        deep_per_asset=71_724_497_888,
        asset_is_base=False,
        safety_multiplier=1.10,
    )
    assert 15_700_000 <= est <= 15_900_000


@pytest.mark.asyncio
async def test_runner_live_fee_detection_and_deep_discount() -> None:
    """Verifies live 2.5 bps (0 DEEP) vs 2.0 bps (funded Coin<DEEP>) hurdles and cache invalidation."""
    runner = SuiBotRunner(config=SuiBotConfig(port=18112, dry_run_mode=False, sui_private_key="suiprivkey1test"))
    runner.update_gas_balance(5.0)
    live_fees = {
        "SUI/USDC": {
            "taker_fee_raw": 200_000,
            "maker_fee_raw": 0,
            "whitelisted": False,
            "taker_fee_bps_deep": 2.0,
            "taker_fee_bps_no_deep": 2.5,
            "asset_is_base": False,
            "deep_per_asset": 71_724_497_888,
        },
        "DEEP/SUI": {
            "taker_fee_raw": 0,
            "maker_fee_raw": 0,
            "whitelisted": True,
            "taker_fee_bps_deep": 0.0,
            "taker_fee_bps_no_deep": 0.0,
            "asset_is_base": False,
            "deep_per_asset": 0,
        },
        "DEEP/USDC": {
            "taker_fee_raw": 0,
            "maker_fee_raw": 0,
            "whitelisted": True,
            "taker_fee_bps_deep": 0.0,
            "taker_fee_bps_no_deep": 0.0,
            "asset_is_base": False,
            "deep_per_asset": 0,
        },
        "CETUS/SUI": {
            "taker_fee_raw": 1_000_000,
            "maker_fee_raw": 500_000,
            "whitelisted": False,
            "taker_fee_bps_deep": 10.0,
            "taker_fee_bps_no_deep": 12.5,
            "asset_is_base": False,
            "deep_per_asset": 51_773_233,
        },
    }
    live_spreads = {
        "SUI/USDC": {
            "cetus_price": 0.90,
            "deepbook_price": 0.9015,
            "deepbook_ask": 0.9016,
            "spread_bps": 15.0,
            "forward_spread_bps": 15.0,
            "reverse_spread_bps": 0.0,
            "cetus_liquidity": 7.8679e13,
            "cetus_sqrt_price": 33.33,
            "bid_depth_quote": 50_000.0,
            "ask_depth_quote": 50_000.0,
            "source": "live_graphql",
        }
    }
    mock_fill = MagicMock(status="FILLED", order_id="PTB-LIVE-DEEP-1", size=1_000_000_000)

    # Case 1: 0 DEEP in wallet -> SUI/USDC uses 8.5 bps hurdle (5 + 2.5 + 1) & deep_coin=None
    with patch.object(runner, "poll_market_spreads", return_value=live_spreads), \
         patch.object(runner.validator.graphql_client, "get_live_deepbook_fee_params", new_callable=AsyncMock, return_value=live_fees), \
         patch.object(runner.validator.graphql_client, "get_deep_coin", new_callable=AsyncMock, return_value=None), \
         patch.object(runner.validator.venue, "submit_order", new_callable=AsyncMock, return_value=mock_fill) as mock_submit:
        res_no_deep = await runner.scan_once()
        sui = next(r for r in res_no_deep if r["pair"] == "SUI/USDC")
        assert pytest.approx(sui["fee_hurdle_bps"]) == 8.5
        assert sui["deepbook_fee_bps"] == 2.5
        assert sui["deep_coin"] is None
        assert sui["is_profitable"] is True
        submitted = mock_submit.call_args[0][0]
        assert submitted["deep_coin"] is None
        assert submitted["enable_tranche_fallback"] is True

    # Case 2: Funded Coin<DEEP> -> SUI/USDC drops to 8.0 bps hurdle (5 + 2.0 + 1), attaches deep_coin, invalidates cache
    runner._last_deep_check_ts = 0.0
    funded_coin = _dummy_deep_coin(balance=200_000_000)
    with patch.object(runner, "poll_market_spreads", return_value=live_spreads), \
         patch.object(runner.validator.graphql_client, "get_live_deepbook_fee_params", new_callable=AsyncMock, return_value=live_fees), \
         patch.object(runner.validator.graphql_client, "get_deep_coin", new_callable=AsyncMock, return_value=funded_coin), \
         patch.object(runner.validator.venue, "submit_order", new_callable=AsyncMock, return_value=mock_fill) as mock_submit:
        res_with_deep = await runner.scan_once()
        sui = next(r for r in res_with_deep if r["pair"] == "SUI/USDC")
        assert pytest.approx(sui["fee_hurdle_bps"]) == 8.0
        assert sui["deepbook_fee_bps"] == 2.0
        assert sui["deep_coin"] == funded_coin
        assert sui["deep_fee_amount"] > 15_000_000
        submitted = mock_submit.call_args[0][0]
        assert submitted["deep_coin"] == funded_coin
        assert submitted["deep_fee_amount"] > 15_000_000
        assert runner._last_deep_check_ts == 0.0
