"""SPEC-43 Gap 4 slice 17: in-memory deletion tombstone and restore proof.

A tombstone records that a user asked to be deleted, so a simulated backup
restore of their wiped rows can be re-erased: honor_tombstones walks the
tombstoned ids and runs execute_erase for each, against the injected erase
backend. It is not a second delete implementation.

Process-local, like the token denylist: the set lives in this process only
and has no expiry. Remainders: a durable tombstone table, the vendor backup
window, a hosted restore drill, and recording the tombstone from the erase
route. Auth delete, denylist and cache purge stay on the HTTP erase path.

Standard library plus services.data_rights_erase. No SQL, files, sockets or
logging. Matching is exact on the stripped user id (never a prefix). ASCII
only.
"""

from __future__ import annotations

from typing import Any, Iterable, List, Optional, Set

from services.data_rights_erase import execute_erase

_tombstones: Set[str] = set()


def _clean(user_id: Any) -> Optional[str]:
    if not isinstance(user_id, str) or not user_id.strip():
        return None
    return user_id.strip()


def record_tombstone(user_id: str) -> None:
    """Record that *user_id* was erased. Idempotent; blank -> ValueError."""
    cleaned = _clean(user_id)
    if cleaned is None:
        raise ValueError("user_id is required")
    _tombstones.add(cleaned)


def is_tombstoned(user_id: str) -> bool:
    """Exact match after strip. Unknown or blank is False."""
    cleaned = _clean(user_id)
    return cleaned is not None and cleaned in _tombstones


def honor_tombstones(backend: Any, user_ids: Optional[Iterable[str]] = None) -> List[dict]:
    """Re-run execute_erase for each tombstoned id, in sorted order.

    With *user_ids*, only ids that are both listed and tombstoned are erased.
    If execute_erase raises, later ids are not honored and the same exception
    is re-raised.
    """
    if user_ids is None:
        targets = set(_tombstones)
    else:
        listed = {c for c in (_clean(u) for u in user_ids) if c is not None}
        targets = listed & _tombstones
    results: List[dict] = []
    for user_id in sorted(targets):
        results.append({"user_id": user_id, "tables": execute_erase(user_id, backend)})
    return results


def reset_tombstones() -> None:
    """Clear every tombstone (tests; later slices may use it too)."""
    _tombstones.clear()
