from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, ClassVar, Protocol, runtime_checkable

if TYPE_CHECKING:
    from glean.api.events import EventBus
    from glean.config.schema import RenderConfig
    from glean.sources.base import Item
    from glean.state.store import StateStore


@dataclass(frozen=True, slots=True)
class SendContext:
    """Context passed to a Sink's send() method."""

    feed: str
    items: list[Item]
    messages: list[str]
    intro: str
    render: RenderConfig
    state: StateStore | None = None
    event_bus: EventBus | None = None


@runtime_checkable
class Sink(Protocol):
    """A destination for digest output."""

    type: ClassVar[str]
    required: bool

    async def send(self, ctx: SendContext) -> None:
        pass

    async def aclose(self) -> None:
        pass
