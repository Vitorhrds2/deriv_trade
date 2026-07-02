import argparse
import asyncio
import json
import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

from deriv_client import DerivClient


DEFAULT_JOB_ID = "JOB-20260702-002"


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def configure_logging(log_path):
    logger = logging.getLogger("DEMO_TICK_STRATEGY")
    logger.setLevel(logging.INFO)
    logger.handlers.clear()

    formatter = logging.Formatter("%(asctime)s - DEMO_TICK_STRATEGY:%(levelname)s:%(message)s")
    file_handler = logging.FileHandler(log_path, encoding="utf-8")
    file_handler.setFormatter(formatter)
    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)

    logger.addHandler(file_handler)
    logger.addHandler(stream_handler)
    return logger


class DemoTickStrategy:
    def __init__(self, args, logger):
        self.args = args
        self.logger = logger
        self.client = None
        self.ticks = []
        self.in_trade = False
        self.closed_trades = 0
        self.rejects = 0
        self.errors = 0
        self.pnl = 0.0
        self.last_trade_at = 0.0
        self.done = asyncio.Event()
        self.ledger_path = Path(args.ledger_jsonl)
        self.ledger_path.parent.mkdir(parents=True, exist_ok=True)

    def log_event(self, event, **fields):
        row = {
            "ts": utc_now(),
            "job_id": self.args.job_id,
            "event": event,
            **fields,
        }
        with self.ledger_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, sort_keys=True) + "\n")

    def can_trade(self):
        if self.in_trade:
            return False
        if self.closed_trades >= self.args.max_trades:
            self.logger.warning("STOP max_trades reached: %s", self.closed_trades)
            self.done.set()
            return False
        if self.pnl <= -abs(self.args.max_demo_loss):
            self.logger.warning("STOP max_demo_loss reached: pnl=%.2f", self.pnl)
            self.done.set()
            return False
        if time.time() - self.last_trade_at < self.args.cooldown_seconds:
            return False
        return True

    def signal_from_ticks(self):
        needed = self.args.signal_streak + 1
        if len(self.ticks) < needed:
            return None
        recent = self.ticks[-needed:]
        deltas = [recent[i]["quote"] - recent[i - 1]["quote"] for i in range(1, len(recent))]
        if all(delta > 0 for delta in deltas):
            direction = "UP"
        elif all(delta < 0 for delta in deltas):
            direction = "DOWN"
        else:
            return None
        total_move = recent[-1]["quote"] - recent[0]["quote"]
        if abs(total_move) < self.args.min_move:
            return None
        return {
            "direction": direction,
            "contract_type": "CALL" if direction == "UP" else "PUT",
            "streak": self.args.signal_streak,
            "move": total_move,
            "from_quote": recent[0]["quote"],
            "to_quote": recent[-1]["quote"],
        }

    async def on_tick(self, message):
        tick = message.get("tick", {})
        quote = float(tick.get("quote"))
        epoch = tick.get("epoch")
        self.ticks.append({"quote": quote, "epoch": epoch, "seen_at": time.time()})
        self.ticks = self.ticks[-20:]
        self.logger.info(
            "TICK symbol=%s quote=%.5f trades=%s pnl=%.2f",
            self.args.symbol,
            quote,
            self.closed_trades,
            self.pnl,
        )
        if not self.can_trade():
            return
        signal = self.signal_from_ticks()
        if signal:
            self.in_trade = True
            asyncio.create_task(self.execute_trade(signal))

    async def execute_trade(self, signal):
        self.in_trade = True
        self.last_trade_at = time.time()
        start = time.time()
        trade_no = self.closed_trades + 1
        self.logger.info(
            "SIGNAL trade=%s direction=%s contract=%s streak=%s move=%.5f stake=%.2f duration=%st",
            trade_no,
            signal["direction"],
            signal["contract_type"],
            signal["streak"],
            signal["move"],
            self.args.stake,
            self.args.duration_ticks,
        )
        self.log_event("signal", trade_no=trade_no, **signal)
        try:
            response = await self.client.buy_direct(
                contract_type=signal["contract_type"],
                stake=self.args.stake,
                symbol=self.args.symbol,
                duration=self.args.duration_ticks,
                duration_unit="t",
            )
            latency_ms = round((time.time() - start) * 1000, 3)
            if "error" in response:
                self.rejects += 1
                error = response["error"]
                self.logger.warning(
                    "REJECT trade=%s code=%s message=%s latency_ms=%.1f",
                    trade_no,
                    error.get("code"),
                    error.get("message"),
                    latency_ms,
                )
                self.log_event("reject", trade_no=trade_no, latency_ms=latency_ms, error=error)
                return

            contract_id = response["buy"]["contract_id"]
            buy_price = float(response["buy"]["buy_price"])
            self.logger.info(
                "BUY trade=%s contract_id=%s buy_price=%.2f latency_ms=%.1f",
                trade_no,
                contract_id,
                buy_price,
                latency_ms,
            )
            self.log_event(
                "buy",
                trade_no=trade_no,
                contract_id=contract_id,
                buy_price=buy_price,
                latency_ms=latency_ms,
                **signal,
            )
            await self.wait_settlement(trade_no, contract_id, buy_price, signal)
        except Exception as exc:
            self.errors += 1
            self.logger.exception("ERROR trade=%s %s", trade_no, exc)
            self.log_event("error", trade_no=trade_no, error=str(exc))
        finally:
            self.in_trade = False

    async def wait_settlement(self, trade_no, contract_id, buy_price, signal):
        deadline = time.time() + self.args.settlement_timeout_seconds
        while time.time() < deadline:
            response = await self.client.send_request(
                {"proposal_open_contract": 1, "contract_id": contract_id}
            )
            contract = response.get("proposal_open_contract", {})
            if contract.get("is_sold"):
                profit = float(contract.get("profit", 0.0))
                sell_price = float(contract.get("sell_price", buy_price + profit))
                self.pnl += profit
                self.closed_trades += 1
                self.logger.info(
                    "SETTLED trade=%s contract_id=%s profit=%.2f sell_price=%.2f pnl=%.2f",
                    trade_no,
                    contract_id,
                    profit,
                    sell_price,
                    self.pnl,
                )
                self.log_event(
                    "settled",
                    trade_no=trade_no,
                    contract_id=contract_id,
                    profit=profit,
                    sell_price=sell_price,
                    pnl=self.pnl,
                    **signal,
                )
                if self.closed_trades >= self.args.max_trades:
                    self.done.set()
                if self.pnl <= -abs(self.args.max_demo_loss):
                    self.done.set()
                return
            await asyncio.sleep(self.args.poll_seconds)
        self.errors += 1
        self.logger.warning("SETTLEMENT_TIMEOUT trade=%s contract_id=%s", trade_no, contract_id)
        self.log_event("settlement_timeout", trade_no=trade_no, contract_id=contract_id)

    async def run(self):
        load_dotenv()
        self.client = DerivClient(
            app_id=os.getenv("DERIV_APP_ID"),
            api_token=os.getenv("DERIV_API_TOKEN"),
            use_demo=True,
        )
        for attempt in range(1, self.args.auth_retries + 1):
            try:
                await self.client.connect()
                break
            except Exception as exc:
                self.errors += 1
                self.logger.warning(
                    "AUTH_RETRY attempt=%s/%s error=%s",
                    attempt,
                    self.args.auth_retries,
                    exc,
                )
                self.log_event("auth_retry", attempt=attempt, error=str(exc))
                if attempt >= self.args.auth_retries:
                    self.log_event("auth_failed", final_tag="needs_documentation")
                    raise
                await asyncio.sleep(min(2 * attempt, 20))
        account_id = str(self.client.account_id or "")
        if not account_id.startswith("DOT"):
            self.logger.critical("ABORT non-demo account: %s", account_id or "unknown")
            self.log_event("abort_non_demo", account_id_prefix=account_id[:3])
            await self.client.disconnect()
            return

        self.logger.info(
            "START job=%s symbol=%s account_prefix=%s stake=%.2f max_trades=%s max_demo_loss=%.2f",
            self.args.job_id,
            self.args.symbol,
            account_id[:3],
            self.args.stake,
            self.args.max_trades,
            self.args.max_demo_loss,
        )
        self.log_event(
            "start",
            account_id_prefix=account_id[:3],
            symbol=self.args.symbol,
            stake=self.args.stake,
            max_trades=self.args.max_trades,
            max_demo_loss=self.args.max_demo_loss,
            real_money_allowed=False,
        )
        await self.client.subscribe_ticks(self.args.symbol, self.on_tick)
        try:
            await asyncio.wait_for(self.done.wait(), timeout=self.args.max_runtime_seconds)
        except asyncio.TimeoutError:
            self.logger.info("STOP max_runtime reached")
        finally:
            self.log_event(
                "stop",
                trades=self.closed_trades,
                rejects=self.rejects,
                errors=self.errors,
                pnl=round(self.pnl, 4),
                final_tag="needs_documentation",
            )
            await self.client.disconnect()


def parse_args():
    parser = argparse.ArgumentParser(description="Immediate Deriv demo tick strategy runner.")
    parser.add_argument("--job-id", default=os.getenv("JOB_ID", DEFAULT_JOB_ID))
    parser.add_argument("--symbol", default=os.getenv("DEMO_TICK_SYMBOL", "1HZ100V"))
    parser.add_argument("--stake", type=float, default=float(os.getenv("DEMO_TICK_STAKE", "1")))
    parser.add_argument("--duration-ticks", type=int, default=int(os.getenv("DEMO_TICK_DURATION", "1")))
    parser.add_argument("--signal-streak", type=int, default=int(os.getenv("DEMO_TICK_SIGNAL_STREAK", "2")))
    parser.add_argument("--min-move", type=float, default=float(os.getenv("DEMO_TICK_MIN_MOVE", "0")))
    parser.add_argument("--max-trades", type=int, default=int(os.getenv("DEMO_TICK_MAX_TRADES", "5")))
    parser.add_argument("--max-demo-loss", type=float, default=float(os.getenv("DEMO_TICK_MAX_DEMO_LOSS", "10")))
    parser.add_argument("--cooldown-seconds", type=float, default=float(os.getenv("DEMO_TICK_COOLDOWN_SECONDS", "2")))
    parser.add_argument("--poll-seconds", type=float, default=0.25)
    parser.add_argument("--settlement-timeout-seconds", type=float, default=20)
    parser.add_argument("--auth-retries", type=int, default=int(os.getenv("DEMO_TICK_AUTH_RETRIES", "8")))
    parser.add_argument("--max-runtime-seconds", type=float, default=float(os.getenv("DEMO_TICK_MAX_RUNTIME_SECONDS", "900")))
    parser.add_argument("--log-path", default=os.getenv("DEMO_TICK_LOG_PATH", "demo_tick_strategy.log"))
    parser.add_argument(
        "--ledger-jsonl",
        default=os.getenv("DEMO_TICK_LEDGER_JSONL", "demo_tick_strategy_trades.jsonl"),
    )
    return parser.parse_args()


def main():
    args = parse_args()
    logger = configure_logging(args.log_path)
    runner = DemoTickStrategy(args, logger)
    asyncio.run(runner.run())


if __name__ == "__main__":
    main()
