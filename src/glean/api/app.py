"""FastAPI application factory."""

from __future__ import annotations

import os
import shutil
import time
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import TYPE_CHECKING, cast

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Request, Response, status
from fastapi.staticfiles import StaticFiles
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from slowapi.util import get_remote_address
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.types import Scope

from glean import __version__
from glean.api.auth import ApiKeyMaterial, auth_disabled, get_or_create_api_key, make_verify_api_key
from glean.api.events import EventBus
from glean.api.middleware import LimitBodySizeMiddleware, SecurityHeadersMiddleware
from glean.api.models import InitializeResponse
from glean.api.routes.auth_routes import build_auth_router
from glean.api.routes.config import router as config_router
from glean.api.routes.events import router as events_router
from glean.api.routes.feeds import router as feeds_router
from glean.api.routes.system import router as system_router
from glean.logging import get_logger

if TYPE_CHECKING:
    import uvicorn

    from glean.state.store import StateStore

logger = get_logger(__name__)
ExceptionHandler = Callable[[Request, Exception], Response | Awaitable[Response]]


class SPAStaticFiles(StaticFiles):
    """StaticFiles variant that serves index.html for client-side routes."""

    async def get_response(self, path: str, scope: Scope) -> Response:
        normalized_path = path.lstrip("/")
        request_path = str(scope.get("path", "")).lstrip("/")
        reserved_route = (
            normalized_path == "healthz"
            or normalized_path.startswith("api/")
            or request_path == "healthz"
            or request_path.startswith("api/")
        )
        if reserved_route:
            raise StarletteHTTPException(status_code=status.HTTP_404_NOT_FOUND)
        try:
            return await super().get_response(path, scope)
        except StarletteHTTPException as exc:
            route_missing = exc.status_code == status.HTTP_404_NOT_FOUND
            method_can_fallback = scope["method"] in {"GET", "HEAD"}
            if not route_missing or not method_can_fallback:
                raise
            return await super().get_response("index.html", scope)


def _test_mode_enabled() -> bool:
    """True when e2e-only API helpers are enabled."""
    return os.environ.get("GLEAN_TEST_MODE", "").lower() in ("1", "true", "yes")


def _warn_if_data_dir_insecure(data_dir: Path = Path("/data")) -> None:
    """Warn operators when the default data directory is visible to other users."""
    try:
        mode = data_dir.stat().st_mode
    except OSError:
        return
    if mode & 0o007:
        logger.warning(
            "data directory is world-accessible; run chmod 700 /data",
            path=str(data_dir),
            mode=oct(mode & 0o777),
        )


def _max_body_bytes_from_env() -> int:
    raw_value = os.environ.get("GLEAN_MAX_BODY_BYTES")
    if raw_value is None:
        return 1_048_576
    try:
        max_bytes = int(raw_value)
    except ValueError:
        logger.warning("invalid GLEAN_MAX_BODY_BYTES; using default", value=raw_value)
        return 1_048_576
    if max_bytes <= 0:
        logger.warning("non-positive GLEAN_MAX_BODY_BYTES; using default", value=raw_value)
        return 1_048_576
    return max_bytes


async def _clear_test_state(state: StateStore) -> None:
    """Clear state tables for Playwright e2e isolation."""
    await state.db.execute("DELETE FROM seen_items")
    await state.db.execute("DELETE FROM feed_runs")
    await state.db.execute("DELETE FROM etag_cache")
    await state.db.commit()


def _restore_test_config(fixture_name: str) -> None:
    """Restore the active config from the configured e2e fixture."""
    if fixture_name == "empty":
        fixture_env = "GLEAN_TEST_EMPTY_CONFIG_FIXTURE"
    else:
        fixture_env = "GLEAN_TEST_CONFIG_FIXTURE"
    fixture = os.environ.get(fixture_env)
    config = os.environ.get("GLEAN_CONFIG")
    if not fixture or not config:
        return
    config_path = Path(config)
    config_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(Path(fixture), config_path)


def make_app(state: StateStore, db_path: Path) -> FastAPI:
    """Build the FastAPI app with all routes wired up.

    The ``state`` and ``db_path`` are stored on ``app.state`` so future routers
    can fetch them via ``request.app.state.glean_state``.
    """
    docs_enabled = os.environ.get("GLEAN_ENABLE_DOCS") == "1"
    docs_url = "/api/docs" if docs_enabled else None
    openapi_url = "/api/openapi.json" if docs_enabled else None
    app = FastAPI(
        title="glean",
        version=__version__,
        description="Self-hosted content aggregation daemon — REST API",
        docs_url=docs_url,
        redoc_url=None,
        openapi_url=openapi_url,
    )
    limiter = Limiter(key_func=get_remote_address, default_limits=["60/minute"])
    app.state.limiter = limiter
    rate_limit_handler = cast(ExceptionHandler, _rate_limit_exceeded_handler)
    app.add_exception_handler(RateLimitExceeded, rate_limit_handler)
    app.add_middleware(SlowAPIMiddleware)
    app.add_middleware(LimitBodySizeMiddleware, max_bytes=_max_body_bytes_from_env())
    app.add_middleware(SecurityHeadersMiddleware)

    if auth_disabled():
        logger.warning(
            "AUTH_DISABLED — all endpoints unauthenticated; do not expose port 9090 publicly"
        )
    _warn_if_data_dir_insecure(db_path.parent)

    api_key_material = get_or_create_api_key(db_path)
    app.state.glean_state = state
    app.state.glean_db_path = db_path
    app.state.glean_api_key = api_key_material.plaintext
    app.state.glean_api_key_material = api_key_material
    app.state.glean_started_at = time.time()
    app.state.glean_event_bus = EventBus()

    def api_key_getter() -> ApiKeyMaterial:
        return cast(ApiKeyMaterial, app.state.glean_api_key_material)

    def cache_verified_api_key(material: ApiKeyMaterial) -> None:
        app.state.glean_api_key_material = material

    verify = make_verify_api_key(api_key_getter, on_verified=cache_verified_api_key)
    verify_events = make_verify_api_key(
        api_key_getter,
        allow_query_for_events=True,
        on_verified=cache_verified_api_key,
    )

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

    @health_router.get("/api/v1/initialize", response_model=InitializeResponse)
    @limiter.limit("10/minute")
    async def initialize(request: Request) -> InitializeResponse:
        """Return bootstrap data for first-load UI initialization."""
        return InitializeResponse(
            version=__version__,
            auth_disabled=auth_disabled(),
        )

    app.include_router(health_router)

    api_router = APIRouter(prefix="/api/v1", dependencies=[Depends(verify)], tags=["api"])

    @api_router.get("/health")
    async def api_health() -> dict[str, str]:
        return {"status": "ok"}

    if _test_mode_enabled():

        @api_router.post("/test/reset")
        async def test_reset(request: Request, fixture: str = "default") -> dict[str, object]:
            if not _test_mode_enabled():
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="not found")
            await _clear_test_state(state)
            request.app.state.limiter.reset()
            _restore_test_config(fixture)
            return {"ok": True, "message": "test state reset"}

        @api_router.get("/test/rss")
        async def test_rss() -> Response:
            if not _test_mode_enabled():
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="not found")
            rss = """<?xml version=\"1.0\" encoding=\"UTF-8\" ?>
<rss version=\"2.0\">
  <channel>
    <title>glean E2E Feed</title>
    <link>http://localhost:8080/api/v1/test/rss</link>
    <description>Static feed for Playwright e2e tests</description>
    <item>
      <title>Playwright E2E item</title>
      <link>http://localhost:8080/items/playwright-e2e</link>
      <description>Stable RSS item for test runs.</description>
      <guid>playwright-e2e-item</guid>
    </item>
  </channel>
</rss>
"""
            return Response(content=rss, media_type="application/rss+xml")

    api_router.include_router(build_auth_router(limiter))
    api_router.include_router(config_router)
    api_router.include_router(feeds_router)
    api_router.include_router(system_router)
    app.include_router(api_router)

    events_api_router = APIRouter(
        prefix="/api/v1",
        dependencies=[Depends(verify_events)],
        tags=["api"],
    )
    events_api_router.include_router(events_router)
    app.include_router(events_api_router)

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
    app.mount("/", SPAStaticFiles(directory=str(dist), html=True), name="ui")
    logger.info("ui_spa_mounted", dist=str(dist))


async def run_api_server(
    state: StateStore,
    db_path: Path,
    port: int = 9090,
    host: str = "0.0.0.0",  # noqa: S104 -- daemon listens on all interfaces by default # nosec
) -> uvicorn.Server:
    """Start uvicorn as an in-process task sharing the existing asyncio loop."""
    import uvicorn  # noqa: PLC0415

    app = make_app(state, db_path)
    config = uvicorn.Config(
        app=app,
        host=host,
        port=port,
        log_config=None,
        access_log=False,
        server_header=False,
        date_header=False,
        limit_concurrency=50,
        h11_max_incomplete_event_size=65_536,
    )
    server = uvicorn.Server(config)
    server.config.setup_event_loop = lambda: None  # type: ignore[method-assign]
    logger.info("api_listening", port=port)
    return server
