"""Authentication management routes."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, status

from glean.api.auth import api_key_env_override_active, rotate_api_key
from glean.api.models import RotateResponse

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/rotate", response_model=RotateResponse)
async def rotate(request: Request) -> RotateResponse:
    """Rotate the single-user API key and return it once."""
    if api_key_env_override_active():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="API key rotation is disabled while GLEAN_API_KEY is set.",
        )
    db_path = request.app.state.glean_db_path
    new_key = rotate_api_key(db_path)
    request.app.state.glean_api_key = new_key
    return RotateResponse(api_key=new_key)
