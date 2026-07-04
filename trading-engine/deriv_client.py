import asyncio
import json
import logging
import websockets
import urllib.request
from urllib.error import HTTPError

logger = logging.getLogger(__name__)

class DerivClient:
    def __init__(self, app_id=None, api_token=None, use_demo=True):
        """
        Deriv WebSocket API Client.
        If api_token is provided, it will automatically fetch the OTP for the demo or real account
        and connect to the authenticated endpoint.
        """
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
        # 1. Fetch accounts to find the specified account
        loop = asyncio.get_running_loop()
        
        def fetch_accounts():
            req = urllib.request.Request("https://api.derivws.com/trading/v1/options/accounts")
            req.add_header("Authorization", f"Bearer {self.api_token}")
            req.add_header("Deriv-App-ID", str(self.app_id))
            req.add_header("User-Agent", "Codex-DerivDemo/1.0")
            with urllib.request.urlopen(req) as response:
                return json.loads(response.read().decode())
                
        def fetch_otp(acc_id):
            req = urllib.request.Request(f"https://api.derivws.com/trading/v1/options/accounts/{acc_id}/otp", method="POST")
            req.add_header("Authorization", f"Bearer {self.api_token}")
            req.add_header("Deriv-App-ID", str(self.app_id))
            req.add_header("User-Agent", "Codex-DerivDemo/1.0")
            req.add_header("Content-Length", "0")
            with urllib.request.urlopen(req) as response:
                return json.loads(response.read().decode())

        try:
            acc_data = await loop.run_in_executor(None, fetch_accounts)
            
            if self.use_demo:
                target_acc = next((acc for acc in acc_data.get("data", []) if acc.get("account_type") == "demo"), None)
            else:
                target_acc = next((acc for acc in acc_data.get("data", []) if acc.get("account_type") != "demo"), None)
                
            if not target_acc:
                raise ValueError(f"No {'Demo' if self.use_demo else 'Real'} account found!")
                
            self.account_id = target_acc["account_id"]
            logger.info(f"Found {'Demo' if self.use_demo else 'Real'} account: {self.account_id}")
            
            otp_data = await loop.run_in_executor(None, fetch_otp, self.account_id)
            ws_url = otp_data["data"]["url"]
            return f"{ws_url}&app_id={self.app_id}"
        except Exception as e:
            logger.error(f"Failed to authenticate: {e}")
            raise
    
    async def _open_ws(self):
        if self.api_token and self.app_id:
            url = await self._get_auth_url()
        else:
            url = f"{self.base_url}?app_id={self.app_id}" if self.app_id else self.base_url
        self.ws = await websockets.connect(url, ping_interval=15, ping_timeout=45)

    async def connect(self):
        self._closing = False
        await self._open_ws()
        logger.info("Connected.")
        self._listen_task = asyncio.create_task(self._listen())

    async def disconnect(self):
        self._closing = True
        if self.ws:
            await self.ws.close()
        if self._listen_task:
            self._listen_task.cancel()
        logger.info("Disconnected.")

    def _fail_pending(self, reason):
        # Falha futures de requests pendentes para os chamadores nao travarem
        # (send_request nao tem timeout). Preserva os callbacks de tick/ohlc.
        for rid in list(self.callbacks):
            if rid in ("tick", "ohlc"):
                continue
            fut = self.callbacks.pop(rid, None)
            if isinstance(fut, asyncio.Future) and not fut.done():
                fut.set_exception(ConnectionError(reason))

    async def _resubscribe(self):
        # Fire-and-forget: roda DENTRO do listen loop (que esta reconectando), entao
        # nao pode usar send_request (deadlock no future). O listen retoma e despacha.
        if self._tick_callback:
            self.callbacks["tick"] = self._tick_callback
        for sym in list(self._tick_symbols):
            self.req_id_counter += 1
            await self.ws.send(json.dumps(
                {"ticks": sym, "subscribe": 1, "req_id": self.req_id_counter}))

    async def _reconnect(self):
        self._fail_pending("ws reconnecting")
        backoff = 1
        while not self._closing:
            self._reconnects += 1
            try:
                await self._open_ws()
                await self._resubscribe()
                print(f"  [reconnect] WS reconectado (#{self._reconnects}); "
                      f"resubscrito {len(self._tick_symbols)} simbolos", flush=True)
                return
            except Exception as e:
                logger.error(f"reconnect failed: {e}")
                print(f"  [reconnect] falhou: {e}; retry em {backoff}s", flush=True)
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 30)

    async def _listen(self):
        while not self._closing:
            try:
                async for message in self.ws:
                    data = json.loads(message)
                    req_id = data.get("req_id")
                    msg_type = data.get("msg_type")

                    if req_id and req_id in self.callbacks:
                        future = self.callbacks.pop(req_id)
                        if isinstance(future, asyncio.Future) and not future.done():
                            future.set_result(data)

                    if msg_type == "tick" and "tick" in self.callbacks:
                        cb = self.callbacks["tick"]
                        if asyncio.iscoroutinefunction(cb):
                            await cb(data)
                        else:
                            cb(data)
                    elif msg_type == "ohlc" and "ohlc" in self.callbacks:
                        cb = self.callbacks["ohlc"]
                        if asyncio.iscoroutinefunction(cb):
                            await cb(data)
                        else:
                            cb(data)
            except asyncio.CancelledError:
                return
            except Exception as e:
                logger.error(f"Error in listen loop: {e}")
            if self._closing:
                return
            # Conexao caiu (close/erro/ping timeout) -> reconecta e resubscreve.
            await self._reconnect()

    async def send_request(self, payload):
        if not self.ws:
            raise RuntimeError("Not connected to WebSocket")
            
        req_id = self.req_id_counter
        self.req_id_counter += 1
        
        payload["req_id"] = req_id
        
        loop = asyncio.get_running_loop()
        future = loop.create_future()
        self.callbacks[req_id] = future
        
        await self.ws.send(json.dumps(payload))
        return await future

    async def ping(self):
        return await self.send_request({"ping": 1})
    
    async def get_balance(self):
        return await self.send_request({"balance": 1})
        
    async def get_proposal(self, contract_type, stake, symbol="1HZ10V", multiplier=None, stop_loss=None, take_profit=None, duration=5, duration_unit="t", growth_rate=None, barrier=None):
        payload = {
            "proposal": 1,
            "amount": stake,
            "basis": "stake",
            "contract_type": contract_type,
            "currency": "USD",
            "underlying_symbol": symbol
        }

        if contract_type == "ACCU" or growth_rate is not None:
            # Accumuladores nao usam duration/duration_unit: rodam ate knockout ou venda manual.
            payload["growth_rate"] = growth_rate if growth_rate is not None else 0.01
            limit_order = {}
            if take_profit:
                limit_order["take_profit"] = take_profit
            if limit_order:
                payload["limit_order"] = limit_order
        elif multiplier:
            payload["multiplier"] = multiplier
            # Multipliers can have limit_orders
            limit_order = {}
            if stop_loss:
                limit_order["stop_loss"] = stop_loss
            if take_profit:
                limit_order["take_profit"] = take_profit
            if limit_order:
                payload["limit_order"] = limit_order
        else:
            payload["duration"] = duration
            payload["duration_unit"] = duration_unit

        if barrier is not None:
            payload["barrier"] = str(barrier)

        return await self.send_request(payload)

    async def get_ticks_history(self, symbol, count=1000, end="latest", start=1):
        """Historico de ticks BRUTOS (nao-candle) -- estilo 'ticks', para replay tick-a-tick."""
        return await self.send_request({
            "ticks_history": symbol,
            "adjust_start_time": 1,
            "count": count,
            "end": end,
            "start": start,
            "style": "ticks"
        })

    async def get_contracts_for(self, symbol):
        return await self.send_request({"contracts_for": symbol})

    async def buy_contract(self, proposal_id, price):
        return await self.send_request({
            "buy": proposal_id,
            "price": price
        })
        
    async def buy_direct(self, contract_type, stake, symbol="1HZ10V", duration=1, duration_unit="t", barrier=None, multiplier=None, stop_loss=None, take_profit=None):
        params = {
            "amount": stake,
            "basis": "stake",
            "contract_type": contract_type,
            "currency": "USD",
            "underlying_symbol": symbol
        }
        
        if multiplier:
            params["multiplier"] = multiplier
            limit_order = {}
            if stop_loss:
                limit_order["stop_loss"] = stop_loss
            if take_profit:
                limit_order["take_profit"] = take_profit
            if limit_order:
                params["limit_order"] = limit_order
        else:
            params["duration"] = duration
            params["duration_unit"] = duration_unit
            
        if barrier is not None:
            params["barrier"] = str(barrier)
            
        return await self.send_request({
            "buy": 1,
            "price": stake,
            "parameters": params
        })
    
    async def sell_contract(self, contract_id, price=0):
        return await self.send_request({
            "sell": contract_id,
            "price": price
        })
    
    async def get_active_symbols(self):
        return await self.send_request({"active_symbols": "brief"})
    
    async def get_candles(self, symbol, count=5000, granularity=60, end="latest"):
        return await self.send_request({
            "ticks_history": symbol,
            "adjust_start_time": 1,
            "count": count,
            "end": end,
            "start": 1,
            "style": "candles",
            "granularity": granularity
        })
    
    async def subscribe_ticks(self, symbol, callback):
        self.callbacks["tick"] = callback
        self._tick_callback = callback
        if symbol not in self._tick_symbols:
            self._tick_symbols.append(symbol)
        return await self.send_request({
            "ticks": symbol,
            "subscribe": 1
        })

    async def subscribe_candles(self, symbol, granularity, callback, count=1):
        self.callbacks["ohlc"] = callback
        return await self.send_request({
            "ticks_history": symbol,
            "style": "candles",
            "granularity": granularity,
            "end": "latest",
            "count": count,
            "subscribe": 1
        })
