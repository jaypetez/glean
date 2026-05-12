from __future__ import annotations

from typing import TYPE_CHECKING

from apscheduler import AsyncScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from glean.config.schedule import (
    CronSchedule,
    IntervalSchedule,
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


async def _add_feed_job(
    scheduler: AsyncScheduler, runner: Runner, feed: FeedConfig
) -> None:
    sched = parse_schedule(feed.schedule)
    trigger: IntervalTrigger | CronTrigger
    if isinstance(sched, IntervalSchedule):
        trigger = IntervalTrigger(seconds=sched.seconds)
    elif isinstance(sched, CronSchedule):
        parts = sched.expression.split()
        trigger = CronTrigger(
            minute=parts[0],
            hour=parts[1],
            day=parts[2],
            month=parts[3],
            day_of_week=parts[4],
        )
    else:
        raise ValueError(f"unexpected schedule type for feed {feed.name!r}")

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
