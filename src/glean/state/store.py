from __future__ import annotations

import asyncio
import contextlib
import hashlib
import os
import time
import warnings
from collections.abc import AsyncIterator, Iterable
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from pathlib import Path
from typing import Literal

import aiosqlite
from yoyo import get_backend, read_migrations

from glean.logging import get_logger
from glean.sources.base import Item
from glean.state.embedding_bytes import cosine_similarity, unpack_embedding


def item_hash(item: Item) -> str:
    if item.canonical_url:
        seed = item.canonical_url
    else:
        seed = f"{item.title}\n{item.body[:512]}"
    return hashlib.sha256(seed.encode("utf-8")).hexdigest()


logger = get_logger(__name__)

_RUN_HISTORY_SAVEPOINT_SQL = "SAVEPOINT feed_run_history_write"
_RUN_HISTORY_ROLLBACK_SQL = "ROLLBACK TO SAVEPOINT feed_run_history_write"
_RUN_HISTORY_RELEASE_SQL = "RELEASE SAVEPOINT feed_run_history_write"
_RUN_HISTORY_INSERT_SQL = (
    "INSERT INTO feed_run_history ("
    "feed_name, started_at, duration_ms, status, fetched, after_dedup, dropped, sent, "
    "overflow, error, trace_id, dry_run"
    ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
)
_RUN_HISTORY_PRUNE_SQL = (
    "DELETE FROM feed_run_history WHERE feed_name = ? AND id NOT IN ("
    "SELECT id FROM feed_run_history WHERE feed_name = ? "
    "ORDER BY started_at DESC, id DESC LIMIT ?"
    ")"
)


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
        self._write_lock = asyncio.Lock()

    async def open(self) -> None:
        # AGENT: To add a column or table, create src/glean/state/migrations/NNNN_*.sql
        # with `-- depends: NNNN_previous` header. Migrations apply automatically on open.
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

    @asynccontextmanager
    async def write_connection(self) -> AsyncIterator[aiosqlite.Connection]:
        async with self._write_lock:
            yield self.db

    async def ping(self) -> None:
        """Run a trivial query to verify the connection is healthy."""
        if self._db is None:
            raise RuntimeError("StateStore is not open")
        async with self._db.execute("SELECT 1") as cur:
            await cur.fetchone()

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

    async def mark_seen(
        self,
        feed: str,
        items: Iterable[Item],
        *,
        sent: bool,
        embedding: bytes | None = None,
        embedding_model: str | None = None,
    ) -> None:
        now = int(time.time())
        sent_at = now if sent else None
        rows = [
            (
                feed,
                item_hash(item),
                item.canonical_url,
                item.title,
                now,
                1 if sent else 0,
                sent_at,
                item.embedding if item.embedding is not None else embedding,
                embedding_model,
            )
            for item in items
        ]
        if not rows:
            return
        async with self._write_lock:
            await self.db.executemany(
                "INSERT INTO seen_items(feed, item_hash, url, title, seen_at, sent, sent_at, "
                "embedding, embedding_model) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(feed, item_hash) DO UPDATE SET "
                "url = COALESCE(NULLIF(excluded.url, ''), seen_items.url), "
                "title = COALESCE(NULLIF(excluded.title, ''), seen_items.title), "
                "seen_at = seen_items.seen_at, "
                "sent = MAX(seen_items.sent, excluded.sent), "
                "sent_at = COALESCE(seen_items.sent_at, excluded.sent_at), "
                "embedding = COALESCE(excluded.embedding, seen_items.embedding), "
                "embedding_model = COALESCE(excluded.embedding_model, seen_items.embedding_model)",
                rows,
            )
            await self.db.commit()

    async def find_similar_seen_items(
        self,
        *,
        feed: str,
        embedding: list[float] | bytes,
        embedding_model: str,
        threshold: float | None = None,
        min_similarity: float | None = None,
        window: timedelta,
    ) -> list[tuple[str, str | None, float]]:
        """Return sent items in a feed whose embeddings meet the similarity threshold.

        Results are scoped to the requested feed and embedding model, filtered to
        sent items newer than the provided time window, and sorted by descending
        cosine similarity.
        """
        if threshold is not None and min_similarity is not None:
            raise ValueError(
                "find_similar_seen_items accepts either threshold or min_similarity, not both"
            )
        effective_threshold = min_similarity if min_similarity is not None else threshold
        if effective_threshold is None:
            raise ValueError("find_similar_seen_items requires threshold or min_similarity")
        query_embedding = (
            unpack_embedding(embedding) if isinstance(embedding, bytes) else list(embedding)
        )
        cutoff = int(time.time() - window.total_seconds())
        matches: list[tuple[str, str | None, float]] = []
        async with self.db.execute(
            "SELECT url, title, embedding FROM seen_items "
            "WHERE feed = ? AND sent = 1 AND sent_at >= ? AND embedding IS NOT NULL "
            "AND embedding_model = ?",
            (feed, cutoff, embedding_model),
        ) as cur:
            async for row in cur:
                packed = row[2]
                if packed is None:
                    continue
                similarity = cosine_similarity(query_embedding, unpack_embedding(bytes(packed)))
                if similarity >= effective_threshold:
                    title = row[1] if row[1] is None else str(row[1])
                    matches.append((str(row[0] or ""), title, similarity))
        matches.sort(key=lambda match: (-match[2], match[0]))
        return matches

    async def is_bootstrapped(self, feed: str) -> bool:
        async with self.db.execute(
            "SELECT bootstrapped FROM feed_runs WHERE feed = ?", (feed,)
        ) as cur:
            row = await cur.fetchone()
        return bool(row and row[0])

    async def set_bootstrapped(self, feed: str) -> None:
        async with self._write_lock:
            await self.db.execute(
                "INSERT INTO feed_runs(feed, bootstrapped) VALUES (?, 1) "
                "ON CONFLICT(feed) DO UPDATE SET bootstrapped = 1",
                (feed,),
            )
            await self.db.commit()

    async def record_success(self, feed: str) -> bool:
        """Return True if a recovery alert should be posted."""
        now = int(time.time())
        async with self._write_lock:
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
        async with self._write_lock:
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
                await self.db.execute(
                    "UPDATE feed_runs SET alert_active = 1 WHERE feed = ?", (feed,)
                )
                await self.db.commit()
                return count, True
        return count, False

    async def record_run_history(
        self,
        *,
        feed_name: str,
        started_at: datetime,
        duration_ms: int,
        status: Literal["success", "failure", "skip"],
        fetched: int = 0,
        after_dedup: int = 0,
        dropped: int = 0,
        sent: int = 0,
        overflow: int = 0,
        error: str | None = None,
        trace_id: str | None = None,
        dry_run: bool = False,
        keep_last_n: int = 200,
    ) -> None:
        """Append a tick record to feed_run_history. Best-effort: errors are swallowed."""
        async with self.write_connection() as conn:
            savepoint_started = False
            try:
                await conn.execute(_RUN_HISTORY_SAVEPOINT_SQL)
                savepoint_started = True
                await conn.execute(
                    _RUN_HISTORY_INSERT_SQL,
                    (
                        feed_name,
                        started_at.isoformat(),
                        duration_ms,
                        status,
                        fetched,
                        after_dedup,
                        dropped,
                        sent,
                        overflow,
                        error,
                        trace_id,
                        1 if dry_run else 0,
                    ),
                )
                await conn.execute(_RUN_HISTORY_PRUNE_SQL, (feed_name, feed_name, keep_last_n))
                await conn.execute(_RUN_HISTORY_RELEASE_SQL)
                await conn.commit()
            except Exception as exc:
                if savepoint_started:
                    with contextlib.suppress(Exception):
                        await conn.execute(_RUN_HISTORY_ROLLBACK_SQL)
                    with contextlib.suppress(Exception):
                        await conn.execute(_RUN_HISTORY_RELEASE_SQL)
                logger.warning(
                    "record_run_history_failed",
                    feed=feed_name,
                    err_type=type(exc).__name__,
                    err=str(exc)[:200] or "(no message)",
                )

    async def log_suppression(
        self,
        *,
        feed_name: str,
        suppressed_url: str,
        suppressed_title: str | None,
        matched_url: str,
        matched_title: str | None,
        similarity: float,
        trace_id: str | None,
        keep_last_n: int = 200,
    ) -> None:
        """Append a suppression event and prune history to the latest rows per feed."""
        async with self.write_connection() as conn:
            savepoint_started = False
            try:
                await conn.execute("SAVEPOINT semantic_dedup_log_write")
                savepoint_started = True
                await conn.execute(
                    "INSERT INTO semantic_dedup_log("
                    "feed_name, suppressed_url, suppressed_title, matched_url, matched_title, "
                    "similarity, trace_id) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (
                        feed_name,
                        suppressed_url,
                        suppressed_title,
                        matched_url,
                        matched_title,
                        similarity,
                        trace_id,
                    ),
                )
                await conn.execute(
                    "DELETE FROM semantic_dedup_log WHERE feed_name = ? AND id NOT IN ("
                    "SELECT id FROM semantic_dedup_log WHERE feed_name = ? "
                    "ORDER BY suppressed_at DESC, id DESC LIMIT ?)",
                    (feed_name, feed_name, keep_last_n),
                )
                await conn.execute("RELEASE SAVEPOINT semantic_dedup_log_write")
                await conn.commit()
            except Exception:
                if savepoint_started:
                    with contextlib.suppress(Exception):
                        await conn.execute("ROLLBACK TO SAVEPOINT semantic_dedup_log_write")
                    with contextlib.suppress(Exception):
                        await conn.execute("RELEASE SAVEPOINT semantic_dedup_log_write")
                raise

    async def get_etag(self, url: str) -> tuple[str | None, str | None]:
        async with self.db.execute(
            "SELECT etag, last_modified FROM etag_cache WHERE url = ?", (url,)
        ) as cur:
            row = await cur.fetchone()
        if row is None:
            return None, None
        return row[0], row[1]

    async def set_etag(self, url: str, etag: str | None, last_modified: str | None) -> None:
        async with self._write_lock:
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
        async with self._write_lock:
            cur = await self.db.execute("DELETE FROM seen_items WHERE seen_at < ?", (cutoff,))
            await self.db.commit()
            return cur.rowcount or 0
