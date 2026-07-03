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
        self.ticks_by_symbol = {spec["symbol"]: [] for spec in MODEL_SPECS}
        self.last_trade_at = 0.0
        self.in_trade = False
        self.done = asyncio.Event()
        self.state_path = Path(args.state_json)
        self.events_path = Path(args.events_jsonl)
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self.events_path.parent.mkdir(parents=True, exist_ok=True)
        self.state = self.load_or_init_state()

    def load_or_init_state(self):
        if self.state_path.exists() and not self.args.reset:
            state = json.loads(self.state_path.read_text(encoding="utf-8"))
            self.reconcile_model_specs(state)
            self.refresh_runtime_state(state)
            if self.args.continue_model_id:
                self.prepare_model_continuation(state, self.args.continue_model_id)
            self.write_state(state)
            return state

        models = [empty_model_state(spec) for spec in MODEL_SPECS]
        state = {
            "goal": "PnL positivo apos 100 trades, com gate positivo em 30 trades",
            "status": "collecting",
            "job_id": self.args.job_id,
            "started_at": utc_now(),
            "updated_at": utc_now(),
            "real_money_allowed": False,
            "gate_trades": self.args.gate_trades,
            "target_trades": self.args.target_trades,
            "healthy_drawdown_30": self.args.healthy_drawdown_30,
            "healthy_drawdown_100": self.args.healthy_drawdown_100,
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
            },
        }
        if self.args.seed_failed_ledger:
            self.seed_failed_trend_model(state, Path(self.args.seed_failed_ledger))
        self.write_state(state)
        return state

    def refresh_runtime_state(self, state):
        state["job_id"] = self.args.job_id
        state["gate_trades"] = self.args.gate_trades
        state["target_trades"] = self.args.target_trades
        state["healthy_drawdown_30"] = self.args.healthy_drawdown_30
        state["healthy_drawdown_100"] = self.args.healthy_drawdown_100
        state.setdefault("runtime", {}).update(
            {
                "pid": os.getpid(),
                "log_path": str(Path(self.args.log_path).resolve()),
                "events_jsonl": str(self.events_path.resolve()),
                "state_json": str(self.state_path.resolve()),
                "loaded_existing_state_at": utc_now(),
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

    def reconcile_model_specs(self, state):
        existing_ids = {model["id"] for model in state.get("models", [])}
        old_len = len(state.get("models", []))
        appended = []
        for spec in MODEL_SPECS:
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
        return next((spec for spec in MODEL_SPECS if spec["id"] == model["id"]), None)

    def start_current_model(self):
        model = self.current_model()
        if not model:
            self.state["status"] = "exhausted_models"
            self.write_state()
            self.done.set()
            return None
        if model["status"] == "pending":
            model["status"] = "collecting_gate30"
            model["phase"] = "gate30"
            model["started_at"] = utc_now()
            self.logger.info("MODEL_START id=%s phase=%s rationale=%s", model["id"], model["phase"], model["rationale"])
            self.log_event("model_start", model_id=model["id"], phase=model["phase"], rationale=model["rationale"])
        self.write_state()
        return model

    def pivot_current_model(self, reason):
        model = self.current_model()
        if not model:
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

    def max_possible_pnl_at_trade_count(self, model, target_trades):
        spec = self.current_spec()
        stake = float(spec.get("stake", 1.0)) if spec else 1.0
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

    def update_after_settlement(self, model, profit):
        model["trades"] += 1
        if profit > 0:
            model["wins"] += 1
        elif profit < 0:
            model["losses"] += 1
        model["pnl"] = round(model["pnl"] + profit, 4)
        model["peak_pnl"] = max(model["peak_pnl"], model["pnl"])
        dd = model["pnl"] - model["peak_pnl"]
        model["max_drawdown"] = min(model["max_drawdown"], round(dd, 4))
        self.write_state()

        if model["pnl"] <= -abs(self.args.model_kill_loss):
            self.pivot_current_model("model_kill_loss")
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
                model["status"] = "passed_100"
                model["stopped_at"] = utc_now()
                self.state["status"] = "goal_candidate_found"
                self.log_event("passed_100", model_id=model["id"], trades=model["trades"], pnl=model["pnl"])
                self.done.set()
            else:
                reason = "failed_100_pnl_nonpositive" if model["pnl"] <= 0 else "failed_100_drawdown"
                self.pivot_current_model(reason)

    def signal_for_model(self, model, spec):
        ticks = self.ticks_by_symbol[spec["symbol"]]
        if spec["kind"] in ("trend", "reversal"):
            needed = spec["streak"] + 1
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
            if abs(move) < spec.get("min_move", 0.0):
                return None
            if spec["kind"] == "reversal":
                direction = "DOWN" if direction == "UP" else "UP"
            return {
                "direction": direction,
                "contract_type": "CALL" if direction == "UP" else "PUT",
                "move": round(move, 5),
                "from_quote": recent[0]["quote"],
                "to_quote": recent[-1]["quote"],
            }

        if spec["kind"] == "mean_revert":
            window = spec["window"]
            if len(ticks) < window:
                return None
            recent = ticks[-window:]
            mean_quote = statistics.mean(item["quote"] for item in recent[:-1])
            last_quote = recent[-1]["quote"]
            diff = last_quote - mean_quote
            if abs(diff) < spec["min_move"]:
                return None
            direction = "DOWN" if diff > 0 else "UP"
            return {
                "direction": direction,
                "contract_type": "CALL" if direction == "UP" else "PUT",
                "move": round(diff, 5),
                "from_quote": round(mean_quote, 5),
                "to_quote": last_quote,
            }
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
        self.last_trade_at = time.time()
        self.logger.info("SIGNAL model=%s trade=%s contract=%s move=%.5f", model_id, trade_no, signal["contract_type"], signal["move"])
        self.log_event("signal", model_id=model_id, trade_no=trade_no, phase=model["phase"], **signal)
        try:
            response = await self.client.buy_direct(
                contract_type=signal["contract_type"],
                stake=spec["stake"],
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
            self.log_event("buy", model_id=model_id, trade_no=trade_no, contract_id=contract_id, latency_ms=latency_ms, buy_price=float(response["buy"]["buy_price"]), **signal)
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
                self.update_after_settlement(model, profit)
                self.log_event("settled", model_id=model_id, trade_no=trade_no, contract_id=contract_id, profit=profit, pnl=model["pnl"], trades=model["trades"], **signal)
                self.logger.info("SETTLED model=%s trade=%s profit=%.2f pnl=%.2f trades=%s", model_id, trade_no, profit, model["pnl"], model["trades"])
                return
            await asyncio.sleep(self.args.poll_seconds)
        model = next(item for item in self.state["models"] if item["id"] == model_id)
        model["errors"] += 1
        self.log_event("settlement_timeout", model_id=model_id, trade_no=trade_no, contract_id=contract_id)

    async def connect(self):
        load_dotenv(".env", override=True)
        self.client = DerivClient(app_id=os.getenv("DERIV_APP_ID"), api_token=os.getenv("DERIV_API_TOKEN"), use_demo=True)
        for attempt in range(1, self.args.auth_retries + 1):
            try:
                await self.client.connect()
                account_id = str(self.client.account_id or "")
                if not account_id.startswith("DOT"):
                    raise RuntimeError(f"non-demo account blocked: {account_id[:3]}")
                self.log_event("demo_authenticated", account_id_prefix=account_id[:3])
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
        symbols = sorted({spec["symbol"] for spec in MODEL_SPECS})
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
    parser.add_argument("--healthy-drawdown-30", type=float, default=12.0)
    parser.add_argument("--healthy-drawdown-100", type=float, default=20.0)
    parser.add_argument("--model-kill-loss", type=float, default=14.0)
    parser.add_argument("--max-win-return-ratio", type=float, default=0.92)
    parser.add_argument("--max-runtime-seconds", type=float, default=21600)
    parser.add_argument("--poll-seconds", type=float, default=0.25)
    parser.add_argument("--settlement-timeout-seconds", type=float, default=25)
    parser.add_argument("--auth-retries", type=int, default=8)
    parser.add_argument("--continue-model-id", default="")
    parser.add_argument("--allow-backlog-continuation", action="store_true")
    return parser.parse_args()


def main():
    args = parse_args()
    logger = configure_logging(args.log_path)
    runner = StrategyTournament(args, logger)
    asyncio.run(runner.run())


if __name__ == "__main__":
    main()
