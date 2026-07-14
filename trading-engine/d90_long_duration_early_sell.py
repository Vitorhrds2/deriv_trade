import argparse
import asyncio
import fcntl
import json
import os
import re
import statistics
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone

from dotenv import load_dotenv

for _p in [os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")]:
    if os.path.exists(_p):
        load_dotenv(_p)
        break

from d90_deriv_client import DerivClient
from stats_utils import bootstrap_ci

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

APP_ID = os.getenv("DERIV_APP_ID")
TOKEN = os.getenv("DERIV_API_TOKEN")
STAKE = 1.0
SYMBOL = "1HZ10V"
DEFAULT_DURATIONS = ["15m", "1h"]
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_RESULTS = os.path.join(BASE_DIR, "d90_long_duration_early_sell_results.jsonl")
DEFAULT_STATS = os.path.join(BASE_DIR, "d90_long_duration_early_sell_stats.json")
DEFAULT_STATE = os.path.join(BASE_DIR, "d90_long_duration_early_sell_state.json")


def parse_duration(value):
    match = re.fullmatch(r"(\d+)([smhd])", value.strip().lower())
    if not match:
        raise argparse.ArgumentTypeError(f"duracao invalida: {value}")
    return int(match.group(1)), match.group(2)


def parse_csv(value):
    return [item.strip() for item in value.split(",") if item.strip()]


def duration_seconds(duration, duration_unit):
    return duration * {"s": 1, "m": 60, "h": 3600, "d": 86400}[duration_unit]


class AmbiguousBuyError(RuntimeError):
    pass


class D90ConfigurationError(RuntimeError):
    pass


def now_utc():
    return datetime.now(timezone.utc).isoformat()


def atomic_write_json(path, value):
    tmp_path = f"{path}.tmp"
    with open(tmp_path, "w", encoding="utf-8") as handle:
        json.dump(value, handle, indent=2, ensure_ascii=False, default=str)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp_path, path)


def append_jsonl(path, record):
    with open(path, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def load_json(path):
    if not os.path.exists(path):
        return None
    try:
        with open(path, encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        raise D90ConfigurationError(f"state inválido ou corrompido: {path}") from error


def load_records(path):
    if not os.path.exists(path):
        return []
    records = []
    with open(path, encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError as error:
                raise D90ConfigurationError(f"resultado JSONL inválido: {path}") from error
            if not isinstance(record, dict):
                raise D90ConfigurationError(f"resultado JSONL inválido: {path}")
            records.append(record)
    return records


def arm_key(record):
    return record.get("pair_id"), record.get("group")


def is_completed_record(record):
    return "strategy_profit" in record and not record.get("error")


def build_plan(durations, pairs):
    plan = {}
    pair_id = 0
    for duration, duration_unit in durations:
        for local_pair in range(pairs):
            contract_type = "CALL" if local_pair % 2 == 0 else "PUT"
            arms = ["sell", "hold"] if local_pair % 2 == 0 else ["hold", "sell"]
            for group in arms:
                plan[(pair_id, group)] = {
                    "pair_id": pair_id,
                    "group": group,
                    "contract_type": contract_type,
                    "duration": duration,
                    "duration_unit": duration_unit,
                }
            pair_id += 1
    return plan


def completed_records_by_key(records, plan, threshold):
    completed = {}
    for record in records:
        if not is_completed_record(record):
            continue
        key = arm_key(record)
        expected = plan.get(key)
        if not expected:
            raise D90ConfigurationError(f"registro fora do plano atual: {key}")
        if any(record.get(field) != value for field, value in expected.items() if field != "group"):
            raise D90ConfigurationError(f"registro incompatível com o plano atual: {key}")
        if record.get("group") == "sell" and float(record.get("threshold", threshold)) != threshold:
            raise D90ConfigurationError(f"threshold incompatível no registro: {key}")
        if key in completed:
            raise D90ConfigurationError(f"registro duplicado para o mesmo braço: {key}")
        completed[key] = record
    return completed


def state_config(args, durations):
    return {
        "output": os.path.abspath(args.output),
        "symbol": SYMBOL,
        "stake": STAKE,
        "threshold": args.threshold,
        "pairs": args.pairs,
        "durations": [{"duration": duration, "duration_unit": unit} for duration, unit in durations],
    }


def load_or_create_state(args, durations):
    config = state_config(args, durations)
    state = load_json(args.state)
    if state is None:
        state = {
            "version": 1,
            "config": config,
            "inflight": None,
            "status": "running",
            "created_at": now_utc(),
        }
    elif state.get("config") != config:
        raise D90ConfigurationError("state pertence a uma configuração D90 diferente")
    return state


def checkpoint(state, path):
    state["updated_at"] = now_utc()
    atomic_write_json(path, state)


async def validate_demo_account(client):
    import urllib.request

    def fetch_accounts():
        request = urllib.request.Request("https://api.derivws.com/trading/v1/options/accounts")
        request.add_header("Authorization", f"Bearer {TOKEN}")
        request.add_header("Deriv-App-ID", str(APP_ID))
        with urllib.request.urlopen(request) as response:
            return json.loads(response.read().decode())

    try:
        accounts = await asyncio.get_running_loop().run_in_executor(None, fetch_accounts)
    except Exception as error:
        print(f"ERRO: não foi possível validar a conta DEMO: {error}", flush=True)
        return False
    demo_ids = {
        account.get("account_id")
        for account in accounts.get("data", [])
        if account.get("account_type") == "demo"
    }
    valid = bool(client.use_demo and client.account_id in demo_ids)
    print(f"Conta conectada: {client.account_id} | {'DEMO confirmada' if valid else 'NAO DEMO'}", flush=True)
    return valid


async def get_poc(client, contract_id, retries=12):
    for attempt in range(retries):
        try:
            response = await asyncio.wait_for(
                client.send_request({
                    "proposal_open_contract": 1,
                    "contract_id": contract_id,
                }),
                timeout=60,
            )
            poc = response.get("proposal_open_contract")
            if "error" not in response and isinstance(poc, dict):
                return poc
        except Exception:
            pass
        await asyncio.sleep(min(2 * (attempt + 1), 15))
    return None


async def request_proposal(client, contract_type, duration, duration_unit, retries=8):
    payload = {
        "proposal": 1,
        "amount": STAKE,
        "basis": "stake",
        "contract_type": contract_type,
        "currency": "USD",
        "underlying_symbol": SYMBOL,
        "duration": duration,
        "duration_unit": duration_unit,
    }
    for attempt in range(retries):
        try:
            response = await asyncio.wait_for(client.send_request(payload.copy()), timeout=60)
        except Exception:
            await asyncio.sleep(min(2 * (attempt + 1), 15))
            continue
        if "error" in response:
            return None, f"proposal: {response['error'].get('message', 'unknown error')}"
        proposal = response.get("proposal", {})
        if proposal.get("id"):
            return proposal, None
        return None, "proposal sem id valido"
    return None, "proposal: reconexões esgotadas"


async def buy_contract(client, contract_type, duration, duration_unit):
    proposal, error = await request_proposal(client, contract_type, duration, duration_unit)
    if error:
        return None, error
    try:
        buy_response = await asyncio.wait_for(
            client.buy_contract(proposal["id"], price=STAKE), timeout=60
        )
    except Exception as error:
        raise AmbiguousBuyError(
            "conexão caiu após enviar buy; não é seguro repetir sem reconciliar a conta"
        ) from error
    if "error" in buy_response:
        return None, f"buy: {buy_response['error'].get('message', 'unknown error')}"
    buy = buy_response.get("buy", {})
    contract_id = buy.get("contract_id")
    buy_price = float(buy.get("buy_price", 0))
    if not contract_id or buy_price <= 0:
        raise AmbiguousBuyError("buy respondeu sem contract_id/buy_price valido")
    return {
        "contract_id": contract_id,
        "buy_price": buy_price,
        "ask_price": float(proposal.get("ask_price", buy_price)),
        "payout": float(proposal.get("payout", 0)),
        "proposal_spot": proposal.get("spot"),
        "longcode": proposal.get("longcode"),
    }, None


def started_epoch(record):
    try:
        return datetime.fromisoformat(record["ts"]).timestamp()
    except (KeyError, TypeError, ValueError):
        return time.time()


async def monitor_sell_arm(client, record, poll_interval, on_update=None):
    start = started_epoch(record)
    deadline = start + duration_seconds(record["duration"], record["duration_unit"]) + args_timeout_padding(record["duration_unit"])
    bid_path = []
    while True:
        poc = await get_poc(client, record["contract_id"])
        if poc is None:
            await asyncio.sleep(poll_interval)
            continue
        if poc.get("is_sold"):
            profit = float(poc.get("profit", 0))
            terminal = "sold" if record.get("sell_request_pending") else "expired"
            record.update({
                "terminal": terminal,
                "sold": terminal == "sold",
                "expired": terminal == "expired",
                "strategy_profit": profit,
                "hold_profit": profit if terminal == "expired" else record.get("hold_profit"),
                "max_bid_ratio": max((item["bid_ratio"] for item in bid_path), default=record.get("max_bid_ratio", 0.0)),
                "elapsed_seconds": time.time() - start,
            })
            return record
        if record.pop("sell_request_pending", None) and on_update:
            on_update(record)
        bid = poc.get("bid_price")
        if bid is not None:
            bid_value = float(bid)
            bid_ratio = bid_value / record["buy_price"]
            bid_path.append({
                "t": round(time.time() - start, 3),
                "bid": bid_value,
                "bid_ratio": bid_ratio,
            })
            if time.time() < deadline and bid_ratio >= record["threshold"]:
                record["sell_request_pending"] = True
                if on_update:
                    on_update(record)
                try:
                    sell_response = await asyncio.wait_for(
                        client.sell_contract(record["contract_id"], price=0), timeout=60
                    )
                except Exception as error:
                    record["sell_error"] = f"sell reconnect/timeout: {error}"
                    if on_update:
                        on_update(record)
                else:
                    if "error" not in sell_response:
                        sold = sell_response.get("sell", {})
                        sold_for = float(sold.get("sold_for", sold.get("sell_price", 0)))
                        if sold_for > 0:
                            record.update({
                                "terminal": "sold",
                                "sold": True,
                                "sell_price": sold_for,
                                "strategy_profit": sold_for - record["buy_price"],
                                "sell_time_seconds": time.time() - start,
                                "sell_bid_ratio": bid_ratio,
                                "max_bid_ratio": max(item["bid_ratio"] for item in bid_path),
                            })
                            return record
                    record.pop("sell_request_pending", None)
                    record["sell_error"] = sell_response.get("error", {}).get("message", "sell sem preço valido")
                    if on_update:
                        on_update(record)
        if time.time() >= deadline:
            record.setdefault("settlement_overdue_at", now_utc())
        await asyncio.sleep(poll_interval)


async def run_sell_arm(client, pair_id, contract_type, duration, duration_unit, threshold, poll_interval, on_bought=None):
    record = {
        "ts": now_utc(),
        "pair_id": pair_id,
        "group": "sell",
        "contract_type": contract_type,
        "duration": duration,
        "duration_unit": duration_unit,
        "threshold": threshold,
    }
    bought, error = await buy_contract(client, contract_type, duration, duration_unit)
    if error:
        record["error"] = error
        return record
    record.update(bought)
    if on_bought:
        on_bought(record)
    return await monitor_sell_arm(client, record, poll_interval, on_bought)


async def monitor_hold_arm(client, record, poll_interval):
    start = started_epoch(record)
    deadline = start + duration_seconds(record["duration"], record["duration_unit"]) + args_timeout_padding(record["duration_unit"])
    while True:
        poc = await get_poc(client, record["contract_id"])
        if poc is None:
            await asyncio.sleep(poll_interval)
            continue
        if poc.get("is_sold"):
            profit = float(poc.get("profit", 0))
            record.update({
                "terminal": "expired",
                "expired": True,
                "strategy_profit": profit,
                "hold_profit": profit,
                "is_won": poc.get("is_won"),
                "elapsed_seconds": time.time() - start,
            })
            return record
        if time.time() >= deadline:
            record.setdefault("settlement_overdue_at", now_utc())
        await asyncio.sleep(poll_interval)


async def run_hold_arm(client, pair_id, contract_type, duration, duration_unit, poll_interval, on_bought=None):
    record = {
        "ts": now_utc(),
        "pair_id": pair_id,
        "group": "hold",
        "contract_type": contract_type,
        "duration": duration,
        "duration_unit": duration_unit,
    }
    bought, error = await buy_contract(client, contract_type, duration, duration_unit)
    if error:
        record["error"] = error
        return record
    record.update(bought)
    if on_bought:
        on_bought(record)
    return await monitor_hold_arm(client, record, poll_interval)


def args_timeout_padding(duration_unit):
    return 120 if duration_unit in ("s", "m") else 300


def analyze(records, threshold):
    groups = defaultdict(list)
    for record in records:
        if "strategy_profit" in record and "error" not in record:
            groups[(record["duration"], record["duration_unit"])].append(record)
    summary = {}
    for (duration, duration_unit), rows in sorted(groups.items()):
        by_pair = defaultdict(dict)
        for row in rows:
            by_pair[row["pair_id"]][row["group"]] = row
        pair_diffs = []
        sell_values = []
        hold_values = []
        sold_count = 0
        for arms in by_pair.values():
            sell = arms.get("sell")
            hold = arms.get("hold")
            if not sell or not hold:
                continue
            sell_value = sell["strategy_profit"]
            hold_value = hold["strategy_profit"]
            pair_diffs.append(sell_value - hold_value)
            sell_values.append(sell_value)
            hold_values.append(hold_value)
            sold_count += int(sell.get("sold", False))
        lo, point, hi = bootstrap_ci(pair_diffs) if pair_diffs else (0.0, 0.0, 0.0)
        summary[f"{duration}{duration_unit}"] = {
            "duration": duration,
            "duration_unit": duration_unit,
            "threshold": threshold,
            "pairs": len(pair_diffs),
            "sell_ev": statistics.mean(sell_values) if sell_values else None,
            "hold_ev": statistics.mean(hold_values) if hold_values else None,
            "sold_count": sold_count,
            "sell_trigger_rate": sold_count / len(pair_diffs) if pair_diffs else None,
            "paired_diff": point,
            "paired_diff_ci95": [lo, hi],
            "verdict": (
                "positive_edge" if lo > 0 else
                "negative_edge" if hi < 0 else
                "inconclusive"
            ),
        }
    return summary


def write_stats(args, records):
    summary = analyze(records, args.threshold)
    stats = {
        "ts": now_utc(),
        "symbol": SYMBOL,
        "threshold": args.threshold,
        "n_records": len(records),
        "summary": summary,
        "method": "alternating independent sell/hold arms, paired by pair_id, bootstrap CI on sell_strategy_profit - hold_profit",
    }
    atomic_write_json(args.stats, stats)
    return summary


def print_summary(summary, args):
    print("=" * 100)
    for label, result in summary.items():
        print(
            f"{label}: pairs={result['pairs']} sell={result['sell_ev']} hold={result['hold_ev']} "
            f"diff={result['paired_diff']:+.4f} CI95%={result['paired_diff_ci95']} "
            f"verdict={result['verdict']}"
        )
    print(f"Results: {args.output}")
    print(f"Stats: {args.stats}")


def validate_inflight(inflight, plan):
    if not isinstance(inflight, dict):
        raise D90ConfigurationError("state inflight invalido")
    phase = inflight.get("phase")
    if phase not in {"buying", "monitoring"}:
        raise D90ConfigurationError(f"fase inflight invalida: {phase}")
    record = inflight.get("record") if phase == "monitoring" else inflight.get("arm")
    if not isinstance(record, dict):
        raise D90ConfigurationError("state inflight sem registro do braço")
    key = arm_key(record)
    expected = plan.get(key)
    if not expected:
        raise D90ConfigurationError(f"state inflight fora do plano atual: {key}")
    if any(record.get(field) != value for field, value in expected.items()):
        raise D90ConfigurationError(f"state inflight incompatível com o plano atual: {key}")
    if phase == "monitoring" and not record.get("contract_id"):
        raise D90ConfigurationError("state monitoring sem contract_id")
    return phase, record, key


def inspect_resume(args, durations):
    plan = build_plan(durations, args.pairs)
    records = load_records(args.output)
    completed = completed_records_by_key(records, plan, args.threshold)
    state = load_json(args.state)
    if state is not None:
        if state.get("config") != state_config(args, durations):
            raise D90ConfigurationError("state pertence a uma configuração D90 diferente")
        inflight = state.get("inflight")
        if inflight:
            phase, _, key = validate_inflight(inflight, plan)
            inflight_label = f"{phase} {key}"
        else:
            inflight_label = "nenhum"
        status = state.get("status", "unknown")
    else:
        inflight_label = "nenhum"
        status = "sem state persistido"
    print("D90 em modo seguro: nenhuma ordem sera enviada.")
    print(f"Plano: {args.pairs} pares por duracao, durations={durations}, threshold={args.threshold}x")
    print(f"Braços concluídos: {len(completed)}/{len(plan)} | pendentes: {len(plan) - len(completed)}")
    print(f"State: {args.state} | status={status} | inflight={inflight_label}")
    print("Para habilitar trades DEMO explicitamente, use --live.")


def acquire_run_lock(state_path):
    lock_handle = open(f"{state_path}.lock", "a", encoding="utf-8")
    try:
        fcntl.flock(lock_handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError as error:
        lock_handle.close()
        raise D90ConfigurationError(f"outra execução D90 já usa o state: {state_path}") from error
    return lock_handle


async def run_live_locked(args):
    durations = [parse_duration(item) for item in parse_csv(args.durations)]
    plan = build_plan(durations, args.pairs)
    records = load_records(args.output)
    completed = completed_records_by_key(records, plan, args.threshold)
    state = load_or_create_state(args, durations)
    inflight = state.get("inflight")
    if inflight:
        phase, _, key = validate_inflight(inflight, plan)
        if key in completed:
            state["inflight"] = None
            state["status"] = "running"
            checkpoint(state, args.state)
            inflight = None
        elif phase == "buying":
            state["status"] = "manual_reconciliation_required"
            checkpoint(state, args.state)
            raise AmbiguousBuyError(
                f"compra pode ter sido enviada para {key}; reconcilie a conta DEMO antes de retomar"
            )
    if len(completed) == len(plan) and not state.get("inflight"):
        state["status"] = "complete"
        checkpoint(state, args.state)
        print_summary(write_stats(args, records), args)
        return

    client = DerivClient(app_id=APP_ID, api_token=TOKEN, use_demo=True)
    try:
        await client.connect()
        if not await validate_demo_account(client):
            raise D90ConfigurationError("a conta conectada não foi confirmada como DEMO")
        print("=" * 100)
        print("D90 — Long-Duration Early-Sell A/B Validation")
        print(f"Symbol: {SYMBOL} | Durations: {durations} | pairs/duration: {args.pairs}")
        print(f"Threshold: {args.threshold}x buy | Stake: ${STAKE:.2f} | Poll: {args.poll_interval}s")
        print(f"Resume: {len(completed)}/{len(plan)} braços já concluídos")
        print("LIVE DEMO: buy/sell requests enabled")
        print("=" * 100)

        def persist_monitoring(record):
            state["inflight"] = {"phase": "monitoring", "record": record}
            state["status"] = "running"
            checkpoint(state, args.state)

        def finalize(record):
            key = arm_key(record)
            if key in completed:
                raise D90ConfigurationError(f"tentativa de gravar braço já concluído: {key}")
            append_jsonl(args.output, record)
            records.append(record)
            completed[key] = record
            state["inflight"] = None
            state["status"] = "running"
            checkpoint(state, args.state)
            write_stats(args, records)
            print(
                f"{record['duration']}{record['duration_unit']} pair={record['pair_id']} "
                f"{record['group']} {record['contract_type']}: "
                f"terminal={record.get('terminal')} profit={record.get('strategy_profit')}",
                flush=True,
            )

        if state.get("inflight"):
            _, saved_record, _ = validate_inflight(state["inflight"], plan)
            record = dict(saved_record)
            print(
                f"Retomando contrato {record['contract_id']} para pair={record['pair_id']} "
                f"{record['group']}",
                flush=True,
            )
            if record["group"] == "sell":
                record = await monitor_sell_arm(client, record, args.poll_interval, persist_monitoring)
            else:
                record = await monitor_hold_arm(client, record, args.poll_interval)
            finalize(record)
            await asyncio.sleep(args.cooldown)

        for key, arm in plan.items():
            if key in completed:
                continue
            state["inflight"] = {"phase": "buying", "arm": arm, "started_at": now_utc()}
            state["status"] = "running"
            checkpoint(state, args.state)
            try:
                if arm["group"] == "sell":
                    record = await run_sell_arm(
                        client,
                        arm["pair_id"],
                        arm["contract_type"],
                        arm["duration"],
                        arm["duration_unit"],
                        args.threshold,
                        args.poll_interval,
                        persist_monitoring,
                    )
                else:
                    record = await run_hold_arm(
                        client,
                        arm["pair_id"],
                        arm["contract_type"],
                        arm["duration"],
                        arm["duration_unit"],
                        args.poll_interval,
                        persist_monitoring,
                    )
            except AmbiguousBuyError:
                state["status"] = "manual_reconciliation_required"
                checkpoint(state, args.state)
                raise
            if record.get("error"):
                state["inflight"] = None
                state["status"] = "stopped_on_safe_prebuy_error"
                state["last_error"] = record["error"]
                checkpoint(state, args.state)
                raise D90ConfigurationError(f"braço {key} não iniciou: {record['error']}")
            finalize(record)
            await asyncio.sleep(args.cooldown)

        state["inflight"] = None
        state["status"] = "complete"
        checkpoint(state, args.state)
    finally:
        await client.disconnect()

    print_summary(write_stats(args, records), args)


async def run_live(args):
    lock_handle = acquire_run_lock(args.state)
    try:
        await run_live_locked(args)
    finally:
        fcntl.flock(lock_handle.fileno(), fcntl.LOCK_UN)
        lock_handle.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--durations", default=",".join(DEFAULT_DURATIONS))
    parser.add_argument("--pairs", type=int, default=20)
    parser.add_argument("--threshold", type=float, default=1.50)
    parser.add_argument("--poll-interval", type=float, default=2.0)
    parser.add_argument("--cooldown", type=float, default=1.0)
    parser.add_argument("--output", default=DEFAULT_RESULTS)
    parser.add_argument("--stats", default=DEFAULT_STATS)
    parser.add_argument("--state", default=DEFAULT_STATE)
    parser.add_argument("--live", action="store_true")
    args = parser.parse_args()
    args.output = os.path.abspath(args.output)
    args.stats = os.path.abspath(args.stats)
    args.state = os.path.abspath(args.state)
    try:
        durations = [parse_duration(item) for item in parse_csv(args.durations)]
        if not durations or args.pairs < 1 or args.threshold <= 0 or args.poll_interval <= 0 or args.cooldown < 0:
            raise D90ConfigurationError("durations, pairs, threshold e intervalos devem ser positivos")
        if not args.live:
            inspect_resume(args, durations)
            return 0
        if not APP_ID or not TOKEN:
            raise D90ConfigurationError("DERIV_APP_ID ou DERIV_API_TOKEN não encontrado")
        asyncio.run(run_live(args))
        return 0
    except (AmbiguousBuyError, D90ConfigurationError, ValueError) as error:
        print(f"ERRO: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
