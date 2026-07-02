from .base import ExecutionVenue, PriceFeedVenue
from .registry import get_venue, list_venues, register

# Import dos modulos concretos pelo EFEITO COLATERAL do @register -- sem isso, get_venue()/
# list_venues() ficam vazios ate algum script importar cada adapter manualmente, o que anula
# o proposito do registry (nao precisar de um dispatcher central). Bug real encontrado ao
# tentar usar o registry pela primeira vez (multi_venue_compare.py).
from . import binance, deriv, jupiter_execution, jupiter_prediction, polymarket  # noqa: E402,F401

__all__ = ["PriceFeedVenue", "ExecutionVenue", "register", "get_venue", "list_venues"]
