"""Registry for search backend plugins."""
from __future__ import annotations

from collections.abc import Callable
from typing import Any

from glean.search.base import SearchBackend

_REGISTRY: dict[str, Callable[..., SearchBackend]] = {}


def register_backend(
    name: str,
) -> Callable[[Callable[..., SearchBackend]], Callable[..., SearchBackend]]:
    def decorator(cls: Callable[..., SearchBackend]) -> Callable[..., SearchBackend]:
        _REGISTRY[name] = cls
        return cls

    return decorator


def build_backend(spec: dict[str, Any]) -> SearchBackend:
    engine = spec.get("engine")
    if not engine:
        raise ValueError(f"search spec missing 'engine': {spec!r}")
    factory = _REGISTRY.get(engine)
    if factory is None:
        raise ValueError(
            f"unknown search engine: {engine!r}. registered: {sorted(_REGISTRY)}"
        )
    kwargs = {k: v for k, v in spec.items() if k != "engine"}
    return factory(**kwargs)


def _import_builtins() -> None:
    # Eager import so decorators register on first use.
    from glean.search import brave, exa, mwmbl, searxng, serper, tavily  # noqa: F401


_import_builtins()
