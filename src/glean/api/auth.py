"""API key generation and verification.

Single-user self-hosted pattern (Sonarr-style): one auto-generated key
with a persisted verifier stored alongside the state DB. UI fetches the
plaintext key from /api/v1/initialize only when it is first created or
migrated, then includes it as X-Glean-Api-Key on subsequent requests.

Override via GLEAN_API_KEY env var. Disable auth entirely (loopback-only
deployments behind reverse proxies) via GLEAN_DISABLE_AUTH=1.
"""
from __future__ import annotations

import contextlib
import hashlib
import os
import secrets
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated

from fastapi import Header, HTTPException, Query, Request, status

_HASH_PREFIX = "pbkdf2_sha256"
_HASH_ITERATIONS = 200_000


@dataclass(frozen=True, slots=True)
class ApiKeyRecord:
    """Persisted verifier for an API key."""

    iterations: int
    salt_hex: str
    digest_hex: str


@dataclass(frozen=True, slots=True)
class ApiKeyMaterial:
    """Runtime API key material.

    ``plaintext`` is present only for a generated, migrated, rotated, or env-provided key in the
    current process. Restarts load only the persisted verifier.
    """

    plaintext: str | None
    record: ApiKeyRecord | None


def _key_path(state_db_path: Path) -> Path:
    """Locate the API key verifier file beside the state DB."""
    return state_db_path.parent / "api_key"


def _derive_digest(secret: str, *, iterations: int, salt: bytes) -> str:
    return hashlib.pbkdf2_hmac(
        "sha256",
        secret.encode("utf-8"),
        salt,
        iterations,
    ).hex()


def _hash_api_key(secret: str) -> ApiKeyRecord:
    salt = secrets.token_bytes(16)
    return ApiKeyRecord(
        iterations=_HASH_ITERATIONS,
        salt_hex=salt.hex(),
        digest_hex=_derive_digest(secret, iterations=_HASH_ITERATIONS, salt=salt),
    )


def _serialize_record(record: ApiKeyRecord) -> str:
    return f"{_HASH_PREFIX}${record.iterations}${record.salt_hex}${record.digest_hex}"


def _parse_record(raw: str) -> ApiKeyRecord | None:
    parts = raw.strip().split("$")
    if len(parts) != 4 or parts[0] != _HASH_PREFIX:
        return None
    try:
        iterations = int(parts[1])
        salt = bytes.fromhex(parts[2])
        digest = bytes.fromhex(parts[3])
    except ValueError:
        return None
    if iterations < 1 or not salt or len(digest) != hashlib.sha256().digest_size:
        return None
    return ApiKeyRecord(iterations=iterations, salt_hex=parts[2], digest_hex=parts[3])


def _persist_api_key_record(state_db_path: Path, record: ApiKeyRecord) -> None:
    """Persist an API key verifier beside the state DB."""
    key_file = _key_path(state_db_path)
    key_file.parent.mkdir(parents=True, exist_ok=True)
    key_file.write_text(_serialize_record(record), encoding="utf-8")
    with contextlib.suppress(OSError, NotImplementedError):
        key_file.chmod(0o600)


def get_or_create_api_key(state_db_path: Path) -> ApiKeyMaterial:
    """Return runtime API key material, generating and persisting a verifier if needed.

    Precedence:
      1. GLEAN_API_KEY env var (explicit override, no persisted verifier)
      2. Cached verifier file (no plaintext returned after restart)
      3. Newly generated key (plaintext returned once, verifier persisted)
    """
    if env_key := os.environ.get("GLEAN_API_KEY"):
        return ApiKeyMaterial(plaintext=env_key, record=None)

    key_file = _key_path(state_db_path)
    if key_file.is_file():
        raw = key_file.read_text(encoding="utf-8").strip()
        if record := _parse_record(raw):
            return ApiKeyMaterial(plaintext=None, record=record)
        if raw:
            record = _hash_api_key(raw)
            _persist_api_key_record(state_db_path, record)
            return ApiKeyMaterial(plaintext=raw, record=record)

    new_key = secrets.token_urlsafe(32)
    record = _hash_api_key(new_key)
    _persist_api_key_record(state_db_path, record)
    return ApiKeyMaterial(plaintext=new_key, record=record)


def rotate_api_key(state_db_path: Path) -> ApiKeyMaterial:
    """Generate a replacement API key and persist only its verifier."""
    new_key = secrets.token_urlsafe(32)
    record = _hash_api_key(new_key)
    _persist_api_key_record(state_db_path, record)
    return ApiKeyMaterial(plaintext=new_key, record=record)


def auth_disabled() -> bool:
    """True when auth should be bypassed entirely (GLEAN_DISABLE_AUTH=1)."""
    return os.environ.get("GLEAN_DISABLE_AUTH", "").lower() in ("1", "true", "yes")


def api_key_env_override_active() -> bool:
    """True when GLEAN_API_KEY owns the API key for this process."""
    return bool(os.environ.get("GLEAN_API_KEY"))


ExpectedApiKey = ApiKeyMaterial | str | Callable[[], ApiKeyMaterial | str | None]


def verify_api_key(material: ApiKeyMaterial, supplied_key: str | None) -> ApiKeyMaterial | None:
    """Validate a supplied API key and return material with plaintext cached on success."""
    if not supplied_key:
        return None
    if material.plaintext is not None and secrets.compare_digest(supplied_key, material.plaintext):
        return material
    if material.record is None:
        return None
    salt = bytes.fromhex(material.record.salt_hex)
    supplied_digest = _derive_digest(
        supplied_key,
        iterations=material.record.iterations,
        salt=salt,
    )
    if not secrets.compare_digest(supplied_digest, material.record.digest_hex):
        return None
    return ApiKeyMaterial(plaintext=supplied_key, record=material.record)


def _check_api_key(expected: ExpectedApiKey, supplied_key: str | None) -> ApiKeyMaterial | None:
    expected_key = expected() if callable(expected) else expected
    verified_material: ApiKeyMaterial | None = None
    if isinstance(expected_key, ApiKeyMaterial):
        verified_material = verify_api_key(expected_key, supplied_key)
        valid = verified_material is not None
    elif isinstance(expected_key, str) and supplied_key:
        valid = secrets.compare_digest(supplied_key, expected_key)
    else:
        valid = False
    if not valid:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid or missing X-Glean-Api-Key header",
        )
    return verified_material


def make_verify_api_key(
    expected: ExpectedApiKey,
    *,
    allow_query_for_events: bool = False,
    on_verified: Callable[[ApiKeyMaterial], None] | None = None,
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
        verified = _check_api_key(expected, x_glean_api_key)
        if verified is not None and on_verified is not None:
            on_verified(verified)

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
        verified = _check_api_key(expected, supplied_key)
        if verified is not None and on_verified is not None:
            on_verified(verified)

    return verify_events if allow_query_for_events else verify_header
