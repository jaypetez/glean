"""System information routes."""
from __future__ import annotations

import datetime as dt
import os
import platform
import socket
import time
from pathlib import Path

from fastapi import APIRouter, Request

from glean import __version__
from glean.api.models import SystemInfoResponse
from glean.config import load_config
from glean.config.loader import ConfigError

router = APIRouter(prefix="/system", tags=["system"])


def _config_path() -> Path:
    return Path(os.environ.get("GLEAN_CONFIG", "/etc/glean/feeds.yaml"))


@router.get("/info", response_model=SystemInfoResponse)
async def info(request: Request) -> SystemInfoResponse:
    """Return runtime information for the About page."""
    started_at = float(request.app.state.glean_started_at)
    config_path = _config_path()
    feeds_count = 0
    llm_provider: str | None = None
    llm_model: str | None = None
    try:
        cfg = load_config(config_path)
    except ConfigError:
        cfg = None
    if cfg is not None:
        feeds_count = len(cfg.feeds)
        llm_provider = cfg.defaults.llm.provider
        llm_model = cfg.defaults.llm.model
    return SystemInfoResponse(
        version=__version__,
        hostname=socket.gethostname(),
        python=platform.python_version(),
        platform=platform.platform(),
        database_path=str(request.app.state.glean_db_path),
        config_path=str(config_path),
        feeds_count=feeds_count,
        uptime_seconds=time.time() - started_at,
        started_at=dt.datetime.fromtimestamp(started_at, tz=dt.UTC),
        llm_provider=llm_provider,
        llm_model=llm_model,
    )
