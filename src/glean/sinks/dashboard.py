"""Dashboard sink for persisted digests.

This sink stores rendered digest fragments in SQLite and emits a
``digest.persisted`` SSE event with payload fields ``feed_name``, ``digest_ids``,
``sent_at``, ``trace_id``, and ``item_count``.
"""

from __future__ import annotations

import contextlib
import datetime as dt
from typing import TYPE_CHECKING, ClassVar

from structlog.contextvars import get_contextvars

from glean.api.events import RunEvent
from glean.logging import get_logger
from glean.sinks.registry import register_sink

if TYPE_CHECKING:
    import aiosqlite

    from glean.sinks.base import SendContext

logger = get_logger(__name__)

_INSERT_DIGEST_SQL = (
    "INSERT INTO digests("
    "feed_name, sent_at, style, intro, body, fragment_index, item_count, trace_id"
    ") VALUES (?, ?, ?, ?, ?, ?, ?, ?)"
)
_PRUNE_DIGESTS_SQL = (
    "DELETE FROM digests WHERE feed_name = ? AND id NOT IN ("
    "SELECT id FROM digests WHERE feed_name = ? ORDER BY sent_at DESC, id DESC LIMIT ?"
    ")"
)
_SAVEPOINT_DIGEST_SQL = "SAVEPOINT dashboard_digest_write"
_ROLLBACK_DIGEST_SQL = "ROLLBACK TO SAVEPOINT dashboard_digest_write"
_RELEASE_DIGEST_SQL = "RELEASE SAVEPOINT dashboard_digest_write"


@register_sink("dashboard")
class DashboardSink:
    type: ClassVar[str] = "dashboard"

    def __init__(self, *, keep_last_n: int = 50, required: bool = True) -> None:
        if keep_last_n < 1:
            raise ValueError("keep_last_n must be >= 1")
        self.keep_last_n = keep_last_n
        self.required = required

    async def send(self, ctx: SendContext) -> None:
        try:
            await self._persist(ctx)
        except Exception as exc:
            if self.required:
                raise
            logger.warning("dashboard_digest_persist_failed", feed=ctx.feed, err=str(exc))

    async def _persist(self, ctx: SendContext) -> None:
        if not ctx.messages:
            return
        if ctx.state is None:
            raise RuntimeError("dashboard sink requires SendContext.state")

        sent_at = dt.datetime.now(dt.UTC).isoformat()
        item_count = len(ctx.items)
        trace_id = _current_trace_id()
        async with ctx.state.write_connection() as conn:
            digest_ids = await self._insert_rows(
                conn,
                feed_name=ctx.feed,
                sent_at=sent_at,
                style=ctx.render.style,
                intro=ctx.intro or None,
                bodies=ctx.messages,
                item_count=item_count,
                trace_id=trace_id,
            )
        await self._publish_event(
            ctx,
            digest_ids=digest_ids,
            sent_at=sent_at,
            trace_id=trace_id,
            item_count=item_count,
        )

    async def _insert_rows(
        self,
        conn: aiosqlite.Connection,
        *,
        feed_name: str,
        sent_at: str,
        style: str,
        intro: str | None,
        bodies: list[str],
        item_count: int,
        trace_id: str | None,
    ) -> list[int]:
        digest_ids: list[int] = []
        savepoint_started = False
        try:
            await conn.execute(_SAVEPOINT_DIGEST_SQL)
            savepoint_started = True
            for fragment_index, body in enumerate(bodies):
                async with conn.execute(
                    _INSERT_DIGEST_SQL,
                    (
                        feed_name,
                        sent_at,
                        style,
                        intro,
                        body,
                        fragment_index,
                        item_count,
                        trace_id,
                    ),
                ) as cur:
                    row_id = cur.lastrowid
                if row_id is None:
                    raise RuntimeError("dashboard sink insert did not return a row id")
                digest_ids.append(int(row_id))
            await conn.execute(_PRUNE_DIGESTS_SQL, (feed_name, feed_name, self.keep_last_n))
            await conn.execute(_RELEASE_DIGEST_SQL)
            await conn.commit()
        except Exception:
            if savepoint_started:
                with contextlib.suppress(Exception):
                    await conn.execute(_ROLLBACK_DIGEST_SQL)
                with contextlib.suppress(Exception):
                    await conn.execute(_RELEASE_DIGEST_SQL)
            raise
        return digest_ids

    async def _publish_event(
        self,
        ctx: SendContext,
        *,
        digest_ids: list[int],
        sent_at: str,
        trace_id: str | None,
        item_count: int,
    ) -> None:
        if ctx.event_bus is None:
            return
        try:
            await ctx.event_bus.publish(
                RunEvent(
                    type="digest.persisted",
                    feed=ctx.feed,
                    digest_ids=digest_ids,
                    sent_at=sent_at,
                    trace_id=trace_id,
                    item_count=item_count,
                )
            )
        except Exception:
            logger.exception(
                "dashboard_digest_event_failed",
                feed=ctx.feed,
                digest_ids=digest_ids,
            )

    async def aclose(self) -> None:
        pass


def _current_trace_id() -> str | None:
    trace_id = get_contextvars().get("trace_id")
    if isinstance(trace_id, str) and trace_id:
        return trace_id
    return None
