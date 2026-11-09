"""SPEC-43 Gap 4 slice 5: EraseBackend over an injected PostgREST client.

Implements the three erase methods with the same join rules as the
in-memory backend, using the client shape in services/supabase_service.py
(client.table(t).select(...) / .delete().eq(...) / .in_(...).execute()).

Safety rule: a delete is never issued without a row filter. Every delete
carries eq("user_id", ...) or a non-empty in_(...) list; when the owned id
list is empty no delete is sent at all.

The client is injected; this module does not import supabase. It is not
wired to any route or provider. No pagination, retries or RPC.
No logging, no print. Standard library plus services.data_rights_erase.
ASCII only.
"""

from __future__ import annotations

from typing import Any, Dict, List

from services.data_rights_erase import ERASE_REQUIRED, ERASE_STEPS

_METHOD_FOR_TABLE: Dict[str, str] = {s["table"]: s["method"] for s in ERASE_STEPS}


def _data(result: Any) -> list:
    return list(getattr(result, "data", None) or [])


class SupabaseEraseBackend:
    """EraseBackend backed by a supabase-py style client."""

    def __init__(self, client: Any) -> None:
        self._client = client

    # --- checks (run before any client call) -------------------------------

    @staticmethod
    def _check(method: str, user_id: str, table: str) -> None:
        if table not in ERASE_REQUIRED:
            raise ValueError("table is not erase-required")
        if _METHOD_FOR_TABLE[table] != method:
            raise ValueError(f"{table} is not erased by {method}")
        if user_id is None or not str(user_id).strip():
            raise ValueError("user_id is required")

    # --- ownership lookups ---------------------------------------------------

    def _owned_trip_ids(self, user_id: str) -> List[str]:
        result = (
            self._client.table("trip_states")
            .select("trip_id")
            .eq("user_id", str(user_id))
            .execute()
        )
        return sorted({str(r["trip_id"]) for r in _data(result) if r.get("trip_id") is not None})

    def _owned_party_ids(self, trip_ids: List[str]) -> List[str]:
        result = (
            self._client.table("trip_party").select("party_id").in_("trip_id", trip_ids).execute()
        )
        return sorted({str(r["party_id"]) for r in _data(result) if r.get("party_id") is not None})

    # --- EraseBackend --------------------------------------------------------

    def delete_where_user_id(self, user_id: str, table: str) -> int:
        self._check("delete_where_user_id", user_id, table)
        result = self._client.table(table).delete().eq("user_id", str(user_id)).execute()
        return len(_data(result))

    def delete_via_trip_states(self, user_id: str, table: str) -> int:
        self._check("delete_via_trip_states", user_id, table)
        owned = self._owned_trip_ids(user_id)
        if not owned:
            return 0
        result = self._client.table(table).delete().in_("trip_id", owned).execute()
        return len(_data(result))

    def delete_via_party(self, user_id: str, table: str) -> int:
        self._check("delete_via_party", user_id, table)
        owned = self._owned_trip_ids(user_id)
        if not owned:
            return 0
        parties = self._owned_party_ids(owned)
        if not parties:
            return 0
        result = self._client.table(table).delete().in_("party_id", parties).execute()
        return len(_data(result))
