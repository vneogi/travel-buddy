"""SPEC-43 Gap 4 slice 14: GET /api/v1/me/export over SupabaseExportBackend.

The backend dependency is overridden with SupabaseExportBackend(fake_client).
The read-only fake PostgREST client is copied from
tests/test_spec43_g4_export_supabase.py (not imported across test files); its
query object has no write methods. Auth uses the suite's debug header path
(X-Debug-User-Id), which goes through the real resolve_identity. No network.
"""

import copy
import importlib
import logging
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import monitoring.rate_limit as rate_limit
import routers.me_router as me_router
from main import app
from routers.me_router import get_export_backend
from services.data_rights_export import EXPORT_REQUIRED, EXPORT_STEPS
from services.data_rights_export_supabase import SupabaseExportBackend
from services.data_rights_token_deny import is_denied, reset_denylist

EXPORT_PATH = "/api/v1/me/export"
USER_A = "user-g4-xroute-A-7d21"
USER_B = "user-g4-xroute-B-3f86"
CANARY = "EXPORT-CANARY-g4-route"


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
        for t in sorted(EXPORT_REQUIRED)
    }


def _owned_rows(client, owner):
    return {
        t: [r for r in rows if r.get("seed_owner") == owner] for t, rows in client.store.items()
    }


def _auth(user_id):
    return {"X-Debug-User-Id": user_id}


def _returned(body):
    return {t["table"]: t["rows"] for t in body["tables"]}


# --- fixtures --------------------------------------------------------------


@pytest.fixture(autouse=True)
def _clean_denylist():
    reset_denylist()
    yield
    reset_denylist()


@pytest.fixture
def fake():
    c = FakeClient()
    _seed_user(c, USER_A)
    _seed_user(c, USER_B)
    return c


@pytest.fixture
def http(fake):
    app.dependency_overrides[get_export_backend] = lambda: SupabaseExportBackend(fake)
    try:
        with TestClient(app, raise_server_exceptions=False) as client:
            yield client
    finally:
        app.dependency_overrides.pop(get_export_backend, None)


# --- named tests -----------------------------------------------------------


def test_export_route_returns_only_the_authenticated_users_rows(http, fake):
    before_a, before_b = _counts(fake, USER_A), _counts(fake, USER_B)
    rows_b = copy.deepcopy(_owned_rows(fake, USER_B))
    resp = http.get(EXPORT_PATH, headers=_auth(USER_A))
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert set(body) == {"status", "tables"}
    assert body["status"] == "exported"
    assert [t["table"] for t in body["tables"]] == [s["table"] for s in EXPORT_STEPS]
    returned = _returned(body)
    assert {row["seed_owner"] for rows in returned.values() for row in rows} == {USER_A}
    assert {t: len(rows) for t, rows in returned.items()} == before_a
    assert _counts(fake, USER_B) == before_b
    assert _owned_rows(fake, USER_B) == rows_b
    assert USER_B not in resp.text


def test_export_route_requires_authentication(http, fake):
    before = copy.deepcopy(fake.store)
    resp = http.get(EXPORT_PATH)
    assert resp.status_code == 401
    assert fake.ops == []
    assert fake.store == before


def test_export_route_ignores_client_supplied_user_id(http, fake):
    before_b = copy.deepcopy(_owned_rows(fake, USER_B))
    resp = http.get(EXPORT_PATH, headers=_auth(USER_A), params={"user_id": USER_B})
    assert resp.status_code == 200
    returned = _returned(resp.json())
    assert {row["seed_owner"] for rows in returned.values() for row in rows} == {USER_A}
    assert {t: len(rows) for t, rows in returned.items()} == _counts(fake, USER_A)
    assert USER_B not in resp.text
    # A body on GET is ignored as well.
    with_body = http.request("GET", EXPORT_PATH, headers=_auth(USER_A), json={"user_id": USER_B})
    assert with_body.status_code == 200
    assert USER_B not in with_body.text
    assert _owned_rows(fake, USER_B) == before_b


def test_export_route_failure_is_generic_and_leaks_nothing(http, fake, caplog, capsys):
    fake.fail_on_read = "trip_node"
    caplog.set_level(logging.DEBUG)
    capsys.readouterr()
    resp = http.get(EXPORT_PATH, headers=_auth(USER_A))
    out = capsys.readouterr()
    assert resp.status_code == 500
    assert resp.json() == {"detail": "export_incomplete"}
    for needle in (CANARY, USER_A, USER_B, "RuntimeError", "trip_node", "user_tiers"):
        assert needle not in resp.text, needle
    warnings = [
        r for r in caplog.records if r.name == "travelbuddy" and r.levelno == logging.WARNING
    ]
    assert len(warnings) == 1, [r.getMessage() for r in warnings]
    message = warnings[0].getMessage()
    assert message.startswith("export incomplete (RuntimeError) request_id=")
    assert not message.endswith("request_id=unknown")
    for needle in (CANARY, USER_A, "trip_node"):
        assert needle not in message, needle
    assert CANARY not in caplog.text
    assert CANARY not in out.out and CANARY not in out.err


def test_export_route_returns_501_when_no_supabase_backend(monkeypatch):
    provider = importlib.import_module("services.db_provider")
    monkeypatch.setattr(provider, "IS_SUPABASE", False)
    built = []
    monkeypatch.setattr(me_router, "SupabaseExportBackend", lambda client: built.append(client))
    app.dependency_overrides.pop(get_export_backend, None)
    with TestClient(app, raise_server_exceptions=False) as client:
        resp = client.get(EXPORT_PATH, headers=_auth(USER_A))
    assert resp.status_code == 501
    assert resp.json() == {"detail": "export_unavailable"}
    assert built == []


def test_export_route_does_not_create_a_user_record(http, fake, monkeypatch):
    created = []
    for name in ("services.db_provider", "services.database_service"):
        mod = importlib.import_module(name)
        monkeypatch.setattr(mod.db_service, "get_or_create_user", lambda *a, **k: created.append(a))
    resp = http.get(EXPORT_PATH, headers=_auth(USER_A))
    assert resp.status_code == 200
    assert created == []
    assert {op for _t, op, _f in fake.ops} == {"select"}


def test_export_route_does_not_deny_or_purge(http, fake, monkeypatch):
    called = []
    monkeypatch.setattr(me_router, "deny_identity", lambda *a, **k: called.append("deny"))
    monkeypatch.setattr(me_router, "purge_identity_caches", lambda *a, **k: called.append("purge"))
    resp = http.get(EXPORT_PATH, headers=_auth(USER_A))
    assert resp.status_code == 200
    assert called == []
    assert not is_denied(USER_A)
    again = http.get(EXPORT_PATH, headers=_auth(USER_A))
    assert again.status_code == 200


def test_export_route_response_omits_method_and_via(http, fake):
    resp = http.get(EXPORT_PATH, headers=_auth(USER_A))
    assert resp.status_code == 200
    for entry in resp.json()["tables"]:
        assert set(entry) == {"table", "rows"}, entry.keys()
    assert '"method"' not in resp.text and '"via"' not in resp.text


def _registered_http_routes(application) -> set[tuple[str, str]]:
    """Return {(path, METHOD), ...} via OpenAPI, not app.routes shape."""
    paths = application.openapi().get("paths") or {}
    out: set[tuple[str, str]] = set()
    for path, item in paths.items():
        if not isinstance(item, dict):
            continue
        for method in item:
            m = str(method).upper()
            if m in {"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"}:
                out.add((path, m))
    return out


def test_export_route_is_not_exempt_from_the_rate_limiter():
    exempt = {p.rstrip("/") for p in rate_limit._EXEMPT_PATHS}
    assert EXPORT_PATH.rstrip("/") not in exempt
    assert (EXPORT_PATH, "GET") in _registered_http_routes(app)


def test_export_route_module_changes_are_ascii():
    source = Path(me_router.__file__).read_text(encoding="utf-8")
    assert source.isascii()
