from .base import ExecutionVenue, MarketUpdate, OrderExecutionResult, PriceFeedVenue, PriceUpdate, UnifiedVenue
from .registry import get_venue, list_venues, register

# Import concrete venue modules for auto-registration side-effects
from . import binance, deriv, jupiter_execution, jupiter_prediction, polymarket  # noqa: E402,F401
from . import sui_deepbook_venue  # noqa: E402,F401
from .sui_deepbook_venue import SuiDeepBookVenue

# Optional venues guarded against missing dependencies/files in container
try:
    from . import hyperliquid_venue  # noqa: E402,F401
    from .hyperliquid_venue import HyperliquidVenue
except ImportError:
    HyperliquidVenue = None

try:
    from . import velocity_swift_venue  # noqa: E402,F401
    from .velocity_swift_venue import VelocitySwiftVenue
except ImportError:
    VelocitySwiftVenue = None

try:
    from . import kalshi_fix_venue  # noqa: E402,F401
    from .kalshi_fix_venue import KalshiFixVenue
except ImportError:
    KalshiFixVenue = None

try:
    from . import dydx_v4_venue  # noqa: E402,F401
    from .dydx_v4_venue import DydxV4Venue
except ImportError:
    DydxV4Venue = None

try:
    from . import gmx_cex_venue  # noqa: E402,F401
    from .gmx_cex_venue import GmxCexVenue
except ImportError:
    GmxCexVenue = None

__all__ = [
    "PriceFeedVenue",
    "ExecutionVenue",
    "UnifiedVenue",
    "PriceUpdate",
    "MarketUpdate",
    "OrderExecutionResult",
    "register",
    "get_venue",
    "list_venues",
    "SuiDeepBookVenue",
]


