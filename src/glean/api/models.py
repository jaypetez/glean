"""API-layer Pydantic response models."""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict


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
