from __future__ import annotations

import asyncio
import textwrap
from pathlib import Path

import pytest

from glean.api.events import EventBus
from glean.config import load_config
from glean.llm.registry import register_provider
from glean.pipeline.engine import Runner
from glean.sources.base import FetchContext, Item
from glean.sources.registry import register_source
from glean.state.store import StateStore

pytestmark = pytest.mark.asyncio


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

    async def digest(self, items, prompt: str) -> str:
        return prompt

    async def aclose(self) -> None:
        pass


class FakeTelegram:
    def __init__(self) -> None:
        self.sent: list[tuple[int | str, list[str]]] = []
        self.texts: list[tuple[int | str, str]] = []

    async def send_digest(
        self,
        chat_id: int | str,
        messages: list[str],
        *,
        style: str = "html",
        link_preview: bool = False,
    ) -> None:
        self.sent.append((chat_id, list(messages)))

    async def send_text(
        self,
        chat_id: int | str,
        text: str,
        *,
        style: str = "html",
    ) -> None:
        self.texts.append((chat_id, text))

    async def aclose(self) -> None:
        pass


class FailingDigestTelegram(FakeTelegram):
    async def send_digest(
        self,
        chat_id: int | str,
        messages: list[str],
        *,
        style: str = "html",
        link_preview: bool = False,
    ) -> None:
        raise RuntimeError("sink <b>failed</b> & leaked sk-abc12345")


def _cfg_yaml() -> str:
    return textwrap.dedent(
        """
        defaults:
          llm:
            provider: fake
            model: fake
        feeds:
          - name: t1
            schedule: "every 1h"
            chat_id: -1
            sources:
              - type: fake
                items:
                  - {url: "https://a", title: "A"}
                  - {url: "https://b", title: "B"}
            pipeline:
              - dedup
              - rank:
                  prompt: "rank"
                  min_relevance: 0.5
              - summarize:
                  prompt: "summarize"
              - digest:
                  intro: "intro"
        """
    )


async def test_bootstrap_skips_send(tmp_path: Path, write_yaml) -> None:
    cfg = load_config(write_yaml(_cfg_yaml()))
    state = StateStore(tmp_path / "s.db")
    await state.open()
    fake_tg = FakeTelegram()
    runner = Runner(cfg, state, telegram=fake_tg)  # type: ignore[arg-type]
    try:
        result = await runner.run_feed("t1")
        assert result.skipped_reason == "bootstrap"
        assert result.sent == 0
        assert fake_tg.sent == []
        # second run: still nothing new because everything was marked seen
        result2 = await runner.run_feed("t1")
        assert result2.after_dedup == 0
        assert fake_tg.sent == []
    finally:
        await runner.aclose()
        await state.close()


async def test_full_pipeline_sends_after_new_item(
    tmp_path: Path, write_yaml
) -> None:
    cfg = load_config(write_yaml(_cfg_yaml()))
    state = StateStore(tmp_path / "s.db")
    await state.open()
    # Pre-bootstrap so the first call sends.
    await state.set_bootstrapped("t1")
    fake_tg = FakeTelegram()
    runner = Runner(cfg, state, telegram=fake_tg)  # type: ignore[arg-type]
    try:
        result = await runner.run_feed("t1")
        assert result.sent == 2
        assert len(fake_tg.sent) == 1
        chat_id, msgs = fake_tg.sent[0]
        assert chat_id == -1
        assert any("summary of A" in m for m in msgs)
        assert any("summary of B" in m for m in msgs)
    finally:
        await runner.aclose()
        await state.close()


async def test_dry_run_no_writes(tmp_path: Path, write_yaml) -> None:
    cfg = load_config(write_yaml(_cfg_yaml()))
    state = StateStore(tmp_path / "s.db")
    await state.open()
    await state.set_bootstrapped("t1")
    fake_tg = FakeTelegram()
    runner = Runner(cfg, state, telegram=fake_tg)  # type: ignore[arg-type]
    try:
        result = await runner.run_feed("t1", dry_run=True)
        assert result.messages, "dry-run should produce rendered messages"
        assert fake_tg.sent == []
        # Nothing was marked seen, so a second non-dry-run still sees both items.
        result2 = await runner.run_feed("t1")
        assert result2.sent == 2
    finally:
        await runner.aclose()
        await state.close()


async def test_per_source_llm_dispatched_in_full_pipeline(
    tmp_path: Path, write_yaml, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Items from source A use llm A; items from source B use llm B during summarize."""
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "fake")

    calls: dict[str, list[str]] = {"cheap": [], "expensive": []}

    @register_provider("track_cheap")
    class TrackCheap:
        name = "track_cheap"

        def __init__(self, **_: object) -> None:
            self.model = "cheap"

        async def rank(self, item: Item, prompt: str) -> float:
            return 0.9

        async def summarize(self, item: Item, prompt: str) -> str:
            calls["cheap"].append(item.canonical_url)
            return f"cheap:{item.title}"

        async def digest(self, items: list[Item], prompt: str) -> str:
            return ""

        async def aclose(self) -> None:
            pass

    @register_provider("track_expensive")
    class TrackExpensive:
        name = "track_expensive"

        def __init__(self, **_: object) -> None:
            self.model = "expensive"

        async def rank(self, item: Item, prompt: str) -> float:
            return 0.9

        async def summarize(self, item: Item, prompt: str) -> str:
            calls["expensive"].append(item.canonical_url)
            return f"expensive:{item.title}"

        async def digest(self, items: list[Item], prompt: str) -> str:
            return ""

        async def aclose(self) -> None:
            pass

    cfg_yaml = textwrap.dedent(
        """
        defaults:
          llm: {provider: track_cheap, model: cheap}
        feeds:
          - name: t1
            schedule: "every 1h"
            chat_id: -1
            sources:
              - type: fake
                items:
                  - {url: "https://cheap/1", title: "C1"}
                llm: {provider: track_cheap, model: cheap}
              - type: fake
                items:
                  - {url: "https://exp/1", title: "E1"}
                llm: {provider: track_expensive, model: expensive}
            pipeline:
              - dedup
              - summarize:
                  prompt: "sum"
              - digest:
                  intro: "intro"
        """
    )
    cfg = load_config(write_yaml(cfg_yaml))
    state = StateStore(tmp_path / "s.db")
    await state.open()
    await state.set_bootstrapped("t1")
    fake_tg = FakeTelegram()
    runner = Runner(cfg, state, telegram=fake_tg)  # type: ignore[arg-type]
    try:
        result = await runner.run_feed("t1")
    finally:
        await runner.aclose()
        await state.close()

    assert result.error is None
    assert "https://cheap/1" in calls["cheap"]
    assert "https://exp/1" in calls["expensive"]
    assert "https://cheap/1" not in calls["expensive"]
    assert "https://exp/1" not in calls["cheap"]


async def test_run_feed_emits_start_and_completion_events(tmp_path: Path, write_yaml) -> None:
    cfg = load_config(write_yaml(_cfg_yaml()))
    state = StateStore(tmp_path / "s.db")
    await state.open()
    await state.set_bootstrapped("t1")
    fake_tg = FakeTelegram()
    bus = EventBus()
    q = await bus.subscribe()
    runner = Runner(cfg, state, telegram=fake_tg, event_bus=bus)  # type: ignore[arg-type]
    try:
        result = await runner.run_feed("t1")
        started = await asyncio.wait_for(q.get(), timeout=1.0)
        completed = await asyncio.wait_for(q.get(), timeout=1.0)
    finally:
        await bus.unsubscribe(q)
        await runner.aclose()
        await state.close()

    assert result.error is None
    assert started.type == "run_started"
    assert started.feed == "t1"
    assert completed.type == "run_completed"
    assert completed.feed == "t1"
    assert completed.fetched == result.fetched
    assert completed.after_dedup == result.after_dedup
    assert completed.sent == result.sent
    assert completed.duration_ms == result.duration_ms


async def test_run_feed_emits_failure_event(tmp_path: Path, write_yaml) -> None:
    cfg = load_config(write_yaml(_cfg_yaml()))
    state = StateStore(tmp_path / "s.db")
    await state.open()
    await state.set_bootstrapped("t1")
    bus = EventBus()
    q = await bus.subscribe()
    runner = Runner(cfg, state, event_bus=bus)
    try:
        result = await runner.run_feed("t1")
        started = await asyncio.wait_for(q.get(), timeout=1.0)
        failed = await asyncio.wait_for(q.get(), timeout=1.0)
    finally:
        await bus.unsubscribe(q)
        await runner.aclose()
        await state.close()

    assert result.error is not None
    assert started.type == "run_started"
    assert failed.type == "run_failed"
    assert failed.feed == "t1"
    assert failed.error == result.error
    assert failed.duration_ms == result.duration_ms


async def test_ops_alert_redacts_api_key_from_failure(
    tmp_path: Path, write_yaml
) -> None:
    cfg_yaml = textwrap.dedent(
        """
        defaults:
          llm:
            provider: fake
            model: fake
          failure:
            ops_chat_id: ops
            alert_after: 1
        feeds:
          - name: t1
            schedule: "every 1h"
            chat_id: -1
            sources:
              - type: fake
                items:
                  - {url: "https://secret", title: "Secret"}
            pipeline:
              - dedup
              - digest:
                  intro: "intro"
        """
    )
    cfg = load_config(write_yaml(cfg_yaml))
    state = StateStore(tmp_path / "s.db")
    await state.open()
    await state.set_bootstrapped("t1")
    fake_tg = FailingDigestTelegram()
    runner = Runner(cfg, state, telegram=fake_tg)  # type: ignore[arg-type]
    try:
        result = await runner.run_feed("t1")
    finally:
        await runner.aclose()
        await state.close()

    assert result.error is not None
    assert "sk-[REDACTED]" in result.error
    assert "sk-abc12345" not in result.error
    assert "sink <b>failed</b> & leaked sk-[REDACTED]" in result.error

    assert fake_tg.texts == [
        (
            "ops",
            "🚨 <b>t1</b> failing: RuntimeError: required sinks failed: telegram: "
            "RuntimeError: sink &lt;b&gt;failed&lt;/b&gt; &amp; leaked sk-[REDACTED]",
        )
    ]
    assert "<b>failed</b>" not in fake_tg.texts[0][1]
    assert "sk-abc12345" not in fake_tg.texts[0][1]
