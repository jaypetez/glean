from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from glean.sources.base import Item
from glean.state.store import StateStore

pytestmark = pytest.mark.asyncio


async def _store(path: Path) -> StateStore:
    s = StateStore(path)
    await s.open()
    return s


def _item(url: str, title: str = "t") -> Item:
    return Item(canonical_url=url, title=title, source_type="rss", source_name="x")


async def test_dedup_first_run_returns_all(tmp_db: Path) -> None:
    s = await _store(tmp_db)
    try:
        items = [_item("a"), _item("b"), _item("c")]
        out = await s.filter_new("ai", items)
        assert {i.canonical_url for i in out} == {"a", "b", "c"}
    finally:
        await s.close()


async def test_mark_seen_then_dedup(tmp_db: Path) -> None:
    s = await _store(tmp_db)
    try:
        items = [_item("a"), _item("b")]
        await s.mark_seen("ai", items, sent=True)
        out = await s.filter_new("ai", [_item("a"), _item("c")])
        assert {i.canonical_url for i in out} == {"c"}
    finally:
        await s.close()


async def test_failure_alert_threshold(tmp_db: Path) -> None:
    s = await _store(tmp_db)
    try:
        count, should = await s.record_failure("ai", "boom", alert_after=3)
        assert (count, should) == (1, False)
        count, should = await s.record_failure("ai", "boom", alert_after=3)
        assert (count, should) == (2, False)
        count, should = await s.record_failure("ai", "boom", alert_after=3)
        assert count == 3 and should is True
        # subsequent failures should not re-alert
        _, should = await s.record_failure("ai", "boom", alert_after=3)
        assert should is False
    finally:
        await s.close()


async def test_recovery_clears_alert(tmp_db: Path) -> None:
    s = await _store(tmp_db)
    try:
        for _ in range(3):
            await s.record_failure("ai", "boom", alert_after=3)
        recovered = await s.record_success("ai")
        assert recovered is True
        # next success should not be flagged as recovery again
        recovered = await s.record_success("ai")
        assert recovered is False
    finally:
        await s.close()


async def test_bootstrap_flag(tmp_db: Path) -> None:
    s = await _store(tmp_db)
    try:
        assert await s.is_bootstrapped("ai") is False
        await s.set_bootstrapped("ai")
        assert await s.is_bootstrapped("ai") is True
    finally:
        await s.close()


async def test_open_enables_wal_mode(tmp_db: Path) -> None:
    s = StateStore(tmp_db)
    try:
        await s.open()
        async with s.db.execute("PRAGMA journal_mode") as cur:
            journal_mode = await cur.fetchone()
        async with s.db.execute("PRAGMA synchronous") as cur:
            synchronous = await cur.fetchone()
        assert journal_mode == ("wal",)
        assert synchronous == (1,)
    finally:
        await s.close()


async def test_open_enables_security_pragmas(tmp_db: Path) -> None:
    s = StateStore(tmp_db)
    try:
        await s.open()
        async with s.db.execute("SELECT * FROM pragma_foreign_keys") as cur:
            foreign_keys = await cur.fetchone()
        async with s.db.execute("SELECT * FROM pragma_secure_delete") as cur:
            secure_delete = await cur.fetchone()
        async with s.db.execute("SELECT * FROM pragma_trusted_schema") as cur:
            trusted_schema = await cur.fetchone()
        assert foreign_keys == (1,)
        assert secure_delete == (1,)
        assert trusted_schema == (0,)
    finally:
        await s.close()


async def test_db_root_override_allows_tmp_path_outside_pytest(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    root = tmp_path / "allowed"
    db_path = root / "state.db"
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    monkeypatch.setenv("GLEAN_DB_ROOT", str(root))

    s = StateStore(db_path)
    try:
        await s.open()
        assert db_path.exists()
    finally:
        await s.close()


async def test_db_root_override_supports_comma_separated_roots(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    first_root = tmp_path / "first"
    second_root = tmp_path / "second"
    db_path = second_root / "state.db"
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    monkeypatch.setenv("GLEAN_DB_ROOT", f"{first_root},{second_root}")

    s = StateStore(db_path)
    try:
        await s.open()
        assert db_path.exists()
    finally:
        await s.close()


async def test_db_path_outside_allowed_root_raises_value_error(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    root = tmp_path / "allowed"
    db_path = tmp_path / "other" / "state.db"
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    monkeypatch.setenv("GLEAN_DB_ROOT", str(root))

    with pytest.raises(ValueError, match="outside allowed database roots"):
        StateStore(db_path)


async def test_open_raises_when_wal_mode_cannot_be_enabled(
    monkeypatch: pytest.MonkeyPatch, tmp_db: Path
) -> None:
    class FakeCursor:
        def __init__(self, row: tuple[str, ...]) -> None:
            self._row = row

        async def __aenter__(self) -> FakeCursor:
            return self

        async def __aexit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
            return None

        async def fetchone(self) -> tuple[str, ...]:
            return self._row

    class FakeConnection:
        def __init__(self) -> None:
            self.closed = False

        def execute(self, sql: str) -> FakeCursor:
            assert sql == "PRAGMA journal_mode=WAL"
            return FakeCursor(("delete",))

        async def executescript(self, script: str) -> None:
            raise AssertionError("schema should not be applied when WAL cannot be enabled")

        async def commit(self) -> None:
            raise AssertionError("commit should not run when WAL cannot be enabled")

        async def close(self) -> None:
            self.closed = True

    fake_db = FakeConnection()

    async def fake_connect(path: Path) -> FakeConnection:
        assert path == tmp_db
        return fake_db

    monkeypatch.setattr("glean.state.store.aiosqlite.connect", fake_connect)

    s = StateStore(tmp_db)
    with pytest.raises(RuntimeError, match="Failed to enable WAL mode"):
        await s.open()
    assert fake_db.closed is True
    assert s._db is None
