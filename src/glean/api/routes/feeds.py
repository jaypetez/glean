"""REST API routes for feed runs and status."""
from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING

from fastapi import APIRouter, HTTPException, Request, status

from glean.api.models import FeedStatusResponse, RunResultResponse
from glean.api_service.run_service import get_feed_status, list_feeds_with_status, run_feed_once
from glean.config import Config, load_config
from glean.config.loader import ConfigError
from glean.telegram import TelegramSender

if TYPE_CHECKING:
    from glean.api_service.run_service import FeedStatus
    from glean.pipeline.engine import RunResult

router = APIRouter(prefix="/feeds", tags=["feeds"])


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
        last_error=status_result.last_error,
        consecutive_failures=status_result.consecutive_failures,
        alert_active=status_result.alert_active,
        bootstrapped=status_result.bootstrapped,
    )


def _to_run_response(result: RunResult) -> RunResultResponse:
    return RunResultResponse(
        feed=result.feed,
        fetched=result.fetched,
        after_dedup=result.after_dedup,
        sent=result.sent,
        dropped=result.dropped,
        overflow=result.overflow,
        duration_ms=result.duration_ms,
        error=result.error,
        skipped_reason=result.skipped_reason,
        messages=result.messages,
    )
