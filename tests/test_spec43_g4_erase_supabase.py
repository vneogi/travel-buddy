"""SPEC-43 Gap 4 slice 5: Supabase erase backend against a fake client.

The fake mimics the supabase-py PostgREST builder (table / select / delete /
eq / in_ / execute), stores rows per table, applies filters on execute, and
records every executed op as (table, op, filters). A delete with no filters
still runs in the fake and removes every row, so an unfiltered delete is
visible. No network, no supabase package.
"""

import ast
import uuid
from pathlib import Path

import pytest

from services import data_rights_erase_supabase as supa_module
from services.data_rights_erase import ERASE_REQUIRED, ERASE_STEPS, execute_erase
from services.data_rights_erase_supabase import SupabaseEraseBackend

USER_A = "user-g4-supa-A"
USER_B = "user-g4-supa-B"
USER_C = "user-g4-supa-C"
VIA_METHODS = {"delete_via_trip_states", "delete_via_party"}


class _Result:
    def __init__(self, data):
        self.data = data


class _Query:
    def __init__(self, client, table):
        self._client = client
        self._table = table
        self._op = None
        self._filters = []

    def select(self, cols="*"):
        self._op = "select"
        self._cols = cols
        return self

    def delete(self):
        self._op = "delete"
        return self

    def eq(self, col, val):
        self._filters.append(("eq", col, val))
        return self

    def in_(self, col, vals):
        self._filters.append(("in", col, tuple(vals)))
        return self

    def _match(self, row):
        for kind, col, val in self._filters:
            if kind == "eq" and str(row.get(col)) != str(val):
                return False
            if kind == "in" and str(row.get(col)) not in {str(v) for v in val}:
                return False
        return True

    def execute(self):
        rows = self._client.store.setdefault(self._table, [])
        self._client.ops.append((self._table, self._op, tuple(self._filters)))
        hit = [r for r in rows if self._match(r)]
        if self._op == "delete":
            self._client.store[self._table] = [r for r in rows if not self._match(r)]
            return _Result([dict(r) for r in hit])
        if self._op == "select" and self._cols != "*":
            cols = [c.strip() for c in self._cols.split(",")]
            return _Result([{c: r.get(c) for c in cols} for r in hit])
        return _Result([dict(r) for r in hit])


class FakeClient:
    def __init__(self):
        self.store = {}
        self.ops = []

    def table(self, name):
        return _Query(self, name)

    def seed(self, table, row):
        self.store.setdefault(table, []).append(dict(row))


def _seed_user(client, user_id, trips=2):
    client.seed("user_tiers", {"user_id": user_id, "seed_owner": user_id})
    for t in range(trips):
        trip_id = uuid.uuid4()  # uuid in trip_states, text in trip_party
        party_id = f"party-{user_id}-{t}"
        client.seed("trip_states", {"user_id": user_id, "trip_id": trip_id, "seed_owner": user_id})
        for table in ("event_log", "signal", "trip_command"):
            client.seed(table, {"user_id": user_id, "trip_id": trip_id, "seed_owner": user_id})
        for n in range(2):
            client.seed("trip_node", {"trip_id": trip_id, "seq": n, "seed_owner": user_id})
        client.seed("trip_edge", {"trip_id": trip_id, "seed_owner": user_id})
        client.seed(
            "trip_party", {"trip_id": str(trip_id), "party_id": party_id, "seed_owner": user_id}
        )
        for role in ("lead", "companion"):
            client.seed("party_member", {"party_id": party_id, "role": role, "seed_owner": user_id})


def _counts(client, owner):
    return {
        t: sum(1 for r in client.store.get(t, []) if r.get("seed_owner") == owner)
        for t in sorted(ERASE_REQUIRED)
    }


def _trip_ids(client, user_id):
    return tuple(
        sorted(str(r["trip_id"]) for r in client.store["trip_states"] if r["user_id"] == user_id)
    )


def _party_ids(client, user_id):
    return tuple(
        sorted(r["party_id"] for r in client.store["trip_party"] if r["seed_owner"] == user_id)
    )


def _deletes(client):
    return [op for op in client.ops if op[1] == "delete"]


@pytest.fixture
def client():
    c = FakeClient()
    _seed_user(c, USER_A)
    _seed_user(c, USER_B)
    return c


def test_supabase_erase_never_deletes_without_a_filter(client):
    execute_erase(USER_A, SupabaseEraseBackend(client))
    deletes = _deletes(client)
    assert [t for t, _op, _f in deletes] == [s["table"] for s in ERASE_STEPS]
    for table, _op, filters in deletes:
        assert filters, f"unfiltered delete on {table}"
        for kind, _col, val in filters:
            if kind == "in":
                assert val, f"empty in_ list on {table}"


def test_supabase_backend_wipes_target_and_keeps_other_user(client):
    before_a = _counts(client, USER_A)
    before_b = _counts(client, USER_B)
    assert all(n > 0 for n in before_a.values())
    execute_erase(USER_A, SupabaseEraseBackend(client))
    assert _counts(client, USER_A) == {t: 0 for t in ERASE_REQUIRED}
    assert _counts(client, USER_B) == before_b


def test_supabase_erase_skips_delete_when_user_has_no_trips(client):
    client.seed("user_tiers", {"user_id": USER_C, "seed_owner": USER_C})
    before_a, before_b = _counts(client, USER_A), _counts(client, USER_B)
    backend = SupabaseEraseBackend(client)
    assert backend.delete_via_trip_states(USER_C, "trip_node") == 0
    assert backend.delete_via_party(USER_C, "party_member") == 0
    assert _deletes(client) == []
    # The party path stops after the empty trip lookup: no trip_party select.
    assert not [op for op in client.ops if op[0] == "trip_party"]
    results = execute_erase(USER_C, backend)
    via_tables = {s["table"] for s in ERASE_STEPS if s["method"] in VIA_METHODS}
    assert {t for t, _op, _f in _deletes(client)}.isdisjoint(via_tables)
    assert all(r["rows"] == 0 for r in results if r["table"] in via_tables)
    assert _counts(client, USER_C)["user_tiers"] == 0
    assert _counts(client, USER_A) == before_a
    assert _counts(client, USER_B) == before_b


def test_supabase_erase_scopes_via_tables_to_owned_trip_ids(client):
    a_trips = _trip_ids(client, USER_A)
    assert all(isinstance(t, str) for t in a_trips) and len(a_trips) == 2
    execute_erase(USER_A, SupabaseEraseBackend(client))
    for table in ("trip_node", "trip_edge", "trip_party"):
        ops = [op for op in _deletes(client) if op[0] == table]
        assert ops == [(table, "delete", (("in", "trip_id", a_trips),))], table
        assert all(isinstance(v, str) for v in ops[0][2][0][2])


def test_supabase_erase_party_member_scoped_via_trip_party(client):
    a_trips = _trip_ids(client, USER_A)
    a_parties = _party_ids(client, USER_A)
    backend = SupabaseEraseBackend(client)
    removed = backend.delete_via_party(USER_A, "party_member")
    assert removed == 4
    assert client.ops == [
        ("trip_states", "select", (("eq", "user_id", USER_A),)),
        ("trip_party", "select", (("in", "trip_id", a_trips),)),
        ("party_member", "delete", (("in", "party_id", a_parties),)),
    ]
    assert _counts(client, USER_A)["party_member"] == 0
    assert _counts(client, USER_B)["party_member"] == 4


def test_supabase_erase_rows_affected_match_deleted_rows(client):
    seeded = _counts(client, USER_A)
    results = execute_erase(USER_A, SupabaseEraseBackend(client))
    assert {r["table"]: r["rows"] for r in results} == seeded


@pytest.mark.parametrize(
    "method,table",
    [
        ("delete_via_trip_states", "trip_states"),
        ("delete_where_user_id", "venues_rag"),
        ("delete_where_user_id", "cached_responses"),
        ("delete_where_user_id", "trip_node"),
        ("delete_via_party", "trip_party"),
        ("delete_via_trip_states", "nope"),
    ],
)
def test_supabase_erase_rejects_mismatched_or_catalog_table(client, method, table):
    with pytest.raises(ValueError):
        getattr(SupabaseEraseBackend(client), method)(USER_A, table)
    assert client.ops == []


@pytest.mark.parametrize("bad", [None, "", "   "])
def test_supabase_backend_rejects_blank_user_id_before_client(client, bad):
    with pytest.raises(ValueError):
        SupabaseEraseBackend(client).delete_where_user_id(bad, "user_tiers")
    assert client.ops == []


def test_supabase_module_does_not_import_supabase_or_network_clients():
    tree = ast.parse(Path(supa_module.__file__).read_text(encoding="utf-8"))
    roots = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots |= {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom):
            roots.add((node.module or "").split(".")[0])
    assert "supabase" not in roots
    assert roots <= {"__future__", "typing", "services"}, roots
    assert not roots & {"litellm", "httpx", "psycopg", "psycopg2", "logging"}


def test_supabase_backend_does_not_print(client, capsys):
    execute_erase(USER_A, SupabaseEraseBackend(client))
    out = capsys.readouterr()
    assert out.out == "" and out.err == ""
