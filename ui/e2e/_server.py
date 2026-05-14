"""Playwright e2e server launcher."""
from __future__ import annotations

import asyncio
import os
import shutil
from pathlib import Path

import uvicorn

from glean.api.app import make_app
from glean.logging import configure_logging
from glean.state.store import StateStore


async def main() -> None:
    ui_dir = Path(__file__).resolve().parents[1]
    tmp_dir = ui_dir / "e2e" / ".tmp"
    tmp_dir.mkdir(parents=True, exist_ok=True)

    default_fixture = ui_dir / "e2e" / "fixtures" / "test-feeds.yaml"
    empty_fixture = ui_dir / "e2e" / "fixtures" / "empty-feeds.yaml"
    active_config = tmp_dir / "feeds.yaml"
    db_path = tmp_dir / "state.db"

    shutil.copyfile(default_fixture, active_config)

    os.environ.setdefault("GLEAN_DISABLE_AUTH", "1")
    os.environ.setdefault("GLEAN_TEST_MODE", "1")
    os.environ.setdefault("GLEAN_CONFIG", str(active_config))
    os.environ.setdefault("GLEAN_DB", str(db_path))
    os.environ.setdefault("GLEAN_TEST_CONFIG_FIXTURE", str(default_fixture))
    os.environ.setdefault("GLEAN_TEST_EMPTY_CONFIG_FIXTURE", str(empty_fixture))
    os.environ.setdefault("GLEAN_UI_DIST", str(ui_dir / "dist"))
    os.environ.setdefault("LOG_LEVEL", "WARNING")
    configure_logging(os.environ["LOG_LEVEL"])

    state = StateStore(db_path)
    await state.open()
    server = uvicorn.Server(
        uvicorn.Config(
            app=make_app(state, db_path),
            host="127.0.0.1",
            port=int(os.environ.get("GLEAN_E2E_PORT", "8080")),
            log_config=None,
            access_log=False,
        )
    )
    try:
        await server.serve()
    finally:
        await state.close()


if __name__ == "__main__":
    asyncio.run(main())
