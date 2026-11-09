"""SPEC-43 Gap 4 slice 6: POST /api/v1/me/erase over SupabaseEraseBackend.

The backend dependency is overridden with SupabaseEraseBackend(fake_client).
The fake PostgREST client is copied from tests/test_spec43_g4_erase_supabase.py
(not imported across test files). Auth uses the suite's debug header path
(X-Debug-User-Id), which goes through the real resolve_identity. No network.
"""

import importlib
import logging
import uuid

import pytest
from fastapi.testclient import TestClient

import monitoring.rate_limit as rate_limit
import routers.me_router as me_router
from main import app
from routers.me_router import get_erase_backend
from services.data_rights_erase import ERASE_REQUIRED, ERASE_STEPS
from services.data_rights_erase_supabase import SupabaseEraseBackend

ERASE_PATH = "/api/v1/me/erase"
CONFIRM = {"confirm": "erase-my-data"}
USER_A = "user-g4-route-A-5e1f"
USER_B = "user-g4-route-B-9c42"
CANARY = "ERASE-CANARY-g4-route"


# --- fake PostgREST client (copied from the slice 5 tests) ---------------


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
        if self._op == "delete" and self._table == self._client.fail_on_delete:
            raise RuntimeError(f"{CANARY} {self._table}")
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
        self.fail_on_delete = None

    def table(self, name):
        return _Query(self, name)

    def seed(self, table, row):
        self.store.setdefault(table, []).append(dict(row))


def _seed_user(client, user_id, trips=2):
    client.seed("user_tiers", {"user_id": user_id, "seed_owner": user_id})
    for t in range(trips):
        trip_id = uuid.uuid4()
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


def _auth(user_id):
    return {"X-Debug-User-Id": user_id}


# --- fixtures --------------------------------------------------------------


@pytest.fixture
def fake():
    c = FakeClient()
    _seed_user(c, USER_A)
    _seed_user(c, USER_B)
    return c


@pytest.fixture
def http(fake):
    app.dependency_overrides[get_erase_backend] = lambda: SupabaseEraseBackend(fake)
    try:
        with TestClient(app, raise_server_exceptions=False) as client:
            yield client
    finally:
        app.dependency_overrides.pop(get_erase_backend, None)


# --- named tests -----------------------------------------------------------


def test_erase_route_erases_only_the_authenticated_user(http, fake):
    before_b = _counts(fake, USER_B)
    assert sum(_counts(fake, USER_A).values()) > 0
    # A hostile client also names B; only the authenticated caller is erased.
    resp = http.post(ERASE_PATH, json=CONFIRM, headers=_auth(USER_A), params={"user_id": USER_B})
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "erased"
    assert _counts(fake, USER_A) == {t: 0 for t in ERASE_REQUIRED}
    assert _counts(fake, USER_B) == before_b


def test_erase_route_requires_authentication(http, fake):
    before = (_counts(fake, USER_A), _counts(fake, USER_B))
    resp = http.post(ERASE_PATH, json=CONFIRM)
    assert resp.status_code == 401
    assert fake.ops == []
    assert (_counts(fake, USER_A), _counts(fake, USER_B)) == before


@pytest.mark.parametrize(
    "kwargs",
    [
        {},
        {"json": {}},
        {"json": {"confirm": "erase my data"}},
        {"json": {"confirm": "ERASE-MY-DATA"}},
        {"json": {"confirm": ""}},
        {"json": {"confirm": "erase-my-data", "extra": 1}},
        {"json": {"confirm": None}},
    ],
)
def test_erase_route_requires_exact_confirmation(http, fake, kwargs):
    resp = http.post(ERASE_PATH, headers=_auth(USER_A), **kwargs)
    assert resp.status_code == 422, resp.text
    assert fake.ops == []
    assert sum(_counts(fake, USER_A).values()) > 0


def test_erase_route_ignores_client_supplied_user_id(http, fake):
    before_a, before_b = _counts(fake, USER_A), _counts(fake, USER_B)
    # Body field naming B: rejected outright, nothing touched.
    resp = http.post(ERASE_PATH, json=dict(CONFIRM, user_id=USER_B), headers=_auth(USER_A))
    assert resp.status_code == 422
    assert fake.ops == []
    assert (_counts(fake, USER_A), _counts(fake, USER_B)) == (before_a, before_b)
    # Query naming B: ignored; A is erased, B untouched.
    resp = http.post(ERASE_PATH, json=CONFIRM, headers=_auth(USER_A), params={"user_id": USER_B})
    assert resp.status_code == 200
    assert _counts(fake, USER_B) == before_b
    assert _counts(fake, USER_A) == {t: 0 for t in ERASE_REQUIRED}
    filtered_ids = {str(v) for _t, _op, f in fake.ops for kind, col, v in f if col == "user_id"}
    assert filtered_ids == {USER_A}


def test_erase_route_failure_is_generic_and_leaks_nothing(http, fake, caplog, capsys):
    assert ERASE_STEPS[1]["table"] == "trip_party"
    fake.fail_on_delete = "trip_party"
    caplog.set_level(logging.DEBUG)
    capsys.readouterr()
    resp = http.post(ERASE_PATH, json=CONFIRM, headers=_auth(USER_A))
    out = capsys.readouterr()
    assert resp.status_code == 500
    assert resp.json() == {"detail": "erase_incomplete"}
    for needle in (CANARY, "trip_party", USER_A, "RuntimeError"):
        assert needle not in resp.text, needle
    for needle in (CANARY, "trip_party", USER_A):
        assert needle not in caplog.text, needle
        assert needle not in out.out and needle not in out.err, needle
    warnings = [
        r
        for r in caplog.records
        if r.name == "travelbuddy"
        and r.levelno == logging.WARNING
        and r.getMessage().startswith("erase incomplete")
    ]
    assert len(warnings) == 1
    assert "RuntimeError" in warnings[0].getMessage()
    assert "request_id=" in warnings[0].getMessage()
    # Stopped at the failing step: party_member gone, later tables untouched.
    assert _counts(fake, USER_A)["party_member"] == 0
    assert _counts(fake, USER_A)["trip_states"] == 2


def test_erase_route_is_retryable_after_a_partial_failure(http, fake):
    before_b = _counts(fake, USER_B)
    fake.fail_on_delete = "trip_party"
    first = http.post(ERASE_PATH, json=CONFIRM, headers=_auth(USER_A))
    assert first.status_code == 500
    assert sum(_counts(fake, USER_A).values()) > 0
    fake.fail_on_delete = None
    second = http.post(ERASE_PATH, json=CONFIRM, headers=_auth(USER_A))
    assert second.status_code == 200
    rows = {t["table"]: t["rows"] for t in second.json()["tables"]}
    assert rows["party_member"] == 0  # already erased by the first call
    assert rows["trip_states"] == 2
    assert _counts(fake, USER_A) == {t: 0 for t in ERASE_REQUIRED}
    assert _counts(fake, USER_B) == before_b


def test_erase_route_returns_501_when_no_supabase_backend(monkeypatch):
    provider = importlib.import_module("services.db_provider")
    monkeypatch.setattr(provider, "IS_SUPABASE", False)
    built = []
    monkeypatch.setattr(me_router, "SupabaseEraseBackend", lambda client: built.append(client))
    app.dependency_overrides.pop(get_erase_backend, None)
    with TestClient(app, raise_server_exceptions=False) as client:
        resp = client.post(ERASE_PATH, json=CONFIRM, headers=_auth(USER_A))
    assert resp.status_code == 501
    assert resp.json() == {"detail": "erase_unavailable"}
    assert built == []


def test_erase_route_does_not_create_a_user_record(http, fake, monkeypatch):
    created = []
    for name in ("services.db_provider", "services.database_service"):
        mod = importlib.import_module(name)
        monkeypatch.setattr(mod.db_service, "get_or_create_user", lambda *a, **k: created.append(a))
    resp = http.post(ERASE_PATH, json=CONFIRM, headers=_auth(USER_A))
    assert resp.status_code == 200
    assert created == []
    assert {op for _t, op, _f in fake.ops} <= {"select", "delete"}
    assert not [r for r in fake.store["user_tiers"] if r["user_id"] == USER_A]


def test_erase_route_counts_toward_the_rate_limit():
    exempt = {p.rstrip("/") for p in rate_limit._EXEMPT_PATHS}
    assert ERASE_PATH.rstrip("/") not in exempt
    assert "POST" in rate_limit._COUNTED_METHODS
    routes = {(r.path, m) for r in app.routes for m in getattr(r, "methods", set())}
    assert (ERASE_PATH, "POST") in routes


def test_response_contains_no_identifiers(http, fake):
    a_trips = {str(r["trip_id"]) for r in fake.store["trip_states"] if r["user_id"] == USER_A}
    a_parties = {r["party_id"] for r in fake.store["trip_party"] if r["seed_owner"] == USER_A}
    resp = http.post(ERASE_PATH, json=CONFIRM, headers=_auth(USER_A))
    assert resp.status_code == 200
    body = resp.json()
    assert set(body) == {"status", "tables"}
    assert [t["table"] for t in body["tables"]] == [s["table"] for s in ERASE_STEPS]
    for entry in body["tables"]:
        assert set(entry) == {"table", "rows"}
        assert isinstance(entry["rows"], int)
    for needle in {USER_A, *a_trips, *a_parties, "via", "trip_states.trip_id"}:
        assert needle not in resp.text, needle
