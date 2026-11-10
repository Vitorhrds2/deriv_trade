"""Interface comum de "venue" (corretora/plataforma) para o ecossistema multi-corretora.

Ponto de partida da discussao "preparar pra escalar entre Deriv/Binance/Polymarket/Kalshi/
Phantom(Solana)/etc" -- ver docs/venue_adapter_design.md para o racional completo e o plano de
migracao. Nao modifica nenhum arquivo existente (deriv_client.py, hft_arbitrage_bot.py,
polymarket_lag_probe.py continuam intactos); os adapters aqui so ENVELOPAM o que ja existe.

Duas camadas, de proposito:

- `PriceFeedVenue` -- o que toda venue tem em comum de verdade: dado de mercado publico.
  Cobre Binance/Coinbase/Kraken (so feed, nunca vao virar venue de execucao aqui) e a metade
  publica de Deriv/Polymarket/Kalshi.
- `ExecutionVenue` -- adiciona saldo/credenciais. NAO forca um `place_order()` unico: Deriv
  (contratos de opcao com barrier/duration/multiplier), Polymarket/Kalshi (shares de mercado de
  previsao, preco 0-1) e Binance-como-corretora (spot/futures) tem formatos de ordem
  genuinamente diferentes -- fingir uma assinatura comum so esconderia bug. Cada venue expoe
  seus proprios metodos de execucao (ex.: `DerivVenue.buy_contract(...)`), e o que fica comum e
  descoberta/introspeccao (`requires_credentials`, `is_authenticated`).
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Dict, List, Optional


@dataclass
class PriceUpdate:
    venue: str
    symbol: str
    price: float
    ts: float
    raw: Optional[dict] = None


@dataclass
class MarketUpdate:
    venue: str
    symbol: str
    bid_px: float
    bid_sz: float
    ask_px: float
    ask_sz: float
    timestamp_ns: int
    raw: Optional[Dict[str, Any]] = None


@dataclass
class OrderExecutionResult:
    venue: str
    order_id: str
    symbol: str
    side: str  # "BUY" or "SELL"
    price: float
    size: float
    fee_bps: float
    rebate_bps: float
    is_maker: bool
    status: str  # "FILLED", "CANCELLED", "REJECTED"
    latency_ms: float
    timestamp_ns: int


class UnifiedVenue(ABC):
    """Unified interface for execution venues across modern market microstructure vectors."""

    name: str = "unified_venue"

    @abstractmethod
    async def connect(self) -> bool:
        """Establishes connection to the venue (REST/WS/RPC/FIX). Returns True if successful."""
        ...

    @abstractmethod
    async def disconnect(self) -> None:
        """Gracefully shuts down connection and background streaming tasks."""
        ...

    @abstractmethod
    async def subscribe_market_data(
        self, symbol: str, callback: Callable[[MarketUpdate], Awaitable[None]]
    ) -> None:
        """Subscribes to market updates (orderbook/ticker) and invokes callback on each update."""
        ...

    @abstractmethod
    async def submit_order(self, order_params: Dict[str, Any]) -> OrderExecutionResult:
        """Submits an order according to venue protocol rules."""
        ...

    @abstractmethod
    async def cancel_order(self, order_id: str, symbol: str) -> bool:
        """Cancels an existing resting order."""
        ...


class PriceFeedVenue(ABC):
    """Acesso somente-leitura a dado publico de mercado. Nunca precisa de credencial."""

    name: str = "base"
    requires_credentials: bool = False

    @abstractmethod
    async def connect(self) -> None:
        ...

    @abstractmethod
    async def disconnect(self) -> None:
        ...

    @abstractmethod
    async def get_price(self, symbol: str) -> float:
        """Snapshot pontual (poll). Para venues WS, pode usar o ultimo tick cacheado."""
        ...

    @abstractmethod
    async def stream(self, symbols: list, on_update: Callable[[PriceUpdate], Awaitable[None]]) -> None:
        """Roda indefinidamente (ate cancelado) chamando `on_update` a cada novo preco."""
        ...


class ExecutionVenue(PriceFeedVenue):
    """Extensao para venues onde da pra operar de verdade (precisa de credencial)."""

    requires_credentials: bool = True

    @abstractmethod
    def is_authenticated(self) -> bool:
        ...

    @abstractmethod
    async def get_balance(self) -> dict:
        ...

    # Deliberadamente NAO ha `place_order()` generico aqui -- ver docstring do modulo.

