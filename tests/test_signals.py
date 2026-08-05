"""Tests for signal capture endpoint (SPEC-01 Part B).

Verifies:
1. Valid signal -> 200, accepted:1
2. Idempotency: re-POST same signal_id -> 200, duplicates:1, still one row
3. Unknown signal_type -> 422
4. No auth -> 401
"""

import pytest
from fastapi.testclient import TestClient

from main import app
from services.database_service import db_service

client = TestClient(app)

# Auth header for debug mode (TB_SUPABASE_JWT_SECRET unset + TB_DEBUG=true)
DEBUG_USER = "11111111-1111-1111-1111-111111111111"
AUTH_HEADERS = {"X-Debug-User-Id": DEBUG_USER}


@pytest.fixture(autouse=True)
def reset_signals():
    """Clear signal store between tests."""
    db_service._signals.clear()
    yield


class TestSignalIngest:
    """POST /api/v1/signals"""

    def _make_signal(self, signal_id="aaaaaaaa-1111-2222-3333-444444444444",
                     signal_type="user_loved", place_ref="dubai-mall"):
        return {
            "signal_id": signal_id,
            "signal_type": signal_type,
            "place_ref": place_ref,
            "value_text": "loved",
            "captured_at": "2026-08-05T14:30:00Z",
            "trip_id": "trip-001",
        }

    def test_valid_signal_accepted(self):
        """A valid user_loved signal is accepted."""
        resp = client.post(
            "/api/v1/signals",
            json={"signals": [self._make_signal()]},
            headers=AUTH_HEADERS,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["accepted"] == 1
        assert data["duplicates"] == 0

        # Verify it's stored
        assert db_service.get_signals_count() == 1
        stored = db_service.get_signal("aaaaaaaa-1111-2222-3333-444444444444")
        assert stored is not None
        assert stored["user_id"] == DEBUG_USER
        assert stored["signal_type"] == "user_loved"
        assert stored["place_ref"] == "dubai-mall"

    def test_idempotency_duplicate_signal_id(self):
        """Re-posting the same signal_id is a 200 no-op, not a duplicate row."""
        sig = self._make_signal()
        # First post
        resp1 = client.post(
            "/api/v1/signals",
            json={"signals": [sig]},
            headers=AUTH_HEADERS,
        )
        assert resp1.status_code == 200
        assert resp1.json()["accepted"] == 1

        # Second post — same signal_id
        resp2 = client.post(
            "/api/v1/signals",
            json={"signals": [sig]},
            headers=AUTH_HEADERS,
        )
        assert resp2.status_code == 200
        assert resp2.json()["accepted"] == 0
        assert resp2.json()["duplicates"] == 1

        # Still only one row
        assert db_service.get_signals_count() == 1

    def test_batch_multiple_signals(self):
        """A batch with multiple distinct signals records all of them."""
        signals = [
            self._make_signal(signal_id="sig-001", place_ref="burj-khalifa"),
            self._make_signal(signal_id="sig-002", place_ref="dubai-mall"),
            self._make_signal(signal_id="sig-003", place_ref="la-mer"),
        ]
        resp = client.post(
            "/api/v1/signals",
            json={"signals": signals},
            headers=AUTH_HEADERS,
        )
        assert resp.status_code == 200
        assert resp.json()["accepted"] == 3
        assert resp.json()["duplicates"] == 0
        assert db_service.get_signals_count() == 3

    def test_unknown_signal_type_rejected(self):
        """An unknown signal_type gets a 422."""
        sig = self._make_signal(signal_type="totally_fake_type")
        resp = client.post(
            "/api/v1/signals",
            json={"signals": [sig]},
            headers=AUTH_HEADERS,
        )
        assert resp.status_code == 422
        assert "totally_fake_type" in resp.json()["detail"]

    def test_no_auth_rejected(self):
        """No auth header -> 401."""
        sig = self._make_signal()
        resp = client.post(
            "/api/v1/signals",
            json={"signals": [sig]},
            # No headers — no auth
        )
        assert resp.status_code == 401

    def test_user_id_from_token_not_body(self):
        """user_id in the stored signal comes from the auth token, not the payload."""
        sig = self._make_signal()
        # SignalIn model does NOT have a user_id field — this tests that
        # the server fills it from auth, not from any client-supplied value
        resp = client.post(
            "/api/v1/signals",
            json={"signals": [sig]},
            headers={"X-Debug-User-Id": "attacker-id-999"},
        )
        assert resp.status_code == 200
        stored = db_service.get_signal("aaaaaaaa-1111-2222-3333-444444444444")
        assert stored["user_id"] == "attacker-id-999"  # gets whatever token says
        # Key point: there's no way for a client to set user_id to someone
        # else's — the token IS the identity. No IDOR.
