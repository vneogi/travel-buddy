"""SPEC-43 Gap 4 slice 13: read-only ExportBackend over an injected PostgREST client.

Implements the three export fetch methods with the same join rules as the
in-memory export backend, using the supabase-py builder shape
(client.table(t).select(...).eq(...) / .in_(...).execute()).

Safety rule: a read on a user-data table is never issued without an owner
filter. Every read carries eq("user_id", ...) or a non-empty in_(...) list;
when the owned id list is empty no read of that table is sent and the
result is [].

Read-only: no delete, update, upsert, insert or rpc. The client is injected;
this module does not import supabase and is not wired to any route or
provider.

Recorded limits:
- No pagination. PostgREST returns at most its configured max rows per
  request, so a very large table could be truncated silently; a later slice
  must page.
- No retries and no RPC.

No logging, no print. Standard library plus services.data_rights_export.
ASCII only.
"""

from __future__ import annotations

from typing import Any, Dict, List

from services.data_rights_export import EXPORT_REQUIRED, EXPORT_STEPS

_METHOD_FOR_TABLE: Dict[str, str] = {s["table"]: s["method"] for s in EXPORT_STEPS}


def _data(result: Any) -> list:
    return list(getattr(result, "data", None) or [])


def _copies(result: Any) -> List[dict]:
    return [dict(r) for r in _data(result)]


class SupabaseExportBackend:
    """ExportBackend backed by a supabase-py style client. Read-only."""

    def __init__(self, client: Any) -> None:
        self._client = client

    # --- checks (run before any client call) -------------------------------

    @staticmethod
    def _check(method: str, user_id: Any, table: Any) -> None:
        if not isinstance(user_id, str) or not user_id.strip():
            raise ValueError("user_id is required")
        if table not in EXPORT_REQUIRED:
            raise ValueError("table is not export-required")
        if _METHOD_FOR_TABLE[table] != method:
            raise ValueError("table is not exported by this method")

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

    # --- ExportBackend -------------------------------------------------------

    def fetch_where_user_id(self, user_id: str, table: str) -> List[dict]:
        self._check("fetch_where_user_id", user_id, table)
        result = self._client.table(table).select("*").eq("user_id", str(user_id)).execute()
        return _copies(result)

    def fetch_via_trip_states(self, user_id: str, table: str) -> List[dict]:
        self._check("fetch_via_trip_states", user_id, table)
        owned = self._owned_trip_ids(user_id)
        if not owned:
            return []
        result = self._client.table(table).select("*").in_("trip_id", owned).execute()
        return _copies(result)

    def fetch_via_party(self, user_id: str, table: str) -> List[dict]:
        self._check("fetch_via_party", user_id, table)
        owned = self._owned_trip_ids(user_id)
        if not owned:
            return []
        parties = self._owned_party_ids(owned)
        if not parties:
            return []
        result = self._client.table(table).select("*").in_("party_id", parties).execute()
        return _copies(result)
