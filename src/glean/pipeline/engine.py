from __future__ import annotations

import contextlib
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import httpx

from glean.config.schema import Config, FeedConfig, StageSpec
from glean.llm import build_provider
from glean.llm.base import LLMProvider
from glean.logging import get_logger
from glean.pipeline.stages import (
    dedup_stage,
    digest_intro,
    rank_stage,
    summarize_stage,
)
from glean.sources import FetchContext, build_source
from glean.sources.base import Item
from glean.telegram import TelegramSender, render_digest

if TYPE_CHECKING:
    from glean.state import StateStore

logger = get_logger(__name__)


@dataclass(slots=True)
class RunResult:
    feed: str
    fetched: int = 0
    after_dedup: int = 0
    sent: int = 0
    dropped: int = 0
    overflow: int = 0
    duration_ms: int = 0
    error: str | None = None
    skipped_reason: str | None = None
    messages: list[str] = field(default_factory=list)


class Runner:
    def __init__(
        self,
        config: Config,
        state: StateStore,
        telegram: TelegramSender | None,
        http: httpx.AsyncClient | None = None,
    ) -> None:
        self.config = config
        self.state = state
        self.telegram = telegram
        self.http = http or httpx.AsyncClient(timeout=30.0)
        self._owns_http = http is None
        self._llm_cache: dict[tuple[str, str, str | None], LLMProvider] = {}

    async def aclose(self) -> None:
        for provider in self._llm_cache.values():
            with contextlib.suppress(Exception):
                await provider.aclose()
        if self._owns_http:
            await self.http.aclose()
        if self.telegram is not None:
            await self.telegram.aclose()

    def _get_llm(self, feed: FeedConfig) -> LLMProvider:
        cfg = feed.effective_llm(self.config.defaults)
        key = (cfg.provider, cfg.model, cfg.base_url)
        if key not in self._llm_cache:
            self._llm_cache[key] = build_provider(cfg.model_dump(exclude_none=True))
        return self._llm_cache[key]

    async def run_feed(self, name: str, *, dry_run: bool = False) -> RunResult:
        started = time.monotonic()
        feed = self.config.feed(name)
        result = RunResult(feed=name)

        try:
            items = await self._fetch_all(feed)
            result.fetched = len(items)

            bootstrap_mode = feed.effective_bootstrap(self.config.defaults)
            bootstrapped = await self.state.is_bootstrapped(name)

            if not bootstrapped and bootstrap_mode == "skip-and-mark":
                if not dry_run:
                    await self.state.mark_seen(name, items, sent=True)
                    await self.state.set_bootstrapped(name)
                    await self.state.record_success(name)
                result.skipped_reason = "bootstrap"
                result.after_dedup = 0
                logger.info(
                    "bootstrap_skip", feed=name, indexed=len(items), dry_run=dry_run
                )
                return result

            # Run pipeline stages
            new_items = await dedup_stage(name, items, self.state)
            result.after_dedup = len(new_items)
            if not new_items:
                if not dry_run:
                    await self.state.record_success(name)
                logger.info("no_new_items", feed=name)
                return result

            llm = self._get_llm(feed)
            intro: str = ""

            for stage in feed.pipeline:
                new_items, intro = await self._run_stage(
                    feed, stage, new_items, llm, intro, result
                )
                if not new_items:
                    break

            render_cfg = feed.effective_render(self.config.defaults)
            ranked_count = len(new_items)
            if ranked_count > render_cfg.max_items:
                result.overflow = ranked_count - render_cfg.max_items
                new_items = new_items[: render_cfg.max_items]

            if not new_items:
                if not dry_run:
                    await self.state.record_success(name)
                logger.info("nothing_to_send", feed=name)
                return result

            messages = render_digest(
                new_items,
                intro=intro,
                render=render_cfg,
                overflow_count=result.overflow,
            )
            result.messages = messages

            if dry_run:
                logger.info(
                    "dry_run", feed=name, would_send=len(messages), items=ranked_count
                )
            else:
                if self.telegram is None:
                    raise RuntimeError("telegram sender not configured")
                await self.telegram.send_digest(
                    feed.chat_id,
                    messages,
                    style=render_cfg.style,
                    link_preview=render_cfg.link_preview,
                )
                await self.state.mark_seen(name, new_items, sent=True)
                await self.state.set_bootstrapped(name)
                recovery = await self.state.record_success(name)
                if recovery:
                    fc = feed.effective_failure(self.config.defaults)
                    if fc.ops_chat_id:
                        await self.telegram.send_text(
                            fc.ops_chat_id, f"✅ <b>{name}</b> recovered."
                        )
                result.sent = len(new_items)

        except Exception as exc:
            result.error = f"{type(exc).__name__}: {exc}"
            logger.error("feed_failed", feed=name, err=result.error)
            if not dry_run:
                fc = feed.effective_failure(self.config.defaults)
                _, should_alert = await self.state.record_failure(
                    name, result.error, fc.alert_after
                )
                if should_alert and fc.ops_chat_id and self.telegram is not None:
                    try:
                        await self.telegram.send_text(
                            fc.ops_chat_id,
                            f"🚨 <b>{name}</b> failing: {result.error}",
                        )
                    except Exception:  # noqa: BLE001
                        logger.exception("ops_alert_send_failed", feed=name)

        result.duration_ms = int((time.monotonic() - started) * 1000)
        logger.info(
            "feed_run",
            feed=name,
            fetched=result.fetched,
            after_dedup=result.after_dedup,
            sent=result.sent,
            dropped=result.dropped,
            overflow=result.overflow,
            duration_ms=result.duration_ms,
            dry_run=dry_run,
            error=result.error,
        )
        return result

    async def _fetch_all(self, feed: FeedConfig) -> list[Item]:
        ctx = FetchContext(feed_name=feed.name, http=self.http, state=self.state)
        out: list[Item] = []
        for spec in feed.sources:
            try:
                source = build_source(spec)
                items = await source.fetch(ctx)
                out.extend(items)
            except Exception as exc:
                logger.warning(
                    "source_failed",
                    feed=feed.name,
                    source=spec.get("type"),
                    err=str(exc),
                )
        return out

    async def _run_stage(
        self,
        feed: FeedConfig,
        stage: StageSpec,
        items: list[Item],
        llm: LLMProvider,
        intro: str,
        result: RunResult,
    ) -> tuple[list[Item], str]:
        name = stage.name
        params = stage.params

        if name == "dedup":
            # Already deduped against state; this is a within-batch dedup by hash.
            seen: set[str] = set()
            unique: list[Item] = []
            for i in items:
                key = i.canonical_url or i.title
                if key in seen:
                    continue
                seen.add(key)
                unique.append(i)
            return unique, intro

        if name == "rank":
            kept, dropped = await rank_stage(
                feed.name,
                items,
                llm,
                prompt=params.get("prompt", ""),
                min_relevance=float(params.get("min_relevance", 0.5)),
            )
            result.dropped += len(dropped)
            return kept, intro

        if name == "summarize":
            return await summarize_stage(
                feed.name, items, llm, prompt=params.get("prompt", "")
            ), intro

        if name == "digest":
            base = params.get("intro", "")
            llm_prompt = params.get("prompt")
            if llm_prompt:
                base = await digest_intro(feed.name, items, llm, prompt=llm_prompt)
            return items, base

        logger.warning("unknown_stage", stage=name, feed=feed.name)
        return items, intro
