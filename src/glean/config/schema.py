from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class LLMConfig(BaseModel):
    # Plugins may register additional providers, so we accept any string here
    # and defer validation to the registry at construction time.
    model_config = ConfigDict(extra="forbid")

    provider: str = "ollama"
    model: str = "qwen2.5:7b"
    base_url: str | None = None
    api_key: str | None = None
    timeout_s: float = 60.0


class RenderConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    style: Literal["html", "markdown_v2", "plain"] = "html"
    link_preview: bool = False
    max_items: int = Field(default=10, ge=1, le=50)


class FailureConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    alert_after: int = Field(default=3, ge=1)
    ops_chat_id: str | int | None = None


class Defaults(BaseModel):
    model_config = ConfigDict(extra="forbid")

    llm: LLMConfig = Field(default_factory=LLMConfig)
    render: RenderConfig = Field(default_factory=RenderConfig)
    bootstrap: Literal["skip-and-mark", "send-last-N", "send-all"] = "skip-and-mark"
    bootstrap_count: int = Field(default=5, ge=1)
    failure: FailureConfig = Field(default_factory=FailureConfig)


StageName = Literal["dedup", "rank", "summarize", "digest"]


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
    chat_id: str | int
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

    def effective_llm(self, defaults: Defaults) -> LLMConfig:
        return self.llm or defaults.llm

    def effective_render(self, defaults: Defaults) -> RenderConfig:
        return self.render or defaults.render

    def effective_bootstrap(self, defaults: Defaults) -> str:
        return self.bootstrap or defaults.bootstrap

    def effective_bootstrap_count(self, defaults: Defaults) -> int:
        return self.bootstrap_count or defaults.bootstrap_count

    def effective_failure(self, defaults: Defaults) -> FailureConfig:
        return self.failure or defaults.failure


class Config(BaseModel):
    model_config = ConfigDict(extra="forbid")

    defaults: Defaults = Field(default_factory=Defaults)
    feeds: list[FeedConfig] = Field(min_length=1)

    @field_validator("feeds")
    @classmethod
    def _unique_names(cls, v: list[FeedConfig]) -> list[FeedConfig]:
        seen: set[str] = set()
        for f in v:
            if f.name in seen:
                raise ValueError(f"duplicate feed name: {f.name!r}")
            seen.add(f.name)
        return v

    def feed(self, name: str) -> FeedConfig:
        for f in self.feeds:
            if f.name == name:
                return f
        raise KeyError(f"no such feed: {name!r}")
