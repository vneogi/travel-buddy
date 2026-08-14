"""Regression tests for user tier endpoints.

The UserTier(**user_data) bug (commit #47) caused every authenticated endpoint
to 500 because the in-memory dict included `last_reset_date` which isn't a
UserTier field. These tests lock in the fix.
"""
import pytest
from fastapi.testclient import TestClient

from main import app
from tests.conftest import auth


@pytest.fixture
def client():
    return TestClient(app)


class TestUserStatus:
    """GET /api/v1/user/status -- the endpoint that was 500-ing."""

    def test_user_status_returns_200_and_tier(self, client):
        """Regression: UserTier(**user_data) with extra fields -> 500."""
        r = client.get("/api/v1/user/status", headers=auth("regression-user-1"))
        assert r.status_code == 200
        data = r.json()
        assert data["tier"] == "free"
        assert "daily_reroutes_remaining" in data
        assert "max_daily_reroutes" in data

    def test_user_status_new_user_creates_free_tier(self, client):
        """First call for an unknown user should auto-create as free."""
        r = client.get("/api/v1/user/status", headers=auth("brand-new-user"))
        assert r.status_code == 200
        body = r.json()
        assert body["tier"] == "free"
        assert body["daily_reroutes_remaining"] == body["max_daily_reroutes"]

    def test_user_status_requires_auth(self, client):
        """No auth header -> 401 or 403 or 500 (misconfiguration)."""
        r = client.get("/api/v1/user/status")
        # Without X-Debug-User-Id, should not return 200
        assert r.status_code != 200

    def test_trip_create_returns_200_not_500(self, client):
        """Regression: create_trip calls get_or_create_user internally."""
        r = client.post(
            "/api/v1/trip/create",
            json={"start_date": "2026-08-07T09:00:00Z"},
            headers=auth("regression-user-2"),
        )
        # Should NOT be 500 (the old bug). 200 or 201 expected.
        assert r.status_code in (200, 201), f"Got {r.status_code}: {r.text}"
        data = r.json()
        assert "trip_id" in data

    def test_user_status_multiple_calls_idempotent(self, client):
        """Calling status twice for same user should be stable."""
        headers = auth("idempotent-user")
        r1 = client.get("/api/v1/user/status", headers=headers)
        r2 = client.get("/api/v1/user/status", headers=headers)
        assert r1.status_code == 200
        assert r2.status_code == 200
        assert r1.json() == r2.json()
