import asyncio
import json
import logging
import urllib.request

import websockets

logger = logging.getLogger(__name__)


class DerivClient:
    def __init__(self, app_id=None, api_token=None, use_demo=True):
        self.app_id = app_id
        self.api_token = api_token
        self.use_demo = use_demo
        self.base_url = "wss://api.derivws.com/trading/v1/options/ws/public"
        self.ws = None
        self.callbacks = {}
        self.req_id_counter = 1
        self._listen_task = None
        self.account_id = None
        self._tick_symbols = []
        self._tick_callback = None
        self._closing = False
        self._reconnects = 0

    async def _get_auth_url(self):
        loop = asyncio.get_running_loop()

        def fetch_accounts():
            request = urllib.request.Request("https://api.derivws.com/trading/v1/options/accounts")
            request.add_header("Authorization", f"Bearer {self.api_token}")
            request.add_header("Deriv-App-ID", str(self.app_id))
            request.add_header("User-Agent", "Codex-DerivDemo/1.0")
            with urllib.request.urlopen(request) as response:
                return json.loads(response.read().decode())

        def fetch_otp(account_id):
            request = urllib.request.Request(
                f"https://api.derivws.com/trading/v1/options/accounts/{account_id}/otp",
                method="POST",
            )
            request.add_header("Authorization", f"Bearer {self.api_token}")
            request.add_header("Deriv-App-ID", str(self.app_id))
            request.add_header("User-Agent", "Codex-DerivDemo/1.0")
            request.add_header("Content-Length", "0")
            with urllib.request.urlopen(request) as response:
                return json.loads(response.read().decode())

        account_data = await loop.run_in_executor(None, fetch_accounts)
        if self.use_demo:
            target_account = next(
                (account for account in account_data.get("data", []) if account.get("account_type") == "demo"),
                None,
            )
        else:
            target_account = next(
                (account for account in account_data.get("data", []) if account.get("account_type") != "demo"),
                None,
            )
        if not target_account:
            raise ValueError(f"No {'Demo' if self.use_demo else 'Real'} account found!")
        self.account_id = target_account["account_id"]
        otp_data = await loop.run_in_executor(None, fetch_otp, self.account_id)
        return f"{otp_data['data']['url']}&app_id={self.app_id}"

    async def _open_ws(self):
        if self.api_token and self.app_id:
            url = await self._get_auth_url()
        else:
            url = f"{self.base_url}?app_id={self.app_id}" if self.app_id else self.base_url
        self.ws = await websockets.connect(url, ping_interval=15, ping_timeout=45)

    async def connect(self):
        self._closing = False
        await self._open_ws()
        self._listen_task = asyncio.create_task(self._listen())

    async def disconnect(self):
        self._closing = True
        if self.ws:
            await self.ws.close()
        if self._listen_task:
            self._listen_task.cancel()

    def _fail_pending(self, reason):
        for request_id in list(self.callbacks):
            if request_id in ("tick", "ohlc"):
                continue
            future = self.callbacks.pop(request_id, None)
            if isinstance(future, asyncio.Future) and not future.done():
                future.set_exception(ConnectionError(reason))

    async def _resubscribe(self):
        if self._tick_callback:
            self.callbacks["tick"] = self._tick_callback
        for symbol in list(self._tick_symbols):
            self.req_id_counter += 1
            await self.ws.send(json.dumps({"ticks": symbol, "subscribe": 1, "req_id": self.req_id_counter}))

    async def _reconnect(self):
        self._fail_pending("ws reconnecting")
        backoff = 1
        while not self._closing:
            self._reconnects += 1
            try:
                await self._open_ws()
                await self._resubscribe()
                print(
                    f"  [reconnect] WS reconectado (#{self._reconnects}); "
                    f"resubscrito {len(self._tick_symbols)} simbolos",
                    flush=True,
                )
                return
            except Exception as error:
                logger.error("reconnect failed: %s", error)
                print(f"  [reconnect] falhou: {error}; retry em {backoff}s", flush=True)
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 30)

    async def _listen(self):
        while not self._closing:
            try:
                async for message in self.ws:
                    data = json.loads(message)
                    request_id = data.get("req_id")
                    message_type = data.get("msg_type")
                    if request_id and request_id in self.callbacks:
                        future = self.callbacks.pop(request_id)
                        if isinstance(future, asyncio.Future) and not future.done():
                            future.set_result(data)
                    if message_type == "tick" and "tick" in self.callbacks:
                        callback = self.callbacks["tick"]
                        if asyncio.iscoroutinefunction(callback):
                            await callback(data)
                        else:
                            callback(data)
                    elif message_type == "ohlc" and "ohlc" in self.callbacks:
                        callback = self.callbacks["ohlc"]
                        if asyncio.iscoroutinefunction(callback):
                            await callback(data)
                        else:
                            callback(data)
            except asyncio.CancelledError:
                return
            except Exception as error:
                logger.error("Error in listen loop: %s", error)
            if self._closing:
                return
            await self._reconnect()

    async def send_request(self, payload):
        if not self.ws:
            raise RuntimeError("Not connected to WebSocket")
        request_id = self.req_id_counter
        self.req_id_counter += 1
        payload["req_id"] = request_id
        future = asyncio.get_running_loop().create_future()
        self.callbacks[request_id] = future
        try:
            await self.ws.send(json.dumps(payload))
        except Exception:
            self.callbacks.pop(request_id, None)
            raise
        try:
            return await future
        finally:
            self.callbacks.pop(request_id, None)

    async def buy_contract(self, proposal_id, price):
        return await self.send_request({"buy": proposal_id, "price": price})

    async def sell_contract(self, contract_id, price=0):
        return await self.send_request({"sell": contract_id, "price": price})
