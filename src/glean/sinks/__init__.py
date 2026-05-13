from __future__ import annotations

from glean.sinks.base import SendContext, Sink
from glean.sinks.registry import build_sink, register_sink

__all__ = ["SendContext", "Sink", "build_sink", "register_sink"]
