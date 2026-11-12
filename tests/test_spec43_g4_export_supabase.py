"""SPEC-43 Gap 4 slice 13: Supabase export backend against a fake client.

The fake mimics the supabase-py PostgREST read builder (table / select / eq /
in_ / execute), stores rows per table, applies filters on execute, and
records every executed read as (table, op, filters). A select with no
filters still runs in the fake and returns every row, so an unfiltered read
is visible. The query object has no write method at all, so any write
attempt raises AttributeError. No network, no supabase package.
"""

import ast
import copy
import uuid
from pathlib import Path

import pytest

from services import data_rights_export_supabase as supa_module
from services.data_rights_export import EXPORT_REQUIRED, EXPORT_STEPS, execute_export
from services.data_rights_export_supabase import SupabaseExportBackend

USER_A = "user-g4-xsupa-A"
USER_B = "user-g4-xsupa-B"
USER_C = "user-g4-xsupa-C"  # user_tiers only, no trips
USER_D = "user-g4-xsupa-D"  # trips, but no trip_party rows
CANARY = "EXPORT-CANARY-g4-supabase"
TRIP_CHILDREN = ("trip_node", "trip_edge", "trip_party", "party_member")


class _Result:
    def __init__(self, data):
        self.data = data


class _Query:
    """Read-only builder: select, eq, in_, execute. No write methods."""

    def __init__(self, client, table):
        self._client = client
        self._table = table
        self._op = None
        self._cols = "*"
        self._filters = []

    def select(self, cols="*"):
        self._op = "select"
        self._cols = cols
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
        if self._table == self._client.fail_on_read:
            raise RuntimeError(CANARY)
        hit = [r for r in rows if self._match(r)]
        if self._cols != "*":
            cols = [c.strip() for c in self._cols.split(",")]
            return _Result([{c: r.get(c) for c in cols} for r in hit])
        return _Result([dict(r) for r in hit])


class FakeClient:
    def __init__(self, fail_on_read=None):
        self.store = {}
        self.ops = []
        self.fail_on_read = fail_on_read

    def table(self, name):
        return _Query(self, name)

    def seed(self, table, row):
        self.store.setdefault(table, []).append(dict(row))


def _seed_user(client, user_id, trips=2, parties=True):
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
        if not parties:
            continue
        client.seed(
            "trip_party", {"trip_id": str(trip_id), "party_id": party_id, "seed_owner": user_id}
        )
        for role in ("lead", "companion"):
            client.seed("party_member", {"party_id": party_id, "role": role, "seed_owner": user_id})


def _counts(client, owner):
    return {
        t: sum(1 for r in client.store.get(t, []) if r.get("seed_owner") == owner)
        for t in sorted(EXPORT_REQUIRED)
    }


def _trip_ids(client, user_id):
    return tuple(
        sorted(str(r["trip_id"]) for r in client.store["trip_states"] if r["user_id"] == user_id)
    )


def _party_ids(client, user_id):
    return tuple(
        sorted(r["party_id"] for r in client.store["trip_party"] if r["seed_owner"] == user_id)
    )


@pytest.fixture
def client():
    c = FakeClient()
    _seed_user(c, USER_A)
    _seed_user(c, USER_B)
    _seed_user(c, USER_C, trips=0)
    _seed_user(c, USER_D, parties=False)
    return c


def test_supabase_export_returns_only_the_callers_rows(client):
    before_a, before_b = _counts(client, USER_A), _counts(client, USER_B)
    snapshot_b = {
        t: [r for r in rows if r.get("seed_owner") == USER_B] for t, rows in client.store.items()
    }
    results = execute_export(USER_A, SupabaseExportBackend(client))
    assert [r["table"] for r in results] == [s["table"] for s in EXPORT_STEPS]
    assert {row["seed_owner"] for r in results for row in r["rows"]} == {USER_A}
    assert {r["table"]: len(r["rows"]) for r in results} == before_a
    assert _counts(client, USER_A) == before_a
    assert _counts(client, USER_B) == before_b
    assert {
        t: [r for r in rows if r.get("seed_owner") == USER_B] for t, rows in client.store.items()
    } == snapshot_b


def test_supabase_export_never_reads_without_a_filter(client):
    backend = SupabaseExportBackend(client)
    execute_export(USER_A, backend)
    execute_export(USER_C, backend)
    assert client.ops
    for table, op, filters in client.ops:
        assert op == "select", (table, op)
        assert filters, f"unfiltered read on {table}"
        for kind, _col, val in filters:
            if kind == "in":
                assert len(val) > 0, f"empty in_ on {table}"
    read_tables = {t for t, _op, _f in client.ops}
    assert read_tables <= set(EXPORT_REQUIRED)


def test_supabase_export_empty_owned_trips_sends_no_child_read(client):
    backend = SupabaseExportBackend(client)
    assert _trip_ids(client, USER_C) == ()
    for table in ("trip_node", "trip_edge", "trip_party"):
        assert backend.fetch_via_trip_states(USER_C, table) == []
    assert backend.fetch_via_party(USER_C, "party_member") == []
    read_tables = {t for t, _op, _f in client.ops}
    assert not read_tables & set(TRIP_CHILDREN)
    assert read_tables == {"trip_states"}


def test_supabase_export_empty_party_list_sends_no_party_member_read(client):
    backend = SupabaseExportBackend(client)
    assert _trip_ids(client, USER_D)
    assert backend.fetch_via_party(USER_D, "party_member") == []
    assert [t for t, _op, _f in client.ops] == ["trip_states", "trip_party"]
    assert "party_member" not in {t for t, _op, _f in client.ops}


def test_supabase_export_scopes_child_reads_to_owned_ids(client):
    backend = SupabaseExportBackend(client)
    trips = _trip_ids(client, USER_A)
    parties = _party_ids(client, USER_A)
    assert trips and parties
    nodes = backend.fetch_via_trip_states(USER_A, "trip_node")
    assert client.ops == [
        ("trip_states", "select", (("eq", "user_id", USER_A),)),
        ("trip_node", "select", (("in", "trip_id", trips),)),
    ]
    assert {n["seed_owner"] for n in nodes} == {USER_A}
    client.ops.clear()
    members = backend.fetch_via_party(USER_A, "party_member")
    assert client.ops == [
        ("trip_states", "select", (("eq", "user_id", USER_A),)),
        ("trip_party", "select", (("in", "trip_id", trips),)),
        ("party_member", "select", (("in", "party_id", parties),)),
    ]
    assert all(isinstance(v, str) for v in trips + parties)
    assert {m["seed_owner"] for m in members} == {USER_A}


@pytest.mark.parametrize("bad", [None, "", "   ", 42])
def test_supabase_export_rejects_blank_user_id_before_any_read(client, bad):
    backend = SupabaseExportBackend(client)
    with pytest.raises(ValueError):
        backend.fetch_where_user_id(bad, "user_tiers")
    with pytest.raises(ValueError):
        backend.fetch_via_trip_states(bad, "trip_node")
    with pytest.raises(ValueError):
        backend.fetch_via_party(bad, "party_member")
    with pytest.raises(ValueError):
        execute_export(bad, backend)
    assert client.ops == []


@pytest.mark.parametrize(
    "method,table",
    [
        ("fetch_where_user_id", "trip_node"),
        ("fetch_via_party", "trip_states"),
        ("fetch_via_trip_states", "user_tiers"),
        ("fetch_via_party", "trip_party"),
    ],
)
def test_supabase_export_rejects_method_mismatch_before_any_read(client, method, table):
    with pytest.raises(ValueError) as excinfo:
        getattr(SupabaseExportBackend(client), method)(USER_A, table)
    assert USER_A not in str(excinfo.value)
    assert client.ops == []


@pytest.mark.parametrize("table", ["cached_responses", "venues_rag", "nope"])
def test_supabase_export_rejects_non_required_table_before_any_read(client, table):
    backend = SupabaseExportBackend(client)
    for method in ("fetch_where_user_id", "fetch_via_trip_states", "fetch_via_party"):
        with pytest.raises(ValueError) as excinfo:
            getattr(backend, method)(USER_A, table)
        assert table not in str(excinfo.value)
    assert client.ops == []


def test_supabase_export_error_stops_later_reads(client):
    client.fail_on_read = "trip_node"
    with pytest.raises(RuntimeError) as excinfo:
        execute_export(USER_A, SupabaseExportBackend(client))
    assert str(excinfo.value) == CANARY
    order = [s["table"] for s in EXPORT_STEPS]
    later = set(order[order.index("trip_node") + 1 :])
    read_tables = [t for t, _op, _f in client.ops]
    assert read_tables[-1] == "trip_node"
    assert not later & set(read_tables)
    # Nothing was returned; and the canary never lands in the store.
    assert not any(CANARY in str(r) for rows in client.store.values() for r in rows)


def test_supabase_export_rows_are_detached_copies(client):
    backend = SupabaseExportBackend(client)
    before = copy.deepcopy(client.store)
    results = execute_export(USER_A, backend)
    for r in results:
        for row in r["rows"]:
            row["seed_owner"] = "mutated"
        r["rows"].append({"seed_owner": "injected"})
    direct = backend.fetch_via_trip_states(USER_A, "trip_node")
    direct[0]["seq"] = "mutated"
    assert client.store == before


def test_supabase_export_never_writes(client):
    before = copy.deepcopy(client.store)
    execute_export(USER_A, SupabaseExportBackend(client))
    assert client.store == before
    assert client.ops and {op for _t, op, _f in client.ops} == {"select"}
    query = client.table("trip_node")
    for name in ("delete", "update", "insert", "upsert", "rpc"):
        assert not hasattr(query, name), name


def test_export_supabase_module_has_no_forbidden_imports():
    source = Path(supa_module.__file__).read_text(encoding="utf-8")
    assert source.isascii()
    roots = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            roots |= {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom):
            roots.add((node.module or "").split(".")[0])
    assert roots <= {"__future__", "typing", "services"}, roots
    assert not roots & {"supabase", "httpx", "psycopg", "psycopg2", "logging", "litellm"}


def test_supabase_export_does_not_print(client, capsys):
    capsys.readouterr()
    execute_export(USER_A, SupabaseExportBackend(client))
    out = capsys.readouterr()
    assert out.out == "" and out.err == ""
