"""SPEC-43 Gap 4 slice 4: the in-memory backend proves a full, scoped wipe.

Two users are seeded across every erase-required table. Each seeded row also
carries a test-only "seed_owner" tag so leftovers are counted directly from
the store, independent of the backend's join rules. No SQL, no network.
"""

import uuid

import pytest

from services.data_rights_erase import ERASE_REQUIRED, ERASE_STEPS, execute_erase
from services.data_rights_erase_memory import InMemoryEraseBackend

USER_A = "user-g4-mem-A"
USER_B = "user-g4-mem-B"


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
        for t in sorted(ERASE_REQUIRED)
    }


@pytest.fixture
def backend():
    b = InMemoryEraseBackend()
    _seed_user(b, USER_A)
    _seed_user(b, USER_B)
    return b


def test_seed_covers_every_required_table(backend):
    assert all(n > 0 for n in _counts(backend, USER_A).values())
    assert all(n > 0 for n in _counts(backend, USER_B).values())
    # Before erase, the backend's join view finds exactly A's seeded rows.
    view = backend.rows_for_user(USER_A)
    assert set(view) == set(ERASE_REQUIRED)
    assert {t: len(rows) for t, rows in view.items()} == _counts(backend, USER_A)


def test_execute_erase_leaves_zero_rows_for_target_user(backend):
    before = sum(_counts(backend, USER_A).values())
    assert before > 0
    results = execute_erase(USER_A, backend)
    assert [r["table"] for r in results] == [s["table"] for s in ERASE_STEPS]
    assert sum(r["rows"] for r in results) == before
    leftover = backend.rows_for_user(USER_A)
    assert set(leftover) == set(ERASE_REQUIRED)
    for table in ERASE_REQUIRED:
        assert leftover[table] == [], table
    # Independent of the join rules: no row tagged for A remains anywhere.
    assert _counts(backend, USER_A) == {t: 0 for t in ERASE_REQUIRED}
    assert [r for r in backend.rows("trip_states") if r["user_id"] == USER_B]
    assert [r for r in backend.rows("party_member") if r["seed_owner"] == USER_B]


def test_delete_via_trip_states_uses_trip_states_before_parent_delete(backend):
    a_trips = {r["trip_id"] for r in backend.rows("trip_states") if r["user_id"] == USER_A}
    removed = backend.delete_via_trip_states(USER_A, "trip_node")
    assert removed == 4
    assert not [r for r in backend.rows("trip_node") if r["trip_id"] in a_trips]
    assert {r["trip_id"] for r in backend.rows("trip_states") if r["user_id"] == USER_A} == a_trips
    assert _counts(backend, USER_B)["trip_node"] == 4


def test_children_are_orphaned_if_parent_goes_first():
    # Why the plan erases children first: with trip_states gone, the via
    # methods can no longer resolve ownership.
    b = InMemoryEraseBackend()
    _seed_user(b, USER_A, trips=1)
    b.delete_where_user_id(USER_A, "trip_states")
    assert b.delete_via_trip_states(USER_A, "trip_node") == 0
    assert b.delete_via_party(USER_A, "party_member") == 0
    assert _counts(b, USER_A)["trip_node"] == 2


def test_other_users_rows_survive_full_erase(backend):
    snapshot_b = _counts(backend, USER_B)
    rows_b = {t: backend.rows_for_user(USER_B)[t] for t in ERASE_REQUIRED}
    execute_erase(USER_A, backend)
    assert _counts(backend, USER_B) == snapshot_b
    assert backend.rows_for_user(USER_B) == rows_b


@pytest.mark.parametrize("table", ["venues_rag", "cached_responses", "signal_type", "nope"])
def test_seed_rejects_catalog_table(table):
    b = InMemoryEraseBackend()
    with pytest.raises(ValueError):
        b.seed(table, {"user_id": USER_A})
    assert b.rows(table) == []


@pytest.mark.parametrize(
    "table,row",
    [
        ("user_tiers", {"trip_id": "t"}),
        ("trip_node", {"user_id": USER_A}),
        ("party_member", {"trip_id": "t"}),
        ("trip_states", {"user_id": USER_A}),
        ("trip_party", {"trip_id": "t"}),
    ],
)
def test_seed_rejects_wrong_row_shape(table, row):
    with pytest.raises(ValueError):
        InMemoryEraseBackend().seed(table, row)


def test_seed_and_rows_return_copies():
    b = InMemoryEraseBackend()
    row = {"user_id": USER_A}
    b.seed("user_tiers", row)
    row["user_id"] = "mutated"
    b.rows("user_tiers")[0]["user_id"] = "mutated"
    assert b.rows("user_tiers") == [{"user_id": USER_A}]


@pytest.mark.parametrize(
    "method,table",
    [
        ("delete_where_user_id", "venues_rag"),
        ("delete_where_user_id", "cached_responses"),
        ("delete_via_trip_states", "trip_states"),
        ("delete_via_party", "trip_node"),
        ("delete_where_user_id", "trip_node"),
    ],
)
def test_delete_rejects_unknown_or_mismatched_table(backend, method, table):
    with pytest.raises(ValueError):
        getattr(backend, method)(USER_A, table)


def test_memory_backend_satisfies_erase_backend_protocol(backend):
    for name in ("delete_where_user_id", "delete_via_trip_states", "delete_via_party"):
        assert callable(getattr(backend, name))
    assert execute_erase(USER_B, backend)
    assert all(rows == [] for rows in backend.rows_for_user(USER_B).values())


def test_memory_backend_does_not_print(backend, capsys):
    execute_erase(USER_A, backend)
    out = capsys.readouterr()
    assert out.out == "" and out.err == ""
