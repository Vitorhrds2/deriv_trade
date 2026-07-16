import argparse
import asyncio
import json
import os
import random
import statistics
import sys
import time
import urllib.request
from collections import Counter
from datetime import datetime, timezone

from dotenv import load_dotenv

from deriv_client import DerivClient
from stats_utils import bootstrap_ci, wilson_ci

HERE = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(HERE, ".env"))
APP_ID = os.getenv("DERIV_APP_ID")
TOKEN = os.getenv("DERIV_API_TOKEN")


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def append_record(path, record):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, separators=(",", ":")) + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def load_records(path):
    if not os.path.exists(path):
        return []
    records = []
    with open(path, encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                records.append(json.loads(line))
    return records


def write_stats(path, stats):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    temp = path + ".tmp"
    with open(temp, "w", encoding="utf-8") as handle:
        json.dump(stats, handle, indent=2)
    os.replace(temp, path)


async def validate_demo(client, expected_account):
    def fetch_accounts():
        req = urllib.request.Request("https://api.derivws.com/trading/v1/options/accounts")
        req.add_header("Authorization", f"Bearer {TOKEN}")
        req.add_header("Deriv-App-ID", str(APP_ID))
        with urllib.request.urlopen(req, timeout=20) as response:
            return json.loads(response.read().decode())

    data = await asyncio.get_running_loop().run_in_executor(None, fetch_accounts)
    accounts = data.get("data", [])
    demo_ids = [a["account_id"] for a in accounts if a.get("account_type") == "demo"]
    real_ids = [a["account_id"] for a in accounts if a.get("account_type") != "demo"]
    connected = client.account_id
    return bool(
        client.use_demo
        and connected == expected_account
        and connected in demo_ids
        and connected not in real_ids
    ), demo_ids, real_ids


async def request(client, payload, timeout=20):
    return await asyncio.wait_for(client.send_request(payload), timeout=timeout)


async def proposal(client, args):
    return await request(client, {
        "proposal": 1,
        "amount": args.stake,
        "basis": "stake",
        "contract_type": args.contract_type,
        "currency": "USD",
        "underlying_symbol": args.symbol,
        "duration": args.duration,
        "duration_unit": "m",
    })


async def timed_buy(client, proposal_id, stake):
    sent_epoch = time.time()
    response = await request(client, {"buy": proposal_id, "price": stake})
    return response, sent_epoch, time.time()


async def buy_pair(client, args, rng):
    proposals = await asyncio.gather(proposal(client, args), proposal(client, args), return_exceptions=True)
    for item in proposals:
        if isinstance(item, Exception) or "error" in item:
            raise RuntimeError(f"proposal failed: {item}")
    buys = await asyncio.gather(
        timed_buy(client, proposals[0]["proposal"]["id"], args.stake),
        timed_buy(client, proposals[1]["proposal"]["id"], args.stake),
        return_exceptions=True,
    )
    legs = []
    errors = []
    for item in buys:
        if isinstance(item, Exception):
            errors.append(str(item))
            continue
        response, sent_epoch, received_epoch = item
        if "error" in response:
            errors.append(str(response))
            continue
        bought = response["buy"]
        legs.append({
            "contract_id": bought["contract_id"],
            "transaction_id": bought.get("transaction_id"),
            "buy_price": float(bought["buy_price"]),
            "buy_current_spot": float(bought.get("current_spot", 0) or 0),
            "buy_sent_epoch": sent_epoch,
            "buy_received_epoch": received_epoch,
            "buy_latency_s": received_epoch - sent_epoch,
        })
    if len(legs) != 2:
        raise RuntimeError(json.dumps({"buy_errors": errors, "open_partial_legs": legs}))
    rng.shuffle(legs)
    return legs[0], legs[1]


async def wait_for_empty_portfolio(client, timeout_s):
    started = time.monotonic()
    while True:
        response = await request(client, {"portfolio": 1})
        if "error" in response:
            raise RuntimeError(response["error"].get("message", "portfolio error"))
        contracts = response.get("portfolio", {}).get("contracts", [])
        if not contracts:
            return
        if time.monotonic() - started >= timeout_s:
            raise TimeoutError(f"portfolio ainda tem {len(contracts)} contrato(s) aberto(s)")
        await asyncio.sleep(15)


async def poc(client, contract_id):
    response = await request(client, {"proposal_open_contract": 1, "contract_id": contract_id})
    if "error" in response:
        raise RuntimeError(response["error"].get("message", "POC error"))
    return response.get("proposal_open_contract", {})


def complete_profit(data):
    value = data.get("profit")
    return float(value) if value is not None else None


async def run_pair(client, args, attempt):
    rng = random.Random(args.seed + attempt)
    record = {
        "attempt": attempt,
        "started_utc": utc_now(),
        "config": experiment_config(args),
        "status": "started",
    }
    try:
        await wait_for_empty_portfolio(client, args.duration * 60 + 120)
        treatment, control = await buy_pair(client, args, rng)
    except Exception as exc:
        record.update(status="buy_error", error=str(exc), ended_utc=utc_now())
        return record

    record["treatment"] = treatment
    record["control"] = control
    record["buy_send_gap_s"] = abs(treatment["buy_sent_epoch"] - control["buy_sent_epoch"])
    record["buy_response_gap_s"] = abs(treatment["buy_received_epoch"] - control["buy_received_epoch"])
    treatment["bid_path"] = []
    control["bid_path"] = []
    treatment_done = False
    control_done = False
    sell_accepted = False
    last_sell_attempt = 0.0
    started = time.monotonic()
    deadline = started + args.duration * 60 + 90

    while time.monotonic() < deadline and not (treatment_done and control_done):
        elapsed = time.monotonic() - started
        tasks = []
        labels = []
        if not treatment_done:
            tasks.append(poc(client, treatment["contract_id"]))
            labels.append("treatment")
        if not control_done:
            tasks.append(poc(client, control["contract_id"]))
            labels.append("control")
        responses = await asyncio.gather(*tasks, return_exceptions=True)

        for label, data in zip(labels, responses):
            if isinstance(data, Exception):
                record.setdefault("poll_errors", []).append({"t": round(elapsed, 3), "leg": label, "error": str(data)})
                continue
            leg = treatment if label == "treatment" else control
            entry_spot = float(data.get("entry_spot", 0) or 0)
            if entry_spot:
                leg["entry_spot"] = entry_spot
            expiry_epoch = float(data.get("date_expiry", data.get("expiry_time", 0)) or 0)
            if expiry_epoch:
                leg["expiry_epoch"] = expiry_epoch
            bid = float(data.get("bid_price", 0) or 0)
            valid_sell = bool(data.get("is_valid_to_sell", False))
            leg["bid_path"].append([round(elapsed, 3), bid, valid_sell])

            if data.get("is_sold"):
                leg["realized_profit"] = complete_profit(data)
                leg["exit"] = "sell_confirmed" if label == "treatment" and sell_accepted else "expiry"
                leg["ended_t"] = round(elapsed, 3)
                if label == "treatment":
                    treatment_done = True
                else:
                    control_done = True
                continue

            if label == "treatment" and valid_sell and not sell_accepted:
                ratio = bid / treatment["buy_price"] if treatment["buy_price"] else 0
                if ratio >= args.threshold and time.monotonic() - last_sell_attempt >= args.sell_retry:
                    last_sell_attempt = time.monotonic()
                    treatment.setdefault("trigger", {"t": round(elapsed, 3), "bid": bid, "ratio": ratio})
                    minimum_price = round(args.threshold * treatment["buy_price"], 2)
                    sell_started = time.monotonic()
                    sell_attempt = {
                        "t": round(elapsed, 3),
                        "observed_bid": bid,
                        "observed_ratio": ratio,
                        "minimum_price": minimum_price,
                    }
                    try:
                        sold = await request(client, {
                            "sell": treatment["contract_id"],
                            "price": minimum_price,
                        })
                        sell_attempt["latency_s"] = round(time.monotonic() - sell_started, 4)
                        if "error" in sold:
                            raise RuntimeError(sold["error"].get("message", "sell error"))
                        sold_for = float(sold.get("sell", {}).get("sold_for", 0) or 0)
                        sell_attempt["sold_for"] = sold_for
                        sell_attempt["status"] = "accepted"
                        treatment.setdefault("sell_attempts", []).append(sell_attempt)
                        sell_accepted = True
                        treatment["sell_latency_s"] = sell_attempt["latency_s"]
                        treatment["sold_for"] = sold_for
                        treatment["slippage"] = sold_for - bid if sold_for else None
                        if sold_for:
                            treatment["realized_profit"] = sold_for - treatment["buy_price"]
                            treatment["exit"] = "sell"
                            treatment["ended_t"] = round(time.monotonic() - started, 3)
                            treatment_done = True
                    except Exception as exc:
                        sell_attempt["latency_s"] = round(time.monotonic() - sell_started, 4)
                        sell_attempt["status"] = "rejected"
                        sell_attempt["error"] = str(exc)
                        treatment.setdefault("sell_attempts", []).append(sell_attempt)

        if not (treatment_done and control_done):
            await asyncio.sleep(args.poll)

    record["ended_utc"] = utc_now()
    treatment_entry = treatment.get("entry_spot", 0)
    control_entry = control.get("entry_spot", 0)
    treatment_expiry = treatment.get("expiry_epoch", 0)
    control_expiry = control.get("expiry_epoch", 0)
    record["entry_spot_gap_abs"] = abs(treatment_entry - control_entry)
    record["expiry_gap_s"] = abs(treatment_expiry - control_expiry)
    record["pair_quality_ok"] = (
        treatment_entry > 0
        and control_entry > 0
        and treatment_expiry > 0
        and control_expiry > 0
        and record["buy_response_gap_s"] <= args.max_buy_response_gap
        and record["entry_spot_gap_abs"] <= args.max_entry_spot_gap
        and record["expiry_gap_s"] <= args.max_expiry_gap
    )
    if treatment_done and control_done:
        record["status"] = "complete"
        record["treatment_profit"] = treatment.get("realized_profit")
        record["control_profit"] = control.get("realized_profit")
        if record["treatment_profit"] is not None and record["control_profit"] is not None:
            record["paired_diff"] = record["treatment_profit"] - record["control_profit"]
            if not record["pair_quality_ok"]:
                record["status"] = "invalid_pair_gap"
        else:
            record["status"] = "invalid_profit"
    else:
        record["status"] = "timeout"
    return record


def experiment_config(args):
    return {
        "symbol": args.symbol,
        "contract_type": args.contract_type,
        "duration_m": args.duration,
        "stake": args.stake,
        "threshold_ratio": args.threshold,
        "poll_s": args.poll,
        "sell_retry_s": args.sell_retry,
        "max_buy_response_gap_s": args.max_buy_response_gap,
        "max_entry_spot_gap": args.max_entry_spot_gap,
        "max_expiry_gap_s": args.max_expiry_gap,
        "minimum_trigger_rate": args.min_trigger_rate,
        "minimum_fill_rate": args.min_fill_rate,
        "assignment_seed": args.seed,
        "expected_account": args.expected_account,
    }


def enforce_config(records, config):
    mismatches = [r for r in records if r.get("config") and r["config"] != config]
    if mismatches:
        raise ValueError("resultados existentes pertencem a outra configuracao")


def analyze(records, target_pairs, min_trigger_rate=0.25, min_fill_rate=0.95):
    valid = [r for r in records if r.get("status") == "complete" and r.get("paired_diff") is not None]
    treatment = [r["treatment_profit"] for r in valid]
    control = [r["control_profit"] for r in valid]
    diffs = [r["paired_diff"] for r in valid]
    t_ci = bootstrap_ci(treatment) if treatment else (0.0, 0.0, 0.0)
    c_ci = bootstrap_ci(control) if control else (0.0, 0.0, 0.0)
    d_ci = bootstrap_ci(diffs) if diffs else (0.0, 0.0, 0.0)
    treatment_wins = sum(profit > 0 for profit in treatment)
    control_wins = sum(profit > 0 for profit in control)
    treatment_wr_ci = wilson_ci(treatment_wins, len(valid))
    control_wr_ci = wilson_ci(control_wins, len(valid))
    treatment_better = sum(diff > 0 for diff in diffs)
    control_better = sum(diff < 0 for diff in diffs)
    ties = sum(diff == 0 for diff in diffs)
    paired_wr_ci = wilson_ci(treatment_better, len(valid))
    triggered = [r for r in valid if r["treatment"].get("trigger")]
    sold = [r for r in triggered if r["treatment"].get("exit") in ("sell", "sell_confirmed")]
    slippage = [r["treatment"].get("slippage") for r in sold if r["treatment"].get("slippage") is not None]
    sell_latency = [r["treatment"].get("sell_latency_s") for r in sold if r["treatment"].get("sell_latency_s") is not None]
    buy_response_gaps = [r.get("buy_response_gap_s") for r in valid if r.get("buy_response_gap_s") is not None]
    expiry_gaps = [r.get("expiry_gap_s") for r in valid if r.get("expiry_gap_s") is not None]
    entry_spot_gaps = [r.get("entry_spot_gap_abs") for r in valid if r.get("entry_spot_gap_abs") is not None]
    trigger_rate = len(triggered) / len(valid) if valid else 0.0
    fill_rate = len(sold) / len(triggered) if triggered else 0.0
    gate = (
        len(valid) >= target_pairs
        and trigger_rate >= min_trigger_rate
        and fill_rate >= min_fill_rate
        and t_ci[0] > 0
        and d_ci[0] > 0
    )
    return {
        "updated_utc": utc_now(),
        "attempts": len(records),
        "status_counts": dict(sorted(Counter(r.get("status", "missing") for r in records).items())),
        "valid_pairs": len(valid),
        "target_pairs": target_pairs,
        "treatment_ev_ci95": list(t_ci),
        "control_ev_ci95": list(c_ci),
        "paired_diff_ci95": list(d_ci),
        "treatment_total_pnl": sum(treatment),
        "control_total_pnl": sum(control),
        "treatment_wins": treatment_wins,
        "treatment_win_rate": treatment_wins / len(valid) if valid else 0.0,
        "treatment_win_rate_wilson_ci95": list(treatment_wr_ci),
        "control_wins": control_wins,
        "control_win_rate": control_wins / len(valid) if valid else 0.0,
        "control_win_rate_wilson_ci95": list(control_wr_ci),
        "treatment_better_pairs": treatment_better,
        "control_better_pairs": control_better,
        "tied_pairs": ties,
        "paired_treatment_better_rate": treatment_better / len(valid) if valid else 0.0,
        "paired_treatment_better_wilson_ci95": list(paired_wr_ci),
        "triggered": len(triggered),
        "trigger_rate": trigger_rate,
        "minimum_trigger_rate": min_trigger_rate,
        "sold": len(sold),
        "triggered_not_filled": len(triggered) - len(sold),
        "fill_rate": fill_rate,
        "minimum_fill_rate": min_fill_rate,
        "mean_slippage": statistics.mean(slippage) if slippage else None,
        "minimum_slippage": min(slippage) if slippage else None,
        "maximum_slippage": max(slippage) if slippage else None,
        "mean_sell_latency_s": statistics.mean(sell_latency) if sell_latency else None,
        "maximum_sell_latency_s": max(sell_latency) if sell_latency else None,
        "mean_buy_response_gap_s": statistics.mean(buy_response_gaps) if buy_response_gaps else None,
        "maximum_buy_response_gap_s": max(buy_response_gaps) if buy_response_gaps else None,
        "maximum_entry_spot_gap": max(entry_spot_gaps) if entry_spot_gaps else None,
        "maximum_expiry_gap_s": max(expiry_gaps) if expiry_gaps else None,
        "demo_gate_pass": gate,
        "decision": "DEMO_SIGNAL" if gate else "NOT_VALIDATED",
    }


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--pairs", type=int, default=20)
    parser.add_argument("--symbol", default="1HZ10V")
    parser.add_argument("--contract-type", default="CALL", choices=("CALL", "PUT"))
    parser.add_argument("--duration", type=int, default=15)
    parser.add_argument("--stake", type=float, default=10.0)
    parser.add_argument("--threshold", type=float, default=1.20)
    parser.add_argument("--poll", type=float, default=1.0)
    parser.add_argument("--sell-retry", type=float, default=3.0)
    parser.add_argument("--max-buy-response-gap", type=float, default=2.0)
    parser.add_argument("--max-entry-spot-gap", type=float, default=0.0)
    parser.add_argument("--max-expiry-gap", type=float, default=2.0)
    parser.add_argument("--min-trigger-rate", type=float, default=0.25)
    parser.add_argument("--min-fill-rate", type=float, default=0.95)
    parser.add_argument("--seed", type=int, default=72120)
    parser.add_argument("--expected-account", required=True)
    parser.add_argument("--validate-only", action="store_true")
    parser.add_argument("--results-file", default=os.path.join(HERE, "logs", "early_sell_paired_ab", "results.jsonl"))
    parser.add_argument("--stats-file", default=os.path.join(HERE, "logs", "early_sell_paired_ab", "stats.json"))
    args = parser.parse_args()

    if not APP_ID or not TOKEN:
        raise SystemExit("DERIV_APP_ID/DERIV_API_TOKEN ausentes")
    records = load_records(args.results_file)
    enforce_config(records, experiment_config(args))
    valid_count = sum(1 for r in records if r.get("status") == "complete" and r.get("paired_diff") is not None)
    client = DerivClient(app_id=APP_ID, api_token=TOKEN, use_demo=True)
    await client.connect()
    ok, demo_ids, real_ids = await validate_demo(client, args.expected_account)
    print(f"account={client.account_id} demo={demo_ids} real={real_ids} validated={ok}", flush=True)
    if not ok:
        await client.disconnect()
        raise SystemExit("TRAVA: conta demo esperada nao confirmada")
    if args.validate_only:
        portfolio = await request(client, {"portfolio": 1})
        contracts = portfolio.get("portfolio", {}).get("contracts", [])
        print(json.dumps({"validated_demo": True, "account": client.account_id, "open_contracts": len(contracts)}))
        await client.disconnect()
        return

    attempt = max([r.get("attempt", 0) for r in records], default=0)
    max_attempts = attempt + max(args.pairs * 2, 10)
    while valid_count < args.pairs and attempt < max_attempts:
        attempt += 1
        record = await run_pair(client, args, attempt)
        append_record(args.results_file, record)
        records.append(record)
        stats = analyze(records, args.pairs, args.min_trigger_rate, args.min_fill_rate)
        write_stats(args.stats_file, stats)
        valid_count = stats["valid_pairs"]
        print(f"attempt={attempt} status={record['status']} valid={valid_count}/{args.pairs} stats={json.dumps(stats)}", flush=True)
        await asyncio.sleep(2)

    await client.disconnect()
    stats = analyze(records, args.pairs, args.min_trigger_rate, args.min_fill_rate)
    write_stats(args.stats_file, stats)
    print(json.dumps(stats, indent=2), flush=True)
    if stats["valid_pairs"] < args.pairs:
        raise SystemExit(2)


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    asyncio.run(main())
