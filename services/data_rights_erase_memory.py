"""SPEC-43 Gap 4 slice 4: in-memory EraseBackend that proves the wipe.

Holds rows only for ERASE_REQUIRED tables and implements the three erase
methods with the plan's join shapes:

- delete_where_user_id: rows whose user_id matches.
- delete_via_trip_states: rows whose trip_id belongs to the user in the
  current trip_states rows (so it must run before trip_states is erased).
- delete_via_party: party_member rows whose party_id belongs to a
  trip_party row on one of the user's current trips.

Test and reference use only. No SQL, no files, no sockets, no logging.
Standard library plus services.data_rights_erase. ASCII only.
"""

from __future__ import annotations

from typing import Callable, Dict, List, Set

from services.data_rights_erase import ERASE_REQUIRED, ERASE_STEPS

# Table -> erase method, from the plan.
_METHOD_FOR_TABLE: Dict[str, str] = {s["table"]: s["method"] for s in ERASE_STEPS}

# Keys a seeded row must carry, by erase method.
_REQUIRED_KEYS_BY_METHOD: Dict[str, tuple] = {
    "delete_where_user_id": ("user_id",),
    "delete_via_trip_states": ("trip_id",),
    "delete_via_party": ("party_id",),
}
# Join parents also need the key their children resolve through.
_EXTRA_KEYS_BY_TABLE: Dict[str, tuple] = {
    "trip_states": ("trip_id",),
    "trip_party": ("party_id",),
}


def _key(value) -> str:
    # trip_party.trip_id is text while trip_states.trip_id is uuid; compare
    # both as text, as the 0026 policy does with ts.trip_id::text.
    return str(value)


class InMemoryEraseBackend:
    """Dict-of-lists store for erase-required tables."""

    def __init__(self) -> None:
        self._store: Dict[str, List[dict]] = {t: [] for t in sorted(ERASE_REQUIRED)}

    # --- store -------------------------------------------------------------

    def _check_table(self, table: str) -> None:
        if table not in ERASE_REQUIRED:
            raise ValueError("table is not erase-required")

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

    # --- ownership (shared by rows_for_user and the deletes) ---------------

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
        if method == "delete_where_user_id":
            return lambda r: r.get("user_id") == user_id
        if method == "delete_via_trip_states":
            trips = self._owned_trip_ids(user_id)
            return lambda r: _key(r.get("trip_id")) in trips
        if method == "delete_via_party":
            parties = self._owned_party_ids(user_id)
            return lambda r: _key(r.get("party_id")) in parties
        raise ValueError("unknown erase method")

    def rows_for_user(self, user_id: str) -> Dict[str, List[dict]]:
        """Rows each table's erase method would remove now. No mutation."""
        out: Dict[str, List[dict]] = {}
        for table in sorted(ERASE_REQUIRED):
            match = self._matcher(_METHOD_FOR_TABLE[table], user_id)
            out[table] = [dict(r) for r in self._store[table] if match(r)]
        return out

    # --- EraseBackend ------------------------------------------------------

    def _delete(self, method: str, user_id: str, table: str) -> int:
        self._check_table(table)
        if _METHOD_FOR_TABLE[table] != method:
            raise ValueError(f"{table} is not erased by {method}")
        match = self._matcher(method, user_id)
        kept = [r for r in self._store[table] if not match(r)]
        removed = len(self._store[table]) - len(kept)
        self._store[table] = kept
        return removed

    def delete_where_user_id(self, user_id: str, table: str) -> int:
        return self._delete("delete_where_user_id", user_id, table)

    def delete_via_trip_states(self, user_id: str, table: str) -> int:
        return self._delete("delete_via_trip_states", user_id, table)

    def delete_via_party(self, user_id: str, table: str) -> int:
        return self._delete("delete_via_party", user_id, table)
