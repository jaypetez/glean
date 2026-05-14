"""In-process pub/sub event bus for SSE delivery.

A single shared bus is mounted on the FastAPI app. The Runner publishes
RunEvent records as feeds run; SSE subscribers each get their own queue.
"""
from __future__ import annotations

import asyncio
import contextlib
import datetime as dt
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Literal

EventType = Literal["run_started", "run_completed", "run_failed"]


@dataclass(frozen=True, slots=True)
class RunEvent:
    type: EventType
    feed: str
    timestamp: dt.datetime = field(default_factory=lambda: dt.datetime.now(dt.UTC))
    fetched: int | None = None
    after_dedup: int | None = None
    sent: int | None = None
    duration_ms: int | None = None
    error: str | None = None

    def to_json(self) -> dict[str, object]:
        return {
            "type": self.type,
            "feed": self.feed,
            "timestamp": self.timestamp.isoformat(),
            "fetched": self.fetched,
            "after_dedup": self.after_dedup,
            "sent": self.sent,
            "duration_ms": self.duration_ms,
            "error": self.error,
        }


class EventBus:
    """Simple async pub/sub. Each subscriber gets a bounded queue."""

    def __init__(self, queue_max: int = 100) -> None:
        self._subscribers: set[asyncio.Queue[RunEvent]] = set()
        self._queue_max = queue_max
        self._lock = asyncio.Lock()

    async def publish(self, event: RunEvent) -> None:
        async with self._lock:
            subs = list(self._subscribers)
        for queue in subs:
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                with contextlib.suppress(asyncio.QueueEmpty):
                    queue.get_nowait()
                with contextlib.suppress(asyncio.QueueFull):
                    queue.put_nowait(event)

    async def subscribe(self) -> asyncio.Queue[RunEvent]:
        queue: asyncio.Queue[RunEvent] = asyncio.Queue(maxsize=self._queue_max)
        async with self._lock:
            self._subscribers.add(queue)
        return queue

    async def unsubscribe(self, queue: asyncio.Queue[RunEvent]) -> None:
        async with self._lock:
            self._subscribers.discard(queue)

    async def stream(self) -> AsyncIterator[RunEvent]:
        queue = await self.subscribe()
        try:
            while True:
                yield await queue.get()
        finally:
            await self.unsubscribe(queue)

    @property
    def subscriber_count(self) -> int:
        return len(self._subscribers)
