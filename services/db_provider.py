"""Database backend resolution.

If TB_SUPABASE_URL and TB_SUPABASE_KEY are both configured AND the supabase
client library is installed, use SupabaseService. Otherwise fall back to the
in-memory DatabaseService.

This module exports `db_service` — the resolved backend. All other modules
should import from here (or from services/__init__.py which re-exports it).
The name `db_service` is preserved so existing callers don't need changes.

Resolution order:
  1. Check settings.supabase_url AND settings.supabase_key are both non-empty
  2. Try to import and instantiate SupabaseService
  3. If either check fails → in-memory fallback

The chosen backend is logged loudly at import time so "writes to /dev/null"
failures are immediately obvious.
"""

import logging

logger = logging.getLogger("travelbuddy.db_provider")

_BACKEND_NAME: str = "UNKNOWN"


def _resolve_backend():
    """Determine which database backend to use."""
    global _BACKEND_NAME

    from config.settings import settings

    # Gate 1: are Supabase creds configured?
    if not settings.supabase_url or not settings.supabase_key:
        from services.database_service import db_service as _mem_db
        _BACKEND_NAME = "IN-MEMORY (no Supabase creds)"
        return _mem_db

    # Gate 2: is the supabase client library actually installed?
    try:
        from services.supabase_service import get_supabase_service
        svc = get_supabase_service()
    except ImportError:
        from services.database_service import db_service as _mem_db
        _BACKEND_NAME = "IN-MEMORY (supabase package not installed)"
        return _mem_db

    if svc is None:
        from services.database_service import db_service as _mem_db
        _BACKEND_NAME = "IN-MEMORY (SupabaseService init failed)"
        return _mem_db

    # Mask the URL for logging (show host only)
    url = settings.supabase_url
    host = url.replace("https://", "").replace("http://", "").split("/")[0]
    _BACKEND_NAME = f"SUPABASE ({host})"
    return svc


db_service = _resolve_backend()

# ─── LOUD startup log ─────────────────────────────────────────────────────────
# This line must be unmissable. If you see "IN-MEMORY" in production, signals
# are going to a volatile dict that vanishes on restart.
logger.warning("=" * 60)
logger.warning("DATABASE BACKEND: %s", _BACKEND_NAME)
logger.warning("=" * 60)
