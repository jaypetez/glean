"""Tests for /api/v1/feeds/* run + status routes."""

from __future__ import annotations

import textwrap
from pathlib import Path
from types import SimpleNamespace
from typing import Any, ClassVar

import pytest
from httpx import ASGITransport, AsyncClient

from glean.api.app import make_app
from glean.api.routes import feeds as feeds_routes
from glean.llm.registry import register_provider
from glean.sources.base import FetchContext, Item
from glean.sources.registry import register_source
from glean.state.store import StateStore

pytestmark = pytest.mark.asyncio


@register_source("fake")
class FakeSource:
    type: ClassVar[str] = "fake"

    def __init__(self, items: list[dict[str, Any]] | None = None) -> None:
        self.items = items or []

    async def fetch(self, ctx: FetchContext) -> list[Item]:
        return [
            Item(
                canonical_url=str(i.get("url", "")),
                title=str(i.get("title", "")),
                body=str(i.get("body", "")),
                source_type="fake",
                source_name="fake",
            )
            for i in self.items
        ]


@register_provider("fake")
class FakeLLM:
    name: ClassVar[str] = "fake"

    def __init__(self, **_: object) -> None:
        self.model = "fake"

    async def rank(self, item: Item, prompt: str) -> float:
        return 0.9

    async def summarize(self, item: Item, prompt: str) -> str:
        return f"summary of {item.title}"

    async def digest(self, items: list[Item], prompt: str) -> str:
        return prompt

    async def aclose(self) -> None:
        pass


_SAMPLE_YAML = textwrap.dedent(
    """
    defaults:
      llm: {provider: fake, model: fake}
    feeds:
      - name: alpha
        schedule: "every 1h"
        chat_id: -1
        sources:
          - type: fake
            items:
              - {url: "https://a", title: "A"}
        pipeline:
          - dedup
          - summarize:
              prompt: "x"
          - digest:
              intro: "intro"
    """
)


@pytest.fixture
async def configured_app(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    cfg_path = tmp_path / "feeds.yaml"
    cfg_path.write_text(_SAMPLE_YAML, encoding="utf-8")
    monkeypatch.setenv("GLEAN_CONFIG", str(cfg_path))
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    state = StateStore(tmp_path / "state.db")
    await state.open()
    app = make_app(state, tmp_path / "state.db")
    yield app, state
    await state.close()


@pytest.fixture
async def client(configured_app):
    app, _ = configured_app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


@pytest.fixture
def auth_headers(configured_app):
    app, _ = configured_app
    return {"X-Glean-Api-Key": app.state.glean_api_key}


async def test_list_feeds_returns_status(client, auth_headers):
    resp = await client.get("/api/v1/feeds", headers=auth_headers)
    assert resp.status_code == 200
    feeds = resp.json()
    assert len(feeds) == 1
    assert feeds[0]["name"] == "alpha"
    assert feeds[0]["last_success_at"] is None


async def test_list_feeds_unauthenticated_401(client):
    resp = await client.get("/api/v1/feeds")
    assert resp.status_code == 401


async def test_feed_status_returns_single(client, auth_headers):
    resp = await client.get("/api/v1/feeds/alpha/status", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["name"] == "alpha"


async def test_feed_status_404(client, auth_headers):
    resp = await client.get("/api/v1/feeds/nonexistent/status", headers=auth_headers)
    assert resp.status_code == 404


async def test_test_feed_dry_run(client, auth_headers, configured_app):
    _, state = configured_app
    await state.set_bootstrapped("alpha")
    resp = await client.post("/api/v1/feeds/alpha/test", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["feed"] == "alpha"
    assert body["sent"] == 0


async def test_test_feed_404(client, auth_headers):
    resp = await client.post("/api/v1/feeds/nonexistent/test", headers=auth_headers)
    assert resp.status_code == 404


async def test_run_feed_404(client, auth_headers):
    resp = await client.post("/api/v1/feeds/nonexistent/run", headers=auth_headers)
    assert resp.status_code == 404


async def test_run_feed_404_does_not_construct_telegram(
    client,
    auth_headers,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class ExplodingTelegramSender:
        def __init__(self, token: str) -> None:
            raise AssertionError("TelegramSender should not be built for missing feeds")

    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "secret-token")
    monkeypatch.setattr(feeds_routes, "TelegramSender", ExplodingTelegramSender)

    resp = await client.post("/api/v1/feeds/nonexistent/run", headers=auth_headers)

    assert resp.status_code == 404


async def test_run_feed_closes_route_owned_telegram(
    client,
    auth_headers,
    configured_app,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observed: dict[str, object] = {}

    class FakeTelegramSender:
        def __init__(self, token: str) -> None:
            observed["token"] = token
            observed["telegram"] = self
            self.close_count = 0

        async def aclose(self) -> None:
            self.close_count += 1

    async def fake_run_feed_once(
        cfg: object,
        state: object,
        name: str,
        *,
        dry_run: bool,
        telegram: FakeTelegramSender | None = None,
        event_bus: object | None = None,
    ) -> SimpleNamespace:
        observed["run"] = (cfg, state, name, dry_run, telegram, event_bus)
        return SimpleNamespace(
            feed=name,
            fetched=1,
            after_dedup=1,
            sent=1,
            dropped=0,
            overflow=0,
            duration_ms=1,
            error=None,
            skipped_reason=None,
            messages=["sent"],
        )

    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "secret-token")
    monkeypatch.setattr(feeds_routes, "TelegramSender", FakeTelegramSender)
    monkeypatch.setattr(feeds_routes, "run_feed_once", fake_run_feed_once)

    resp = await client.post("/api/v1/feeds/alpha/run", headers=auth_headers)

    assert resp.status_code == 200
    assert resp.json()["feed"] == "alpha"
    assert observed["token"] == "secret-token"
    app, _ = configured_app
    _, _, service_name, dry_run, telegram, event_bus = observed["run"]
    assert service_name == "alpha"
    assert dry_run is False
    assert telegram is observed["telegram"]
    assert event_bus is app.state.glean_event_bus
    assert observed["telegram"].close_count == 1


async def test_list_feeds_config_error_400(client, auth_headers, tmp_path: Path, monkeypatch):
    bad_cfg = tmp_path / "bad-feeds.yaml"
    bad_cfg.write_text("feeds: [", encoding="utf-8")
    monkeypatch.setenv("GLEAN_CONFIG", str(bad_cfg))

    resp = await client.get("/api/v1/feeds", headers=auth_headers)

    assert resp.status_code == 400
