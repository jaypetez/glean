from __future__ import annotations

import textwrap
from pathlib import Path
from types import SimpleNamespace
from typing import Any, ClassVar

from glean.config import load_config
from glean.llm.registry import register_provider
from glean.pipeline import stages
from glean.pipeline.engine import Runner, RunResult
from glean.sources.base import FetchContext, Item
from glean.sources.registry import register_source
from glean.state.store import StateStore


@register_source("budget_fake")
class BudgetFakeSource:
    type: ClassVar[str] = "budget_fake"

    def __init__(self, count: int = 1) -> None:
        self.count = count

    async def fetch(self, ctx: FetchContext) -> list[Item]:
        return [
            Item(
                canonical_url=f"https://example.com/{index}",
                title=f"Item {index}",
                body=f"Body {index}",
                source_type="budget_fake",
                source_name="budget_fake",
            )
            for index in range(self.count)
        ]


@register_provider("budget_fake")
class BudgetFakeLLM:
    name: ClassVar[str] = "budget_fake"
    calls: ClassVar[list[str]] = []

    def __init__(self, **_: object) -> None:
        self.model = "budget_fake"

    @classmethod
    def reset(cls) -> None:
        cls.calls = []

    async def rank(self, item: Item, prompt: str) -> float:
        self.calls.append(f"rank:{item.title}")
        return 1.0

    async def summarize(self, item: Item, prompt: str) -> str:
        self.calls.append(f"summarize:{item.title}")
        return f"summary of {item.title}"

    async def digest(self, items: list[Item], prompt: str) -> str:
        self.calls.append("digest")
        return "generated intro"

    async def aclose(self) -> None:
        pass


async def _run_budget_feed(
    tmp_path: Path,
    write_yaml: Any,
    monkeypatch: Any,
    *,
    item_count: int,
    max_llm_calls_per_run: int | None,
    default_max_llm_calls_per_run: int | None = None,
    pipeline: str | None = None,
) -> tuple[RunResult, list[tuple[str, dict[str, object]]], list[str]]:
    BudgetFakeLLM.reset()
    warnings: list[tuple[str, dict[str, object]]] = []
    monkeypatch.setattr(
        stages,
        "logger",
        SimpleNamespace(
            debug=lambda *_args, **_kwargs: None,
            warning=lambda event, **kwargs: warnings.append((event, kwargs)),
        ),
    )
    default_cap_line = (
        ""
        if default_max_llm_calls_per_run is None
        else f"          max_llm_calls_per_run: {default_max_llm_calls_per_run}\n"
    )
    cap_line = (
        ""
        if max_llm_calls_per_run is None
        else f"            max_llm_calls_per_run: {max_llm_calls_per_run}\n"
    )
    pipeline_steps = (
        pipeline
        or """
    - dedup
    - summarize:
        prompt: "summarize"
    - digest:
        prompt: "write intro"
    """
    )
    pipeline_yaml = textwrap.indent(textwrap.dedent(pipeline_steps).strip(), "              ")
    yaml = textwrap.dedent(
        f"""
        defaults:
          llm: {{provider: budget_fake, model: budget_fake}}
{default_cap_line}        feeds:
          - name: budgeted
            schedule: "every 1h"
            chat_id: -1
{cap_line}            sources:
              - type: budget_fake
                count: {item_count}
            render:
              max_items: 50
            pipeline:
{pipeline_yaml}
        """
    )
    cfg = load_config(write_yaml(yaml))
    state = StateStore(tmp_path / "budget.db")
    await state.open()
    await state.set_bootstrapped("budgeted")
    runner = Runner(cfg, state)
    try:
        result = await runner.run_feed("budgeted", dry_run=True)
    finally:
        await runner.aclose()
        await state.close()
    return result, warnings, list(BudgetFakeLLM.calls)


async def test_feed_llm_budget_caps_calls_and_leaves_items_in_digest(
    tmp_path: Path,
    write_yaml: Any,
    monkeypatch: Any,
) -> None:
    result, warnings, calls = await _run_budget_feed(
        tmp_path,
        write_yaml,
        monkeypatch,
        item_count=100,
        max_llm_calls_per_run=10,
    )

    assert result.error is None
    assert len(calls) == 10
    assert calls == [f"summarize:Item {index}" for index in range(10)]
    assert result.after_dedup == 100
    assert result.overflow == 50
    assert any("Item 49" in message for message in result.messages)
    assert not any("summary of Item 10" in message for message in result.messages)
    assert warnings == [("llm_budget_capped", {"feed": "budgeted", "calls": 10, "max": 10})]


async def test_feed_without_llm_budget_allows_all_calls(
    tmp_path: Path,
    write_yaml: Any,
    monkeypatch: Any,
) -> None:
    result, warnings, calls = await _run_budget_feed(
        tmp_path,
        write_yaml,
        monkeypatch,
        item_count=12,
        max_llm_calls_per_run=None,
    )

    assert result.error is None
    assert len(calls) == 13
    assert calls == [f"summarize:Item {index}" for index in range(12)] + ["digest"]
    assert warnings == []


async def test_feed_llm_budget_of_one_allows_one_call(
    tmp_path: Path,
    write_yaml: Any,
    monkeypatch: Any,
) -> None:
    result, warnings, calls = await _run_budget_feed(
        tmp_path,
        write_yaml,
        monkeypatch,
        item_count=3,
        max_llm_calls_per_run=1,
    )

    assert result.error is None
    assert calls == ["summarize:Item 0"]
    assert any("Item 1" in message for message in result.messages)
    assert not any("summary of Item 1" in message for message in result.messages)
    assert warnings == [("llm_budget_capped", {"feed": "budgeted", "calls": 1, "max": 1})]


async def test_default_llm_budget_applies_to_feed(
    tmp_path: Path,
    write_yaml: Any,
    monkeypatch: Any,
) -> None:
    result, warnings, calls = await _run_budget_feed(
        tmp_path,
        write_yaml,
        monkeypatch,
        item_count=5,
        max_llm_calls_per_run=None,
        default_max_llm_calls_per_run=2,
    )

    assert result.error is None
    assert calls == ["summarize:Item 0", "summarize:Item 1"]
    assert warnings == [("llm_budget_capped", {"feed": "budgeted", "calls": 2, "max": 2})]


async def test_llm_budget_is_shared_across_rank_and_summarize(
    tmp_path: Path,
    write_yaml: Any,
    monkeypatch: Any,
) -> None:
    result, warnings, calls = await _run_budget_feed(
        tmp_path,
        write_yaml,
        monkeypatch,
        item_count=5,
        max_llm_calls_per_run=3,
        pipeline="""
        - dedup
        - rank:
            prompt: "rank"
            min_relevance: 0.5
        - summarize:
            prompt: "summarize"
        """,
    )

    assert result.error is None
    assert calls == ["rank:Item 0", "rank:Item 1", "rank:Item 2"]
    assert any("Item 4" in message for message in result.messages)
    assert not any("summary of Item" in message for message in result.messages)
    assert warnings == [("llm_budget_capped", {"feed": "budgeted", "calls": 3, "max": 3})]
