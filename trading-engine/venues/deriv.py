"""Deriv como ExecutionVenue -- ENVELOPA `deriv_client.DerivClient` (nao modifica, nao
reimplementa). Precisa rodar com trading-engine/ no sys.path (mesma convencao de todo o resto
do repo: os scripts sao executados de dentro de trading-engine/).

Contratos de opcao (barrier/duration/multiplier/growth_rate) nao cabem num `place_order()`
generico sem esconder detalhe importante -- por isso os metodos de compra/venda ficam expostos
direto no `DerivClient` (`.client.buy_contract(...)`, `.client.buy_direct(...)`,
`.client.sell_contract(...)`), nao renomeados/achatados aqui. Ver base.py.
"""
import os
import time
from typing import Awaitable, Callable

from dotenv import load_dotenv

from deriv_client import DerivClient

from .base import ExecutionVenue, PriceUpdate
from .registry import register


@register
class DerivVenue(ExecutionVenue):
    name = "deriv"
    requires_credentials = True

    def __init__(self, use_demo: bool = True):
        load_dotenv()
        self.client = DerivClient(
            app_id=os.getenv("DERIV_APP_ID"),
            api_token=os.getenv("DERIV_API_TOKEN"),
            use_demo=use_demo,
        )
        self._last_price: dict = {}

    async def connect(self) -> None:
        await self.client.connect()

    async def disconnect(self) -> None:
        await self.client.disconnect()

    def is_authenticated(self) -> bool:
        return bool(self.client.account_id)

    async def get_balance(self) -> dict:
        return await self.client.get_balance()

    async def get_price(self, symbol: str) -> float:
        if symbol in self._last_price:
            return self._last_price[symbol]
        raise RuntimeError(f"sem preco cacheado pra {symbol}; chame stream() primeiro")

    async def stream(self, symbols: list, on_update: Callable[[PriceUpdate], Awaitable[None]]) -> None:
        async def _on_tick(data):
            tick = data.get("tick", {})
            symbol = tick.get("symbol")
            quote = tick.get("quote")
            if symbol is None or quote is None:
                return
            price = float(quote)
            self._last_price[symbol] = price
            await on_update(PriceUpdate(venue=self.name, symbol=symbol, price=price, ts=time.time(), raw=tick))

        for symbol in symbols:
            await self.client.subscribe_ticks(symbol, _on_tick)
