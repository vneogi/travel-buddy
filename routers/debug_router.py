"""Debug endpoints (SPEC-05). Gated: 404 when debug is off, so it is not
discoverable in production.

SPEC-43 Gap 10 part A: also 404 unless TB_DEBUG_ADMIN_TOKEN is configured.
SPEC-43 Gap 10 part B: when configured, the X-Debug-Admin-Token header must
match it (401 otherwise). X-Debug-User-Id and traveller Bearer tokens never
open the ring; query, body and Authorization are not read.
"""

import hmac
from typing import Optional

from fastapi import APIRouter, HTTPException, Request, status

from config.settings import settings
from monitoring.error_log import error_log

router = APIRouter(prefix="/api/v1/debug", tags=["debug"])

DEBUG_ADMIN_HEADER = "X-Debug-Admin-Token"

# Shorter values are treated as unset (fail closed).
DEBUG_ADMIN_TOKEN_MIN_LEN = 16


def admin_token_configured(token: Optional[str]) -> bool:
    """True only for a string of at least 16 chars after strip."""
    if not isinstance(token, str):
        return False
    return len(token.strip()) >= DEBUG_ADMIN_TOKEN_MIN_LEN


def _require_debug() -> None:
    # 404 (not 403) so the endpoint's existence isn't revealed in production.
    if not settings.debug:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    # Fail closed: debug on but no admin token configured -> same 404.
    if not admin_token_configured(settings.debug_admin_token):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")


def admin_header_matches(supplied: Optional[str], expected: str) -> bool:
    """Constant-time compare on UTF-8 bytes. Length mismatch rejects first."""
    if not isinstance(supplied, str):
        return False
    supplied_b = supplied.encode("utf-8")
    expected_b = expected.encode("utf-8")
    if len(supplied_b) != len(expected_b):
        return False
    return hmac.compare_digest(supplied_b, expected_b)


def _require_debug_admin(request: Request) -> None:
    # Part A gates first: debug off or unset token -> 404.
    _require_debug()
    expected = settings.debug_admin_token.strip()
    # Header only. Never log the supplied value or the setting.
    supplied = request.headers.get(DEBUG_ADMIN_HEADER)
    if not admin_header_matches(supplied, expected):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized")


@router.get("/errors")
async def recent_errors(request: Request, limit: int = 50):
    """Recent errors, newest first. Requires the admin header."""
    _require_debug_admin(request)
    return {"count": error_log.count(), "errors": error_log.recent(limit=limit)}


@router.delete("/errors")
async def clear_errors(request: Request):
    _require_debug_admin(request)
    error_log.clear()
    return {"cleared": True}
