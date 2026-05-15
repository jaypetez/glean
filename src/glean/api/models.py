"""API-layer Pydantic response models."""

from __future__ import annotations

import datetime as dt

from pydantic import BaseModel, ConfigDict, Field


class FeedListResponse(BaseModel):
    """List view of a feed (subset of FeedConfig)."""

    model_config = ConfigDict(extra="forbid")

    name: str
    schedule: str
    sources_count: int
    pipeline_stages: list[str]
    sinks_count: int


class ValidateResponse(BaseModel):
    """Result of a config validation request."""

    model_config = ConfigDict(extra="forbid")

    valid: bool
    feeds_count: int
    skills_count: int
    errors: list[str] = []


class WriteResponse(BaseModel):
    """Generic response for write endpoints."""

    model_config = ConfigDict(extra="forbid")

    ok: bool
    message: str | None = None


class FeedStatusResponse(BaseModel):
    """Status of a single feed (combines config + feed_runs row)."""

    model_config = ConfigDict(extra="forbid")

    name: str
    schedule: str
    llm_provider: str
    llm_model: str
    last_success_at: dt.datetime | None
    last_attempt_at: dt.datetime | None
    last_error: str | None
    consecutive_failures: int
    alert_active: bool
    bootstrapped: bool


class RunResultResponse(BaseModel):
    """Result of a feed run."""

    model_config = ConfigDict(extra="forbid")

    feed: str
    fetched: int
    after_dedup: int
    sent: int
    dropped: int
    overflow: int
    duration_ms: int
    error: str | None
    skipped_reason: str | None
    messages: list[str] = Field(default_factory=list)


class InitializeResponse(BaseModel):
    """First-load UI initialization payload."""

    model_config = ConfigDict(extra="forbid")

    version: str
    auth_disabled: bool


class RotateResponse(BaseModel):
    """One-time API key rotation response."""

    model_config = ConfigDict(extra="forbid")

    api_key: str


class EventTokenResponse(BaseModel):
    """Short-lived token for opening an authenticated EventSource stream."""

    model_config = ConfigDict(extra="forbid")

    token: str
    expires_in: int


class SystemInfoResponse(BaseModel):
    """Runtime system information for the About settings tab."""

    model_config = ConfigDict(extra="forbid")

    version: str
    hostname: str
    python: str
    platform: str
    database_path: str
    config_path: str
    feeds_count: int
    uptime_seconds: float
    started_at: dt.datetime
    llm_provider: str | None
    llm_model: str | None
