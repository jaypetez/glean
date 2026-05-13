from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

import glean.scheduler as scheduler_module
from glean.config.schema import Config

pytestmark = pytest.mark.asyncio


class FakeScheduler:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    async def add_schedule(self, func, **kwargs) -> None:  # type: ignore[no-untyped-def]
        self.calls.append({"func": func, **kwargs})


def _make_config() -> Config:
    return Config.model_validate(
        {
            "defaults": {"llm": {"provider": "ollama", "model": "qwen2.5:7b"}},
            "feeds": [
                {
                    "name": "interval-feed",
                    "schedule": "every 15m",
                    "chat_id": -1,
                    "sources": [{"type": "rss", "url": "https://example.com/interval"}],
                    "pipeline": ["dedup"],
                },
                {
                    "name": "cron-feed",
                    "schedule": "daily 09:30",
                    "chat_id": -2,
                    "sources": [{"type": "rss", "url": "https://example.com/cron"}],
                    "pipeline": ["dedup"],
                },
            ],
        }
    )


async def test_schedule_feeds_adds_interval_and_cron_jobs(monkeypatch) -> None:
    scheduler = FakeScheduler()
    runner = SimpleNamespace(config=_make_config())
    logs: list[tuple[str, dict[str, object]]] = []
    monkeypatch.setattr(
        scheduler_module,
        "logger",
        SimpleNamespace(info=lambda event, **kwargs: logs.append((event, kwargs))),
    )

    await scheduler_module.schedule_feeds(scheduler, runner)

    assert len(scheduler.calls) == 2
    assert isinstance(scheduler.calls[0]["trigger"], IntervalTrigger)
    assert scheduler.calls[0]["id"] == "feed:interval-feed"
    assert scheduler.calls[0]["args"] == (runner, "interval-feed")
    assert isinstance(scheduler.calls[1]["trigger"], CronTrigger)
    assert scheduler.calls[1]["id"] == "feed:cron-feed"
    assert scheduler.calls[1]["args"] == (runner, "cron-feed")
    assert logs == [
        ("scheduled", {"feed": "interval-feed", "schedule": "every 15m"}),
        ("scheduled", {"feed": "cron-feed", "schedule": "daily 09:30"}),
    ]


async def test_add_feed_job_rejects_unexpected_schedule_type(monkeypatch) -> None:
    scheduler = FakeScheduler()
    runner = SimpleNamespace(config=_make_config())
    feed = runner.config.feeds[0]

    monkeypatch.setattr(scheduler_module, "parse_schedule", lambda _raw: object())

    with pytest.raises(ValueError, match="unexpected schedule type"):
        await scheduler_module._add_feed_job(scheduler, runner, feed)


async def test_run_feed_job_logs_unhandled_errors(monkeypatch) -> None:
    runner = SimpleNamespace(run_feed=AsyncMock(side_effect=RuntimeError("boom")))
    logged: list[tuple[str, dict[str, object]]] = []
    monkeypatch.setattr(
        scheduler_module,
        "logger",
        SimpleNamespace(exception=lambda event, **kwargs: logged.append((event, kwargs))),
    )

    await scheduler_module._run_feed_job(runner, "interval-feed")

    runner.run_feed.assert_awaited_once_with("interval-feed")
    assert logged == [("scheduled_run_unhandled", {"feed": "interval-feed"})]
