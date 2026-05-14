from __future__ import annotations

import asyncio
import contextlib
import dataclasses
import os
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, ClassVar

import httpx

from glean.config.llm import LLMConfig
from glean.config.schema import Config, FeedConfig, RenderConfig, StageSpec
from glean.llm import build_provider
from glean.llm.base import LLMProvider
from glean.logging import get_logger
from glean.pipeline.stages import (
    apply_skill_stage,
    dedup_stage,
    digest_intro,
    rank_stage,
    summarize_stage,
)
from glean.sinks import SendContext, Sink, build_sink
from glean.sources import FetchContext, build_source
from glean.sources.base import Item
from glean.telegram import TelegramSender, render_digest

if TYPE_CHECKING:
    from glean.state import StateStore

logger = get_logger(__name__)


def _llm_key(cfg: LLMConfig) -> str:
    """Stable string key for the LLM cache, also used as Item.llm_key."""
    return f"{cfg.provider}:{cfg.model}:{cfg.base_url or ''}"


class _InjectedTelegramSink:
    type: ClassVar[str] = "telegram"

    def __init__(
        self,
        sender: TelegramSender,
        chat_id: str | int,
        *,
        required: bool = True,
    ) -> None:
        self._sender = sender
        self.chat_id = chat_id
        self.required = required

    async def send(self, ctx: SendContext) -> None:
        await self._sender.send_digest(
            self.chat_id,
            ctx.messages,
            style=ctx.render.style,
            link_preview=ctx.render.link_preview,
        )

    async def aclose(self) -> None:
        pass


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
        telegram: TelegramSender | None = None,
        http: httpx.AsyncClient | None = None,
    ) -> None:
        self.config = config
        self.state = state
        self.telegram = telegram
        self.http = http or httpx.AsyncClient(timeout=30.0)
        self._owns_http = http is None
        self._llm_cache: dict[str, LLMProvider] = {}
        self._sinks_cache: dict[str, list[Sink]] = {}

    async def aclose(self) -> None:
        for sink_list in self._sinks_cache.values():
            for sink in sink_list:
                with contextlib.suppress(Exception):
                    await sink.aclose()
        for provider in self._llm_cache.values():
            with contextlib.suppress(Exception):
                await provider.aclose()
        if self._owns_http:
            await self.http.aclose()
        if self.telegram is not None:
            await self.telegram.aclose()

    def _get_llm(self, feed: FeedConfig) -> LLMProvider:
        cfg = feed.effective_llm(self.config.defaults)
        return self._get_llm_from_config(cfg)

    def _get_llm_from_config(self, cfg: LLMConfig) -> LLMProvider:
        key = _llm_key(cfg)
        if key not in self._llm_cache:
            self._llm_cache[key] = build_provider(cfg.model_dump(exclude_none=True))
        return self._llm_cache[key]

    def _llm_resolver(self, feed: FeedConfig) -> Callable[[Item], LLMProvider]:
        """Return a per-item LLM resolver. Falls back to feed default if item.llm_key missing."""
        default = self._get_llm(feed)
        has_overrides = any("llm" in spec for spec in feed.sources)
        if not has_overrides:
            return lambda _item: default

        def resolver(item: Item) -> LLMProvider:
            if item.llm_key and item.llm_key in self._llm_cache:
                return self._llm_cache[item.llm_key]
            return default

        return resolver

    def _build_sinks_for(self, feed: FeedConfig) -> list[Sink]:
        """Build (and cache) the list of sinks for a feed."""
        if feed.name in self._sinks_cache:
            return self._sinks_cache[feed.name]

        sinks: list[Sink] = []
        for spec in feed.effective_sinks(self.config.defaults):
            if self._can_use_injected_telegram(spec):
                chat_id = spec.get("chat_id", feed.chat_id)
                if chat_id is None:
                    raise RuntimeError("telegram sink missing chat_id")
                required = spec.get("required", True)
                if not isinstance(required, bool):
                    raise ValueError("telegram sink 'required' must be a boolean")
                telegram = self.telegram
                if telegram is None:
                    raise RuntimeError("telegram sender not configured")
                sinks.append(_InjectedTelegramSink(telegram, chat_id, required=required))
            else:
                sinks.append(build_sink(spec))

        self._sinks_cache[feed.name] = sinks
        return sinks

    def _can_use_injected_telegram(self, spec: dict[str, object]) -> bool:
        # Token, base URL, or unknown Telegram options need the real plugin constructor.
        return (
            self.telegram is not None
            and spec.get("type") == "telegram"
            and "token" not in spec
            and not os.environ.get("TELEGRAM_BASE_URL")
            and set(spec) <= {"type", "chat_id", "required"}
        )

    async def _dispatch_sinks(
        self,
        feed: FeedConfig,
        items: list[Item],
        messages: list[str],
        intro: str,
        render_cfg: RenderConfig,
    ) -> None:
        """Send to all configured sinks. Required failures raise; optional just log."""
        sinks = self._build_sinks_for(feed)
        if not sinks:
            if self.telegram is None:
                raise RuntimeError("feed has no sinks and no telegram sender configured")
            if feed.chat_id is None:
                raise RuntimeError("feed has no sinks and no chat_id configured")
            await self.telegram.send_digest(
                feed.chat_id,
                messages,
                style=render_cfg.style,
                link_preview=render_cfg.link_preview,
            )
            return

        ctx = SendContext(
            feed=feed.name,
            items=items,
            messages=messages,
            intro=intro,
            render=render_cfg,
        )
        results = await asyncio.gather(
            *(sink.send(ctx) for sink in sinks),
            return_exceptions=True,
        )

        required_errors: list[str] = []
        for sink, result in zip(sinks, results, strict=True):
            if isinstance(result, BaseException):
                if not isinstance(result, Exception):
                    raise result
                err = f"{type(result).__name__}: {result}"
                if sink.required:
                    logger.error("sink_failed", feed=feed.name, sink=sink.type, err=err)
                    required_errors.append(f"{sink.type}: {err}")
                else:
                    logger.warning(
                        "sink_failed_optional", feed=feed.name, sink=sink.type, err=err
                    )

        if required_errors:
            raise RuntimeError(f"required sinks failed: {'; '.join(required_errors)}")

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

            default_llm = self._get_llm(feed)
            llm_for = self._llm_resolver(feed)
            intro: str = ""

            for stage in feed.pipeline:
                new_items, intro = await self._run_stage(
                    feed, stage, new_items, llm_for, default_llm, intro, result
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
                await self._dispatch_sinks(feed, new_items, messages, intro, render_cfg)
                await self.state.mark_seen(name, new_items, sent=True)
                await self.state.set_bootstrapped(name)
                recovery = await self.state.record_success(name)
                if recovery:
                    fc = feed.effective_failure(self.config.defaults)
                    if fc.ops_chat_id and self.telegram is not None:
                        await self.telegram.send_text(
                            fc.ops_chat_id, f"✅ <b>{name}</b> recovered."
                        )
                    elif fc.ops_chat_id:
                        logger.warning(
                            "recovery_alert_skipped", feed=name, reason="telegram_missing"
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
                if llm_spec := spec.get("llm"):
                    cfg = LLMConfig.model_validate(llm_spec)
                    key = _llm_key(cfg)
                    self._get_llm_from_config(cfg)
                    items = [dataclasses.replace(item, llm_key=key) for item in items]
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
        llm_for: Callable[[Item], LLMProvider],
        default_llm: LLMProvider,
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
                llm_for,
                prompt=params.get("prompt", ""),
                min_relevance=float(params.get("min_relevance", 0.5)),
            )
            result.dropped += len(dropped)
            return kept, intro

        if name == "summarize":
            return await summarize_stage(
                feed.name, items, llm_for, prompt=params.get("prompt", "")
            ), intro

        if name == "digest":
            base = params.get("intro", "")
            llm_prompt = params.get("prompt")
            if llm_prompt:
                base = await digest_intro(feed.name, items, default_llm, prompt=llm_prompt)
            return items, base

        if name == "apply_skill":
            return await self._run_apply_skill_stage(feed, stage, items, llm_for, intro)

        logger.warning("unknown_stage", stage=name, feed=feed.name)
        return items, intro

    async def _run_apply_skill_stage(
        self,
        feed: FeedConfig,
        stage: StageSpec,
        items: list[Item],
        llm_for: Callable[[Item], LLMProvider],
        intro: str,
    ) -> tuple[list[Item], str]:
        params = stage.params
        skill_name = params.get("skill")
        if not skill_name:
            logger.warning("apply_skill_missing_skill_param", feed=feed.name)
            return items, intro
        try:
            skill = self.config.skill(skill_name)
        except KeyError:
            logger.warning(
                "apply_skill_unknown_skill",
                feed=feed.name,
                skill=skill_name,
            )
            return items, intro
        skill_llm: LLMProvider | None = None
        if skill.llm:
            skill_llm = self._get_llm_from_config(skill.llm)
        new_items = await apply_skill_stage(
            feed.name,
            items,
            llm_for,
            skill=skill,
            skill_llm=skill_llm,
        )
        return new_items, intro
