"""SPEC-43 Gap 4 slice 18: nested, human-readable export document.

build_export_document regroups the flat per-table result of execute_export
(or the HTTP shape, table + rows) into one document grouped under trips:
trip children sit under their trip and party members under their party.
Every input row appears exactly once; rows that cannot be attached go to
"unattached", never dropped. Trip and party ids are compared as text,
because trip_party.trip_id is text while trip_states.trip_id is a uuid.

Pure: the input is not mutated and every output row is a deep copy. It adds
no identity data. Not wired to HTTP yet; route wiring, zip, PDF and
pagination are remainders.

Standard library plus services.data_rights_export. No SQL, network, files,
logging or print. ASCII only.
"""

from __future__ import annotations

import copy
from typing import Any, Dict, Iterable, List, Optional

from services.data_rights_export import EXPORT_REQUIRED

FORMAT = "travel-buddy-export"
VERSION = 1

# Trip-scoped tables attached by trip_id -> document key under each trip.
_TRIP_CHILD_KEYS = {
    "trip_node": "nodes",
    "trip_edge": "edges",
    "trip_command": "commands",
    "signal": "signals",
    "event_log": "events",
}
_UNATTACHED_TABLES = (
    "trip_node",
    "trip_edge",
    "trip_party",
    "party_member",
    "trip_command",
    "signal",
    "event_log",
)


def _key(value: Any) -> Optional[str]:
    """Join key compared as text; None stays None (never matches a trip)."""
    if value is None:
        return None
    return str(value)


def _unattach(document: dict, table: str, row: dict) -> None:
    document["unattached"][table].append(copy.deepcopy(row))


def _validated(results: Iterable[dict]) -> Dict[str, List[dict]]:
    by_table: Dict[str, List[dict]] = {}
    for entry in results:
        if not isinstance(entry, dict):
            raise ValueError("export entry must be a dict")
        table = entry.get("table")
        if table not in EXPORT_REQUIRED:
            raise ValueError("export contains a table that is not export-required")
        if table in by_table:
            raise ValueError("export lists a table more than once")
        rows = entry.get("rows")
        if not isinstance(rows, list):
            raise ValueError("export rows must be a list")
        by_table[table] = rows
    if set(by_table) != set(EXPORT_REQUIRED):
        raise ValueError("export is missing an export-required table")
    return by_table


def _empty_trip(row: dict) -> dict:
    return {
        "trip": copy.deepcopy(row),
        "nodes": [],
        "edges": [],
        "parties": [],
        "commands": [],
        "signals": [],
        "events": [],
    }


def build_export_document(results: Iterable[dict]) -> dict:
    """Group a caller's flat export under trips. Raises ValueError if invalid."""
    by_table = _validated(results)
    document: dict = {
        "format": FORMAT,
        "version": VERSION,
        "account": {"user_tiers": [copy.deepcopy(r) for r in by_table["user_tiers"]]},
        "trips": [],
        "unattached": {table: [] for table in _UNATTACHED_TABLES},
    }

    trips: Dict[str, dict] = {}
    for row in by_table["trip_states"]:
        if "trip_id" not in row:
            raise ValueError("trip_states row has no trip_id")
        trip_key = _key(row["trip_id"])
        if trip_key in trips:
            raise ValueError("export has duplicate trip ids")
        entry = _empty_trip(row)
        trips[trip_key] = entry
        document["trips"].append(entry)

    for table, doc_key in _TRIP_CHILD_KEYS.items():
        for row in by_table[table]:
            trip = trips.get(_key(row.get("trip_id")))
            if trip is None:
                _unattach(document, table, row)
            else:
                trip[doc_key].append(copy.deepcopy(row))

    attached_parties: Dict[str, dict] = {}
    seen_parties: set = set()
    for row in by_table["trip_party"]:
        party_key = _key(row.get("party_id"))
        if party_key is not None and party_key in seen_parties:
            raise ValueError("export has duplicate party ids")
        seen_parties.add(party_key)
        trip = trips.get(_key(row.get("trip_id")))
        if trip is None or party_key is None:
            _unattach(document, "trip_party", row)
            continue
        party = {"party": copy.deepcopy(row), "members": []}
        trip["parties"].append(party)
        attached_parties[party_key] = party

    for row in by_table["party_member"]:
        party = attached_parties.get(_key(row.get("party_id")))
        if party is None:
            _unattach(document, "party_member", row)
        else:
            party["members"].append(copy.deepcopy(row))

    return document


def count_rows(document: dict) -> Dict[str, int]:
    """Rows per source table, counted from the built document only."""
    counts = {table: 0 for table in sorted(EXPORT_REQUIRED)}
    counts["user_tiers"] += len(document["account"]["user_tiers"])
    for trip in document["trips"]:
        counts["trip_states"] += 1
        for table, doc_key in _TRIP_CHILD_KEYS.items():
            counts[table] += len(trip[doc_key])
        counts["trip_party"] += len(trip["parties"])
        for party in trip["parties"]:
            counts["party_member"] += len(party["members"])
    for table, rows in document["unattached"].items():
        counts[table] += len(rows)
    return counts
