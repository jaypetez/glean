"""Authentication management routes."""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import APIRouter, HTTPException, Request, status

from glean.api.auth import api_key_env_override_active, rotate_api_key
from glean.api.models import RotateResponse

if TYPE_CHECKING:
    from slowapi import Limiter


async def rotate(request: Request) -> RotateResponse:
    """Rotate the single-user API key and return it once."""
    if api_key_env_override_active():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="API key rotation is disabled while GLEAN_API_KEY is set.",
        )
    db_path = request.app.state.glean_db_path
    material = rotate_api_key(db_path)
    if material.plaintext is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="API key rotation did not produce a new key.",
        )
    request.app.state.glean_api_key = material.plaintext
    request.app.state.glean_api_key_material = material
    return RotateResponse(api_key=material.plaintext)


def build_auth_router(limiter: Limiter) -> APIRouter:
    limited_router = APIRouter(prefix="/auth", tags=["auth"])
    limited_router.post("/rotate", response_model=RotateResponse)(
        limiter.limit("10/minute")(rotate)
    )
    return limited_router
