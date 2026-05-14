"""SSE endpoint for live feed run events."""
from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from typing import TYPE_CHECKING

from fastapi import APIRouter, Request
from sse_starlette.sse import EventSourceResponse

from glean.api.events import RunEvent

if TYPE_CHECKING:
    from glean.api.events import EventBus

router = APIRouter(tags=["events"])

_KEEPALIVE_SECS = 30.0


@router.get("/events")
async def events_stream(request: Request) -> EventSourceResponse:
    """Stream RunEvent records as SSE.

    The connection is kept alive with a ': keepalive' comment every 30s
    so reverse proxies don't time out idle streams.
    """
    bus: EventBus = request.app.state.glean_event_bus
    queue = await bus.subscribe()

    async def generator() -> AsyncIterator[dict[str, str]]:
        try:
            while True:
                if await request.is_disconnected():
                    break
                try:
                    event: RunEvent = await asyncio.wait_for(
                        queue.get(), timeout=_KEEPALIVE_SECS
                    )
                    yield {
                        "event": event.type,
                        "data": json.dumps(event.to_json()),
                    }
                except TimeoutError:
                    yield {"comment": "keepalive"}
        finally:
            await bus.unsubscribe(queue)

    return EventSourceResponse(generator())
