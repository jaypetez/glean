"""Tests for system info API."""
from __future__ import annotations

import platform
import textwrap
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from glean import __version__
from glean.api.app import make_app
from glean.state.store import StateStore

pytestmark = pytest.mark.asyncio


@pytest.fixture
async def app_client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    cfg_path = tmp_path / "feeds.yaml"
    cfg_path.write_text(
        textwrap.dedent(
            """
            defaults:
              llm:
                provider: openai
                model: gpt-4o-mini
            feeds:
              - name: alpha
                schedule: "every 1h"
                chat_id: -1
                sources:
                  - type: rss
                    url: https://example.com/feed.xml
                pipeline:
                  - dedup
            """
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("GLEAN_CONFIG", str(cfg_path))
    db_path = tmp_path / "state.db"
    state = StateStore(db_path)
    await state.open()
    app = make_app(state, db_path)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield app, client, cfg_path, db_path
    await state.close()


async def test_system_info_requires_auth(app_client) -> None:
    _, client, _, _ = app_client

    resp = await client.get("/api/v1/system/info")

    assert resp.status_code == 401


async def test_system_info_returns_expected_shape(app_client) -> None:
    app, client, cfg_path, db_path = app_client

    resp = await client.get(
        "/api/v1/system/info",
        headers={"X-Glean-Api-Key": app.state.glean_api_key},
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["version"] == __version__
    assert isinstance(body["hostname"], str)
    assert body["hostname"]
    assert body["python"] == platform.python_version()
    assert isinstance(body["platform"], str)
    assert body["platform"]
    assert body["database_path"] == str(db_path)
    assert body["config_path"] == str(cfg_path)
    assert body["feeds_count"] == 1
    assert body["llm_provider"] == "openai"
    assert body["llm_model"] == "gpt-4o-mini"
    assert isinstance(body["started_at"], str)
    assert isinstance(body["uptime_seconds"], (int, float))
    assert body["uptime_seconds"] >= 0
