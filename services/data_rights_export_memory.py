"""SPEC-43 Gap 4 slice 12: in-memory ExportBackend that proves caller-only export.

Holds rows only for EXPORT_REQUIRED tables and implements the three export
fetch methods with the plan's join shapes:

- fetch_where_user_id: rows whose user_id matches.
- fetch_via_trip_states: rows whose trip_id belongs to the user in the
  current trip_states rows.
- fetch_via_party: party_member rows whose party_id belongs to a trip_party
  row on one of the user's current trips.

Read-only: fetches return shallow copies and never mutate the store. There
is no delete method. Test and reference use only. No SQL, no files, no
sockets, no logging, no print. Standard library plus
services.data_rights_export. ASCII only.
"""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Set

from services.data_rights_export import EXPORT_REQUIRED, EXPORT_STEPS

# Table -> export method, from the plan.
_METHOD_FOR_TABLE: Dict[str, str] = {s["table"]: s["method"] for s in EXPORT_STEPS}

# Keys a seeded row must carry, by export method.
_REQUIRED_KEYS_BY_METHOD: Dict[str, tuple] = {
    "fetch_where_user_id": ("user_id",),
    "fetch_via_trip_states": ("trip_id",),
    "fetch_via_party": ("party_id",),
}
# Join parents also need the key their children resolve through.
_EXTRA_KEYS_BY_TABLE: Dict[str, tuple] = {
    "trip_states": ("trip_id",),
    "trip_party": ("party_id",),
}


def _key(value: Any) -> str:
    # trip_party.trip_id is text while trip_states.trip_id is uuid; compare
    # both as text, as the 0026 policy does with ts.trip_id::text.
    return str(value)


class InMemoryExportBackend:
    """Dict-of-lists store for export-required tables. Read-only fetches."""

    def __init__(self) -> None:
        self._store: Dict[str, List[dict]] = {t: [] for t in sorted(EXPORT_REQUIRED)}

    # --- store -------------------------------------------------------------

    def _check_table(self, table: Any) -> None:
        if table not in EXPORT_REQUIRED:
            raise ValueError("table is not export-required")

    def seed(self, table: str, row: dict) -> None:
        self._check_table(table)
        needed = _REQUIRED_KEYS_BY_METHOD[_METHOD_FOR_TABLE[table]]
        needed = needed + _EXTRA_KEYS_BY_TABLE.get(table, ())
        missing = [k for k in needed if k not in row or row[k] is None]
        if missing:
            raise ValueError(f"row for {table} is missing {missing}")
        self._store[table].append(dict(row))

    def rows(self, table: str) -> List[dict]:
        return [dict(r) for r in self._store.get(table, [])]

    # --- ownership ---------------------------------------------------------

    def _owned_trip_ids(self, user_id: str) -> Set[str]:
        return {
            _key(r["trip_id"]) for r in self._store["trip_states"] if r.get("user_id") == user_id
        }

    def _owned_party_ids(self, user_id: str) -> Set[str]:
        trips = self._owned_trip_ids(user_id)
        return {
            _key(r["party_id"])
            for r in self._store["trip_party"]
            if _key(r.get("trip_id")) in trips
        }

    def _matcher(self, method: str, user_id: str) -> Callable[[dict], bool]:
        if method == "fetch_where_user_id":
            return lambda r: r.get("user_id") == user_id
        if method == "fetch_via_trip_states":
            trips = self._owned_trip_ids(user_id)
            return lambda r: _key(r.get("trip_id")) in trips
        if method == "fetch_via_party":
            parties = self._owned_party_ids(user_id)
            return lambda r: _key(r.get("party_id")) in parties
        raise ValueError("unknown export method")

    # --- ExportBackend -----------------------------------------------------

    def _fetch(self, method: str, user_id: Any, table: Any) -> List[dict]:
        if not isinstance(user_id, str) or not user_id.strip():
            raise ValueError("user_id is required")
        self._check_table(table)
        if _METHOD_FOR_TABLE[table] != method:
            raise ValueError(f"{table} is not exported by {method}")
        match = self._matcher(method, user_id)
        return [dict(r) for r in self._store[table] if match(r)]

    def fetch_where_user_id(self, user_id: str, table: str) -> List[dict]:
        return self._fetch("fetch_where_user_id", user_id, table)

    def fetch_via_trip_states(self, user_id: str, table: str) -> List[dict]:
        return self._fetch("fetch_via_trip_states", user_id, table)

    def fetch_via_party(self, user_id: str, table: str) -> List[dict]:
        return self._fetch("fetch_via_party", user_id, table)
