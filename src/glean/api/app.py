"""FastAPI application factory."""
from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from fastapi import APIRouter, Depends, FastAPI, HTTPException, status

from glean import __version__
from glean.api.auth import auth_disabled, get_or_create_api_key, make_verify_api_key
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

    app.include_router(api_router)

    return app


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
