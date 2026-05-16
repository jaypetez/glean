"""REST API routes for digest history."""

from __future__ import annotations

import datetime as dt
from typing import Annotated, Literal, cast

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict, Field

from glean.api.routes.feeds import _load_or_400, _require_feed
from glean.state.store import StateStore

router = APIRouter(tags=["digests"])

_DIGEST_LIST_SQL = """
WITH cursor_row AS (
    SELECT sent_at, id
    FROM digests
    WHERE id = ?
)
SELECT id, feed_name, sent_at, style, intro, body, fragment_index, item_count, trace_id
FROM digests
WHERE (
    ? IS NULL OR (
        EXISTS(SELECT 1 FROM cursor_row) AND (
            sent_at < (SELECT sent_at FROM cursor_row)
            OR (
                sent_at = (SELECT sent_at FROM cursor_row)
                AND id < (SELECT id FROM cursor_row)
            )
        )
    )
)
  AND (? IS NULL OR feed_name = ?)
ORDER BY sent_at DESC, id DESC
LIMIT ?
"""


class DigestResponse(BaseModel):
    """Stored digest fragment returned by API routes."""

    model_config = ConfigDict(extra="forbid")

    id: int
    feed_name: str
    sent_at: dt.datetime
    style: Literal["html", "markdown_v2", "plain"]
    intro: str | None
    body: str
    fragment_index: int
    item_count: int
    trace_id: str | None


class DigestListQuery(BaseModel):
    """Pagination query parameters for digest list endpoints."""

    model_config = ConfigDict(extra="forbid")

    limit: int = Field(default=50, ge=1, le=200)
    before: int | None = Field(default=None, ge=1)


@router.get("/digests", response_model=list[DigestResponse])
async def list_digests(
    request: Request,
    query: Annotated[DigestListQuery, Depends()],
) -> list[DigestResponse]:
    state = cast(StateStore, request.app.state.glean_state)
    return await _fetch_digests(state, before=query.before, feed_name=None, limit=query.limit)


@router.get("/feeds/{name}/digests", response_model=list[DigestResponse])
async def list_feed_digests(
    request: Request,
    name: str,
    query: Annotated[DigestListQuery, Depends()],
) -> list[DigestResponse]:
    cfg = _load_or_400()
    _require_feed(cfg, name)
    state = cast(StateStore, request.app.state.glean_state)
    return await _fetch_digests(state, before=query.before, feed_name=name, limit=query.limit)


async def _fetch_digests(
    state: StateStore,
    *,
    before: int | None,
    feed_name: str | None,
    limit: int,
) -> list[DigestResponse]:
    async with state.db.execute(
        _DIGEST_LIST_SQL,
        (before, before, feed_name, feed_name, limit),
    ) as cur:
        rows = await cur.fetchall()
    return [
        DigestResponse.model_validate(
            {
                "id": row[0],
                "feed_name": row[1],
                "sent_at": row[2],
                "style": row[3],
                "intro": row[4],
                "body": row[5],
                "fragment_index": row[6],
                "item_count": row[7],
                "trace_id": row[8],
            }
        )
        for row in rows
    ]
