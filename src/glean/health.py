"""Backwards-compat shim for the old aiohttp health server.

The health endpoint is now served by FastAPI from glean.api.app.
This module re-exports the original helpers for any test/code that still
imports them, but new code should use glean.api.app.make_app directly.
"""
from __future__ import annotations

import warnings
from typing import TYPE_CHECKING

from aiohttp import web

if TYPE_CHECKING:
    from glean.state.store import StateStore


def make_app(state: StateStore) -> web.Application:
    """Deprecated. Returns an aiohttp web.Application for backwards compat."""
    warnings.warn(
        "glean.health.make_app is deprecated; use glean.api.app.make_app instead",
        DeprecationWarning,
        stacklevel=2,
    )
    app = web.Application()

    async def healthz(_req: web.Request) -> web.Response:
        try:
            async with state.db.execute("SELECT 1") as cur:
                await cur.fetchone()
            return web.Response(text="ok\n")
        except Exception:
            return web.Response(status=503, text="db error\n")

    app.router.add_get("/healthz", healthz)
    return app


async def run_health_server(state: StateStore, port: int = 9090) -> web.AppRunner:
    """Deprecated. Use glean.api.app.run_api_server."""
    warnings.warn(
        "run_health_server is deprecated; use glean.api.app.run_api_server",
        DeprecationWarning,
        stacklevel=2,
    )
    app = make_app(state)
    runner = web.AppRunner(app, access_log=None)
    await runner.setup()
    site = web.TCPSite(runner, host="0.0.0.0", port=port)  # noqa: S104 # nosec
    await site.start()
    return runner
