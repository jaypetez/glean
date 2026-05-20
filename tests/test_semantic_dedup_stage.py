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


# === End-to-end Runner integration: prove ranked-out items still
# === contribute embeddings to the next tick's semantic_dedup query.

class _CrossTickEmbeddingProvider:
    """Deterministic embedding provider keyed by item title.

    Used to model 'two distinct URLs covering the same story' across
    runs without depending on a live embedding service.
    """

    name = "crosstick-fake"

    def __init__(self, vectors_by_title: dict[str, list[float]]) -> None:
        self._vectors_by_title = vectors_by_title
        self.embed_calls: list[str] = []

    async def embed(self, text: str) -> list[float]:
        self.embed_calls.append(text)
        for title, vec in self._vectors_by_title.items():
            if title in text:
                return list(vec)
        raise KeyError(f"no fake embedding configured for: {text!r}")

    async def aclose(self) -> None:
        pass


async def test_semantic_dedup_e2e_suppresses_cross_url_near_dups_next_tick(
    tmp_path: Any,
    write_yaml: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Regression for PR #186 bugs caught by end-to-end verification:

    Tick 1: fetch 2 items (A1, B1) with distinct URLs. They go through dedup ->
            semantic_dedup (no prior items, both pass) -> rank (both get 0.9).
            Only ONE of them gets sent (low render.max_items).
    Tick 2: fetch 2 NEW items (A2, B2) with DIFFERENT URLs but SAME embedding
            vectors as A1, B1. URL dedup lets them through (URLs are new).
            semantic_dedup should suppress BOTH because their embeddings match
            items already seen in tick 1 -- including the one that was NEVER
            sent (proves the fix to find_similar_seen_items + post-stage
            mark_seen are both correct).
    """
    # Local FakeSource so we can swap items between ticks
    fake_items: list[dict] = []

    from glean.sources.base import FetchContext
    from glean.sources.registry import register_source

    @register_source("crosstick_fake")
    class CrossTickFakeSource:
        type = "crosstick_fake"

        def __init__(self) -> None:
            pass

        async def fetch(self, ctx: FetchContext) -> list[Item]:
            return [
                Item(
                    canonical_url=i["url"],
                    title=i["title"],
                    body=i.get("body", ""),
                    source_type="crosstick_fake",
                    source_name="crosstick",
                )
                for i in fake_items
            ]

    # Reuse the FakeLLM from test_runner.py via a minimal local register
    from glean.llm.registry import register_provider

    @register_provider("ct_fake_llm")
    class CtFakeLLM:
        name = "ct_fake_llm"

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

    # Vectors keyed by stable substring in the title. A1/A2 share a vector;
    # B1/B2 share a vector. So tick 2's items will look near-identical to
    # items already seen in tick 1.
    fake_emb = _CrossTickEmbeddingProvider(
        {
            "story_a": [1.0, 0.0],
            "story_b": [0.0, 1.0],
        }
    )

    def fake_build_embedding_provider(spec: dict[str, Any]) -> _CrossTickEmbeddingProvider:
        return fake_emb

    monkeypatch.setattr(engine_module, "build_embedding_provider", fake_build_embedding_provider)

    yaml = textwrap.dedent(
        """
        defaults:
          llm:
            provider: ct_fake_llm
            model: fake
        feeds:
          - name: t-semantic
            schedule: "every 1h"
            chat_id: -1
            sources:
              - type: crosstick_fake
            pipeline:
              - dedup
              - semantic_dedup:
                  embedding_model: fake
                  min_similarity: 0.85
                  window: "1d"
              - rank:
                  prompt: "rank"
                  min_relevance: 0.5
              - summarize:
                  prompt: "summarize"
              - digest:
                  intro: "intro"
        """
    )
    cfg = load_config(write_yaml(yaml))
    state = StateStore(tmp_path / "state.db")
    await state.open()

    # Skip the bootstrap-skip-and-mark branch so tick 1 actually runs the pipeline.
    await state.set_bootstrapped("t-semantic")

    # Minimal telegram stub
    class _TG:
        def __init__(self) -> None:
            self.sent: list[tuple[int | str, list[str]]] = []
            self.texts: list[tuple[int | str, str]] = []

        async def send_digest(self, chat_id, messages, *, style="html", link_preview=False):
            self.sent.append((chat_id, list(messages)))

        async def send_text(self, chat_id, text, *, style="html"):
            self.texts.append((chat_id, text))

        async def aclose(self):
            pass

    tg = _TG()
    runner = Runner(cfg, state, telegram=tg)  # type: ignore[arg-type]

    try:
        # Tick 1: two distinct stories, distinct URLs
        fake_items[:] = [
            {"url": "https://source-a.example/story_a-v1", "title": "story_a from A"},
            {"url": "https://source-b.example/story_b-v1", "title": "story_b from A"},
        ]
        result1 = await runner.run_feed("t-semantic")
        assert result1.sent == 2, f"tick 1 should send both items, got result={result1}"
        assert result1.suppressed_semantic == 0
        assert len(fake_emb.embed_calls) == 2

        # Tick 2: same two stories, DIFFERENT URLs (so url-dedup passes them through),
        # SAME embedding vectors (so semantic_dedup catches them as near-dups)
        fake_items[:] = [
            {"url": "https://source-a.example/story_a-v2-different-url", "title": "story_a from B"},
            {"url": "https://source-b.example/story_b-v2-different-url", "title": "story_b from B"},
        ]
        result2 = await runner.run_feed("t-semantic")

        # The whole point: both should be suppressed because they are near-dups
        # of items seen in tick 1.
        assert result2.suppressed_semantic == 2, (
            f"tick 2 should suppress both near-duplicates, got "
            f"suppressed_semantic={result2.suppressed_semantic}, sent={result2.sent}"
        )
        assert result2.sent == 0
        # Embeddings were called for tick 2's 2 items
        assert len(fake_emb.embed_calls) == 4
    finally:
        await runner.aclose()
        await state.close()

async def test_semantic_dedup_persists_embeddings_for_ranked_out_items(
    tmp_path: Any,
    write_yaml: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Regression for PR #187 engine-side fix.

    Tick 1: 1 item passes semantic_dedup but gets dropped by rank (low score).
            Without the fix, this item's embedding is LOST -- mark_seen with
            sent=True is never called for it.
    Tick 2: 1 NEW item with DIFFERENT URL but SAME embedding as tick 1's
            ranked-out item. semantic_dedup must suppress it, which proves
            the engine persisted the embedding via mark_seen(sent=False)
            right after the stage.
    """
    fake_items: list[dict] = []

    from glean.sources.base import FetchContext
    from glean.sources.registry import register_source

    @register_source("ranked_out_fake")
    class RankedOutFakeSource:
        type = "ranked_out_fake"

        def __init__(self) -> None:
            pass

        async def fetch(self, ctx: FetchContext) -> list[Item]:
            return [
                Item(
                    canonical_url=i["url"],
                    title=i["title"],
                    body=i.get("body", ""),
                    source_type="ranked_out_fake",
                    source_name="ranked_out",
                )
                for i in fake_items
            ]

    from glean.llm.registry import register_provider

    # Returns rank=0.1 always -- below the 0.5 min_relevance threshold,
    # so ALL items get dropped by rank.
    @register_provider("zero_rank_llm")
    class ZeroRankLLM:
        name = "zero_rank_llm"

        def __init__(self, **_: object) -> None:
            self.model = "fake"

        async def rank(self, item: Item, prompt: str) -> float:
            return 0.1

        async def summarize(self, item: Item, prompt: str) -> str:
            return ""

        async def digest(self, items, prompt: str) -> str:
            return prompt

        async def aclose(self) -> None:
            pass

    fake_emb = _CrossTickEmbeddingProvider(
        {"story_c": [1.0, 0.0]}
    )

    monkeypatch.setattr(
        engine_module, "build_embedding_provider", lambda _spec: fake_emb
    )

    yaml = textwrap.dedent(
        """
        defaults:
          llm:
            provider: zero_rank_llm
            model: fake
        feeds:
          - name: t-ranked-out
            schedule: "every 1h"
            chat_id: -1
            sources:
              - type: ranked_out_fake
            pipeline:
              - dedup
              - semantic_dedup:
                  embedding_model: fake
                  min_similarity: 0.85
                  window: "1d"
              - rank:
                  prompt: "rank"
                  min_relevance: 0.5
              - digest:
                  intro: "intro"
        """
    )
    cfg = load_config(write_yaml(yaml))
    state = StateStore(tmp_path / "state.db")
    await state.open()
    await state.set_bootstrapped("t-ranked-out")

    class _TG:
        async def send_digest(self, *_a, **_kw): pass
        async def send_text(self, *_a, **_kw): pass
        async def aclose(self): pass

    runner = Runner(cfg, state, telegram=_TG())  # type: ignore[arg-type]

    try:
        # Tick 1: one item, will be ranked out (rank=0.1 < min=0.5)
        fake_items[:] = [
            {"url": "https://source-a.example/story_c-v1", "title": "story_c version A"},
        ]
        result1 = await runner.run_feed("t-ranked-out")
        assert result1.sent == 0, "tick 1 should send 0 (ranked out)"
        assert result1.suppressed_semantic == 0
        assert len(fake_emb.embed_calls) == 1

        # Tick 2: same story, different URL
        fake_items[:] = [
            {"url": "https://source-b.example/story_c-v2-different", "title": "story_c version B"},
        ]
        result2 = await runner.run_feed("t-ranked-out")

        # If the engine fix is in place, tick 1's embedding was persisted
        # despite the rank-out, so tick 2's near-dup gets suppressed.
        # Without the fix: tick 1's embedding was lost -> tick 2's item
        # passes semantic_dedup with suppressed_semantic=0.
        assert result2.suppressed_semantic == 1, (
            f"tick 2 must suppress the cross-URL near-dup of the ranked-out item; "
            f"got suppressed_semantic={result2.suppressed_semantic}, sent={result2.sent}"
        )
    finally:
        await runner.aclose()
        await state.close()