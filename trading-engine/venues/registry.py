"""Registro simples de venues -- novo venue se cadastra com @register(), ninguem precisa editar
um dispatcher central pra adicionar Kalshi/Phantom/etc no futuro."""
from typing import Any, Dict, Type

_REGISTRY: Dict[str, Type[Any]] = {}


def register(cls: Type[Any]) -> Type[Any]:
    key = getattr(cls, "name", cls.__name__.lower())
    if key in _REGISTRY and _REGISTRY[key] is not cls:
        raise ValueError(f"venue '{key}' ja registrada por {_REGISTRY[key]!r}")
    _REGISTRY[key] = cls
    return cls


def get_venue(name: str) -> Type[Any]:
    if name not in _REGISTRY:
        raise KeyError(f"venue '{name}' nao registrada. Disponiveis: {sorted(_REGISTRY)}")
    return _REGISTRY[name]


def list_venues() -> Dict[str, Type[Any]]:
    return dict(_REGISTRY)

