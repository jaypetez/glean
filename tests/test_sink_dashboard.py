from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
import structlog.testing
from structlog.contextvars import bind_contextvars, reset_contextvars

from glean.api.events import EventBus
from glean.config.schema import RenderConfig
from glean.sinks import SendContext, build_sink
from glean.sources.base import Item
from glean.state.store import StateStore

pytestmark = pytest.mark.asyncio


async def _open_state(tmp_db: Path) -> StateStore:
    store = StateStore(tmp_db)
    await store.open()
    return store


def _items() -> list[Item]:
    return [
        Item(canonical_url="https://example.com/a", title="A"),
        Item(canonical_url="https://example.com/b", title="B"),
    ]


def _ctx(
    *,
    state: StateStore,
    event_bus: EventBus | None = None,
    feed: str = "alpha",
    messages: list[str] | None = None,
    intro: str = "intro",
    items: list[Item] | None = None,
) -> SendContext:
    return SendContext(
        feed=feed,
        items=items if items is not None else _items(),
        messages=messages if messages is not None else ["rendered body"],
        intro=intro,
        render=RenderConfig(),
        state=state,
        event_bus=event_bus,
    )


async def _digest_rows(store: StateStore) -> list[tuple[object, ...]]:
    async with store.db.execute(
        "SELECT id, feed_name, sent_at, style, intro, body, fragment_index, item_count, trace_id "
        "FROM digests ORDER BY id"
    ) as cur:
        return [row async for row in cur]


async def test_dashboard_sink_persists_single_fragment_and_emits_sse_event(tmp_db: Path) -> None:
    store = await _open_state(tmp_db)
    bus = EventBus()
    queue = await bus.subscribe()
    sink = build_sink({"type": "dashboard"})
    tokens = bind_contextvars(trace_id="single123")

    try:
        await sink.send(_ctx(state=store, event_bus=bus, messages=["<b>digest</b>"]))
        event = await asyncio.wait_for(queue.get(), timeout=1.0)
        rows = await _digest_rows(store)
    finally:
        reset_contextvars(**tokens)
        await bus.unsubscribe(queue)
        await sink.aclose()
        await store.close()

    assert len(rows) == 1
    (
        digest_id,
        feed_name,
        sent_at,
        style,
        intro,
        body,
        fragment_index,
        item_count,
        trace_id,
    ) = rows[0]
    assert feed_name == "alpha"
    assert isinstance(sent_at, str)
    assert style == "html"
    assert intro == "intro"
    assert body == "<b>digest</b>"
    assert fragment_index == 0
    assert item_count == 2
    assert trace_id == "single123"

    payload = event.to_json()
    assert event.type == "digest.persisted"
    assert payload["feed_name"] == "alpha"
    assert payload["digest_ids"] == [digest_id]
    assert payload["sent_at"] == sent_at
    assert payload["trace_id"] == "single123"
    assert payload["item_count"] == 2


async def test_dashboard_sink_persists_multiple_fragments_in_order(tmp_db: Path) -> None:
    store = await _open_state(tmp_db)
    sink = build_sink({"type": "dashboard"})

    try:
        await sink.send(
            _ctx(
                state=store,
                messages=["fragment 1", "fragment 2", "fragment 3"],
            )
        )
        rows = await _digest_rows(store)
    finally:
        await sink.aclose()
        await store.close()

    assert [(row[5], row[6]) for row in rows] == [
        ("fragment 1", 0),
        ("fragment 2", 1),
        ("fragment 3", 2),
    ]


async def test_dashboard_sink_prunes_only_the_target_feed(tmp_db: Path) -> None:
    store = await _open_state(tmp_db)
    sink = build_sink({"type": "dashboard", "keep_last_n": 3})

    try:
        await sink.send(_ctx(state=store, feed="alpha", messages=["one"]))
        await sink.send(_ctx(state=store, feed="beta", messages=["beta-one"]))
        await sink.send(_ctx(state=store, feed="alpha", messages=["two"]))
        await sink.send(_ctx(state=store, feed="alpha", messages=["three"]))
        await sink.send(_ctx(state=store, feed="alpha", messages=["four"]))
        async with store.db.execute(
            "SELECT feed_name, body FROM digests ORDER BY feed_name, id"
        ) as cur:
            rows = [row async for row in cur]
    finally:
        await sink.aclose()
        await store.close()

    assert rows == [
        ("alpha", "two"),
        ("alpha", "three"),
        ("alpha", "four"),
        ("beta", "beta-one"),
    ]


async def test_dashboard_sink_uses_existing_implicit_transaction(tmp_db: Path) -> None:
    store = await _open_state(tmp_db)
    sink = build_sink({"type": "dashboard"})

    try:
        await store.db.execute(
            "INSERT INTO digests(feed_name, style, body) VALUES (?, ?, ?)",
            ("setup", "html", "seed"),
        )
        await sink.send(_ctx(state=store, feed="alpha", messages=["later"]))
    finally:
        await sink.aclose()
        await store.close()

    reopened = await _open_state(tmp_db)
    try:
        async with reopened.db.execute(
            "SELECT feed_name, body FROM digests WHERE feed_name = ? ORDER BY id",
            ("alpha",),
        ) as cur:
            rows = [row async for row in cur]
    finally:
        await reopened.close()

    assert rows == [("alpha", "later")]


async def test_dashboard_sink_rolls_back_partial_insert_failures(
    tmp_db: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = await _open_state(tmp_db)
    sink = build_sink({"type": "dashboard"})
    original_execute = store.db.execute
    insert_calls = 0

    def flaky_execute(sql: str, parameters: object = ()) -> object:
        nonlocal insert_calls
        if sql == (
            "INSERT INTO digests("
            "feed_name, sent_at, style, intro, body, fragment_index, item_count, trace_id"
            ") VALUES (?, ?, ?, ?, ?, ?, ?, ?)"
        ):
            insert_calls += 1
            if insert_calls == 2:
                raise RuntimeError("second insert failed")
        return original_execute(sql, parameters)

    monkeypatch.setattr(store.db, "execute", flaky_execute)

    try:
        with pytest.raises(RuntimeError, match="second insert failed"):
            await sink.send(_ctx(state=store, messages=["first", "second"]))
        await sink.send(_ctx(state=store, messages=["recovered"]))
        async with store.db.execute(
            "SELECT body FROM digests WHERE feed_name = ? ORDER BY id",
            ("alpha",),
        ) as cur:
            rows = [row async for row in cur]
    finally:
        await sink.aclose()
        await store.close()

    assert rows == [("recovered",)]


async def test_dashboard_sink_stores_trace_id_from_contextvars(tmp_db: Path) -> None:
    store = await _open_state(tmp_db)
    sink = build_sink({"type": "dashboard"})
    tokens = bind_contextvars(trace_id="tracebeef")

    try:
        await sink.send(_ctx(state=store))
        async with store.db.execute("SELECT trace_id FROM digests") as cur:
            row = await cur.fetchone()
    finally:
        reset_contextvars(**tokens)
        await sink.aclose()
        await store.close()

    assert row == ("tracebeef",)


async def test_dashboard_sink_stores_raw_html_verbatim(tmp_db: Path) -> None:
    store = await _open_state(tmp_db)
    sink = build_sink({"type": "dashboard"})
    payload = "<script>alert(1)</script>"

    try:
        await sink.send(_ctx(state=store, items=[], messages=[payload]))
        async with store.db.execute("SELECT body FROM digests") as cur:
            row = await cur.fetchone()
    finally:
        await sink.aclose()
        await store.close()

    # Intentional: the dashboard stores rendered digest HTML verbatim.
    # Sanitization happens in the UI layer after engine-level filtering/escaping.
    assert row == (payload,)


async def test_dashboard_sink_optional_db_errors_are_swallowed(
    tmp_db: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = await _open_state(tmp_db)
    sink = build_sink({"type": "dashboard", "required": False})

    async def fail_execute(*_args: object, **_kwargs: object) -> object:
        raise RuntimeError("db unavailable")

    monkeypatch.setattr(store.db, "execute", fail_execute)

    try:
        with structlog.testing.capture_logs() as captured_logs:
            await sink.send(_ctx(state=store))
    finally:
        await sink.aclose()
        await store.close()

    assert any(log["event"] == "dashboard_digest_persist_failed" for log in captured_logs)


async def test_dashboard_sink_required_db_errors_propagate(
    tmp_db: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = await _open_state(tmp_db)
    sink = build_sink({"type": "dashboard"})

    async def fail_execute(*_args: object, **_kwargs: object) -> object:
        raise RuntimeError("db unavailable")

    monkeypatch.setattr(store.db, "execute", fail_execute)

    try:
        with pytest.raises(RuntimeError, match="db unavailable"):
            await sink.send(_ctx(state=store))
    finally:
        await sink.aclose()
        await store.close()
