"""Feed run + status service functions used by CLI + API."""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import TYPE_CHECKING

from glean.config import Config
from glean.pipeline.engine import Runner, RunResult

if TYPE_CHECKING:
    from glean.api.events import EventBus
    from glean.state.store import StateStore
    from glean.telegram import TelegramSender


@dataclass(frozen=True, slots=True)
class FeedStatus:
    """Runtime status of a single feed (combines config + feed_runs row)."""

    name: str
    schedule: str
    llm_provider: str
    llm_model: str
    last_success_at: dt.datetime | None
    last_attempt_at: dt.datetime | None
    last_error: str | None
    consecutive_failures: int
    alert_active: bool
    bootstrapped: bool


async def list_feeds_with_status(cfg: Config, state: StateStore) -> list[FeedStatus]:
    """Return per-feed status info merging Config + feed_runs."""
    out: list[FeedStatus] = []
    for feed in cfg.feeds:
        async with state.db.execute(
            "SELECT last_success_at, last_attempt_at, last_error, "
            "consecutive_failures, alert_active, bootstrapped "
            "FROM feed_runs WHERE feed = ?",
            (feed.name,),
        ) as cur:
            row = await cur.fetchone()
        if row is None:
            ls = la = None
            le: str | None = None
            cf = 0
            alert = False
            boot = False
        else:
            ls_ts, la_ts, le, cf, alert_int, boot_int = row
            ls = dt.datetime.fromtimestamp(ls_ts, tz=dt.UTC) if ls_ts else None
            la = dt.datetime.fromtimestamp(la_ts, tz=dt.UTC) if la_ts else None
            alert = bool(alert_int)
            boot = bool(boot_int)
        llm = feed.effective_llm(cfg.defaults)
        out.append(
            FeedStatus(
                name=feed.name,
                schedule=feed.schedule,
                llm_provider=llm.provider,
                llm_model=llm.model,
                last_success_at=ls,
                last_attempt_at=la,
                last_error=le,
                consecutive_failures=cf,
                alert_active=alert,
                bootstrapped=boot,
            )
        )
    return out


async def run_feed_once(
    cfg: Config,
    state: StateStore,
    name: str,
    *,
    dry_run: bool,
    telegram: TelegramSender | None = None,
    event_bus: EventBus | None = None,
) -> RunResult:
    """Run a single feed once. Caller manages injected telegram lifecycle."""
    cfg.feed(name)  # raises KeyError if feed missing — let caller handle
    runner = Runner(cfg, state, telegram, close_telegram=False, event_bus=event_bus)
    try:
        return await runner.run_feed(name, dry_run=dry_run)
    finally:
        await runner.aclose()


async def get_feed_status(cfg: Config, state: StateStore, name: str) -> FeedStatus:
    """Get the runtime status for a single feed. Raises KeyError if not found."""
    cfg.feed(name)  # raises KeyError if missing
    statuses = await list_feeds_with_status(cfg, state)
    for status in statuses:
        if status.name == name:
            return status
    raise KeyError(f"feed not found in status list: {name!r}")
