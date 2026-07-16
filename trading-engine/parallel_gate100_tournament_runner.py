import argparse
import asyncio
import json
import logging
import os
import statistics
import time
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

from deriv_client import DerivClient
from strategy_tournament_runner import DISCOVERY_MODEL_SPECS, MODEL_SPECS


DEFAULT_GATE100_MODEL_IDS = [
    "reversal_3tick_minmove020_1HZ10V",
    "mean_revert_5tick_dev025",
    "reversal_2tick_R100",
    "reversal_4tick_minmove020_1HZ10V",
    "reversal_3tick_minmove030_1HZ25V",
    "mean_revert_5tick_dev025_1HZ25V",
    "reversal_3tick_minmove020_guard_1HZ10V_w3",
    "reversal_3tick_minmove020_guard_v2_1HZ10V_w4",
]

GATE100_SOURCE_SNAPSHOT = {
    "reversal_3tick_minmove020_1HZ10V": {
        "source": "JOB-20260702-005",
        "gate100_status": "passed_100",
        "source_trades": 1000,
        "source_pnl": 23.36,
        "source_max_drawdown": -23.08,
    },
    "mean_revert_5tick_dev025": {
        "source": "JOB-20260702-005",
        "gate100_status": "target100_failed_recovery",
        "source_trades": 96,
        "source_pnl": -5.76,
        "source_max_drawdown": -14.44,
    },
    "reversal_2tick_R100": {
        "source": "JOB-20260702-005",
        "gate100_status": "target100_failed_recovery",
        "source_trades": 92,
        "source_pnl": -7.52,
        "source_max_drawdown": -14.04,
    },
    "reversal_4tick_minmove020_1HZ10V": {
        "source": "JOB-20260703-012-DISCOVERY-A2-W3-PRIORITY",
        "gate100_status": "target100_failed_recovery",
        "source_trades": 91,
        "source_pnl": -8.44,
        "source_max_drawdown": -13.96,
    },
    "reversal_3tick_minmove030_1HZ25V": {
        "source": "JOB-20260703-012-DISCOVERY-A2-W3-PRIORITY",
        "gate100_status": "target100_failed_recovery",
        "source_trades": 95,
        "source_pnl": -4.76,
        "source_max_drawdown": -13.0,
    },
    "mean_revert_5tick_dev025_1HZ25V": {
        "source": "JOB-20260703-012-DISCOVERY-A2-W3-PRIORITY",
        "gate100_status": "post100_failed",
        "source_trades": 119,
        "source_pnl": -51.71,
        "source_max_drawdown": -64.79,
    },
    "reversal_3tick_minmove020_guard_1HZ10V_w3": {
        "source": "JOB-20260703-012-DISCOVERY-A2-W3-PRIORITY",
        "gate100_status": "target100_drawdown_failed_positive_pnl",
        "source_trades": 38,
        "source_pnl": 62.29,
        "source_max_drawdown": -50.0,
    },
    "reversal_3tick_minmove020_guard_v2_1HZ10V_w4": {
        "source": "JOB-20260703-013-DISCOVERY-A2-W4",
        "gate100_status": "target100_drawdown_failed",
        "source_trades": 38,
        "source_pnl": -14.63,
        "source_max_drawdown": -43.08,
    },
}


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def configure_logging(log_path):
    logger = logging.getLogger("GATE100_PARALLEL")
    logger.setLevel(logging.INFO)
    logger.handlers.clear()
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
    stream = logging.StreamHandler()
    stream.setFormatter(fmt)
    logger.addHandler(stream)
    if log_path:
        file_handler = logging.FileHandler(log_path, encoding="utf-8")
        file_handler.setFormatter(fmt)
        logger.addHandler(file_handler)
    return logger


def all_specs_by_id():
    specs = {}
    for spec in MODEL_SPECS + DISCOVERY_MODEL_SPECS:
        specs[spec["id"]] = dict(spec)
    return specs


def empty_parallel_model(spec):
    source = GATE100_SOURCE_SNAPSHOT.get(spec["id"], {})
    return {
        "id": spec["id"],
        "kind": spec["kind"],
        "symbol": spec["symbol"],
        "duration_ticks": spec.get("duration_ticks", 1),
        "status": "collecting",
        "phase": "pnl500_parallel",
        "started_at": utc_now(),
        "stopped_at": None,
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
        "loss_streak": 0,
        "blocked_until_ts": 0.0,
        "blocked_reason": None,
        "in_trade": False,
        "last_trade_at": 0.0,
        "last_signal": None,
        "last_settlement": None,
        "source_gate100": source,
    }


class ParallelGate100Tournament:
    def __init__(self, args, logger):
        self.args = args
        self.logger = logger
        self.specs_by_id = all_specs_by_id()
        requested = [item.strip() for item in (args.model_ids or ",".join(DEFAULT_GATE100_MODEL_IDS)).split(",") if item.strip()]
        missing = [model_id for model_id in requested if model_id not in self.specs_by_id]
        if missing:
            raise RuntimeError(f"unknown model ids: {missing}")
        self.model_ids = requested
        self.model_specs = [self.specs_by_id[model_id] for model_id in self.model_ids]
        self.ticks_by_symbol = {spec["symbol"]: [] for spec in self.model_specs}
        self.open_contracts = 0
        self.done = asyncio.Event()
        self.state_path = Path(args.state_json)
        self.events_path = Path(args.events_jsonl)
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self.events_path.parent.mkdir(parents=True, exist_ok=True)
        self.state = self.load_or_init_state()

    def load_or_init_state(self):
        if self.state_path.exists() and not self.args.reset:
            state = json.loads(self.state_path.read_text(encoding="utf-8"))
            state.setdefault("runtime", {}).update(self.runtime_payload())
            state["status"] = "collecting"
            self.write_state(state)
            return state

        models = [empty_parallel_model(spec) for spec in self.model_specs]
        state = {
            "goal": "Parallel tournament among gate100-reached models until a model reaches +$500 demo PnL consistently.",
            "job_id": self.args.job_id,
            "status": "collecting",
            "mode": "parallel_gate100_pnl500",
            "started_at": utc_now(),
            "updated_at": utc_now(),
            "real_money_allowed": False,
            "target_pnl": self.args.target_pnl,
            "stake_override": self.args.stake_override,
            "model_kill_loss": self.args.model_kill_loss,
            "model_drawdown_stop": self.args.model_drawdown_stop,
            "global_kill_loss": self.args.global_kill_loss,
            "max_concurrent_open_contracts": self.args.max_concurrent_open_contracts,
            "selection_rule": "models promoted to target100 or passed_100 in prior Deriv demo tournaments",
            "selected_model_ids": self.model_ids,
            "models": models,
            "global": {
                "pnl": 0.0,
                "peak_pnl": 0.0,
                "max_drawdown": 0.0,
                "trades": 0,
                "wins": 0,
                "losses": 0,
                "open_contracts": 0,
                "winner_model_id": None,
            },
            "last_event": None,
            "runtime": self.runtime_payload(),
        }
        self.write_state(state)
        return state

    def runtime_payload(self):
        return {
            "pid": os.getpid(),
            "log_path": str(Path(self.args.log_path).resolve()),
            "events_jsonl": str(self.events_path.resolve()),
            "state_json": str(self.state_path.resolve()),
            "app_id_env": self.args.app_id_env,
            "api_token_env": self.args.api_token_env,
        }

    def write_state(self, state=None):
        target = state if state is not None else self.state
        target["updated_at"] = utc_now()
        target["leaderboard"] = self.leaderboard(target)
        self.state_path.write_text(json.dumps(target, indent=2, sort_keys=True), encoding="utf-8")

    def log_event(self, event, **fields):
        row = {"ts": utc_now(), "event": event, "job_id": self.args.job_id, **fields}
        with self.events_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, sort_keys=True) + "\n")
        self.state["last_event"] = row
        self.write_state()

    def leaderboard(self, state=None):
        state = state or self.state
        rows = []
        for model in state.get("models", []):
            trades = int(model.get("trades", 0) or 0)
            rows.append(
                {
                    "model_id": model["id"],
                    "status": model.get("status"),
                    "trades": trades,
                    "wins": model.get("wins", 0),
                    "losses": model.get("losses", 0),
                    "wr": round((model.get("wins", 0) / trades), 4) if trades else None,
                    "pnl": model.get("pnl", 0.0),
                    "peak_pnl": model.get("peak_pnl", 0.0),
                    "max_drawdown": model.get("max_drawdown", 0.0),
                    "blocked_reason": model.get("blocked_reason"),
                }
            )
        return sorted(rows, key=lambda row: (float(row["pnl"]), int(row["trades"])), reverse=True)

    def model_by_id(self, model_id):
        return next(model for model in self.state["models"] if model["id"] == model_id)

    def spec_for(self, model_id):
        return self.specs_by_id[model_id]

    def stake_for_spec(self, spec):
        if self.args.stake_override > 0:
            base = float(self.args.stake_override)
        else:
            base = float(spec.get("stake", 1.0))
        return round(base * float(spec.get("stake_multiplier", 1.0)), 2)

    def signal_from_rule(self, ticks, rule):
        if rule["kind"] in ("trend", "reversal"):
            streak = int(rule["streak"])
            if len(ticks) < streak + 1:
                return None
            recent = ticks[-(streak + 1):]
            deltas = [recent[i + 1]["quote"] - recent[i]["quote"] for i in range(streak)]
            if all(delta > 0 for delta in deltas):
                direction = "UP"
            elif all(delta < 0 for delta in deltas):
                direction = "DOWN"
            else:
                return None
            move = recent[-1]["quote"] - recent[0]["quote"]
            if abs(move) < float(rule.get("min_move", 0.0)):
                return None
            if rule["kind"] == "reversal":
                direction = "DOWN" if direction == "UP" else "UP"
            signal = {
                "direction": direction,
                "contract_type": "CALL" if direction == "UP" else "PUT",
                "move": round(move, 5),
                "from_quote": recent[0]["quote"],
                "to_quote": recent[-1]["quote"],
                "rule_kind": rule["kind"],
                "rule_family": rule.get("family", rule["kind"]),
            }
            return self.apply_rule_contract_filter(rule, signal)

        if rule["kind"] == "mean_revert":
            window = int(rule["window"])
            if len(ticks) < window:
                return None
            recent = ticks[-window:]
            mean_quote = statistics.mean(item["quote"] for item in recent[:-1])
            last_quote = recent[-1]["quote"]
            diff = last_quote - mean_quote
            if abs(diff) < float(rule.get("min_move", 0.0)):
                return None
            direction = "DOWN" if diff > 0 else "UP"
            signal = {
                "direction": direction,
                "contract_type": "CALL" if direction == "UP" else "PUT",
                "move": round(diff, 5),
                "from_quote": round(mean_quote, 5),
                "to_quote": last_quote,
                "rule_kind": rule["kind"],
                "rule_family": rule.get("family", rule["kind"]),
            }
            return self.apply_rule_contract_filter(rule, signal)
        return None

    def apply_rule_contract_filter(self, rule, signal):
        allowed_contracts = rule.get("allowed_contract_types")
        if allowed_contracts and signal.get("contract_type") not in set(allowed_contracts):
            return None
        return signal

    def signal_for_model(self, model, spec):
        if spec["kind"] == "adaptive_agent":
            return None
        ticks = self.ticks_by_symbol[spec["symbol"]]
        signal = self.signal_from_rule(ticks, spec)
        if not signal:
            return None
        allowed_contracts = spec.get("allowed_contract_types")
        if allowed_contracts and signal.get("contract_type") not in set(allowed_contracts):
            return None
        blocked_until = float(model.get("blocked_until_ts", 0.0) or 0.0)
        if blocked_until > time.time():
            return None
        return signal

    def active_models_for_symbol(self, symbol):
        for model in self.state["models"]:
            if model.get("status") != "collecting":
                continue
            spec = self.spec_for(model["id"])
            if spec["symbol"] == symbol:
                yield model, spec

    async def on_tick(self, message):
        tick = message.get("tick", {})
        symbol = tick.get("symbol")
        if not symbol:
            return
        quote = float(tick.get("quote"))
        ticks = self.ticks_by_symbol.setdefault(symbol, [])
        ticks.append({"quote": quote, "epoch": tick.get("epoch"), "seen_at": time.time()})
        self.ticks_by_symbol[symbol] = ticks[-50:]

        for model, spec in list(self.active_models_for_symbol(symbol)):
            if model.get("in_trade"):
                continue
            if self.open_contracts >= self.args.max_concurrent_open_contracts:
                break
            if time.time() - float(model.get("last_trade_at", 0.0) or 0.0) < float(spec["cooldown_seconds"]):
                continue
            signal = self.signal_for_model(model, spec)
            if not signal:
                continue
            model["in_trade"] = True
            model["last_signal"] = {"ts": utc_now(), **signal}
            self.open_contracts += 1
            self.state["global"]["open_contracts"] = self.open_contracts
            self.write_state()
            asyncio.create_task(self.execute_trade(model["id"], spec, signal))

    async def execute_trade(self, model_id, spec, signal):
        start = time.time()
        model = self.model_by_id(model_id)
        trade_no = int(model["trades"]) + 1
        stake = self.stake_for_spec(spec)
        model["last_trade_at"] = time.time()
        self.logger.info(
            "SIGNAL model=%s trade=%s contract=%s stake=%.2f move=%.5f",
            model_id,
            trade_no,
            signal["contract_type"],
            stake,
            signal["move"],
        )
        self.log_event("signal", model_id=model_id, trade_no=trade_no, phase=model["phase"], stake=stake, **signal)
        try:
            response = await self.client.buy_direct(
                contract_type=signal["contract_type"],
                stake=stake,
                symbol=spec["symbol"],
                duration=spec.get("duration_ticks", 1),
                duration_unit="t",
            )
            latency_ms = round((time.time() - start) * 1000, 3)
            if "error" in response:
                model["rejects"] += 1
                model["in_trade"] = False
                self.log_event("reject", model_id=model_id, trade_no=trade_no, latency_ms=latency_ms, error=response["error"])
                self.logger.warning("REJECT model=%s trade=%s error=%s", model_id, trade_no, response["error"])
                return
            contract_id = response["buy"]["contract_id"]
            model["latencies_ms"].append(latency_ms)
            self.log_event(
                "buy",
                model_id=model_id,
                trade_no=trade_no,
                contract_id=contract_id,
                latency_ms=latency_ms,
                buy_price=float(response["buy"]["buy_price"]),
                stake=stake,
                **signal,
            )
            await self.wait_settlement(model_id, trade_no, contract_id, signal)
        except Exception as exc:
            model["errors"] += 1
            self.logger.exception("ERROR model=%s trade=%s %s", model_id, trade_no, exc)
            self.log_event("error", model_id=model_id, trade_no=trade_no, error=str(exc))
        finally:
            model["in_trade"] = False
            self.open_contracts = max(0, self.open_contracts - 1)
            self.state["global"]["open_contracts"] = self.open_contracts
            self.write_state()

    async def wait_settlement(self, model_id, trade_no, contract_id, signal):
        deadline = time.time() + self.args.settlement_timeout_seconds
        while time.time() < deadline:
            response = await self.client.send_request({"proposal_open_contract": 1, "contract_id": contract_id})
            contract = response.get("proposal_open_contract", {})
            if contract.get("is_sold"):
                profit = float(contract.get("profit", 0.0))
                model = self.model_by_id(model_id)
                self.update_after_settlement(model, profit)
                model["last_settlement"] = {"ts": utc_now(), "trade_no": trade_no, "contract_id": contract_id, "profit": profit}
                self.log_event(
                    "settled",
                    model_id=model_id,
                    trade_no=trade_no,
                    contract_id=contract_id,
                    profit=profit,
                    pnl=model["pnl"],
                    trades=model["trades"],
                    wins=model["wins"],
                    losses=model["losses"],
                    global_pnl=self.state["global"]["pnl"],
                    **signal,
                )
                self.logger.info("SETTLED model=%s trade=%s profit=%.2f pnl=%.2f", model_id, trade_no, profit, model["pnl"])
                return
            await asyncio.sleep(self.args.poll_seconds)
        model = self.model_by_id(model_id)
        model["errors"] += 1
        self.log_event("settlement_timeout", model_id=model_id, trade_no=trade_no, contract_id=contract_id)

    def update_after_settlement(self, model, profit):
        model["trades"] += 1
        if profit > 0:
            model["wins"] += 1
            model["loss_streak"] = 0
        elif profit < 0:
            model["losses"] += 1
            model["loss_streak"] = int(model.get("loss_streak", 0) or 0) + 1
        model["pnl"] = round(float(model.get("pnl", 0.0)) + profit, 4)
        model["peak_pnl"] = max(float(model.get("peak_pnl", 0.0)), model["pnl"])
        dd = model["pnl"] - model["peak_pnl"]
        model["max_drawdown"] = min(float(model.get("max_drawdown", 0.0)), round(dd, 4))
        model.setdefault("recent_profits", []).append(round(profit, 4))
        model["recent_profits"] = model["recent_profits"][-100:]

        g = self.state["global"]
        g["trades"] += 1
        if profit > 0:
            g["wins"] += 1
        elif profit < 0:
            g["losses"] += 1
        g["pnl"] = round(float(g.get("pnl", 0.0)) + profit, 4)
        g["peak_pnl"] = max(float(g.get("peak_pnl", 0.0)), g["pnl"])
        g["max_drawdown"] = min(float(g.get("max_drawdown", 0.0)), round(g["pnl"] - g["peak_pnl"], 4))

        self.apply_guards(model)
        self.check_stops(model)
        self.write_state()

    def apply_guards(self, model):
        spec = self.spec_for(model["id"])
        now = time.time()
        block_guard = spec.get("block_guard")
        if block_guard:
            recent = model.get("recent_profits", [])
            window = int(block_guard.get("window", 0))
            pause_seconds = float(block_guard.get("pause_seconds", 0))
            if window > 0 and pause_seconds > 0 and len(recent) >= window:
                block_pnl = round(sum(recent[-window:]), 4)
                reason = None
                if "max_loss" in block_guard and block_pnl <= float(block_guard["max_loss"]):
                    reason = f"recent_loss_block_{window}_pnl_{block_pnl}"
                if "max_gain" in block_guard and block_pnl >= float(block_guard["max_gain"]):
                    reason = f"recent_hot_block_{window}_pnl_{block_pnl}"
                if reason:
                    model["blocked_until_ts"] = now + pause_seconds
                    model["blocked_reason"] = reason
                    self.log_event("block_guard_pause", model_id=model["id"], reason=reason, pause_seconds=pause_seconds)

        loss_guard = spec.get("loss_streak_pause")
        if loss_guard:
            required = int(loss_guard.get("losses", 0))
            pause_seconds = float(loss_guard.get("pause_seconds", 0))
            if required > 0 and pause_seconds > 0 and int(model.get("loss_streak", 0) or 0) >= required:
                reason = f"loss_streak_{required}"
                model["blocked_until_ts"] = max(float(model.get("blocked_until_ts", 0.0) or 0.0), now + pause_seconds)
                model["blocked_reason"] = reason
                self.log_event("loss_streak_pause", model_id=model["id"], reason=reason, pause_seconds=pause_seconds)

        trailing = spec.get("target100_trailing_pause")
        if trailing:
            min_trades = int(trailing.get("min_trades", 0))
            pause_seconds = float(trailing.get("pause_seconds", 0))
            drawdown_from_peak = abs(float(trailing.get("drawdown_from_peak", 0)))
            retrace = float(model.get("pnl", 0.0)) - float(model.get("peak_pnl", 0.0))
            if model["trades"] >= min_trades and drawdown_from_peak > 0 and pause_seconds > 0 and abs(retrace) >= drawdown_from_peak:
                reason = f"target_pnl500_peak_retrace_{round(abs(retrace), 4)}"
                model["blocked_until_ts"] = max(float(model.get("blocked_until_ts", 0.0) or 0.0), now + pause_seconds)
                model["blocked_reason"] = reason
                self.log_event("target_pnl_trailing_pause", model_id=model["id"], reason=reason, pause_seconds=pause_seconds)

    def check_stops(self, model):
        if model.get("status") != "collecting":
            return
        if float(model.get("pnl", 0.0)) >= float(self.args.target_pnl):
            model["status"] = "target_pnl_reached"
            model["stopped_at"] = utc_now()
            self.state["global"]["winner_model_id"] = model["id"]
            self.log_event("target_pnl_reached", model_id=model["id"], trades=model["trades"], pnl=model["pnl"], target_pnl=self.args.target_pnl)
            if self.args.stop_on_first_winner:
                self.state["status"] = "target_pnl_reached"
                self.done.set()
            return
        if float(model.get("pnl", 0.0)) <= -abs(float(self.args.model_kill_loss)):
            self.stop_model(model, "model_kill_loss")
            return
        if abs(float(model.get("max_drawdown", 0.0))) >= abs(float(self.args.model_drawdown_stop)):
            self.stop_model(model, "model_drawdown_stop")
            return
        if self.args.global_kill_loss > 0 and self.state["global"]["pnl"] <= -abs(float(self.args.global_kill_loss)):
            self.state["status"] = "global_kill_loss"
            self.log_event("global_kill_loss", pnl=self.state["global"]["pnl"], limit=self.args.global_kill_loss)
            self.done.set()

    def stop_model(self, model, reason):
        model["status"] = "backlog"
        model["stopped_at"] = utc_now()
        model["pivot_reason"] = reason
        self.log_event("pivot", model_id=model["id"], reason=reason, trades=model["trades"], pnl=model["pnl"])
        if not any(item.get("status") == "collecting" for item in self.state["models"]):
            self.state["status"] = "exhausted_models"
            self.done.set()

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
        for model in self.state["models"]:
            if model.get("status") == "collecting" and not model.get("started_at"):
                model["started_at"] = utc_now()
            self.log_event(
                "parallel_model_start",
                model_id=model["id"],
                symbol=model["symbol"],
                source_gate100=model.get("source_gate100"),
                stake=self.stake_for_spec(self.spec_for(model["id"])),
            )
        symbols = sorted({spec["symbol"] for spec in self.model_specs})
        for symbol in symbols:
            await self.client.subscribe_ticks(symbol, self.on_tick)
            await asyncio.sleep(0.25)
        self.log_event("parallel_tournament_started", model_ids=self.model_ids, symbols=symbols)
        try:
            await asyncio.wait_for(self.done.wait(), timeout=self.args.max_runtime_seconds)
        except asyncio.TimeoutError:
            self.state["status"] = "stopped_runtime_timeout"
            self.log_event("runtime_timeout", seconds=self.args.max_runtime_seconds)
        finally:
            self.write_state()
            await self.client.disconnect()


def parse_args():
    parser = argparse.ArgumentParser(description="Parallel Deriv demo tournament for models that reached gate100.")
    parser.add_argument("--job-id", default="JOB-20260704-009-GATE100-PARALLEL-PNL500-CLOUD")
    parser.add_argument("--state-json", default="strategy_gate100_parallel_pnl500_state.json")
    parser.add_argument("--events-jsonl", default="strategy_gate100_parallel_pnl500_events.jsonl")
    parser.add_argument("--log-path", default="strategy_gate100_parallel_pnl500.log")
    parser.add_argument("--reset", action="store_true")
    parser.add_argument("--model-ids", default="")
    parser.add_argument("--target-pnl", type=float, default=500.0)
    parser.add_argument("--stake-override", type=float, default=10.0)
    parser.add_argument("--model-kill-loss", type=float, default=40.0)
    parser.add_argument("--model-drawdown-stop", type=float, default=40.0)
    parser.add_argument("--global-kill-loss", type=float, default=240.0)
    parser.add_argument("--max-concurrent-open-contracts", type=int, default=8)
    parser.add_argument("--max-runtime-seconds", type=float, default=86400)
    parser.add_argument("--poll-seconds", type=float, default=0.25)
    parser.add_argument("--settlement-timeout-seconds", type=float, default=25)
    parser.add_argument("--auth-retries", type=int, default=8)
    parser.add_argument("--app-id-env", default="DERIV_APP_ID_2")
    parser.add_argument("--api-token-env", default="DERIV_API_TOKEN_2")
    parser.add_argument("--stop-on-first-winner", action="store_true")
    return parser.parse_args()


def main():
    args = parse_args()
    logger = configure_logging(args.log_path)
    runner = ParallelGate100Tournament(args, logger)
    asyncio.run(runner.run())


if __name__ == "__main__":
    main()
