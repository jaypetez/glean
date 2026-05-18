from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from glean.state import store as store_module
from glean.state.store import StateStore

pytestmark = pytest.mark.asyncio


async def _store(path: Path) -> StateStore:
    store = StateStore(path)
    await store.open()
    return store


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
