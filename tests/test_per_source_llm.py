"""Tests for per-source LLM model dispatch."""

from __future__ import annotations

import textwrap
from pathlib import Path
from typing import ClassVar

import pytest

from glean.config import load_config
from glean.config.loader import ConfigError
from glean.config.schema import LLMConfig
from glean.llm.base import LLMProvider
from glean.llm.registry import register_provider
from glean.pipeline.engine import Runner, _llm_key
from glean.pipeline.stages import rank_stage, summarize_stage
from glean.sources.base import FetchContext, Item
from glean.sources.registry import build_source, register_source
from glean.state.store import StateStore


@register_source("ttagged")
class _TaggedSource:
    """Test source that emits tagged items."""

    type: ClassVar[str] = "ttagged"

    def __init__(self, urls: list[str] | None = None) -> None:
        self.urls = urls or ["https://x/a", "https://x/b"]

    async def fetch(self, ctx: FetchContext) -> list[Item]:
        return [
            Item(canonical_url=url, title=url, source_type="ttagged", source_name="t")
            for url in self.urls
        ]


class TrackerCalls:
    """Module-level test recorder for tracking which provider got which call."""

    log: ClassVar[dict[str, list[str]]] = {"a": [], "b": []}

    @classmethod
    def reset(cls) -> None:
        cls.log = {"a": [], "b": []}

    @classmethod
    def add(cls, provider: str, msg: str) -> None:
        cls.log[provider].append(msg)


@register_source("tstrict")
class _StrictSource:
    """Source constructor that rejects unexpected kwargs."""

    type: ClassVar[str] = "tstrict"

    def __init__(self, url: str) -> None:
        self.url = url

    async def fetch(self, ctx: FetchContext) -> list[Item]:
        return [Item(canonical_url=self.url, title=self.url)]


@register_provider("tracker_a")
class _TrackerA:
    name: ClassVar[str] = "tracker_a"

    def __init__(self, **_: object) -> None:
        self.model = "tracker_a"
        TrackerCalls.add("a", "init")

    async def rank(self, item: Item, prompt: str) -> float:
        TrackerCalls.add("a", "rank:" + item.canonical_url)
        return 0.9

    async def summarize(self, item: Item, prompt: str) -> str:
        TrackerCalls.add("a", "summarize:" + item.canonical_url)
        return "sa"

    async def digest(self, items: list[Item], prompt: str) -> str:
        return "d"

    async def aclose(self) -> None:
        pass


@register_provider("tracker_b")
class _TrackerB:
    name: ClassVar[str] = "tracker_b"

    def __init__(self, **_: object) -> None:
        self.model = "tracker_b"
        TrackerCalls.add("b", "init")

    async def rank(self, item: Item, prompt: str) -> float:
        TrackerCalls.add("b", "rank:" + item.canonical_url)
        return 0.8

    async def summarize(self, item: Item, prompt: str) -> str:
        TrackerCalls.add("b", "summarize:" + item.canonical_url)
        return "sb"

    async def digest(self, items: list[Item], prompt: str) -> str:
        return "d"

    async def aclose(self) -> None:
        pass


@pytest.fixture(autouse=True)
def _reset_tracker() -> None:
    TrackerCalls.reset()


def test_source_llm_config_parses(write_yaml) -> None:
    yaml = textwrap.dedent(
        """
        defaults:
          llm: {provider: tracker_a, model: tracker_a}
        feeds:
          - name: f
            schedule: "every 1h"
            chat_id: -1
            sources:
              - type: ttagged
                llm:
                  provider: tracker_b
                  model: tracker_b
            pipeline:
              - dedup
        """
    )
    cfg = load_config(write_yaml(yaml))
    spec = cfg.feeds[0].sources[0]
    llm_cfg = LLMConfig.model_validate(spec["llm"])
    assert llm_cfg.provider == "tracker_b"


def test_build_source_strips_llm_from_constructor_kwargs() -> None:
    source = build_source(
        {
            "type": "tstrict",
            "url": "https://strict/1",
            "llm": {"provider": "tracker_b", "model": "tracker_b"},
        }
    )

    assert isinstance(source, _StrictSource)
    assert source.url == "https://strict/1"


def test_source_llm_config_invalid_rejected_at_load(write_yaml) -> None:
    yaml = textwrap.dedent(
        """
        defaults:
          llm: {provider: tracker_a, model: tracker_a}
        feeds:
          - name: f
            schedule: "every 1h"
            chat_id: -1
            sources:
              - type: ttagged
                llm:
                  not_a_real_field: oops
            pipeline:
              - dedup
        """
    )
    with pytest.raises(ConfigError, match=r"sources\[0\]\.llm"):
        load_config(write_yaml(yaml))


async def test_fetch_all_tags_items_with_llm_key(tmp_path: Path, write_yaml) -> None:
    yaml = textwrap.dedent(
        """
        defaults:
          llm: {provider: tracker_a, model: tracker_a}
        feeds:
          - name: f
            schedule: "every 1h"
            chat_id: -1
            sources:
              - type: ttagged
                llm:
                  provider: tracker_b
                  model: tracker_b
            pipeline: [dedup]
        """
    )
    cfg = load_config(write_yaml(yaml))
    state = StateStore(tmp_path / "s.db")
    await state.open()
    runner = Runner(cfg, state)
    try:
        items = await runner._fetch_all(cfg.feed("f"))
    finally:
        await runner.aclose()
        await state.close()
    expected_key = _llm_key(LLMConfig(provider="tracker_b", model="tracker_b"))
    assert len(items) == 2
    assert all(i.llm_key == expected_key for i in items), f"got {[i.llm_key for i in items]}"


async def test_rank_stage_dispatches_per_item() -> None:
    """Items with different llm_key go to different providers."""
    key_a = "tracker_a:tracker_a:"
    key_b = "tracker_b:tracker_b:"
    item_a = Item(canonical_url="https://a", title="A", llm_key=key_a)
    item_b = Item(canonical_url="https://b", title="B", llm_key=key_b)

    llm_a: LLMProvider = _TrackerA()
    llm_b: LLMProvider = _TrackerB()
    cache = {key_a: llm_a, key_b: llm_b}

    def resolver(item: Item) -> LLMProvider:
        return cache.get(item.llm_key or "", llm_a)

    TrackerCalls.reset()
    await rank_stage("feed", [item_a, item_b], resolver, prompt="r", min_relevance=0.0)
    assert "rank:https://a" in TrackerCalls.log["a"]
    assert "rank:https://b" in TrackerCalls.log["b"]
    assert "rank:https://a" not in TrackerCalls.log["b"]
    assert "rank:https://b" not in TrackerCalls.log["a"]


async def test_summarize_stage_dispatches_per_item() -> None:
    key_a = "tracker_a:tracker_a:"
    key_b = "tracker_b:tracker_b:"
    items = [
        Item(canonical_url="https://a", title="A", llm_key=key_a),
        Item(canonical_url="https://b", title="B", llm_key=key_b),
    ]
    llm_a: LLMProvider = _TrackerA()
    llm_b: LLMProvider = _TrackerB()
    cache = {key_a: llm_a, key_b: llm_b}

    def resolver(item: Item) -> LLMProvider:
        return cache.get(item.llm_key or "", llm_a)

    TrackerCalls.reset()
    out = await summarize_stage("feed", items, resolver, prompt="s")
    summaries = {item.canonical_url: item.llm_summary for item in out}
    assert summaries["https://a"] == "sa"
    assert summaries["https://b"] == "sb"


async def test_untagged_items_use_default_llm() -> None:
    """Items without llm_key fall back to feed default."""
    default = _TrackerA()
    item = Item(canonical_url="https://x", title="X")

    TrackerCalls.reset()
    await summarize_stage("feed", [item], lambda _: default, prompt="s")
    assert "summarize:https://x" in TrackerCalls.log["a"]


async def test_two_sources_same_llm_share_one_instance(tmp_path: Path, write_yaml) -> None:
    """Two sources with identical LLM config should share the cached provider."""
    yaml = textwrap.dedent(
        """
        defaults:
          llm: {provider: tracker_a, model: default}
        feeds:
          - name: f
            schedule: "every 1h"
            chat_id: -1
            sources:
              - type: ttagged
                llm: {provider: tracker_b, model: shared}
              - type: ttagged
                llm: {provider: tracker_b, model: shared}
            pipeline: [dedup]
        """
    )
    cfg = load_config(write_yaml(yaml))
    state = StateStore(tmp_path / "s.db")
    await state.open()
    runner = Runner(cfg, state)
    try:
        await runner._fetch_all(cfg.feed("f"))
        keys = list(runner._llm_cache.keys())
        assert any("tracker_b" in key and "shared" in key for key in keys)
        assert len(keys) == 1
    finally:
        await runner.aclose()
        await state.close()
