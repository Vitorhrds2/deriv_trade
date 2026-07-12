import argparse
import json
import os
import time
from datetime import datetime, timezone

from iv_anomaly_paper_bot import (
    build_iv_surface,
    compute_fair_iv,
    compute_vega,
    fetch_json,
    fetch_options,
    filter_liquid,
    find_neighbors,
)
from stats_utils import bootstrap_ci, wilson_ci

OPTION_FEE_RATE = 0.0003
OPTION_FEE_CAP_FRACTION = 0.125
CURRENCIES = ("BTC", "ETH")


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def atomic_write(path, value):
    absolute = os.path.abspath(path)
    os.makedirs(os.path.dirname(absolute), exist_ok=True)
    temporary = absolute + ".tmp"
    with open(temporary, "w", encoding="utf-8") as handle:
        json.dump(value, handle, indent=2, sort_keys=True)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, absolute)


def load_state(path):
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def experiment_config(args):
    return {
        "paper_only": True,
        "currencies": list(CURRENCIES),
        "mispricing_threshold_iv": args.threshold_iv,
        "reversion_threshold_iv": args.reversion_iv,
        "position_usd": args.position_usd,
        "max_positions": args.max_positions,
        "max_entries_per_cycle": args.max_entries_per_cycle,
        "max_hold_hours": args.max_hold_hours,
        "target_settled": args.target_settled,
        "target_clusters": args.target_clusters,
        "enforce_min_trade_amount": True,
        "option_fee_rate_underlying": OPTION_FEE_RATE,
        "option_fee_cap_fraction_premium": OPTION_FEE_CAP_FRACTION,
    }


def empty_state(config):
    return {
        "version": 1,
        "strategy": "D36_IV_ANOMALY_OOS_ASK_TO_BID",
        "config": config,
        "trades": [],
        "cycles": 0,
        "created_utc": utc_now(),
        "updated_utc": utc_now(),
    }


def option_fair_iv(option, surface):
    neighbors = find_neighbors(surface, option["expiry_str"], option["strike"], option["type"])
    return compute_fair_iv(neighbors)


def make_candidate(option, fair_iv, position_usd, now, entry_cycle=None):
    entry_price_usd = option["ask"] * option["underlying_price"]
    if entry_price_usd <= 0:
        return None
    minimum = option.get("min_trade_amount")
    if not minimum or minimum <= 0:
        return None
    raw_quantity = position_usd / entry_price_usd
    quantity = int((raw_quantity + 1e-12) / minimum) * minimum
    if quantity < minimum:
        return None
    deviation = option["iv"] - fair_iv
    expected_usd_per_contract = abs(deviation) * compute_vega(option, fair_iv)
    expected_gross_usd = expected_usd_per_contract * quantity
    spread_cost_usd = (option["ask"] - option["bid"]) * option["underlying_price"] * quantity
    estimated_fees_usd = 2 * option_fee_usd(option["ask"], option["underlying_price"], quantity)
    expected_net_usd = expected_gross_usd - spread_cost_usd - estimated_fees_usd
    actual_entry_value_usd = entry_price_usd * quantity
    expected_return_pct = expected_net_usd / actual_entry_value_usd * 100
    if expected_net_usd <= 0:
        return None
    return {
        "currency": option["currency"],
        "instrument": option["instrument"],
        "type": option["type"],
        "strike": option["strike"],
        "expiry": option["expiry_str"],
        "entry_time": now.isoformat(),
        "entry_price_crypto": option["ask"],
        "entry_underlying": option["underlying_price"],
        "entry_value_usd": entry_price_usd * quantity,
        "entry_iv": option["iv"],
        "entry_fair_iv": fair_iv,
        "entry_deviation_iv": deviation,
        "entry_bid": option["bid"],
        "entry_ask": option["ask"],
        "entry_spread_pct": option["spread_pct"],
        "quantity": quantity,
        "min_trade_amount": minimum,
        "expected_gross_usd": expected_gross_usd,
        "expected_spread_cost_usd": spread_cost_usd,
        "expected_fees_usd": estimated_fees_usd,
        "expected_net_usd": expected_net_usd,
        "expected_return_pct": expected_return_pct,
        "entry_cycle": entry_cycle,
        "status": "open",
    }


def option_fee_usd(price_crypto, underlying_price, quantity):
    underlying_fee = underlying_price * OPTION_FEE_RATE * quantity
    premium_cap = price_crypto * underlying_price * OPTION_FEE_CAP_FRACTION * quantity
    return min(underlying_fee, premium_cap)


def settle_trade(trade, option, fair_iv, now, reason):
    exit_price_crypto = option["bid"]
    exit_underlying = option["underlying_price"]
    quantity = trade["quantity"]
    entry_value = trade["entry_price_crypto"] * trade["entry_underlying"] * quantity
    exit_value = exit_price_crypto * exit_underlying * quantity
    entry_fee = option_fee_usd(trade["entry_price_crypto"], trade["entry_underlying"], quantity)
    exit_fee = option_fee_usd(exit_price_crypto, exit_underlying, quantity)
    fees = entry_fee + exit_fee
    pnl_usd = exit_value - entry_value - fees
    trade.update({
        "status": "settled",
        "exit_reason": reason,
        "exit_time": now.isoformat(),
        "entry_value_usd": entry_value,
        "exit_price_crypto": exit_price_crypto,
        "exit_underlying": exit_underlying,
        "exit_value_usd": exit_value,
        "exit_iv": option["iv"],
        "exit_fair_iv": fair_iv,
        "exit_deviation_iv": option["iv"] - fair_iv if fair_iv is not None else None,
        "entry_fee_usd": entry_fee,
        "exit_fee_usd": exit_fee,
        "fees_usd": fees,
        "pnl_usd": pnl_usd,
        "pnl_pct": pnl_usd / entry_value * 100 if entry_value else 0.0,
        "hold_hours": (now - datetime.fromisoformat(trade["entry_time"])).total_seconds() / 3600,
    })
    return trade


def compute_stats(state, target_settled, target_clusters):
    settled = [trade for trade in state.get("trades", []) if trade.get("status") == "settled"]
    open_trades = [trade for trade in state.get("trades", []) if trade.get("status") == "open"]
    pnls = [trade["pnl_pct"] for trade in settled]
    wins = sum(pnl > 0 for pnl in pnls)
    ev_ci = bootstrap_ci(pnls) if pnls else (0.0, 0.0, 0.0)
    wr_ci = wilson_ci(wins, len(pnls))
    clusters = {}
    for trade in settled:
        cluster = str(trade.get("entry_cycle", trade["entry_time"]))
        clusters.setdefault(cluster, []).append(trade["pnl_pct"])
    cluster_pnls = [sum(values) / len(values) for values in clusters.values()]
    cluster_ci = bootstrap_ci(cluster_pnls) if cluster_pnls else (0.0, 0.0, 0.0)
    gate = (
        len(pnls) >= target_settled
        and len(cluster_pnls) >= target_clusters
        and ev_ci[0] > 0
        and cluster_ci[0] > 0
    )
    return {
        "updated_utc": utc_now(),
        "cycles": state.get("cycles", 0),
        "settled": len(settled),
        "target_settled": target_settled,
        "settled_clusters": len(cluster_pnls),
        "target_clusters": target_clusters,
        "open": len(open_trades),
        "wins": wins,
        "win_rate": wins / len(pnls) if pnls else 0.0,
        "win_rate_wilson_ci95": list(wr_ci),
        "ev_pct_ci95": list(ev_ci),
        "cluster_ev_pct_ci95": list(cluster_ci),
        "total_pnl_usd": sum(trade["pnl_usd"] for trade in settled),
        "total_pnl_pct": sum(pnls),
        "paper_gate_pass": gate,
        "decision": "PAPER_SIGNAL" if gate else "NOT_VALIDATED",
    }


def fetch_market():
    market = {}
    for currency in CURRENCIES:
        instruments = fetch_json(
            f"https://www.deribit.com/api/v2/public/get_instruments?currency={currency}&kind=option&expired=false"
        ).get("result", [])
        minimums = {
            item["instrument_name"]: float(item.get("min_trade_amount", 0) or 0)
            for item in instruments
        }
        options = fetch_options(currency)
        for option in options:
            option["min_trade_amount"] = minimums.get(option["instrument"], 0)
        liquid = filter_liquid(options)
        market[currency] = {
            "all": {option["instrument"]: option for option in options},
            "liquid": liquid,
            "surface": build_iv_surface(liquid),
        }
    return market


def run_cycle(state, args, now=None, market=None):
    now = now or datetime.now(timezone.utc)
    market = market or fetch_market()
    settled_now = []
    for trade in [item for item in state["trades"] if item.get("status") == "open"]:
        currency_market = market.get(trade["currency"], {})
        option = currency_market.get("all", {}).get(trade["instrument"])
        if not option or option["bid"] <= 0 or option["underlying_price"] <= 0:
            continue
        surface = currency_market.get("surface", {})
        fair_iv = option_fair_iv(option, surface)
        age_h = (now - datetime.fromisoformat(trade["entry_time"])).total_seconds() / 3600
        reason = None
        if fair_iv is not None and abs(option["iv"] - fair_iv) <= args.reversion_iv:
            reason = "reversion"
        elif age_h >= args.max_hold_hours:
            reason = "timeout"
        if reason:
            settle_trade(trade, option, fair_iv, now, reason)
            settled_now.append(trade["instrument"])

    open_instruments = {trade["instrument"] for trade in state["trades"] if trade.get("status") == "open"}
    capacity = max(0, args.max_positions - len(open_instruments))
    candidates = []
    for currency in CURRENCIES:
        currency_market = market[currency]
        for option in currency_market["liquid"]:
            if option["instrument"] in open_instruments:
                continue
            remaining_hours = (option["expiry_date"] - now).total_seconds() / 3600
            if remaining_hours <= args.max_hold_hours + 1:
                continue
            fair_iv = option_fair_iv(option, currency_market["surface"])
            if fair_iv is None or option["iv"] - fair_iv > -args.threshold_iv:
                continue
            candidate = make_candidate(option, fair_iv, args.position_usd, now, state.get("cycles", 0) + 1)
            if candidate:
                candidates.append(candidate)
    candidates.sort(key=lambda item: (item["expected_return_pct"], -item["entry_spread_pct"]), reverse=True)
    entry_limit = min(capacity, args.max_entries_per_cycle)
    new_entries = candidates[:entry_limit]
    state["trades"].extend(new_entries)
    state["cycles"] = state.get("cycles", 0) + 1
    state["last_cycle_epoch"] = now.timestamp()
    state["updated_utc"] = utc_now()
    return {
        "settled": settled_now,
        "entered": [trade["instrument"] for trade in new_entries],
        "candidate_count": len(candidates),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--threshold-iv", type=float, default=3.0)
    parser.add_argument("--reversion-iv", type=float, default=1.0)
    parser.add_argument("--position-usd", type=float, default=100.0)
    parser.add_argument("--max-positions", type=int, default=10)
    parser.add_argument("--max-entries-per-cycle", type=int, default=2)
    parser.add_argument("--max-hold-hours", type=float, default=168.0)
    parser.add_argument("--target-settled", type=int, default=30)
    parser.add_argument("--target-clusters", type=int, default=15)
    parser.add_argument("--interval-s", type=float, default=3600.0)
    parser.add_argument("--state-file", default="d36_oos_state.json")
    parser.add_argument("--stats-file", default="d36_oos_stats.json")
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args()

    if args.validate_only:
        market = fetch_market()
        print(json.dumps({
            "paper_only": True,
            "currencies": {
                currency: {
                    "all": len(data["all"]),
                    "liquid": len(data["liquid"]),
                }
                for currency, data in market.items()
            },
        }, sort_keys=True))
        return

    config = experiment_config(args)
    state = load_state(args.state_file)
    if state is None:
        state = empty_state(config)
    elif state.get("config") != config:
        raise SystemExit("estado pertence a outra configuracao")

    while True:
        elapsed_since_cycle = time.time() - state.get("last_cycle_epoch", 0)
        wait_s = max(0.0, args.interval_s - elapsed_since_cycle)
        if wait_s > 0:
            if args.once:
                stats = compute_stats(state, args.target_settled, args.target_clusters)
                print(json.dumps({"cycle": {"skipped_wait_s": wait_s}, "stats": stats}, sort_keys=True), flush=True)
                break
            time.sleep(wait_s)
        market = fetch_market()
        result = run_cycle(state, args, market=market)
        atomic_write(args.state_file, state)
        stats = compute_stats(state, args.target_settled, args.target_clusters)
        atomic_write(args.stats_file, stats)
        print(json.dumps({"cycle": result, "stats": stats}, sort_keys=True), flush=True)
        if args.once:
            break


if __name__ == "__main__":
    main()
