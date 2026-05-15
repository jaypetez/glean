from __future__ import annotations

import importlib
from typing import Any

from glean.sinks.base import SendContext, Sink

__all__ = ["SendContext", "Sink", "build_sink", "register_sink"]


def __getattr__(name: str) -> Any:
    if name in {"build_sink", "register_sink"}:
        registry = importlib.import_module("glean.sinks.registry")
        return getattr(registry, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
