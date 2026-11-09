"""SPEC-43 Gap 4 slice 2: ordered erase plan over the data-rights inventory.

Every table whose RIGHTS_MAP identity is not "none" must have exactly one
erase step here, ordered dependents first so a trip-scoped row is removed
while its trip_states parent still exists to resolve ownership. A new
identity table without a step fails tests/test_spec43_g4_erase_plan.py.

Slice 3: execute_erase walks the plan against an injected EraseBackend in
order and stops on the first backend error, so a partial erase is visible to
the caller. There is still no SQL here and no concrete database backend.

No SQL, no connections, no files, no logging.
Standard library plus config.data_rights. ASCII only.
"""

from __future__ import annotations

from typing import Dict, FrozenSet, Iterable, List, Optional, Protocol, Set, Tuple

from config.data_rights import RIGHTS_MAP

# RIGHTS_MAP identity -> (erase method, via join).
METHOD_FOR_IDENTITY: Dict[str, Tuple[str, Optional[str]]] = {
    "direct_user_id": ("delete_where_user_id", None),
    "via_trip_states": ("delete_via_trip_states", "trip_states.trip_id"),
    "via_party": ("delete_via_party", "trip_party.party_id->trip_states"),
}
ERASE_METHODS: FrozenSet[str] = frozenset(m for m, _via in METHOD_FOR_IDENTITY.values())
STEP_KEYS: FrozenSet[str] = frozenset({"table", "method", "via", "note"})


def required_tables(rights: Dict[str, dict] = RIGHTS_MAP) -> FrozenSet[str]:
    """Tables whose identity is not "none"."""
    return frozenset(t for t, entry in rights.items() if entry.get("identity") != "none")


ERASE_REQUIRED: FrozenSet[str] = required_tables(RIGHTS_MAP)


def _step(table: str, note: str) -> dict:
    method, via = METHOD_FOR_IDENTITY[RIGHTS_MAP[table]["identity"]]
    return {"table": table, "method": method, "via": via, "note": note}


# Erase order: children first, trip_states last among trip data.
ERASE_STEPS: Tuple[dict, ...] = (
    _step("party_member", "Members of parties on the user's trips, before trip_party."),
    _step("trip_party", "Parties on the user's trips, resolved via trip_states."),
    _step("trip_edge", "Edges on the user's trips, resolved via trip_states."),
    _step("trip_node", "Nodes on the user's trips, resolved via trip_states."),
    _step("trip_command", "Command integrity rows keyed by user_id."),
    _step("signal", "Raw behavioral signals keyed by user_id."),
    _step("event_log", "Trip event history keyed by user_id."),
    _step("trip_states", "The user's trips; parent of every trip-scoped row."),
    _step("user_tiers", "The user's tier and quota row."),
)


def _step_tables(steps: Iterable[dict]) -> Set[str]:
    return {s["table"] for s in steps}


def missing_erase_steps(
    rights: Dict[str, dict] = RIGHTS_MAP, steps: Iterable[dict] = None
) -> Set[str]:
    """Required tables with no erase step."""
    steps = ERASE_STEPS if steps is None else steps
    return set(required_tables(rights)) - _step_tables(steps)


def extra_erase_steps(
    rights: Dict[str, dict] = RIGHTS_MAP, steps: Iterable[dict] = None
) -> Set[str]:
    """Tables with an erase step that are not required (none / catalog)."""
    steps = ERASE_STEPS if steps is None else steps
    return _step_tables(steps) - set(required_tables(rights))


def plan_erase(user_id: str) -> List[dict]:
    """Ordered erase plan for *user_id*. Pure data; nothing is executed."""
    if user_id is None or not isinstance(user_id, str) or not user_id.strip():
        raise ValueError("user_id is required")
    return [dict(step, user_id=user_id) for step in ERASE_STEPS]


class EraseBackend(Protocol):
    """Deletes one table's rows for a user. Returns rows affected."""

    def delete_where_user_id(self, user_id: str, table: str) -> int: ...

    def delete_via_trip_states(self, user_id: str, table: str) -> int: ...

    def delete_via_party(self, user_id: str, table: str) -> int: ...


class UnknownEraseMethodError(ValueError):
    """A step names a method that is not an EraseBackend method."""


def execute_erase(
    user_id: str, backend: EraseBackend, steps: Optional[Iterable[dict]] = None
) -> List[dict]:
    """Run each erase step on *backend*, in order.

    The plan (and user_id) is validated before any backend call. If a backend
    method raises, later steps are not called and the same exception is
    re-raised; nothing is swallowed.
    """
    # plan_erase raises ValueError on a blank user_id before any backend call.
    default_plan = plan_erase(user_id)
    plan = default_plan if steps is None else list(steps)
    for step in plan:
        if step.get("method") not in ERASE_METHODS:
            raise UnknownEraseMethodError("unknown erase method")
    results: List[dict] = []
    for step in plan:
        method = getattr(backend, step["method"])
        rows = method(user_id=user_id, table=step["table"])
        results.append(
            {
                "table": step["table"],
                "method": step["method"],
                "via": step.get("via"),
                "rows": int(rows),
            }
        )
    return results
