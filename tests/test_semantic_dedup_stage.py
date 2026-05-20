from __future__ import annotations

import textwrap
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any

import pytest

from glean.config import load_config
from glean.config.loader import ConfigError
from glean.pipeline import engine as engine_module
from glean.pipeline import stages as stages_module
from glean.pipeline.engine import Runner
from glean.pipeline.stages import LLMCallCounter, semantic_dedup_stage
from glean.sources.base import Item
from glean.state.embedding_bytes import cosine_similarity, pack_embedding, unpack_embedding
from glean.state.store import StateStore

pytestmark = pytest.mark.asyncio

_NOW = datetime(2025, 1, 3, tzinfo=UTC)


class FakeEmbeddingProvider:
    name = "fake"

    def __init__(
        self,
        vectors_by_text: dict[str, list[float]],
        *,
        fail_texts: set[str] | None = None,
    ) -> None:
        self._vectors_by_text = vectors_by_text
        self._fail_texts = fail_texts or set()
        self.embed_calls: list[str] = []

    async def embed(self, text: str) -> list[float]:
        self.embed_calls.append(text)
        if text in self._fail_texts:
            raise RuntimeError("embedding boom")
        return list(self._vectors_by_text[text])

    async def aclose(self) -> None:
        pass


@dataclass(frozen=True, slots=True)
class _SeenItem:
    feed: str
    canonical_url: str
    title: str | None
    embedding: bytes
    embedding_model: str
    seen_at: datetime


class FakeStore:
    def __init__(self, seen: list[_SeenItem], *, now: datetime = _NOW) -> None:
        self._seen = seen
        self._now = now
        self.calls: list[dict[str, object]] = []

    async def find_similar_seen_items(
        self,
        *,
        feed: str,
        embedding: list[float],
        embedding_model: str,
        threshold: float,
        window: timedelta,
    ) -> list[tuple[str, str | None, float]]:
        self.calls.append(
            {
                "feed": feed,
                "threshold": threshold,
                "window": window,
                "embedding_model": embedding_model,
            }
        )
        query = embedding
        cutoff = self._now - window
        matches: list[tuple[str, str | None, float]] = []
        for record in self._seen:
            if record.feed != feed:
                continue
            if record.embedding_model != embedding_model:
                continue
            if record.seen_at < cutoff:
                continue
            similarity = cosine_similarity(query, unpack_embedding(record.embedding))
            if similarity >= threshold:
                matches.append((record.canonical_url, record.title, similarity))
        matches.sort(key=lambda row: row[2], reverse=True)
        return matches


def _item(title: str, *, body: str = "") -> Item:
    return Item(
        canonical_url=f"https://example.com/{title}",
        title=title,
        body=body,
        source_type="rss",
        source_name="feed",
    )


@pytest.fixture
def warning_events(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, dict[str, object]]]:
    warnings: list[tuple[str, dict[str, object]]] = []
    monkeypatch.setattr(
        stages_module,
        "logger",
        SimpleNamespace(
            debug=lambda *_args, **_kwargs: None,
            warning=lambda event, **kwargs: warnings.append((event, kwargs)),
        ),
    )
    return warnings


async def test_semantic_dedup_stage_suppresses_similar_item() -> None:
    item = _item("fresh")
    provider = FakeEmbeddingProvider({"fresh": [1.0, 0.0]})
    store = FakeStore(
        [
            _SeenItem(
                feed="feed",
                canonical_url="https://example.com/old",
                title="Old title",
                embedding=pack_embedding([1.0, 0.0]),
                embedding_model="embed-model",
                seen_at=_NOW,
            )
        ]
    )

    kept, suppressed = await semantic_dedup_stage(
        "feed",
        [item],
        provider,
        store,
        embedding_model_name="embed-model",
    )

    assert kept == []
    assert len(suppressed) == 1
    assert suppressed[0].suppressed_url == item.canonical_url
    assert suppressed[0].suppressed_title == item.title
    assert suppressed[0].matched_url == "https://example.com/old"
    assert suppressed[0].matched_title == "Old title"
    assert suppressed[0].similarity == pytest.approx(1.0)


async def test_semantic_dedup_stage_keeps_distant_item_and_attaches_embedding() -> None:
    item = _item("fresh")
    provider = FakeEmbeddingProvider({"fresh": [0.0, 1.0]})
    store = FakeStore(
        [
            _SeenItem(
                feed="feed",
                canonical_url="https://example.com/old",
                title="Old title",
                embedding=pack_embedding([1.0, 0.0]),
                embedding_model="embed-model",
                seen_at=_NOW,
            )
        ]
    )

    kept, suppressed = await semantic_dedup_stage(
        "feed",
        [item],
        provider,
        store,
        embedding_model_name="embed-model",
    )

    assert suppressed == []
    assert len(kept) == 1
    assert kept[0].canonical_url == item.canonical_url
    assert kept[0].embedding == pack_embedding([0.0, 1.0])


async def test_semantic_dedup_stage_keeps_all_items_when_seen_set_is_empty() -> None:
    items = [_item("a"), _item("b")]
    provider = FakeEmbeddingProvider({"a": [1.0, 0.0], "b": [0.0, 1.0]})

    kept, suppressed = await semantic_dedup_stage(
        "feed",
        items,
        provider,
        FakeStore([]),
        embedding_model_name="embed-model",
    )

    assert suppressed == []
    assert [item.title for item in kept] == ["a", "b"]
    assert kept[0].embedding == pack_embedding([1.0, 0.0])
    assert kept[1].embedding == pack_embedding([0.0, 1.0])


async def test_semantic_dedup_stage_fails_open_when_embedding_provider_raises(
    warning_events: list[tuple[str, dict[str, object]]],
) -> None:
    item = _item("boom")
    provider = FakeEmbeddingProvider({"boom": [1.0, 0.0]}, fail_texts={"boom"})

    kept, suppressed = await semantic_dedup_stage(
        "feed",
        [item],
        provider,
        FakeStore([]),
        embedding_model_name="embed-model",
    )

    assert suppressed == []
    assert len(kept) == 1
    assert kept[0].canonical_url == item.canonical_url
    assert kept[0].embedding is None
    assert warning_events == [
        (
            "semantic_dedup_failed",
            {
                "feed": "feed",
                "url": item.canonical_url,
                "err_type": "RuntimeError",
                "err": "embedding boom",
            },
        )
    ]


async def test_semantic_dedup_stage_with_similarity_one_keeps_non_identical_match() -> None:
    item = _item("fresh")
    provider = FakeEmbeddingProvider({"fresh": [1.0, 0.1]})
    store = FakeStore(
        [
            _SeenItem(
                feed="feed",
                canonical_url="https://example.com/old",
                title="Old title",
                embedding=pack_embedding([1.0, 0.0]),
                embedding_model="embed-model",
                seen_at=_NOW,
            )
        ]
    )

    kept, suppressed = await semantic_dedup_stage(
        "feed",
        [item],
        provider,
        store,
        min_similarity=1.0,
        embedding_model_name="embed-model",
    )

    assert len(kept) == 1
    assert suppressed == []


async def test_semantic_dedup_stage_with_similarity_zero_suppresses_everything() -> None:
    item = _item("fresh")
    provider = FakeEmbeddingProvider({"fresh": [0.0, 1.0]})
    store = FakeStore(
        [
            _SeenItem(
                feed="feed",
                canonical_url="https://example.com/old",
                title="Old title",
                embedding=pack_embedding([1.0, 0.0]),
                embedding_model="embed-model",
                seen_at=_NOW,
            )
        ]
    )

    kept, suppressed = await semantic_dedup_stage(
        "feed",
        [item],
        provider,
        store,
        min_similarity=0.0,
        embedding_model_name="embed-model",
    )

    assert kept == []
    assert len(suppressed) == 1
    assert suppressed[0].matched_url == "https://example.com/old"


async def test_semantic_dedup_stage_ignores_matches_outside_window() -> None:
    item = _item("fresh")
    provider = FakeEmbeddingProvider({"fresh": [1.0, 0.0]})
    store = FakeStore(
        [
            _SeenItem(
                feed="feed",
                canonical_url="https://example.com/old",
                title="Old title",
                embedding=pack_embedding([1.0, 0.0]),
                embedding_model="embed-model",
                seen_at=_NOW - timedelta(days=2),
            )
        ]
    )

    kept, suppressed = await semantic_dedup_stage(
        "feed",
        [item],
        provider,
        store,
        window=timedelta(days=1),
        embedding_model_name="embed-model",
    )

    assert len(kept) == 1
    assert suppressed == []


async def test_semantic_dedup_stage_skips_item_when_llm_budget_is_exhausted() -> None:
    item = _item("fresh")
    provider = FakeEmbeddingProvider({"fresh": [1.0, 0.0]})

    kept, suppressed = await semantic_dedup_stage(
        "feed",
        [item],
        provider,
        FakeStore([]),
        embedding_model_name="embed-model",
        llm_counter=LLMCallCounter(0),
    )

    assert suppressed == []
    assert len(kept) == 1
    assert kept[0].embedding is None
    assert provider.embed_calls == []


async def test_semantic_dedup_config_defaults_window_and_similarity(write_yaml: Any) -> None:
    yaml = textwrap.dedent(
        """
        defaults:
          llm:
            provider: ollama
            model: embed-default
            base_url: http://ollama:11434
        feeds:
          - name: semantic
            schedule: \"every 1h\"
            chat_id: -1
            sources:
              - type: rss
                url: https://example.com/feed.xml
            pipeline:
              - dedup
              - semantic_dedup: {}
        """
    )

    cfg = load_config(write_yaml(yaml))
    stage = cfg.feeds[0].pipeline[1]

    assert stage.name == "semantic_dedup"
    assert stage.params["min_similarity"] == pytest.approx(0.85)
    assert stage.params["window"] == timedelta(days=7)
    assert "embedding_model" not in stage.params


async def test_semantic_dedup_config_rejects_invalid_similarity(write_yaml: Any) -> None:
    yaml = textwrap.dedent(
        """
        feeds:
          - name: semantic
            schedule: \"every 1h\"
            chat_id: -1
            sources:
              - type: rss
                url: https://example.com/feed.xml
            pipeline:
              - semantic_dedup:
                  min_similarity: 1.5
        """
    )

    with pytest.raises(ConfigError, match="semantic_dedup.min_similarity"):
        load_config(write_yaml(yaml))


async def test_semantic_dedup_config_rejects_invalid_window(write_yaml: Any) -> None:
    yaml = textwrap.dedent(
        """
        feeds:
          - name: semantic
            schedule: \"every 1h\"
            chat_id: -1
            sources:
              - type: rss
                url: https://example.com/feed.xml
            pipeline:
              - semantic_dedup:
                  window: weekly
        """
    )

    with pytest.raises(ConfigError, match="semantic_dedup.window"):
        load_config(write_yaml(yaml))


async def test_runner_uses_feed_effective_llm_for_semantic_dedup_provider(
    tmp_path: Any,
    write_yaml: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured_specs: list[dict[str, Any]] = []

    class StubEmbeddingProvider:
        name = "stub"

        async def embed(self, text: str) -> list[float]:
            return [1.0]

        async def aclose(self) -> None:
            pass

    def fake_build_embedding_provider(spec: dict[str, Any]) -> StubEmbeddingProvider:
        captured_specs.append(dict(spec))
        return StubEmbeddingProvider()

    monkeypatch.setattr(engine_module, "build_embedding_provider", fake_build_embedding_provider)

    yaml = textwrap.dedent(
        """
        defaults:
          llm:
            provider: ollama
            model: default-model
            base_url: http://ollama:11434
        feeds:
          - name: semantic
            schedule: \"every 1h\"
            chat_id: -1
            llm:
              provider: ollama
              model: feed-model
              base_url: http://ollama:11434
            sources:
              - type: rss
                url: https://example.com/feed.xml
            pipeline:
              - semantic_dedup: {}
        """
    )
    cfg = load_config(write_yaml(yaml))
    state = StateStore(tmp_path / "state.db")
    await state.open()
    runner = Runner(cfg, state)
    try:
        feed = cfg.feed("semantic")
        stage = feed.pipeline[0]

        provider_one, model_one = runner._get_embedding_provider(feed, stage)
        provider_two, model_two = runner._get_embedding_provider(feed, stage)

        assert provider_one is provider_two
        assert model_one == model_two == "feed-model"
        assert len(captured_specs) == 1
        assert captured_specs[0]["provider"] == "ollama"
        assert captured_specs[0]["model"] == "feed-model"
    finally:
        await runner.aclose()
        await state.close()
