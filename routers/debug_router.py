"""Debug endpoints (SPEC-05). Gated: 404 when debug is off, so it is not
discoverable in production.

SPEC-43 Gap 10: even with debug on, the ring needs administrator
authorization -- a shared token in the X-Debug-Admin-Token header. The
traveller identity (X-Debug-User-Id, Bearer JWT) is never an administrator.
"""

import hmac
from typing import Optional

from fastapi import APIRouter, HTTPException, Request, status

from config.settings import settings
from monitoring.error_log import error_log

router = APIRouter(prefix="/api/v1/debug", tags=["debug"])

ADMIN_TOKEN_HEADER = "X-Debug-Admin-Token"
MIN_ADMIN_TOKEN_LEN = 16

# Provider / database secrets must never double as the admin token.
_NOT_ADMIN_TOKEN_FIELDS = (
    "litellm_api_key",
    "gemini_api_key",
    "google_maps_api_key",
    "google_places_api_key",
    "openweather_api_key",
    "supabase_key",
    "supabase_jwt_secret",
    "stripe_secret_key",
    "stripe_webhook_secret",
)


def _not_found() -> HTTPException:
    # 404 (not 403) so the endpoint's existence isn't revealed.
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")


def _configured_admin_token() -> Optional[str]:
    """The usable admin token, or None (fail closed)."""
    token = settings.debug_admin_token
    if not isinstance(token, str) or len(token) < MIN_ADMIN_TOKEN_LEN:
        return None
    for field in _NOT_ADMIN_TOKEN_FIELDS:
        if getattr(settings, field, None) == token:
            return None
    return token


def _require_debug_admin(request: Request) -> None:
    if not settings.debug:
        raise _not_found()
    expected = _configured_admin_token()
    if expected is None:
        raise _not_found()
    provided = request.headers.get(ADMIN_TOKEN_HEADER)
    expected_b = expected.encode("utf-8")
    provided_b = provided.encode("utf-8") if provided is not None else b""
    # compare_digest requires equal lengths for constant-time behaviour on
    # bytes; reject a length mismatch before calling it. Never log either.
    if provided is None or len(provided_b) != len(expected_b):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized")
    if not hmac.compare_digest(provided_b, expected_b):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized")


@router.get("/errors")
async def recent_errors(request: Request, limit: int = 50):
    """Recent errors, newest first. Administrator only."""
    _require_debug_admin(request)
    return {"count": error_log.count(), "errors": error_log.recent(limit=limit)}


@router.delete("/errors")
async def clear_errors(request: Request):
    _require_debug_admin(request)
    error_log.clear()
    return {"cleared": True}
