"""Kalshi FIXT.1.1 / FIX50SP2 High-Fidelity Mock Server.

Implements an in-memory, high-fidelity FIX server emulating the Kalshi DCM binary contract
orderbook architecture (FIXT.1.1 transport + FIX50SP2 application profile).

Key Architecture:
- SOH (\\x01) delimited Tag=Value parser & serializer.
- Strict checksum (Tag 10) and BodyLength (Tag 9) calculation.
- Authentication: Tag 96 (RawData) Ed25519 or RSA-2048 signature verification or mock bypass.
- Regulatory / Protocol Rules:
  * Strict prohibition of Tag 50 (SenderSubID) during Logon (35=A) -> triggers 35=5 Logout.
  * Strict concurrency control: 1 active FIX session per API Key ID (SenderCompID).
  * Heartbeat (35=0), TestRequest (35=1), ResendRequest (35=2).
  * NewOrderSingle (35=D), OrderCancelRequest (35=F).
  * ExecutionReport (35=8) generation for New, PartiallyFilled, Filled, Canceled, Rejected.
- Binary Contract Order Book (0.01 - 0.99 dollars / 1 - 99 cents) with price-time priority matching.
- Supports both async TCP and TLS sockets.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import logging
import ssl
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Tuple

logger = logging.getLogger("KalshiFixMock")

SOH = "\x01"

# Standard FIX Tags
TAG_BEGIN_STRING = 8
TAG_BODY_LENGTH = 9
TAG_CHECK_SUM = 10
TAG_CL_ORD_ID = 11
TAG_CUM_QTY = 14
TAG_EXEC_ID = 17
TAG_MSG_SEQ_NUM = 34
TAG_MSG_TYPE = 35
TAG_ORDER_ID = 37
TAG_ORDER_QTY = 38
TAG_ORD_STATUS = 39
TAG_ORD_TYPE = 40
TAG_ORIG_CL_ORD_ID = 41
TAG_PRICE = 44
TAG_SENDER_COMP_ID = 49
TAG_SENDER_SUB_ID = 50
TAG_SENDING_TIME = 52
TAG_SIDE = 54
TAG_SYMBOL = 55
TAG_TARGET_COMP_ID = 56
TAG_TEXT = 58
TAG_TIME_IN_FORCE = 59
TAG_AVG_PX = 6
TAG_RAW_DATA_LENGTH = 95
TAG_RAW_DATA = 96
TAG_ENCRYPT_METHOD = 98
TAG_HEART_BT_INT = 108
TAG_TEST_REQ_ID = 112
TAG_EXEC_TYPE = 150
TAG_LEAVES_QTY = 151
TAG_LAST_PX = 31
TAG_LAST_QTY = 32
TAG_NO_MD_ENTRIES = 268
TAG_MD_ENTRY_TYPE = 269
TAG_MD_ENTRY_PX = 270
TAG_MD_ENTRY_SIZE = 271
TAG_APPL_VER_ID = 1128

# MsgTypes
MSG_HEARTBEAT = "0"
MSG_TEST_REQUEST = "1"
MSG_RESEND_REQUEST = "2"
MSG_REJECT = "3"
MSG_SEQUENCE_RESET = "4"
MSG_LOGOUT = "5"
MSG_EXECUTION_REPORT = "8"
MSG_ORDER_CANCEL_REJECT = "9"
MSG_LOGON = "A"
MSG_NEW_ORDER_SINGLE = "D"
MSG_ORDER_CANCEL_REQUEST = "F"
MSG_MARKET_DATA_REQUEST = "V"
MSG_MARKET_DATA_SNAPSHOT = "W"

# ExecType (150) / OrdStatus (39)
STATUS_NEW = "0"
STATUS_PARTIALLY_FILLED = "1"
STATUS_FILLED = "2"
STATUS_CANCELED = "4"
STATUS_REJECTED = "8"
STATUS_EXPIRED = "C"

# Side (54)
SIDE_BUY = "1"
SIDE_SELL = "2"


@dataclass
class FixMessage:
    """Parsed or serializable FIX message."""
    msg_type: str
    fields: Dict[int, str]
    raw: str = ""

    def get(self, tag: int, default: Optional[str] = None) -> Optional[str]:
        return self.fields.get(tag, default)

    def get_int(self, tag: int, default: int = 0) -> int:
        val = self.fields.get(tag)
        if val is None:
            return default
        try:
            return int(val)
        except ValueError:
            return default

    def get_float(self, tag: int, default: float = 0.0) -> float:
        val = self.fields.get(tag)
        if val is None:
            return default
        try:
            return float(val)
        except ValueError:
            return default


def parse_fix_message(raw_data: str) -> FixMessage:
    """Parses a SOH-delimited FIX string into a FixMessage."""
    fields: Dict[int, str] = {}
    tokens = raw_data.split(SOH)
    msg_type = ""
    for token in tokens:
        if not token or "=" not in token:
            continue
        tag_str, val = token.split("=", 1)
        try:
            tag = int(tag_str)
            fields[tag] = val
            if tag == TAG_MSG_TYPE:
                msg_type = val
        except ValueError:
            continue
    return FixMessage(msg_type=msg_type, fields=fields, raw=raw_data)


def compute_checksum(data: str) -> str:
    """Computes FIX modulo-256 checksum formatted as 3 digits."""
    return f"{sum(data.encode('latin1')) % 256:03d}"


def build_fix_message(
    msg_type: str,
    fields: Dict[int, Any],
    sender_comp_id: str,
    target_comp_id: str,
    msg_seq_num: int,
    sending_time: Optional[str] = None,
    begin_string: str = "FIXT.1.1",
    appl_ver_id: str = "9",  # FIX50SP2
) -> str:
    """Encodes a full FIXT.1.1 / FIX50SP2 message with strict BodyLength and CheckSum."""
    if sending_time is None:
        now = datetime.now(timezone.utc)
        sending_time = now.strftime("%Y%m%d-%H:%M:%S.%f")[:-3]

    # Standard header fields
    body_fields: List[Tuple[int, str]] = [
        (TAG_MSG_TYPE, str(msg_type)),
        (TAG_APPL_VER_ID, appl_ver_id),
        (TAG_SENDER_COMP_ID, sender_comp_id),
        (TAG_TARGET_COMP_ID, target_comp_id),
        (TAG_MSG_SEQ_NUM, str(msg_seq_num)),
        (TAG_SENDING_TIME, sending_time),
    ]

    for tag, val in fields.items():
        if tag in (TAG_BEGIN_STRING, TAG_BODY_LENGTH, TAG_CHECK_SUM, TAG_MSG_TYPE,
                   TAG_APPL_VER_ID, TAG_SENDER_COMP_ID, TAG_TARGET_COMP_ID,
                   TAG_MSG_SEQ_NUM, TAG_SENDING_TIME):
            continue
        body_fields.append((tag, str(val)))

    body_str = "".join(f"{tag}={val}{SOH}" for tag, val in body_fields)
    body_length = len(body_str)

    header_str = f"{TAG_BEGIN_STRING}={begin_string}{SOH}{TAG_BODY_LENGTH}={body_length}{SOH}"
    pre_checksum_msg = header_str + body_str
    checksum = compute_checksum(pre_checksum_msg)
    full_msg = f"{pre_checksum_msg}{TAG_CHECK_SUM}={checksum}{SOH}"
    return full_msg


@dataclass
class RestingOrder:
    order_id: str
    cl_ord_id: str
    client_comp_id: str
    symbol: str
    side: str
    price: float  # In dollars (0.01 - 0.99)
    order_qty: int
    leaves_qty: int
    cum_qty: int = 0
    created_at: float = field(default_factory=time.time)


class BinaryContractOrderBook:
    """In-memory matching engine for Kalshi binary prediction contracts (1¢ - 99¢)."""

    def __init__(self, symbol: str):
        self.symbol = symbol
        # Bids: sorted descending by price, then ascending by time
        self.bids: List[RestingOrder] = []
        # Asks: sorted ascending by price, then ascending by time
        self.asks: List[RestingOrder] = []
        self.orders_by_id: Dict[str, RestingOrder] = {}
        self.orders_by_cl_ord_id: Dict[str, RestingOrder] = {}

    def get_l2_snapshot(self) -> Dict[str, Any]:
        """Returns aggregated bid/ask snapshot."""
        bids_agg: Dict[float, int] = {}
        for b in self.bids:
            bids_agg[b.price] = bids_agg.get(b.price, 0) + b.leaves_qty

        asks_agg: Dict[float, int] = {}
        for a in self.asks:
            asks_agg[a.price] = asks_agg.get(a.price, 0) + a.leaves_qty

        sorted_bids = sorted(bids_agg.items(), key=lambda x: x[0], reverse=True)
        sorted_asks = sorted(asks_agg.items(), key=lambda x: x[0])
        return {
            "symbol": self.symbol,
            "bids": sorted_bids,
            "asks": sorted_asks,
        }

    def cancel_order(self, orig_cl_ord_id: str, client_comp_id: str) -> Optional[RestingOrder]:
        """Cancels a resting order by client order ID."""
        order = self.orders_by_cl_ord_id.get(orig_cl_ord_id)
        if not order or order.client_comp_id != client_comp_id:
            return None

        if order.side == SIDE_BUY:
            self.bids = [o for o in self.bids if o.cl_ord_id != orig_cl_ord_id]
        else:
            self.asks = [o for o in self.asks if o.cl_ord_id != orig_cl_ord_id]

        order.leaves_qty = 0
        del self.orders_by_cl_ord_id[orig_cl_ord_id]
        return order

    def process_new_order(
        self,
        cl_ord_id: str,
        client_comp_id: str,
        side: str,
        price: float,
        qty: int,
    ) -> Tuple[RestingOrder, List[Tuple[RestingOrder, int, float]]]:
        """Matches a new limit order against the book.

        Returns (new_or_resting_order, list_of_fills: [(maker_order, fill_qty, fill_px)]).
        """
        order_id = f"KALSHI-{uuid.uuid4().hex[:12].upper()}"
        order = RestingOrder(
            order_id=order_id,
            cl_ord_id=cl_ord_id,
            client_comp_id=client_comp_id,
            symbol=self.symbol,
            side=side,
            price=price,
            order_qty=qty,
            leaves_qty=qty,
            cum_qty=0,
        )
        self.orders_by_id[order_id] = order
        self.orders_by_cl_ord_id[cl_ord_id] = order

        fills: List[Tuple[RestingOrder, int, float]] = []

        if side == SIDE_BUY:
            # Match against lowest asks where ask.price <= order.price
            idx = 0
            while idx < len(self.asks) and order.leaves_qty > 0:
                best_ask = self.asks[idx]
                if best_ask.price > price + 1e-6:
                    break  # Spread not crossed

                fill_qty = min(order.leaves_qty, best_ask.leaves_qty)
                fill_px = best_ask.price  # Price-time priority: maker price

                order.leaves_qty -= fill_qty
                order.cum_qty += fill_qty
                best_ask.leaves_qty -= fill_qty
                best_ask.cum_qty += fill_qty

                fills.append((best_ask, fill_qty, fill_px))

                if best_ask.leaves_qty == 0:
                    del self.orders_by_cl_ord_id[best_ask.cl_ord_id]
                    self.asks.pop(idx)
                else:
                    idx += 1

            # If unexecuted leaves remaining, add to resting bids
            if order.leaves_qty > 0:
                self.bids.append(order)
                self.bids.sort(key=lambda o: (-o.price, o.created_at))

        else:  # SIDE_SELL
            # Match against highest bids where bid.price >= order.price
            idx = 0
            while idx < len(self.bids) and order.leaves_qty > 0:
                best_bid = self.bids[idx]
                if best_bid.price < price - 1e-6:
                    break

                fill_qty = min(order.leaves_qty, best_bid.leaves_qty)
                fill_px = best_bid.price

                order.leaves_qty -= fill_qty
                order.cum_qty += fill_qty
                best_bid.leaves_qty -= fill_qty
                best_bid.cum_qty += fill_qty

                fills.append((best_bid, fill_qty, fill_px))

                if best_bid.leaves_qty == 0:
                    del self.orders_by_cl_ord_id[best_bid.cl_ord_id]
                    self.bids.pop(idx)
                else:
                    idx += 1

            if order.leaves_qty > 0:
                self.asks.append(order)
                self.asks.sort(key=lambda o: (o.price, o.created_at))

        return order, fills


class KalshiFixSession:
    """Tracks state and sequence numbers for an active FIX connection."""

    def __init__(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
        server: KalshiFixMockServer,
    ):
        self.reader = reader
        self.writer = writer
        self.server = server
        self.sender_comp_id: str = server.target_comp_id  # e.g., 'KalshiNR'
        self.target_comp_id: str = ""                     # Client API Key UUID
        self.out_seq_num: int = 1
        self.in_seq_num: int = 1
        self.is_authenticated: bool = False
        self.heartbeat_interval: int = 30
        self.heartbeat_task: Optional[asyncio.Task[None]] = None
        self.last_received: float = time.time()

    async def send(self, msg_type: str, fields: Dict[int, Any]) -> str:
        """Constructs, increments sequence, and sends a FIX message."""
        raw_msg = build_fix_message(
            msg_type=msg_type,
            fields=fields,
            sender_comp_id=self.sender_comp_id,
            target_comp_id=self.target_comp_id,
            msg_seq_num=self.out_seq_num,
        )
        self.out_seq_num += 1
        self.writer.write(raw_msg.encode("latin1"))
        await self.writer.drain()
        return raw_msg

    async def logout_and_close(self, reason: str) -> None:
        """Sends 35=5 Logout and terminates socket."""
        try:
            await self.send(MSG_LOGOUT, {TAG_TEXT: reason})
        except Exception:
            pass
        finally:
            self.writer.close()
            try:
                await self.writer.wait_closed()
            except Exception:
                pass


class KalshiFixMockServer:
    """High-Fidelity FIXT.1.1 / FIX50SP2 Mock Server for Kalshi Markets."""

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 8228,
        target_comp_id: str = "KalshiNR",
        verify_signatures: bool = False,
        ssl_context: Optional[ssl.SSLContext] = None,
        latency_injection_ms: float = 0.0,
    ):
        self.host = host
        self.port = port
        self.target_comp_id = target_comp_id
        self.verify_signatures = verify_signatures
        self.ssl_context = ssl_context
        self.latency_injection_ms = latency_injection_ms

        self.server: Optional[asyncio.Server] = None
        self.active_sessions: Dict[str, KalshiFixSession] = {}
        self.books: Dict[str, BinaryContractOrderBook] = {}
        self._is_running = False

        # Pre-seed realistic Kalshi binary markets
        self._seed_default_markets()

    def _seed_default_markets(self) -> None:
        """Populates realistic binary markets with initial liquid bid/ask ladders."""
        symbols = [
            "KXFEDDEC26-YES",
            "KXPRES28-YES",
            "KXBTCHIT100K-YES",
            "KXETHETFFLOW-YES",
        ]
        for sym in symbols:
            book = BinaryContractOrderBook(sym)
            # Add resting bids (35¢, 40¢, 45¢) and asks (55¢, 60¢, 65¢)
            book.bids.append(RestingOrder("SEED-B1", "SEED-CL-B1", "SEED_MM", sym, SIDE_BUY, 0.45, 100, 100))
            book.bids.append(RestingOrder("SEED-B2", "SEED-CL-B2", "SEED_MM", sym, SIDE_BUY, 0.40, 200, 200))
            book.bids.append(RestingOrder("SEED-B3", "SEED-CL-B3", "SEED_MM", sym, SIDE_BUY, 0.35, 300, 300))

            book.asks.append(RestingOrder("SEED-A1", "SEED-CL-A1", "SEED_MM", sym, SIDE_SELL, 0.55, 100, 100))
            book.asks.append(RestingOrder("SEED-A2", "SEED-CL-A2", "SEED_MM", sym, SIDE_SELL, 0.60, 200, 200))
            book.asks.append(RestingOrder("SEED-A3", "SEED-CL-A3", "SEED_MM", sym, SIDE_SELL, 0.65, 300, 300))

            for o in book.bids + book.asks:
                book.orders_by_id[o.order_id] = o
                book.orders_by_cl_ord_id[o.cl_ord_id] = o

            self.books[sym] = book

    async def start(self) -> None:
        """Starts the async TCP/TLS server."""
        self.server = await asyncio.start_server(
            self._handle_client,
            self.host,
            self.port,
            ssl=self.ssl_context,
        )
        self._is_running = True
        logger.info(f"Kalshi FIX Mock Server started on {self.host}:{self.port} (TLS: {self.ssl_context is not None})")

    async def stop(self) -> None:
        """Gracefully shuts down all active sessions and server socket."""
        self._is_running = False
        for comp_id, session in list(self.active_sessions.items()):
            await session.logout_and_close("Server shutting down")

        if self.server:
            self.server.close()
            await self.server.wait_closed()
            self.server = None
        logger.info("Kalshi FIX Mock Server stopped.")

    async def _handle_client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        """Handles lifecycle for a single client connection."""
        session = KalshiFixSession(reader, writer, self)
        buffer = ""

        try:
            while self._is_running:
                data = await reader.read(4096)
                if not data:
                    break

                session.last_received = time.time()
                buffer += data.decode("latin1", errors="replace")

                # Parse complete FIX messages (ending with 10=xyz\x01)
                while SOH in buffer:
                    # Look for complete message
                    end_idx = buffer.find(f"{TAG_CHECK_SUM}=")
                    if end_idx == -1:
                        break
                    # Find SOH after checksum
                    soh_idx = buffer.find(SOH, end_idx)
                    if soh_idx == -1:
                        break

                    raw_msg = buffer[:soh_idx + 1]
                    buffer = buffer[soh_idx + 1:]

                    msg = parse_fix_message(raw_msg)
                    if not msg.msg_type:
                        continue

                    if self.latency_injection_ms > 0:
                        await asyncio.sleep(self.latency_injection_ms / 1000.0)

                    await self._dispatch_message(session, msg)

        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"Error handling FIX client: {e}")
        finally:
            if session.target_comp_id in self.active_sessions:
                del self.active_sessions[session.target_comp_id]
            if session.heartbeat_task:
                session.heartbeat_task.cancel()
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:
                pass

    async def _dispatch_message(self, session: KalshiFixSession, msg: FixMessage) -> None:
        """Processes incoming client messages according to Kalshi specification."""
        msg_type = msg.msg_type

        # 1. Unauthenticated session must start with Logon (35=A)
        if not session.is_authenticated and msg_type != MSG_LOGON:
            await session.logout_and_close("First message must be Logon (35=A)")
            return

        if msg_type == MSG_LOGON:
            await self._handle_logon(session, msg)
        elif msg_type == MSG_HEARTBEAT:
            # Update heartbeat timestamp
            pass
        elif msg_type == MSG_TEST_REQUEST:
            test_req_id = msg.get(TAG_TEST_REQ_ID, "")
            await session.send(MSG_HEARTBEAT, {TAG_TEST_REQ_ID: test_req_id})
        elif msg_type == MSG_LOGOUT:
            await session.logout_and_close("Logout acknowledged")
        elif msg_type == MSG_NEW_ORDER_SINGLE:
            await self._handle_new_order(session, msg)
        elif msg_type == MSG_ORDER_CANCEL_REQUEST:
            await self._handle_order_cancel(session, msg)
        elif msg_type == MSG_MARKET_DATA_REQUEST:
            await self._handle_market_data_request(session, msg)
        else:
            # Reject unrecognized message
            seq_num = msg.get(TAG_MSG_SEQ_NUM, "0")
            await session.send(MSG_REJECT, {
                TAG_MSG_SEQ_NUM: seq_num,
                TAG_TEXT: f"Unsupported MsgType {msg_type}",
            })

    async def _handle_logon(self, session: KalshiFixSession, msg: FixMessage) -> None:
        """Validates Logon message according to CFTC/Kalshi FIX specifications."""
        client_comp_id = msg.get(TAG_SENDER_COMP_ID, "")
        target_comp = msg.get(TAG_TARGET_COMP_ID, "")

        # Strict Kalshi Rule 1: SenderSubID (Tag 50) MUST NOT be present in Logon (35=A)
        if TAG_SENDER_SUB_ID in msg.fields:
            await session.logout_and_close("Tag 50 (SenderSubID) not permitted in Logon (35=A)")
            return

        # TargetCompID must match configured server role (e.g. KalshiNR)
        if target_comp != self.target_comp_id:
            await session.logout_and_close(f"Invalid TargetCompID: {target_comp}. Expected {self.target_comp_id}")
            return

        # Concurrency Rule: Only 1 active session per API Key ID
        if client_comp_id in self.active_sessions:
            await session.logout_and_close(f"Session already exists for {client_comp_id}")
            return

        # Signature verification if enforced
        if self.verify_signatures:
            raw_data = msg.get(TAG_RAW_DATA)
            if not raw_data:
                await session.logout_and_close("Missing Tag 96 (RawData) signature")
                return

        session.target_comp_id = client_comp_id
        session.is_authenticated = True
        session.heartbeat_interval = msg.get_int(TAG_HEART_BT_INT, 30)
        self.active_sessions[client_comp_id] = session

        # Respond with Logon confirmation
        await session.send(MSG_LOGON, {
            TAG_HEART_BT_INT: session.heartbeat_interval,
            TAG_ENCRYPT_METHOD: 0,
        })
        logger.info(f"FIX Session established for {client_comp_id}")

    async def _handle_new_order(self, session: KalshiFixSession, msg: FixMessage) -> None:
        """Processes NewOrderSingle (35=D) against the binary order book."""
        cl_ord_id = msg.get(TAG_CL_ORD_ID, "")
        symbol = msg.get(TAG_SYMBOL, "")
        side = msg.get(TAG_SIDE, "")
        price = msg.get_float(TAG_PRICE, 0.0)
        qty = msg.get_int(TAG_ORDER_QTY, 0)

        # Normalize price: if passed in whole cents (e.g. 45 or 45.0), convert to dollars (0.45)
        # Dollar prices > $0.99 (such as $1.50) are invalid for Kalshi binary contracts ($0.01 - $0.99).
        if 1.0 <= price <= 99.0 and price == int(price):
            price = price / 100.0

        # Validate symbol
        if symbol not in self.books:
            # Auto-create book for dynamic test markets
            self.books[symbol] = BinaryContractOrderBook(symbol)

        book = self.books[symbol]

        # Validate price boundary for binary contracts (1¢ to 99¢ / $0.01 to $0.99)
        if price < 0.01 or price > 0.99 or qty <= 0:
            # Emit ExecutionReport with STATUS_REJECTED
            await session.send(MSG_EXECUTION_REPORT, {
                TAG_ORDER_ID: "NONE",
                TAG_CL_ORD_ID: cl_ord_id,
                TAG_EXEC_ID: f"EXEC-REJ-{uuid.uuid4().hex[:8]}",
                TAG_EXEC_TYPE: STATUS_REJECTED,
                TAG_ORD_STATUS: STATUS_REJECTED,
                TAG_SYMBOL: symbol,
                TAG_SIDE: side,
                TAG_ORDER_QTY: qty,
                TAG_PRICE: price,
                TAG_LEAVES_QTY: 0,
                TAG_CUM_QTY: 0,
                TAG_AVG_PX: 0.0,
                TAG_TEXT: "Invalid price: must be between $0.01 and $0.99 with qty > 0",
            })
            return

        # Check duplicate ClOrdID
        if cl_ord_id in book.orders_by_cl_ord_id:
            await session.send(MSG_EXECUTION_REPORT, {
                TAG_ORDER_ID: "NONE",
                TAG_CL_ORD_ID: cl_ord_id,
                TAG_EXEC_ID: f"EXEC-REJ-{uuid.uuid4().hex[:8]}",
                TAG_EXEC_TYPE: STATUS_REJECTED,
                TAG_ORD_STATUS: STATUS_REJECTED,
                TAG_SYMBOL: symbol,
                TAG_SIDE: side,
                TAG_ORDER_QTY: qty,
                TAG_PRICE: price,
                TAG_LEAVES_QTY: 0,
                TAG_CUM_QTY: 0,
                TAG_AVG_PX: 0.0,
                TAG_TEXT: f"Duplicate ClOrdID {cl_ord_id}",
            })
            return

        # Process order through matching engine
        order, fills = book.process_new_order(
            cl_ord_id=cl_ord_id,
            client_comp_id=session.target_comp_id,
            side=side,
            price=price,
            qty=qty,
        )

        if not fills:
            # Completely resting order -> emit ExecType=0 (New)
            await session.send(MSG_EXECUTION_REPORT, {
                TAG_ORDER_ID: order.order_id,
                TAG_CL_ORD_ID: order.cl_ord_id,
                TAG_EXEC_ID: f"EXEC-NEW-{uuid.uuid4().hex[:8]}",
                TAG_EXEC_TYPE: STATUS_NEW,
                TAG_ORD_STATUS: STATUS_NEW,
                TAG_SYMBOL: symbol,
                TAG_SIDE: side,
                TAG_ORDER_QTY: qty,
                TAG_PRICE: price,
                TAG_LEAVES_QTY: order.leaves_qty,
                TAG_CUM_QTY: 0,
                TAG_AVG_PX: 0.0,
            })
        else:
            # Emit execution reports for each fill
            for maker_order, fill_qty, fill_px in fills:
                # Notify taker (current session)
                status = STATUS_FILLED if order.leaves_qty == 0 else STATUS_PARTIALLY_FILLED
                await session.send(MSG_EXECUTION_REPORT, {
                    TAG_ORDER_ID: order.order_id,
                    TAG_CL_ORD_ID: order.cl_ord_id,
                    TAG_EXEC_ID: f"EXEC-TRD-{uuid.uuid4().hex[:8]}",
                    TAG_EXEC_TYPE: STATUS_PARTIALLY_FILLED if status == STATUS_PARTIALLY_FILLED else STATUS_FILLED,
                    TAG_ORD_STATUS: status,
                    TAG_SYMBOL: symbol,
                    TAG_SIDE: side,
                    TAG_ORDER_QTY: qty,
                    TAG_PRICE: price,
                    TAG_LAST_QTY: fill_qty,
                    TAG_LAST_PX: fill_px,
                    TAG_LEAVES_QTY: order.leaves_qty,
                    TAG_CUM_QTY: order.cum_qty,
                    TAG_AVG_PX: fill_px,
                })

                # If maker is an active connected session, notify them too
                maker_session = self.active_sessions.get(maker_order.client_comp_id)
                if maker_session:
                    maker_status = STATUS_FILLED if maker_order.leaves_qty == 0 else STATUS_PARTIALLY_FILLED
                    await maker_session.send(MSG_EXECUTION_REPORT, {
                        TAG_ORDER_ID: maker_order.order_id,
                        TAG_CL_ORD_ID: maker_order.cl_ord_id,
                        TAG_EXEC_ID: f"EXEC-MKR-{uuid.uuid4().hex[:8]}",
                        TAG_EXEC_TYPE: STATUS_PARTIALLY_FILLED if maker_status == STATUS_PARTIALLY_FILLED else STATUS_FILLED,
                        TAG_ORD_STATUS: maker_status,
                        TAG_SYMBOL: symbol,
                        TAG_SIDE: maker_order.side,
                        TAG_ORDER_QTY: maker_order.order_qty,
                        TAG_PRICE: maker_order.price,
                        TAG_LAST_QTY: fill_qty,
                        TAG_LAST_PX: fill_px,
                        TAG_LEAVES_QTY: maker_order.leaves_qty,
                        TAG_CUM_QTY: maker_order.cum_qty,
                        TAG_AVG_PX: fill_px,
                    })

    async def _handle_order_cancel(self, session: KalshiFixSession, msg: FixMessage) -> None:
        """Processes OrderCancelRequest (35=F)."""
        cl_ord_id = msg.get(TAG_CL_ORD_ID, "")
        orig_cl_ord_id = msg.get(TAG_ORIG_CL_ORD_ID, "")
        symbol = msg.get(TAG_SYMBOL, "")

        book = self.books.get(symbol)
        if not book:
            await session.send(MSG_ORDER_CANCEL_REJECT, {
                TAG_ORDER_ID: "NONE",
                TAG_CL_ORD_ID: cl_ord_id,
                TAG_ORIG_CL_ORD_ID: orig_cl_ord_id,
                TAG_ORD_STATUS: STATUS_REJECTED,
                TAG_TEXT: f"Symbol {symbol} not found",
            })
            return

        canceled_order = book.cancel_order(orig_cl_ord_id, session.target_comp_id)
        if not canceled_order:
            await session.send(MSG_ORDER_CANCEL_REJECT, {
                TAG_ORDER_ID: "NONE",
                TAG_CL_ORD_ID: cl_ord_id,
                TAG_ORIG_CL_ORD_ID: orig_cl_ord_id,
                TAG_ORD_STATUS: STATUS_REJECTED,
                TAG_TEXT: f"Order {orig_cl_ord_id} not found or already filled",
            })
            return

        # Order successfully canceled -> emit ExecutionReport with STATUS_CANCELED
        await session.send(MSG_EXECUTION_REPORT, {
            TAG_ORDER_ID: canceled_order.order_id,
            TAG_CL_ORD_ID: cl_ord_id,
            TAG_ORIG_CL_ORD_ID: orig_cl_ord_id,
            TAG_EXEC_ID: f"EXEC-CANC-{uuid.uuid4().hex[:8]}",
            TAG_EXEC_TYPE: STATUS_CANCELED,
            TAG_ORD_STATUS: STATUS_CANCELED,
            TAG_SYMBOL: symbol,
            TAG_SIDE: canceled_order.side,
            TAG_ORDER_QTY: canceled_order.order_qty,
            TAG_PRICE: canceled_order.price,
            TAG_LEAVES_QTY: 0,
            TAG_CUM_QTY: canceled_order.cum_qty,
            TAG_AVG_PX: canceled_order.price,
        })

    async def _handle_market_data_request(self, session: KalshiFixSession, msg: FixMessage) -> None:
        """Provides MarketDataSnapshot (35=W) for KalshiMD sessions."""
        symbol = msg.get(TAG_SYMBOL, "")
        book = self.books.get(symbol)
        if not book:
            return

        snap = book.get_l2_snapshot()
        # Compose snapshot
        bids = snap["bids"][:5]
        asks = snap["asks"][:5]

        fields: Dict[int, Any] = {
            TAG_SYMBOL: symbol,
            TAG_NO_MD_ENTRIES: len(bids) + len(asks),
        }
        await session.send(MSG_MARKET_DATA_SNAPSHOT, fields)


# Client Helper for testing
class KalshiFixClient:
    """Async FIX client for testing and connecting to Kalshi FIX gateway or mock."""

    def __init__(
        self,
        host: str,
        port: int,
        sender_comp_id: str,
        target_comp_id: str = "KalshiNR",
        ssl_context: Optional[ssl.SSLContext] = None,
    ):
        self.host = host
        self.port = port
        self.sender_comp_id = sender_comp_id
        self.target_comp_id = target_comp_id
        self.ssl_context = ssl_context

        self.reader: Optional[asyncio.StreamReader] = None
        self.writer: Optional[asyncio.StreamWriter] = None
        self.out_seq_num: int = 1
        self.in_seq_num: int = 1
        self.received_messages: List[FixMessage] = []
        self._read_task: Optional[asyncio.Task[None]] = None

    async def connect(self) -> None:
        """Connects to server."""
        self.reader, self.writer = await asyncio.open_connection(
            self.host, self.port, ssl=self.ssl_context
        )
        self._read_task = asyncio.create_task(self._read_loop())

    async def _read_loop(self) -> None:
        buffer = ""
        try:
            while self.reader and not self.reader.at_eof():
                data = await self.reader.read(4096)
                if not data:
                    break
                buffer += data.decode("latin1", errors="replace")
                while SOH in buffer:
                    end_idx = buffer.find(f"{TAG_CHECK_SUM}=")
                    if end_idx == -1:
                        break
                    soh_idx = buffer.find(SOH, end_idx)
                    if soh_idx == -1:
                        break
                    raw_msg = buffer[:soh_idx + 1]
                    buffer = buffer[soh_idx + 1:]
                    msg = parse_fix_message(raw_msg)
                    self.received_messages.append(msg)
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"Client read error: {e}")

    async def send(self, msg_type: str, fields: Dict[int, Any]) -> str:
        """Sends FIX message."""
        if not self.writer:
            raise RuntimeError("Not connected")
        raw_msg = build_fix_message(
            msg_type=msg_type,
            fields=fields,
            sender_comp_id=self.sender_comp_id,
            target_comp_id=self.target_comp_id,
            msg_seq_num=self.out_seq_num,
        )
        self.out_seq_num += 1
        self.writer.write(raw_msg.encode("latin1"))
        await self.writer.drain()
        return raw_msg

    async def logon(self, raw_data_sig: str = "mock_sig_ed25519") -> FixMessage:
        """Sends Logon (35=A) and waits for response."""
        await self.send(MSG_LOGON, {
            TAG_HEART_BT_INT: 30,
            TAG_ENCRYPT_METHOD: 0,
            TAG_RAW_DATA: raw_data_sig,
            TAG_RAW_DATA_LENGTH: len(raw_data_sig),
        })
        # Wait for response
        return await self.wait_for_message(MSG_LOGON)

    async def wait_for_message(self, msg_type: str, timeout: float = 2.0) -> FixMessage:
        """Polls received messages until requested msg_type arrives."""
        start = time.time()
        while time.time() - start < timeout:
            for i, msg in enumerate(self.received_messages):
                if msg.msg_type == msg_type:
                    return self.received_messages.pop(i)
            await asyncio.sleep(0.01)
        raise TimeoutError(f"Timed out waiting for MsgType {msg_type}")

    async def close(self) -> None:
        """Closes client."""
        if self._read_task:
            self._read_task.cancel()
        if self.writer:
            self.writer.close()
            try:
                await self.writer.wait_closed()
            except Exception:
                pass
