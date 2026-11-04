"""SPEC-43 Gap 10 part A: debug ring fails closed when the admin token is unset.

Goes in through the real HTTP routes (R17): TestClient -> debug_router.
"""

import pytest
from fastapi.testclient import TestClient

from config.settings import settings
from main import app
from routers.debug_router import admin_token_configured

CANARY_TOKEN = "g10-admin-canary-token"
UNSET_TOKENS = (None, "", "x" * 8)


def test_canary_token_is_exactly_22_chars():
    assert len(CANARY_TOKEN) == 22
    assert admin_token_configured(CANARY_TOKEN)


@pytest.mark.parametrize("token", [None, "", "   ", "x" * 8, " " * 20, "a" * 15])
def test_admin_token_configured_rejects_short_or_empty(token):
    assert admin_token_configured(token) is False


def test_debug_errors_404_when_admin_token_unset(monkeypatch):
    client = TestClient(app, raise_server_exceptions=False)
    monkeypatch.setattr(settings, "debug", True)

    for token in UNSET_TOKENS:
        monkeypatch.setattr(settings, "debug_admin_token", token)
        assert admin_token_configured(settings.debug_admin_token) is False
        r = client.get("/api/v1/debug/errors")
        assert r.status_code == 404, (token, r.status_code)
        body = r.json()
        assert "errors" not in body, token
        assert body == {"detail": "Not found"}

        d = client.delete("/api/v1/debug/errors")
        assert d.status_code == 404, (token, d.status_code)
        assert "cleared" not in d.json()

    # Configured token: part A keeps the old unauthenticated dump (no header).
    # Part B will require X-Debug-Admin-Token and change this assertion.
    monkeypatch.setattr(settings, "debug_admin_token", CANARY_TOKEN)
    r = client.get("/api/v1/debug/errors")
    assert r.status_code == 200
    assert "errors" in r.json()


def test_debug_errors_404_when_debug_off_even_with_token(monkeypatch):
    client = TestClient(app, raise_server_exceptions=False)
    monkeypatch.setattr(settings, "debug", False)
    monkeypatch.setattr(settings, "debug_admin_token", CANARY_TOKEN)
    assert client.get("/api/v1/debug/errors").status_code == 404
    assert client.delete("/api/v1/debug/errors").status_code == 404
