from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

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

    async def aclose(self) -> None: ...


class FakeTelegram:
    def __init__(self) -> None:
        self.sent: list[tuple[int | str, list[str]]] = []
        self.texts: list[tuple[int | str, str]] = []

    async def send_digest(self, chat_id, messages, *, style="html", link_preview=False):
        self.sent.append((chat_id, list(messages)))

    async def send_text(self, chat_id, text, *, style="html"):
        self.texts.append((chat_id, text))

    async def aclose(self): ...


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
