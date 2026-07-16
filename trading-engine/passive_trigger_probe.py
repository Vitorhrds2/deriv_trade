import argparse
import asyncio
import json
import time
from collections import deque
from datetime import datetime, timezone
from pathlib import Path

import websockets


DERIV_SYMBOL = "cryBTCUSD"
BINANCE_SYMBOL = "btcusdt"
JUMP_FORMATION_WINDOW = 0.050
L_DERIV = 0.350
DERIV_LAG = 0.690
GOLDEN_HOUR_START_UTC = 12
GOLDEN_HOUR_END_UTC = 18

COEFFS = {
    "binance": 0.3874,
    "coinbase": 0.5338,
    "kraken": 0.0266,
}
INTERCEPT = 3152.82


class ProbeState:
    def __init__(self, thresholds):
        self.thresholds = thresholds
        self.prices = {"binance": None, "coinbase": None, "kraken": None}
        self.feed_updates = {"binance": 0, "coinbase": 0, "kraken": 0, "deriv_ticks": 0}
        self.feed_connected = {"binance": False, "coinbase": False, "kraken": False, "deriv": False}
        self.history = deque()
        self.last_deriv_tick_time = 0.0
        self.last_count_time = {threshold: 0.0 for threshold in thresholds}
        self.counts = {
            str(threshold): {
                "formed": 0,
                "timing_eligible": 0,
                "golden_eligible": 0,
                "up": 0,
                "down": 0,
                "max_abs_jump": 0.0,
            }
            for threshold in thresholds
        }
        self.synthetic_updates = 0
        self.last_synthetic = None
        self.start_wall = datetime.now(timezone.utc).isoformat()
        self.start_time = time.time()

    def is_golden_hour(self):
        hour_utc = datetime.now(timezone.utc).hour
        return GOLDEN_HOUR_START_UTC <= hour_utc < GOLDEN_HOUR_END_UTC

    def synthetic_price(self):
        if not all(self.prices.values()):
            return None
        return (
            COEFFS["binance"] * self.prices["binance"]
            + COEFFS["coinbase"] * self.prices["coinbase"]
            + COEFFS["kraken"] * self.prices["kraken"]
            + INTERCEPT
        )

    def update_synthetic(self):
        synthetic = self.synthetic_price()
        if synthetic is None:
            return

        now = time.time()
        self.synthetic_updates += 1
        self.last_synthetic = synthetic
        self.history.append({"t": now, "p": synthetic})
        while self.history and now - self.history[0]["t"] > JUMP_FORMATION_WINDOW:
            self.history.popleft()

        if len(self.history) < 2:
            return

        oldest = self.history[0]
        diff = synthetic - oldest["p"]
        abs_diff = abs(diff)
        direction = "up" if diff > 0 else "down"
        t_next_tick = self.last_deriv_tick_time + 1.000
        timing_eligible = ((now + L_DERIV) < t_next_tick) and (t_next_tick < (now + DERIV_LAG))
        golden = self.is_golden_hour()

        for threshold in self.thresholds:
            if abs_diff < threshold:
                continue
            if now - self.last_count_time[threshold] < JUMP_FORMATION_WINDOW:
                continue
            self.last_count_time[threshold] = now
            bucket = self.counts[str(threshold)]
            bucket["formed"] += 1
            bucket[direction] += 1
            bucket["max_abs_jump"] = max(bucket["max_abs_jump"], abs_diff)
            if timing_eligible:
                bucket["timing_eligible"] += 1
            if timing_eligible and golden:
                bucket["golden_eligible"] += 1

    def snapshot(self):
        elapsed = max(0.0, time.time() - self.start_time)
        return {
            "started_at": self.start_wall,
            "elapsed_seconds": round(elapsed, 3),
            "golden_hour": self.is_golden_hour(),
            "feeds_connected": dict(self.feed_connected),
            "feed_updates": dict(self.feed_updates),
            "synthetic_updates": self.synthetic_updates,
            "last_synthetic": self.last_synthetic,
            "thresholds": self.counts,
            "note": "passive probe only; no auth, no proposal, no buy/order",
        }


async def deriv_tick_sync(state):
    uri = "wss://api.derivws.com/trading/v1/options/ws/public"
    while True:
        try:
            async with websockets.connect(uri) as ws:
                await ws.send(json.dumps({"ticks": DERIV_SYMBOL}))
                state.feed_connected["deriv"] = True
                async for message in ws:
                    data = json.loads(message)
                    if "tick" in data:
                        state.last_deriv_tick_time = time.time()
                        state.feed_updates["deriv_ticks"] += 1
        except asyncio.CancelledError:
            raise
        except Exception:
            state.feed_connected["deriv"] = False
            await asyncio.sleep(2)


async def binance_ws(state):
    uri = f"wss://stream.binance.com:9443/ws/{BINANCE_SYMBOL}@bookTicker"
    while True:
        try:
            async with websockets.connect(uri) as ws:
                state.feed_connected["binance"] = True
                async for message in ws:
                    data = json.loads(message)
                    state.prices["binance"] = float(data["a"])
                    state.feed_updates["binance"] += 1
                    state.update_synthetic()
        except asyncio.CancelledError:
            raise
        except Exception:
            state.feed_connected["binance"] = False
            await asyncio.sleep(2)


async def coinbase_ws(state):
    uri = "wss://ws-feed.exchange.coinbase.com"
    while True:
        try:
            async with websockets.connect(uri) as ws:
                await ws.send(
                    json.dumps(
                        {
                            "type": "subscribe",
                            "product_ids": ["BTC-USD"],
                            "channels": ["ticker"],
                        }
                    )
                )
                state.feed_connected["coinbase"] = True
                async for message in ws:
                    data = json.loads(message)
                    if data.get("type") == "ticker" and "best_ask" in data:
                        state.prices["coinbase"] = float(data["best_ask"])
                        state.feed_updates["coinbase"] += 1
                        state.update_synthetic()
        except asyncio.CancelledError:
            raise
        except Exception:
            state.feed_connected["coinbase"] = False
            await asyncio.sleep(2)


async def kraken_ws(state):
    uri = "wss://ws.kraken.com"
    while True:
        try:
            async with websockets.connect(uri) as ws:
                await ws.send(
                    json.dumps(
                        {
                            "event": "subscribe",
                            "pair": ["XBT/USD"],
                            "subscription": {"name": "ticker"},
                        }
                    )
                )
                state.feed_connected["kraken"] = True
                async for message in ws:
                    data = json.loads(message)
                    if isinstance(data, list) and len(data) > 1 and "a" in data[1]:
                        state.prices["kraken"] = float(data[1]["a"][0])
                        state.feed_updates["kraken"] += 1
                        state.update_synthetic()
        except asyncio.CancelledError:
            raise
        except Exception:
            state.feed_connected["kraken"] = False
            await asyncio.sleep(2)


async def run_probe(args):
    thresholds = [float(item) for item in args.thresholds.split(",") if item.strip()]
    state = ProbeState(thresholds)
    tasks = [
        asyncio.create_task(deriv_tick_sync(state)),
        asyncio.create_task(binance_ws(state)),
        asyncio.create_task(coinbase_ws(state)),
        asyncio.create_task(kraken_ws(state)),
    ]

    try:
        while time.time() - state.start_time < args.seconds:
            await asyncio.sleep(args.report_interval)
            print(json.dumps(state.snapshot(), ensure_ascii=True, sort_keys=True), flush=True)
    finally:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

    snapshot = state.snapshot()
    if args.json_out:
        out_path = Path(args.json_out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(snapshot, indent=2, sort_keys=True), encoding="utf-8")
    return snapshot


def parse_args():
    parser = argparse.ArgumentParser(description="Passive trigger probe; no auth and no orders.")
    parser.add_argument("--seconds", type=int, default=120)
    parser.add_argument("--report-interval", type=int, default=15)
    parser.add_argument("--thresholds", default="5,10,15,30,45")
    parser.add_argument("--json-out", default="")
    return parser.parse_args()


def main():
    snapshot = asyncio.run(run_probe(parse_args()))
    print("FINAL " + json.dumps(snapshot, ensure_ascii=True, sort_keys=True))


if __name__ == "__main__":
    main()
