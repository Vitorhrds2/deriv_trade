"""Binance como PriceFeedVenue (so leitura -- mesmo uso que ja fazemos hoje em varios scripts:
passive_trigger_probe.py, hft_arbitrage_bot.py, etc, todos com a mesma logica de WS duplicada).

Se/quando "Binance como corretora" (ordem real, spot/futures) entrar em pauta, isso vira um
`BinanceExecutionVenue(ExecutionVenue)` separado, com API key/secret HMAC -- fora de escopo aqui
de proposito (nenhuma hipotese deste repo precisou de execucao na Binance ate agora).
"""
import json
import time
from typing import Awaitable, Callable

import websockets

from .base import PriceFeedVenue, PriceUpdate
from .registry import register


@register
class BinanceVenue(PriceFeedVenue):
    name = "binance"
    requires_credentials = False

    def __init__(self):
        self._ws = None
        self._last_price: dict = {}

    async def connect(self) -> None:
        return None  # conexao e por-simbolo em stream(); sem estado persistente de "sessao"

    async def disconnect(self) -> None:
        if self._ws is not None:
            await self._ws.close()
            self._ws = None

    async def get_price(self, symbol: str) -> float:
        if symbol.lower() in self._last_price:
            return self._last_price[symbol.lower()]
        raise RuntimeError(f"sem preco cacheado pra {symbol}; chame stream() primeiro ou use REST")

    async def stream(self, symbols: list, on_update: Callable[[PriceUpdate], Awaitable[None]]) -> None:
        streams = "/".join(f"{s.lower()}@bookTicker" for s in symbols)
        uri = f"wss://stream.binance.com:9443/stream?streams={streams}"
        async with websockets.connect(uri) as ws:
            self._ws = ws
            async for message in ws:
                data = json.loads(message).get("data", {})
                sym = data.get("s", "").lower()
                ask = data.get("a")
                if not sym or ask is None:
                    continue
                price = float(ask)
                self._last_price[sym] = price
                await on_update(PriceUpdate(venue=self.name, symbol=sym, price=price, ts=time.time(), raw=data))
