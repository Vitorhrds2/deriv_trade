"""Hyperliquid Mempool Gossip Streaming Emulator (Tokyo Node Mock).

Emulates the behavior of a non-validator Hyperliquid L1 node running with
`split_client_blocks: true` in Tokyo (AWS ap-northeast-1).

Key Microstructure Characteristics:
- Pre-consensus gossip streaming: Transactions emitted 70-150ms prior to block commitment.
- Bifurcated streams:
  1. Mempool Eager Stream: Emits raw uncommitted user actions (Order, Cancel, Liquidation).
  2. Committed Block Stream: Emits finalized blocks with deterministic execution results.
- Toxic Flow Simulation: Generates aggressive taker sweeps and liquidation cascades.
- Defensive Cancellation Latency Model: Simulates maker reactions comparing Tokyo (<5ms)
  vs US-East (~150ms RTT) latency to measure adverse selection avoidance.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import random
import time
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, AsyncGenerator, Callable, Dict, List, Optional, Set, Tuple

logger = logging.getLogger("HyperliquidMempoolMock")


@dataclass
class MempoolTransaction:
    """Represents a pre-consensus uncommitted transaction in Hyperliquid gossip."""
    tx_id: str
    user: str
    action_type: str  # "order", "cancel", "cancelByCloid", "liquidate"
    coin: str
    is_buy: bool
    limit_px: float
    sz: float
    tif: str  # "Alo", "Gtc", "Ioc"
    cloid: Optional[str] = None
    is_toxic: bool = False
    gossip_time_ns: int = field(default_factory=time.time_ns)
    scheduled_block_time_ns: int = 0
    raw_payload: Dict[str, Any] = field(default_factory=dict)


@dataclass
class CommittedBlock:
    """Represents a finalized block committed by HyperBFT consensus."""
    block_number: int
    block_time_ns: int
    transactions: List[MempoolTransaction]
    fills: List[Dict[str, Any]]
    cancels: List[str]


class HyperliquidMempoolEmulator:
    """Tokyo Gossip Emulator with split_client_blocks: true.

    Allows discrete-event testing and simulation of toxic flow avoidance without
    requiring an active $2,700/mo bare-metal node in Tokyo.
    """

    def __init__(
        self,
        min_lead_time_ms: float = 70.0,
        max_lead_time_ms: float = 150.0,
        block_interval_ms: float = 200.0,
        output_dir: Optional[str] = None,
        split_client_blocks: bool = True,
    ):
        self.min_lead_time_ms = min_lead_time_ms
        self.max_lead_time_ms = max_lead_time_ms
        self.block_interval_ms = block_interval_ms
        self.output_dir = Path(output_dir) if output_dir else None
        self.split_client_blocks = split_client_blocks

        self.current_block: int = 100_000
        self.pending_mempool: List[MempoolTransaction] = []
        self.defensive_cancels: Set[str] = set()  # ClOIDs or TxIDs cancelled defensively
        self.active_maker_orders: Dict[str, Dict[str, Any]] = {}
        self._is_running: bool = False
        self._block_task: Optional[asyncio.Task[None]] = None
        self._tx_listeners: List[Callable[[MempoolTransaction], None]] = []

        if self.output_dir:
            self.output_dir.mkdir(parents=True, exist_ok=True)

    def add_tx_listener(self, listener: Callable[[MempoolTransaction], None]) -> None:
        """Registers a synchronous or asynchronous observer on pre-consensus txs."""
        self._tx_listeners.append(listener)

    def register_maker_order(self, cloid: str, coin: str, is_buy: bool, limit_px: float, sz: float) -> None:
        """Registers a passive maker limit order to track whether toxic flow sweeps it."""
        self.active_maker_orders[cloid] = {
            "cloid": cloid,
            "coin": coin,
            "is_buy": is_buy,
            "limit_px": limit_px,
            "sz": sz,
            "created_at": time.time_ns(),
        }

    def submit_defensive_cancel(self, cloid: str, receipt_time_ns: Optional[int] = None) -> bool:
        """Submits a fast cancel request to pull resting order before block commitment."""
        if cloid not in self.active_maker_orders:
            return False
        self.defensive_cancels.add(cloid)
        return True

    def generate_synthetic_tx(
        self,
        coin: str = "SOL",
        force_toxic: bool = False,
        toxic_side: Optional[bool] = None,
        toxic_size: float = 50.0,
    ) -> MempoolTransaction:
        """Synthesizes a mempool transaction with realistic parameters."""
        tx_id = f"0x{uuid.uuid4().hex}"
        now_ns = time.time_ns()
        lead_time_ms = random.uniform(self.min_lead_time_ms, self.max_lead_time_ms)
        lead_time_ns = int(lead_time_ms * 1_000_000)
        scheduled_commit_ns = now_ns + lead_time_ns

        if force_toxic:
            is_buy = toxic_side if toxic_side is not None else random.choice([True, False])
            action_type = "order"
            sz = toxic_size
            limit_px = 150.0 if is_buy else 140.0
            tif = "Ioc"
            is_toxic = True
        else:
            is_toxic = random.random() < 0.20  # 20% natural toxic flow probability
            action_type = random.choice(["order", "order", "cancel"])
            is_buy = random.choice([True, False])
            sz = round(random.uniform(1.0, 100.0 if is_toxic else 5.0), 2)
            limit_px = round(random.uniform(142.0, 148.0), 2)
            tif = "Alo" if not is_toxic else "Ioc"

        tx = MempoolTransaction(
            tx_id=tx_id,
            user=f"0x{uuid.uuid4().hex[:40]}",
            action_type=action_type,
            coin=coin,
            is_buy=is_buy,
            limit_px=limit_px,
            sz=sz,
            tif=tif,
            cloid=f"0x{uuid.uuid4().hex}",
            is_toxic=is_toxic,
            gossip_time_ns=now_ns,
            scheduled_block_time_ns=scheduled_commit_ns,
            raw_payload={
                "coin": coin,
                "is_buy": is_buy,
                "sz": sz,
                "limit_px": limit_px,
                "order_type": {"limit": {"tif": tif}},
            },
        )
        return tx

    def ingest_gossip_tx(self, tx: MempoolTransaction) -> None:
        """Eagerly ingests a gossip tx into pending mempool and notifies listeners."""
        self.pending_mempool.append(tx)

        # Notify active listeners
        for listener in self._tx_listeners:
            try:
                listener(tx)
            except Exception as e:
                logger.error(f"Listener error on gossip tx: {e}")

        # If disk writing configured, write to mempool log
        if self.output_dir and self.split_client_blocks:
            date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            log_file = self.output_dir / f"mempool_txs_{date_str}.jsonl"
            with open(log_file, "a") as f:
                f.write(json.dumps(asdict(tx)) + "\n")

    def process_block_round(self, commit_time_ns: int) -> CommittedBlock:
        """Processes block commitment round, evaluating executions vs cancels."""
        self.current_block += 1
        committed_txs: List[MempoolTransaction] = []
        remaining_mempool: List[MempoolTransaction] = []

        fills: List[Dict[str, Any]] = []
        cancels: List[str] = []

        for tx in self.pending_mempool:
            if tx.scheduled_block_time_ns <= commit_time_ns:
                committed_txs.append(tx)
            else:
                remaining_mempool.append(tx)

        self.pending_mempool = remaining_mempool

        # Process executions against active maker orders
        for tx in committed_txs:
            if tx.action_type == "cancel":
                if tx.cloid and tx.cloid in self.active_maker_orders:
                    del self.active_maker_orders[tx.cloid]
                    cancels.append(tx.cloid)
                continue

            if tx.action_type != "order":
                continue

            # Check if this order crosses resting maker orders
            for maker_cloid, maker in list(self.active_maker_orders.items()):
                if maker["coin"] != tx.coin:
                    continue

                # Defensive check: Was this maker order cancelled BEFORE this block commit?
                if maker_cloid in self.defensive_cancels:
                    cancels.append(maker_cloid)
                    del self.active_maker_orders[maker_cloid]
                    continue

                # Crossing condition: Taker Buy crosses Maker Ask (maker.is_buy=False, taker.is_buy=True)
                crosses = False
                if tx.is_buy and not maker["is_buy"] and tx.limit_px >= maker["limit_px"]:
                    crosses = True
                elif not tx.is_buy and maker["is_buy"] and tx.limit_px <= maker["limit_px"]:
                    crosses = True

                if crosses:
                    fill_sz = min(tx.sz, maker["sz"])
                    fills.append({
                        "taker_tx_id": tx.tx_id,
                        "maker_cloid": maker_cloid,
                        "is_toxic": tx.is_toxic,
                        "coin": tx.coin,
                        "price": maker["limit_px"],
                        "size": fill_sz,
                        "timestamp_ns": commit_time_ns,
                    })
                    maker["sz"] -= fill_sz
                    if maker["sz"] <= 0:
                        del self.active_maker_orders[maker_cloid]

        block = CommittedBlock(
            block_number=self.current_block,
            block_time_ns=commit_time_ns,
            transactions=committed_txs,
            fills=fills,
            cancels=cancels,
        )
        return block

    async def stream_mempool(
        self,
        count: int = 10,
        tx_interval_ms: float = 20.0,
        toxic_ratio: float = 0.3,
    ) -> AsyncGenerator[Tuple[str, Any], None]:
        """Async generator streaming pre-consensus transactions followed by block commits."""
        for _ in range(count):
            is_toxic = random.random() < toxic_ratio
            tx = self.generate_synthetic_tx(force_toxic=is_toxic)
            self.ingest_gossip_tx(tx)
            yield ("mempool_tx", tx)

            await asyncio.sleep(tx_interval_ms / 1000.0)

            # Check if pending txs reached commit time
            now_ns = time.time_ns()
            ready = any(t.scheduled_block_time_ns <= now_ns for t in self.pending_mempool)
            if ready:
                block = self.process_block_round(now_ns)
                yield ("block_commit", block)

    def evaluate_cancellation_race(
        self,
        toxic_tx: MempoolTransaction,
        maker_cloid: str,
        network_rtt_ms: float,
        detection_delay_ms: float = 5.0,
    ) -> Dict[str, Any]:
        """Evaluates whether a maker cancel beats the toxic transaction into the block.

        Parameters:
        - toxic_tx: The mempool transaction detected.
        - maker_cloid: The resting maker order ID.
        - network_rtt_ms: Round-trip time from maker bot to Tokyo node:
            * Tokyo co-located: ~2-5 ms
            * US-East (Virginia/Ohio): ~140-160 ms
        - detection_delay_ms: Internal bot algorithmic parsing delay (~2-5ms).

        Returns:
            Dict containing:
            - lead_time_ms: Total lead time granted by Tokyo gossip
            - total_cancel_latency_ms: Detection delay + 0.5 * network_rtt
            - canceled_successfully: True if cancel arrived before block commitment
            - adverse_selection_avoided: True if toxic fill avoided
        """
        lead_time_ms = (toxic_tx.scheduled_block_time_ns - toxic_tx.gossip_time_ns) / 1_000_000.0
        # Cancel propagation time is one-way transit (0.5 * RTT) from bot to Tokyo node
        cancel_arrival_latency_ms = detection_delay_ms + (0.5 * network_rtt_ms)

        canceled_successfully = cancel_arrival_latency_ms < lead_time_ms

        if canceled_successfully:
            self.submit_defensive_cancel(maker_cloid)

        return {
            "lead_time_ms": lead_time_ms,
            "network_rtt_ms": network_rtt_ms,
            "cancel_arrival_latency_ms": cancel_arrival_latency_ms,
            "margin_ms": lead_time_ms - cancel_arrival_latency_ms,
            "canceled_successfully": canceled_successfully,
            "adverse_selection_avoided": canceled_successfully and toxic_tx.is_toxic,
        }
