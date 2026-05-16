from __future__ import annotations

import os
import shutil
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import pytest
from hypothesis import HealthCheck, given, settings
from schemathesis import Case, openapi

from glean.api.app import make_app
from glean.security import ssrf
from glean.state.store import StateStore

_SCHEMA_DIR = Path("data") / "api-schema-fuzz"
_DB_PATH = _SCHEMA_DIR / "state.db"
_CONFIG_PATH = _SCHEMA_DIR / "feeds.yaml"
_API_KEY = "schema-fuzz-key"
_ORIGINAL_RESOLVE = ssrf._resolve


@contextmanager
def _patched_env(**updates: str) -> Iterator[None]:
    previous = {key: os.environ.get(key) for key in updates}
    os.environ.update(updates)
    try:
        yield
    finally:
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def _write_minimal_config() -> None:
    _SCHEMA_DIR.mkdir(parents=True, exist_ok=True)
    _CONFIG_PATH.write_text("defaults: {}\nskills: []\nfeeds: []\n", encoding="utf-8")


def _empty_resolve(_host: str) -> list[ssrf.IPAddress]:
    return []


_write_minimal_config()
with _patched_env(
    GLEAN_API_KEY=_API_KEY,
    GLEAN_DB_ROOT=str(Path.cwd()),
    GLEAN_ENABLE_DOCS="1",
    GLEAN_UI_DIST="__missing_ui_dist__",
):
    _STATE = StateStore(_DB_PATH)
    _APP = make_app(_STATE, _DB_PATH)
    schema = (
        openapi.from_asgi("/api/openapi.json", _APP)
        .exclude(path="/api/v1/events")
        .exclude(path_regex=r"^/api/v1/(feeds/[^/]+/)?digests$")
    )


@pytest.fixture(scope="module", autouse=True)
def _schema_state_cleanup() -> Iterator[None]:
    yield
    shutil.rmtree(_SCHEMA_DIR, ignore_errors=True)


@given(case=schema.as_strategy())
@settings(
    max_examples=25,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow],
)
def test_api_schema_inputs_do_not_500(case: Case) -> None:
    _write_minimal_config()
    ssrf._resolve = _empty_resolve
    try:
        with _patched_env(GLEAN_CONFIG=str(_CONFIG_PATH)):
            response = case.call(headers={"X-Glean-Api-Key": _APP.state.glean_api_key})
    finally:
        ssrf._resolve = _ORIGINAL_RESOLVE

    assert response.status_code != 500
