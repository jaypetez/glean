"""Tests for the FastAPI foundation + auth."""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from httpx import ASGITransport, AsyncClient

from glean.api.app import make_app
from glean.state.store import StateStore

pytestmark = pytest.mark.asyncio

AUTH_DISABLED_WARNING = (
    "AUTH_DISABLED — all endpoints unauthenticated; do not expose port 9090 publicly"
)


def _structured_events(
    records: list[logging.LogRecord], *, logger_name: str, contains: str
) -> list[str]:
    events: list[str] = []
    for record in records:
        if record.name != logger_name:
            continue
        message = record.getMessage()
        try:
            decoded = json.loads(message)
        except json.JSONDecodeError:
            event = message
        else:
            event = str(decoded.get("event", message))
        if contains in event:
            events.append(event)
    return events


@pytest.fixture
async def app_and_state(tmp_path: Path):
    state = StateStore(tmp_path / "state.db")
    await state.open()
    app = make_app(state, tmp_path / "state.db")
    yield app, state
    await state.close()


@pytest.fixture
async def client(app_and_state):
    app, _ = app_and_state
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


@pytest.fixture
def api_key(app_and_state) -> str:
    app, _ = app_and_state
    return app.state.glean_api_key


async def test_healthz_unauthenticated(client: AsyncClient) -> None:
    """/healthz must work without auth (Docker HEALTHCHECK depends on this)."""
    resp = await client.get("/healthz")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


async def test_healthz_reports_generic_db_error(tmp_path: Path) -> None:
    """/healthz must not expose exception details to callers."""

    class BrokenDb:
        def execute(self, _query: str):
            raise RuntimeError("sensitive database path")

    app = make_app(SimpleNamespace(db=BrokenDb()), tmp_path / "state.db")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/healthz")

    assert resp.status_code == 503
    assert resp.json() == {"detail": "db error"}


async def test_initialize_does_not_return_api_key(client: AsyncClient) -> None:
    """/api/v1/initialize is unauthenticated but never returns the api_key."""
    resp = await client.get("/api/v1/initialize")
    assert resp.status_code == 200
    body = resp.json()
    assert "api_key" not in body
    assert body["version"]
    assert body["auth_disabled"] is False


async def test_authenticated_route_rejects_missing_key(client: AsyncClient) -> None:
    resp = await client.get("/api/v1/health")
    assert resp.status_code == 401


async def test_authenticated_route_rejects_wrong_key(client: AsyncClient) -> None:
    resp = await client.get(
        "/api/v1/health",
        headers={"X-Glean-Api-Key": "obviously-not-the-real-key"},
    )
    assert resp.status_code == 401


async def test_authenticated_route_accepts_valid_key(client: AsyncClient, api_key: str) -> None:
    resp = await client.get(
        "/api/v1/health",
        headers={"X-Glean-Api-Key": api_key},
    )
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


async def test_auth_disabled_via_env(client: AsyncClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GLEAN_DISABLE_AUTH", "1")
    resp = await client.get("/api/v1/health")
    assert resp.status_code == 200


async def test_make_app_checks_configured_data_dir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from glean.api import app as app_module

    checked_dirs: list[Path] = []
    monkeypatch.setattr(app_module, "_warn_if_data_dir_insecure", checked_dirs.append)

    db_path = tmp_path / "custom-data" / "state.db"
    db_path.parent.mkdir()
    state = StateStore(db_path)
    await state.open()
    try:
        make_app(state, db_path)
    finally:
        await state.close()

    assert checked_dirs == [db_path.parent]


async def test_auth_disabled_logs_warning_once_per_app_instance(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    import glean.logging as logging_module
    from glean.api import app as app_module

    monkeypatch.setenv("GLEAN_DISABLE_AUTH", "1")
    logging_module.structlog.reset_defaults()
    try:
        logging_module.configure_logging("INFO", json_logs=True)
        monkeypatch.setattr(app_module, "logger", logging_module.get_logger("glean.api.app"))
        caplog.set_level(logging.WARNING, logger="glean.api.app")

        state1 = StateStore(tmp_path / "state1.db")
        await state1.open()
        try:
            app1 = make_app(state1, tmp_path / "state1.db")
            async with AsyncClient(transport=ASGITransport(app=app1), base_url="http://test") as ac:
                assert (await ac.get("/api/v1/health")).status_code == 200
                assert (await ac.get("/api/v1/health")).status_code == 200
        finally:
            await state1.close()

        auth_disabled_warnings = _structured_events(
            caplog.records,
            logger_name="glean.api.app",
            contains="AUTH_DISABLED",
        )
        assert auth_disabled_warnings == [AUTH_DISABLED_WARNING]

        state2 = StateStore(tmp_path / "state2.db")
        await state2.open()
        try:
            make_app(state2, tmp_path / "state2.db")
        finally:
            await state2.close()

        assert _structured_events(
            caplog.records,
            logger_name="glean.api.app",
            contains="AUTH_DISABLED",
        ) == [AUTH_DISABLED_WARNING, AUTH_DISABLED_WARNING]
    finally:
        logging_module.structlog.reset_defaults()


@pytest.mark.skipif(
    sys.platform == "win32", reason="POSIX chmod checks are not reliable on Windows"
)
async def test_make_app_warns_when_data_dir_has_world_permission_bits(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    import glean.logging as logging_module
    from glean.api import app as app_module

    data_dir = tmp_path / "data"
    data_dir.mkdir()
    data_dir.chmod(0o701)
    db_path = data_dir / "state.db"

    logging_module.structlog.reset_defaults()
    try:
        logging_module.configure_logging("INFO", json_logs=True)
        monkeypatch.setattr(app_module, "logger", logging_module.get_logger("glean.api.app"))
        caplog.set_level(logging.WARNING, logger="glean.api.app")

        state = StateStore(db_path)
        await state.open()
        try:
            make_app(state, db_path)
        finally:
            await state.close()

        assert _structured_events(
            caplog.records,
            logger_name="glean.api.app",
            contains="data directory",
        ) == ["data directory is world-accessible; run chmod 700 /data"]
    finally:
        logging_module.structlog.reset_defaults()


async def test_api_key_persisted_as_verifier_not_cleartext(tmp_path: Path) -> None:
    """Restarted apps should verify the key without storing or re-revealing it."""
    state1 = StateStore(tmp_path / "state.db")
    await state1.open()
    app1 = make_app(state1, tmp_path / "state.db")
    api_key = app1.state.glean_api_key
    await state1.close()

    assert isinstance(api_key, str)
    assert len(api_key) >= 32
    assert (tmp_path / "api_key").read_text(encoding="utf-8").strip() != api_key

    state2 = StateStore(tmp_path / "state.db")
    await state2.open()
    app2 = make_app(state2, tmp_path / "state.db")
    assert app2.state.glean_api_key is None
    assert app2.state.glean_api_key_material.plaintext is None
    async with AsyncClient(transport=ASGITransport(app=app2), base_url="http://test") as ac:
        init = await ac.get("/api/v1/initialize")
        health = await ac.get("/api/v1/health", headers={"X-Glean-Api-Key": api_key})
        init_after_auth = await ac.get("/api/v1/initialize")
    await state2.close()

    assert init.status_code == 200
    assert "api_key" not in init.json()
    assert health.status_code == 200
    assert app2.state.glean_api_key_material.plaintext == api_key
    assert "api_key" not in init_after_auth.json()


async def test_legacy_plaintext_api_key_file_is_migrated(tmp_path: Path) -> None:
    legacy_key = "legacy-manual-key"
    (tmp_path / "api_key").write_text(legacy_key, encoding="utf-8")

    state = StateStore(tmp_path / "state.db")
    await state.open()
    app = make_app(state, tmp_path / "state.db")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        init = await ac.get("/api/v1/initialize")
        health = await ac.get("/api/v1/health", headers={"X-Glean-Api-Key": legacy_key})
    await state.close()

    persisted = (tmp_path / "api_key").read_text(encoding="utf-8").strip()
    assert persisted != legacy_key
    assert persisted.startswith("pbkdf2_sha256$")
    assert "api_key" not in init.json()
    assert health.status_code == 200


async def test_api_key_env_override(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from glean.api.auth import get_or_create_api_key

    monkeypatch.setenv("GLEAN_API_KEY", "env-override-key")
    assert get_or_create_api_key(tmp_path / "x.db").plaintext == "env-override-key"


async def test_openapi_schema_available_when_enabled(
    app_and_state, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _, state = app_and_state
    monkeypatch.setenv("GLEAN_ENABLE_DOCS", "1")
    app = make_app(state, tmp_path / "state.db")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/api/openapi.json")
    assert resp.status_code == 200
    body = resp.json()
    assert body["info"]["title"] == "glean"


async def test_spa_not_mounted_when_dist_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """If no dist dir is available, /api and /healthz still work; / 404s gracefully."""
    monkeypatch.setenv("GLEAN_UI_DIST", str(tmp_path / "nonexistent"))
    state = StateStore(tmp_path / "state.db")
    await state.open()
    try:
        app = make_app(state, tmp_path / "state.db")
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            healthz = await ac.get("/healthz")
            assert healthz.status_code == 200
            root = await ac.get("/")
            assert root.status_code == 404
    finally:
        await state.close()


async def test_spa_mounted_when_dist_present(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """If a dist directory with index.html exists, / serves the SPA shell."""
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("<html><body>glean ui</body></html>")
    monkeypatch.setenv("GLEAN_UI_DIST", str(dist))
    state = StateStore(tmp_path / "state.db")
    await state.open()
    try:
        app = make_app(state, tmp_path / "state.db")
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            root = await ac.get("/")
            assert root.status_code == 200
            assert b"glean ui" in root.content
            nested = await ac.get("/feeds/new")
            assert nested.status_code == 200
            assert b"glean ui" in nested.content
            unknown_api = await ac.get("/api/v1/missing")
            assert unknown_api.status_code == 404
            healthz = await ac.get("/healthz")
            assert healthz.status_code == 200
    finally:
        await state.close()
