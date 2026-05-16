"""FastAPI application factory."""

from __future__ import annotations

import datetime as dt
import os
import re
import secrets
import shutil
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal, TypeVar, cast

from apscheduler import RunState
from fastapi import APIRouter, Depends, FastAPI, HTTPException, Request, Response, status
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from slowapi.util import get_remote_address
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.types import Scope
from structlog.contextvars import bind_contextvars, clear_contextvars

from glean import __version__
from glean.api.auth import ApiKeyMaterial, auth_disabled, get_or_create_api_key, make_verify_api_key
from glean.api.events import EventBus, RunEvent
from glean.api.middleware import LimitBodySizeMiddleware, SecurityHeadersMiddleware
from glean.api.models import InitializeResponse
from glean.api.routes.auth_routes import build_auth_router
from glean.api.routes.config import router as config_router
from glean.api.routes.digests import router as digests_router
from glean.api.routes.events import router as events_router
from glean.api.routes.feeds import router as feeds_router
from glean.api.routes.system import router as system_router
from glean.config import load_config
from glean.config.loader import ConfigError
from glean.logging import get_logger

if TYPE_CHECKING:
    import uvicorn

    from glean.state.store import StateStore

logger = get_logger(__name__)
ExceptionHandler = Callable[[Request, Exception], Response | Awaitable[Response]]
RouteHandler = TypeVar("RouteHandler", bound=Callable[..., Any])
_TRACE_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


@dataclass(frozen=True, slots=True)
class HealthConfigSnapshot:
    """Cached feed-name snapshot for /healthz responses."""

    path: Path
    mtime_ns: int | None
    feed_names: tuple[str, ...]
    valid: bool


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
    await state.db.execute("DELETE FROM digests")
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


class TestSeedDigestRequest(BaseModel):
    """E2E-only payload for seeding persisted digests."""

    model_config = ConfigDict(extra="forbid")

    feed_name: str = Field(min_length=1)
    style: Literal["html", "markdown_v2", "plain"] = "html"
    intro: str | None = None
    body: str = Field(min_length=1)
    fragment_index: int = Field(default=0, ge=0)
    item_count: int = Field(default=1, ge=0)
    trace_id: str | None = None
    sent_at: dt.datetime | None = None


def _config_path() -> Path:
    """Return the configured feeds.yaml path."""
    return Path(os.environ.get("GLEAN_CONFIG", "/etc/glean/feeds.yaml"))


def _trace_id_from_header(trace_id: str | None) -> str:
    """Return a safe trace identifier for request correlation."""
    if trace_id and _TRACE_ID_RE.fullmatch(trace_id):
        return trace_id
    return secrets.token_hex(4)


def _health_config_snapshot(app: FastAPI) -> HealthConfigSnapshot:
    """Return cached config details for /healthz, refreshing on file changes."""
    config_path = _config_path()
    try:
        mtime_ns = config_path.stat().st_mtime_ns
    except OSError:
        snapshot = HealthConfigSnapshot(
            path=config_path,
            mtime_ns=None,
            feed_names=(),
            valid=False,
        )
        app.state.glean_health_config_snapshot = snapshot
        return snapshot

    cached = cast(
        HealthConfigSnapshot | None,
        getattr(app.state, "glean_health_config_snapshot", None),
    )
    if cached is not None and cached.path == config_path and cached.mtime_ns == mtime_ns:
        return cached

    try:
        cfg = load_config(config_path)
    except ConfigError:
        snapshot = HealthConfigSnapshot(
            path=config_path,
            mtime_ns=mtime_ns,
            feed_names=(),
            valid=False,
        )
    else:
        snapshot = HealthConfigSnapshot(
            path=config_path,
            mtime_ns=mtime_ns,
            feed_names=tuple(feed.name for feed in cfg.feeds),
            valid=True,
        )
    app.state.glean_health_config_snapshot = snapshot
    return snapshot


async def _feed_health_snapshot(
    state: StateStore, feed_names: tuple[str, ...]
) -> tuple[dict[str, int], list[str]]:
    """Return last-run ages and active alerts for configured feeds."""
    if not feed_names:
        return {}, []

    now = int(time.time())
    configured_feeds = set(feed_names)
    async with state.db.execute(
        "SELECT feed, last_attempt_at, alert_active FROM feed_runs ORDER BY feed"
    ) as cur:
        rows = await cur.fetchall()

    last_run_age_seconds: dict[str, int] = {}
    alert_active_feeds: list[str] = []
    for feed_name, last_attempt_at, alert_active in rows:
        feed_name_str = str(feed_name)
        if feed_name_str not in configured_feeds:
            continue
        if last_attempt_at is not None:
            last_run_age_seconds[feed_name_str] = max(0, now - int(last_attempt_at))
        if alert_active:
            alert_active_feeds.append(feed_name_str)
    return last_run_age_seconds, alert_active_feeds


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

    def exempt_from_rate_limit(handler: RouteHandler) -> RouteHandler:
        """Preserve handler types when applying SlowAPI exemptions."""
        return cast(RouteHandler, cast(Any, limiter.exempt)(handler))
    rate_limit_handler = cast(ExceptionHandler, _rate_limit_exceeded_handler)
    app.add_exception_handler(RateLimitExceeded, rate_limit_handler)
    app.add_middleware(SlowAPIMiddleware)
    app.add_middleware(LimitBodySizeMiddleware, max_bytes=_max_body_bytes_from_env())
    app.add_middleware(SecurityHeadersMiddleware)

    @app.middleware("http")
    async def trace_id_middleware(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        trace_id = _trace_id_from_header(request.headers.get("X-Glean-Trace-Id"))
        clear_contextvars()
        bind_contextvars(trace_id=trace_id)
        request.state.trace_id = trace_id
        started_at = time.perf_counter()
        try:
            response = await call_next(request)
            duration_ms = int((time.perf_counter() - started_at) * 1000)
            response.headers["X-Glean-Trace-Id"] = trace_id
            logger.info(
                "api_request_completed",
                method=request.method,
                path=request.url.path,
                status_code=response.status_code,
                duration_ms=duration_ms,
            )
            return response
        except Exception:
            logger.exception("api_request_failed", method=request.method, path=request.url.path)
            raise
        finally:
            clear_contextvars()

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
    app.state.glean_started_monotonic = time.monotonic()
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

    health_router = APIRouter()

    @health_router.get("/healthz", tags=["health"])
    async def healthz(request: Request) -> dict[str, Any]:
        try:
            await state.ping()
            db_ok = True
        except Exception:
            db_ok = False

        scheduler = getattr(request.app.state, "glean_scheduler", None)
        sched_ok: bool | None
        if scheduler is None:
            # API-only/test apps do not always host the scheduler; that is healthy.
            sched_ok = None
        else:
            running = getattr(scheduler, "running", None)
            if running is None:
                scheduler_state = getattr(scheduler, "state", None)
                sched_ok = None if scheduler_state is None else scheduler_state == RunState.started
            else:
                sched_ok = bool(running)

        config_snapshot = _health_config_snapshot(request.app)
        last_run_age_seconds, alert_active_feeds = await _feed_health_snapshot(
            state, config_snapshot.feed_names
        )
        started_monotonic = float(request.app.state.glean_started_monotonic)
        uptime_seconds = int(time.monotonic() - started_monotonic)
        degraded = (
            bool(alert_active_feeds)
            or not config_snapshot.valid
            or not db_ok
            or sched_ok is False
        )
        return {
            "status": "degraded" if degraded else "ok",
            "db": "ok" if db_ok else "error",
            "scheduler": "running" if sched_ok else ("stopped" if sched_ok is False else "n/a"),
            "version": __version__,
            "uptime_s": uptime_seconds,
            "uptime_seconds": uptime_seconds,
            "feed_count": len(config_snapshot.feed_names),
            "last_run_age_seconds": last_run_age_seconds,
            "alert_active_feeds": alert_active_feeds,
        }

    @health_router.get("/api/v1/initialize", response_model=InitializeResponse, tags=["auth"])
    @limiter.limit("10/minute")
    async def initialize(request: Request) -> InitializeResponse:
        """Return bootstrap data for first-load UI initialization."""
        return InitializeResponse(
            version=__version__,
            auth_disabled=auth_disabled(),
        )

    app.include_router(health_router)

    api_router = APIRouter(prefix="/api/v1", dependencies=[Depends(verify)])

    @api_router.get("/health", tags=["health"])
    async def api_health() -> dict[str, str]:
        return {"status": "ok"}

    if _test_mode_enabled():

        @exempt_from_rate_limit
        @api_router.post("/test/reset", tags=["system"])
        async def test_reset(request: Request, fixture: str = "default") -> dict[str, object]:
            if not _test_mode_enabled():
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="not found")
            await _clear_test_state(state)
            request.app.state.limiter.reset()
            _restore_test_config(fixture)
            return {"ok": True, "message": "test state reset"}

        @exempt_from_rate_limit
        @api_router.get("/test/rss", tags=["system"])
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

        # E2E-only helper: seed dashboard digests without waiting for a scheduled pipeline run.
        @exempt_from_rate_limit
        @api_router.post("/test/seed-digest", tags=["system"])
        async def test_seed_digest(
            request: Request, payload: TestSeedDigestRequest
        ) -> dict[str, object]:
            if not _test_mode_enabled():
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="not found")
            sent_at = (payload.sent_at or dt.datetime.now(dt.UTC)).isoformat()
            cursor = await state.db.execute(
                """
                INSERT INTO digests (
                    feed_name,
                    sent_at,
                    style,
                    intro,
                    body,
                    fragment_index,
                    item_count,
                    trace_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    payload.feed_name,
                    sent_at,
                    payload.style,
                    payload.intro,
                    payload.body,
                    payload.fragment_index,
                    payload.item_count,
                    payload.trace_id,
                ),
            )
            await state.db.commit()
            row_id = int(cursor.lastrowid or 0)
            await request.app.state.glean_event_bus.publish(
                RunEvent(
                    type="digest.persisted",
                    feed=payload.feed_name,
                    digest_ids=[row_id],
                    sent_at=sent_at,
                    trace_id=payload.trace_id,
                    item_count=payload.item_count,
                )
            )
            return {"ok": True, "id": row_id}

    api_router.include_router(build_auth_router(limiter))
    api_router.include_router(config_router)
    api_router.include_router(digests_router)
    api_router.include_router(feeds_router)
    api_router.include_router(system_router)
    app.include_router(api_router)

    events_api_router = APIRouter(
        prefix="/api/v1",
        dependencies=[Depends(verify_events)],
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
