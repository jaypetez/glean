from __future__ import annotations

from types import SimpleNamespace

import pytest
from aiohttp import web
from aiohttp.test_utils import make_mocked_request

import glean.health as health_module

pytestmark = pytest.mark.asyncio


class _Cursor:
    async def __aenter__(self) -> _Cursor:
        return self

    async def __aexit__(self, *_args: object) -> None:
        return None

    async def fetchone(self) -> tuple[int]:
        return (1,)


class _Db:
    def __init__(self, *, error: Exception | None = None) -> None:
        self.error = error
        self.queries: list[str] = []

    def execute(self, query: str) -> _Cursor:
        self.queries.append(query)
        if self.error is not None:
            raise self.error
        return _Cursor()


async def test_health_shim_endpoint_returns_ok() -> None:
    state = SimpleNamespace(db=_Db())
    with pytest.deprecated_call(match="glean.health.make_app is deprecated"):
        app = health_module.make_app(state)
    request = make_mocked_request("GET", "/healthz", app=app)

    response = await app._handle(request)

    assert response.status == 200
    assert response.text == "ok\n"
    assert state.db.queries == ["SELECT 1"]


async def test_health_shim_endpoint_reports_db_errors() -> None:
    state = SimpleNamespace(db=_Db(error=RuntimeError("boom")))
    with pytest.deprecated_call(match="glean.health.make_app is deprecated"):
        app = health_module.make_app(state)
    request = make_mocked_request("GET", "/healthz", app=app)

    response = await app._handle(request)

    assert response.status == 503
    assert response.text == "db error: boom\n"


async def test_run_health_server_starts_tcp_site(monkeypatch: pytest.MonkeyPatch) -> None:
    started: dict[str, object] = {}

    class FakeSite:
        def __init__(self, runner: web.AppRunner, *, host: str, port: int) -> None:
            started["runner"] = runner
            started["host"] = host
            started["port"] = port

        async def start(self) -> None:
            started["started"] = True

    monkeypatch.setattr(web, "TCPSite", FakeSite)

    with pytest.warns(DeprecationWarning) as captured_warnings:
        runner = await health_module.run_health_server(SimpleNamespace(db=_Db()), port=9123)

    assert [str(warning.message) for warning in captured_warnings] == [
        "run_health_server is deprecated; use glean.api.app.run_api_server",
        "glean.health.make_app is deprecated; use glean.api.app.make_app instead",
    ]

    assert isinstance(runner, web.AppRunner)
    assert started == {
        "runner": runner,
        "host": "0.0.0.0",
        "port": 9123,
        "started": True,
    }

    await runner.cleanup()
