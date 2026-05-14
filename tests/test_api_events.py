"""Tests for the SSE event stream + event bus."""
from __future__ import annotations

import asyncio
import json
import warnings
from collections.abc import Iterator
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException, Response
from httpx import ASGITransport, AsyncClient

from glean.api.app import make_app
from glean.api.events import EventBus, RunEvent
from glean.api.routes import events as events_routes
from glean.api.routes.events import events_stream
from glean.state.store import StateStore

pytestmark = pytest.mark.asyncio


@pytest.fixture(autouse=True)
def clear_event_tokens() -> Iterator[None]:
    token_store = getattr(events_routes, "_EVENT_TOKENS", None)
    if token_store is not None:
        token_store.clear()
    events_routes._API_KEY_QUERY_WARNING_EMITTED = False
    yield
    if token_store is not None:
        token_store.clear()
    events_routes._API_KEY_QUERY_WARNING_EMITTED = False


async def test_event_bus_publish_and_subscribe() -> None:
    bus = EventBus()
    q = await bus.subscribe()
    event = RunEvent(type="run_started", feed="alpha")
    await bus.publish(event)
    received = await asyncio.wait_for(q.get(), timeout=1.0)
    assert received.type == "run_started"
    assert received.feed == "alpha"
    await bus.unsubscribe(q)


async def test_event_bus_multiple_subscribers() -> None:
    bus = EventBus()
    q1 = await bus.subscribe()
    q2 = await bus.subscribe()
    await bus.publish(RunEvent(type="run_completed", feed="x"))
    e1 = await asyncio.wait_for(q1.get(), timeout=1.0)
    e2 = await asyncio.wait_for(q2.get(), timeout=1.0)
    assert e1.feed == "x" and e2.feed == "x"
    await bus.unsubscribe(q1)
    await bus.unsubscribe(q2)


async def test_event_bus_drops_oldest_when_full() -> None:
    bus = EventBus(queue_max=2)
    q = await bus.subscribe()
    for i in range(5):
        await bus.publish(RunEvent(type="run_started", feed=f"f{i}"))
    held = []
    while not q.empty():
        held.append(q.get_nowait())
    assert [event.feed for event in held] == ["f3", "f4"]
    await bus.unsubscribe(q)


async def test_unsubscribe_decrements_count() -> None:
    bus = EventBus()
    assert bus.subscriber_count == 0
    q = await bus.subscribe()
    assert bus.subscriber_count == 1
    await bus.unsubscribe(q)
    assert bus.subscriber_count == 0


async def test_event_bus_max_subscribers_can_be_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GLEAN_MAX_SSE_SUBSCRIBERS", "2")
    bus = EventBus()
    q1 = await bus.subscribe()
    q2 = await bus.subscribe()
    with pytest.raises(HTTPException) as exc_info:
        await bus.subscribe()
    assert exc_info.value.status_code == 503
    await bus.unsubscribe(q1)
    await bus.unsubscribe(q2)


async def test_run_event_to_json_serializes_timestamp() -> None:
    event = RunEvent(type="run_failed", feed="alpha", error="boom")
    payload = event.to_json()
    assert payload["type"] == "run_failed"
    assert payload["feed"] == "alpha"
    assert isinstance(payload["timestamp"], str)
    assert payload["error"] == "boom"


async def test_run_event_to_json_scrubs_sensitive_error_text() -> None:
    event = RunEvent(type="run_failed", feed="alpha", error="upstream rejected sk-abc12345")
    payload = event.to_json()
    assert payload["error"] == "upstream rejected sk-[REDACTED]"


@pytest.fixture
async def configured_app(tmp_path: Path):
    state = StateStore(tmp_path / "state.db")
    await state.open()
    app = make_app(state, tmp_path / "state.db")
    yield app, state
    await state.close()


async def test_make_app_mounts_event_bus(configured_app) -> None:
    app, _ = configured_app
    assert isinstance(app.state.glean_event_bus, EventBus)


async def test_events_endpoint_requires_auth(configured_app) -> None:
    app, _ = configured_app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/api/v1/events", timeout=2.0)
        assert resp.status_code == 401


async def test_events_endpoint_accepts_api_key_query_param(
    configured_app, monkeypatch: pytest.MonkeyPatch
) -> None:
    app, _ = configured_app

    def stub_event_source_response(body_iterator: object) -> Response:
        return Response(status_code=204, media_type="text/event-stream")

    monkeypatch.setattr(events_routes, "EventSourceResponse", stub_event_source_response)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        with pytest.warns(DeprecationWarning, match="Passing api_key"):
            resp = await ac.get(f"/api/v1/events?api_key={app.state.glean_api_key}", timeout=2.0)
        assert resp.status_code == 204

        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always", DeprecationWarning)
            resp = await ac.get(f"/api/v1/events?api_key={app.state.glean_api_key}", timeout=2.0)
        assert resp.status_code == 204
        assert caught == []


async def test_event_token_endpoint_returns_short_lived_token(configured_app) -> None:
    app, _ = configured_app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post(
            "/api/v1/events/token",
            headers={"X-Glean-Api-Key": app.state.glean_api_key},
            timeout=2.0,
        )
    assert resp.status_code == 200
    payload = resp.json()
    assert isinstance(payload["token"], str)
    assert payload["token"]
    assert payload["expires_in"] == 60


async def test_event_token_endpoint_requires_api_key(configured_app) -> None:
    app, _ = configured_app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post("/api/v1/events/token", timeout=2.0)
    assert resp.status_code == 401


async def test_events_endpoint_accepts_single_use_token(
    configured_app, monkeypatch: pytest.MonkeyPatch
) -> None:
    app, _ = configured_app

    def stub_event_source_response(body_iterator: object) -> Response:
        return Response(status_code=204, media_type="text/event-stream")

    monkeypatch.setattr(events_routes, "EventSourceResponse", stub_event_source_response)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        token_resp = await ac.post(
            "/api/v1/events/token",
            headers={"X-Glean-Api-Key": app.state.glean_api_key},
            timeout=2.0,
        )
        token = token_resp.json()["token"]
        first = await ac.get(f"/api/v1/events?token={token}", timeout=2.0)
        second = await ac.get(f"/api/v1/events?token={token}", timeout=2.0)
    assert first.status_code == 204
    assert second.status_code == 401


async def test_events_endpoint_rejects_expired_token(
    configured_app, monkeypatch: pytest.MonkeyPatch
) -> None:
    app, _ = configured_app
    current_time = [1_000.0]
    monkeypatch.setattr(events_routes.time, "time", lambda: current_time[0])
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        token_resp = await ac.post(
            "/api/v1/events/token",
            headers={"X-Glean-Api-Key": app.state.glean_api_key},
            timeout=2.0,
        )
        token = token_resp.json()["token"]
        current_time[0] += 61.0
        resp = await ac.get(f"/api/v1/events?token={token}", timeout=2.0)
    assert resp.status_code == 401


async def test_events_endpoint_rejects_disallowed_origin(configured_app) -> None:
    app, _ = configured_app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get(
            f"/api/v1/events?api_key={app.state.glean_api_key}",
            headers={"Origin": "http://evil.com"},
            timeout=2.0,
        )
    assert resp.status_code == 403


async def test_events_endpoint_rejects_subscriber_above_limit(configured_app) -> None:
    app, _ = configured_app
    bus: EventBus = app.state.glean_event_bus
    queues = [await bus.subscribe() for _ in range(EventBus.MAX_SUBSCRIBERS)]
    try:
        assert bus.subscriber_count == EventBus.MAX_SUBSCRIBERS
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.get(
                "/api/v1/events",
                headers={"X-Glean-Api-Key": app.state.glean_api_key},
                timeout=2.0,
            )
        assert resp.status_code == 503
    finally:
        for queue in queues:
            await bus.unsubscribe(queue)


async def test_events_endpoint_does_not_consume_token_when_subscriber_limit_reached(
    configured_app,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app, _ = configured_app
    bus: EventBus = app.state.glean_event_bus

    def stub_event_source_response(body_iterator: object) -> Response:
        return Response(status_code=204, media_type="text/event-stream")

    monkeypatch.setattr(events_routes, "EventSourceResponse", stub_event_source_response)
    queues = [await bus.subscribe() for _ in range(EventBus.MAX_SUBSCRIBERS)]
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            token_resp = await ac.post(
                "/api/v1/events/token",
                headers={"X-Glean-Api-Key": app.state.glean_api_key},
                timeout=2.0,
            )
            token = token_resp.json()["token"]
            first = await ac.get(f"/api/v1/events?token={token}", timeout=2.0)
            await bus.unsubscribe(queues.pop())
            second = await ac.get(f"/api/v1/events?token={token}", timeout=2.0)
        assert first.status_code == 503
        assert second.status_code == 204
    finally:
        for queue in queues:
            await bus.unsubscribe(queue)


async def test_events_endpoint_streams_published_events() -> None:
    """Call the route directly so the infinite SSE response can be inspected safely."""
    bus = EventBus()
    disconnected = False

    class FakeRequest:
        app = SimpleNamespace(state=SimpleNamespace(glean_event_bus=bus))
        headers: dict[str, str] = {}
        query_params: dict[str, str] = {}

        async def is_disconnected(self) -> bool:
            return disconnected

    response = await events_stream(FakeRequest())  # type: ignore[arg-type]
    await bus.publish(RunEvent(type="run_completed", feed="alpha", sent=3))

    chunk = await asyncio.wait_for(response.body_iterator.__anext__(), timeout=1.0)
    assert chunk["event"] == "run_completed"
    data = json.loads(chunk["data"])
    assert data["feed"] == "alpha"
    assert data["sent"] == 3

    disconnected = True
    with pytest.raises(StopAsyncIteration):
        await asyncio.wait_for(response.body_iterator.__anext__(), timeout=1.0)
    assert bus.subscriber_count == 0


async def test_events_endpoint_emits_keepalive_comments(monkeypatch: pytest.MonkeyPatch) -> None:
    bus = EventBus()
    monkeypatch.setattr("glean.api.routes.events._KEEPALIVE_SECS", 0.01)

    class FakeRequest:
        app = SimpleNamespace(state=SimpleNamespace(glean_event_bus=bus))
        headers: dict[str, str] = {}
        query_params: dict[str, str] = {}

        async def is_disconnected(self) -> bool:
            return False

    response = await events_stream(FakeRequest())  # type: ignore[arg-type]
    chunk = await asyncio.wait_for(response.body_iterator.__anext__(), timeout=1.0)
    assert chunk == {"comment": "keepalive"}
    await response.body_iterator.aclose()
    assert bus.subscriber_count == 0
