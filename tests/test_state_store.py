from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from glean.sources.base import Item
from glean.state import store as store_module
from glean.state.embedding_bytes import pack_embedding
from glean.state.store import StateStore

pytestmark = pytest.mark.asyncio


async def _store(path: Path) -> StateStore:
    store = StateStore(path)
    await store.open()
    return store


def _embedded_item(url: str, title: str, embedding: list[float]) -> Item:
    return Item(
        canonical_url=url,
        title=title,
        source_type="rss",
        source_name="test",
        embedding=pack_embedding(embedding),
    )


async def test_record_run_history_inserts_row(tmp_db: Path) -> None:
    store = await _store(tmp_db)
    started_at = datetime(2025, 1, 1, 12, 0, tzinfo=UTC)

    try:
        await store.record_run_history(
            feed_name="alpha",
            started_at=started_at,
            duration_ms=123,
            status="success",
            fetched=10,
            after_dedup=8,
            dropped=2,
            sent=5,
            overflow=1,
            error="boom",
            trace_id="trace-123",
            dry_run=True,
        )

        async with store.db.execute(
            "SELECT feed_name, started_at, duration_ms, status, fetched, after_dedup, "
            "dropped, sent, overflow, error, trace_id, dry_run FROM feed_run_history"
        ) as cur:
            row = await cur.fetchone()

        assert row is not None
        assert row[0] == "alpha"
        assert datetime.fromisoformat(str(row[1])) == started_at
        assert row[2:] == (123, "success", 10, 8, 2, 5, 1, "boom", "trace-123", 1)
    finally:
        await store.close()


async def test_record_run_history_prunes_to_keep_last_n(tmp_db: Path) -> None:
    store = await _store(tmp_db)
    base = datetime(2025, 1, 1, tzinfo=UTC)

    try:
        for index in range(4):
            await store.record_run_history(
                feed_name="alpha",
                started_at=base + timedelta(minutes=index),
                duration_ms=index,
                status="success",
                keep_last_n=2,
            )

        async with store.db.execute(
            "SELECT duration_ms FROM feed_run_history "
            "WHERE feed_name = ? ORDER BY started_at DESC, id DESC",
            ("alpha",),
        ) as cur:
            rows = await cur.fetchall()

        assert rows == [(3,), (2,)]
    finally:
        await store.close()


async def test_record_run_history_is_per_feed_scoped(tmp_db: Path) -> None:
    store = await _store(tmp_db)
    base = datetime(2025, 1, 1, tzinfo=UTC)

    try:
        for index in range(3):
            await store.record_run_history(
                feed_name="alpha",
                started_at=base + timedelta(minutes=index),
                duration_ms=index,
                status="success",
                keep_last_n=2,
            )
        for index in range(2):
            await store.record_run_history(
                feed_name="beta",
                started_at=base + timedelta(minutes=index),
                duration_ms=10 + index,
                status="failure",
                keep_last_n=2,
            )

        async with store.db.execute(
            "SELECT feed_name, duration_ms FROM feed_run_history "
            "ORDER BY feed_name, started_at DESC, id DESC"
        ) as cur:
            rows = await cur.fetchall()

        assert rows == [
            ("alpha", 2),
            ("alpha", 1),
            ("beta", 11),
            ("beta", 10),
        ]
    finally:
        await store.close()


async def test_record_run_history_failure_does_not_raise(
    tmp_db: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = StateStore(tmp_db)
    warnings: list[tuple[str, dict[str, object]]] = []

    class BrokenConnection:
        async def execute(
            self,
            _sql: str,
            _params: tuple[object, ...] | None = None,
        ) -> None:
            raise RuntimeError("insert exploded")

        async def commit(self) -> None:
            raise AssertionError("commit should not be called after execute failure")

    @asynccontextmanager
    async def fake_write_connection():
        yield BrokenConnection()

    def fake_warning(event: str, **kwargs: object) -> None:
        warnings.append((event, dict(kwargs)))

    monkeypatch.setattr(store, "write_connection", fake_write_connection)
    monkeypatch.setattr(store_module.logger, "warning", fake_warning)

    await store.record_run_history(
        feed_name="alpha",
        started_at=datetime(2025, 1, 1, tzinfo=UTC),
        duration_ms=1,
        status="failure",
    )

    assert warnings == [
        (
            "record_run_history_failed",
            {
                "feed": "alpha",
                "err_type": "RuntimeError",
                "err": "insert exploded",
            },
        )
    ]


async def test_find_similar_seen_items_returns_matches_above_threshold(tmp_db: Path) -> None:
    store = await _store(tmp_db)

    try:
        await store.mark_seen(
            "alpha",
            [
                _embedded_item("https://example.com/match", "Match", [1.0, 0.0]),
                _embedded_item("https://example.com/other", "Other", [0.0, 1.0]),
            ],
            sent=True,
            embedding_model="model-a",
        )

        matches = await store.find_similar_seen_items(
            feed="alpha",
            embedding=[0.9, 0.1],
            embedding_model="model-a",
            threshold=0.8,
            window=timedelta(days=1),
        )

        assert len(matches) == 1
        assert matches[0][0] == "https://example.com/match"
        assert matches[0][1] == "Match"
        assert matches[0][2] > 0.99
    finally:
        await store.close()


async def test_find_similar_seen_items_filters_by_window(tmp_db: Path) -> None:
    store = await _store(tmp_db)

    try:
        await store.mark_seen(
            "alpha",
            [_embedded_item("https://example.com/old", "Old", [1.0, 0.0])],
            sent=True,
            embedding_model="model-a",
        )
        old_timestamp = int((datetime.now(UTC) - timedelta(days=10)).timestamp())
        await store.db.execute(
            "UPDATE seen_items SET sent_at = ? WHERE feed = ? AND url = ?",
            (old_timestamp, "alpha", "https://example.com/old"),
        )
        await store.db.commit()

        matches = await store.find_similar_seen_items(
            feed="alpha",
            embedding=[1.0, 0.0],
            embedding_model="model-a",
            threshold=0.8,
            window=timedelta(hours=1),
        )

        assert matches == []
    finally:
        await store.close()


async def test_find_similar_seen_items_filters_by_model(tmp_db: Path) -> None:
    store = await _store(tmp_db)

    try:
        await store.mark_seen(
            "alpha",
            [_embedded_item("https://example.com/model-a", "Model A", [1.0, 0.0])],
            sent=True,
            embedding_model="model-a",
        )
        await store.mark_seen(
            "alpha",
            [_embedded_item("https://example.com/model-b", "Model B", [1.0, 0.0])],
            sent=True,
            embedding_model="model-b",
        )

        matches = await store.find_similar_seen_items(
            feed="alpha",
            embedding=[1.0, 0.0],
            embedding_model="model-a",
            threshold=0.8,
            window=timedelta(days=1),
        )

        assert matches == [("https://example.com/model-a", "Model A", pytest.approx(1.0))]
    finally:
        await store.close()


async def test_find_similar_seen_items_per_feed_isolation(tmp_db: Path) -> None:
    store = await _store(tmp_db)

    try:
        await store.mark_seen(
            "alpha",
            [_embedded_item("https://example.com/alpha", "Alpha", [1.0, 0.0])],
            sent=True,
            embedding_model="model-a",
        )
        await store.mark_seen(
            "beta",
            [_embedded_item("https://example.com/beta", "Beta", [1.0, 0.0])],
            sent=True,
            embedding_model="model-a",
        )

        matches = await store.find_similar_seen_items(
            feed="alpha",
            embedding=[1.0, 0.0],
            embedding_model="model-a",
            threshold=0.8,
            window=timedelta(days=1),
        )

        assert matches == [("https://example.com/alpha", "Alpha", pytest.approx(1.0))]
    finally:
        await store.close()


async def test_log_suppression_inserts_and_prunes(tmp_db: Path) -> None:
    store = await _store(tmp_db)

    try:
        for index in range(3):
            await store.log_suppression(
                feed_name="alpha",
                suppressed_url=f"https://example.com/suppressed-{index}",
                suppressed_title=f"Suppressed {index}",
                matched_url="https://example.com/matched",
                matched_title="Matched",
                similarity=0.9 + (index * 0.01),
                trace_id=f"trace-{index}",
                keep_last_n=2,
            )
        await store.log_suppression(
            feed_name="beta",
            suppressed_url="https://example.com/beta",
            suppressed_title="Beta",
            matched_url="https://example.com/matched-beta",
            matched_title="Matched Beta",
            similarity=0.95,
            trace_id="trace-beta",
            keep_last_n=2,
        )

        async with store.db.execute(
            "SELECT feed_name, suppressed_url FROM semantic_dedup_log ORDER BY feed_name, id"
        ) as cur:
            rows = await cur.fetchall()

        assert rows == [
            ("alpha", "https://example.com/suppressed-1"),
            ("alpha", "https://example.com/suppressed-2"),
            ("beta", "https://example.com/beta"),
        ]
    finally:
        await store.close()


async def test_mark_seen_preserves_first_seen_and_backfills_embedding_columns(tmp_db: Path) -> None:
    store = await _store(tmp_db)

    try:
        item = _embedded_item("https://example.com/item", "Title", [1.0, 0.0])
        await store.mark_seen("alpha", [item], sent=True, embedding_model="model-a")
        await store.db.execute(
            "UPDATE seen_items SET seen_at = 123, title = NULL, embedding = NULL, "
            "embedding_model = NULL WHERE feed = ? AND url = ?",
            ("alpha", item.canonical_url),
        )
        await store.db.commit()

        await store.mark_seen("alpha", [item], sent=True, embedding_model="model-a")

        async with store.db.execute(
            "SELECT seen_at, title, embedding, embedding_model FROM seen_items "
            "WHERE feed = ? AND url = ?",
            ("alpha", item.canonical_url),
        ) as cur:
            row = await cur.fetchone()

        assert row == (123, "Title", item.embedding, "model-a")
    finally:
        await store.close()
