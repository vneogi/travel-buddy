from tests.conftest import auth


def test_health_is_public(client):
    assert client.get("/api/v1/health").status_code == 200


def test_user_status_requires_auth(client):
    assert client.get("/api/v1/user/status").status_code == 401


def test_user_status_with_dev_auth(client):
    r = client.get("/api/v1/user/status", headers=auth("u1"))
    assert r.status_code == 200
    assert r.json()["user_id"] == "u1"
    assert r.json()["tier"] == "free"


def test_trip_ownership_enforced(client):
    trip_id = client.post(
        "/api/v1/trip/create",
        headers=auth("u1"),
        json={"start_date": "2026-08-05T09:00:00"},
    ).json()["trip_id"]
    assert client.get(f"/api/v1/trip/{trip_id}", headers=auth("u1")).status_code == 200
    # A different user must NOT be able to read it.
    assert client.get(f"/api/v1/trip/{trip_id}", headers=auth("u2")).status_code == 403


def test_free_upgrade_endpoint_removed(client):
    r = client.post("/api/v1/user/u1/upgrade", headers=auth("u1"))
    assert r.status_code in (404, 405)


def test_debug_header_cannot_override_real_jwt(client, monkeypatch):
    """With a JWT secret configured, X-Debug-User-Id must be ignored (401),
    never trusted. Guards against the auth-bypass regression where debug
    header was checked BEFORE the JWT secret, allowing anyone to impersonate
    any user by sending a single header."""
    import sys

    settings_module = sys.modules["config.settings"]
    monkeypatch.setattr(settings_module.settings, "supabase_jwt_secret", "test-secret-value")
    r = client.get(
        "/api/v1/user/status",
        headers={"X-Debug-User-Id": "attacker"},
    )
    # The debug header must NOT grant access when a JWT secret is set
    assert r.status_code == 401, (
        f"SECURITY BUG: X-Debug-User-Id bypassed JWT auth! Got {r.status_code}"
    )


def test_debug_header_cannot_override_jwks(client, monkeypatch):
    """SPEC-43 G1: with JWKS configured, X-Debug-User-Id is never trusted."""
    import sys

    s = sys.modules["config.settings"].settings
    monkeypatch.setattr(
        s, "supabase_jwks_url", "https://p.supabase.co/auth/v1/.well-known/jwks.json"
    )
    monkeypatch.setattr(s, "supabase_jwt_iss", "https://p.supabase.co/auth/v1")
    r = client.get("/api/v1/user/status", headers={"X-Debug-User-Id": "attacker"})
    assert r.status_code == 401


def test_anonymous_header_rejected_even_when_allowed(client, monkeypatch):
    """SPEC-43 G1: TB_ALLOW_ANONYMOUS is a no-op; Anonymous <uuid> is 401."""
    import sys
    import uuid

    s = sys.modules["config.settings"].settings
    monkeypatch.setattr(s, "allow_anonymous", True)
    r = client.get("/api/v1/user/status", headers={"Authorization": f"Anonymous {uuid.uuid4()}"})
    assert r.status_code == 401
