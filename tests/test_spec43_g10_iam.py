"""SPEC-43 Gap 10: administrator IAM on the debug ring.

/api/v1/debug/errors needs X-Debug-Admin-Token even when debug is on.
Debug off or an unusable token is 404. Traveller identity is never admin.
No widgets, no live Postgres.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from config.settings import settings
from main import app
from monitoring.error_log import error_log

URL = "/api/v1/debug/errors"
ADMIN = "g10-admin-canary-token"
HEADER = "X-Debug-Admin-Token"

client = TestClient(app, raise_server_exceptions=False)


@pytest.fixture()
def admin_on(monkeypatch):
    assert len(ADMIN) == 22
    monkeypatch.setattr(settings, "debug", True)
    monkeypatch.setattr(settings, "debug_admin_token", ADMIN)


@pytest.fixture(autouse=True)
def _ring():
    error_log.clear()
    error_log.record(
        request_id="rid-g10-iam",
        method="GET",
        path="/x",
        status=500,
        exc_type="RuntimeError",
        message="ring entry for iam tests",
    )
    yield
    error_log.clear()


def test_debug_errors_requires_admin_token(admin_on):
    bare = client.get(URL)
    assert bare.status_code == 401
    assert bare.json() == {"detail": "Unauthorized"}
    assert "errors" not in bare.json()

    ok = client.get(URL, headers={HEADER: ADMIN})
    assert ok.status_code == 200
    assert "errors" in ok.json() and ok.json()["count"] == 1

    wrong = client.get(URL, headers={HEADER: "wrong-token-not-the-canary"})
    assert wrong.status_code == 401
    assert "errors" not in wrong.json()

    same_len_wrong = client.get(URL, headers={HEADER: "x" * len(ADMIN)})
    assert same_len_wrong.status_code == 401


def test_debug_errors_rejects_debug_user_header(admin_on):
    r = client.get(URL, headers={"X-Debug-User-Id": "user-g10-iam"})
    assert r.status_code == 401
    assert "errors" not in r.json()

    r = client.get(
        URL,
        headers={"X-Debug-User-Id": "user-g10-iam", "Authorization": f"Bearer {ADMIN}"},
    )
    assert r.status_code == 401
    assert "errors" not in r.json()

    r = client.get(URL, headers={"X-Debug-User-Id": "user-g10-iam", HEADER: ADMIN})
    assert r.status_code == 200


def test_token_not_accepted_in_query_or_body(admin_on):
    assert client.get(URL, params={"X-Debug-Admin-Token": ADMIN, "token": ADMIN}).status_code == 401
    r = client.request("DELETE", URL, json={"X-Debug-Admin-Token": ADMIN})
    assert r.status_code == 401
    assert error_log.count() == 1


def test_debug_off_with_valid_token_is_404(monkeypatch):
    monkeypatch.setattr(settings, "debug", False)
    monkeypatch.setattr(settings, "debug_admin_token", ADMIN)
    r = client.get(URL, headers={HEADER: ADMIN})
    assert r.status_code == 404
    assert "errors" not in r.json()
    assert client.delete(URL, headers={HEADER: ADMIN}).status_code == 404


@pytest.mark.parametrize("configured", [None, "", "x" * 8, "y" * 15])
def test_unusable_token_setting_is_404_even_with_debug_on(monkeypatch, configured):
    monkeypatch.setattr(settings, "debug", True)
    monkeypatch.setattr(settings, "debug_admin_token", configured)
    sent = configured or "x" * 8
    r = client.get(URL, headers={HEADER: sent})
    assert r.status_code == 404
    assert "errors" not in r.json()
    assert client.delete(URL, headers={HEADER: sent}).status_code == 404
    assert error_log.count() == 1


def test_conftest_does_not_configure_admin_token(monkeypatch):
    from pathlib import Path

    conftest = (Path(__file__).resolve().parent / "conftest.py").read_text()
    assert "TB_DEBUG_ADMIN_TOKEN" not in conftest
    assert "debug_admin_token" not in conftest
    monkeypatch.setattr(settings, "debug_admin_token", None)
    assert client.get(URL, headers={HEADER: ADMIN}).status_code == 404


def test_provider_secret_cannot_double_as_admin_token(monkeypatch):
    reused = "sk-provider-key-reused-as-admin-0001"
    monkeypatch.setattr(settings, "debug", True)
    monkeypatch.setattr(settings, "litellm_api_key", reused)
    monkeypatch.setattr(settings, "debug_admin_token", reused)
    assert client.get(URL, headers={HEADER: reused}).status_code == 404


def test_delete_uses_the_same_gate(admin_on):
    assert client.delete(URL).status_code == 401
    assert client.delete(URL, headers={HEADER: "wrong-token-not-the-canary"}).status_code == 401
    assert client.delete(URL, headers={"X-Debug-User-Id": "user-g10-iam"}).status_code == 401
    assert error_log.count() == 1

    ok = client.delete(URL, headers={HEADER: ADMIN})
    assert ok.status_code == 200 and ok.json() == {"cleared": True}
    assert error_log.count() == 0
