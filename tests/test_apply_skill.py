"""Tests for the apply_skill pipeline stage."""

from __future__ import annotations

import textwrap
from pathlib import Path
from typing import Any, ClassVar

import pytest

from glean.config import load_config
from glean.config.skills import SkillConfig
from glean.llm.registry import register_provider
from glean.pipeline.engine import Runner
from glean.pipeline.stages import apply_skill_stage
from glean.sources.base import FetchContext, Item
from glean.sources.registry import register_source
from glean.state.store import StateStore

pytestmark = pytest.mark.asyncio


# Tracking provider for apply_skill tests
class _TrackingProvider:
    name: ClassVar[str] = "tracking"
    model: ClassVar[str] = "tracking"

    def __init__(
        self,
        *,
        response: dict[str, Any] | None = None,
        raise_on_extract: bool = False,
        **_: object,
    ) -> None:
        self._response = response if response is not None else {"summary": "ok", "score": 0.5}
        self._raise = raise_on_extract
        self.extract_calls: list[str] = []

    async def rank(self, item: Item, prompt: str) -> float:
        return 0.9

    async def summarize(self, item: Item, prompt: str) -> str:
        return "s"

    async def digest(self, items: list[Item], prompt: str) -> str:
        return "d"

    async def aclose(self) -> None:
        pass

    async def extract(
        self,
        item: Item,
        prompt: str,
        output_schema: dict[str, Any],
        *,
        system_prompt: str | None = None,
    ) -> dict[str, Any]:
        self.extract_calls.append(item.canonical_url)
        if self._raise:
            raise RuntimeError("simulated failure")
        return dict(self._response)


def _basic_skill(**overrides: Any) -> SkillConfig:
    base: dict[str, Any] = {
        "name": "test-skill",
        "prompt": "Extract from: {title}",
        "output_schema": {"summary": "str", "score": "float"},
    }
    base.update(overrides)
    return SkillConfig(**base)


def _items(*urls: str) -> list[Item]:
    return [Item(canonical_url=u, title=f"T-{u}") for u in urls]


async def test_apply_skill_attaches_structured_data() -> None:
    skill = _basic_skill()
    provider = _TrackingProvider(response={"summary": "extracted", "score": 0.8})
    items = _items("https://a", "https://b")

    out = await apply_skill_stage("feed", items, lambda _: provider, skill=skill)

    assert len(out) == 2
    assert all(item.structured == {"summary": "extracted", "score": 0.8} for item in out)
    # llm_summary auto-populated from "summary" field
    assert all(item.llm_summary == "extracted" for item in out)


async def test_apply_skill_uses_one_liner_field() -> None:
    skill = _basic_skill()
    provider = _TrackingProvider(response={"one_liner": "short version"})
    items = _items("https://x")

    out = await apply_skill_stage("feed", items, lambda _: provider, skill=skill)

    assert out[0].llm_summary == "short version"


async def test_apply_skill_failure_returns_empty_structured() -> None:
    skill = _basic_skill()
    provider = _TrackingProvider(raise_on_extract=True)
    items = _items("https://x")

    out = await apply_skill_stage("feed", items, lambda _: provider, skill=skill)

    assert out[0].structured == {}
    assert out[0].llm_summary is None


async def test_apply_skill_skips_when_provider_lacks_extract() -> None:
    """Defensive: providers without extract() shouldn't crash the pipeline."""
    skill = _basic_skill()

    class NoExtractProvider:
        name = model = "no-extract"

        async def rank(self, item: Item, prompt: str) -> float:
            return 0.9

        async def summarize(self, item: Item, prompt: str) -> str:
            return ""

        async def digest(self, items: list[Item], prompt: str) -> str:
            return ""

        async def aclose(self) -> None:
            pass

    items = _items("https://x")
    out = await apply_skill_stage("feed", items, lambda _: NoExtractProvider(), skill=skill)

    # Items pass through unchanged
    assert out[0].structured == {}
    assert out[0].llm_summary is None


async def test_apply_skill_explicit_skill_llm_overrides_resolver() -> None:
    skill = _basic_skill()
    source_provider = _TrackingProvider(response={"summary": "from source"})
    skill_provider = _TrackingProvider(response={"summary": "from skill"})

    items = _items("https://x")
    out = await apply_skill_stage(
        "feed",
        items,
        lambda _: source_provider,
        skill=skill,
        skill_llm=skill_provider,
    )

    assert out[0].llm_summary == "from skill"
    assert source_provider.extract_calls == []
    assert skill_provider.extract_calls == ["https://x"]


async def test_apply_skill_empty_items_returns_empty() -> None:
    skill = _basic_skill()
    provider = _TrackingProvider()

    out = await apply_skill_stage("feed", [], lambda _: provider, skill=skill)

    assert out == []


async def test_apply_skill_template_renders_with_item_fields() -> None:
    skill = SkillConfig(
        name="render-test",
        prompt="title={title} url={url} body={body}",
        output_schema={"summary": "str"},
    )

    captured_prompts: list[str] = []

    class CapturingProvider(_TrackingProvider):
        async def extract(
            self,
            item: Item,
            prompt: str,
            output_schema: dict[str, Any],
            *,
            system_prompt: str | None = None,
        ) -> dict[str, Any]:
            captured_prompts.append(prompt)
            return {"summary": "x"}

    items = [Item(canonical_url="https://x", title="Hello", body="World")]

    await apply_skill_stage("feed", items, lambda _: CapturingProvider(), skill=skill)

    assert "title=Hello" in captured_prompts[0]
    assert "url=https://x" in captured_prompts[0]
    assert "body=World" in captured_prompts[0]


# === Integration: apply_skill end-to-end via Runner ===


@register_source("apply_skill_test_source")
class _ApplySkillTestSource:
    type: ClassVar[str] = "apply_skill_test_source"

    def __init__(self, urls: list[str] | None = None) -> None:
        self.urls = urls or ["https://x/1"]

    async def fetch(self, ctx: FetchContext) -> list[Item]:
        return [
            Item(
                canonical_url=u,
                title=u,
                source_type="apply_skill_test_source",
                source_name="t",
            )
            for u in self.urls
        ]


@register_provider("apply_skill_test_llm")
class _ApplySkillTestLLM:
    name: ClassVar[str] = "apply_skill_test_llm"

    def __init__(self, **_: object) -> None:
        self.model = "test"

    async def rank(self, item: Item, prompt: str) -> float:
        return 0.9

    async def summarize(self, item: Item, prompt: str) -> str:
        return "fallback"

    async def digest(self, items: list[Item], prompt: str) -> str:
        return ""

    async def extract(
        self,
        item: Item,
        prompt: str,
        output_schema: dict[str, Any],
        *,
        system_prompt: str | None = None,
    ) -> dict[str, Any]:
        return {"summary": f"structured:{item.title}", "score": 0.7}

    async def aclose(self) -> None:
        pass


async def test_apply_skill_full_pipeline_via_runner(tmp_path: Path, write_yaml: Any) -> None:
    yaml = textwrap.dedent(
        """
        defaults:
          llm: {provider: apply_skill_test_llm, model: x}
        skills:
          - name: extract-test
            prompt: "Extract from {title}"
            output_schema:
              summary: str
              score: float
        feeds:
          - name: f
            schedule: "every 1h"
            chat_id: -1
            sources:
              - type: apply_skill_test_source
            pipeline:
              - dedup
              - apply_skill:
                  skill: extract-test
        """
    )
    cfg = load_config(write_yaml(yaml))
    state = StateStore(tmp_path / "s.db")
    await state.open()
    await state.set_bootstrapped("f")
    runner = Runner(cfg, state)
    try:
        # Verify the runner can resolve and dispatch the skill stage.
        result = await runner.run_feed("f", dry_run=True)
        assert result.error is None
        assert result.after_dedup == 1
        assert any("structured:https://x/1" in message for message in result.messages)
    finally:
        await runner.aclose()
        await state.close()
