from __future__ import annotations

from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from glean.api.app import make_app
from glean.state.store import StateStore

pytestmark = pytest.mark.asyncio


async def test_initialize_is_rate_limited_after_ten_requests(tmp_path: Path) -> None:
    state = StateStore(tmp_path / "state.db")
    await state.open()
    try:
        app = make_app(state, tmp_path / "state.db")
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            statuses = [(await client.get("/api/v1/initialize")).status_code for _ in range(11)]
    finally:
        await state.close()

    assert statuses[:10] == [200] * 10
    assert 429 in statuses[10:]


async def test_healthz_is_exempt_from_rate_limiting(tmp_path: Path) -> None:
    state = StateStore(tmp_path / "state.db")
    await state.open()
    try:
        app = make_app(state, tmp_path / "state.db")
        healthz_route = next(
            route for route in app.routes if getattr(route, "path", None) == "/healthz"
        )
    finally:
        await state.close()

    exempt_routes = app.state.limiter._exempt_routes
    route_name = f"{healthz_route.endpoint.__module__}.{healthz_route.endpoint.__name__}"
    assert route_name in exempt_routes
