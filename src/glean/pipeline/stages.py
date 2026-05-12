from __future__ import annotations

import asyncio
import dataclasses
from typing import TYPE_CHECKING

from glean.logging import get_logger
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
    llm: LLMProvider,
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
                s = await llm.rank(item, prompt)
            except Exception as exc:
                logger.warning(
                    "rank_failed",
                    feed=feed,
                    url=item.canonical_url,
                    err=str(exc),
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
    llm: LLMProvider,
    *,
    prompt: str,
) -> list[Item]:
    if not items:
        return []
    sem = asyncio.Semaphore(_SUMMARIZE_CONCURRENCY)

    async def one(item: Item) -> Item:
        async with sem:
            try:
                summary = await llm.summarize(item, prompt)
            except Exception as exc:
                logger.warning(
                    "summarize_failed",
                    feed=feed,
                    url=item.canonical_url,
                    err=str(exc),
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
        return await llm.digest(items, prompt)
    except Exception as exc:
        logger.warning("digest_failed", feed=feed, err=str(exc))
        return prompt
