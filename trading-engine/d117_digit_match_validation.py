import argparse
import asyncio
import gzip
import json
import os
import time
from pathlib import Path

import numpy as np

from deriv_client import DerivClient
from massive_edge_sweep import infer_pip, normalize_history, split_summary


HERE = Path(__file__).resolve().parent


def fit_model(prices, pip, train_fraction=0.6, confidence=0.02, minimum_context=100):
    digits = np.rint(np.asarray(prices, dtype=np.float64) / pip).astype(np.int64) % 10
    train_end = int(len(digits) * train_fraction)
    counts = np.zeros((100, 10), dtype=np.int64)
    indices = np.arange(1, train_end - 1, dtype=np.int64)
    contexts = digits[indices] + 10 * digits[indices - 1]
    np.add.at(counts, (contexts, digits[indices + 1]), 1)
    totals = counts.sum(axis=1)
    probabilities = np.divide(
        counts,
        totals[:, None],
        out=np.full_like(counts, 0.1, dtype=np.float64),
        where=totals[:, None] > 0,
    )
    actions = probabilities.argmax(axis=1)
    selected = (totals >= minimum_context) & (probabilities.max(axis=1) >= 0.1 + confidence)
    return {
        "digits": digits,
        "train_end": train_end,
        "counts": counts,
        "totals": totals,
        "probabilities": probabilities,
        "actions": actions,
        "selected": selected,
        "confidence": confidence,
        "minimum_context": minimum_context,
    }


def evaluate_model(model, start, end, lag, gross):
    digits = model["digits"]
    stop = min(end, len(digits) - lag)
    indices = np.arange(max(1, start), stop, dtype=np.int64)
    contexts = digits[indices] + 10 * digits[indices - 1]
    mask = model["selected"][contexts]
    targets = digits[indices + lag]
    actions = model["actions"][contexts]
    wins = int(((actions == targets) & mask).sum())
    summary = split_summary(wins, int(mask.sum()), gross)
    summary["lag"] = lag
    return summary


def digit_from_tick(tick, fallback_pip):
    quote = float(tick["quote"])
    pip_size = tick.get("pip_size")
    try:
        decimals = int(pip_size)
        scale = 10 ** decimals
    except (TypeError, ValueError):
        scale = round(1.0 / fallback_pip)
    return int(round(quote * scale)) % 10


class LiveValidator:
    def __init__(self, args, model, pip):
        self.args = args
        self.model = model
        self.pip = pip
        self.client = None
        self.digits = []
        self.in_trade = False
        self.trade_task = None
        self.trades = 0
        self.wins = 0
        self.pnl = 0.0
        self.shadow_n = 0
        self.shadow_wins = 0
        self.pending_shadow = None
        self.done = asyncio.Event()
        self.started = time.monotonic()
        self.output = Path(args.output)
        self.output.parent.mkdir(parents=True, exist_ok=True)

    def write(self, record):
        with self.output.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, sort_keys=True) + "\n")

    def action(self):
        if len(self.digits) < 2:
            return None
        context = self.digits[-1] + 10 * self.digits[-2]
        if not self.model["selected"][context]:
            return None
        return {
            "context": int(context),
            "previous_digit": int(self.digits[-2]),
            "signal_digit": int(self.digits[-1]),
            "barrier": int(self.model["actions"][context]),
            "train_probability": float(self.model["probabilities"][context].max()),
            "train_count": int(self.model["totals"][context]),
        }

    async def on_tick(self, message):
        tick = message.get("tick", {})
        if tick.get("symbol") != self.args.symbol or "quote" not in tick:
            return
        digit = digit_from_tick(tick, self.pip)
        epoch = int(tick.get("epoch") or 0)
        if self.pending_shadow is not None:
            self.shadow_n += 1
            won = digit == self.pending_shadow["barrier"]
            self.shadow_wins += int(won)
            self.write({"event": "shadow", "epoch": epoch, "digit": digit, "won": won, **self.pending_shadow})
        self.digits.append(digit)
        self.digits = self.digits[-2:]
        signal = self.action()
        self.pending_shadow = {"signal_epoch": epoch, **signal} if signal else None
        if signal and not self.in_trade and self.trades < self.args.demo_trades:
            self.in_trade = True
            self.trade_task = asyncio.create_task(self.execute(signal, epoch))
        if self.trades >= self.args.demo_trades or self.pnl <= -abs(self.args.max_demo_loss):
            self.done.set()

    async def execute(self, signal, epoch):
        started = time.perf_counter()
        try:
            response = await self.client.buy_direct(
                contract_type="DIGITMATCH",
                stake=self.args.stake,
                symbol=self.args.symbol,
                duration=1,
                duration_unit="t",
                barrier=signal["barrier"],
            )
            latency_ms = (time.perf_counter() - started) * 1000.0
            if "error" in response or "buy" not in response:
                self.write({"event": "reject", "signal_epoch": epoch, "latency_ms": latency_ms,
                            "error": response.get("error", {}).get("message"), **signal})
                return
            buy = response["buy"]
            contract_id = buy["contract_id"]
            last = {}
            for _ in range(60):
                await asyncio.sleep(0.2)
                result = await self.client.send_request({
                    "proposal_open_contract": 1,
                    "contract_id": contract_id,
                })
                last = result.get("proposal_open_contract", {})
                if last.get("is_sold") or last.get("status") in {"won", "lost", "sold"}:
                    break
            profit = float(last.get("profit") or 0.0)
            won = profit > 0
            self.trades += 1
            self.wins += int(won)
            self.pnl += profit
            record = {
                "event": "settled",
                "trade": self.trades,
                "signal_epoch": epoch,
                "contract_id": contract_id,
                "latency_ms": latency_ms,
                "buy_price": float(buy.get("buy_price") or self.args.stake),
                "payout": float(buy.get("payout") or last.get("payout") or 0.0),
                "profit": profit,
                "won": won,
                "status": last.get("status"),
                "entry_spot": last.get("entry_spot"),
                "exit_spot": last.get("exit_spot"),
                "entry_tick_time": last.get("entry_tick_time"),
                "exit_tick_time": last.get("exit_tick_time"),
                "pnl": self.pnl,
                **signal,
            }
            self.write(record)
            print(
                f"trade={self.trades:03d} barrier={signal['barrier']} "
                f"{'WIN' if won else 'LOSS'} profit={profit:+.2f} pnl={self.pnl:+.2f} "
                f"latency={latency_ms:.0f}ms shadow={self.shadow_wins}/{self.shadow_n}",
                flush=True,
            )
        finally:
            self.in_trade = False
            if self.trades >= self.args.demo_trades or self.pnl <= -abs(self.args.max_demo_loss):
                self.done.set()

    async def run(self):
        app_id = os.getenv("DERIV_APP_ID")
        token = os.getenv("DERIV_API_TOKEN")
        if not app_id or not token:
            raise RuntimeError("DERIV_APP_ID and DERIV_API_TOKEN are required")
        self.client = DerivClient(app_id=app_id, api_token=token, use_demo=True)
        await self.client.connect()
        if not str(self.client.account_id or "").startswith("DOT"):
            raise RuntimeError("non-demo account blocked")
        self.write({"event": "demo_authenticated", "account_prefix": "DOT", "symbol": self.args.symbol})
        await self.client.subscribe_ticks(self.args.symbol, self.on_tick)
        try:
            await asyncio.wait_for(self.done.wait(), timeout=self.args.max_runtime_seconds)
        except asyncio.TimeoutError:
            pass
        if self.trade_task and not self.trade_task.done():
            await self.trade_task
        await self.client.disconnect()
        return {
            "trades": self.trades,
            "wins": self.wins,
            "pnl": self.pnl,
            "shadow_n": self.shadow_n,
            "shadow_wins": self.shadow_wins,
        }


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbol", default="R_75")
    parser.add_argument("--cache", default=str(HERE / "data" / "d117_cache" / "R_75_100000.json.gz"))
    parser.add_argument("--gross-return", type=float, default=8.929)
    parser.add_argument("--confidence", type=float, default=0.02)
    parser.add_argument("--minimum-context", type=int, default=100)
    parser.add_argument("--demo-trades", type=int, default=0)
    parser.add_argument("--stake", type=float, default=0.35)
    parser.add_argument("--max-demo-loss", type=float, default=25.0)
    parser.add_argument("--max-runtime-seconds", type=float, default=600.0)
    parser.add_argument("--output", default=str(HERE / "data" / "d117_digit_match_live.jsonl"))
    args = parser.parse_args()

    with gzip.open(args.cache, "rt", encoding="utf-8") as handle:
        data = json.load(handle)
    prices, _ = normalize_history(data["prices"], data["epochs"], len(data["prices"]))
    pip = infer_pip(prices)
    model = fit_model(prices, pip, confidence=args.confidence, minimum_context=args.minimum_context)
    validation_end = int(len(prices) * 0.8)
    print(f"{args.symbol} ticks={len(prices):,} pip={pip} selected_contexts={int(model['selected'].sum())}")
    for lag in (1, 2, 3):
        validation = evaluate_model(model, model["train_end"], validation_end, lag, args.gross_return)
        test = evaluate_model(model, validation_end, len(prices), lag, args.gross_return)
        print(
            f"lag={lag} val N={validation['n']} WR={validation['wr']*100:.2f}% EV={validation['ev']:+.4f} "
            f"test N={test['n']} WR={test['wr']*100:.2f}% EV={test['ev']:+.4f} "
            f"EVlo={test['ev_lo']:+.4f} p={test['p']:.4g}"
        )
    if args.demo_trades <= 0:
        return
    validator = LiveValidator(args, model, pip)
    result = await validator.run()
    shadow = split_summary(result["shadow_wins"], result["shadow_n"], args.gross_return)
    print(
        f"LIVE FINAL trades={result['trades']} wins={result['wins']} pnl={result['pnl']:+.2f} | "
        f"shadow N={shadow['n']} WR={shadow['wr']*100:.2f}% EV={shadow['ev']:+.4f} "
        f"EVlo={shadow['ev_lo']:+.4f} p={shadow['p']:.4g}"
    )


if __name__ == "__main__":
    asyncio.run(main())
