"""REST API routes for feed runs and status."""

from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING, Annotated, Literal, cast

from fastapi import APIRouter, HTTPException, Query, Request, status

from glean.api.models import FeedRunResponse, FeedStatusResponse, RunResultResponse
from glean.api_service.run_service import get_feed_status, list_feeds_with_status, run_feed_once
from glean.config import Config, load_config
from glean.config.loader import ConfigError
from glean.security.scrub import scrub
from glean.state.store import StateStore
from glean.telegram import TelegramSender

if TYPE_CHECKING:
    from glean.api_service.run_service import FeedStatus
    from glean.pipeline.engine import RunResult

router = APIRouter(prefix="/feeds", tags=["feeds"])

_FEED_RUN_LIST_SQL = """
WITH cursor_row AS (
    SELECT started_at, id
    FROM feed_run_history
    WHERE id = ?
)
SELECT id, feed_name, started_at, duration_ms, status, fetched, after_dedup, dropped, sent,
       overflow, error, trace_id, dry_run
FROM feed_run_history
WHERE feed_name = ?
  AND (
    ? IS NULL OR (
        EXISTS(SELECT 1 FROM cursor_row) AND (
            started_at < (SELECT started_at FROM cursor_row)
            OR (
                started_at = (SELECT started_at FROM cursor_row)
                AND id < (SELECT id FROM cursor_row)
            )
        )
    )
)
  AND (? IS NULL OR status = ?)
ORDER BY started_at DESC, id DESC
LIMIT ?
"""


def _config_path() -> Path:
    return Path(os.environ.get("GLEAN_CONFIG", "/etc/glean/feeds.yaml"))


def _load_or_400() -> Config:
    try:
        return load_config(_config_path())
    except ConfigError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"config load error: {exc}",
        ) from exc


@router.get("", response_model=list[FeedStatusResponse])
async def list_feeds(request: Request) -> list[FeedStatusResponse]:
    cfg = _load_or_400()
    statuses = await list_feeds_with_status(cfg, request.app.state.glean_state)
    return [_to_status_response(s) for s in statuses]


@router.get("/{name}/status", response_model=FeedStatusResponse)
async def feed_status(request: Request, name: str) -> FeedStatusResponse:
    cfg = _load_or_400()
    try:
        status_result = await get_feed_status(cfg, request.app.state.glean_state, name)
    except KeyError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"no such feed: {name!r}",
        ) from exc
    return _to_status_response(status_result)


@router.get("/{name}/runs", response_model=list[FeedRunResponse])
async def list_feed_runs(
    request: Request,
    name: str,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    before: Annotated[int | None, Query(ge=1)] = None,
    status: Annotated[Literal["success", "failure", "skip"] | None, Query()] = None,
) -> list[FeedRunResponse]:
    cfg = _load_or_400()
    _require_feed(cfg, name)
    state = cast(StateStore, request.app.state.glean_state)
    return await _fetch_feed_runs(state, feed_name=name, before=before, limit=limit, status=status)


@router.post("/{name}/test", response_model=RunResultResponse)
async def test_feed(request: Request, name: str) -> RunResultResponse:
    """Dry-run a feed (no Telegram, no state writes for sending)."""
    cfg = _load_or_400()
    _require_feed(cfg, name)
    result = await run_feed_once(
        cfg,
        request.app.state.glean_state,
        name,
        dry_run=True,
        telegram=None,
        event_bus=request.app.state.glean_event_bus,
    )
    return _to_run_response(result)


@router.post("/{name}/run", response_model=RunResultResponse)
async def run_feed_now(request: Request, name: str) -> RunResultResponse:
    """Run a feed off-schedule with real sends."""
    cfg = _load_or_400()
    _require_feed(cfg, name)
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    telegram = TelegramSender(token) if token else None
    try:
        result = await run_feed_once(
            cfg,
            request.app.state.glean_state,
            name,
            dry_run=False,
            telegram=telegram,
            event_bus=request.app.state.glean_event_bus,
        )
    finally:
        if telegram is not None:
            await telegram.aclose()
    return _to_run_response(result)


def _require_feed(cfg: Config, name: str) -> None:
    try:
        cfg.feed(name)
    except KeyError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"no such feed: {name!r}",
        ) from exc


def _to_status_response(status_result: FeedStatus) -> FeedStatusResponse:
    return FeedStatusResponse(
        name=status_result.name,
        schedule=status_result.schedule,
        llm_provider=status_result.llm_provider,
        llm_model=status_result.llm_model,
        last_success_at=status_result.last_success_at,
        last_attempt_at=status_result.last_attempt_at,
        last_error=scrub(status_result.last_error)[:500] if status_result.last_error else None,
        consecutive_failures=status_result.consecutive_failures,
        alert_active=status_result.alert_active,
        bootstrapped=status_result.bootstrapped,
    )


async def _fetch_feed_runs(
    state: StateStore,
    *,
    feed_name: str,
    before: int | None,
    limit: int,
    status: Literal["success", "failure", "skip"] | None,
) -> list[FeedRunResponse]:
    async with state.db.execute(
        _FEED_RUN_LIST_SQL,
        (before, feed_name, before, status, status, limit),
    ) as cur:
        rows = await cur.fetchall()
    return [
        FeedRunResponse.model_validate(
            {
                "id": row[0],
                "feed_name": row[1],
                "started_at": row[2],
                "duration_ms": row[3],
                "status": row[4],
                "fetched": row[5],
                "after_dedup": row[6],
                "dropped": row[7],
                "sent": row[8],
                "overflow": row[9],
                "error": row[10],
                "trace_id": row[11],
                "dry_run": bool(row[12]),
            }
        )
        for row in rows
    ]


def _to_run_response(result: RunResult) -> RunResultResponse:
    return RunResultResponse(
        feed=result.feed,
        fetched=result.fetched,
        after_dedup=result.after_dedup,
        sent=result.sent,
        dropped=result.dropped,
        overflow=result.overflow,
        duration_ms=result.duration_ms,
        error=scrub(result.error)[:500] if result.error else None,
        skipped_reason=result.skipped_reason,
        messages=result.messages,
    )
