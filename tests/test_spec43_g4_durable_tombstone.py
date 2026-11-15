"""SPEC-43 Gap 4: durable tombstone (migration 0027, Supabase store, erase route).

No test opens a socket or calls Supabase: the store runs over an in-memory
fake client, the route runs through TestClient with fake erase backend,
store and Auth deleter, and an autouse guard fails any connect or DNS lookup.
"""

import copy
import logging
import re
import socket
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import services.data_rights_tombstone as tomb
from config.data_rights import (
    ERASE_EXEMPT_TABLES,
    RIGHTS_MAP,
    erase_exempt_violations,
    identity_tables,
)
from main import app
from routers.me_router import get_auth_deleter, get_erase_backend, get_tombstone_store
from security import ResolvedIdentity, resolve_identity
from services.data_rights_erase import ERASE_REQUIRED, ERASE_STEPS
from services.data_rights_erase_supabase import SupabaseEraseBackend
from services.data_rights_export import EXPORT_REQUIRED, EXPORT_STEPS
from services.data_rights_token_deny import is_denied, reset_denylist
from services.data_rights_tombstone_supabase import (
    READ_FAILED,
    WRITE_FAILED,
    SupabaseTombstoneStore,
    TombstoneStoreError,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
MIGRATIONS_DIR = REPO_ROOT / "supabase" / "migrations"
MIGRATION_0027 = MIGRATIONS_DIR / "0027_spec43_g4_tombstone.sql"
TABLE = "data_rights_tombstone"
ERASE_PATH = "/api/v1/me/erase"
CONFIRM = {"confirm": "erase-my-data"}
USER = "user-g4-durable-7a31"
FAKE_KEY = "sb-service-key-canary-0123456789"


# --- fakes ---------------------------------------------------------------------


class _Result:
    def __init__(self, data):
        self.data = data


class _TombQuery:
    def __init__(self, client):
        self._client = client
        self._op = None
        self._row = None
        self._range = None

    def upsert(self, row, on_conflict=None):
        self._op, self._row = "upsert", dict(row)
        self._client.ops.append(("upsert", dict(row), on_conflict))
        return self

    def select(self, cols="*"):
        self._op = "select"
        self._client.ops.append(("select", cols, None))
        return self

    def order(self, col):
        return self

    def range(self, start, end):
        self._range = (start, end)
        return self

    def execute(self):
        if self._client.fail is not None:
            raise self._client.fail
        if self._op == "upsert":
            self._client.rows[self._row["user_id"]] = self._row
            return _Result([self._row])
        ids = sorted(self._client.rows)
        start, end = self._range or (0, len(ids) - 1)
        return _Result([{"user_id": i} for i in ids[start : end + 1]])


class FakeTombClient:
    def __init__(self, fail=None):
        self.rows = {}
        self.ops = []
        self.fail = fail
        self.tables = []

    def table(self, name):
        self.tables.append(name)
        return _TombQuery(self)


class RecordingStore:
    def __init__(self, ops, ids=(), fail=None):
        self.ops, self.ids, self.fail = ops, list(ids), fail
        self.puts = []

    def put(self, user_id):
        self.ops.append(("store.put", user_id))
        if self.fail is not None:
            raise self.fail
        self.puts.append(user_id)

    def list_ids(self):
        self.ops.append(("store.list_ids", None))
        if self.fail is not None:
            raise self.fail
        return list(self.ids)


class RecordingEraseBackend:
    def __init__(self, ops):
        self.ops = ops

    def _rec(self, method, user_id, table):
        self.ops.append(("erase", table))
        return 0

    def delete_where_user_id(self, user_id, table):
        return self._rec("delete_where_user_id", user_id, table)

    def delete_via_trip_states(self, user_id, table):
        return self._rec("delete_via_trip_states", user_id, table)

    def delete_via_party(self, user_id, table):
        return self._rec("delete_via_party", user_id, table)


class RecordingDeleter:
    def __init__(self, ops):
        self.ops = ops
        self.calls = []

    def delete_auth_user(self, user_id):
        self.calls.append(user_id)
        self.ops.append(("auth.delete", user_id))


@pytest.fixture(autouse=True)
def _isolation(monkeypatch):
    def _blocked(*args, **kwargs):
        raise AssertionError("real network access attempted in a test")

    monkeypatch.setattr(socket, "create_connection", _blocked)
    monkeypatch.setattr(socket, "getaddrinfo", _blocked)
    monkeypatch.setattr(socket.socket, "connect", _blocked)
    tomb.reset_tombstones()
    reset_denylist()
    yield
    tomb.reset_tombstones()
    reset_denylist()


def _sql():
    text = MIGRATION_0027.read_text(encoding="utf-8")
    return re.sub(r"--[^\n]*", "", text).lower()


# --- migration ------------------------------------------------------------------


def test_migration_0027_enables_and_forces_rls():
    sql = _sql()
    assert re.search(r"create table if not exists data_rights_tombstone\s*\(", sql)
    assert re.search(r"user_id text primary key", sql)
    assert re.search(r"alter table data_rights_tombstone enable row level security\s*;", sql)
    assert re.search(r"alter table data_rights_tombstone force row level security\s*;", sql)
    assert re.search(
        r"revoke all on table data_rights_tombstone from public,\s*anon,\s*authenticated\s*;", sql
    )
    assert re.search(r"grant all on table data_rights_tombstone to service_role\s*;", sql)
    assert "create policy" not in sql
    assert not re.search(r"grant[^;]*\bto\s+(anon|authenticated)\b", sql)


def test_migration_0027_is_ascii():
    assert MIGRATION_0027.read_text(encoding="utf-8").isascii()


# --- store ----------------------------------------------------------------------


def test_store_put_is_idempotent():
    client = FakeTombClient()
    store = SupabaseTombstoneStore(client)
    store.put(USER)
    store.put("  " + USER + "  ")
    assert client.rows == {USER: {"user_id": USER, "source": "me_erase"}}
    assert set(client.tables) == {TABLE}
    assert [op for op in client.ops if op[0] == "upsert"] == [
        ("upsert", {"user_id": USER, "source": "me_erase"}, "user_id")
    ] * 2
    store.put("user-other")
    assert store.list_ids() == sorted([USER, "user-other"])


def test_store_put_failure_raises_closed_code():
    client = FakeTombClient(fail=RuntimeError(f"PostgREST 500 for {USER} key={FAKE_KEY}"))
    store = SupabaseTombstoneStore(client)
    with pytest.raises(TombstoneStoreError) as exc:
        store.put(USER)
    assert str(exc.value) == WRITE_FAILED
    assert exc.value.code == WRITE_FAILED
    assert exc.value.__cause__ is None and exc.value.__suppress_context__
    for needle in (USER, FAKE_KEY, "PostgREST"):
        assert needle not in str(exc.value)
        assert needle not in repr(exc.value)
    with pytest.raises(TombstoneStoreError) as exc:
        store.list_ids()
    assert str(exc.value) == READ_FAILED
    assert USER not in str(exc.value)


# --- durable record / honor --------------------------------------------------------


def test_record_durable_writes_store_then_memory():
    ops = []
    store = RecordingStore(ops)
    seen_in_memory_at_put = []
    original_put = store.put

    def put(user_id):
        seen_in_memory_at_put.append(tomb.is_tombstoned(user_id))
        original_put(user_id)

    store.put = put
    tomb.record_tombstone_durable("  " + USER + " ", store)
    assert store.puts == [USER]
    assert seen_in_memory_at_put == [False]  # store first, memory second
    assert tomb.is_tombstoned(USER)


def test_record_durable_failure_leaves_memory_unchanged():
    ops = []
    store = RecordingStore(ops, fail=TombstoneStoreError(WRITE_FAILED))
    with pytest.raises(TombstoneStoreError):
        tomb.record_tombstone_durable(USER, store)
    assert not tomb.is_tombstoned(USER)
    assert ops == [("store.put", USER)]


def test_honor_reads_durable_ids_when_store_given():
    ops = []
    tomb.record_tombstone("user-mem")
    store = RecordingStore(ops, ids=["user-durable", "user-mem"])
    results = tomb.honor_tombstones(RecordingEraseBackend(ops), store=store)
    assert [r["user_id"] for r in results] == ["user-durable", "user-mem"]
    assert ("store.list_ids", None) in ops
    erased_tables = [t for kind, t in ops if kind == "erase"]
    assert erased_tables == [s["table"] for s in ERASE_STEPS] * 2


def test_honor_without_store_is_unchanged():
    ops = []
    tomb.record_tombstone("user-b")
    tomb.record_tombstone("user-a")
    results = tomb.honor_tombstones(RecordingEraseBackend(ops))
    assert [r["user_id"] for r in results] == ["user-a", "user-b"]
    # With user_ids, only listed-and-tombstoned-in-memory ids; a store is not read.
    store = RecordingStore(ops, ids=["user-durable"])
    ops.clear()
    listed = tomb.honor_tombstones(
        RecordingEraseBackend(ops), user_ids=["user-a", "user-durable"], store=store
    )
    assert [r["user_id"] for r in listed] == ["user-a"]
    assert ("store.list_ids", None) not in ops
    assert tomb.honor_tombstones(RecordingEraseBackend([]), user_ids=[]) == []


def test_honor_store_failure_propagates():
    ops = []
    tomb.record_tombstone("user-mem")
    store = RecordingStore(ops, fail=TombstoneStoreError(READ_FAILED))
    with pytest.raises(TombstoneStoreError) as exc:
        tomb.honor_tombstones(RecordingEraseBackend(ops), store=store)
    assert exc.value.code == READ_FAILED
    assert [kind for kind, _t in ops if kind == "erase"] == []  # nothing erased


# --- erase route -----------------------------------------------------------------


@pytest.fixture
def route():
    ops = []
    state = {"store": RecordingStore(ops), "deleter": RecordingDeleter(ops)}
    app.dependency_overrides[get_erase_backend] = lambda: RecordingEraseBackend(ops)
    app.dependency_overrides[get_tombstone_store] = lambda: state["store"]
    app.dependency_overrides[get_auth_deleter] = lambda: state["deleter"]
    app.dependency_overrides[resolve_identity] = lambda: ResolvedIdentity(USER, "supabase")
    try:
        with TestClient(app, raise_server_exceptions=False) as client:
            yield client, ops, state
    finally:
        for dep in (get_erase_backend, get_tombstone_store, get_auth_deleter, resolve_identity):
            app.dependency_overrides.pop(dep, None)


def test_erase_route_records_tombstone_after_row_erase(route):
    client, ops, state = route
    resp = client.post(ERASE_PATH, json=CONFIRM)
    assert resp.status_code == 200, resp.text
    kinds = [kind for kind, _x in ops]
    assert kinds == ["erase"] * len(ERASE_STEPS) + ["store.put", "auth.delete"]
    assert state["store"].puts == [USER]
    assert state["deleter"].calls == [USER]
    assert tomb.is_tombstoned(USER)
    assert is_denied(USER)


def test_erase_route_store_failure_returns_erase_incomplete(route):
    client, ops, state = route
    state["store"].fail = TombstoneStoreError(WRITE_FAILED)
    resp = client.post(ERASE_PATH, json=CONFIRM)
    assert resp.status_code == 500
    assert resp.json() == {"detail": "erase_incomplete"}
    assert state["deleter"].calls == []
    assert ("auth.delete", USER) not in ops
    assert not is_denied(USER)
    assert not tomb.is_tombstoned(USER)
    # Retry after the store recovers completes the whole erase.
    state["store"].fail = None
    ops.clear()
    retry = client.post(ERASE_PATH, json=CONFIRM)
    assert retry.status_code == 200
    assert [k for k, _x in ops][-2:] == ["store.put", "auth.delete"]


def test_erase_route_store_failure_logs_no_user_id(route, caplog):
    client, ops, state = route
    state["store"].fail = TombstoneStoreError(WRITE_FAILED)
    caplog.set_level(logging.DEBUG)
    resp = client.post(ERASE_PATH, json=CONFIRM)
    assert resp.status_code == 500
    warnings = [
        r.getMessage()
        for r in caplog.records
        if r.name == "travelbuddy" and r.levelno == logging.WARNING
    ]
    assert len(warnings) == 1
    assert warnings[0].startswith("erase incomplete (TombstoneStoreError) request_id=")
    assert USER not in caplog.text
    assert USER not in resp.text


def test_blank_user_id_rejected_before_store():
    ops = []
    store = RecordingStore(ops)
    for bad in (None, "", "   ", 42):
        with pytest.raises(ValueError):
            tomb.record_tombstone_durable(bad, store)
    assert ops == []
    client = FakeTombClient()
    for bad in (None, "", "   "):
        with pytest.raises(ValueError):
            SupabaseTombstoneStore(client).put(bad)
    assert client.ops == []


# --- classification (Amendment 1) -------------------------------------------------


def test_tombstone_table_is_erase_exempt():
    assert RIGHTS_MAP[TABLE]["identity"] == "erase_exempt"
    assert RIGHTS_MAP[TABLE]["export"] == "planned"
    assert RIGHTS_MAP[TABLE]["delete"] == "planned"
    assert TABLE in identity_tables(MIGRATIONS_DIR)  # the scan still sees user_id
    assert ERASE_EXEMPT_TABLES == frozenset({TABLE})


def test_erase_and_export_plans_skip_tombstone_table():
    assert TABLE not in ERASE_REQUIRED
    assert TABLE not in EXPORT_REQUIRED
    assert TABLE not in {s["table"] for s in ERASE_STEPS}
    assert TABLE not in {s["table"] for s in EXPORT_STEPS}
    assert EXPORT_REQUIRED == ERASE_REQUIRED


def test_erase_exempt_is_allowlisted():
    assert erase_exempt_violations(RIGHTS_MAP) == set()
    rights = copy.deepcopy(RIGHTS_MAP)
    rights["synthetic"] = dict(rights[TABLE])
    assert erase_exempt_violations(rights) == {"synthetic"}


class _GuardClient:
    def __init__(self):
        self.ops = []

    def table(self, name):
        self.ops.append(name)
        raise AssertionError("client used before the table guard")


@pytest.mark.parametrize(
    "method", ["delete_where_user_id", "delete_via_trip_states", "delete_via_party"]
)
def test_supabase_erase_backend_refuses_tombstone_table(method):
    client = _GuardClient()
    with pytest.raises(ValueError):
        getattr(SupabaseEraseBackend(client), method)(USER, TABLE)
    assert client.ops == []


def test_touched_files_are_ascii():
    for rel in (
        "supabase/migrations/0027_spec43_g4_tombstone.sql",
        "services/data_rights_tombstone.py",
        "services/data_rights_tombstone_supabase.py",
        "routers/me_router.py",
        "config/data_rights.py",
        "services/data_rights_erase.py",
        "services/data_rights_export.py",
        "tests/test_spec43_g4_durable_tombstone.py",
        "tests/test_spec43_g2_rls.py",
        "tests/test_spec43_g4_erase_plan.py",
        "tests/test_spec43_g4_export_plan.py",
    ):
        assert (REPO_ROOT / rel).read_text(encoding="utf-8").isascii(), rel
