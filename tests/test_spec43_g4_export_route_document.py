"""SPEC-43 Gap 4 slice 19: GET /api/v1/me/export?format=document.

The nested document (build_export_document, slice 18) is returned only with
format=document; the default stays the flat {status, tables} body. The
read-only fake client, seed helper and fixtures are copied from
tests/test_spec43_g4_export_route.py (not imported across test files). Auth
uses the debug header through the real resolve_identity. No network.
"""

import copy
import importlib
import logging
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import routers.me_router as me_router
from main import app
from routers.me_router import get_export_backend
from services.data_rights_export import EXPORT_REQUIRED, EXPORT_STEPS
from services.data_rights_export_document import count_rows
from services.data_rights_export_supabase import SupabaseExportBackend
from services.data_rights_token_deny import reset_denylist

EXPORT_PATH = "/api/v1/me/export"
USER_A = "user-g4-xdoc-A-5b19"
USER_B = "user-g4-xdoc-B-8e42"
CANARY = "EXPORT-CANARY-g4-route-doc"
DOC_CANARY = "DOC-CANARY-g4-route"
DOC = {"format": "document"}


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


def _doc_rows(document):
    """Every row in the nested document (account, trips, unattached)."""
    rows = list(document["account"]["user_tiers"])
    for trip in document["trips"]:
        rows.append(trip["trip"])
        for key in ("nodes", "edges", "commands", "signals", "events"):
            rows += trip[key]
        for party in trip["parties"]:
            rows.append(party["party"])
            rows += party["members"]
    for table_rows in document["unattached"].values():
        rows += table_rows
    return rows


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


def test_export_document_format_returns_nested_document_for_caller_only(http, fake):
    before_b = copy.deepcopy(_owned_rows(fake, USER_B))
    resp = http.get(EXPORT_PATH, headers=_auth(USER_A), params=DOC)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert set(body) == {"status", "document"}
    assert body["status"] == "exported"
    document = body["document"]
    assert set(document) == {"format", "version", "account", "trips", "unattached"}
    assert document["format"] == "travel-buddy-export"
    assert document["version"] == 1
    assert len(document["trips"]) == _counts(fake, USER_A)["trip_states"]
    rows = _doc_rows(document)
    assert rows and {r["seed_owner"] for r in rows} == {USER_A}
    assert USER_B not in resp.text
    assert _owned_rows(fake, USER_B) == before_b


def test_export_document_format_conserves_rows(http, fake):
    resp = http.get(EXPORT_PATH, headers=_auth(USER_A), params=DOC)
    document = resp.json()["document"]
    assert count_rows(document) == _counts(fake, USER_A)
    assert all(rows == [] for rows in document["unattached"].values())


def test_default_and_tables_format_still_return_flat_shape(http, fake):
    for params in (None, {"format": "tables"}):
        resp = http.get(EXPORT_PATH, headers=_auth(USER_A), params=params)
        assert resp.status_code == 200, params
        body = resp.json()
        assert set(body) == {"status", "tables"}, params
        assert body["status"] == "exported"
        assert [t["table"] for t in body["tables"]] == [s["table"] for s in EXPORT_STEPS]
        assert all(set(t) == {"table", "rows"} for t in body["tables"])
        assert "document" not in resp.text


def test_export_document_ignores_client_supplied_user_id(http, fake):
    before_b = copy.deepcopy(_owned_rows(fake, USER_B))
    resp = http.get(
        EXPORT_PATH, headers=_auth(USER_A), params={"format": "document", "user_id": USER_B}
    )
    assert resp.status_code == 200
    document = resp.json()["document"]
    assert {r["seed_owner"] for r in _doc_rows(document)} == {USER_A}
    assert count_rows(document) == _counts(fake, USER_A)
    assert USER_B not in resp.text
    with_body = http.request(
        "GET", EXPORT_PATH, headers=_auth(USER_A), params=DOC, json={"user_id": USER_B}
    )
    assert with_body.status_code == 200
    assert USER_B not in with_body.text
    assert _owned_rows(fake, USER_B) == before_b


def test_export_document_requires_authentication(http, fake):
    before = copy.deepcopy(fake.store)
    resp = http.get(EXPORT_PATH, params=DOC)
    assert resp.status_code == 401
    assert fake.ops == []
    assert fake.store == before


def test_export_document_invalid_format_is_422(http, fake):
    for value in ("nested", "", "json", "DOCUMENT"):
        resp = http.get(EXPORT_PATH, headers=_auth(USER_A), params={"format": value})
        assert resp.status_code == 422, value
    assert fake.ops == []


def test_export_document_builder_failure_is_generic_500(http, fake, monkeypatch, caplog, capsys):
    def boom(results):
        raise ValueError(DOC_CANARY)

    monkeypatch.setattr(me_router, "build_export_document", boom)
    caplog.set_level(logging.DEBUG)
    capsys.readouterr()
    resp = http.get(EXPORT_PATH, headers=_auth(USER_A), params=DOC)
    out = capsys.readouterr()
    assert resp.status_code == 500
    assert resp.json() == {"detail": "export_incomplete"}
    for needle in (DOC_CANARY, USER_A, USER_B, "ValueError", "trip_node", "user_tiers"):
        assert needle not in resp.text, needle
    warnings = [
        r for r in caplog.records if r.name == "travelbuddy" and r.levelno == logging.WARNING
    ]
    assert len(warnings) == 1, [r.getMessage() for r in warnings]
    message = warnings[0].getMessage()
    assert message.startswith("export incomplete (ValueError) request_id=")
    assert not message.endswith("request_id=unknown")
    assert DOC_CANARY not in message and USER_A not in message
    assert DOC_CANARY not in caplog.text
    assert DOC_CANARY not in out.out and DOC_CANARY not in out.err
    # The flat path does not call the builder, so it still succeeds.
    assert http.get(EXPORT_PATH, headers=_auth(USER_A)).status_code == 200


def test_export_document_execute_failure_still_generic_500(http, fake, caplog, capsys):
    fake.fail_on_read = "trip_node"
    caplog.set_level(logging.DEBUG)
    capsys.readouterr()
    resp = http.get(EXPORT_PATH, headers=_auth(USER_A), params=DOC)
    out = capsys.readouterr()
    assert resp.status_code == 500
    assert resp.json() == {"detail": "export_incomplete"}
    for needle in (CANARY, USER_A, USER_B, "RuntimeError", "trip_node"):
        assert needle not in resp.text, needle
    warnings = [
        r for r in caplog.records if r.name == "travelbuddy" and r.levelno == logging.WARNING
    ]
    assert len(warnings) == 1
    message = warnings[0].getMessage()
    assert message.startswith("export incomplete (RuntimeError) request_id=")
    assert CANARY not in message and CANARY not in caplog.text
    assert CANARY not in out.out and CANARY not in out.err


def test_export_document_returns_501_when_no_supabase_backend(monkeypatch):
    provider = importlib.import_module("services.db_provider")
    monkeypatch.setattr(provider, "IS_SUPABASE", False)
    built = []
    monkeypatch.setattr(me_router, "SupabaseExportBackend", lambda client: built.append(client))
    app.dependency_overrides.pop(get_export_backend, None)
    with TestClient(app, raise_server_exceptions=False) as client:
        resp = client.get(EXPORT_PATH, headers=_auth(USER_A), params=DOC)
    assert resp.status_code == 501
    assert resp.json() == {"detail": "export_unavailable"}
    assert built == []


def test_export_document_route_module_is_ascii():
    source = Path(me_router.__file__).read_text(encoding="utf-8")
    assert source.isascii()
