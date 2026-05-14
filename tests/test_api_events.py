"""Tests for the SSE event stream + event bus."""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from httpx import ASGITransport, AsyncClient

from glean.api.app import make_app
from glean.api.events import EventBus, RunEvent
from glean.api.routes.events import events_stream
from glean.state.store import StateStore

pytestmark = pytest.mark.asyncio


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


async def test_run_event_to_json_serializes_timestamp() -> None:
    event = RunEvent(type="run_failed", feed="alpha", error="boom")
    payload = event.to_json()
    assert payload["type"] == "run_failed"
    assert payload["feed"] == "alpha"
    assert isinstance(payload["timestamp"], str)
    assert payload["error"] == "boom"


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


async def test_events_endpoint_streams_published_events() -> None:
    """Call the route directly so the infinite SSE response can be inspected safely."""
    bus = EventBus()
    disconnected = False

    class FakeRequest:
        app = SimpleNamespace(state=SimpleNamespace(glean_event_bus=bus))

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

        async def is_disconnected(self) -> bool:
            return False

    response = await events_stream(FakeRequest())  # type: ignore[arg-type]
    chunk = await asyncio.wait_for(response.body_iterator.__anext__(), timeout=1.0)
    assert chunk == {"comment": "keepalive"}
    await response.body_iterator.aclose()
    assert bus.subscriber_count == 0
