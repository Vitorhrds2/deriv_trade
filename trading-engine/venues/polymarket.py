"""Polymarket como PriceFeedVenue (so leitura -- Gamma + CLOB publicos, sem credencial).

Wrapper ENXUTO e ilustrativo pra provar que a interface comum (base.py) acomoda um modelo
REST-poll (Polymarket) tao bem quanto um WS-push (binance.py) -- proposito diferente do
`polymarket_lag_probe.py` (Carlos, branch feat/polymarket-arb), que ja tem a logica completa de
descoberta de janela Up/Down, lead-lag e o A/B PAPER usado no PA5. Nao duplica aquilo por
completo de proposito (ainda nao mergeado nesta branch) -- so implementa o primitivo generico
"preco por token" pra este adapter funcionar sozinho. Quando `feat/polymarket-arb` mergear,
este arquivo deve passar a chamar as funcoes de la em vez de reimplementar `_get`/`best_ask`.
"""
import asyncio
import json
import time
import urllib.parse
import urllib.request
from typing import Awaitable, Callable

from .base import PriceFeedVenue, PriceUpdate
from .registry import register

GAMMA = "https://gamma-api.polymarket.com"
CLOB = "https://clob.polymarket.com"
UA = {"User-Agent": "trading-engine-venues/0.1 (research; read-only)"}


def _get(url: str, timeout: int = 10) -> dict:
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


@register
class PolymarketVenue(PriceFeedVenue):
    name = "polymarket"
    requires_credentials = False

    def __init__(self, poll_interval_s: float = 2.0):
        self.poll_interval_s = poll_interval_s
        self._last_price: dict = {}

    async def connect(self) -> None:
        return None  # REST puro, sem sessao persistente

    async def disconnect(self) -> None:
        return None

    def resolve_token_ids(self, slug: str) -> list:
        """slug de mercado (ex.: 'btc-updown-5m-<epoch>') -> [token_up, token_down]."""
        data = _get(f"{GAMMA}/markets?slug={urllib.parse.quote(slug)}")
        rows = data if isinstance(data, list) else data.get("data", [])
        if not rows:
            raise RuntimeError(f"mercado nao encontrado: {slug}")
        raw = rows[0].get("clobTokenIds") or "[]"
        return json.loads(raw) if isinstance(raw, str) else raw

    async def get_price(self, symbol: str) -> float:
        """symbol aqui = token_id do CLOB (ver resolve_token_ids). Retorna melhor ask."""
        loop = asyncio.get_running_loop()
        book = await loop.run_in_executor(None, _get, f"{CLOB}/book?token_id={urllib.parse.quote(symbol)}")
        asks = [float(level["price"]) for level in book.get("asks", [])]
        if not asks:
            raise RuntimeError(f"sem ask no book pra token {symbol}")
        price = min(asks)
        self._last_price[symbol] = price
        return price

    async def stream(self, symbols: list, on_update: Callable[[PriceUpdate], Awaitable[None]]) -> None:
        """Poll simples (o publico da Polymarket usado ate aqui neste repo e REST, nao WS --
        ver docs/polymarket_dev_reference.md pro endpoint WS publico oficial, ainda nao
        validado por nenhum script daqui)."""
        while True:
            for token_id in symbols:
                try:
                    price = await self.get_price(token_id)
                    await on_update(PriceUpdate(venue=self.name, symbol=token_id, price=price, ts=time.time()))
                except Exception:
                    continue
            await asyncio.sleep(self.poll_interval_s)
