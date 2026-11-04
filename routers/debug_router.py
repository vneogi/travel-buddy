"""Debug endpoints (SPEC-05). Gated: 404 when debug is off, so it is not
discoverable in production.

SPEC-43 Gap 10 part A: also 404 unless TB_DEBUG_ADMIN_TOKEN is configured.
"""

from typing import Optional

from fastapi import APIRouter, HTTPException, status

from config.settings import settings
from monitoring.error_log import error_log

router = APIRouter(prefix="/api/v1/debug", tags=["debug"])

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


@router.get("/errors")
async def recent_errors(limit: int = 50):
    """Recent errors, newest first. Readable from the phone's browser."""
    _require_debug()
    return {"count": error_log.count(), "errors": error_log.recent(limit=limit)}


@router.delete("/errors")
async def clear_errors():
    _require_debug()
    error_log.clear()
    return {"cleared": True}
