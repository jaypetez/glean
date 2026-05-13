from __future__ import annotations

from collections.abc import Callable
from typing import Any

from glean.sources.base import Source

_REGISTRY: dict[str, Callable[..., Source]] = {}


def register_source(type_name: str) -> Callable[[Callable[..., Source]], Callable[..., Source]]:
    def decorator(cls: Callable[..., Source]) -> Callable[..., Source]:
        _REGISTRY[type_name] = cls
        return cls

    return decorator


def build_source(spec: dict[str, Any]) -> Source:
    type_name = spec.get("type")
    if not type_name:
        raise ValueError(f"source spec missing 'type': {spec!r}")
    factory = _REGISTRY.get(type_name)
    if factory is None:
        raise ValueError(
            f"unknown source type: {type_name!r}. registered: {sorted(_REGISTRY)}"
        )
    kwargs = {k: v for k, v in spec.items() if k not in ("type", "llm")}
    return factory(**kwargs)


def _import_builtins() -> None:
    # Eager import so decorators register on first use.
    from glean.sources import hn, reddit, rss, scraper, search  # noqa: F401


_import_builtins()
