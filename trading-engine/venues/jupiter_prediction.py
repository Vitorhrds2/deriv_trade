"""Jupiter Prediction API (api.jup.ag/prediction/v1) -- agrega liquidez de Polymarket E Kalshi
numa API so, paga em USDC/JupUSD via carteira Solana (Phantom serve). Ver
docs/phantom_ecosystem_findings.md pro levantamento completo.

STATUS: NAO TESTADO -- ao contrario de binance.py/polymarket.py (validados ao vivo), esta API
exige `x-api-key` em TODA chamada, inclusive leitura, entao nao da pra validar sem uma key gerada
em https://developers.jup.ag/portal (acao do usuario, mesma limitacao ja explicada pra criar
conta na Polymarket -- nao posso gerar isso). Assim que existir JUPITER_API_KEY no ambiente,
rodar um smoke test real (GET /events) antes de confiar em qualquer coisa aqui, mesma disciplina
usada nos outros adapters.

So implementa a camada de LEITURA (PriceFeedVenue) de proposito: executar ordem de verdade exige
assinar transacao Solana (chave privada da carteira), o que e uma decisao separada -- ver
ExecutionVenue em base.py e a ressalva de seguranca em docs/polymarket_dev_reference.md, que se
aplica aqui do mesmo jeito.

Nomes de campo vem direto de developers.jup.ag/docs/guides/how-to-build-a-prediction-market-app-
on-solana (Response format / Market) -- nao inventados.
"""
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Awaitable, Callable, Optional

from dotenv import load_dotenv

from .base import PriceFeedVenue, PriceUpdate
from .registry import register

BASE_URL = "https://api.jup.ag/prediction/v1"


class JupiterAuthError(RuntimeError):
    pass


@register
class JupiterPredictionVenue(PriceFeedVenue):
    name = "jupiter_prediction"
    requires_credentials = True  # API key exigida ate pra leitura, diferente de binance/polymarket

    def __init__(self, api_key: Optional[str] = None, poll_interval_s: float = 2.0):
        load_dotenv()
        self.api_key = api_key or os.getenv("JUPITER_API_KEY")
        self.poll_interval_s = poll_interval_s

    def _get(self, path: str, params: Optional[dict] = None, timeout: int = 10) -> dict:
        if not self.api_key:
            raise JupiterAuthError("JUPITER_API_KEY nao configurada (nem passada explicitamente)")
        url = f"{BASE_URL}{path}"
        if params:
            url += "?" + urllib.parse.urlencode(params)
        req = urllib.request.Request(url, headers={"x-api-key": self.api_key})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            raise JupiterAuthError(f"Jupiter API retornou {e.code}: {e.read().decode('utf-8', 'ignore')}") from e

    async def connect(self) -> None:
        return None

    async def disconnect(self) -> None:
        return None

    def list_events(self, category: str = "crypto", provider: str = "polymarket", live_only: bool = False) -> list:
        """GET /events -- provider: 'polymarket' (default da API) ou 'kalshi'."""
        params = {"category": category, "provider": provider}
        if live_only:
            params["filter"] = "live"
        data = self._get("/events", params)
        return data.get("data", data) if isinstance(data, dict) else data

    def get_market(self, market_id: str) -> dict:
        data = self._get(f"/markets/{market_id}")
        return data.get("data", data) if isinstance(data, dict) else data

    async def get_price(self, symbol: str) -> float:
        """symbol aqui = marketId. Retorna buyYesPriceUsd convertido de micro-USD pra USD."""
        import asyncio
        loop = asyncio.get_running_loop()
        market = await loop.run_in_executor(None, self.get_market, symbol)
        pricing = market.get("pricing", {})
        micro = pricing.get("buyYesPriceUsd")
        if micro is None:
            raise RuntimeError(f"sem buyYesPriceUsd pro market {symbol} (status={market.get('status')})")
        return float(micro) / 1_000_000

    async def stream(self, symbols: list, on_update: Callable[[PriceUpdate], Awaitable[None]]) -> None:
        """Poll -- a API nao documenta um canal WS publico (diferente do CLOB direto da
        Polymarket, que tem wss://ws-subscriptions-clob.polymarket.com/ws/market)."""
        import asyncio
        while True:
            for market_id in symbols:
                try:
                    price = await self.get_price(market_id)
                    await on_update(PriceUpdate(venue=self.name, symbol=market_id, price=price, ts=time.time()))
                except Exception:
                    continue
            await asyncio.sleep(self.poll_interval_s)
