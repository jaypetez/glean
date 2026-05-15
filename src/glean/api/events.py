"""In-process pub/sub event bus for SSE delivery.

A single shared bus is mounted on the FastAPI app. The Runner publishes
RunEvent records as feeds run; SSE subscribers each get their own queue.
"""

from __future__ import annotations

import asyncio
import contextlib
import datetime as dt
import os
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Literal

from fastapi import HTTPException, status

from glean.security.scrub import scrub

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
            "error": scrub(self.error) if self.error is not None else None,
        }


class EventBus:
    """Simple async pub/sub. Each subscriber gets a bounded queue."""

    MAX_SUBSCRIBERS = 20

    def __init__(self, queue_max: int = 100, max_subscribers: int | None = None) -> None:
        self._subscribers: set[asyncio.Queue[RunEvent]] = set()
        self._queue_max = queue_max
        self.max_subscribers = self._resolve_max_subscribers(max_subscribers)
        self._lock = asyncio.Lock()

    @classmethod
    def _resolve_max_subscribers(cls, override: int | None) -> int:
        if override is not None:
            return override
        raw = os.environ.get("GLEAN_MAX_SSE_SUBSCRIBERS")
        if raw is None:
            return cls.MAX_SUBSCRIBERS
        with contextlib.suppress(ValueError):
            return int(raw)
        return cls.MAX_SUBSCRIBERS

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
            if len(self._subscribers) >= self.max_subscribers:
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="SSE subscriber limit reached",
                )
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
