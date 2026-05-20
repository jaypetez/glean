from __future__ import annotations

import asyncio
import dataclasses
from collections.abc import Callable
from dataclasses import dataclass
from datetime import timedelta
from typing import TYPE_CHECKING

from glean.config.skills import SkillConfig, render_skill_prompt, skill_output_schema
from glean.llm.embedding import EmbeddingProvider
from glean.llm.output_filter import filter_llm_output
from glean.logging import get_logger
from glean.security.scrub import scrub
from glean.sources.base import Item
from glean.state.embedding_bytes import pack_embedding

if TYPE_CHECKING:
    from glean.llm.base import LLMProvider
    from glean.state.store import StateStore

logger = get_logger(__name__)

_RANK_CONCURRENCY = 4
_SUMMARIZE_CONCURRENCY = 4
_SEMANTIC_DEDUP_CONCURRENCY = 4


@dataclass(frozen=True, slots=True)
class SuppressedItemRecord:
    suppressed_url: str
    suppressed_title: str | None
    matched_url: str
    matched_title: str | None
    similarity: float


class LLMCallCounter:
    def __init__(self, max_calls: int | None) -> None:
        self.max_calls = max_calls
        self.calls = 0
        self._capped_logged = False
        self._lock = asyncio.Lock()

    @property
    def at_limit(self) -> bool:
        return self.max_calls is not None and self.calls >= self.max_calls

    async def increment(self, feed: str) -> bool:
        calls: int | None = None
        max_calls: int | None = None
        async with self._lock:
            if self.at_limit:
                if not self._capped_logged:
                    calls = self.calls
                    max_calls = self.max_calls
                    self._capped_logged = True
            else:
                self.calls += 1
                return True
        if calls is not None and max_calls is not None:
            logger.warning("llm_budget_capped", feed=feed, calls=calls, max=max_calls)
        return False


def _semantic_dedup_text(item: Item) -> str:
    body = item.body.strip()
    summary = (item.llm_summary or item.summary or "").strip()
    parts = [item.title.strip()]
    if body:
        parts.append(body)
    elif summary:
        parts.append(summary)
    return "\n\n".join(part for part in parts if part)


async def semantic_dedup_stage(
    feed: str,
    items: list[Item],
    embedding_provider: EmbeddingProvider,
    store: StateStore,
    *,
    min_similarity: float = 0.85,
    window: timedelta = timedelta(days=7),
    embedding_model_name: str,
    trace_id: str | None = None,
    llm_counter: LLMCallCounter | None = None,
) -> tuple[list[Item], list[SuppressedItemRecord]]:
    """Suppress items semantically similar to already-sent items in this feed."""
    if not items:
        return [], []
    sem = asyncio.Semaphore(_SEMANTIC_DEDUP_CONCURRENCY)

    async def one(item: Item) -> tuple[Item | None, SuppressedItemRecord | None]:
        async with sem:
            # Shares the feed-level LLM budget with other stages by design.
            if llm_counter is not None and not await llm_counter.increment(feed):
                return item, None
            try:
                text = _semantic_dedup_text(item)
                embedding = await embedding_provider.embed(text)
                packed_embedding = pack_embedding(embedding)
                matches = await store.find_similar_seen_items(
                    feed=feed,
                    embedding=embedding,
                    embedding_model=embedding_model_name,
                    threshold=min_similarity,
                    window=window,
                )
            except Exception as exc:
                log_kwargs = {
                    "feed": feed,
                    "url": item.canonical_url,
                    "err_type": type(exc).__name__,
                    "err": scrub(str(exc))[:500] or "(no message)",
                }
                if trace_id is not None:
                    log_kwargs["trace_id"] = trace_id
                logger.warning("semantic_dedup_failed", **log_kwargs)
                return item, None

            if matches:
                matched_url, matched_title, similarity = matches[0]
                return None, SuppressedItemRecord(
                    suppressed_url=item.canonical_url,
                    suppressed_title=item.title,
                    matched_url=matched_url,
                    matched_title=matched_title,
                    similarity=similarity,
                )

            return dataclasses.replace(item, embedding=packed_embedding), None

    results = await asyncio.gather(*(one(item) for item in items))
    kept = [item for item, _record in results if item is not None]
    suppressed = [record for _item, record in results if record is not None]
    logger.debug("semantic_dedup", feed=feed, kept=len(kept), suppressed=len(suppressed))
    return kept, suppressed


async def dedup_stage(feed: str, items: list[Item], state: StateStore) -> list[Item]:
    new_items = await state.filter_new(feed, items)
    logger.debug("dedup", feed=feed, before=len(items), after=len(new_items))
    return new_items


async def rank_stage(
    feed: str,
    items: list[Item],
    llm_for: Callable[[Item], LLMProvider],
    *,
    prompt: str,
    min_relevance: float,
    llm_counter: LLMCallCounter | None = None,
) -> tuple[list[Item], list[Item]]:
    """Return (kept, dropped). Items get a .relevance score attached."""
    if not items:
        return [], []
    sem = asyncio.Semaphore(_RANK_CONCURRENCY)

    async def score(item: Item) -> tuple[Item, bool]:
        async with sem:
            if llm_counter is not None and not await llm_counter.increment(feed):
                return item, False
            try:
                s = await llm_for(item).rank(item, prompt)
            except Exception as exc:
                logger.warning(
                    "rank_failed",
                    feed=feed,
                    url=item.canonical_url,
                    err_type=type(exc).__name__,
                    err=scrub(str(exc))[:500] or "(no message)",
                )
                s = 0.0
            return dataclasses.replace(item, relevance=s), True

    score_results = await asyncio.gather(*(score(i) for i in items))
    scored = [i for i, called in score_results if called]
    skipped = [i for i, called in score_results if not called]
    kept = [i for i in scored if (i.relevance or 0.0) >= min_relevance]
    dropped = [i for i in scored if (i.relevance or 0.0) < min_relevance]
    kept.sort(key=lambda i: i.relevance or 0.0, reverse=True)
    kept.extend(skipped)
    logger.debug("rank", feed=feed, kept=len(kept), dropped=len(dropped))
    return kept, dropped


async def summarize_stage(
    feed: str,
    items: list[Item],
    llm_for: Callable[[Item], LLMProvider],
    *,
    prompt: str,
    llm_counter: LLMCallCounter | None = None,
) -> list[Item]:
    if not items:
        return []
    sem = asyncio.Semaphore(_SUMMARIZE_CONCURRENCY)

    async def one(item: Item) -> Item:
        async with sem:
            if llm_counter is not None and not await llm_counter.increment(feed):
                return dataclasses.replace(item, llm_summary="")
            try:
                summary = filter_llm_output(await llm_for(item).summarize(item, prompt))
            except Exception as exc:
                logger.warning(
                    "summarize_failed",
                    feed=feed,
                    url=item.canonical_url,
                    err_type=type(exc).__name__,
                    err=scrub(str(exc))[:500] or "(no message)",
                )
                summary = item.summary or ""
            return dataclasses.replace(item, llm_summary=summary)

    return await asyncio.gather(*(one(i) for i in items))


async def digest_intro(
    feed: str,
    items: list[Item],
    llm: LLMProvider,
    *,
    prompt: str,
    llm_counter: LLMCallCounter | None = None,
) -> str:
    if not items:
        return prompt
    if llm_counter is not None and not await llm_counter.increment(feed):
        return prompt
    try:
        return filter_llm_output(await llm.digest(items, prompt))
    except Exception as exc:
        logger.warning(
            "digest_failed",
            feed=feed,
            err_type=type(exc).__name__,
            err=scrub(str(exc))[:500] or "(no message)",
        )
        return prompt


async def apply_skill_stage(
    feed: str,
    items: list[Item],
    llm_for: Callable[[Item], LLMProvider],
    *,
    skill: SkillConfig,
    skill_llm: LLMProvider | None = None,
    llm_counter: LLMCallCounter | None = None,
) -> list[Item]:
    """Run structured extraction for each item using the skill's schema.

    Precedence: skill_llm (if set) > llm_for(item) > falls back inside resolver.
    """
    if not items:
        return []
    sem = asyncio.Semaphore(_SUMMARIZE_CONCURRENCY)
    json_schema = skill_output_schema(skill)

    async def one(item: Item) -> Item:
        async with sem:
            provider = skill_llm or llm_for(item)
            # Defensive: third-party providers may not implement extract()
            extract_fn = getattr(provider, "extract", None)
            if extract_fn is None:
                logger.warning(
                    "skill_extract_unavailable",
                    feed=feed,
                    skill=skill.name,
                    provider=type(provider).__name__,
                )
                return item

            rendered_prompt = render_skill_prompt(skill.prompt, item)
            if llm_counter is not None and not await llm_counter.increment(feed):
                return item
            try:
                result = await extract_fn(
                    item,
                    rendered_prompt,
                    json_schema,
                    system_prompt=skill.system_prompt,
                )
            except Exception as exc:
                logger.warning(
                    "skill_extract_failed",
                    feed=feed,
                    skill=skill.name,
                    url=item.canonical_url,
                    err_type=type(exc).__name__,
                    err=scrub(str(exc))[:500] or "(no message)",
                )
                result = {}

            # Auto-populate llm_summary from common summary field names so
            # existing renderers work without changes.
            new_summary: str | None = item.llm_summary
            for key in ("summary", "one_liner", "tldr"):
                value = result.get(key)
                if isinstance(value, str) and value.strip():
                    new_summary = value
                    break

            return dataclasses.replace(item, structured=result, llm_summary=new_summary)

    return list(await asyncio.gather(*(one(i) for i in items)))
