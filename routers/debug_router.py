"""Debug endpoints (SPEC-05). Gated: 404 when debug is off, so it is not
discoverable in production."""

from fastapi import APIRouter, HTTPException, status

from config.settings import settings
from monitoring.error_log import error_log

router = APIRouter(prefix="/api/v1/debug", tags=["debug"])


def _require_debug() -> None:
    # 404 (not 403) so the endpoint's existence isn't revealed in production.
    if not settings.debug:
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
