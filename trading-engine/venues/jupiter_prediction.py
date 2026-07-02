"""Jupiter Prediction API (api.jup.ag/prediction/v1) -- agrega liquidez de Polymarket E Kalshi
numa API so, paga em USDC/JupUSD via carteira Solana (Phantom serve). Ver
docs/phantom_ecosystem_findings.md pro levantamento completo.

STATUS: VALIDADO AO VIVO (2026-07-02, com JUPITER_API_KEY real do usuario) -- COM RESSALVA DE
CONFIABILIDADE.
- Autenticacao e dados: OK. `list_events()` (GET /events) retorna eventos/markets reais
  (ex.: "What price will Bitcoin hit in July?") com `pricing` ja embutido por market.
- Fix aplicado: `urllib` manda `User-Agent: Python-urllib/x.y` por padrao, que o WAF (Cloudflare)
  na frente da api.jup.ag barra com 403 "error code: 1010" mesmo com key valida -- `_get()` agora
  manda um User-Agent explicito.
- **A API tem falha intermitente real** (timeout sem resposta), pior em GET /markets/{id}
  (~40% em 7 tentativas) mas tambem observada em GET /events (1/6, e uma vez com falha nas 3
  tentativas seguidas mesmo com retry+backoff -- ou seja, existem janelas de instabilidade mais
  amplas, nao so glitches isolados por request). Mitigacoes aplicadas em `_get()`: retry
  automatico (3 tentativas, backoff 1.5s) + `get_market()` cai pra varrer `list_events()` se
  `/markets/{id}` direto falhar. Isso reduz mas NAO elimina falhas -- callers devem tratar
  `JupiterAPIError` como esperado (`stream()` ja faz isso via `except Exception: continue` por
  symbol/ciclo). Detalhes e numeros completos em docs/phantom_ecosystem_findings.md.

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


class JupiterAPIError(RuntimeError):
    """Timeout/erro de conexao -- distinto de erro de auth (401/403). Visto ao vivo em
    2026-07-02: /markets/{id} deu timeout intermitente (funcionou 1x, travou nas 3
    tentativas seguintes, via curl E via Python, geral -- nao e bug de client) enquanto
    /events nunca falhou. Ver docs/phantom_ecosystem_findings.md."""
    pass


@register
class JupiterPredictionVenue(PriceFeedVenue):
    name = "jupiter_prediction"
    requires_credentials = True  # API key exigida ate pra leitura, diferente de binance/polymarket

    def __init__(self, api_key: Optional[str] = None, poll_interval_s: float = 2.0):
        load_dotenv()
        self.api_key = api_key or os.getenv("JUPITER_API_KEY")
        self.poll_interval_s = poll_interval_s

    def _get(self, path: str, params: Optional[dict] = None, timeout: int = 10, retries: int = 2) -> dict:
        if not self.api_key:
            raise JupiterAuthError("JUPITER_API_KEY nao configurada (nem passada explicitamente)")
        url = f"{BASE_URL}{path}"
        if params:
            url += "?" + urllib.parse.urlencode(params)
        # User-Agent explicito: o default do urllib ("Python-urllib/x.y") e barrado pelo WAF
        # do Cloudflare na frente da api.jup.ag (HTTP 403, "error code: 1010") mesmo com
        # x-api-key valida. curl passa porque manda um UA diferente.
        req = urllib.request.Request(
            url,
            headers={
                "x-api-key": self.api_key,
                "User-Agent": "Mozilla/5.0 (compatible; hypothesis-research-bot/1.0)",
                "Accept": "application/json",
            },
        )
        # Retry com backoff curto: confirmado ao vivo que a api.jup.ag tem falha intermitente
        # (timeout sem resposta) em QUALQUER rota, nao so /markets/{id} -- /events tambem
        # falhou 1x em 6 tentativas no teste. Nao e rate-limit por sequencia (retestado com
        # espera de 2-3s, falhou igual), parece infra/CDN instavel em alguns edges.
        last_err = None
        for attempt in range(retries + 1):
            try:
                with urllib.request.urlopen(req, timeout=timeout) as r:
                    return json.loads(r.read().decode("utf-8"))
            except urllib.error.HTTPError as e:
                raise JupiterAuthError(f"Jupiter API retornou {e.code}: {e.read().decode('utf-8', 'ignore')}") from e
            except (TimeoutError, urllib.error.URLError) as e:
                last_err = e
                if attempt < retries:
                    time.sleep(1.5)
                    continue
        raise JupiterAPIError(f"Jupiter API sem resposta em {timeout}s pra {path} (apos {retries + 1} tentativas): {last_err}") from last_err

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
        """GET /markets/{id} -- confirmado ao vivo como intermitente (~40% falha em 7
        tentativas, curl E Python, com e sem espera entre chamadas -- nao e rate-limit por
        timing, parece infra/CDN inconsistente so nessa rota especifica). /events nunca falhou
        nos mesmos testes e ja traz pricing embutido por market, entao usamos como fallback
        automatico em vez de propagar o timeout pro caller."""
        try:
            data = self._get(f"/markets/{market_id}")
            return data.get("data", data) if isinstance(data, dict) else data
        except JupiterAPIError:
            return self._find_market_via_events(market_id)

    def _find_market_via_events(self, market_id: str, category: str = "crypto") -> dict:
        """Fallback do get_market: varre /events (default 'crypto', unico category testado
        neste projeto) procurando o marketId. Tenta os dois providers conhecidos."""
        for provider in ("polymarket", "kalshi"):
            try:
                events = self.list_events(category=category, provider=provider)
            except JupiterAuthError:
                raise
            except Exception:
                continue
            for ev in events:
                for m in ev.get("markets", []):
                    if m.get("marketId") == market_id:
                        return m
        raise JupiterAPIError(
            f"market {market_id} nao encontrado via fallback /events (category={category}) "
            "-- /markets/{id} direto tambem falhou"
        )

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
