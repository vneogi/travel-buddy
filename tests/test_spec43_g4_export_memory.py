"""SPEC-43 Gap 4 slice 12: the in-memory backend proves caller-only export.

Two users are seeded across every export-required table. Each seeded row
also carries a test-only "seed_owner" tag so ownership is checked directly,
independent of the backend's join rules. No SQL, no network.
"""

import ast
import uuid
from pathlib import Path

import pytest

from config.data_rights import RIGHTS_MAP
from services import data_rights_export_memory as memory_module
from services.data_rights_export import EXPORT_REQUIRED, EXPORT_STEPS, execute_export
from services.data_rights_export_memory import InMemoryExportBackend

USER_A = "user-g4-xmem-A"
USER_B = "user-g4-xmem-B"


def _seed_user(backend, user_id, trips=2):
    backend.seed("user_tiers", {"user_id": user_id, "seed_owner": user_id})
    for t in range(trips):
        trip_id = uuid.uuid4()
        party_id = f"party-{user_id}-{t}"
        backend.seed("trip_states", {"user_id": user_id, "trip_id": trip_id, "seed_owner": user_id})
        for table in ("event_log", "signal", "trip_command"):
            backend.seed(table, {"user_id": user_id, "trip_id": trip_id, "seed_owner": user_id})
        for n in range(2):
            backend.seed("trip_node", {"trip_id": trip_id, "seq": n, "seed_owner": user_id})
        backend.seed("trip_edge", {"trip_id": trip_id, "seed_owner": user_id})
        # trip_party.trip_id is text in the schema.
        backend.seed(
            "trip_party", {"trip_id": str(trip_id), "party_id": party_id, "seed_owner": user_id}
        )
        for role in ("lead", "companion"):
            backend.seed(
                "party_member", {"party_id": party_id, "role": role, "seed_owner": user_id}
            )


def _counts(backend, owner):
    return {
        t: sum(1 for r in backend.rows(t) if r.get("seed_owner") == owner)
        for t in sorted(EXPORT_REQUIRED)
    }


@pytest.fixture
def backend():
    b = InMemoryExportBackend()
    _seed_user(b, USER_A)
    _seed_user(b, USER_B)
    return b


def test_seed_covers_every_export_required_table(backend):
    assert set(backend._store) == set(EXPORT_REQUIRED)
    assert all(n > 0 for n in _counts(backend, USER_A).values())
    assert all(n > 0 for n in _counts(backend, USER_B).values())


def test_execute_export_returns_only_the_callers_rows(backend):
    before_a, before_b = _counts(backend, USER_A), _counts(backend, USER_B)
    results = execute_export(USER_A, backend)
    assert [r["table"] for r in results] == [s["table"] for s in EXPORT_STEPS]
    owners = {row.get("seed_owner") for r in results for row in r["rows"]}
    assert owners == {USER_A}
    per_table = {r["table"]: len(r["rows"]) for r in results}
    assert per_table == before_a
    assert sum(per_table.values()) == sum(before_a.values())
    # Fetch is read-only: both users' store counts are unchanged.
    assert _counts(backend, USER_B) == before_b
    assert _counts(backend, USER_A) == before_a


def test_other_users_rows_survive_and_export_separately(backend):
    before_a, before_b = _counts(backend, USER_A), _counts(backend, USER_B)
    results_a = execute_export(USER_A, backend)
    assert {row["seed_owner"] for r in results_a for row in r["rows"]} == {USER_A}
    results_b = execute_export(USER_B, backend)
    rows_b = [row for r in results_b for row in r["rows"]]
    assert rows_b
    assert {row["seed_owner"] for row in rows_b} == {USER_B}
    assert {r["table"]: len(r["rows"]) for r in results_b} == before_b
    assert _counts(backend, USER_A) == before_a
    assert _counts(backend, USER_B) == before_b


def test_fetch_via_trip_states_resolves_through_trip_states(backend):
    a_trips = {str(r["trip_id"]) for r in backend.rows("trip_states") if r["user_id"] == USER_A}
    nodes = backend.fetch_via_trip_states(USER_A, "trip_node")
    assert len(nodes) == 4
    assert {n["seed_owner"] for n in nodes} == {USER_A}
    assert {str(n["trip_id"]) for n in nodes} == a_trips
    assert _counts(backend, USER_B)["trip_node"] == 4
    assert _counts(backend, USER_A)["trip_node"] == 4
    members = backend.fetch_via_party(USER_A, "party_member")
    assert len(members) == 4 and {m["seed_owner"] for m in members} == {USER_A}


@pytest.mark.parametrize("table", ["cached_responses", "venues_rag", "dish_glossary", "nope"])
def test_seed_rejects_catalog_or_cached_responses(table):
    b = InMemoryExportBackend()
    with pytest.raises(ValueError):
        b.seed(table, {"user_id": USER_A, "trip_id": "t"})
    assert table not in b._store
    assert b.rows(table) == []
    none_tables = {t for t, e in RIGHTS_MAP.items() if e["identity"] == "none"}
    assert not none_tables & set(b._store)
    with pytest.raises(ValueError):
        b.seed("trip_states", {"user_id": USER_A})  # missing trip_id
    with pytest.raises(ValueError):
        b.seed("trip_party", {"trip_id": "t"})  # missing party_id


def test_fetch_rejects_blank_user_id_and_method_mismatch(backend):
    snapshot = {t: backend.rows(t) for t in EXPORT_REQUIRED}
    for bad in (None, "", "   ", 42):
        with pytest.raises(ValueError):
            backend.fetch_where_user_id(bad, "user_tiers")
    with pytest.raises(ValueError):
        backend.fetch_where_user_id(USER_A, "trip_node")
    with pytest.raises(ValueError):
        backend.fetch_via_trip_states(USER_A, "user_tiers")
    with pytest.raises(ValueError):
        backend.fetch_via_party(USER_A, "trip_party")
    with pytest.raises(ValueError):
        backend.fetch_where_user_id(USER_A, "cached_responses")
    assert {t: backend.rows(t) for t in EXPORT_REQUIRED} == snapshot


def test_exported_rows_are_detached_from_the_store(backend):
    results = execute_export(USER_A, backend)
    tiers = next(r for r in results if r["table"] == "user_tiers")
    tiers["rows"][0]["seed_owner"] = "mutated"
    tiers["rows"].append({"user_id": USER_A, "seed_owner": "injected"})
    direct = backend.fetch_where_user_id(USER_A, "user_tiers")
    direct[0]["user_id"] = "mutated"
    stored = [r for r in backend.rows("user_tiers") if r["user_id"] == USER_A]
    assert stored == [{"user_id": USER_A, "seed_owner": USER_A}]
    assert not hasattr(backend, "delete_where_user_id")


def test_export_memory_module_has_no_forbidden_imports():
    source = Path(memory_module.__file__).read_text(encoding="utf-8")
    assert source.isascii()
    roots = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            roots |= {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom):
            roots.add((node.module or "").split(".")[0])
    assert roots <= {"__future__", "typing", "services"}, roots
    assert "print(" not in source and "import logging" not in source
