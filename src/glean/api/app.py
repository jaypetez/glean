"""FastAPI application factory."""
from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING

from fastapi import APIRouter, Depends, FastAPI, HTTPException, status
from fastapi.staticfiles import StaticFiles

from glean import __version__
from glean.api.auth import auth_disabled, get_or_create_api_key, make_verify_api_key
from glean.api.routes.config import router as config_router
from glean.api.routes.feeds import router as feeds_router
from glean.logging import get_logger

if TYPE_CHECKING:
    import uvicorn

    from glean.state.store import StateStore

logger = get_logger(__name__)


def make_app(state: StateStore, db_path: Path) -> FastAPI:
    """Build the FastAPI app with all routes wired up.

    The ``state`` and ``db_path`` are stored on ``app.state`` so future routers
    can fetch them via ``request.app.state.glean_state``.
    """
    app = FastAPI(
        title="glean",
        version=__version__,
        description="Self-hosted content aggregation daemon — REST API",
        docs_url="/api/docs",
        redoc_url=None,
        openapi_url="/api/openapi.json",
    )

    api_key = get_or_create_api_key(db_path)
    app.state.glean_state = state
    app.state.glean_db_path = db_path
    app.state.glean_api_key = api_key
    verify = make_verify_api_key(api_key)

    health_router = APIRouter(tags=["health"])

    @health_router.get("/healthz")
    async def healthz() -> dict[str, str]:
        try:
            async with state.db.execute("SELECT 1") as cur:
                await cur.fetchone()
            return {"status": "ok"}
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="db error",
            ) from exc

    @health_router.get("/api/v1/initialize")
    async def initialize() -> dict[str, object]:
        """Return bootstrap data for first-load UI initialization."""
        return {
            "version": __version__,
            "api_key": api_key,
            "auth_disabled": auth_disabled(),
        }

    app.include_router(health_router)

    api_router = APIRouter(prefix="/api/v1", dependencies=[Depends(verify)], tags=["api"])

    @api_router.get("/health")
    async def api_health() -> dict[str, str]:
        return {"status": "ok"}

    api_router.include_router(config_router)
    api_router.include_router(feeds_router)
    app.include_router(api_router)

    # Serve the pre-built SPA. MUST be mounted last so /api and /healthz
    # routes win over the catch-all.
    _mount_spa(app)

    return app


def _spa_dist_path() -> Path | None:
    """Locate the built SPA assets. Searches GLEAN_UI_DIST then default paths."""
    if env := os.environ.get("GLEAN_UI_DIST"):
        candidate = Path(env)
        if candidate.is_dir() and (candidate / "index.html").is_file():
            return candidate
        return None

    candidates = [
        Path("/home/glean/ui/dist"),
        Path(__file__).resolve().parent.parent.parent.parent / "ui" / "dist",
    ]
    for candidate in candidates:
        if candidate.is_dir() and (candidate / "index.html").is_file():
            return candidate
    return None


def _mount_spa(app: FastAPI) -> None:
    """Mount the built SPA at / if a dist directory is available."""
    dist = _spa_dist_path()
    if dist is None:
        logger.info("ui_spa_not_mounted", reason="no dist directory found")
        return
    app.mount("/", StaticFiles(directory=str(dist), html=True), name="ui")
    logger.info("ui_spa_mounted", dist=str(dist))


async def run_api_server(
    state: StateStore,
    db_path: Path,
    port: int = 9090,
) -> uvicorn.Server:
    """Start uvicorn as an in-process task sharing the existing asyncio loop."""
    import uvicorn  # noqa: PLC0415

    app = make_app(state, db_path)
    config = uvicorn.Config(
        app=app,
        host="0.0.0.0",  # noqa: S104 -- daemon listens on all interfaces
        port=port,
        log_config=None,
        access_log=False,
    )
    server = uvicorn.Server(config)
    server.config.setup_event_loop = lambda: None  # type: ignore[method-assign]
    logger.info("api_listening", port=port)
    return server
