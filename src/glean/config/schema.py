from __future__ import annotations

from typing import Any, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from glean.config.skills import SkillConfig


class LLMConfig(BaseModel):
    # Plugins may register additional providers, so we accept any string here
    # and defer validation to the registry at construction time.
    model_config = ConfigDict(extra="forbid")

    provider: str = "ollama"
    model: str = "qwen2.5:7b"
    base_url: str | None = None
    api_key: str | None = None
    timeout_s: float = 60.0


SkillConfig.model_rebuild(_types_namespace={"LLMConfig": LLMConfig})


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
    def _ensure_sinks(self) -> Self:
        if self.sinks is not None:
            return self
        if self.chat_id is not None:
            self.sinks = [{"type": "telegram", "chat_id": self.chat_id}]
            return self
        raise ValueError("feed must have either 'chat_id' or 'sinks'")

    def effective_llm(self, defaults: Defaults) -> LLMConfig:
        return self.llm or defaults.llm

    def effective_render(self, defaults: Defaults) -> RenderConfig:
        return self.render or defaults.render

    def effective_sinks(self, defaults: Defaults) -> list[dict[str, Any]]:
        if self.sinks is None:
            raise ValueError("feed must have either 'chat_id' or 'sinks'")
        return self.sinks

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
    feeds: list[FeedConfig] = Field(min_length=1)

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
