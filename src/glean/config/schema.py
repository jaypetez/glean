from __future__ import annotations

from typing import Any, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from glean.config.llm import LLMConfig
from glean.config.skills import SkillConfig
from glean.security.ssrf import SSRFValidationError, validate_url

_WEBHOOK_METHODS = {"POST", "PUT", "PATCH"}


def _validate_url_field(value: Any, *, field: str, allow_private: bool = False) -> None:
    if not isinstance(value, str) or not value:
        return
    try:
        validate_url(value, allow_private=allow_private)
    except SSRFValidationError as exc:
        raise ValueError(f"{field}: SSRF blocked: {exc}") from exc


def _validate_source_urls(spec: dict[str, Any], *, field: str) -> None:
    source_type = str(spec.get("type", "")).lower()
    if source_type == "rss":
        _validate_url_field(spec.get("url"), field=f"{field}.url")
        return
    if source_type == "scraper":
        urls = spec.get("urls")
        if isinstance(urls, list):
            for index, url in enumerate(urls):
                _validate_url_field(url, field=f"{field}.urls[{index}]")
        return
    if source_type != "search":
        return

    engine = str(spec.get("engine", "")).lower()
    allow_private = engine == "searxng" or "searxng_url" in spec
    _validate_url_field(
        spec.get("searxng_url"), field=f"{field}.searxng_url", allow_private=True
    )
    _validate_url_field(
        spec.get("base_url"), field=f"{field}.base_url", allow_private=allow_private
    )


def _validate_sink_urls(sinks: list[dict[str, Any]] | None, *, field: str) -> None:
    if sinks is None:
        return
    for index, spec in enumerate(sinks):
        sink_type = str(spec.get("type", "")).lower()
        prefix = f"{field}[{index}]"
        if sink_type == "webhook":
            _validate_url_field(spec.get("url"), field=f"{prefix}.url")
            method = str(spec.get("method", "POST")).upper()
            if method not in _WEBHOOK_METHODS:
                allowed = ", ".join(sorted(_WEBHOOK_METHODS))
                raise ValueError(f"{prefix}.method must be one of: {allowed}")
        elif sink_type == "discord":
            from glean.sinks.discord import (  # noqa: PLC0415
                validate_discord_avatar_url,
                validate_discord_webhook_url,
            )

            webhook_url = spec.get("webhook_url")
            if isinstance(webhook_url, str) and webhook_url:
                validate_discord_webhook_url(webhook_url)
            avatar_url = spec.get("avatar_url")
            if isinstance(avatar_url, str) and avatar_url:
                validate_discord_avatar_url(avatar_url)
        elif sink_type == "slack":
            from glean.sinks.slack import validate_slack_webhook_url  # noqa: PLC0415

            webhook_url = spec.get("webhook_url")
            if isinstance(webhook_url, str) and webhook_url:
                validate_slack_webhook_url(webhook_url)
        elif sink_type == "ntfy":
            from glean.sinks.ntfy import validate_ntfy_topic  # noqa: PLC0415

            topic = spec.get("topic")
            if isinstance(topic, str) and topic:
                validate_ntfy_topic(topic)
            _validate_url_field(spec.get("base_url"), field=f"{prefix}.base_url")
        elif sink_type == "telegram":
            _validate_url_field(spec.get("base_url"), field=f"{prefix}.base_url")
        elif sink_type == "file":
            from glean.sinks.file import validate_file_sink_path  # noqa: PLC0415

            path = spec.get("path")
            if isinstance(path, str) and path:
                validate_file_sink_path(path)


class RenderConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    style: Literal["html", "markdown_v2", "plain"] = "html"
    link_preview: bool = False
    max_items: int = Field(default=10, ge=1, le=50)


class FailureConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    alert_after: int = Field(default=3, ge=1)
    ops_chat_id: str | int | None = None


class TelegramDefaults(BaseModel):
    model_config = ConfigDict(extra="forbid")

    bot_token: str | None = None
    chat_id: str | int | None = None


class Defaults(BaseModel):
    model_config = ConfigDict(extra="forbid")

    telegram: TelegramDefaults = Field(default_factory=TelegramDefaults)
    llm: LLMConfig = Field(default_factory=LLMConfig)
    render: RenderConfig = Field(default_factory=RenderConfig)
    sinks: list[dict[str, Any]] | None = Field(default=None, min_length=1)
    bootstrap: Literal["skip-and-mark", "send-last-N", "send-all"] = "skip-and-mark"
    bootstrap_count: int = Field(default=5, ge=1)
    failure: FailureConfig = Field(default_factory=FailureConfig)

    @model_validator(mode="after")
    def _validate_default_sinks(self) -> Self:
        _validate_sink_urls(self.sinks, field="defaults.sinks")
        return self


StageName = Literal["dedup", "rank", "summarize", "digest", "apply_skill"]


class StageSpec(BaseModel):
    model_config = ConfigDict(extra="allow")

    name: StageName
    params: dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def from_raw(cls, raw: str | dict[str, Any]) -> StageSpec:
        if isinstance(raw, str):
            return cls(name=raw, params={})  # type: ignore[arg-type]
        if not isinstance(raw, dict) or len(raw) != 1:
            raise ValueError(f"stage must be a string or single-key mapping: {raw!r}")
        (name, params), = raw.items()
        if not isinstance(params, dict):
            params = {"value": params}
        return cls(name=name, params=params)  # type: ignore[arg-type]


class FeedConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, pattern=r"^[a-z0-9][a-z0-9._-]*$")
    schedule: str
    chat_id: str | int | None = None
    sinks: list[dict[str, Any]] | None = Field(default=None, min_length=1)
    sources: list[dict[str, Any]] = Field(min_length=1)
    pipeline: list[StageSpec] = Field(min_length=1)
    llm: LLMConfig | None = None
    render: RenderConfig | None = None
    bootstrap: Literal["skip-and-mark", "send-last-N", "send-all"] | None = None
    bootstrap_count: int | None = None
    failure: FailureConfig | None = None

    @field_validator("pipeline", mode="before")
    @classmethod
    def _normalize_pipeline(cls, v: Any) -> Any:
        if not isinstance(v, list):
            return v
        return [StageSpec.from_raw(x) if not isinstance(x, StageSpec) else x for x in v]

    @model_validator(mode="after")
    def _normalize_legacy_chat_id(self) -> Self:
        if self.sinks is None and self.chat_id is not None:
            self.sinks = [{"type": "telegram", "chat_id": self.chat_id}]
        return self

    @model_validator(mode="after")
    def _validate_url_specs(self) -> Self:
        for i, spec in enumerate(self.sources):
            try:
                _validate_source_urls(spec, field=f"sources[{i}]")
            except ValueError as exc:
                raise ValueError(str(exc)) from exc
        try:
            _validate_sink_urls(self.sinks, field="sinks")
        except ValueError as exc:
            raise ValueError(str(exc)) from exc
        return self

    @model_validator(mode="after")
    def _validate_source_llm_specs(self) -> Self:
        for i, spec in enumerate(self.sources):
            if "llm" in spec:
                try:
                    LLMConfig.model_validate(spec["llm"])
                except ValidationError as exc:
                    raise ValueError(f"sources[{i}].llm: {exc}") from exc
        return self

    def effective_llm(self, defaults: Defaults) -> LLMConfig:
        return self.llm or defaults.llm

    def effective_render(self, defaults: Defaults) -> RenderConfig:
        return self.render or defaults.render

    def effective_sinks(self, defaults: Defaults) -> list[dict[str, Any]]:
        if self.sinks is not None:
            return self.sinks
        if defaults.sinks is not None:
            return defaults.sinks
        if defaults.telegram.chat_id is not None:
            telegram_sink: dict[str, Any] = {
                "type": "telegram",
                "chat_id": defaults.telegram.chat_id,
            }
            if defaults.telegram.bot_token is not None:
                telegram_sink["token"] = defaults.telegram.bot_token
            return [telegram_sink]
        raise ValueError(
            "feed must have feed-level sinks/chat_id, defaults.sinks, or Telegram defaults"
        )

    def effective_bootstrap(self, defaults: Defaults) -> str:
        return self.bootstrap or defaults.bootstrap

    def effective_bootstrap_count(self, defaults: Defaults) -> int:
        return self.bootstrap_count or defaults.bootstrap_count

    def effective_failure(self, defaults: Defaults) -> FailureConfig:
        return self.failure or defaults.failure


class Config(BaseModel):
    model_config = ConfigDict(extra="forbid")

    defaults: Defaults = Field(default_factory=Defaults)
    skills: list[SkillConfig] = Field(default_factory=list)
    feeds: list[FeedConfig] = Field(default_factory=list)

    @field_validator("skills")
    @classmethod
    def _unique_skill_names(cls, v: list[SkillConfig]) -> list[SkillConfig]:
        seen: set[str] = set()
        for s in v:
            if s.name in seen:
                raise ValueError(f"duplicate skill name: {s.name!r}")
            seen.add(s.name)
        return v

    @field_validator("feeds")
    @classmethod
    def _unique_names(cls, v: list[FeedConfig]) -> list[FeedConfig]:
        seen: set[str] = set()
        for f in v:
            if f.name in seen:
                raise ValueError(f"duplicate feed name: {f.name!r}")
            seen.add(f.name)
        return v

    @model_validator(mode="after")
    def _validate_effective_sinks(self) -> Self:
        return self.ensure_effective_sinks()

    def ensure_effective_sinks(self) -> Self:
        for feed in self.feeds:
            try:
                feed.effective_sinks(self.defaults)
            except ValueError as exc:
                raise ValueError(f"feed {feed.name!r}: {exc}") from exc
        return self

    def skill(self, name: str) -> SkillConfig:
        for s in self.skills:
            if s.name == name:
                return s
        raise KeyError(f"no such skill: {name!r}")

    def feed(self, name: str) -> FeedConfig:
        for f in self.feeds:
            if f.name == name:
                return f
        raise KeyError(f"no such feed: {name!r}")
