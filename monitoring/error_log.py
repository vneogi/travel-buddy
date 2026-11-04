"""In-memory error ring buffer for SPEC-05 observability.

Recent unhandled exceptions and validation failures, readable via
GET /api/v1/debug/errors so failures are diagnosable from the device with no
laptop terminal (Laos field-test requirement).

NEVER store secrets: no env values, tokens, or request bodies that may contain
credentials.

SPEC-43 Gap 10 retention: entries older than ERROR_RING_TTL_HOURS (or with a
missing/unparseable ts) are dropped on every record, recent and count. No
background thread; purge runs on the live paths only.
"""

import threading
from collections import deque
from datetime import datetime, timedelta, timezone
from typing import Deque, Dict, List, Optional

from monitoring.redact import redact_secrets

MAX_ERRORS = 100
ERROR_RING_TTL_HOURS = 24


def _entry_is_live(entry: Dict, cutoff: datetime) -> bool:
    """False for missing, unparseable, or expired ts. Naive ts is UTC."""
    ts = entry.get("ts") if isinstance(entry, dict) else None
    if not isinstance(ts, str) or not ts:
        return False
    try:
        parsed = datetime.fromisoformat(ts)
    except ValueError:
        return False
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed >= cutoff


class ErrorLog:
    def __init__(self, maxlen: int = MAX_ERRORS):
        self._entries: Deque[Dict] = deque(maxlen=maxlen)  # auto-evicts oldest
        self._lock = threading.Lock()

    def _drop_expired_locked(self) -> None:
        # Caller holds self._lock. Never logs dropped entries.
        cutoff = datetime.now(timezone.utc) - timedelta(hours=ERROR_RING_TTL_HOURS)
        if all(_entry_is_live(e, cutoff) for e in self._entries):
            return
        live = [e for e in self._entries if _entry_is_live(e, cutoff)]
        self._entries.clear()
        self._entries.extend(live)

    def clear_expired(self) -> None:
        """Drop entries past ERROR_RING_TTL_HOURS or with a bad ts."""
        with self._lock:
            self._drop_expired_locked()

    def record(
        self,
        *,
        request_id: str,
        method: str,
        path: str,
        status: int,
        exc_type: str,
        message: str,
        traceback_str: Optional[str] = None,
    ) -> None:
        entry = {
            "ts": datetime.now(tz=timezone.utc).isoformat(),
            "request_id": request_id,
            "method": method,
            "path": path,
            "status": status,
            "exc_type": exc_type,
            # SPEC-43 Gap 10: redact on write so every writer is covered.
            # Redact before truncation so a cut cannot expose a key prefix.
            "message": redact_secrets(message or "")[:2000],
            "traceback": redact_secrets(traceback_str or "")[:8000],
        }
        with self._lock:
            self._drop_expired_locked()
            self._entries.append(entry)

    def recent(self, limit: int = 50) -> List[Dict]:
        with self._lock:
            self._drop_expired_locked()
            items = list(self._entries)
        return list(reversed(items))[:limit]  # newest first

    def count(self) -> int:
        with self._lock:
            self._drop_expired_locked()
            return len(self._entries)

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()


error_log = ErrorLog()
