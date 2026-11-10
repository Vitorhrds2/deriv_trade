"""Comprehensive Unit Test Suite for High-Fidelity Mock Infrastructure.

Validates:
1. FIXT.1.1 / FIX50SP2 parser, serializer, and checksum validation.
2. Kalshi Binary Contract Order Book matching engine.
3. Kalshi FIX Mock Server socket lifecycle, authentication, Tag 50 rejection,
   concurrency control, order placement, matching, fills, and cancellation.
4. Hyperliquid Tokyo Gossip Emulator: pre-consensus lead time (70-150ms),
   toxic flow injection, Tokyo vs US-East defensive cancellation race.
"""

from __future__ import annotations

import asyncio
import os
import sys
import time
import pytest
from pathlib import Path

# Ensure trading-engine directory is on sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from mocks.kalshi_fix_mock import (
    BinaryContractOrderBook,
    FixMessage,
    KalshiFixClient,
    KalshiFixMockServer,
    MSG_EXECUTION_REPORT,
    MSG_HEARTBEAT,
    MSG_LOGON,
    MSG_LOGOUT,
    MSG_NEW_ORDER_SINGLE,
    MSG_ORDER_CANCEL_REJECT,
    MSG_ORDER_CANCEL_REQUEST,
    MSG_TEST_REQUEST,
    SIDE_BUY,
    SIDE_SELL,
    SOH,
    STATUS_CANCELED,
    STATUS_FILLED,
    STATUS_NEW,
    STATUS_REJECTED,
    TAG_CHECK_SUM,
    TAG_CL_ORD_ID,
    TAG_EXEC_TYPE,
    TAG_LAST_PX,
    TAG_LAST_QTY,
    TAG_MSG_TYPE,
    TAG_ORD_STATUS,
    TAG_ORDER_QTY,
    TAG_ORIG_CL_ORD_ID,
    TAG_PRICE,
    TAG_SENDER_SUB_ID,
    TAG_SIDE,
    TAG_SYMBOL,
    TAG_TEST_REQ_ID,
    TAG_TEXT,
    build_fix_message,
    compute_checksum,
    parse_fix_message,
)
from mocks.hyperliquid_mempool_mock import (
    HyperliquidMempoolEmulator,
    MempoolTransaction,
)


# ==============================================================================
# 1. FIX PROTOCOL MESSAGE PARSER & SERIALIZER TESTS
# ==============================================================================

def test_fix_checksum_computation():
    """Validates modulo-256 checksum calculation according to FIX standard."""
    sample_data = f"8=FIXT.1.1{SOH}9=25{SOH}35=0{SOH}49=SENDER{SOH}56=TARGET{SOH}"
    checksum = compute_checksum(sample_data)
    assert len(checksum) == 3
    assert checksum.isdigit()
    expected = f"{sum(sample_data.encode('latin1')) % 256:03d}"
    assert checksum == expected


def test_fix_build_and_parse_roundtrip():
    """Validates building and parsing FIXT.1.1 messages."""
    fields = {
        TAG_CL_ORD_ID: "CLORD-12345",
        TAG_SYMBOL: "KXFEDDEC26-YES",
        TAG_PRICE: "0.45",
        TAG_ORDER_QTY: "100",
    }
    raw_msg = build_fix_message(
        msg_type=MSG_NEW_ORDER_SINGLE,
        fields=fields,
        sender_comp_id="CLIENT_UUID",
        target_comp_id="KalshiNR",
        msg_seq_num=42,
    )

    assert raw_msg.startswith(f"8=FIXT.1.1{SOH}9=")
    assert raw_msg.endswith(f"{TAG_CHECK_SUM}=") or f"{TAG_CHECK_SUM}=" in raw_msg[-10:]

    parsed = parse_fix_message(raw_msg)
    assert parsed.msg_type == MSG_NEW_ORDER_SINGLE
    assert parsed.get(TAG_CL_ORD_ID) == "CLORD-12345"
    assert parsed.get(TAG_SYMBOL) == "KXFEDDEC26-YES"
    assert parsed.get_float(TAG_PRICE) == 0.45
    assert parsed.get_int(TAG_ORDER_QTY) == 100
    assert parsed.get_int(34) == 42  # MsgSeqNum


# ==============================================================================
# 2. BINARY CONTRACT ORDER BOOK MATCHING ENGINE TESTS
# ==============================================================================

def test_binary_order_book_bids_asks_sorting():
    """Tests price-time priority sorting in binary contract book."""
    book = BinaryContractOrderBook("KXTEST-YES")
    # Add bids at 40¢, 45¢, 42¢
    book.process_new_order("B1", "USER_A", SIDE_BUY, 0.40, 10)
    book.process_new_order("B2", "USER_B", SIDE_BUY, 0.45, 10)
    book.process_new_order("B3", "USER_C", SIDE_BUY, 0.42, 10)

    # Highest bid first
    assert [b.price for b in book.bids] == [0.45, 0.42, 0.40]

    # Add asks at 60¢, 55¢, 58¢
    book.process_new_order("A1", "USER_D", SIDE_SELL, 0.60, 10)
    book.process_new_order("A2", "USER_E", SIDE_SELL, 0.55, 10)
    book.process_new_order("A3", "USER_F", SIDE_SELL, 0.58, 10)

    # Lowest ask first
    assert [a.price for a in book.asks] == [0.55, 0.58, 0.60]


def test_binary_order_book_matching_crossing_fill():
    """Tests immediate matching when order crosses the resting spread."""
    book = BinaryContractOrderBook("KXTEST-YES")
    # Resting ask: 10 contracts @ $0.55
    book.process_new_order("A1", "MAKER", SIDE_SELL, 0.55, 10)
    assert len(book.asks) == 1

    # Aggressive taker buy: 10 contracts @ $0.55
    order, fills = book.process_new_order("B1", "TAKER", SIDE_BUY, 0.55, 10)

    assert len(fills) == 1
    maker_order, fill_qty, fill_px = fills[0]
    assert maker_order.cl_ord_id == "A1"
    assert fill_qty == 10
    assert fill_px == 0.55

    # Taker is fully filled, book is empty
    assert order.leaves_qty == 0
    assert order.cum_qty == 10
    assert len(book.asks) == 0
    assert len(book.bids) == 0


def test_binary_order_book_cancellation():
    """Tests cancellation of resting order."""
    book = BinaryContractOrderBook("KXTEST-YES")
    book.process_new_order("B1", "USER_A", SIDE_BUY, 0.45, 50)
    assert len(book.bids) == 1

    canceled = book.cancel_order("B1", "USER_A")
    assert canceled is not None
    assert canceled.cl_ord_id == "B1"
    assert len(book.bids) == 0

    # Canceling non-existent or other user's order fails
    assert book.cancel_order("B1", "USER_A") is None
    assert book.cancel_order("NON_EXISTENT", "USER_A") is None


# ==============================================================================
# 3. KALSHI FIX MOCK SERVER END-TO-END ASYNC TESTS
# ==============================================================================

def test_kalshi_fix_logon_and_heartbeat():
    """Tests socket connection, Logon handshake, and Heartbeat exchange."""
    async def _run():
        server = KalshiFixMockServer(host="127.0.0.1", port=9128, target_comp_id="KalshiNR")
        await server.start()

        client = KalshiFixClient(
            host="127.0.0.1",
            port=9128,
            sender_comp_id="TEST-CLIENT-UUID-1",
            target_comp_id="KalshiNR",
        )
        try:
            await client.connect()
            logon_resp = await client.logon()
            assert logon_resp.msg_type == MSG_LOGON
            assert logon_resp.get(35) == MSG_LOGON

            # Send TestRequest (35=1) -> Expect Heartbeat (35=0) with matching TestReqID (Tag 112)
            await client.send(MSG_TEST_REQUEST, {TAG_TEST_REQ_ID: "TEST-PING-99"})
            hb_resp = await client.wait_for_message(MSG_HEARTBEAT)
            assert hb_resp.get(TAG_TEST_REQ_ID) == "TEST-PING-99"

        finally:
            await client.close()
            await server.stop()

    asyncio.run(_run())


def test_kalshi_fix_strict_tag50_rejection_on_logon():
    """Kalshi CFTC Rule: Tag 50 (SenderSubID) in Logon (35=A) must trigger immediate Logout."""
    async def _run():
        server = KalshiFixMockServer(host="127.0.0.1", port=9129, target_comp_id="KalshiNR")
        await server.start()

        client = KalshiFixClient(
            host="127.0.0.1",
            port=9129,
            sender_comp_id="TEST-CLIENT-TAG50",
            target_comp_id="KalshiNR",
        )
        try:
            await client.connect()
            # Illegally send Tag 50 during Logon
            await client.send(MSG_LOGON, {
                108: 30,
                98: 0,
                TAG_SENDER_SUB_ID: "ILLEGAL_SUB_ACCOUNT",
            })

            logout_resp = await client.wait_for_message(MSG_LOGOUT)
            assert logout_resp.msg_type == MSG_LOGOUT
            assert "Tag 50" in logout_resp.get(TAG_TEXT, "")
        finally:
            await client.close()
            await server.stop()

    asyncio.run(_run())


def test_kalshi_fix_single_concurrency_limit():
    """Tests that a duplicate session for the same API Key ID is rejected."""
    async def _run():
        server = KalshiFixMockServer(host="127.0.0.1", port=9130, target_comp_id="KalshiNR")
        await server.start()

        client1 = KalshiFixClient(host="127.0.0.1", port=9130, sender_comp_id="SAME_UUID")
        client2 = KalshiFixClient(host="127.0.0.1", port=9130, sender_comp_id="SAME_UUID")

        try:
            await client1.connect()
            resp1 = await client1.logon()
            assert resp1.msg_type == MSG_LOGON

            # Second client attempts logon with same comp ID
            await client2.connect()
            await client2.send(MSG_LOGON, {108: 30, 98: 0})
            resp2 = await client2.wait_for_message(MSG_LOGOUT)
            assert resp2.msg_type == MSG_LOGOUT
            assert "already exists" in resp2.get(TAG_TEXT, "")
        finally:
            await client1.close()
            await client2.close()
            await server.stop()

    asyncio.run(_run())


def test_kalshi_fix_order_placement_fill_and_cancellation():
    """Full lifecycle: Place resting order, cancel it, place crossing order, get fill."""
    async def _run():
        server = KalshiFixMockServer(host="127.0.0.1", port=9131, target_comp_id="KalshiNR")
        await server.start()

        client = KalshiFixClient(host="127.0.0.1", port=9131, sender_comp_id="TRADER_CLIENT")
        try:
            await client.connect()
            await client.logon()

            # 1. Place a resting BUY limit order: 10 contracts of KXTEST @ $0.48
            cl_ord_id = "ORDER-001"
            await client.send(MSG_NEW_ORDER_SINGLE, {
                TAG_CL_ORD_ID: cl_ord_id,
                TAG_SYMBOL: "KXTEST-YES",
                TAG_SIDE: SIDE_BUY,
                TAG_ORDER_QTY: 10,
                TAG_PRICE: "0.48",
            })

            exec_rep = await client.wait_for_message(MSG_EXECUTION_REPORT)
            assert exec_rep.get(TAG_CL_ORD_ID) == cl_ord_id
            assert exec_rep.get(TAG_EXEC_TYPE) == STATUS_NEW
            assert exec_rep.get(TAG_ORD_STATUS) == STATUS_NEW

            # 2. Cancel the resting order
            cancel_id = "CANCEL-001"
            await client.send(MSG_ORDER_CANCEL_REQUEST, {
                TAG_CL_ORD_ID: cancel_id,
                TAG_ORIG_CL_ORD_ID: cl_ord_id,
                TAG_SYMBOL: "KXTEST-YES",
                TAG_SIDE: SIDE_BUY,
            })

            cancel_rep = await client.wait_for_message(MSG_EXECUTION_REPORT)
            assert cancel_rep.get(TAG_EXEC_TYPE) == STATUS_CANCELED
            assert cancel_rep.get(TAG_ORD_STATUS) == STATUS_CANCELED

            # 3. Test crossing pre-seeded liquidity
            # The mock server pre-seeds KXFEDDEC26-YES with best Ask at $0.55
            buy_id = "ORDER-SWEEP-001"
            await client.send(MSG_NEW_ORDER_SINGLE, {
                TAG_CL_ORD_ID: buy_id,
                TAG_SYMBOL: "KXFEDDEC26-YES",
                TAG_SIDE: SIDE_BUY,
                TAG_ORDER_QTY: 50,
                TAG_PRICE: "0.55",  # Matches seeded ask @ 0.55
            })

            fill_rep = await client.wait_for_message(MSG_EXECUTION_REPORT)
            assert fill_rep.get(TAG_CL_ORD_ID) == buy_id
            assert fill_rep.get(TAG_EXEC_TYPE) in (STATUS_FILLED, "1")
            assert fill_rep.get_int(TAG_LAST_QTY) == 50
            assert fill_rep.get_float(TAG_LAST_PX) == 0.55

            # 4. Test invalid price rejection (price > $0.99)
            bad_id = "ORDER-BAD-001"
            await client.send(MSG_NEW_ORDER_SINGLE, {
                TAG_CL_ORD_ID: bad_id,
                TAG_SYMBOL: "KXTEST-YES",
                TAG_SIDE: SIDE_BUY,
                TAG_ORDER_QTY: 10,
                TAG_PRICE: "1.50",  # Out of range!
            })

            rej_rep = await client.wait_for_message(MSG_EXECUTION_REPORT)
            assert rej_rep.get(TAG_EXEC_TYPE) == STATUS_REJECTED
            assert rej_rep.get(TAG_ORD_STATUS) == STATUS_REJECTED

        finally:
            await client.close()
            await server.stop()

    asyncio.run(_run())


# ==============================================================================
# 4. HYPERLIQUID TOKYO GOSSIP EMULATOR TESTS
# ==============================================================================

def test_hyperliquid_lead_time_generation():
    """Validates that synthetic mempool transactions provide 70-150ms lead time."""
    emulator = HyperliquidMempoolEmulator(min_lead_time_ms=70.0, max_lead_time_ms=150.0)
    tx = emulator.generate_synthetic_tx(coin="SOL")

    lead_time_ms = (tx.scheduled_block_time_ns - tx.gossip_time_ns) / 1_000_000.0
    assert 70.0 <= lead_time_ms <= 150.0
    assert tx.coin == "SOL"
    assert tx.tx_id.startswith("0x")


def test_hyperliquid_toxic_flow_avoidance_tokyo_vs_useast():
    """Proves quantitatively why Tokyo co-location succeeds and US-East fails.

    Scenario:
    - Toxic taker order arrives via gossip with 100ms lead time before block commit.
    - Maker bot in Tokyo: RTT = 4ms -> Cancel arrives in 5ms (detection) + 2ms = 7ms.
      7ms < 100ms -> Cancel succeeds, toxic flow avoided!
    - Maker bot in US-East: RTT = 150ms -> Cancel arrives in 5ms + 75ms = 80ms.
      If lead time is 70ms: 80ms > 70ms -> Cancel fails, maker suffers adverse selection!
    """
    emulator = HyperliquidMempoolEmulator()

    # Pre-configure a toxic taker order with 80ms lead time
    toxic_tx = emulator.generate_synthetic_tx(coin="SOL", force_toxic=True)
    # Fix lead time strictly to 80ms for deterministic test
    toxic_tx.scheduled_block_time_ns = toxic_tx.gossip_time_ns + int(80.0 * 1_000_000)

    maker_cloid = "MAKER-RESTING-SOL-01"
    emulator.register_maker_order(maker_cloid, "SOL", is_buy=True, limit_px=145.0, sz=10.0)

    # 1. Tokyo co-located bot (4ms RTT)
    res_tokyo = emulator.evaluate_cancellation_race(
        toxic_tx=toxic_tx,
        maker_cloid=maker_cloid,
        network_rtt_ms=4.0,
        detection_delay_ms=3.0,
    )
    assert res_tokyo["canceled_successfully"] is True
    assert res_tokyo["adverse_selection_avoided"] is True
    assert res_tokyo["margin_ms"] > 70.0  # Safe positive margin

    # 2. US-East bot (160ms RTT)
    # Reset maker order
    maker_cloid_2 = "MAKER-RESTING-SOL-02"
    emulator.register_maker_order(maker_cloid_2, "SOL", is_buy=True, limit_px=145.0, sz=10.0)

    res_useast = emulator.evaluate_cancellation_race(
        toxic_tx=toxic_tx,
        maker_cloid=maker_cloid_2,
        network_rtt_ms=160.0,
        detection_delay_ms=5.0,
    )
    # Cancel arrival: 5ms + 80ms = 85ms > 80ms lead time -> FAILS
    assert res_useast["canceled_successfully"] is False
    assert res_useast["adverse_selection_avoided"] is False
    assert res_useast["margin_ms"] < 0.0  # Negative margin (too slow)


def test_hyperliquid_mempool_stream_async():
    """Tests the async streaming generator producing mempool events and block commits."""
    async def _run():
        emulator = HyperliquidMempoolEmulator(min_lead_time_ms=10.0, max_lead_time_ms=20.0)

        events: list = []
        async for event_type, payload in emulator.stream_mempool(count=5, tx_interval_ms=10.0):
            events.append((event_type, payload))

        mempool_events = [e for e in events if e[0] == "mempool_tx"]
        assert len(mempool_events) == 5
        for _, tx in mempool_events:
            assert isinstance(tx, MempoolTransaction)

    asyncio.run(_run())

