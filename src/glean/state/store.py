from __future__ import annotations

import asyncio
import hashlib
import os
import time
import warnings
from collections.abc import Iterable
from pathlib import Path

import aiosqlite
from yoyo import get_backend, read_migrations

from glean.sources.base import Item


def item_hash(item: Item) -> str:
    if item.canonical_url:
        seed = item.canonical_url
    else:
        seed = f"{item.title}\n{item.body[:512]}"
    return hashlib.sha256(seed.encode("utf-8")).hexdigest()


def _allowed_db_roots() -> list[Path]:
    root_spec = os.environ.get("GLEAN_DB_ROOT")
    roots = root_spec.split(",") if root_spec else ["/data"]
    return [Path(root.strip()).expanduser().resolve() for root in roots if root.strip()]


def _validate_db_path(path: Path) -> None:
    if os.environ.get("PYTEST_CURRENT_TEST") is not None:
        return

    allowed_roots = _allowed_db_roots()
    if any(path == root or path.is_relative_to(root) for root in allowed_roots):
        return

    allowed = ", ".join(str(root) for root in allowed_roots)
    raise ValueError(f"SQLite state DB path {path} is outside allowed database roots: {allowed}")


class StateStore:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path).expanduser().resolve()
        _validate_db_path(self.path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._db: aiosqlite.Connection | None = None

    async def open(self) -> None:
        await self._apply_migrations()
        self._db = await aiosqlite.connect(self.path)
        async with self._db.execute("PRAGMA journal_mode=WAL") as cur:
            journal_mode = await cur.fetchone()
        if journal_mode is None or str(journal_mode[0]).lower() != "wal":
            await self._db.close()
            self._db = None
            raise RuntimeError(f"Failed to enable WAL mode for {self.path}")
        await self._db.execute("PRAGMA foreign_keys = ON")
        await self._db.execute("PRAGMA secure_delete = ON")
        await self._db.execute("PRAGMA trusted_schema = OFF")
        await self._db.execute("PRAGMA synchronous=NORMAL")
        await self._db.commit()

    async def _apply_migrations(self) -> None:
        """Run any pending schema migrations using yoyo."""

        def run_sync() -> None:
            backend = get_backend(f"sqlite:///{self.path.as_posix()}")
            migrations_dir = Path(__file__).parent / "migrations"
            migrations = read_migrations(str(migrations_dir))
            with warnings.catch_warnings():
                warnings.filterwarnings(
                    "ignore",
                    message="The default datetime adapter is deprecated.*",
                    category=DeprecationWarning,
                )
                with backend.lock():
                    backend.apply_migrations(backend.to_apply(migrations))

        await asyncio.to_thread(run_sync)

    async def close(self) -> None:
        if self._db is not None:
            await self._db.close()
            self._db = None

    @property
    def db(self) -> aiosqlite.Connection:
        if self._db is None:
            raise RuntimeError("StateStore is not open")
        return self._db

    async def filter_new(self, feed: str, items: Iterable[Item]) -> list[Item]:
        items = list(items)
        if not items:
            return []
        hashes = {item_hash(i): i for i in items}
        placeholders = ",".join("?" * len(hashes))
        # `placeholders` is built from a count of items, never from user input.
        query = f"SELECT item_hash FROM seen_items WHERE feed = ? AND item_hash IN ({placeholders})"  # noqa: S608 # nosec
        async with self.db.execute(query, (feed, *hashes.keys())) as cur:
            seen = {row[0] async for row in cur}
        return [i for h, i in hashes.items() if h not in seen]

    async def mark_seen(self, feed: str, items: Iterable[Item], *, sent: bool) -> None:
        now = int(time.time())
        rows = [(feed, item_hash(i), i.canonical_url, now, 1 if sent else 0) for i in items]
        if not rows:
            return
        await self.db.executemany(
            "INSERT OR IGNORE INTO seen_items(feed, item_hash, url, seen_at, sent) "
            "VALUES (?, ?, ?, ?, ?)",
            rows,
        )
        await self.db.commit()

    async def is_bootstrapped(self, feed: str) -> bool:
        async with self.db.execute(
            "SELECT bootstrapped FROM feed_runs WHERE feed = ?", (feed,)
        ) as cur:
            row = await cur.fetchone()
        return bool(row and row[0])

    async def set_bootstrapped(self, feed: str) -> None:
        await self.db.execute(
            "INSERT INTO feed_runs(feed, bootstrapped) VALUES (?, 1) "
            "ON CONFLICT(feed) DO UPDATE SET bootstrapped = 1",
            (feed,),
        )
        await self.db.commit()

    async def record_success(self, feed: str) -> bool:
        """Return True if a recovery alert should be posted."""
        now = int(time.time())
        async with self.db.execute(
            "SELECT alert_active FROM feed_runs WHERE feed = ?", (feed,)
        ) as cur:
            row = await cur.fetchone()
        was_alerting = bool(row and row[0])
        await self.db.execute(
            "INSERT INTO feed_runs(feed, last_success_at, last_attempt_at, "
            "consecutive_failures, alert_active) VALUES (?, ?, ?, 0, 0) "
            "ON CONFLICT(feed) DO UPDATE SET "
            "last_success_at = excluded.last_success_at, "
            "last_attempt_at = excluded.last_attempt_at, "
            "consecutive_failures = 0, alert_active = 0",
            (feed, now, now),
        )
        await self.db.commit()
        return was_alerting

    async def record_failure(self, feed: str, error: str, alert_after: int) -> tuple[int, bool]:
        """Return (consecutive_failures, should_alert_now)."""
        now = int(time.time())
        await self.db.execute(
            "INSERT INTO feed_runs(feed, last_attempt_at, last_error, "
            "consecutive_failures) VALUES (?, ?, ?, 1) "
            "ON CONFLICT(feed) DO UPDATE SET "
            "last_attempt_at = excluded.last_attempt_at, "
            "last_error = excluded.last_error, "
            "consecutive_failures = consecutive_failures + 1",
            (feed, now, error),
        )
        async with self.db.execute(
            "SELECT consecutive_failures, alert_active FROM feed_runs WHERE feed = ?",
            (feed,),
        ) as cur:
            row = await cur.fetchone()
        await self.db.commit()
        if row is None:
            return 1, False
        count, active = int(row[0]), bool(row[1])
        if count >= alert_after and not active:
            await self.db.execute("UPDATE feed_runs SET alert_active = 1 WHERE feed = ?", (feed,))
            await self.db.commit()
            return count, True
        return count, False

    async def get_etag(self, url: str) -> tuple[str | None, str | None]:
        async with self.db.execute(
            "SELECT etag, last_modified FROM etag_cache WHERE url = ?", (url,)
        ) as cur:
            row = await cur.fetchone()
        if row is None:
            return None, None
        return row[0], row[1]

    async def set_etag(self, url: str, etag: str | None, last_modified: str | None) -> None:
        await self.db.execute(
            "INSERT INTO etag_cache(url, etag, last_modified, cached_at) "
            "VALUES (?, ?, ?, ?) ON CONFLICT(url) DO UPDATE SET "
            "etag = excluded.etag, last_modified = excluded.last_modified, "
            "cached_at = excluded.cached_at",
            (url, etag, last_modified, int(time.time())),
        )
        await self.db.commit()

    async def prune_seen(self, older_than_days: int = 60) -> int:
        cutoff = int(time.time()) - older_than_days * 86400
        cur = await self.db.execute("DELETE FROM seen_items WHERE seen_at < ?", (cutoff,))
        await self.db.commit()
        return cur.rowcount or 0
