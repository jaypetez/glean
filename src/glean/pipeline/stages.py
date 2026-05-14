from __future__ import annotations

import asyncio
import dataclasses
from collections.abc import Callable
from typing import TYPE_CHECKING

from glean.config.skills import SkillConfig, render_skill_prompt, skill_output_schema
from glean.llm.output_filter import filter_llm_output
from glean.logging import get_logger
from glean.security.scrub import scrub
from glean.sources.base import Item

if TYPE_CHECKING:
    from glean.llm.base import LLMProvider
    from glean.state.store import StateStore

logger = get_logger(__name__)

_RANK_CONCURRENCY = 4
_SUMMARIZE_CONCURRENCY = 4


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
) -> tuple[list[Item], list[Item]]:
    """Return (kept, dropped). Items get a .relevance score attached."""
    if not items:
        return [], []
    sem = asyncio.Semaphore(_RANK_CONCURRENCY)

    async def score(item: Item) -> Item:
        async with sem:
            try:
                s = await llm_for(item).rank(item, prompt)
            except Exception as exc:
                logger.warning(
                    "rank_failed",
                    feed=feed,
                    url=item.canonical_url,
                    err=scrub(str(exc))[:500],
                )
                s = 0.0
            return dataclasses.replace(item, relevance=s)

    scored = await asyncio.gather(*(score(i) for i in items))
    kept = [i for i in scored if (i.relevance or 0.0) >= min_relevance]
    dropped = [i for i in scored if (i.relevance or 0.0) < min_relevance]
    kept.sort(key=lambda i: i.relevance or 0.0, reverse=True)
    logger.debug("rank", feed=feed, kept=len(kept), dropped=len(dropped))
    return kept, dropped


async def summarize_stage(
    feed: str,
    items: list[Item],
    llm_for: Callable[[Item], LLMProvider],
    *,
    prompt: str,
) -> list[Item]:
    if not items:
        return []
    sem = asyncio.Semaphore(_SUMMARIZE_CONCURRENCY)

    async def one(item: Item) -> Item:
        async with sem:
            try:
                summary = filter_llm_output(await llm_for(item).summarize(item, prompt))
            except Exception as exc:
                logger.warning(
                    "summarize_failed",
                    feed=feed,
                    url=item.canonical_url,
                    err=scrub(str(exc))[:500],
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
) -> str:
    if not items:
        return prompt
    try:
        return filter_llm_output(await llm.digest(items, prompt))
    except Exception as exc:
        logger.warning("digest_failed", feed=feed, err=scrub(str(exc))[:500])
        return prompt


async def apply_skill_stage(
    feed: str,
    items: list[Item],
    llm_for: Callable[[Item], LLMProvider],
    *,
    skill: SkillConfig,
    skill_llm: LLMProvider | None = None,
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
                    err=scrub(str(exc))[:500],
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
