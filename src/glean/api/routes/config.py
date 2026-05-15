"""REST API routes for config CRUD."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Body, HTTPException, status
from pydantic import ValidationError

from glean.api.models import FeedListResponse, ValidateResponse, WriteResponse
from glean.api_service.config_service import write_config
from glean.config import Config, load_config
from glean.config.loader import ConfigError
from glean.config.schema import Defaults, FeedConfig
from glean.config.skills import SkillConfig
from glean.security.scrub import scrub

router = APIRouter(prefix="/config", tags=["config"])


def _config_path() -> Path:
    """Resolve the config path from env or default container path."""
    return Path(os.environ.get("GLEAN_CONFIG", "/etc/glean/feeds.yaml"))


def _load_or_400() -> Config:
    try:
        return load_config(_config_path())
    except ConfigError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"config load error: {scrub(str(exc))[:500]}",
        ) from exc


def _ensure_valid_for_write(cfg: Config) -> Config:
    try:
        return cfg.ensure_effective_sinks()
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=scrub(str(exc))[:500],
        ) from exc


# --- Defaults ---


@router.get("/defaults", response_model=Defaults)
async def get_defaults() -> Defaults:
    cfg = _load_or_400()
    return cfg.defaults


@router.put("/defaults", response_model=WriteResponse)
async def put_defaults(
    defaults: Defaults = Body(...),  # noqa: B008
) -> WriteResponse:
    cfg = _load_or_400()
    new_cfg = _ensure_valid_for_write(cfg.model_copy(update={"defaults": defaults}))
    write_config(new_cfg, _config_path())
    return WriteResponse(ok=True, message="defaults updated")


# --- Feeds ---


def _sinks_count(feed: FeedConfig, defaults: Defaults) -> int:
    try:
        return len(feed.effective_sinks(defaults))
    except ValueError:
        return 0


@router.get("/feeds", response_model=list[FeedListResponse])
async def list_feeds() -> list[FeedListResponse]:
    cfg = _load_or_400()
    return [
        FeedListResponse(
            name=f.name,
            schedule=f.schedule,
            sources_count=len(f.sources),
            pipeline_stages=[s.name for s in f.pipeline],
            sinks_count=_sinks_count(f, cfg.defaults),
        )
        for f in cfg.feeds
    ]


@router.get("/feeds/{name}", response_model=FeedConfig)
async def get_feed(name: str) -> FeedConfig:
    cfg = _load_or_400()
    try:
        return cfg.feed(name)
    except KeyError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"no such feed: {name!r}",
        ) from exc


@router.post("/feeds", response_model=WriteResponse, status_code=status.HTTP_201_CREATED)
async def create_feed(feed: FeedConfig = Body(...)) -> WriteResponse:  # noqa: B008
    cfg = _load_or_400()
    if any(f.name == feed.name for f in cfg.feeds):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"feed {feed.name!r} already exists",
        )
    new_cfg = _ensure_valid_for_write(cfg.model_copy(update={"feeds": [*cfg.feeds, feed]}))
    write_config(new_cfg, _config_path())
    return WriteResponse(ok=True, message=f"feed {feed.name!r} created")


@router.put("/feeds/{name}", response_model=WriteResponse)
async def update_feed(name: str, feed: FeedConfig = Body(...)) -> WriteResponse:  # noqa: B008
    if feed.name != name:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"feed name mismatch: path={name!r}, body={feed.name!r}",
        )
    cfg = _load_or_400()
    if not any(f.name == name for f in cfg.feeds):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"no such feed: {name!r}",
        )
    new_feeds = [feed if f.name == name else f for f in cfg.feeds]
    new_cfg = _ensure_valid_for_write(cfg.model_copy(update={"feeds": new_feeds}))
    write_config(new_cfg, _config_path())
    return WriteResponse(ok=True, message=f"feed {name!r} updated")


@router.delete("/feeds/{name}", response_model=WriteResponse)
async def delete_feed(name: str) -> WriteResponse:
    cfg = _load_or_400()
    if not any(f.name == name for f in cfg.feeds):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"no such feed: {name!r}",
        )
    new_feeds = [f for f in cfg.feeds if f.name != name]
    new_cfg = _ensure_valid_for_write(cfg.model_copy(update={"feeds": new_feeds}))
    write_config(new_cfg, _config_path())
    return WriteResponse(ok=True, message=f"feed {name!r} deleted")


# --- Skills ---


@router.get("/skills", response_model=list[SkillConfig])
async def list_skills() -> list[SkillConfig]:
    cfg = _load_or_400()
    return list(cfg.skills)


@router.get("/skills/{name}", response_model=SkillConfig)
async def get_skill(name: str) -> SkillConfig:
    cfg = _load_or_400()
    try:
        return cfg.skill(name)
    except KeyError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"no such skill: {name!r}",
        ) from exc


@router.post("/skills", response_model=WriteResponse, status_code=status.HTTP_201_CREATED)
async def create_skill(skill: SkillConfig = Body(...)) -> WriteResponse:  # noqa: B008
    cfg = _load_or_400()
    if any(s.name == skill.name for s in cfg.skills):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"skill {skill.name!r} already exists",
        )
    new_cfg = cfg.model_copy(update={"skills": [*cfg.skills, skill]})
    write_config(new_cfg, _config_path())
    return WriteResponse(ok=True, message=f"skill {skill.name!r} created")


@router.put("/skills/{name}", response_model=WriteResponse)
async def update_skill(
    name: str,
    skill: SkillConfig = Body(...),  # noqa: B008
) -> WriteResponse:
    if skill.name != name:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"skill name mismatch: path={name!r}, body={skill.name!r}",
        )
    cfg = _load_or_400()
    if not any(s.name == name for s in cfg.skills):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"no such skill: {name!r}",
        )
    new_skills = [skill if s.name == name else s for s in cfg.skills]
    new_cfg = cfg.model_copy(update={"skills": new_skills})
    write_config(new_cfg, _config_path())
    return WriteResponse(ok=True, message=f"skill {name!r} updated")


@router.delete("/skills/{name}", response_model=WriteResponse)
async def delete_skill(name: str) -> WriteResponse:
    cfg = _load_or_400()
    if not any(s.name == name for s in cfg.skills):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"no such skill: {name!r}",
        )
    new_skills = [s for s in cfg.skills if s.name != name]
    new_cfg = cfg.model_copy(update={"skills": new_skills})
    write_config(new_cfg, _config_path())
    return WriteResponse(ok=True, message=f"skill {name!r} deleted")


# --- Validate ---


@router.post("/validate", response_model=ValidateResponse)
async def validate_config_endpoint(
    body: dict[str, Any] | None = Body(default=None),  # noqa: B008
) -> ValidateResponse:
    """Validate a config dict, or the current on-disk config if no body is sent."""
    if body is None:
        try:
            cfg = load_config(_config_path())
        except ConfigError as exc:
            return ValidateResponse(
                valid=False,
                feeds_count=0,
                skills_count=0,
                errors=[scrub(str(exc))[:500]],
            )
    else:
        try:
            cfg = Config.model_validate(body)
        except ValidationError as exc:
            return ValidateResponse(
                valid=False,
                feeds_count=0,
                skills_count=0,
                errors=[str(e) for e in exc.errors()],
            )
    return ValidateResponse(
        valid=True,
        feeds_count=len(cfg.feeds),
        skills_count=len(cfg.skills),
        errors=[],
    )
