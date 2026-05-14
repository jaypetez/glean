"""API key generation and verification.

Single-user self-hosted pattern (Sonarr-style): one auto-generated key
stored alongside the state DB. UI fetches it from /api/v1/initialize
(unauthenticated) on first load and includes it as X-Glean-Api-Key on
all subsequent requests.

Override via GLEAN_API_KEY env var. Disable auth entirely (loopback-only
deployments behind reverse proxies) via GLEAN_DISABLE_AUTH=1.
"""
from __future__ import annotations

import contextlib
import os
import secrets
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Annotated

from fastapi import Header, HTTPException, Query, Request, status


def _key_path(state_db_path: Path) -> Path:
    """Locate the API key file beside the state DB."""
    return state_db_path.parent / "api_key"


def _persist_api_key(state_db_path: Path, api_key: str) -> None:
    """Persist an API key beside the state DB."""
    key_file = _key_path(state_db_path)
    key_file.parent.mkdir(parents=True, exist_ok=True)
    key_file.write_text(api_key, encoding="utf-8")
    with contextlib.suppress(OSError, NotImplementedError):
        key_file.chmod(0o600)


def get_or_create_api_key(state_db_path: Path) -> str:
    """Return the configured API key, generating one on first call if needed.

    Precedence:
      1. GLEAN_API_KEY env var (explicit override)
      2. Cached key file (generated previously)
      3. Newly generated key (persisted for future runs)
    """
    if env_key := os.environ.get("GLEAN_API_KEY"):
        return env_key
    key_file = _key_path(state_db_path)
    if key_file.is_file():
        return key_file.read_text(encoding="utf-8").strip()
    new_key = secrets.token_urlsafe(32)
    _persist_api_key(state_db_path, new_key)
    return new_key


def rotate_api_key(state_db_path: Path) -> str:
    """Generate and persist a replacement API key."""
    new_key = secrets.token_urlsafe(32)
    _persist_api_key(state_db_path, new_key)
    return new_key


def auth_disabled() -> bool:
    """True when auth should be bypassed entirely (GLEAN_DISABLE_AUTH=1)."""
    return os.environ.get("GLEAN_DISABLE_AUTH", "").lower() in ("1", "true", "yes")


def api_key_env_override_active() -> bool:
    """True when GLEAN_API_KEY owns the API key for this process."""
    return bool(os.environ.get("GLEAN_API_KEY"))


def _check_api_key(expected: str | Callable[[], str | None], supplied_key: str | None) -> None:
    expected_key = expected() if callable(expected) else expected
    if (
        not expected_key
        or not supplied_key
        or not secrets.compare_digest(supplied_key, expected_key)
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid or missing X-Glean-Api-Key header",
        )


def make_verify_api_key(
    expected: str | Callable[[], str | None],
    *,
    allow_query_for_events: bool = False,
) -> Callable[..., Awaitable[None]]:
    """Build a FastAPI dependency that validates the X-Glean-Api-Key header."""

    async def verify_header(
        x_glean_api_key: Annotated[
            str | None,
            Header(alias="X-Glean-Api-Key"),
        ] = None,
    ) -> None:
        if auth_disabled():
            return
        _check_api_key(expected, x_glean_api_key)

    async def verify_events(
        request: Request,
        x_glean_api_key: Annotated[
            str | None,
            Header(alias="X-Glean-Api-Key"),
        ] = None,
        api_key: Annotated[str | None, Query(alias="api_key")] = None,
    ) -> None:
        if auth_disabled():
            return
        supplied_key = x_glean_api_key
        if supplied_key is None and request.scope.get("path") == "/api/v1/events":
            supplied_key = api_key
        _check_api_key(expected, supplied_key)

    return verify_events if allow_query_for_events else verify_header
