"""In-memory error ring buffer for SPEC-05 observability.

Recent unhandled exceptions and validation failures, readable via
GET /api/v1/debug/errors so failures are diagnosable from the device with no
laptop terminal (Laos field-test requirement).

NEVER store secrets: no env values, tokens, or request bodies that may contain
credentials.
"""

import threading
from collections import deque
from datetime import datetime, timezone
from typing import Deque, Dict, List, Optional

MAX_ERRORS = 100


class ErrorLog:
    def __init__(self, maxlen: int = MAX_ERRORS):
        self._entries: Deque[Dict] = deque(maxlen=maxlen)  # auto-evicts oldest
        self._lock = threading.Lock()

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
            "message": message[:2000],
            "traceback": (traceback_str or "")[:8000],
        }
        with self._lock:
            self._entries.append(entry)

    def recent(self, limit: int = 50) -> List[Dict]:
        with self._lock:
            items = list(self._entries)
        return list(reversed(items))[:limit]  # newest first

    def count(self) -> int:
        with self._lock:
            return len(self._entries)

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()


error_log = ErrorLog()
