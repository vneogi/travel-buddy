"""SPEC-43 Gap 4 slice 8: process-local erase denylist.

After a successful POST /api/v1/me/erase the caller's user_id is denied for
DENY_TTL_SECONDS, and resolve_identity refuses a denied id with 401. This
closes the window in which a still-unexpired access token would keep
verifying (and recreate a user_tiers row) after the Auth user is deleted.

Process-local, like the error ring: entries live in this process only and
expire on read. Sharing across Cloud Run instances, per-jti revocation and
settings knobs are remainders, not this slice.

No network, no supabase import, no logging, no print. ASCII only.
"""

from __future__ import annotations

import threading
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

DENY_TTL_SECONDS = 3600  # covers the default Supabase access-token lifetime

_lock = threading.Lock()
_denied: Dict[str, datetime] = {}


def _now(now: Optional[datetime]) -> datetime:
    if now is None:
        return datetime.now(timezone.utc)
    if now.tzinfo is None:
        return now.replace(tzinfo=timezone.utc)
    return now


def _valid(user_id: Any) -> bool:
    return isinstance(user_id, str) and bool(user_id.strip())


def deny_identity(user_id: str, *, now: Optional[datetime] = None) -> datetime:
    """Deny *user_id* until now + DENY_TTL_SECONDS; re-deny refreshes it."""
    if not _valid(user_id):
        raise ValueError("user_id is required")
    until = _now(now) + timedelta(seconds=DENY_TTL_SECONDS)
    with _lock:
        current = _denied.get(user_id)
        if current is None or until > current:
            _denied[user_id] = until
        return _denied[user_id]


def is_denied(user_id: str, *, now: Optional[datetime] = None) -> bool:
    """True while now < until. Blank / non-string is False; never raises."""
    if not _valid(user_id):
        return False
    moment = _now(now)
    with _lock:
        for key in [k for k, until in _denied.items() if moment >= until]:
            del _denied[key]
        until = _denied.get(user_id)
        return until is not None and moment < until


def reset_denylist() -> None:
    """Clear every entry (tests)."""
    with _lock:
        _denied.clear()
