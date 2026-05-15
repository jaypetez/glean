"""SSE endpoint for live feed run events."""

from __future__ import annotations

import asyncio
import json
import os
import secrets
import time
import warnings
from collections.abc import AsyncIterator
from typing import TYPE_CHECKING

from fastapi import APIRouter, HTTPException, Request, status
from sse_starlette.sse import EventSourceResponse

from glean.api.events import RunEvent
from glean.api.models import EventTokenResponse

if TYPE_CHECKING:
    from glean.api.events import EventBus

router = APIRouter(tags=["events"])

_KEEPALIVE_SECS = 30.0
_EVENT_TOKEN_TTL_SECS = 60
_EVENT_TOKENS: dict[str, float] = {}


def _sweep_expired_event_tokens(now: float) -> None:
    for token, expires_at in list(_EVENT_TOKENS.items()):
        if expires_at <= now:
            _EVENT_TOKENS.pop(token, None)


def _consume_event_token(token: str) -> float | None:
    expires_at = _EVENT_TOKENS.pop(token, None)
    if expires_at is None or expires_at <= time.time():
        return None
    return expires_at


def _restore_event_token(token: str, expires_at: float) -> None:
    if expires_at > time.time():
        _EVENT_TOKENS[token] = expires_at


def _check_origin(request: Request) -> None:
    allowed_origins_env = os.environ.get(
        "GLEAN_ALLOWED_ORIGINS",
        "http://localhost:9090,http://127.0.0.1:9090",
    )
    allowed_origins = {
        origin.strip() for origin in allowed_origins_env.split(",") if origin.strip()
    }
    origin = request.headers.get("origin")
    if origin is not None and origin not in allowed_origins:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="origin not allowed",
        )


class _ApiKeyDeprecationFlag:
    emitted = False


def _warn_api_key_query_deprecated_once() -> None:
    if _ApiKeyDeprecationFlag.emitted:
        return
    warnings.warn(
        "Passing api_key in the events stream query string is deprecated; "
        "POST /api/v1/events/token and pass token instead.",
        DeprecationWarning,
        stacklevel=2,
    )
    _ApiKeyDeprecationFlag.emitted = True


@router.post("/events/token", response_model=EventTokenResponse)
async def create_event_token() -> EventTokenResponse:
    now = time.time()
    _sweep_expired_event_tokens(now)
    token = secrets.token_urlsafe(32)
    _EVENT_TOKENS[token] = now + _EVENT_TOKEN_TTL_SECS
    return EventTokenResponse(token=token, expires_in=_EVENT_TOKEN_TTL_SECS)


@router.get("/events")
async def events_stream(request: Request) -> EventSourceResponse:
    """Stream RunEvent records as SSE.

    The connection is kept alive with a ': keepalive' comment every 30s
    so reverse proxies don't time out idle streams.
    """
    _check_origin(request)
    token = request.query_params.get("token")
    consumed_token: tuple[str, float] | None = None
    if token is not None:
        expires_at = _consume_event_token(token)
        if expires_at is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="invalid event token",
            )
        consumed_token = (token, expires_at)
    elif request.query_params.get("api_key") is not None:
        _warn_api_key_query_deprecated_once()

    bus: EventBus = request.app.state.glean_event_bus
    try:
        queue = await bus.subscribe()
    except HTTPException:
        if consumed_token is not None:
            _restore_event_token(*consumed_token)
        raise

    async def generator() -> AsyncIterator[dict[str, str]]:
        try:
            while True:
                if await request.is_disconnected():
                    break
                try:
                    event: RunEvent = await asyncio.wait_for(queue.get(), timeout=_KEEPALIVE_SECS)
                    yield {
                        "event": event.type,
                        "data": json.dumps(event.to_json()),
                    }
                except TimeoutError:
                    yield {"comment": "keepalive"}
        finally:
            await bus.unsubscribe(queue)

    return EventSourceResponse(generator())
