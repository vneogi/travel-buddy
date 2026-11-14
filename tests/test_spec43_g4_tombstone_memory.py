"""SPEC-43 Gap 4 slice 17: tombstone + simulated restore + honor.

Two users are seeded across every erase-required table (seed helper copied
from tests/test_spec43_g4_erase_memory.py, not imported). Each seeded row
carries a test-only "seed_owner" tag. The simulated restore (_restore)
re-seeds every snapshot row that is missing from the store, which returns
the store to the snapshot without duplicating rows that were never erased.
No SQL, no network.
"""

import copy
import uuid
from pathlib import Path

import pytest

import services.data_rights_tombstone as tomb
from services.data_rights_erase import ERASE_REQUIRED, execute_erase
from services.data_rights_erase_memory import InMemoryEraseBackend
from services.data_rights_tombstone import (
    honor_tombstones,
    is_tombstoned,
    record_tombstone,
    reset_tombstones,
)

USER_A = "user-g4-tomb-A"
USER_B = "user-g4-tomb-B"


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


def _snapshot(backend):
    return {t: copy.deepcopy(backend.rows(t)) for t in sorted(ERASE_REQUIRED)}


def _restore(backend, snapshot):
    """Simulated backup restore: re-seed every snapshot row that is missing."""
    for table, rows in snapshot.items():
        current = backend.rows(table)
        for row in rows:
            if row not in current:
                backend.seed(table, copy.deepcopy(row))


def _sorted_rows(rows_by_table):
    return {t: sorted(repr(sorted(r.items())) for r in rows) for t, rows in rows_by_table.items()}


def _view(backend, user_id):
    return {t: len(rows) for t, rows in backend.rows_for_user(user_id).items()}


@pytest.fixture(autouse=True)
def _clean_tombstones():
    reset_tombstones()
    yield
    reset_tombstones()


@pytest.fixture
def backend():
    b = InMemoryEraseBackend()
    _seed_user(b, USER_A)
    _seed_user(b, USER_B)
    return b


def test_restore_without_honor_reactivates_deleted_user(backend):
    before_a, before_b = _counts(backend, USER_A), _counts(backend, USER_B)
    snapshot = _snapshot(backend)
    execute_erase(USER_A, backend)
    assert all(rows == [] for rows in backend.rows_for_user(USER_A).values())
    _restore(backend, snapshot)
    # Control: without honor the deleted account is active again.
    assert _counts(backend, USER_A) == before_a
    assert all(n > 0 for n in _view(backend, USER_A).values())
    assert _counts(backend, USER_B) == before_b
    assert not is_tombstoned(USER_A)


def test_erase_record_restore_honor_leaves_zero_rows_for_tombstoned_user(backend):
    snapshot = _snapshot(backend)
    b_before = copy.deepcopy(backend.rows_for_user(USER_B))
    b_counts = _counts(backend, USER_B)
    execute_erase(USER_A, backend)
    record_tombstone(USER_A)
    _restore(backend, snapshot)
    assert all(n > 0 for n in _view(backend, USER_A).values())  # restore really ran
    results = honor_tombstones(backend)
    assert [r["user_id"] for r in results] == [USER_A]
    assert {t: 0 for t in ERASE_REQUIRED} == _view(backend, USER_A)
    assert _counts(backend, USER_A) == {t: 0 for t in ERASE_REQUIRED}
    assert _counts(backend, USER_B) == b_counts
    assert _sorted_rows(backend.rows_for_user(USER_B)) == _sorted_rows(b_before)
    assert is_tombstoned(USER_A) is True
    assert is_tombstoned(USER_B) is False


def test_honor_tombstones_does_not_touch_other_user(backend):
    snapshot = _snapshot(backend)
    b_rows = {t: [r for r in rows if r.get("seed_owner") == USER_B] for t, rows in snapshot.items()}
    execute_erase(USER_A, backend)
    record_tombstone(USER_A)
    _restore(backend, snapshot)
    targets = []
    for name in ("delete_where_user_id", "delete_via_trip_states", "delete_via_party"):
        real = getattr(backend, name)

        def spy(user_id, table, _real=real):
            targets.append(user_id)
            return _real(user_id=user_id, table=table)

        setattr(backend, name, spy)
    honor_tombstones(backend)
    assert targets and set(targets) == {USER_A}
    for table, rows in b_rows.items():
        current = backend.rows(table)
        for row in rows:
            assert row in current, table
    assert _counts(backend, USER_A) == {t: 0 for t in ERASE_REQUIRED}


def test_tombstone_does_not_prefix_match():
    b = InMemoryEraseBackend()
    _seed_user(b, "user-A")
    _seed_user(b, "user-A-extra")
    extra_counts = _counts(b, "user-A-extra")
    snapshot = _snapshot(b)
    execute_erase("user-A", b)
    record_tombstone("user-A")
    _restore(b, snapshot)
    honor_tombstones(b)
    assert _counts(b, "user-A") == {t: 0 for t in ERASE_REQUIRED}
    assert _counts(b, "user-A-extra") == extra_counts
    assert all(n > 0 for n in _view(b, "user-A-extra").values())
    assert is_tombstoned("user-A") is True
    assert is_tombstoned("user-A-extra") is False
    assert is_tombstoned("user-") is False


def test_honor_with_empty_store_does_not_delete(monkeypatch):
    b = InMemoryEraseBackend()
    record_tombstone(USER_A)
    called = []

    def spy(user_id, backend):
        called.append(user_id)
        return execute_erase(user_id, backend)

    monkeypatch.setattr(tomb, "execute_erase", spy)
    results = honor_tombstones(b)
    assert called == [USER_A]
    assert len(results) == 1 and results[0]["user_id"] == USER_A
    assert all(t["rows"] == 0 for t in results[0]["tables"])
    assert USER_B not in called
    # Empty tombstone set, or no intersection: no execute_erase call at all.
    called.clear()
    assert honor_tombstones(b, user_ids=[USER_B]) == []
    reset_tombstones()
    assert honor_tombstones(b) == []
    assert called == []


def test_record_rejects_blank_user_id():
    for bad in ("", "   "):
        with pytest.raises(ValueError):
            record_tombstone(bad)
        assert is_tombstoned(bad) is False
    assert tomb._tombstones == set()
    record_tombstone("  " + USER_A + "  ")
    record_tombstone(USER_A)
    assert tomb._tombstones == {USER_A}
    assert is_tombstoned(USER_A) and is_tombstoned(" " + USER_A)


def test_honor_skips_ids_that_are_not_tombstoned(backend):
    b_counts = _counts(backend, USER_B)
    record_tombstone(USER_A)
    results = honor_tombstones(backend, user_ids=[USER_A, USER_B])
    assert [r["user_id"] for r in results] == [USER_A]
    assert _counts(backend, USER_A) == {t: 0 for t in ERASE_REQUIRED}
    assert _counts(backend, USER_B) == b_counts
    assert is_tombstoned(USER_B) is False


def test_honor_stops_and_reraises_on_first_error(backend, monkeypatch):
    record_tombstone("user-a-first")
    record_tombstone("user-b-second")
    called = []
    err = RuntimeError("honor-canary")

    def boom(user_id, backend):
        called.append(user_id)
        raise err

    monkeypatch.setattr(tomb, "execute_erase", boom)
    with pytest.raises(RuntimeError) as excinfo:
        honor_tombstones(backend)
    assert excinfo.value is err
    assert called == ["user-a-first"]


def test_tombstone_module_is_ascii():
    source = Path(tomb.__file__).read_text(encoding="utf-8")
    assert source.isascii()
    assert "import logging" not in source and "print(" not in source
