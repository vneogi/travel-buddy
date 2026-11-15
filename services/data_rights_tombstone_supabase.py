"""SPEC-43 Gap 4: durable tombstone store over the Supabase service client.

SupabaseTombstoneStore writes and reads public.data_rights_tombstone
(migration 0027) through the existing supabase-py style service-key client;
it never builds a client of its own. put() is an idempotent upsert on
user_id. list_ids() returns every stored id, sorted, reading in pages so a
large table is never silently truncated.

Every failure raises TombstoneStoreError whose message is one closed code.
Nothing here logs, and no row, user id, key, URL or response body is put on
an exception. No sockets of its own, no SQL text. ASCII only.
"""

from __future__ import annotations

from typing import Any, List

TOMBSTONE_TABLE = "data_rights_tombstone"
TOMBSTONE_SOURCE = "me_erase"
PAGE_SIZE = 1000

WRITE_FAILED = "tombstone_write_failed"
READ_FAILED = "tombstone_read_failed"
STORE_ERROR_CODES = frozenset({WRITE_FAILED, READ_FAILED})


class TombstoneStoreError(Exception):
    """Durable tombstone store failure. The message is the closed code only."""

    def __init__(self, code: str) -> None:
        if code not in STORE_ERROR_CODES:
            raise ValueError("unknown tombstone store error code")
        super().__init__(code)
        self.code = code


def _clean(user_id: Any) -> str:
    if not isinstance(user_id, str) or not user_id.strip():
        raise ValueError("user_id is required")
    return user_id.strip()


class SupabaseTombstoneStore:
    """Durable tombstones in data_rights_tombstone (service_role only)."""

    def __init__(self, client: Any) -> None:
        self._client = client

    def put(self, user_id: str) -> None:
        """Upsert one tombstone. Idempotent on user_id. Blank -> ValueError."""
        cleaned = _clean(user_id)
        try:
            self._client.table(TOMBSTONE_TABLE).upsert(
                {"user_id": cleaned, "source": TOMBSTONE_SOURCE},
                on_conflict="user_id",
            ).execute()
        except Exception:
            raise TombstoneStoreError(WRITE_FAILED) from None

    def list_ids(self) -> List[str]:
        """Every stored user_id, stripped and sorted."""
        ids = set()
        start = 0
        try:
            while True:
                result = (
                    self._client.table(TOMBSTONE_TABLE)
                    .select("user_id")
                    .order("user_id")
                    .range(start, start + PAGE_SIZE - 1)
                    .execute()
                )
                rows = getattr(result, "data", None)
                if not isinstance(rows, list):
                    raise TypeError("rows")
                for row in rows:
                    ids.add(_clean(row["user_id"]))
                if len(rows) < PAGE_SIZE:
                    break
                start += PAGE_SIZE
        except Exception:
            raise TombstoneStoreError(READ_FAILED) from None
        return sorted(ids)
