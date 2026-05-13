from __future__ import annotations

from collections.abc import Callable
from typing import Any

from glean.sinks.base import Sink

_REGISTRY: dict[str, Callable[..., Sink]] = {}


def register_sink(type_name: str) -> Callable[[Callable[..., Sink]], Callable[..., Sink]]:
    def decorator(cls: Callable[..., Sink]) -> Callable[..., Sink]:
        _REGISTRY[type_name] = cls
        return cls

    return decorator


def build_sink(spec: dict[str, Any]) -> Sink:
    type_name = spec.get("type")
    if not type_name:
        raise ValueError(f"sink spec missing 'type': {spec!r}")
    factory = _REGISTRY.get(type_name)
    if factory is None:
        raise ValueError(
            f"unknown sink type: {type_name!r}. registered: {sorted(_REGISTRY)}"
        )
    kwargs = {k: v for k, v in spec.items() if k != "type"}
    return factory(**kwargs)


def _import_builtins() -> None:
    # Eager import so decorators register on first use.
    from glean.sinks import telegram  # noqa: F401


_import_builtins()
