"""Tests for /api/v1/config/* CRUD routes."""
from __future__ import annotations

import textwrap
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from glean.api.app import make_app
from glean.config import load_config
from glean.state.store import StateStore

pytestmark = pytest.mark.asyncio


_SAMPLE_YAML = textwrap.dedent(
    """
    defaults:
      llm: {provider: ollama, model: qwen2.5:7b}
    skills:
      - name: example-skill
        prompt: "Extract from {title}"
        output_schema:
          summary: str
    feeds:
      - name: alpha
        schedule: "every 1h"
        chat_id: -1
        sources:
          - type: rss
            url: https://example.com/a.xml
        pipeline:
          - dedup
          - summarize:
              prompt: "Summarize"
    """
)


@pytest.fixture
async def configured_app(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    cfg_path = tmp_path / "feeds.yaml"
    cfg_path.write_text(_SAMPLE_YAML, encoding="utf-8")
    monkeypatch.setenv("GLEAN_CONFIG", str(cfg_path))
    state = StateStore(tmp_path / "state.db")
    await state.open()
    app = make_app(state, tmp_path / "state.db")
    yield app, cfg_path, app.state.glean_api_key
    await state.close()


@pytest.fixture
async def client(configured_app):
    app, _, _ = configured_app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


@pytest.fixture
def auth_headers(configured_app) -> dict[str, str]:
    _, _, key = configured_app
    return {"X-Glean-Api-Key": key}


# === Defaults ===


async def test_get_defaults_returns_current(client: AsyncClient, auth_headers) -> None:
    resp = await client.get("/api/v1/config/defaults", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["llm"]["provider"] == "ollama"


async def test_put_defaults_writes_yaml(
    client: AsyncClient, auth_headers, configured_app
) -> None:
    _, cfg_path, _ = configured_app
    new_defaults = {"llm": {"provider": "openai", "model": "gpt-4o-mini"}}
    resp = await client.put(
        "/api/v1/config/defaults",
        headers=auth_headers,
        json=new_defaults,
    )
    assert resp.status_code == 200
    assert resp.json()["ok"] is True
    cfg = load_config(cfg_path)
    assert cfg.defaults.llm.provider == "openai"


# === Feeds ===


async def test_list_feeds_returns_summary(client: AsyncClient, auth_headers) -> None:
    resp = await client.get("/api/v1/config/feeds", headers=auth_headers)
    assert resp.status_code == 200
    feeds = resp.json()
    assert len(feeds) == 1
    assert feeds[0]["name"] == "alpha"
    assert feeds[0]["sources_count"] == 1
    assert "dedup" in feeds[0]["pipeline_stages"]


async def test_get_feed_returns_full_model(client: AsyncClient, auth_headers) -> None:
    resp = await client.get("/api/v1/config/feeds/alpha", headers=auth_headers)
    assert resp.status_code == 200
    feed = resp.json()
    assert feed["name"] == "alpha"
    assert feed["schedule"] == "every 1h"


async def test_get_feed_404(client: AsyncClient, auth_headers) -> None:
    resp = await client.get("/api/v1/config/feeds/nonexistent", headers=auth_headers)
    assert resp.status_code == 404


async def test_create_feed_writes_yaml(
    client: AsyncClient, auth_headers, configured_app
) -> None:
    _, cfg_path, _ = configured_app
    new_feed = {
        "name": "beta",
        "schedule": "daily 09:00",
        "chat_id": -2,
        "sources": [{"type": "rss", "url": "https://example.com/b.xml"}],
        "pipeline": [{"dedup": {}}],
    }
    resp = await client.post(
        "/api/v1/config/feeds", headers=auth_headers, json=new_feed
    )
    assert resp.status_code == 201
    cfg = load_config(cfg_path)
    assert any(f.name == "beta" for f in cfg.feeds)


async def test_create_feed_409_on_duplicate(
    client: AsyncClient, auth_headers
) -> None:
    dup = {
        "name": "alpha",
        "schedule": "every 1h",
        "chat_id": -1,
        "sources": [{"type": "rss", "url": "https://example.com/a.xml"}],
        "pipeline": [{"dedup": {}}],
    }
    resp = await client.post("/api/v1/config/feeds", headers=auth_headers, json=dup)
    assert resp.status_code == 409


async def test_update_feed(client: AsyncClient, auth_headers, configured_app) -> None:
    _, cfg_path, _ = configured_app
    updated = {
        "name": "alpha",
        "schedule": "every 30m",
        "chat_id": -1,
        "sources": [{"type": "rss", "url": "https://example.com/a.xml"}],
        "pipeline": [{"dedup": {}}],
    }
    resp = await client.put(
        "/api/v1/config/feeds/alpha", headers=auth_headers, json=updated
    )
    assert resp.status_code == 200
    cfg = load_config(cfg_path)
    assert cfg.feed("alpha").schedule == "every 30m"


async def test_update_feed_400_on_name_mismatch(
    client: AsyncClient, auth_headers
) -> None:
    body = {
        "name": "different",
        "schedule": "every 1h",
        "chat_id": -1,
        "sources": [{"type": "rss", "url": "https://example.com/a.xml"}],
        "pipeline": [{"dedup": {}}],
    }
    resp = await client.put(
        "/api/v1/config/feeds/alpha", headers=auth_headers, json=body
    )
    assert resp.status_code == 400


async def test_update_feed_404(client: AsyncClient, auth_headers) -> None:
    body = {
        "name": "ghost",
        "schedule": "every 1h",
        "chat_id": -1,
        "sources": [{"type": "rss", "url": "https://example.com/g.xml"}],
        "pipeline": [{"dedup": {}}],
    }
    resp = await client.put(
        "/api/v1/config/feeds/ghost", headers=auth_headers, json=body
    )
    assert resp.status_code == 404


async def test_delete_feed_removes_from_yaml(
    client: AsyncClient, auth_headers, configured_app
) -> None:
    _, cfg_path, _ = configured_app
    extra = {
        "name": "beta",
        "schedule": "daily 09:00",
        "chat_id": -2,
        "sources": [{"type": "rss", "url": "https://example.com/b.xml"}],
        "pipeline": [{"dedup": {}}],
    }
    await client.post("/api/v1/config/feeds", headers=auth_headers, json=extra)

    resp = await client.delete("/api/v1/config/feeds/alpha", headers=auth_headers)
    assert resp.status_code == 200
    cfg = load_config(cfg_path)
    assert all(f.name != "alpha" for f in cfg.feeds)


async def test_delete_last_feed_400(client: AsyncClient, auth_headers) -> None:
    """Cannot delete last feed because config requires at least one."""
    resp = await client.delete("/api/v1/config/feeds/alpha", headers=auth_headers)
    assert resp.status_code == 400


# === Skills ===


async def test_list_skills(client: AsyncClient, auth_headers) -> None:
    resp = await client.get("/api/v1/config/skills", headers=auth_headers)
    assert resp.status_code == 200
    skills = resp.json()
    assert len(skills) == 1
    assert skills[0]["name"] == "example-skill"


async def test_create_skill(
    client: AsyncClient, auth_headers, configured_app
) -> None:
    _, cfg_path, _ = configured_app
    new_skill = {
        "name": "deal-finder",
        "prompt": "Extract deal from {title}",
        "output_schema": {"summary": "str", "price": "str | None"},
    }
    resp = await client.post(
        "/api/v1/config/skills", headers=auth_headers, json=new_skill
    )
    assert resp.status_code == 201
    cfg = load_config(cfg_path)
    assert any(s.name == "deal-finder" for s in cfg.skills)


async def test_update_skill(
    client: AsyncClient, auth_headers, configured_app
) -> None:
    _, cfg_path, _ = configured_app
    updated = {
        "name": "example-skill",
        "prompt": "Updated prompt for {title}",
        "output_schema": {"summary": "str"},
    }
    resp = await client.put(
        "/api/v1/config/skills/example-skill", headers=auth_headers, json=updated
    )
    assert resp.status_code == 200
    cfg = load_config(cfg_path)
    assert cfg.skill("example-skill").prompt == "Updated prompt for {title}"


async def test_delete_skill(
    client: AsyncClient, auth_headers, configured_app
) -> None:
    _, cfg_path, _ = configured_app
    resp = await client.delete(
        "/api/v1/config/skills/example-skill", headers=auth_headers
    )
    assert resp.status_code == 200
    cfg = load_config(cfg_path)
    assert all(s.name != "example-skill" for s in cfg.skills)


# === Validate ===


async def test_validate_no_body_validates_disk(
    client: AsyncClient, auth_headers
) -> None:
    resp = await client.post("/api/v1/config/validate", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["valid"] is True
    assert body["feeds_count"] == 1
    assert body["skills_count"] == 1


async def test_validate_with_invalid_body(client: AsyncClient, auth_headers) -> None:
    resp = await client.post(
        "/api/v1/config/validate",
        headers=auth_headers,
        json={"invalid": "shape"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["valid"] is False
    assert len(body["errors"]) > 0


async def test_yaml_round_trip_preserves_data(
    client: AsyncClient, auth_headers, configured_app
) -> None:
    """After update + reload, the YAML still parses correctly."""
    _, cfg_path, _ = configured_app
    new_defaults = {
        "llm": {
            "provider": "anthropic",
            "model": "claude-haiku-4-5",
            "api_key": "sk-test",
        }
    }
    resp = await client.put(
        "/api/v1/config/defaults", headers=auth_headers, json=new_defaults
    )
    assert resp.status_code == 200
    cfg = load_config(cfg_path)
    assert cfg.defaults.llm.provider == "anthropic"
    assert cfg.defaults.llm.api_key == "sk-test"
    assert len(cfg.feeds) == 1
    assert len(cfg.skills) == 1


async def test_unauthenticated_blocked(client: AsyncClient) -> None:
    """All config endpoints require auth."""
    resp = await client.get("/api/v1/config/defaults")
    assert resp.status_code == 401
    resp = await client.get("/api/v1/config/feeds")
    assert resp.status_code == 401
