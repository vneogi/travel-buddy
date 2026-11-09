"""SPEC-43 Gap 4 slice 10: ordered export plan over the data-rights inventory.

Every table whose RIGHTS_MAP identity is not "none" has exactly one export
step here, the same required set as the erase plan. The order is
parent-first (the inverse concern of erase) so a later document builder can
nest trip children under their trip. A new identity table without a step
fails tests/test_spec43_g4_export_plan.py.

Pure data: no SQL, no backend, no route, no network, no logging, no print.
Standard library plus config.data_rights. ASCII only. execute_export and an
export backend are later slices; RIGHTS_MAP export stays "planned".
"""

from __future__ import annotations

from typing import Dict, FrozenSet, Iterable, List, Optional, Set, Tuple

from config.data_rights import RIGHTS_MAP

# RIGHTS_MAP identity -> (export fetch method, via join).
METHOD_FOR_IDENTITY: Dict[str, Tuple[str, Optional[str]]] = {
    "direct_user_id": ("fetch_where_user_id", None),
    "via_trip_states": ("fetch_via_trip_states", "trip_states.trip_id"),
    "via_party": ("fetch_via_party", "trip_party.party_id->trip_states"),
}
EXPORT_METHODS: FrozenSet[str] = frozenset(m for m, _via in METHOD_FOR_IDENTITY.values())
STEP_KEYS: FrozenSet[str] = frozenset({"table", "method", "via", "note"})


def required_tables(rights: Dict[str, dict] = RIGHTS_MAP) -> FrozenSet[str]:
    """Tables whose identity is not "none"."""
    return frozenset(t for t, entry in rights.items() if entry.get("identity") != "none")


EXPORT_REQUIRED: FrozenSet[str] = required_tables(RIGHTS_MAP)


def _step(table: str, note: str) -> dict:
    method, via = METHOD_FOR_IDENTITY[RIGHTS_MAP[table]["identity"]]
    return {"table": table, "method": method, "via": via, "note": note}


# Export order: parents first, so children can be nested under them later.
EXPORT_STEPS: Tuple[dict, ...] = (
    _step("user_tiers", "The user's tier and quota row."),
    _step("trip_states", "The user's trips; parent of every trip-scoped row."),
    _step("trip_node", "Nodes on the user's trips, resolved via trip_states."),
    _step("trip_edge", "Edges on the user's trips, resolved via trip_states."),
    _step("trip_party", "Parties on the user's trips, resolved via trip_states."),
    _step("party_member", "Members of parties on the user's trips, after trip_party."),
    _step("trip_command", "Command integrity rows keyed by user_id."),
    _step("signal", "Raw behavioral signals keyed by user_id."),
    _step("event_log", "Trip event history keyed by user_id."),
)


def _step_tables(steps: Iterable[dict]) -> Set[str]:
    return {s["table"] for s in steps}


def missing_export_steps(
    rights: Dict[str, dict] = RIGHTS_MAP, steps: Iterable[dict] = None
) -> Set[str]:
    """Required tables with no export step."""
    steps = EXPORT_STEPS if steps is None else steps
    return set(required_tables(rights)) - _step_tables(steps)


def extra_export_steps(
    rights: Dict[str, dict] = RIGHTS_MAP, steps: Iterable[dict] = None
) -> Set[str]:
    """Tables with an export step that are not required (none / catalog)."""
    steps = EXPORT_STEPS if steps is None else steps
    return _step_tables(steps) - set(required_tables(rights))


def plan_export(user_id: str) -> List[dict]:
    """Ordered export plan for *user_id*. Pure data; nothing is fetched."""
    if user_id is None or not isinstance(user_id, str) or not user_id.strip():
        raise ValueError("user_id is required")
    return [dict(step, user_id=user_id) for step in EXPORT_STEPS]
