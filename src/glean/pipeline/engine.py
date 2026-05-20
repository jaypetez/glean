from __future__ import annotations

import asyncio
import contextlib
import dataclasses
import datetime as dt
import html
import os
import secrets
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, ClassVar, Literal, cast

import httpx
from structlog.contextvars import bind_contextvars, reset_contextvars

from glean.config.llm import LLMConfig
from glean.config.schema import Config, FeedConfig, RenderConfig, StageSpec
from glean.llm import EmbeddingProvider, build_embedding_provider, build_provider
from glean.llm.base import LLMProvider
from glean.logging import get_logger
from glean.pipeline.stages import (
    LLMCallCounter,
    apply_skill_stage,
    dedup_stage,
    digest_intro,
    rank_stage,
    semantic_dedup_stage,
    summarize_stage,
)
from glean.security.scrub import scrub
from glean.security.ssrf_transport import SSRFGuardedTransport, outbound_timeout
from glean.sinks import SendContext, Sink, build_sink
from glean.sources import FetchContext, build_source
from glean.sources.base import Item
from glean.telegram import TelegramSender, render_digest

if TYPE_CHECKING:
    from glean.api.events import EventBus
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
    suppressed_semantic: int = 0
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
        *,
        close_telegram: bool = True,
        event_bus: EventBus | None = None,
    ) -> None:
        self.config = config
        self.state = state
        self.telegram = telegram
        timeout = outbound_timeout()
        self.http = http or httpx.AsyncClient(
            timeout=timeout,
            follow_redirects=False,
            max_redirects=0,
            transport=SSRFGuardedTransport(allow_private=False),
        )
        self._owns_http = http is None
        self._close_telegram = close_telegram
        self._event_bus = event_bus
        self._logger = get_logger(__name__)
        self._llm_cache: dict[str, LLMProvider] = {}
        self._embedding_cache: dict[str, tuple[EmbeddingProvider, str]] = {}
        self._sinks_cache: dict[str, list[Sink]] = {}

    async def aclose(self) -> None:
        for sink_list in self._sinks_cache.values():
            for sink in sink_list:
                with contextlib.suppress(Exception):
                    await sink.aclose()
        for provider in self._llm_cache.values():
            with contextlib.suppress(Exception):
                await provider.aclose()
        for embedding_provider, _model_name in self._embedding_cache.values():
            with contextlib.suppress(Exception):
                await embedding_provider.aclose()
        if self._owns_http:
            await self.http.aclose()
        if self._close_telegram and self.telegram is not None:
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

    def _semantic_dedup_embedding_spec(
        self,
        feed: FeedConfig,
        stage: StageSpec,
    ) -> tuple[dict[str, Any], str]:
        cfg = feed.effective_llm(self.config.defaults)
        model_name = str(stage.params.get("embedding_model") or cfg.model)
        spec = cfg.model_dump(exclude_none=True)
        spec["model"] = model_name
        return spec, model_name

    def _get_embedding_provider(
        self,
        feed: FeedConfig,
        stage: StageSpec,
    ) -> tuple[EmbeddingProvider, str]:
        spec, model_name = self._semantic_dedup_embedding_spec(feed, stage)
        cache_key = f"{feed.name}:{spec['provider']}:{model_name}:{spec.get('base_url', '')}"
        if cache_key not in self._embedding_cache:
            self._embedding_cache[cache_key] = (build_embedding_provider(spec), model_name)
        return self._embedding_cache[cache_key]

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
            state=self.state,
            event_bus=self._event_bus,
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
                err = f"{type(result).__name__}: {scrub(str(result))[:500]}"
                if sink.required:
                    logger.error("sink_failed", feed=feed.name, sink=sink.type, err=err)
                    required_errors.append(f"{sink.type}: {err}")
                else:
                    logger.warning("sink_failed_optional", feed=feed.name, sink=sink.type, err=err)

        if required_errors:
            raise RuntimeError(f"required sinks failed: {'; '.join(required_errors)}")

    async def _emit(self, **kwargs: Any) -> None:
        if self._event_bus is None:
            return
        from glean.api.events import RunEvent  # noqa: PLC0415

        try:
            await self._event_bus.publish(RunEvent(**kwargs))
        except Exception:
            logger.exception("event_publish_failed", **kwargs)

    async def _finalize_run_result(
        self,
        result: RunResult,
        started: float,
        *,
        dry_run: bool,
    ) -> RunResult:
        result.duration_ms = int((time.monotonic() - started) * 1000)
        if result.error is None:
            await self._emit(
                type="run_completed",
                feed=result.feed,
                fetched=result.fetched,
                after_dedup=result.after_dedup,
                sent=result.sent,
                duration_ms=result.duration_ms,
            )
        else:
            await self._emit(
                type="run_failed",
                feed=result.feed,
                error=result.error,
                duration_ms=result.duration_ms,
            )
        logger.info(
            "feed_run",
            feed=result.feed,
            fetched=result.fetched,
            after_dedup=result.after_dedup,
            sent=result.sent,
            dropped=result.dropped,
            overflow=result.overflow,
            suppressed_semantic=result.suppressed_semantic,
            duration_ms=result.duration_ms,
            dry_run=dry_run,
            error=result.error,
        )
        return result

    async def run_feed(self, name: str, *, dry_run: bool = False) -> RunResult:
        # AGENT: This is the heart of glean. Read docs/agents/key-files.md before editing.
        # Stage order is YAML-driven (feed.pipeline) — never hardcode it here.
        trace_id = secrets.token_hex(4)
        context_tokens = bind_contextvars(feed=name, trace_id=trace_id)
        log = self._logger.bind(feed=name, trace_id=trace_id)
        started = time.monotonic()
        started_at = dt.datetime.now(dt.UTC)
        feed = self.config.feed(name)
        result = RunResult(feed=name)
        bootstrap_skipped = False

        async def finalize() -> RunResult:
            finalized = await self._finalize_run_result(result, started, dry_run=dry_run)
            run_status: Literal["success", "failure", "skip"]
            if finalized.error is not None:
                run_status = "failure"
            elif bootstrap_skipped or (finalized.sent == 0 and finalized.fetched == 0):
                run_status = "skip"
            else:
                run_status = "success"
            try:
                await self.state.record_run_history(
                    feed_name=name,
                    started_at=started_at,
                    duration_ms=finalized.duration_ms,
                    status=run_status,
                    fetched=finalized.fetched,
                    after_dedup=finalized.after_dedup,
                    dropped=finalized.dropped,
                    sent=finalized.sent,
                    overflow=finalized.overflow,
                    error=finalized.error,
                    trace_id=trace_id,
                    dry_run=dry_run,
                )
            except Exception as exc:
                log.warning(
                    "run_history_record_failed",
                    err_type=type(exc).__name__,
                    err=scrub(str(exc))[:200] or "(no message)",
                )
            if finalized.error is None:
                log.info(
                    "run_feed.complete",
                    duration_ms=finalized.duration_ms,
                    sent=finalized.sent,
                    suppressed_semantic=finalized.suppressed_semantic,
                )
            return finalized

        try:
            log.info("run_feed.start", dry_run=dry_run)
            try:
                await self._emit(type="run_started", feed=name)
                items = await self._fetch_all(feed)
                result.fetched = len(items)

                bootstrap_mode = feed.effective_bootstrap(self.config.defaults)
                bootstrapped = await self.state.is_bootstrapped(name)

                if not bootstrapped and bootstrap_mode == "skip-and-mark":
                    if not dry_run:
                        await self.state.mark_seen(name, items, sent=True)
                        await self.state.set_bootstrapped(name)
                        await self.state.record_success(name)
                    bootstrap_skipped = True
                    result.skipped_reason = "bootstrap"
                    result.after_dedup = 0
                    log.info("bootstrap_skip", indexed=len(items), dry_run=dry_run)
                    return await finalize()

                # Run pipeline stages
                new_items = await dedup_stage(name, items, self.state)
                result.after_dedup = len(new_items)
                if not new_items:
                    if not dry_run:
                        await self.state.record_success(name)
                    log.info("no_new_items")
                    return await finalize()

                default_llm = self._get_llm(feed)
                llm_for = self._llm_resolver(feed)
                llm_counter = LLMCallCounter(
                    feed.effective_max_llm_calls_per_run(self.config.defaults)
                )
                intro: str = ""
                semantic_embedding_model_name: str | None = None

                for stage in feed.pipeline:
                    new_items, intro, stage_embedding_model_name = await self._run_stage(
                        feed,
                        stage,
                        new_items,
                        llm_for,
                        default_llm,
                        llm_counter,
                        intro,
                        trace_id,
                        result,
                    )
                    if stage_embedding_model_name is not None:
                        semantic_embedding_model_name = stage_embedding_model_name
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
                    log.info("nothing_to_send")
                    return await finalize()

                messages = render_digest(
                    new_items,
                    intro=intro,
                    render=render_cfg,
                    overflow_count=result.overflow,
                )
                result.messages = messages

                if dry_run:
                    log.info("dry_run", would_send=len(messages), items=ranked_count)
                else:
                    await self._dispatch_sinks(feed, new_items, messages, intro, render_cfg)
                    await self._mark_seen(
                        name,
                        new_items,
                        sent=True,
                        embedding_model=semantic_embedding_model_name,
                    )
                    await self.state.set_bootstrapped(name)
                    recovery = await self.state.record_success(name)
                    if recovery:
                        fc = feed.effective_failure(self.config.defaults)
                        if fc.ops_chat_id and self.telegram is not None:
                            await self.telegram.send_text(
                                fc.ops_chat_id, f"✅ <b>{name}</b> recovered."
                            )
                        elif fc.ops_chat_id:
                            log.warning("recovery_alert_skipped", reason="telegram_missing")
                    result.sent = len(new_items)

            except Exception as exc:
                result.error = f"{type(exc).__name__}: {scrub(str(exc))[:500]}"
                log.exception("run_feed.failed", error=str(exc), err=result.error)
                if not dry_run:
                    fc = feed.effective_failure(self.config.defaults)
                    _, should_alert = await self.state.record_failure(
                        name, result.error, fc.alert_after
                    )
                    if should_alert and fc.ops_chat_id and self.telegram is not None:
                        try:
                            alert_error = html.escape(result.error)
                            await self.telegram.send_text(
                                fc.ops_chat_id,
                                f"🚨 <b>{html.escape(name)}</b> failing: {alert_error}",
                            )
                        except Exception:
                            log.exception("ops_alert_send_failed")

            return await finalize()
        finally:
            reset_contextvars(**context_tokens)

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
                    err=scrub(str(exc))[:500],
                )
        return out

    async def _mark_seen(
        self,
        feed_name: str,
        items: list[Item],
        *,
        sent: bool,
        embedding_model: str | None,
    ) -> None:
        kwargs: dict[str, Any] = {"sent": sent}
        if embedding_model is not None:
            kwargs["embedding_model"] = embedding_model
        await self.state.mark_seen(feed_name, items, **kwargs)

    async def _run_stage(
        self,
        feed: FeedConfig,
        stage: StageSpec,
        items: list[Item],
        llm_for: Callable[[Item], LLMProvider],
        default_llm: LLMProvider,
        llm_counter: LLMCallCounter,
        intro: str,
        trace_id: str,
        result: RunResult,
    ) -> tuple[list[Item], str, str | None]:
        name = stage.name
        params = stage.params
        next_items = items
        next_intro = intro
        embedding_model_name: str | None = None

        if name == "dedup":
            # Already deduped against state; this is a within-batch dedup by hash.
            seen: set[str] = set()
            unique: list[Item] = []
            for item in items:
                key = item.canonical_url or item.title
                if key in seen:
                    continue
                seen.add(key)
                unique.append(item)
            next_items = unique
        elif name == "rank":
            kept, dropped = await rank_stage(
                feed.name,
                items,
                llm_for,
                prompt=params.get("prompt", ""),
                min_relevance=float(params.get("min_relevance", 0.5)),
                llm_counter=llm_counter,
            )
            result.dropped += len(dropped)
            next_items = kept
        elif name == "summarize":
            next_items = await summarize_stage(
                feed.name,
                items,
                llm_for,
                prompt=params.get("prompt", ""),
                llm_counter=llm_counter,
            )
        elif name == "digest":
            base = params.get("intro", "")
            llm_prompt = params.get("prompt")
            if llm_prompt:
                base = await digest_intro(
                    feed.name,
                    items,
                    default_llm,
                    prompt=llm_prompt,
                    llm_counter=llm_counter,
                )
            next_intro = base
        elif name == "semantic_dedup":
            next_items, next_intro, embedding_model_name = await self._run_semantic_dedup_stage(
                feed,
                stage,
                items,
                llm_counter,
                intro,
                trace_id,
                result,
            )
        elif name == "apply_skill":
            next_items, next_intro, embedding_model_name = await self._run_apply_skill_stage(
                feed,
                stage,
                items,
                llm_for,
                llm_counter,
                intro,
            )
        else:
            logger.warning("unknown_stage", stage=name, feed=feed.name)

        return next_items, next_intro, embedding_model_name

    async def _run_semantic_dedup_stage(
        self,
        feed: FeedConfig,
        stage: StageSpec,
        items: list[Item],
        llm_counter: LLMCallCounter,
        intro: str,
        trace_id: str,
        result: RunResult,
    ) -> tuple[list[Item], str, str | None]:
        try:
            provider, embedding_model_name = self._get_embedding_provider(feed, stage)
        except Exception as exc:
            logger.warning(
                "semantic_dedup_provider_failed",
                feed=feed.name,
                err_type=type(exc).__name__,
                err=scrub(str(exc))[:500] or "(no message)",
            )
            return items, intro, None

        kept, suppressed_records = await semantic_dedup_stage(
            feed.name,
            items,
            provider,
            self.state,
            min_similarity=cast(float, stage.params["min_similarity"]),
            window=cast(dt.timedelta, stage.params["window"]),
            embedding_model_name=embedding_model_name,
            trace_id=trace_id,
            llm_counter=llm_counter,
        )
        result.suppressed_semantic += len(suppressed_records)

        for record in suppressed_records:
            try:
                await self.state.log_suppression(
                    feed_name=feed.name,
                    suppressed_url=record.suppressed_url,
                    suppressed_title=record.suppressed_title,
                    matched_url=record.matched_url,
                    matched_title=record.matched_title,
                    similarity=record.similarity,
                    trace_id=trace_id,
                )
            except Exception as exc:
                logger.warning(
                    "semantic_dedup_log_write_failed",
                    feed=feed.name,
                    suppressed_url=record.suppressed_url,
                    matched_url=record.matched_url,
                    err_type=type(exc).__name__,
                    err=scrub(str(exc))[:500] or "(no message)",
                )
        return kept, intro, embedding_model_name

    async def _run_apply_skill_stage(
        self,
        feed: FeedConfig,
        stage: StageSpec,
        items: list[Item],
        llm_for: Callable[[Item], LLMProvider],
        llm_counter: LLMCallCounter,
        intro: str,
    ) -> tuple[list[Item], str, str | None]:
        params = stage.params
        skill_name = params.get("skill")
        if not skill_name:
            logger.warning("apply_skill_missing_skill_param", feed=feed.name)
            return items, intro, None
        try:
            skill = self.config.skill(skill_name)
        except KeyError:
            logger.warning(
                "apply_skill_unknown_skill",
                feed=feed.name,
                skill=skill_name,
            )
            return items, intro, None
        skill_llm: LLMProvider | None = None
        if skill.llm:
            skill_llm = self._get_llm_from_config(skill.llm)
        new_items = await apply_skill_stage(
            feed.name,
            items,
            llm_for,
            skill=skill,
            skill_llm=skill_llm,
            llm_counter=llm_counter,
        )
        return new_items, intro, None
