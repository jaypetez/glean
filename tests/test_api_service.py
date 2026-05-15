"""Tests for the shared api_service layer (used by both CLI and API)."""

from __future__ import annotations

import asyncio
import textwrap
from pathlib import Path

import pytest

from glean.api.events import EventBus
from glean.api_service import (
    ConfigSummary,
    FeedStatus,
    list_feeds_with_status,
    run_feed_once,
    validate_config_summary,
)
from glean.config import load_config
from glean.config.loader import ConfigError
from glean.llm.registry import register_provider
from glean.sources.base import FetchContext, Item
from glean.sources.registry import register_source
from glean.state.store import StateStore


@register_source("fake")
class FakeSource:
    type = "fake"

    def __init__(self, items: list[dict] | None = None) -> None:
        self.items = items or []

    async def fetch(self, ctx: FetchContext) -> list[Item]:
        return [
            Item(
                canonical_url=i.get("url", ""),
                title=i.get("title", ""),
                body=i.get("body", ""),
                source_type="fake",
                source_name="fake",
            )
            for i in self.items
        ]


@register_provider("fake")
class FakeLLM:
    name = "fake"

    def __init__(self, **_: object) -> None:
        self.model = "fake"

    async def rank(self, item: Item, prompt: str) -> float:
        return 0.9

    async def summarize(self, item: Item, prompt: str) -> str:
        return f"summary of {item.title}"

    async def digest(self, items, prompt: str):  # type: ignore[no-untyped-def]
        return prompt

    async def aclose(self) -> None:
        pass


class FakeTelegram:
    def __init__(self) -> None:
        self.close_count = 0

    async def aclose(self) -> None:
        self.close_count += 1


def _basic_cfg_yaml() -> str:
    return textwrap.dedent(
        """
        defaults:
          llm: {provider: fake, model: fake}
        feeds:
          - name: alpha
            schedule: "every 1h"
            chat_id: -1
            sources:
              - type: fake
            pipeline: [dedup]
          - name: beta
            schedule: "daily 09:00"
            chat_id: -2
            sources:
              - type: fake
              - type: fake
            pipeline: [dedup]
        """
    )


def test_validate_config_summary_returns_typed_dataclass(write_yaml) -> None:
    summary = validate_config_summary(write_yaml(_basic_cfg_yaml()))
    assert isinstance(summary, ConfigSummary)
    assert summary.feeds_count == 2
    assert summary.feeds[0].name == "alpha"
    assert summary.feeds[0].schedule == "every 1h"
    assert summary.feeds[0].sources_count == 1
    assert summary.feeds[1].sources_count == 2


def test_validate_config_summary_raises_on_invalid(tmp_path: Path) -> None:
    bad = tmp_path / "missing.yaml"
    with pytest.raises(ConfigError):
        validate_config_summary(bad)


async def test_list_feeds_with_status_no_runs(tmp_path: Path, write_yaml) -> None:
    cfg = load_config(write_yaml(_basic_cfg_yaml()))
    state = StateStore(tmp_path / "s.db")
    await state.open()
    try:
        statuses = await list_feeds_with_status(cfg, state)
    finally:
        await state.close()
    assert len(statuses) == 2
    for s in statuses:
        assert isinstance(s, FeedStatus)
        assert s.last_success_at is None
        assert s.consecutive_failures == 0
        assert s.alert_active is False
        assert s.bootstrapped is False


async def test_list_feeds_with_status_after_record_success(tmp_path: Path, write_yaml) -> None:
    cfg = load_config(write_yaml(_basic_cfg_yaml()))
    state = StateStore(tmp_path / "s.db")
    await state.open()
    try:
        await state.record_success("alpha")
        statuses = await list_feeds_with_status(cfg, state)
    finally:
        await state.close()
    by_name = {s.name: s for s in statuses}
    assert by_name["alpha"].last_success_at is not None
    assert by_name["alpha"].consecutive_failures == 0
    assert by_name["beta"].last_success_at is None


async def test_run_feed_once_dry_run(tmp_path: Path, write_yaml) -> None:
    """run_feed_once should call Runner.run_feed and return RunResult."""
    yaml = textwrap.dedent(
        """
        defaults:
          llm: {provider: fake, model: fake}
        feeds:
          - name: t1
            schedule: "every 1h"
            chat_id: -1
            sources:
              - type: fake
                items:
                  - {url: "https://a", title: "A"}
            pipeline:
              - dedup
              - summarize:
                  prompt: "x"
              - digest:
                  intro: "intro"
        """
    )
    cfg = load_config(write_yaml(yaml))
    state = StateStore(tmp_path / "s.db")
    await state.open()
    try:
        await state.set_bootstrapped("t1")
        result = await run_feed_once(cfg, state, "t1", dry_run=True)
    finally:
        await state.close()
    assert result.feed == "t1"
    assert result.error is None


async def test_run_feed_once_leaves_injected_telegram_lifecycle_to_caller(
    tmp_path: Path, write_yaml
) -> None:
    cfg = load_config(write_yaml(_basic_cfg_yaml()))
    state = StateStore(tmp_path / "s.db")
    telegram = FakeTelegram()
    await state.open()
    try:
        await run_feed_once(cfg, state, "alpha", dry_run=True, telegram=telegram)  # type: ignore[arg-type]
    finally:
        await state.close()
    assert telegram.close_count == 0


async def test_run_feed_once_publishes_to_event_bus(tmp_path: Path, write_yaml) -> None:
    cfg = load_config(write_yaml(_basic_cfg_yaml()))
    state = StateStore(tmp_path / "s.db")
    bus = EventBus()
    queue = await bus.subscribe()
    await state.open()
    try:
        await state.set_bootstrapped("alpha")
        result = await run_feed_once(cfg, state, "alpha", dry_run=True, event_bus=bus)
        started = await asyncio.wait_for(queue.get(), timeout=1.0)
        completed = await asyncio.wait_for(queue.get(), timeout=1.0)
    finally:
        await bus.unsubscribe(queue)
        await state.close()
    assert result.error is None
    assert started.type == "run_started"
    assert completed.type == "run_completed"
    assert completed.feed == "alpha"


async def test_run_feed_once_unknown_feed_raises(tmp_path: Path, write_yaml) -> None:
    cfg = load_config(write_yaml(_basic_cfg_yaml()))
    state = StateStore(tmp_path / "s.db")
    await state.open()
    try:
        with pytest.raises(KeyError):
            await run_feed_once(cfg, state, "nonexistent", dry_run=True)
    finally:
        await state.close()
