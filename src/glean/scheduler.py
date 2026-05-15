from __future__ import annotations

import os
from datetime import UTC, datetime
from typing import TYPE_CHECKING
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from apscheduler import AsyncScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from glean.config.schedule import (
    CronSchedule,
    IntervalSchedule,
    Schedule,
    parse_schedule,
)
from glean.logging import get_logger

if TYPE_CHECKING:
    from glean.config.schema import FeedConfig
    from glean.pipeline.engine import Runner

logger = get_logger(__name__)


async def schedule_feeds(scheduler: AsyncScheduler, runner: Runner) -> None:
    for feed in runner.config.feeds:
        await _add_feed_job(scheduler, runner, feed)


def _timezone_from_env() -> ZoneInfo:
    tz_name = os.environ.get("TZ") or "UTC"
    try:
        return ZoneInfo(tz_name)
    except ZoneInfoNotFoundError as exc:
        raise ValueError(f"invalid TZ environment value: {tz_name!r}") from exc


def _trigger_from_schedule(sched: Schedule) -> IntervalTrigger | CronTrigger:
    if isinstance(sched, IntervalSchedule):
        return IntervalTrigger(seconds=sched.seconds, start_time=datetime.now(UTC))

    if isinstance(sched, CronSchedule):
        parts = sched.expression.split()
        timezone = _timezone_from_env()
        return CronTrigger(
            minute=parts[0],
            hour=parts[1],
            day=parts[2],
            month=parts[3],
            day_of_week=parts[4],
            timezone=timezone,
            start_time=datetime.now(timezone),
        )

    raise ValueError(f"unexpected schedule type: {sched!r}")


async def _add_feed_job(
    scheduler: AsyncScheduler, runner: Runner, feed: FeedConfig
) -> None:
    sched = parse_schedule(feed.schedule)
    trigger = _trigger_from_schedule(sched)

    await scheduler.add_schedule(
        _run_feed_job,
        trigger=trigger,
        id=f"feed:{feed.name}",
        args=(runner, feed.name),
        misfire_grace_time=300,
        max_jitter=10,
    )
    logger.info("scheduled", feed=feed.name, schedule=feed.schedule)


async def _run_feed_job(runner: Runner, name: str) -> None:
    try:
        await runner.run_feed(name)
    except Exception:
        logger.exception("scheduled_run_unhandled", feed=name)
