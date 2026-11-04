"""SPEC-43 Gap 10 IAM: debug ring fails closed when the admin token is unset
(part A) and requires the X-Debug-Admin-Token header when it is set (part B).

Goes in through the real HTTP routes (R17): TestClient -> debug_router.
"""

import pytest
from fastapi.testclient import TestClient

from config.settings import settings
from main import app
from routers.debug_router import admin_token_configured

CANARY_TOKEN = "g10-admin-canary-token"
UNSET_TOKENS = (None, "", "x" * 8)
ADMIN_HEADERS = {"X-Debug-Admin-Token": CANARY_TOKEN}


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

    # Configured token: part B requires the admin header to read the ring.
    monkeypatch.setattr(settings, "debug_admin_token", CANARY_TOKEN)
    r = client.get("/api/v1/debug/errors", headers=ADMIN_HEADERS)
    assert r.status_code == 200
    assert "errors" in r.json()


def test_debug_errors_404_when_debug_off_even_with_token(monkeypatch):
    client = TestClient(app, raise_server_exceptions=False)
    monkeypatch.setattr(settings, "debug", False)
    monkeypatch.setattr(settings, "debug_admin_token", CANARY_TOKEN)
    assert client.get("/api/v1/debug/errors", headers=ADMIN_HEADERS).status_code == 404
    assert client.delete("/api/v1/debug/errors", headers=ADMIN_HEADERS).status_code == 404


# ---------------------------------------------------------------------------
# Part B: X-Debug-Admin-Token header required when the token is configured.
# ---------------------------------------------------------------------------


def _assert_unauthorized(r):
    assert r.status_code == 401, r.status_code
    body = r.json()
    assert body == {"detail": "Unauthorized"}
    assert "errors" not in body


@pytest.fixture
def admin_client(monkeypatch):
    monkeypatch.setattr(settings, "debug", True)
    monkeypatch.setattr(settings, "debug_admin_token", CANARY_TOKEN)
    return TestClient(app, raise_server_exceptions=False)


def test_debug_errors_requires_admin_token(admin_client):
    _assert_unauthorized(admin_client.get("/api/v1/debug/errors"))

    r = admin_client.get("/api/v1/debug/errors", headers=ADMIN_HEADERS)
    assert r.status_code == 200
    assert "errors" in r.json()

    _assert_unauthorized(
        admin_client.get(
            "/api/v1/debug/errors",
            headers={"X-Debug-Admin-Token": "wrong-token-not-the-canary"},
        )
    )


def test_debug_errors_rejects_debug_user_header(admin_client):
    _assert_unauthorized(
        admin_client.get("/api/v1/debug/errors", headers={"X-Debug-User-Id": "user-g10-iam"})
    )


@pytest.mark.parametrize(
    "kwargs",
    [
        {"headers": {"Authorization": f"Bearer {CANARY_TOKEN}"}},
        {"params": {"token": CANARY_TOKEN}},
        {"params": {"X-Debug-Admin-Token": CANARY_TOKEN}},
        {"headers": {"X-Debug-Admin-Token": CANARY_TOKEN[:-1]}},
        {"headers": {"X-Debug-Admin-Token": CANARY_TOKEN + "x"}},
        {"headers": {"X-Debug-Admin-Token": ""}},
    ],
)
def test_debug_errors_rejects_other_token_channels(admin_client, kwargs):
    _assert_unauthorized(admin_client.get("/api/v1/debug/errors", **kwargs))


def test_debug_errors_delete_requires_admin_token(admin_client):
    _assert_unauthorized(admin_client.delete("/api/v1/debug/errors"))
    _assert_unauthorized(
        admin_client.delete("/api/v1/debug/errors", headers={"X-Debug-User-Id": "user-g10-iam"})
    )
    r = admin_client.delete("/api/v1/debug/errors", headers=ADMIN_HEADERS)
    assert r.status_code == 200
    assert r.json() == {"cleared": True}
