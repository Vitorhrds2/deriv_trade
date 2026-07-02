"""Registro simples de venues -- novo venue se cadastra com @register(), ninguem precisa editar
um dispatcher central pra adicionar Kalshi/Phantom/etc no futuro."""
from typing import Dict, Type

from .base import PriceFeedVenue

_REGISTRY: Dict[str, Type[PriceFeedVenue]] = {}


def register(cls: Type[PriceFeedVenue]) -> Type[PriceFeedVenue]:
    key = cls.name
    if key in _REGISTRY and _REGISTRY[key] is not cls:
        raise ValueError(f"venue '{key}' ja registrada por {_REGISTRY[key]!r}")
    _REGISTRY[key] = cls
    return cls


def get_venue(name: str) -> Type[PriceFeedVenue]:
    if name not in _REGISTRY:
        raise KeyError(f"venue '{name}' nao registrada. Disponiveis: {sorted(_REGISTRY)}")
    return _REGISTRY[name]


def list_venues() -> Dict[str, Type[PriceFeedVenue]]:
    return dict(_REGISTRY)
