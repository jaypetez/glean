from __future__ import annotations

from typing import TYPE_CHECKING

from aiohttp import web

from glean.logging import get_logger

if TYPE_CHECKING:
    from glean.state.store import StateStore

logger = get_logger(__name__)


def make_app(state: StateStore) -> web.Application:
    app = web.Application()

    async def healthz(_req: web.Request) -> web.Response:
        try:
            async with state.db.execute("SELECT 1") as cur:
                await cur.fetchone()
            return web.Response(text="ok\n")
        except Exception as exc:
            return web.Response(status=503, text=f"db error: {exc}\n")

    app.router.add_get("/healthz", healthz)
    return app


async def run_health_server(state: StateStore, port: int = 9090) -> web.AppRunner:
    app = make_app(state)
    runner = web.AppRunner(app, access_log=None)
    await runner.setup()
    site = web.TCPSite(runner, host="0.0.0.0", port=port)  # noqa: S104
    await site.start()
    logger.info("health_listening", port=port)
    return runner
