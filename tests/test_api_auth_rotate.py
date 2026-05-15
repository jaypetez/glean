"""Tests for API key rotation."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import HTTPException
from httpx import ASGITransport, AsyncClient
from starlette.requests import Request

from glean.api.app import make_app
from glean.api.auth import ApiKeyMaterial, make_verify_api_key
from glean.api.routes import auth_routes
from glean.state.store import StateStore

pytestmark = pytest.mark.asyncio


def _request(path: str) -> Request:
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": path,
            "headers": [],
            "query_string": b"",
        }
    )


@pytest.fixture
async def app_client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("GLEAN_API_KEY", raising=False)
    state = StateStore(tmp_path / "state.db")
    await state.open()
    app = make_app(state, tmp_path / "state.db")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield app, client, tmp_path / "api_key"
    await state.close()


async def test_rotate_requires_auth(app_client) -> None:
    _, client, _ = app_client

    resp = await client.post("/api/v1/auth/rotate")

    assert resp.status_code == 401


async def test_rotate_returns_new_key_and_persists_it(app_client) -> None:
    app, client, key_file = app_client
    old_key = app.state.glean_api_key

    resp = await client.post(
        "/api/v1/auth/rotate",
        headers={"X-Glean-Api-Key": old_key},
    )

    assert resp.status_code == 200
    body = resp.json()
    new_key = body["api_key"]
    assert isinstance(new_key, str)
    assert len(new_key) >= 32
    assert new_key != old_key
    persisted = key_file.read_text(encoding="utf-8").strip()
    assert persisted != new_key
    assert persisted.startswith("pbkdf2_sha256$")
    assert app.state.glean_api_key == new_key


async def test_rotate_rejects_env_override(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GLEAN_API_KEY", "env-fixed-key")
    state = StateStore(tmp_path / "state.db")
    await state.open()
    app = make_app(state, tmp_path / "state.db")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/api/v1/auth/rotate",
            headers={"X-Glean-Api-Key": "env-fixed-key"},
        )
    await state.close()

    assert resp.status_code == 409
    assert "GLEAN_API_KEY" in resp.text
    assert app.state.glean_api_key == "env-fixed-key"


async def test_rotated_key_is_required_for_subsequent_requests(app_client) -> None:
    app, client, _ = app_client
    old_key = app.state.glean_api_key
    rotate = await client.post(
        "/api/v1/auth/rotate",
        headers={"X-Glean-Api-Key": old_key},
    )
    assert rotate.status_code == 200
    new_key = rotate.json()["api_key"]

    old_resp = await client.get("/api/v1/health", headers={"X-Glean-Api-Key": old_key})
    new_resp = await client.get("/api/v1/health", headers={"X-Glean-Api-Key": new_key})

    assert old_resp.status_code == 401
    assert new_resp.status_code == 200


async def test_rotated_key_survives_restart_and_old_key_stays_invalid(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("GLEAN_API_KEY", raising=False)
    state1 = StateStore(tmp_path / "state.db")
    await state1.open()
    app1 = make_app(state1, tmp_path / "state.db")
    old_key = app1.state.glean_api_key
    async with AsyncClient(transport=ASGITransport(app=app1), base_url="http://test") as client:
        rotate = await client.post(
            "/api/v1/auth/rotate",
            headers={"X-Glean-Api-Key": old_key},
        )
    await state1.close()
    assert rotate.status_code == 200
    new_key = rotate.json()["api_key"]

    state2 = StateStore(tmp_path / "state.db")
    await state2.open()
    app2 = make_app(state2, tmp_path / "state.db")
    async with AsyncClient(transport=ASGITransport(app=app2), base_url="http://test") as client:
        old_resp = await client.get("/api/v1/health", headers={"X-Glean-Api-Key": old_key})
        new_resp = await client.get("/api/v1/health", headers={"X-Glean-Api-Key": new_key})
    await state2.close()

    assert old_resp.status_code == 401
    assert new_resp.status_code == 200


async def test_rotate_does_not_replace_active_key_if_rotation_fails(
    app_client, monkeypatch: pytest.MonkeyPatch
) -> None:
    app, client, _ = app_client
    old_key = app.state.glean_api_key
    old_material = app.state.glean_api_key_material

    def broken_rotate(_db_path: Path) -> ApiKeyMaterial:
        return ApiKeyMaterial(plaintext=None, record=None)

    monkeypatch.setattr(auth_routes, "rotate_api_key", broken_rotate)

    resp = await client.post("/api/v1/auth/rotate", headers={"X-Glean-Api-Key": old_key})
    health = await client.get("/api/v1/health", headers={"X-Glean-Api-Key": old_key})

    assert resp.status_code == 500
    assert app.state.glean_api_key == old_key
    assert app.state.glean_api_key_material is old_material
    assert health.status_code == 200


async def test_query_api_key_only_authenticates_events_endpoint(app_client) -> None:
    app, client, _ = app_client

    health_resp = await client.get("/api/v1/health", params={"api_key": app.state.glean_api_key})
    assert health_resp.status_code == 401

    events_verify = make_verify_api_key("secret", allow_query_for_events=True)
    await events_verify(_request("/api/v1/events"), api_key="secret")
    with pytest.raises(HTTPException) as exc:
        await events_verify(_request("/api/v1/health"), api_key="secret")

    assert exc.value.status_code == 401


async def test_openapi_only_advertises_query_api_key_for_events(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("GLEAN_ENABLE_DOCS", "1")
    state = StateStore(tmp_path / "state.db")
    await state.open()
    app = make_app(state, tmp_path / "state.db")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/openapi.json")
    await state.close()

    assert resp.status_code == 200
    paths = resp.json()["paths"]
    health_params = paths["/api/v1/health"]["get"].get("parameters", [])
    events_params = paths["/api/v1/events"]["get"].get("parameters", [])
    assert "api_key" not in {param["name"] for param in health_params}
    assert "api_key" in {param["name"] for param in events_params}


async def test_missing_expected_key_rejects_without_server_error() -> None:
    verify = make_verify_api_key(lambda: None)  # type: ignore[arg-type]

    with pytest.raises(HTTPException) as exc:
        await verify(x_glean_api_key="secret")

    assert exc.value.status_code == 401
