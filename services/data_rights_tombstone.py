"""SPEC-43 Gap 4 slice 17: in-memory deletion tombstone and restore proof.

A tombstone records that a user asked to be deleted, so a simulated backup
restore of their wiped rows can be re-erased: honor_tombstones walks the
tombstoned ids and runs execute_erase for each, against the injected erase
backend. It is not a second delete implementation.

Process-local, like the token denylist: the set lives in this process only
and has no expiry. Auth delete, denylist and cache purge stay on the HTTP
erase path.

Durable path: record_tombstone_durable writes a store (for example
SupabaseTombstoneStore over migration 0027) and then the in-memory set; the
erase route calls it after the row erase succeeds. honor_tombstones with a
store reads the durable ids plus the in-memory set. Remainders: the vendor
backup window and a hosted restore drill.

Standard library plus services.data_rights_erase. No SQL, files, sockets or
logging. Matching is exact on the stripped user id (never a prefix). ASCII
only.
"""

from __future__ import annotations

from typing import Any, Iterable, List, Optional, Protocol, Set

from services.data_rights_erase import execute_erase

_tombstones: Set[str] = set()


class TombstoneStore(Protocol):
    """Durable tombstone store; failures raise TombstoneStoreError."""

    def put(self, user_id: str) -> None: ...

    def list_ids(self) -> List[str]: ...


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


def record_tombstone_durable(user_id: str, store: TombstoneStore) -> None:
    """Write *user_id* to the durable *store*, then to the in-memory set.

    Blank -> ValueError before the store is touched. If store.put raises
    (TombstoneStoreError), it propagates and the in-memory set is unchanged.
    """
    cleaned = _clean(user_id)
    if cleaned is None:
        raise ValueError("user_id is required")
    store.put(cleaned)
    record_tombstone(cleaned)


def is_tombstoned(user_id: str) -> bool:
    """Exact match after strip. Unknown or blank is False."""
    cleaned = _clean(user_id)
    return cleaned is not None and cleaned in _tombstones


def honor_tombstones(
    backend: Any,
    user_ids: Optional[Iterable[str]] = None,
    store: Optional[TombstoneStore] = None,
) -> List[dict]:
    """Re-run execute_erase for each tombstoned id, in sorted order.

    Without *user_ids*: with a *store*, the targets are store.list_ids() union
    the in-memory set (a TombstoneStoreError propagates); without a store,
    the in-memory set. With *user_ids*, behaviour is unchanged: only ids that
    are both listed and tombstoned in memory are erased.
    If execute_erase raises, later ids are not honored and the same exception
    is re-raised.
    """
    if user_ids is None:
        targets = set(_tombstones)
        if store is not None:
            targets |= {c for c in (_clean(u) for u in store.list_ids()) if c is not None}
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
